"""Same-measurement correction controls; synthetic records, no worker/model calls."""
import copy,tempfile,unittest
from pathlib import Path
from evida.store import Store,dump
from evida.next_observation_binding import prepare,evaluate
from evida.observation_amendment import eligibility
from tests.test_check_subject_binding import publish_subjects,keep_result
from tests.test_next_observation import result_fixture
PASS={'measurement_validity':'validated','intervention_status':'validated','precision':'adequate','context_match':True}
class AmendmentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(Path(self.tmp.name)/'test.sqlite');self.wid=self.store.create('Synthetic')['id']
  self.source=self.store.add_artifact(self.wid,'Candidate','analogue_proposal',dump({'rows':[{'candidate_id':'proposed-1','smiles':'CCO'}]}).encode(),{},bump=False)
  self.refs=[{'role':'candidate','artifact_id':self.source,'json_pointer':'/rows/0'}];self.args,self.loop=publish_subjects(self.store,self.wid,self.refs)
  self.parent=keep_result(self.store,self.wid,evaluate(prepare(self.store,self.wid,self.args)))
  self.rc={'decision_id':self.args['artifact_id'],'check_id':'function','hypothesis_ids':['h'],'comparison':'unclear'}
  self.mid=self.observe();self.assessment=result_fixture(message_id=self.mid);self.original=evaluate(prepare(self.store,self.wid,self.args_for(self.parent,self.assessment)));self.held=keep_result(self.store,self.wid,self.original)
 def observe(self,**extra):
  rev=self.store.snapshot(self.wid)['rev'];return self.store.command(self.wid,rev,'obs-'+str(rev),{'kind':'observation','text':'Original synthetic measurement unchanged','synthetic':True,'research_context':self.rc,**extra})['message_id']
 def args_for(self,aid,r):return {'mode':'review_result','artifact_id':aid,'source_artifact_ids':[],'problem':None,'result':r}
 def amend(self,aid=None,mid=None,**extra):
  rev=self.store.snapshot(self.wid)['rev'];return self.store.command(self.wid,rev,'amend-'+str(rev),{'kind':'correction','text':'Confirm facts, not new experiment','observation_amendment':{'target_message_id':mid or self.mid,'prior_selection_id':aid or self.held,'reason':'Original record checked'},'recalculate_held_selection':True,**extra})
 def compute(self,saved):
  job=next(j for j in self.store.snapshot(self.wid)['jobs'] if j['id']==saved['job_id']);args=copy.deepcopy(job['request']);mid=args.pop('_observation_amendment_id');bundle=prepare(self.store,self.wid,args,amendment_id=mid,own_job=job['id']);return bundle,evaluate(bundle)
 def retain(self,saved,out):
  aid=self.store.add_artifact(self.wid,'Synthetic amended output','next_observation_selection',dump(out).encode(),{},bump=False);self.store.finish_job(saved['job_id'],'succeeded',aid);return aid
 def test_confirmation_and_later_normal_replay_keep_original_measurement(self):
  raw=self.store.artifact(self.wid,self.held)['content'];info=eligibility(self.store,self.wid,self.held);self.assertTrue(info['eligible']);self.assertEqual(info['expected_subject_refs'],self.refs)
  saved=self.amend(reported_subject_refs=self.refs,measurement_report=PASS);_,out=self.compute(saved)
  self.assertEqual(out['summary']['selection_status'],'decision_region_reached');self.assertEqual(len(out['summary']['retained_configuration_ids']),2);self.assertEqual(out['result_assessment'],self.assessment);self.assertEqual(out['observed_events'],self.original['observed_events']);self.assertEqual(out['binding']['prior_selection_id'],self.parent);self.assertEqual(out['binding']['observation_message_ids'],[self.mid]);self.assertFalse(out['observation_amendment']['independent_observation_added']);self.assertEqual(raw,self.store.artifact(self.wid,self.held)['content'])
  corrected=self.retain(saved,out);self.assertFalse(eligibility(self.store,self.wid,self.held)['eligible']);later=self.observe(reported_subject_refs=self.refs)
  replay=evaluate(prepare(self.store,self.wid,self.args_for(corrected,result_fixture(message_id=later))));self.assertEqual(replay['binding']['observation_message_ids'],[self.mid,later]);self.assertEqual(replay['summary']['retained_configuration_ids'],out['summary']['retained_configuration_ids'])
 def test_precision_still_blocks_then_repeat_amendment_inherits_subject(self):
  saved=self.amend(reported_subject_refs=self.refs,measurement_report={**PASS,'precision':'insufficient'});_,out=self.compute(saved)
  self.assertEqual(out['summary']['selection_status'],'report_confirmation_required');self.assertEqual(len(out['summary']['retained_configuration_ids']),3);self.assertEqual(out['conditional_exclusions'],[]);self.assertIsNone(out['summary']['cost']);self.assertTrue(out['report_guard']['applied']);self.assertFalse(out['subject_guard']['applied'])
  corrected=self.retain(saved,out);saved2=self.amend(aid=corrected,measurement_report=PASS);_,out2=self.compute(saved2)
  self.assertEqual(out2['summary']['selection_status'],'decision_region_reached');self.assertEqual(out2['observed_events'],self.original['observed_events']);self.assertEqual(out2['observation_amendment']['previous_amendment_id'],saved['message_id']);self.assertEqual(out2['binding']['observation_message_ids'],[self.mid])
 def test_report_and_attachments_do_not_confirm_subject(self):
  saved=self.amend(measurement_report=PASS,source_artifact_ids=[self.source]);_,out=self.compute(saved);self.assertEqual(out['summary']['selection_status'],'subject_confirmation_required');self.assertEqual(out['conditional_exclusions'],[]);self.assertEqual(out['observation_amendment']['effective_reported_subject_refs'],[])
 def test_invalid_changes_atomic(self):
  before=self.store.snapshot(self.wid)
  bad=[{'reported_subject_refs':self.refs,'synthetic':False},{'reported_subject_refs':self.refs,'research_context':{**self.rc,'check_id':'repeat'}},{'reported_subject_refs':self.refs,'amendment_receipt':{}},{'reported_subject_refs':self.refs,'review_requested':True},{'reported_subject_refs':[{**self.refs[0],'artifact_id':'missing'}]},{'measurement_report':{**PASS,'precision':'invented'}}]
  for fields in bad:
   with self.subTest(fields=fields),self.assertRaises(ValueError):self.amend(**fields)
   self.assertEqual(before,self.store.snapshot(self.wid))
  with self.assertRaises(ValueError):self.amend(mid='other',reported_subject_refs=self.refs)
  with self.assertRaises(ValueError):self.amend(aid=self.parent,reported_subject_refs=self.refs)
 def test_idempotent_command_one_job_and_duplicate_prior_rejected(self):
  rev=self.store.snapshot(self.wid)['rev'];body={'kind':'correction','text':'same','observation_amendment':{'target_message_id':self.mid,'prior_selection_id':self.held,'reason':'same'},'recalculate_held_selection':True,'reported_subject_refs':self.refs}
  a=self.store.command(self.wid,rev,'fixed',body);b=self.store.command(self.wid,rev,'fixed',body);self.assertEqual(a,b)
  with self.assertRaisesRegex(ValueError,'이미 정정'):self.amend(reported_subject_refs=self.refs)
  self.assertEqual(len([j for j in self.store.snapshot(self.wid)['jobs'] if j['request'].get('_observation_amendment_id')]),1)
 def test_transfer_tamper_and_duplicate_original_rejected(self):
  saved=self.amend(reported_subject_refs=self.refs,measurement_report=PASS);bundle,out=self.compute(saved)
  for mutate in [lambda b:b['arguments']['result'].__setitem__('outcome_index',1),lambda b:b['events'][-1]['body']['amendment_receipt'].__setitem__('original_selection_sha256','bad'),lambda b:b['events'][-1]['body'].__setitem__('synthetic',False),lambda b:b['events'][-1]['body']['amendment_receipt']['effective_measurement_report'].__setitem__('precision','insufficient')]:
   bad=copy.deepcopy(bundle);mutate(bad)
   with self.assertRaises(ValueError):evaluate(bad)
  aid=self.retain(saved,out)
  with self.assertRaisesRegex(ValueError,'반복'):prepare(self.store,self.wid,self.args_for(aid,self.assessment))
 def test_descendant_blocks_prior(self):
  later=self.observe();keep_result(self.store,self.wid,evaluate(prepare(self.store,self.wid,self.args_for(self.held,result_fixture(message_id=later)))))
  self.assertFalse(eligibility(self.store,self.wid,self.held)['eligible'])
  with self.assertRaisesRegex(ValueError,'뒤에 계산'):self.amend(reported_subject_refs=self.refs)
 def test_pending_normal_review_reserves_terminal(self):
  mid=self.observe();self.store.enqueue(self.wid,self.store.snapshot(self.wid)['rev'],'next_observation_selection',self.args_for(self.held,result_fixture(message_id=mid)))
  self.assertFalse(eligibility(self.store,self.wid,self.held)['eligible'])
  with self.assertRaisesRegex(ValueError,'진행 중'):self.amend(reported_subject_refs=self.refs)
 def test_original_failed_assessment_is_not_promoted(self):
  mid=self.observe(measurement_report={**PASS,'intervention_status':'unknown'},reported_subject_refs=self.refs)
  failed=result_fixture(message_id=mid,measurement_validity='failed');old=evaluate(prepare(self.store,self.wid,self.args_for(self.parent,failed)));self.assertEqual(old['summary']['selection_status'],'report_confirmation_required')
  held=keep_result(self.store,self.wid,old);saved=self.amend(aid=held,mid=mid,measurement_report=PASS);_,out=self.compute(saved)
  self.assertEqual(out['result_assessment'],failed);self.assertEqual(out['summary']['selection_status'],'repair_readout');self.assertEqual(out['conditional_exclusions'],[]);self.assertEqual(len(out['summary']['retained_configuration_ids']),3)
 def test_original_classification_correction_is_inherited_separately(self):
  rev=self.store.snapshot(self.wid)['rev'];self.store.command(self.wid,rev,'classify',{'kind':'correction','text':'Original fixture source classification confirmation','synthetic':False,'provenance_correction':{'target_message_id':self.mid,'corrected_synthetic':True,'reason':'Software fixture','researcher_reply':'Retain synthetic'}})
  saved=self.amend(reported_subject_refs=self.refs);_,out=self.compute(saved)
  inherited=out['observation_amendment']['original_effective_provenance'];self.assertTrue(inherited['synthetic']);self.assertEqual(len(inherited['corrections']),1);self.assertFalse(out['observation_amendment']['scientific_validation'])
 def test_historical_source_tamper_rejected_before_saving(self):
  with self.store.connect(True) as db:db.execute('UPDATE artifacts SET content=? WHERE id=?',(b'{}',self.parent))
  before=self.store.snapshot(self.wid)
  with self.assertRaises(ValueError):self.amend(reported_subject_refs=self.refs)
  self.assertEqual(self.store.snapshot(self.wid),before)
 def test_enqueue_failure_rolls_back_entire_command(self):
  from unittest.mock import patch
  before=self.store.snapshot(self.wid)
  with patch('evida.observation_amendment.enqueue',side_effect=RuntimeError('synthetic enqueue failure')):
   with self.assertRaises(RuntimeError):self.amend(reported_subject_refs=self.refs)
  self.assertEqual(before,self.store.snapshot(self.wid))
 def test_report_amendment_without_declared_subject_on_other_check(self):
  rc={**self.rc,'check_id':'repeat'}
  mid=self.store.command(self.wid,self.store.snapshot(self.wid)['rev'],'other-check',{'kind':'observation','text':'Synthetic other check','synthetic':True,'research_context':rc,'measurement_report':{**PASS,'precision':'unknown'}})['message_id']
  assessment=result_fixture(message_id=mid,check_id='repeat');out=evaluate(prepare(self.store,self.wid,self.args_for(self.parent,assessment)))
  held=keep_result(self.store,self.wid,out);saved=self.amend(aid=held,mid=mid,measurement_report=PASS,reported_subject_refs=[]);_,updated=self.compute(saved)
  self.assertEqual(updated['observation_amendment']['effective_subject_binding']['comparison']['status'],'not_declared')
 def test_real_run_adapter_receipt_replays_as_history_and_parent(self):
  from evida.next_observation_binding import run,stage
  saved=self.amend(reported_subject_refs=self.refs,measurement_report=PASS);bundle,_=self.compute(saved)
  transfer=stage(bundle,Path(self.tmp.name));out=run({'arguments':bundle['arguments'],'next_observation_input':transfer})
  self.assertEqual(out['provenance']['input_bundle_sha256'],transfer['sha256']);self.assertIn('observation_amendment.py',out['provenance']['code_sha256'])
  aid=self.retain(saved,out);original=self.store.artifact(self.wid,aid)['content']
  history=evaluate(prepare(self.store,self.wid,self.args_for(aid,self.assessment),_history_only=True),_history_only=True)
  self.assertEqual(history['previous'],aid);self.assertEqual(history['used_messages'],[self.mid])
  with self.assertRaisesRegex(ValueError,'반복'):prepare(self.store,self.wid,self.args_for(aid,self.assessment))
  later=self.observe(reported_subject_refs=self.refs,measurement_report=PASS)
  result=evaluate(prepare(self.store,self.wid,self.args_for(aid,result_fixture(message_id=later))))
  self.assertEqual(result['binding']['observation_message_ids'],[self.mid,later]);self.assertEqual(original,self.store.artifact(self.wid,aid)['content'])
 def test_worker_receipt_keeps_science_and_digest_tamper_guards(self):
  import base64,hashlib
  from evida.next_observation_binding import run,stage,encoded
  saved=self.amend(reported_subject_refs=self.refs,measurement_report={**PASS,'precision':'insufficient'});bundle,_=self.compute(saved)
  out=run({'arguments':bundle['arguments'],'next_observation_input':stage(bundle,Path(self.tmp.name))});aid=self.retain(saved,out)
  history=prepare(self.store,self.wid,self.args_for(aid,self.assessment),_history_only=True)
  mutations={
   'retained':lambda x:x['summary'].__setitem__('retained_configuration_ids',[]),
   'guard':lambda x:x['report_guard'].__setitem__('applied',False),
   'argument_digest':lambda x:x['provenance'].__setitem__('argument_sha256','0'*64),
   'partial_worker_receipt':lambda x:x['provenance'].pop('input_bundle_sha256'),
   'input_digest':lambda x:x['provenance'].__setitem__('input_bundle_sha256','bad'),
   'code_digest':lambda x:x['provenance']['code_sha256'].__setitem__('observation_amendment.py','bad'),
  }
  for name,mutate in mutations.items():
   with self.subTest(name=name):
    damaged=copy.deepcopy(history);value=copy.deepcopy(out);mutate(value);raw=encoded(value);record=damaged['artifacts'][aid]
    record['content_base64']=base64.b64encode(raw).decode();record['sha256']=hashlib.sha256(raw).hexdigest()
    with self.assertRaises(ValueError):evaluate(damaged,_history_only=True)
