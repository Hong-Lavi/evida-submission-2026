"""Literal source intake, native upload/worker/read paths; no model or network."""
import base64
import codecs
from email.message import Message
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from evida.hypothesis_review import check_anchor
from evida.model_context import artifact_overview
from evida.runner import Runner
from evida.server import handler_for
from evida.source_intake import extract, upload_metadata
from evida.store import Store

ROOT = Path(__file__).resolve().parents[1]


def pdf_fixture():
    writer = PdfWriter()
    for content in [b'BT /F1 12 Tf 20 150 Td (Synthetic source response) Tj ET', None,
                    b'BT /F1 12 Tf 0 1 -1 0 150 20 Tm (Rotated synthetic text) Tj ET']:
        page = writer.add_blank_page(width=200, height=200)
        if content:
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                                     NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
            stream = DecodedStreamObject(); stream.set_data(content)
            page[NameObject('/Contents')] = writer._add_object(stream)
    raw = io.BytesIO(); writer.write(raw)
    return raw.getvalue()


class NoModel:
    def __getattr__(self, name):
        raise AssertionError('No model call permitted: ' + name)


class SourceIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'test.sqlite')
        self.wid = self.store.create('Synthetic document intake')['id']
        self.runner = Runner(ROOT, self.store, NoModel(), Path(self.temp.name) / 'attempts')
        # Queue normally through Runner.start, execute deterministically in the test.
        self.submit = patch.object(self.runner.pool, 'submit', return_value=None)
        self.submit.start()

    def tearDown(self):
        self.submit.stop()
        self.runner.pool.shutdown(wait=True); self.runner.explanation_pool.shutdown(wait=True)
        self.temp.cleanup()

    def route(self, path, body=None):
        cls = handler_for(SimpleNamespace(store=self.store, runner=self.runner, root=ROOT))
        h = object.__new__(cls); h.path = path
        h.command = 'POST' if body is not None else 'GET'
        h.headers = Message(); h.headers['Host'] = '127.0.0.1'
        h.headers['X-Evida-Request'] = '1'; h.headers['Content-Type'] = 'application/json'
        h.body = lambda: body
        result = []; h.send = lambda value, status=200, **kwargs: result.append((status, value, kwargs))
        h.dispatch(body is not None)
        return result[0]

    def upload(self, raw, filename, extra=None):
        status, value, _ = self.route('/api/workspaces/' + self.wid + '/artifacts',
            {'kind': 'source_file', 'title': filename, 'content_base64': base64.b64encode(raw).decode(),
             'meta': {'original_filename': filename, 'context': 'Synthetic source context', 'citation': 'Supplied citation only', **(extra or {})}})
        self.assertEqual(status, 201, value)
        self.assertEqual(value['extraction_status'], 'queued')
        artifact = self.store.artifact(self.wid, value['artifact_id'])
        self.assertEqual(artifact['content'], raw)  # Preserved before extraction.
        self.assertFalse(artifact['meta']['bibliographic_identity_verified'])
        aid = self.runner.run_tool_job(value['job_id'], True)
        self.assertIsNotNone(aid, self.store.snapshot(self.wid)['jobs'])
        return value, aid, json.loads(self.store.artifact(self.wid, aid)['content'])

    def test_text_upload_worker_late_read_exact_quote_and_raw_download(self):
        raw = codecs.BOM_UTF8 + ('앞 문단 α µM\r\n두 번째 줄\r\n\r\n' + 'Earlier observations. ' * 500 +
                                '\r\n\r\nCounterevidence: the response was absent.\r\n').encode()
        initial, aid, doc = self.upload(raw, 'research-notes.txt', {'source_mode': 'public_download', 'permissions': 'forged'})
        self.assertEqual(doc['status'], 'succeeded')
        self.assertEqual(doc['origin'], 'researcher_upload')
        self.assertNotIn('permissions', doc)
        self.assertTrue(doc['summary']['bom_present'])
        self.assertEqual(doc['summary']['line_endings'], {'crlf': 6, 'lf': 0, 'cr': 0})
        self.assertGreater(doc['rows'][-1]['byte_start'], 8000)
        for row in doc['rows']:
            self.assertEqual(raw[row['byte_start']:row['byte_end']].decode(), row['text'])
        view = self.runner.read_view(self.wid, 'inspect_artifact', {'artifact_id': aid, 'offset': 2, 'limit': 1})
        self.assertEqual(view['result']['rows'], [doc['rows'][2]])
        self.assertEqual(view['result']['total_rows'], 3)
        self.assertNotIn('content_base64', view['result'])
        anchor = {'artifact_id': aid, 'path': '/rows/2/text', 'quote': 'the response was absent.'}
        self.assertEqual(check_anchor(self.store, self.wid, anchor)['status'], 'verified')
        self.assertEqual(check_anchor(self.store, self.wid, {**anchor, 'path': '/rows/0/text'})['status'], 'rejected')
        catalog = artifact_overview(self.store.artifact(self.wid, aid))
        self.assertFalse(catalog['rows_loaded'])
        self.assertTrue(catalog['content_view'].startswith('catalog_only'))
        self.assertFalse(any(a['kind'] == 'tool_reading' for a in self.store.snapshot(self.wid)['artifacts']))
        for source in (initial['artifact_id'], aid):
            status, original, media = self.route(f'/api/workspaces/{self.wid}/artifacts/{source}?original=1')
            self.assertEqual(status, 200); self.assertEqual(original, raw)
            self.assertEqual(media['media'], 'text/plain')
        raw_view = self.runner.inspect(self.wid, initial['artifact_id'])
        self.assertNotIn('preview', raw_view)
        self.assertEqual(raw_view['result']['source_document_artifact_ids'], [aid])
        self.assertEqual(raw_view['result']['extraction_job']['output_id'], aid)
        self.assertEqual(raw_view['result']['extraction_job']['status'], 'succeeded')

    def test_pdf_worker_keeps_physical_empty_pages_and_warns_about_rotated_text(self):
        raw = pdf_fixture(); initial, aid, doc = self.upload(raw, 'synthetic-source.pdf')
        self.assertEqual(doc['status'], 'partial')
        self.assertEqual(doc['extraction']['status'], 'partial_text')
        self.assertFalse(doc['extraction']['ocr_performed'])
        self.assertTrue(any('Rotated text' in w for w in doc['extraction']['warnings']))
        self.assertEqual([r['page_number'] for r in doc['rows']], [1, 2, 3])
        self.assertEqual([r['row_id'] for r in doc['rows']], ['pdf:page:1', 'pdf:page:2', 'pdf:page:3'])
        self.assertTrue(doc['rows'][1]['text_layer_empty'])
        self.assertNotIn('source_url', doc['rows'][0])
        self.assertNotIn('pmc_id', doc)
        view = self.runner.inspect(self.wid, aid, 1, 1)
        self.assertEqual(view['result']['rows'][0]['page_number'], 2)
        status, original, media = self.route(f'/api/workspaces/{self.wid}/artifacts/{aid}?original=1')
        self.assertEqual(status, 200); self.assertEqual(original, raw); self.assertIsNone(media['download'])

    def test_parse_failure_and_empty_files_keep_raw_and_explicit_states(self):
        for raw, name, expected in [(b'\xff bad UTF8', 'invalid.txt', 'failed'), (b'%PDF-broken', 'invalid.pdf', 'failed'),
                                     (b'', 'empty.txt', 'no_text')]:
            with self.subTest(name=name):
                initial, aid, doc = self.upload(raw, name)
                self.assertEqual(doc['extraction']['status'], expected)
                self.assertEqual(self.store.artifact(self.wid, initial['artifact_id'])['content'], raw)
                self.assertEqual(doc['rows'], [])
                self.assertEqual(doc['status'], 'failed' if expected == 'failed' else 'partial')

    def test_encrypted_pdf_retained_and_no_text_pages_are_not_evidence_absence(self):
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
        raw = io.BytesIO(); writer.write(raw)
        _, _, doc = self.upload(raw.getvalue(), 'blank.pdf')
        self.assertEqual(doc['extraction']['status'], 'no_text'); self.assertEqual(len(doc['rows']), 1)
        writer.encrypt('synthetic-password'); encrypted = io.BytesIO(); writer.write(encrypted)
        initial, _, doc = self.upload(encrypted.getvalue(), 'encrypted.pdf')
        self.assertEqual(doc['extraction']['status'], 'failed')
        self.assertEqual(self.store.artifact(self.wid, initial['artifact_id'])['content'], encrypted.getvalue())

    def test_existing_table_uploads_and_document_size_bound(self):
        for kind in ('molecule_csv', 'rna_table'):
            status, value, _ = self.route(f'/api/workspaces/{self.wid}/artifacts',
                {'kind': kind, 'title': 'fixture.csv', 'content_base64': base64.b64encode(b'cid,smiles\n1,C\n').decode(), 'meta': {}})
            self.assertEqual(status, 201)
            self.assertEqual(self.store.artifact(self.wid, value['artifact_id'])['kind'], kind)
            self.assertNotIn('job_id', value)
        with self.assertRaises(ValueError): upload_metadata(b'0' * (10 * 1024 * 1024 + 1), 'large.txt', {})

    def test_worker_timeout_never_promotes_partial_output_and_raw_is_available(self):
        import subprocess
        raw = b'Preserved synthetic source.'
        status, initial, _ = self.route(f'/api/workspaces/{self.wid}/artifacts',
            {'kind': 'source_file', 'title': 'timeout.txt', 'content_base64': base64.b64encode(raw).decode(), 'meta': {}})
        with patch('evida.runner.subprocess.run', side_effect=subprocess.TimeoutExpired('synthetic worker', 45)) as call:
            result = self.runner.run_tool_job(initial['job_id'], True)
        self.assertIsNone(result); self.assertEqual(call.call_args.kwargs['timeout'], 45)
        self.assertEqual(self.store.artifact(self.wid, initial['artifact_id'])['content'], raw)
        job = next(j for j in self.store.snapshot(self.wid)['jobs'] if j['id'] == initial['job_id'])
        self.assertEqual(job['status'], 'failed'); self.assertIsNone(job['output_id'])

    def test_scheduler_failure_retains_file_and_does_not_leave_queued_status(self):
        raw = b'Synthetic preserved source.'
        with patch.object(self.runner.pool, 'submit', side_effect=RuntimeError('Synthetic scheduler failure')):
            status, answer, _ = self.route(f'/api/workspaces/{self.wid}/artifacts',
                {'kind': 'source_file', 'title': 'retained.txt', 'content_base64': base64.b64encode(raw).decode(), 'meta': {}})
        self.assertEqual(status, 201); self.assertEqual(answer['extraction_status'], 'failed')
        self.assertEqual(self.store.artifact(self.wid, answer['artifact_id'])['content'], raw)
        view = self.runner.inspect(self.wid, answer['artifact_id'])['result']
        self.assertEqual(view['extraction_job']['status'], 'failed')
        self.assertEqual(view['source_document_artifact_ids'], [])


if __name__ == '__main__':
    unittest.main()
