"""Retention and actual worker bridge. Fixtures are not efficacy evidence."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from evida.discovery import catalog,inspect,record_review,choice_command
from evida.store import Store,Conflict,dump
from evida.compound_discovery import collect,materialize

class DiscoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'db');self.w=self.s.create('fixture')['id']
  self.raw={'disease':{'id':'D1'},'status':'succeeded','summary':{'total':150,'has_more':True},'rows':[{'target':{'id':'G'+str(i),'approvedSymbol':'Target '+str(i)},'score':1-i/100} for i in range(50)]}
  self.a=self.s.add_artifact(self.w,'fixture50','disease_targets',dump(self.raw).encode(),{},bump=False)
 def tearDown(self):self.tmp.cleanup()
 def review(self,ids):
  return {'question':'fixture','new_options':[],'assessments':[{'option_id':'target:D1:G'+str(i),'status':'recommended','priority':n+1,'comparison_group':'fixture','reason':'explicit fixture reason','support_source_ids':[self.a],'challenge_source_ids':[],'uncertainties':['not real evidence'],'next_action':'read original'} for n,i in enumerate(ids)],'unsearched_scope':['100 unread source rows']}
 def test_review_subset_never_deletes_pool_or_history(self):
  record_review(self.s,self.w,1,'fixture',self.review([0,1,2]));record_review(self.s,self.w,1,'fixture',self.review([1]))
  c=catalog(self.s,self.w);self.assertEqual((c['total'],c['reviewed']),(50,3));by={x['option_id']:x for x in c['options']}
  self.assertEqual(len(by['target:D1:G1']['assessments']),2);self.assertIsNone(by['target:D1:G13']['assessment'])
  self.assertEqual(json.loads(self.s.artifact(self.w,self.a)['content']),self.raw)
  pages=[inspect(self.s,self.w,offset=i,limit=12)['rows'] for i in range(0,50,12)];self.assertEqual(len({x['option_id'] for page in pages for x in page}),50)
 def test_recommended_then_uncertain_stays_visible_without_becoming_recommended(self):
  from evida.discovery import overview
  record_review(self.s,self.w,1,'fixture',self.review([0]))
  revised=self.review([0]);revised['assessments'][0]['status']='needs_evidence'
  revised['assessments'][0]['reason']='new matched observation needs review'
  record_review(self.s,self.w,1,'fixture',revised)
  shown=overview(self.s,self.w)
  self.assertEqual(shown['recommendations'],[])
  self.assertEqual(shown['reconsidered_options'][0]['assessment']['status'],'needs_evidence')
  self.assertEqual(shown['reconsidered_options'][0]['assessment']['reason'],'new matched observation needs review')
  self.assertEqual(shown['total'],50)
 def test_choice_and_explicit_followthrough_are_atomic_and_not_silently_changed(self):
  request={'expected_rev':1,'command_id':'review-choice','option_id':'target:D1:G13','text':'test another path','review_requested':True}
  first=choice_command(self.s,self.w,request)
  self.assertEqual(choice_command(self.s,self.w,request),first)
  state=self.s.snapshot(self.w);self.assertEqual(state['rev'],2)
  self.assertEqual(len(state['followthrough_requests']),1)
  self.assertEqual(state['followthrough_requests'][0]['id'],first['review_request_id'])
  self.assertEqual(state['followthrough_requests'][0]['status'],'pending')
  self.assertEqual(state['jobs'],[])
  with self.assertRaises(Conflict):choice_command(self.s,self.w,{**request,'review_requested':False})
  with self.assertRaises(ValueError):choice_command(self.s,self.w,{**request,'review_requested':'true'})

 def test_nonrecommended_choice_and_new_proposal_preserve_recommendations(self):
  record_review(self.s,self.w,1,'fixture',self.review([0]))
  choice_command(self.s,self.w,{'expected_rev':1,'command_id':'one','option_id':'target:D1:G13','text':'another path'})
  c=catalog(self.s,self.w);self.assertEqual(c['selected']['option_id'],'target:D1:G13');first=next(x for x in c['options'] if x['option_id']=='target:D1:G0')
  self.assertEqual(first['review_status'],'recommended');self.assertFalse(first['assessment']['current_conditions'])
  choice_command(self.s,self.w,{'expected_rev':2,'command_id':'two','label':'Unseen mechanism','text':'hypothesis'},proposal=True)
  c=catalog(self.s,self.w);self.assertEqual(c['total'],51);new=next(x for x in c['options'] if x['kind']=='researcher_proposal');self.assertIsNone(new['assessment'])
 def test_repeated_choice_is_idempotent_after_revision_changes(self):
  record_review(self.s,self.w,1,'fixture',self.review([0]))
  request={'expected_rev':1,'command_id':'repeat','option_id':'target:D1:G13','text':'another path'}
  first=choice_command(self.s,self.w,request)
  self.assertEqual(choice_command(self.s,self.w,request),first)
  self.assertEqual(self.s.snapshot(self.w)['rev'],2)
  with self.assertRaises(Conflict):choice_command(self.s,self.w,{**request,'text':'different intent'})
 def test_generated_rna_union_never_implies_unexamined_windows_screened(self):
  for start in (100,110):
   raw={'reference':{'transcript_id':'T','sequence_sha256':'same','version':'v'},'generation':{'paired_length':19,'total_possible_windows':598,'start_1_based':start,'count':20,'stride':10},'rows':[]}
   self.s.add_artifact(self.w,'rna','rna_candidate_generation',dump(raw).encode(),{},bump=False)
  coverage=catalog(self.s,self.w)['rna_search_coverage'][0]
  self.assertEqual(coverage['generated_windows'],21);self.assertEqual(coverage['remaining_windows_not_generated'],577)
 def test_observed_bad_new_option_id_rejected_by_exposed_schema(self):
  import jsonschema
  from evida.discovery import REVIEW
  value={'question':'fixture','new_options':[{'option_id':'mech-hepatic-supply','kind':'mechanism','label':'fixture mechanism','description':'fixture only','source_ids':[self.a]}],'assessments':[],'unsearched_scope':[]}
  with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,REVIEW)
  value['new_options'][0]['option_id']='mechanism:hepatic-supply'
  record_review(self.s,self.w,1,'fixture',value)
  self.assertTrue(any(x['option_id']=='mechanism:hepatic-supply' for x in catalog(self.s,self.w)['options']))
 def test_unknown_sources_and_stale_selection_rejected(self):
  bad=self.review([0]);bad['assessments'][0]['support_source_ids']=['invented']
  with self.assertRaises(ValueError):record_review(self.s,self.w,1,'fixture',bad)
  with self.assertRaises(ValueError):choice_command(self.s,self.w,{'expected_rev':1,'command_id':'bad','option_id':'absent','text':''})
  with self.assertRaises(Conflict):choice_command(self.s,self.w,{'expected_rev':0,'command_id':'stale','option_id':'target:D1:G13','text':''})
 def test_different_contexts_never_merge(self):
  x=copy.deepcopy(self.raw);x['disease']['id']='D2';self.s.add_artifact(self.w,'d2','disease_targets',dump(x).encode(),{},bump=False)
  for seq in ('AAAC','AAAG'):self.s.add_artifact(self.w,'rna','rna_candidate_generation',dump({'reference':{'transcript_id':'T1','sequence_sha256':seq},'rows':[{'id':'T1:10-28','guide_5to3':seq}]}).encode(),{},bump=False)
  self.assertEqual(catalog(self.s,self.w)['total'],102)
 def test_missing_structure_and_assay_relation_preserved(self):
  evidence={'status':'succeeded','rows':[{'molecule_chembl_id':'CHEMBL1','standard_value':'100','standard_relation':'<','assay_context':{'organism':'mouse'}},{'molecule_chembl_id':'CHEMBL1','standard_value':None},{'molecule_chembl_id':'CHEMBL2'}],'source':{'url':'fixture'},'response':{},'summary':{'total':99,'has_more':True}}
  mol={'molecules':[{'molecule_chembl_id':'CHEMBL1','molecule_structures':{'canonical_smiles':'CCO'}}]}
  with patch('evida.compound_discovery.bioactivities',return_value=evidence),patch('evida.compound_discovery.fetch',return_value=(json.dumps(mol).encode(),{'url':'fixture'})):r=collect({'target_chembl_id':'CHEMBL10','page':0})
  self.assertEqual(r['status'],'partial');self.assertEqual(len(r['rows']),2);self.assertEqual(len(r['rows'][0]['activities']),2);self.assertEqual(r['rows'][0]['activities'][0]['standard_relation'],'<');self.assertIsNone(r['rows'][1]['smiles'])
  self.assertIn('CHEMBL1,CCO,CHEMBL10',materialize(r,{'candidate_ids':['CHEMBL1'],'reason':'fixture'})['csv_text'])
  for ids in (['CHEMBL2'],['CHEMBL999']):
   with self.assertRaises(ValueError):materialize(r,{'candidate_ids':ids,'reason':'fixture'})
 def test_actual_materialization_worker_then_rdkit(self):
  from evida.runner import Runner
  from evida.gateway import Gateway
  root=Path(__file__).resolve().parents[1]
  r={'target_chembl_id':'CHEMBL10','rows':[{'candidate_id':'CHEMBL1','smiles':'CCO','structure_status':'available'}]};aid=self.s.add_artifact(self.w,'fixture','compound_candidates',dump(r).encode(),{},bump=False)
  runner=Runner(root,self.s,Gateway(json.loads((root/'configs/api_policy.json').read_text()),False),Path(self.tmp.name)/'attempts')
  try:
   args={'artifact_id':aid,'candidate_ids':['CHEMBL1'],'reason':'fixture calculation'};runner.validate_tool(self.w,'compound_selection',args)
   jid=self.s.enqueue(self.w,1,'compound_selection',args,runner.cache_key(self.w,'compound_selection',args));out=runner.run_tool_job(jid,True)
   result=json.loads(self.s.artifact(self.w,out)['content']);csv=self.s.artifact(self.w,result['molecule_csv_artifact_id']);self.assertEqual(csv['meta']['source_pool_id'],aid);self.assertEqual(self.s.snapshot(self.w)['rev'],2)
   jid=self.s.enqueue(self.w,2,'rdkit',{'artifact_id':csv['id']},None);out=runner.run_tool_job(jid,False);calc=json.loads(self.s.artifact(self.w,out)['content']);self.assertEqual(calc['summary']['calculated'],1);self.assertEqual(calc['rows'][0]['candidate_id'],'CHEMBL1');self.assertEqual(self.s.artifact(self.w,aid)['content'],dump(r).encode())
  finally:runner.pool.shutdown(wait=True)
