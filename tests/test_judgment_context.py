"""Condition correction preserves evidence; review paths do not assert causes."""
import copy,tempfile,unittest
from pathlib import Path
from evida.judgment_context import review_impact,validate,view,CONTEXT
from evida.store import Store,dump
from test_integrity import proposal
from test_research_loop import hypothesis

def fixture(aid):
    c={k:'' for k in CONTEXT['properties']};c.update(id='ctx',organism='human',assay_buffer='buffer1',unknowns=['time'],source_ids=[aid])
    return {'contexts':[c],'assumptions':[dict(id='transfer',statement='explicit transfer',status='unknown',context_id='ctx',source_ids=[aid])],
      'bindings':[dict(hypothesis_id=h,part_id='',stage='candidate',context_id='ctx',assumption_ids=['transfer'],prediction=dict(observable='measurement',direction_or_range='increase',unit='',time='',comparator='control',origin='prospective')) for h in ['h1','h2','alternative']],
      'observation_reviews':[],'review_links':[dict(from_hypothesis_id=a,review_upstream_hypothesis_id=b,assumption_id='transfer',reason='explicit fixture relation') for a,b in [('h1','h2'),('h2','h1')]],'unresolved_context':['not scientific evidence']}
class ContextTests(unittest.TestCase):
    def test_same_claim_preserves_distinct_contexts_and_opposed_observations(self):
        x=fixture('a');second=copy.deepcopy(x['contexts'][0]);second.update(id='different_trial',time='different time',comparator='different control')
        x['contexts'].append(second)
        binding=copy.deepcopy(x['bindings'][0]);binding.update(context_id='different_trial')
        binding['prediction']['comparator']='different control';x['bindings'].append(binding)
        for ctx,outcome in [('ctx','positive surrogate'),('different_trial','no established clinical improvement')]:
            x['observation_reviews'].append(dict(source_id='a',hypothesis_id='h1',part_id='',context_id=ctx,
                measurement_quality='fixture',processing_validity='fixture',applicability='Different conditions',
                explanatory_adequacy=outcome,next_check='Compare endpoint and population'))
        state={'artifacts':[{'id':'a'}],'events':[]};hs=[]
        for hid in ['h1','h2','alternative']:
            h=hypothesis('a');h['id']=hid;hs.append(h)
        before=copy.deepcopy(x);validate(x,state,hs)
        self.assertEqual(x,before)
        bad=copy.deepcopy(x);bad['bindings'].append(copy.deepcopy(binding))
        with self.assertRaisesRegex(ValueError,'동일 문맥'):validate(bad,state,hs)

    def test_cycle_terminates_without_rejecting_alternative_or_reexecuting(self):
        x=fixture('a');before=copy.deepcopy(x);r=review_impact(x,['h1'])
        self.assertEqual(r['upstream_review'],['h2']);self.assertEqual(r['outside_explicit_review_paths'],['alternative']);self.assertEqual(x,before)
        self.assertFalse(r['automatic_assessment_changes']);self.assertFalse(r['automatic_scientific_reexecution'])
    def test_condition_correction_original_idempotency_and_wrong_before_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'db');wid=store.create('fixture')['id'];aid=store.add_artifact(wid,'input','evidence',b'{}',{},bump=False)
            hs=[]
            for hid in ['h1','h2','alternative']:
                h=hypothesis(aid);h['id']=hid;hs.append(h)
            x=fixture(aid);validate(x,store.snapshot(wid),hs)
            ctx=store.add_artifact(wid,'context','judgment_context',dump({'schema_version':'1','context':x}).encode(),{'based_rev':1,'job_id':'fixture'},bump=False)
            p=proposal(1);p['research_loop']['hypotheses']=hs;pid=store.add_artifact(wid,'decision','decision_proposal',dump(p).encode(),{'job_id':'fixture'},bump=False);store.publish_decision(wid,1,p,pid)
            body={'kind':'correction','text':'buffer corrected','synthetic':True,'research_context':{'decision_id':pid,'check_id':None,'hypothesis_ids':['h1'],'comparison':'unclear'},'context_update':{'context_artifact_id':ctx,'context_id':'ctx','field':'assay_buffer','before':'buffer1','after':'buffer2','reason':'fixture'}}
            original=store.artifact(wid,ctx)['content'];first=store.command(wid,1,'cmd',body);self.assertEqual(store.command(wid,1,'cmd',body),first)
            self.assertEqual(store.artifact(wid,ctx)['content'],original);current=store.snapshot(wid);self.assertEqual(current['jobs'],[]);self.assertEqual(current['decision'],p)
            self.assertEqual(view(store,wid,current)['pending_changes'][0]['impact']['upstream_review'],['h2'])
            bad=copy.deepcopy(body);bad['context_update']['before']='fabricated'
            with self.assertRaisesRegex(ValueError,'원 조건'):store.command(wid,2,'bad',bad)
            self.assertEqual(store.snapshot(wid)['rev'],2)
            bad=copy.deepcopy(x);bad['contexts'][0]['source_ids']=['foreign']
            with self.assertRaisesRegex(ValueError,'출처'):validate(bad,current,hs)
