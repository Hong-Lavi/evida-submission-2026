"""Actual runner → article worker → cached figure → read-only UI projection.

The article and ZIP below are explicit synthetic transport fixtures. No network,
model or live Store is used. The worker and publication boundary are real.
"""
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from evida import science
from evida.article_figures import cache_name, retrieve_for_article, _entries
from evida.discovery import anchored_figures
from evida.runner import Runner
from evida.store import Store

PNG = b'\x89PNG\r\n\x1a\n' + b'synthetic-image' * 80


def article():
    return {'status': 'succeeded', 'pmc_id': 'PMC123', 'original_xml': '<synthetic/>',
            'source': {'sha256': 'synthetic-source-hash'},
            'rows': [{'row_id': str(i), 'kind': 'paragraph', 'text': 'Synthetic paragraph'}
                     for i in range(38)] + [{'row_id': 'PMC123:block:38', 'xml_id': 'F1',
                'kind': 'fig', 'section': 'Body / Results', 'text': 'Figure 1 Synthetic caption',
                'source_url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC123/#F1',
                'asset_references': [{'href': 'declared.png'}]}]}


class FigureConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'isolated.sqlite3')
        self.wid = self.store.create('Synthetic article figure connection')['id']
        self.runner = Runner.__new__(Runner)
        self.runner.root, self.runner.store = self.root, self.store
        self.runner.attempts_root = self.root / 'attempts'
        self.runner.science_lock = threading.Lock()
        self.runner.science_python = self.root / 'fixture-worker'
        self.runner.native_library_directory = None
        self.runner.fingerprint = {'test_fixture': True}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('declared.png', PNG)
            archive.writestr('not-in-article.png', PNG)
        self.archive = buffer.getvalue()

    def run_article(self, side_effect=None):
        def worker(command, **kwargs):
            with patch('sys.argv', ['science', command[-1]]):
                science.main()
            return SimpleNamespace(returncode=0)
        jid = self.store.enqueue(self.wid, self.store.snapshot(self.wid)['rev'],
                                 'article', {'pmc_id': 'PMC123'})
        with patch('evida.runner.subprocess.run', side_effect=worker), \
                patch('evida.public_evidence.read_article', return_value=article()), \
                patch('evida.science.fetch', side_effect=side_effect,
                      return_value=(self.archive, {'url': 'synthetic-transport'})) as fetch, \
                patch('evida.interaction.dispatch_followthrough'):
            aid = self.runner.run_tool_job(jid, False)
        value = json.loads(self.store.artifact(self.wid, aid)['content'])
        return aid, value, fetch

    def test_successful_article_automatically_supplies_anchored_figure(self):
        aid, value, fetch = self.run_article()
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.kwargs, {'timeout': 25, 'max_download': 8 * 1024 * 1024})
        self.assertEqual(value['status'], 'succeeded')
        self.assertEqual(value['figure_retrieval']['status'], 'succeeded')
        self.assertEqual(value['original_xml'], '<synthetic/>')
        self.assertEqual(value['rows'], article()['rows'])
        self.assertEqual((self.root / '.figure-cache' / cache_name('PMC123', 'declared.png')).read_bytes(), PNG)
        self.assertFalse((self.root / '.figure-cache' / cache_name('PMC123', 'not-in-article.png')).exists())
        figures = anchored_figures(self.store, self.wid,
            {'clauses': [{'anchor': {'artifact_id': aid, 'quote': 'Synthetic paragraph'}}]},
            cache=self.root / '.figure-cache')
        self.assertEqual(figures[0]['artifact_id'], aid)
        self.assertEqual(figures[0]['source_url'], article()['rows'][-1]['source_url'])
        with patch('evida.science.fetch', side_effect=AssertionError('GET must not fetch')), \
                patch('evida.structure_depiction.attach', side_effect=lambda value, *args: value):
            view = self.runner.inspect(self.wid, aid, depict=True)['result']
        self.assertEqual(len(view['rows']), 30)
        self.assertEqual(len(view['figures']), 1, 'figure navigation is independent of row pagination')
        self.assertTrue(view['figures'][0]['available'][0]['cached'])
        _, second, again = self.run_article()
        self.assertEqual(again.call_count, 0)
        self.assertTrue(second['figure_retrieval']['reused_receipt'])

    def test_archive_expansion_and_article_figure_count_are_bounded(self):
        self.assertEqual(_entries(self.archive, {'declared.png'}, max_entry_bytes=32), {})
        value = article()
        value['rows'] = [dict(value['rows'][-1], xml_id=f'F{i}',
            asset_references=[{'href': f'declared-{i}.png'}]) for i in range(12)]
        with patch('evida.article_figures.fetch_figures', return_value={
                'files': [], 'not_returned': ['declared-0.png']}) as fetch:
            record = retrieve_for_article(value, self.root / '.figure-cache', None)
        self.assertEqual(record['declared_figures'], 12)
        self.assertEqual(len(fetch.call_args.args[1]), 8)
        self.assertEqual(record['status'], 'not_returned')

    def test_absent_declared_filename_creates_no_download_or_visual_claim(self):
        value = article()
        value['rows'][-1]['asset_references'] = []
        with patch('evida.article_figures.fetch_figures') as fetch:
            record = retrieve_for_article(value, self.root / '.figure-cache', None)
        fetch.assert_not_called()
        self.assertEqual(record['status'], 'no_declared_browser_image')
        self.assertFalse(record['visual_interpretation'])

    def test_failed_figure_fetch_preserves_article_and_does_not_repeat(self):
        _, value, fetch = self.run_article(TimeoutError('synthetic timeout'))
        self.assertEqual(value['status'], 'succeeded')
        self.assertEqual(value['figure_retrieval']['status'], 'failed')
        self.assertEqual(value['figure_retrieval']['error_type'], 'TimeoutError')
        self.assertEqual(fetch.call_count, 1)
        _, second, again = self.run_article()
        self.assertEqual(again.call_count, 0)
        self.assertEqual(second['figure_retrieval']['status'], 'failed')
        self.assertTrue(second['figure_retrieval']['reused_receipt'])


if __name__ == '__main__':
    unittest.main()
