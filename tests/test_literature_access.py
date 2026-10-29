import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, Mock
from evida import literature_access as access
from evida.literal_source_binding import row_binding

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'evida'))
import literature_access_worker as worker


class LiteratureAccessTests(unittest.TestCase):
    def test_credentials_auth_schemes_and_ports_are_rejected(self):
        for url in ('https://x:y@example.org/a', 'https://example.org/a?api_key=secret',
                    'https://example.org/login', 'http://example.org/a', 'file:///tmp/a',
                    'https://example.org:8080/a', 'https://localhost/a',
                    'https://example.org/a?sig=SYNTHETIC', 'https://example.org/a?auth=SYNTHETIC',
                    'https://example.org/a#access_token=SYNTHETIC'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                access.validate_public_url(url)

    def test_research_loop_accepts_read_page_but_rejects_search_and_links(self):
        from evida.research_loop import check_anchor
        raw = b'<html>source</html>'; text = 'Exact source statement.'
        value = {'source': {'sha256': hashlib.sha256(raw).hexdigest()},
            'original_response_base64': base64.b64encode(raw).decode(),
            'rows': [{'kind': 'paragraph', 'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}]}
        artifact = {'kind': 'public_research_page', 'id': 'a', 'sha256': 'stored', 'content': json.dumps(value).encode()}
        store = Mock(); store.artifact.return_value = artifact
        self.assertEqual(check_anchor(store, 'w', {'artifact_id': 'a', 'row_index': 0, 'quote': text})['status'], 'verified')
        artifact['kind'] = 'public_web_search'
        self.assertNotEqual(check_anchor(store, 'w', {'artifact_id': 'a', 'row_index': 0, 'quote': text})['status'], 'verified')
        artifact['kind'] = 'public_research_page'; value['rows'][0]['kind'] = 'source_link'
        artifact['content'] = json.dumps(value).encode()
        self.assertNotEqual(check_anchor(store, 'w', {'artifact_id': 'a', 'row_index': 0, 'quote': text})['status'], 'verified')

    def test_pdf_expansion_stops_and_reports_partial(self):
        class Document:
            is_encrypted = False
            pages = [Mock(extract_text=lambda: 'A'*1000) for _ in range(100)]
        with patch.dict(sys.modules, {'pypdf': types.SimpleNamespace(PdfReader=lambda *a, **kw: Document(), __version__='fixture')}), \
                patch.object(worker, 'MAX_TEXT_BYTES', 1500):
            value = worker.extract_document(b'%PDF-SYNTHETIC', 'https://example.org/a', True)
        self.assertEqual(value['status'], 'partial'); self.assertTrue(value['extraction_truncated'])
        self.assertEqual(sum(len(r['text']) for r in value['rows']), 1500)
        self.assertEqual(len(value['rows']), 2)

    def test_denied_and_challenge_do_not_launch_chrome(self):
        for status, raw in [('access_denied', b'403'),
                            ('response_received', b'<html><title>Client Challenge</title></html>')]:
            result = {'acquisition_status': status, 'source': {'content_encoding': ''},
                      'original_response_base64': base64.b64encode(raw).decode()}
            with tempfile.TemporaryDirectory() as work, patch.object(worker, 'fetch', return_value=result), \
                    patch.object(worker, 'render') as render:
                body = worker.acquire('public_research_page', {'url': 'https://example.org/paper',
                    'render_mode': 'chrome'}, '/usr/bin/google-chrome', Path(work))
                self.assertEqual(body['status'], 'failed'); render.assert_not_called()

    def test_dns_failure_never_opens_connection(self):
        with patch.object(worker, '_addresses', side_effect=ValueError('private')), \
                patch.object(worker, 'PinnedHTTPS') as connection:
            result = worker.fetch('https://private.example.org/a')
            self.assertEqual(result['acquisition_status'], 'network_or_policy_failure')
            connection.assert_not_called()

    def test_public_redirect_rechecks_dns_and_preserves_first_attempt(self):
        response = Mock(status=302); response.read.return_value = b'redirect'
        response.getheader.side_effect = lambda key, default='': {'Location': 'https://private.example.org/paper'}.get(key, default)
        response.getheaders.return_value = []
        connection = Mock(); connection.getresponse.return_value = response
        with patch.object(worker, '_addresses', side_effect=[['8.8.8.8'], ValueError('private')]), \
                patch.object(worker, 'PinnedHTTPS', return_value=connection) as open_connection:
            result = worker.fetch('https://example.org/paper')
            self.assertEqual(open_connection.call_count, 1)
            self.assertEqual(result['source']['access_attempts'][0]['http_status'], 302)
            self.assertEqual(result['acquisition_status'], 'network_or_policy_failure')

    def test_search_results_are_links_not_read_articles(self):
        raw = b'<rss><channel><item><title>Paper</title><link>https://example.org/paper</link><description>Snippet</description></item></channel></rss>'
        result = {'acquisition_status': 'response_received', 'source': {'resolved_url': 'https://www.bing.com/search', 'content_encoding': ''},
                  'original_response_base64': base64.b64encode(raw).decode()}
        with tempfile.TemporaryDirectory() as work, patch.object(worker, 'fetch', return_value=result):
            body = worker.acquire('public_web_search', {'query': 'research', 'engine': 'bing'}, '', Path(work))
        self.assertFalse(body['full_document_read'])
        self.assertFalse(body['rows'][0]['destination_retrieved'])
        self.assertTrue(body['rows'][0]['search_snippet_is_not_claim_support'])

    def test_publisher_signed_download_is_followed_without_logging_signature(self):
        signed = 'https://objects.example.org/paper.pdf?X-Amz-Credential=temporary-id&X-Amz-Signature=temporary-signature&X-Amz-Expires=30'
        first = Mock(status=302); first.read.return_value = b''
        first.getheader.side_effect = lambda key, default='': {'Location': signed}.get(key, default)
        first.getheaders.return_value = []
        second = Mock(status=200); second.read.return_value = b'%PDF-public'
        second.getheader.side_effect = lambda key, default='': {'Content-Type': 'application/pdf'}.get(key, default)
        second.getheaders.return_value = [('Content-Type', 'application/pdf')]
        connection = Mock(); connection.getresponse.side_effect = [first, second]
        with patch.object(worker, '_addresses', return_value=['8.8.8.8']), \
                patch.object(worker, 'PinnedHTTPS', return_value=connection):
            result = worker.fetch('https://publisher.example.org/supplement')
        self.assertEqual(result['acquisition_status'], 'response_received')
        self.assertNotIn('temporary-signature', json.dumps(result))
        self.assertNotIn('temporary-id', json.dumps(result))
        self.assertEqual(result['source']['resolved_url'], 'https://objects.example.org/paper.pdf')
        with self.assertRaises(ValueError): access.validate_public_url(signed)

    def test_candidate_anchor_rejects_unvisited_links_and_corrupt_dom(self):
        raw = b'<html>source</html>'; text = 'C1 was compared with a control.'
        value = {'source': {'sha256': hashlib.sha256(raw).hexdigest()},
            'original_response_base64': base64.b64encode(raw).decode(),
            'rows': [{'kind': 'source_link', 'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}]}
        artifact = {'kind': 'public_research_page', 'id': 'a', 'sha256': 'stored'}
        with self.assertRaises(ValueError): row_binding(None, 'w', artifact, value, 0)
        value['rows'][0]['kind'] = 'paragraph'
        value.update(original_rendered_html_base64=base64.b64encode(raw).decode(), browser={'rendered_sha256': 'corrupt'})
        with self.assertRaises(ValueError): row_binding(None, 'w', artifact, value, 0)


if __name__ == '__main__': unittest.main()
