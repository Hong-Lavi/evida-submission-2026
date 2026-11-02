import copy, hashlib, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from evida.capacity_recovery import request_with_recovery, recovery_view, prepare_subscription_resume, RecoveryCancelled
from evida.gateway import GatewayError
from evida.store import Store, dump, Conflict

class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root/'db.sqlite3')
  self.wid=self.store.create('capacity fixture')['id'];self.jid=self.store.enqueue(self.wid,1,'planner',{'model':'subscription:gpt-6-sol'})
  self.job=self.store.start_job(self.jid);self.runner=SimpleNamespace(store=self.store)
  self.receipt={'status':'FAILED','route':'subscription:gpt-6-sol','started_at':'2026-11-02T01:00:00+00:00',
   'requested_model':'gpt-6-sol','requested_effort':'medium','provider_failure':{'retryable':True,'failure_evidence':{'provider_capacity':True,'source':'plaintext_stderr'}}}
 def tearDown(self):self.tmp.cleanup()
 def test_same_payload_retries_and_keeps_each_failure(self):
  calls=[];waits=[]
  def send(payload,model):
   calls.append((copy.deepcopy(payload),model))
   if len(calls)<3:raise GatewayError('provider_capacity','busy',self.receipt)
   return {'output':[]},{'status':'COMPLETED'}
  self.runner.gateway=SimpleNamespace(request=send)
  self.assertEqual(request_with_recovery(self.runner,self.job,{'input':['original']},'subscription:gpt-6-sol','p',sleep=waits.append)[1]['status'],'COMPLETED')
  self.assertEqual(calls,[({'input':['original']},'subscription:gpt-6-sol')]*3);self.assertEqual(sum(waits),90)
  state=self.store.snapshot(self.wid);self.assertEqual(sum(a['kind']=='model_receipt' for a in state['artifacts']),2)
  self.assertIsNone(recovery_view(state));self.assertEqual(state['jobs'][0]['status'],'running')
 def test_quota_identity_unknown_never_retried(self):
  for status in ['quota_or_rate_limit','failed','provider_capacity']:
   calls=[]
   def send(payload,model):
    calls.append(1);raise GatewayError(status,'failure',{'status':'FAILED'})
   self.runner.gateway=SimpleNamespace(request=send)
   with self.assertRaises(GatewayError):request_with_recovery(self.runner,self.job,{},'subscription:gpt-6-sol','p',sleep=lambda _:None)
   self.assertEqual(calls,[1])
 def test_cancellation_while_waiting_preserves_terminal_state(self):
  self.runner.gateway=SimpleNamespace(request=lambda *a,**kw:(_ for _ in ()).throw(GatewayError('provider_capacity','busy',self.receipt)))
  def stop(_):self.store.finish_job(self.jid,'cancelled')
  with self.assertRaises(RecoveryCancelled):request_with_recovery(self.runner,self.job,{},'subscription:gpt-6-sol','p',sleep=stop)
  self.assertEqual(self.store.snapshot(self.wid)['jobs'][0]['status'],'cancelled')
 def test_changed_input_prevents_old_request_retry(self):
  self.runner.gateway=SimpleNamespace(request=lambda *a,**kw:(_ for _ in ()).throw(GatewayError('provider_capacity','busy',self.receipt)))
  def change(_):self.store.command(self.wid,1,'new-message',{'kind':'message','text':'new condition','synthetic':True})
  with self.assertRaises(Conflict):request_with_recovery(self.runner,self.job,{},'subscription:gpt-6-sol','p',sleep=change)
 def test_cancel_during_provider_call_preserves_response_without_dispatch(self):
  def send(payload,model):
   self.store.finish_job(self.jid,'cancelled')
   return {'output':[{'type':'function_call','name':'read_article'}]}, {'status':'COMPLETED'}
  self.runner.gateway=SimpleNamespace(request=send)
  with self.assertRaises(RecoveryCancelled):request_with_recovery(self.runner,self.job,{},'subscription:gpt-6-sol','p')
  state=self.store.snapshot(self.wid);self.assertEqual(state['jobs'][0]['status'],'cancelled')
  self.assertEqual({a['kind'] for a in state['artifacts']},{'model_receipt','decision_proposal'})
 def test_waiting_status_clears_before_retry_response(self):
  calls=[]
  def send(payload,model):
   calls.append(1)
   if len(calls)==1:raise GatewayError('provider_capacity','busy',self.receipt)
   self.assertIsNone(recovery_view(self.store.snapshot(self.wid)))
   return {'output':[]},{'status':'COMPLETED'}
  self.runner.gateway=SimpleNamespace(request=send)
  request_with_recovery(self.runner,self.job,{},'subscription:gpt-6-sol','p',sleep=lambda _:None)
 def fixture_resume(self):
  self.store.finish_job(self.jid,'failed');p=self.root/'calls'/'call-0364';(p/'provider').mkdir(parents=True)
  payload={'input':['preserved'],'instructions':'prompt'};receipt={**self.receipt,'provider_record':'/old/runtime/call-0364','request_sha256':hashlib.sha256(dump(payload).encode()).hexdigest()}
  (p/'input.json').write_text(dump(payload));(p/'receipt.json').write_text(dump(receipt))
  (p/'provider/terminal.json').write_text('{"returncode":1}');(p/'provider/last-message.bin').write_bytes(b'')
  (p/'provider/stderr.bin').write_text('ERROR: Selected model is at capacity. Please try a different model.\n')
  self.store.add_artifact(self.wid,'failure','model_receipt',dump(receipt).encode(),{'job_id':self.jid},bump=False)
  route=SimpleNamespace(model='gpt-6-sol',effort='medium',dispatch=SimpleNamespace(root=p.parent))
  self.runner.gateway=SimpleNamespace(route=lambda _:route)
  return p,payload
 def test_bound_record_resume_and_tamper_rejection(self):
  p,payload=self.fixture_resume();got=prepare_subscription_resume(self.runner,self.wid,1,self.jid)
  self.assertEqual(got['request'],payload);self.assertEqual(got['arguments']['model'],'subscription:gpt-6-sol')
  (p/'input.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'해시'):prepare_subscription_resume(self.runner,self.wid,1,self.jid)
 def test_partial_response_is_not_replayed(self):
  p,_=self.fixture_resume();(p/'provider/last-message.bin').write_bytes(b'partial response')
  with self.assertRaisesRegex(ValueError,'응답 없는'):prepare_subscription_resume(self.runner,self.wid,1,self.jid)
if __name__=='__main__':unittest.main()
