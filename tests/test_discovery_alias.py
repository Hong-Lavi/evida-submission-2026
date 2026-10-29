"""A real final-response failure: exact guide IDs versus scoped catalog IDs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from evida.discovery import catalog,record_review,resolve_review_ids
from evida.store import Store,dump


class DiscoveryAliasTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db')
        self.wid=self.store.create('fixture')['id'];self.entity='guide_'+'a'*20
        self.aid=self.add('T1')
        self.review={'question':'fixture','new_options':[],'unsearched_scope':['Other retained options'],
            'assessments':[{'option_id':self.entity,'status':'recommended','priority':1,'comparison_group':'fixture',
                'reason':'Fixture only','support_source_ids':[self.aid],'challenge_source_ids':[],
                'uncertainties':['No efficacy evidence'],'next_action':'Read exact source'}]}
    def add(self,transcript):
        return self.store.add_artifact(self.wid,'fixture','rna_sequence_evaluation',dump({
            'reference':{'transcript_id':transcript},'rows':[{'id':self.entity,'guide_5to3':'ACGU'}]}).encode(),{},bump=False)
    def tearDown(self):self.tmp.cleanup()
    def test_unique_exact_entity_resolves_and_raw_input_survives(self):
        original=copy.deepcopy(self.review)
        result=record_review(self.store,self.wid,1,'j',self.review)
        saved=self.store.artifact(self.wid,result['artifact_id'])
        value=json.loads(saved['content']);meta=saved['meta']
        self.assertEqual(self.review,original)
        self.assertTrue(value['assessments'][0]['option_id'].startswith('rna:'))
        self.assertEqual(meta['option_id_resolution'][0]['returned_entity_id'],self.entity)
        self.assertEqual(meta['option_id_resolution'][0]['original_sources'][0]['artifact_id'],self.aid)
        self.assertEqual(catalog(self.store,self.wid)['reviewed'],1)
    def test_same_entity_in_different_reference_context_is_not_guessed(self):
        self.add('T2')
        with self.assertRaisesRegex(ValueError,'여러 참조'):record_review(self.store,self.wid,1,'j',self.review)
        self.assertEqual(catalog(self.store,self.wid)['reviewed'],0)
    def test_typo_unknown_namespace_and_duplicate_alias_rejected(self):
        for key in ['guide_'+'b'*20,'Guide_'+'a'*20,'rna:invented']:
            value=copy.deepcopy(self.review);value['assessments'][0]['option_id']=key
            with self.assertRaises(ValueError):record_review(self.store,self.wid,1,'j',value)
        value,_=resolve_review_ids(self.store,self.wid,self.review)
        value['assessments'].append(copy.deepcopy(self.review['assessments'][0]))
        with self.assertRaises(ValueError):record_review(self.store,self.wid,1,'j',value)
    def test_exact_id_bypasses_alias_and_source_validation_stays(self):
        value,mappings=resolve_review_ids(self.store,self.wid,self.review)
        same,second=resolve_review_ids(self.store,self.wid,value)
        self.assertEqual(same,value);self.assertEqual(second,[]);self.assertEqual(len(mappings),1)
        value['assessments'][0]['support_source_ids']=['foreign']
        with self.assertRaises(ValueError):record_review(self.store,self.wid,1,'j',value)


if __name__=='__main__':unittest.main()
