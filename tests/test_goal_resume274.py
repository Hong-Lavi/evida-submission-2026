"""Original API payload replay and HTTP failure boundaries, fake transport only."""
from pathlib import Path
import json,tempfile,unittest,io,urllib.error,hashlib,copy
from email.message import Message
from evida.store import Store,dump
from evida.runner import Runner
from evida.gateway import Gateway
from evida.planner_recovery import prepare_quota_resume
from evida.model_context import unpack
from evida.research_loop import decision_id
from evida.goal_completion import pending_from_request
from planner_fixtures import current_frame,current_final
from test_current_call_tools import current_call,proposal
from test_goal_completion274 import authored_review
ROOT=Path(__file__).resolve().parents[1]
class GoalResumeTests(unittest.TestCase):
 def exercise(self,http=429):
  with tempfile.TemporaryDirectory()as tmp:
   tmp=Path(tmp);store=Store(tmp/'f.sqlite3');wid=store.create('Synthetic goal-review exact replay')['id'];calls=[];failed=[False]
   def transport(request):
    calls.append(copy.deepcopy(request));c=unpack(current_call(request))
    if c['stage']=='frame':out=[{'type':'function_call','name':'frame_work','call_id':'frame','arguments':dump(current_frame(store,wid,{'intent_records':[],'current_question':'Synthetic interface request','task_brief':[],'questions':[],'hypotheses':[]}))}]
    elif c['stage']=='goal_review':
     if not failed[0]:
      failed[0]=True;h=Message();h['retry-after']='0';raise urllib.error.HTTPError('https://synthetic.invalid',http,'Synthetic HTTP fixture',h,io.BytesIO(b'{}'))
     out=[{'type':'message','content':[{'type':'output_text','text':dump(authored_review(decision_id(store.snapshot(wid))))}]}]
    else:out=[{'type':'message','content':[{'type':'output_text','text':dump(current_final(store,wid,proposal(1)))}]}]
    return {'id':'fixture-'+str(len(calls)),'model':gateway.model,'status':'completed','usage':{},'output':out},{}
   policy=json.loads((ROOT/'configs/api_policy.json').read_text());policy['min_request_interval_seconds']=0;policy['secret_env']='EVIDA_UNUSED_SYNTHETIC_KEY_274'
   gateway=Gateway(policy,True,model='gpt-6-sol',effort='medium',transport=transport,requests_dir=tmp/'requests');runner=object.__new__(Runner);runner.root=ROOT;runner.store=store;runner.gateway=gateway;runner.prompt=(ROOT/'configs/planner.md').read_text();runner._response_limit_setting=None;runner.attempts_root=gateway.requests_dir
   jid=store.enqueue(wid,1,'planner',{});runner.run_planner(jid);before=store.snapshot(wid);old_id=decision_id(before);old=store.artifact(wid,old_id);firstjob=next(j for j in before['jobs']if j['id']==jid);self.assertEqual(len(calls),3);self.assertTrue(all(c['model']=='gpt-6-sol'and c['reasoning']=={'effort':'medium'}for c in calls))
   if http==403:
    self.assertEqual(firstjob['status'],'quota_exhausted');self.assertEqual(len(calls),3)
    with self.assertRaises(ValueError):prepare_quota_resume(runner,wid,1,jid)
    self.assertEqual(len(calls),3);return
   self.assertEqual(firstjob['status'],'quota_or_rate_limit');resume=prepare_quota_resume(runner,wid,1,jid);self.assertEqual(resume['completed_rounds'],2);self.assertEqual(resume['request'],calls[2]);self.assertEqual(pending_from_request(resume['request'],runner.prompt)['decision_id'],old_id)
   original=copy.deepcopy(resume['request']);bad=copy.deepcopy(original);bad['text']['format']['schema']['properties']['goal_status']['enum']=['request_satisfied']
   with self.assertRaises(ValueError):pending_from_request(bad,runner.prompt)
   newjid=store.enqueue(wid,1,'planner',resume['arguments']);runner.run_planner(newjid,resume=resume);after=store.snapshot(wid);job=next(j for j in after['jobs']if j['id']==newjid);self.assertEqual(job['status'],'succeeded',job['error']);self.assertEqual(len(calls),4);self.assertEqual(calls[3],calls[2]);self.assertEqual(original,resume['request'])
   new_id=decision_id(after);new=store.artifact(wid,new_id);self.assertNotEqual(old_id,new_id);self.assertEqual(old['content'],new['content']);self.assertEqual(old['sha256'],new['sha256']);self.assertEqual(new['meta']['job_id'],newjid);self.assertEqual(new['meta']['reaffirmed_from'],old_id);self.assertEqual(job['output_id'],new_id);self.assertEqual(after['review_status'],before['review_status']);self.assertEqual(next(j for j in after['jobs']if j['id']==jid)['status'],'quota_or_rate_limit');self.assertEqual(sum(a['kind']=='model_receipt'for a in after['artifacts']),4);self.assertEqual(sum(a['kind']=='goal_coverage_binding'for a in after['artifacts']),1)
 def test_exact_goal_review_429_replay_preserves_request_identity_and_checkpoint_bytes(self):self.exercise()
 def test_goal_review_403_stops_without_fallback_or_automatic_resume(self):self.exercise(403)
if __name__=='__main__':unittest.main(verbosity=2)
