"""Normal Runner + fake transport only; no biological or future actual-run results."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from evida.store import Store,dump
from evida.runner import Runner
from evida.gateway import Gateway,GatewayError
from evida.goal_completion import validate,finish_current,SCHEMA
from evida.research_loop import decision_id
from evida.model_context import unpack
from planner_fixtures import current_frame,current_final
from test_current_call_tools import current_call,proposal
ROOT=Path(__file__).resolve().parents[1]

def authored_review(aid,status='request_satisfied'):
 remaining=status=='continue_internal_work';waiting=status=='awaiting_researcher_input'
 return {'decision_id':aid,'goal_status':status,'coverage':[{'request_requirement':'Synthetic interface request only; no scientific goal or result','assessment':'internal_work_remaining'if remaining else'requires_researcher_choice'if waiting else'conditional_plan_sufficient','basis_refs':[aid],'reason':'Synthetic lifecycle condition, not a scientific judgment','next_internal_action':'Read existing synthetic interface record'if remaining else''}],'reason':'Synthetic lifecycle review','next_goal':'Inspect the remaining synthetic record'if remaining else'','core_use':[]}
class GoalCompletionTests(unittest.TestCase):
 def exercise(self,continue_once=False,waiting=False,finite=False,invalid_review=False,fail_review=False,revise_on_review=False):
  with tempfile.TemporaryDirectory()as tmp:
   store=Store(Path(tmp)/'fixture.sqlite3');wid=store.create('Synthetic request-coverage lifecycle fixture')['id'];source=store.add_artifact(wid,'Synthetic input','repository_document',dump({'rows':[{'condition':'synthetic interface only'}]}).encode(),{},bump=False)
   calls=[];phases=[];publications_seen=[];review_number=0
   def transport(request):
    nonlocal review_number
    calls.append(request);self.assertLessEqual(len(calls),12,'Synthetic test response script exceeded its declared sequence');c=unpack(current_call(request));phases.append(c['stage']);stage=c['stage']
    if stage=='frame':out=[{'type':'function_call','name':'frame_work','call_id':'frame','arguments':dump(current_frame(store,wid,{'intent_records':[],'current_question':'Synthetic request','task_brief':[],'questions':[],'hypotheses':[]}))}]
    elif stage=='goal_review':
     review_number+=1;state=store.snapshot(wid);aid=decision_id(state);publications_seen.append(aid)
     self.assertEqual(request['tools'],[]);self.assertEqual(request['tool_choice'],'none');self.assertEqual(request['text']['format']['name'],'evida_goal_coverage_review');self.assertEqual(c['reasoning_core']['stage'],'goal_review');self.assertEqual(len(c['reasoning_core']['perspectives']),48)
     self.assertTrue(any(j['id']==jid and j['status']=='running'for j in state['jobs']))
     if fail_review:raise GatewayError('refused','Synthetic refusal; never retry')
     review=authored_review(aid,'continue_internal_work'if continue_once and review_number==1 else'awaiting_researcher_input'if waiting else'request_satisfied')
     if invalid_review and review_number==1:review['decision_id']='art_wrong'
     if revise_on_review:store.command(wid,1,'synthetic-new-request',{'kind':'message','text':'Synthetic updated request','review_requested':False})
     out=[{'type':'message','content':[{'type':'output_text','text':dump(review)}]}]
    elif continue_once and review_number==1 and phases[-2]=='goal_review':
     self.assertTrue(any('GOAL_COVERAGE_FOLLOWUP'in str(x['content'])for x in request['input']))
     out=[{'type':'function_call','name':'inspect_artifact','call_id':'read','arguments':dump({'artifact_id':source,'offset':0,'limit':1,'research_notes':{'findings':[],'open_questions':['Synthetic missing input view'],'next_goal':'Read the synthetic saved record'}})}]
    else:
     p=proposal(1);p['recommendation']='Synthetic preserved checkpoint '+str(review_number);out=[{'type':'message','content':[{'type':'output_text','text':dump(current_final(store,wid,p))}]}]
    return {'id':'fixture-'+str(len(calls)),'model':gateway.model,'status':'completed','usage':{},'output':out},{}
   policy=json.loads((ROOT/'configs/api_policy.json').read_text());policy['min_request_interval_seconds']=0;policy['secret_env']='EVIDA_UNUSED_SYNTHETIC_CREDENTIAL_274';gateway=Gateway(policy,True,model='gpt-6-sol',effort='medium',transport=transport)
   runner=object.__new__(Runner);runner.root=ROOT;runner.store=store;runner.gateway=gateway;runner.prompt=(ROOT/'configs/planner.md').read_text();runner.context_recent_views=2;runner._response_limit_setting=16 if finite else None
   jid=store.enqueue(wid,1,'planner',{});runner.run_planner(jid);state=store.snapshot(wid);job=next(j for j in state['jobs']if j['id']==jid)
   values=[json.loads(store.artifact(wid,a['id'])['content'])for a in state['artifacts']if a['kind']=='goal_coverage_review']
   data={'phases':phases,'job':job,'state':state,'reviews':values,'publications_seen':publications_seen,'calls':calls,'artifacts':state['artifacts']}
   if not(fail_review or revise_on_review):self.assertEqual(job['status'],'succeeded',job['error'])
   return data
 def test_partial_publication_review_continues_tools_and_preserves_both_checkpoints(self):
  d=self.exercise(continue_once=True);self.assertEqual(d['phases'],['frame','research','goal_review','research','research','goal_review']);self.assertEqual(len(d['reviews']),2);self.assertEqual([x['review']['goal_status']for x in d['reviews']],['continue_internal_work','request_satisfied']);self.assertEqual(len(set(d['publications_seen'])),2)
  events=[e for e in d['state']['events']if e['kind']=='decision_published'];self.assertEqual(len(events),2);self.assertEqual(d['job']['output_id'],events[-1]['body']['receipt_id']);self.assertTrue(all(any(a['id']==e['body']['receipt_id']for a in d['artifacts'])for e in events));self.assertEqual(sum(a['kind']=='model_receipt'for a in d['artifacts']),6);self.assertEqual(sum(a['kind']=='tool_reading'for a in d['artifacts']),1)
 def test_sufficient_conditional_proposal_does_not_wait_for_external_results_or_all_tools(self):
  d=self.exercise();self.assertEqual(d['phases'],['frame','research','goal_review']);self.assertEqual(len(d['reviews']),1);self.assertEqual(d['reviews'][0]['review']['goal_status'],'request_satisfied')
 def test_essential_researcher_input_is_explicitly_waiting_not_goal_satisfied(self):
  d=self.exercise(waiting=True);self.assertEqual(d['reviews'][0]['review']['goal_status'],'awaiting_researcher_input');self.assertEqual(len(d['calls']),3)
 def test_finite_original_path_has_no_added_review_call(self):
  d=self.exercise(finite=True);self.assertEqual(d['phases'],['frame','research']);self.assertEqual(d['reviews'],[])
 def test_wrong_decision_review_is_retained_and_corrected_without_tool_execution(self):
  d=self.exercise(invalid_review=True);self.assertEqual(d['phases'],['frame','research','goal_review','goal_review']);self.assertEqual(sum(a['kind']=='goal_coverage_validation_error'for a in d['artifacts']),1);self.assertEqual(sum(a['kind']=='tool_reading'for a in d['artifacts']),0)
 def test_refusal_in_review_preserves_checkpoint_and_does_not_retry(self):
  d=self.exercise(fail_review=True);self.assertEqual(d['job']['status'],'refused');self.assertEqual(len(d['calls']),3);self.assertIsNotNone(d['state']['decision']);self.assertEqual(len([e for e in d['state']['events']if e['kind']=='decision_published']),1)
 def test_goal_revision_during_review_preserves_response_without_completing_new_request(self):
  d=self.exercise(revise_on_review=True);self.assertEqual(d['job']['status'],'stale');self.assertEqual(d['state']['rev'],2);self.assertEqual(d['state']['decision_rev'],1);self.assertEqual(len(d['calls']),3)
 def test_inconsistent_coverage_or_invented_core_id_rejected(self):
  for mutate in [lambda r:r['coverage'][0].update(assessment='internal_work_remaining'),lambda r:r.update(core_use=[{'id':'invented','application':'test'}]),lambda r:r['coverage'][0].update(basis_refs=['art_missing']),lambda r:r.update(coverage=[])]:
   v=authored_review('art_test');mutate(v)
   with self.assertRaises(ValueError):validate(v,decision_id='art_test',known_artifacts={'art_test'},allowed_core_ids=set())
 def test_explicit_cancellation_not_overwritten_by_completion(self):
  with tempfile.TemporaryDirectory()as tmp:
   s=Store(Path(tmp)/'f.sqlite3');wid=s.create('Synthetic cancellation')['id'];jid=s.enqueue(wid,1,'planner',{});s.finish_job(jid,'cancelled',error='Synthetic explicit cancel');self.assertEqual(finish_current(s,wid,1,jid,'art_test','art_review'),'EXISTING_TERMINAL_PRESERVED');self.assertEqual(next(j for j in s.snapshot(wid)['jobs']if j['id']==jid)['status'],'cancelled')
if __name__=='__main__':unittest.main(verbosity=2)
