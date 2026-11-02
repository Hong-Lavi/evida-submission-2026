"""Source navigation and reconsideration regressions; synthetic rows, no calls."""
import copy
import unittest
from evida.source_navigation358 import navigation
from evida.goal_supervision import build, source_attempt_observations
from evida.catalog_delivery import apply_catalog_delivery


class SourceNavigationTests(unittest.TestCase):
    def test_glp_page_332_paragraphs_254_links_before_12_row_delivery(self):
        # Exact observed GLP page shape, without pretending synthetic content is evidence.
        rows=[{'kind':'paragraph','text':f'paragraph {i}'} for i in range(332)]
        rows += [{'kind':'source_link','url':f'https://example.org/file/{i}',
                  'text':f'link {i}','is_supplement_candidate':i in (5,200),'retrieved':False}
                 for i in range(254)]
        original=copy.deepcopy(rows)
        nav=navigation(rows,artifact_id='saved-page')
        delivered={'rows':rows[:12],'source_navigation':nav}
        self.assertEqual(nav['total_rows'],586)
        self.assertEqual(nav['source_link_ranges'],[{'offset':332,'row_count':254}])
        self.assertEqual(nav['supplement_candidate_offsets'],[337,532])
        self.assertEqual(nav['read_saved_rows']['offset'],332)
        self.assertEqual(delivered['source_navigation']['supplement_candidate_preview'][0]['url'],rows[337]['url'])
        self.assertTrue(all(not p['retrieved'] for p in nav['supplement_candidate_preview']))
        self.assertEqual(rows,original)
        self.assertEqual(len(delivered['rows']),12)

    def test_empty_pdf_and_noncontiguous_link_rows(self):
        self.assertEqual(navigation([],artifact_id='empty')['source_link_ranges'],[])
        self.assertEqual(navigation([{'kind':'pdf_page'}],artifact_id='pdf')['source_link_count'],0)
        rows=[{'kind':'source_link'}, {'kind':'paragraph'}, {'kind':'source_link'}]
        self.assertEqual(navigation(rows,artifact_id='mixed')['source_link_ranges'],[{'offset':0,'row_count':1},{'offset':2,'row_count':1}])

    def test_candidate_preview_is_explicit_and_all_addresses_remain_available(self):
        rows=[{'kind':'source_link','is_supplement_candidate':True,'url':str(i)} for i in range(20)]
        value=navigation(rows,artifact_id='many')
        self.assertEqual(value['supplement_candidate_offsets'],list(range(20)))
        self.assertEqual(len(value['supplement_candidate_preview']),12)
        self.assertTrue(value['supplement_preview_has_more'])

    def test_cross_tool_nonconsecutive_revisits_keep_new_ranges(self):
        def view(function,args,aid,offset=0):
            return {'function':function,'arguments':args,'source_artifact_id':aid,
                    'reading_id':f'reading-{aid}-{offset}', 'delivery':{'status':'succeeded','offset':offset,'has_more':True}}
        catalog=[view('read_open_article',{'pmc_id':'PMC7703558'},'article-a'),
                 view('inspect_artifact',{'artifact_id':'article-a','offset':36,'limit':1},'article-a',36),
                 view('search_public_web',{'query':'something unrelated','engine':'bing'},'search'),
                 view('read_public_research_page',{'url':'https://pmc.ncbi.nlm.nih.gov/articles/PMC7703558/','render_mode':'http'},'page-a'),
                 view('read_open_article',{'pmc_id':'PMC7703558'},'article-b'),
                 view('inspect_artifact',{'artifact_id':'article-b','offset':36,'limit':1},'article-b',36),
                 view('inspect_artifact',{'artifact_id':'page-a','offset':332,'limit':12},'page-a',332)]
        original=copy.deepcopy(catalog)
        result=source_attempt_observations(catalog)
        group=result['revisited_sources'][0]
        self.assertEqual(group['source_key'],'pmc:7703558')
        self.assertEqual(group['view_count'],6)
        self.assertEqual(len(group['repeated_exact_operations']),1)
        self.assertEqual(group['repeated_exact_operations'][0]['operation']['function'],'read_open_article')
        self.assertIn(332,[v['arguments'].get('offset') for v in group['latest_views']])
        self.assertFalse(result['automatic_stop'])
        self.assertEqual(catalog,original)

    def test_real_catalog_compaction_does_not_erase_precomputed_source_observation(self):
        catalog=[{'function':'read_public_research_page',
                  'arguments':{'url':'https://pmc.ncbi.nlm.nih.gov/articles/PMC7703558/','render_mode':'http'},
                  'delivery':{'status':'failed','offset':0,'total_rows':0,'has_more':False},
                  'source_artifact_id':f'page-{i}','reading_id':f'reading-{i}','sha256':str(i)}
                 for i in range(2)]
        raw={'COMPLETED_VIEWS':catalog,'RELEVANT_EVIDENCE':[]}
        original=copy.deepcopy(raw)
        derived=source_attempt_observations(raw['COMPLETED_VIEWS'])
        compact=apply_catalog_delivery(raw)
        # This is the actual production ordering bug, not a mock of compaction.
        self.assertNotIn('arguments',compact['COMPLETED_VIEWS'][0])
        self.assertNotIn('delivery',compact['COMPLETED_VIEWS'][0])
        broken=build(compact)
        self.assertEqual(broken['source_attempt_observations']['revisited_sources'],[])
        fixed=build(compact,source_observations=derived)
        expected=build(raw)['source_attempt_observations']
        self.assertEqual(fixed['source_attempt_observations'],expected)
        self.assertEqual(expected['revisited_sources'][0]['view_count'],2)
        self.assertEqual(expected['revisited_sources'][0]['latest_views'][0]['status'],'failed')
        self.assertEqual(raw,original)
        self.assertFalse(fixed['automatic_stop'])
        self.assertIsNone(fixed['forced_tool'])

    def test_failed_access_and_query_repetition_do_not_force_scientific_action(self):
        catalog=[{'function':'read_public_research_page','arguments':{'url':'https://example.org/paper'},
                  'delivery':{'status':'failed'},'reading_id':str(i)} for i in range(2)]
        context={'COMPLETED_VIEWS':catalog,'ORIGINAL_MESSAGES':[{'text':'researcher goal'}]}
        original=copy.deepcopy(context)
        value=build(context)
        group=value['source_attempt_observations']['revisited_sources'][0]
        self.assertEqual(group['latest_views'][0]['status'],'failed')
        self.assertIsNone(value['strategic_reconsideration']['forced_action'])
        self.assertTrue(value['strategic_reconsideration']['model_decides'])
        self.assertFalse(value['automatic_stop'])
        self.assertFalse(value['scientific_sufficiency_assessed'])
        self.assertEqual(context,original)

if __name__=='__main__':unittest.main()
