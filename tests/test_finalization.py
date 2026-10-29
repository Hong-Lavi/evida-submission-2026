import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evida.finalization import commit, finalize, prepare
from evida.store import Store, dump
from test_integrity import proposal
from test_judgment_context import fixture
from test_research_loop import hypothesis


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db')
        self.wid=self.store.create('Final bundle fixture')['id']
        self.aid=self.store.add_artifact(self.wid,'Source','literature',b'{"rows":[]}',{},bump=False)
        p=proposal(1);p['research_loop']['hypotheses']=[hypothesis(self.aid)];p['research_loop']['next_checks']=[]
        ctx=fixture(self.aid);ctx['bindings']=ctx['bindings'][:1];ctx['review_links']=[]
        review={'question':'Fixture condition','new_options':[], 'assessments':[], 'unsearched_scope':['Other mechanisms unsearched']}
        self.value={'decision':p,'discovery_review':review,'judgment_context':ctx,
                    'hypothesis_review': {'schema_version':'2','causal_steps':[],'observations':[],
                        'scope':{'hypotheses':[{'hypothesis_id':'h1','status':'not_reviewed',
                                              'reason':'Synthetic transaction test; causality not assessed.'}],
                                 'checks':[]}}}

    def tearDown(self):self.tmp.cleanup()

    def test_invalid_auxiliary_record_cannot_publish_or_partially_apply(self):
        before=self.store.snapshot(self.wid)
        value=copy.deepcopy(self.value);value['judgment_context']['contexts'][0]['source_ids']=['foreign']
        with self.assertRaises(ValueError):finalize(self.store,self.wid,1,'j',value,True,[],None)
        after=self.store.snapshot(self.wid)
        self.assertEqual(before['artifacts'],after['artifacts']);self.assertEqual(before['events'],after['events'])
        self.assertIsNone(after['decision'])

    def test_storage_failure_rolls_back_context_and_decision_together(self):
        p,records=prepare(self.store,self.wid,1,self.value,True)
        before=self.store.snapshot(self.wid)
        with patch.object(self.store,'_publish_decision',side_effect=OSError('Injected write failure')):
            with self.assertRaises(OSError):commit(self.store,self.wid,1,'j',p,records,[],None)
        after=self.store.snapshot(self.wid)
        self.assertEqual(before['artifacts'],after['artifacts']);self.assertEqual(before['events'],after['events'])

    def test_changed_revision_preserves_proposal_without_applying_sidecars(self):
        p,records=prepare(self.store,self.wid,1,self.value,True)
        self.store.command(self.wid,1,'changed',{'kind':'correction','text':'Different research condition'})
        aid,published=commit(self.store,self.wid,1,'j',p,records,[],None)
        self.assertFalse(published);state=self.store.snapshot(self.wid)
        self.assertIsNone(state['decision'])
        self.assertFalse(any(a['kind'] in ('discovery_review','judgment_context') for a in state['artifacts']))
        self.assertEqual(self.store.artifact(self.wid,aid)['content'],dump(p).encode())

    def test_optional_records_remain_optional_and_unsearched_scope_stays(self):
        value={**self.value,'judgment_context':None}
        aid,published=finalize(self.store,self.wid,1,'j',value,True,[],None)
        self.assertTrue(published)
        state=self.store.snapshot(self.wid)
        self.assertEqual(state['decision'],value['decision'])
        record=next(a for a in state['artifacts'] if a['kind']=='discovery_review')
        self.assertIn(b'Other mechanisms unsearched',self.store.artifact(self.wid,record['id'])['content'])
        self.assertFalse(any(a['kind']=='judgment_context' for a in state['artifacts']))


if __name__=='__main__':unittest.main()
