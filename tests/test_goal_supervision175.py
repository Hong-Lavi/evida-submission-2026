"""Synthetic public-goal and normal Runner contracts; no model/network calls."""
import copy,json,tempfile,unittest
from pathlib import Path
from evida.goal_supervision import build
from evida.model_context import unpack
from evida.gateway import Gateway
from evida.runner import Runner
from evida.store import Store,dump
from planner_fixtures import current_frame,current_final
ROOT=Path(__file__).resolve().parents[1]
class GoalSupervision(unittest.TestCase):
 def test_observations_never_judge_missing_stage_or_change_evidence(self):
  c={'RELEVANT_EVIDENCE':[{'artifact_id':'unassessed','kind':'compound_candidates'}],
     'COMPLETED_VIEWS':[{'reading_id':'one','function':'inspect_artifact'}],
     'PRIOR_NOTE_FINDINGS':[{'text':'counterevidence remains unknown','source_ids':['source']}],
     'WORKING_READINGS':[{'reading_id':'one','content':{'value':None}}],'PREVIOUS_DECISION':None}
  before=copy.deepcopy(c);r=build(c);self.assertEqual(c,before);self.assertFalse(r['scientific_sufficiency_assessed']);self.assertFalse(r['automatic_stop']);self.assertIsNone(r['forced_tool']);self.assertFalse(r['published_decision_present']);self.assertEqual(r['retained_artifact_counts_by_kind'],{'compound_candidates':1})
 def test_sustained_reading_is_observed_without_scheduled_finalization(self):
  c={'COMPLETED_VIEWS':[{'reading_id':str(i),'function':'inspect_artifact'}for i in range(50)]}
  r=build(c);self.assertEqual(r['recent_reading_ids'],[str(i)for i in range(42,50)]);self.assertEqual(r['context_observations']['completed_view_count'],50);self.assertFalse(r['automatic_stop']);self.assertIsNone(r['forced_tool'])
 def test_monitor_does_not_change_scientific_snapshot_but_real_source_does(self):
  from evida.reassessment import snapshot
  with tempfile.TemporaryDirectory()as d:
   store=Store(Path(d)/'snapshot.sqlite3');wid=store.create('Synthetic snapshot')['id'];before=snapshot(store,wid)['snapshot_sha256']
   monitor=store.add_artifact(wid,'Synthetic monitor','supervision_progress',dump({'response_number':1,'automatic_stop':False}).encode(),{},bump=False)
   self.assertEqual(snapshot(store,wid)['snapshot_sha256'],before);self.assertIn(monitor,{a['id']for a in store.snapshot(wid)['artifacts']})
   store.add_artifact(wid,'Synthetic source','repository_document',dump({'observed':'Synthetic new evidence'}).encode(),{},bump=False)
   self.assertNotEqual(snapshot(store,wid)['snapshot_sha256'],before)
 def test_normal_runner_delivers_goal_checkpoint_and_keeps_valid_final_without_computation(self):
  with tempfile.TemporaryDirectory()as d:
   store=Store(Path(d)/'fixture.sqlite3');wid=store.create('Synthetic review goal')['id'];source=store.add_artifact(wid,'Synthetic source','repository_document',dump({'rows':[{'observation':'Synthetic observation only; no biological interpretation'}]}).encode(),{},bump=False);calls=[]
   def transport(request):
    calls.append(request);n=len(calls)
    if n>4:
     from evida.gateway import GatewayError
     raise GatewayError('failed','Synthetic fixture call bound')
    if n==1:
     args=current_frame(store,wid,{'intent_records':[],'current_question':'Review synthetic evidence','task_brief':[],'questions':[],'hypotheses':[]});output=[{'type':'function_call','name':'frame_work','arguments':dump(args),'call_id':'frame'}]
    elif n==2:
     args={'artifact_id':source,'offset':0,'limit':1,'research_notes':{'findings':[],'open_questions':['Fixture source not yet read'],'next_goal':'Determine which synthetic observation is present; its value allows an explicitly limited decision.'}};output=[{'type':'function_call','name':'inspect_artifact','arguments':dump(args),'call_id':'read'}]
    else:
     decision={'based_on_state_rev':1,'intent_records':[],'action':'defer','recommendation':'Synthetic read-only decision','reason':'Only interface behavior is tested','evidence_refs':[source],'alternatives':[],'changed':[],'preserved':[],'unknowns':['No scientific claim tested'],'next_actions':[],'questions':[],'research_loop':{'hypotheses':[],'next_checks':[],'revision_rationale':'Synthetic interface fixture'}}
     output=[{'type':'message','role':'assistant','content':[{'type':'output_text','text':dump(current_final(store,wid,decision))}]}]
    return {'id':f'fixture{n}','model':'gpt-6.1-sol','status':'completed','usage':{},'output':output},{}
   class FixtureGateway:
    model='gpt-6.1-sol';effort='medium'
    def status(self):return {'available':True,'transport_mode':'synthetic_fixture_no_provider'}
    def request(self,request,model=None):
     result,_=transport(request)
     return result,{'requested_model':self.model,'requested_effort':self.effort,'actual_model':self.model,'synthetic_fixture':True,'actual_provider_calls':0}
   gateway=FixtureGateway()
   runner=object.__new__(Runner);runner.root=ROOT;runner.store=store;runner.gateway=gateway;runner.prompt=(ROOT/'configs/planner.md').read_text();runner.context_recent_views=2;runner._response_limit_setting=None
   jid=store.enqueue(wid,1,'planner',{});runner.run_planner(jid);state=store.snapshot(wid);j=next(j for j in state['jobs']if j['id']==jid)
   self.assertEqual(j['status'],'succeeded',str(j.get('error'))+str([json.loads(store.artifact(wid,a['id'])['content'])for a in state['artifacts']if a['kind'] in ('model_output_validation_error','decision_validation_error')]));self.assertEqual(len(calls),3);self.assertIsNotNone(state['decision']);self.assertEqual(store.artifact(wid,source)['sha256'],next(a['sha256']for a in state['artifacts']if a['id']==source))
   contexts=[unpack(json.loads(req['input'][0]['content']))for req in calls]
   self.assertTrue(all('GOAL_SUPERVISION'in c for c in contexts));self.assertEqual(contexts[-1]['GOAL_SUPERVISION']['recent_operation_names'],['inspect_artifact']);self.assertFalse(contexts[-1]['GOAL_SUPERVISION']['scientific_sufficiency_assessed']);self.assertEqual(calls[1]['tool_choice'],'auto')
   protocol=next(a for a in state['artifacts']if a['kind']=='protocol_snapshot');self.assertIn('evida/goal_supervision.py',json.loads(store.artifact(wid,protocol['id'])['content'])['code_sha256'])
if __name__=='__main__':unittest.main()
