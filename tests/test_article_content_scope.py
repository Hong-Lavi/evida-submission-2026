from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from evida.public_evidence import article_presentation, parse_article

FRONT=b'''<front><article-meta><article-id pub-id-type="pmc">123</article-id><title-group><article-title>Scope fixture</article-title></title-group><abstract><p>Thirteen people received three crossover periods.</p></abstract><counts><ref-count count="40"/><table-count count="3"/></counts></article-meta></front>'''


class ArticleContentScopeTests(unittest.TestCase):
    def test_official_abstract_response_does_not_become_full_article(self):
        raw=b'<pmc-articleset><article>'+FRONT+b'</article></pmc-articleset>'
        result=parse_article(raw,'PMC123',{'http_status':200})
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['content_coverage']['scope'],'abstract_only')
        self.assertFalse(result['content_coverage']['body_element_present'])
        self.assertEqual(result['summary']['reference_count'],0)
        self.assertEqual(result['content_coverage']['declared_counts']['ref-count']['count'],'40')
        self.assertEqual(result['original_xml'].encode(),raw)

    def test_empty_body_and_declared_counts_do_not_establish_full_retrieval(self):
        result=parse_article(b'<article>'+FRONT+b'<body><sec><title>Unavailable</title></sec></body></article>','PMC123',{})
        self.assertTrue(result['content_coverage']['body_element_present'])
        self.assertEqual(result['content_coverage']['scope'],'abstract_only')
        self.assertEqual(result['status'],'partial')

    def test_historical_misclassification_is_visible_without_changing_original(self):
        result=parse_article(b'<article>'+FRONT+b'</article>','PMC123',{})
        old=deepcopy(result);old.pop('content_coverage');old['summary'].pop('content_scope')
        old.update(status='succeeded',semantic_type='published_full_text',limits=['Legacy whole-text claim'])
        original=deepcopy(old);view=article_presentation(old)
        self.assertEqual(old,original)
        self.assertEqual(view['rows'],original['rows'])
        self.assertEqual(view['status'],'succeeded')
        self.assertEqual(view['content_coverage']['scope'],'abstract_only')
        self.assertIn('본문은 반환되지',view['limits'][0])

    def test_body_rows_mean_body_available_not_all_content_read(self):
        result=parse_article(b'<article>'+FRONT+b'<body><p id="p1">Actual study methods.</p></body></article>','PMC123',{})
        self.assertEqual(result['status'],'succeeded')
        self.assertEqual(result['content_coverage']['returned_body_blocks'],1)
        self.assertEqual(result['summary']['content_scope'],'body_available')
        self.assertTrue(result['content_coverage']['source_retrieval_is_not_reading_or_complete_paper_verification'])

    def test_saved_article_title_is_readable_without_rewriting_legacy_artifact(self):
        from evida.store import Store
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'state.sqlite3');wid=store.create('Title test')['id']
            native=json.dumps({'title':'An actual source title','rows':[]}).encode()
            aid=store.add_artifact(wid,'Legacy generic tool label','article',native,{})
            bad=store.add_artifact(wid,'Unparseable historical article','article',b'not JSON',{})
            before=store.artifact(wid,aid)
            index={a['id']:a for a in store.snapshot(wid)['artifacts']}
            self.assertEqual(index[aid]['source_title'],'An actual source title')
            self.assertIsNone(index[bad]['source_title'])
            self.assertEqual(index[aid]['title'],'Legacy generic tool label')
            self.assertEqual(store.artifact(wid,aid),before)


if __name__=='__main__':unittest.main()
