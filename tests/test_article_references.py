from copy import deepcopy
import unittest

from evida.article_references import reference_view
from evida.public_evidence import parse_article


XML=b'''<article><front><article-meta><article-id pub-id-type="pmc">12345</article-id><title-group><article-title>Controlled reference fixture</article-title></title-group></article-meta></front><body><sec><title>Results</title><p id="p1">Condition-specific observation <xref ref-type="bibr" rid="r2 r1">2,1</xref>.</p><p id="p2">Different condition <xref ref-type="bibr" rid="r2">2</xref>.</p></sec></body><back><ref-list><ref id="r1"><label>1</label><element-citation><article-title>First source fixture</article-title><pub-id pub-id-type="pmid">11111</pub-id></element-citation></ref><ref id="r2"><label>2</label><element-citation><article-title>Second source fixture</article-title><pub-id pub-id-type="doi">10.0000/fixture</pub-id></element-citation></ref></ref-list></back></article>'''


class ArticleReferencesTests(unittest.TestCase):
    def test_selected_reference_links_every_preserved_context_without_read_claim(self):
        value=parse_article(XML,'PMC12345',{'sha256':'fixture'})
        original=deepcopy(value)
        view=reference_view(value,['r2','unknown'],0,30)
        self.assertEqual(value,original)
        self.assertEqual(view['source_total_references'],2)
        self.assertEqual(view['unresolved_reference_ids'],['unknown'])
        self.assertEqual([c['offset'] for c in view['rows'][0]['citation_contexts']],[0,1])
        self.assertEqual(view['rows'][0]['article_ids'],[{'type':'doi','value':'10.0000/fixture'}])
        self.assertTrue(view['rows'][0]['bibliography_entry_is_not_source_reading'])

    def test_legacy_block_rows_gain_navigation_without_mutation_or_reindexing(self):
        value=parse_article(XML,'PMC12345',{})
        for row in value['rows']:row.pop('citation_markers')
        original=deepcopy(value)
        view=reference_view(value,[],1,1)
        self.assertEqual(value,original)
        self.assertEqual(view['rows'][0]['original_reference_index'],1)
        self.assertEqual(view['rows'][0]['citation_contexts'][0]['row_id'],'PMC12345:block:0')
        self.assertEqual(view['citation_context_mapping'],'checked_preserved_blocks')

    def test_historical_mismatched_layout_is_not_silently_remapped(self):
        value=parse_article(XML,'PMC12345',{})
        for row in value['rows']:row.pop('citation_markers')
        value['rows'][0]['text']='different preserved text'
        view=reference_view(value,['r2'],0,30)
        self.assertEqual(view['rows'][0]['citation_contexts'],[])
        self.assertEqual(view['citation_context_mapping'],'unavailable_for_historical_block_layout')
        self.assertEqual(view['rows'][0]['reference_id'],'r2')


if __name__=='__main__':unittest.main()
