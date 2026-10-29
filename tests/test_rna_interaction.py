import copy,csv,hashlib,io,json,os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from evida.rna_interaction import prepare,run,configuration,parse_rows,cache_key
from evida.contracts import FUNCTION_BY_NAME,CHECK_OPERATION,model_functions
from evida.runner import Runner
from evida.store import Store
from evida.gateway import Gateway
ROOT=Path(__file__).resolve().parents[1];sha=lambda x:hashlib.sha256(x).hexdigest()
def fixture(target='GGGGAAAACCCCUUUUGGGGAAAACCCC',guide='GGGGUUUUCCCCAAAAGGGG'):
 ref={'semantic_type':'versioned_transcript_sequence','sequence_5to3':target,'reference':{'sequence_sha256':sha(target.encode()),'transcript_id':'SYNTHETIC_SOFTWARE_FIXTURE_NOT_PUBLIC_TRANSCRIPT','version':1}}
 raw=json.dumps(ref).encode();reference={'id':'fixture-reference','sha256':sha(raw),'kind':'rna_reference','content':raw,'meta':{'synthetic_software_fixture':True}}
 result={'status':'succeeded','reference':ref['reference'],'rows':[{'id':'synthetic-guide','guide_5to3':guide,'chemistry':'modified','calculation_scope':'unmodified_sequence_surrogate_only'}]}
 raw=json.dumps(result).encode();source={'id':'fixture-guides','sha256':sha(raw),'kind':'rna_sequence_evaluation','content':raw,'meta':{'consumed_artifacts':[reference['id']],'synthetic_software_fixture':True}}
 args={'artifact_id':source['id'],'source_artifact_sha256':source['sha256'],'reference_id':reference['id'],'reference_artifact_sha256':reference['sha256'],'guide_source_pointer':'/rows/0/guide_5to3','guide_5to3':guide,'reference_start_1_based':1,'reference_end_1_based':len(target),'reference_window_5to3':target,'accessibility_window_size':len(target),'maximum_base_pair_span':min(20,len(target)),'seed_base_pairs':7,'temperature_celsius':37.,'max_interactions':3,'representation':'unmodified_sequence_proxy'}
 return source,reference,args
class BindingTests(unittest.TestCase):
 def test_exact_binding_and_explicit_modified_source_proxy(self):
  s,r,a=fixture();b=prepare(s,r,a);self.assertEqual(b['guide_sequence_sha256'],sha(a['guide_5to3'].encode()));self.assertEqual(b['source_chemistry'],'modified');self.assertEqual(b['parameters']['representation'],'unmodified_sequence_proxy')
 def test_tampered_bytes_and_mutually_forged_reported_hashes_rejected(self):
  for which in ('guide','reference'):
   s,r,a=fixture();v=s if which=='guide'else r;v['content']+=b' '
   with self.subTest(which=which),self.assertRaises(ValueError):prepare(s,r,a)
  for key,sk,objindex in [('source_artifact_sha256','sha256',0),('reference_artifact_sha256','sha256',1)]:
   vals=list(fixture());vals[objindex][sk]=vals[2][key]='0'*64
   with self.assertRaises(ValueError):prepare(*vals)
 def test_invalid_named_parameters_and_mismatched_reference(self):
  edits={'guide_source_pointer':'/rows/1/guide_5to3','guide_5to3':'A'*20,'reference_start_1_based':0,'reference_end_1_based':50001,'reference_window_5to3':'A'*28,'seed_base_pairs':True,'temperature_celsius':float('nan'),'accessibility_window_size':501,'maximum_base_pair_span':500,'max_interactions':0,'representation':'modified_RNA','command':'arbitrary'}
  for k,v in edits.items():
   s,r,a=fixture();a[k]=v
   with self.subTest(key=k),self.assertRaises(ValueError):prepare(s,r,a)
  s,r,a=fixture();s['meta']['consumed_artifacts']=['another-reference']
  with self.assertRaises(ValueError):prepare(s,r,a)
  s,r,a=fixture(target='A'*501)
  with self.assertRaises(ValueError):prepare(s,r,a)
  s,r,a=fixture();v=json.loads(s['content']);v['reference']['sequence_sha256']='0'*64;s['content']=json.dumps(v).encode();s['sha256']=a['source_artifact_sha256']=sha(s['content'])
  with self.assertRaises(ValueError):prepare(s,r,a)
 def test_normal_registration_and_research_check_schema(self):
  self.assertIn('predict_rna_interactions',FUNCTION_BY_NAME);self.assertIn('predict_rna_interactions',[f['name']for f in model_functions()]);self.assertTrue(any(v.get('properties',{}).get('name',{}).get('enum')==['predict_rna_interactions']for v in CHECK_OPERATION['anyOf']))
class AuthorTests(unittest.TestCase):
 def test_real_cpu_all52_columns_energies_and_global_coordinates(self):
  s,r,a=fixture(target='AAGGGGAAAACCCCUUUUGGGGAAAACCCCAA');a.update(reference_start_1_based=3,reference_end_1_based=30,reference_window_5to3='GGGGAAAACCCCUUUUGGGGAAAACCCC',accessibility_window_size=28)
  with tempfile.TemporaryDirectory()as t:
   work=Path(t)/'run';out=run(prepare(s,r,a),work);self.assertEqual(out['status'],'succeeded');self.assertEqual(len(out['rows']),3);self.assertEqual(len(out['author_columns']),52);self.assertEqual(out['raw_csv_text'].encode(),(work/'author-output.csv').read_bytes());self.assertEqual(out['raw_csv_sha256'],sha((work/'author-output.csv').read_bytes()))
   for row in out['rows']:
    self.assertIn(':',row['author_fields']['seedE']);self.assertEqual(row['transcript_start_1_based'],int(row['author_fields']['start1'])+2);en=row['energy_kcal_mol'];self.assertAlmostEqual(en['E'],en['E_hybrid']+en['ED1']+en['ED2'],delta=.03);self.assertNotEqual(en['E'],en['Etotal'])
   self.assertEqual(out['runtime_receipt']['threads'],1);self.assertEqual(out['model_calls'],0)
 def test_real_no_interactions_retains_success_and_conditional_reporting(self):
  s,r,a=fixture(target='A'*31,guide='A'*19)
  with tempfile.TemporaryDirectory()as t:out=run(prepare(s,r,a),Path(t)/'none')
  self.assertEqual(out['status'],'succeeded');self.assertEqual(out['rows'],[]);self.assertIn('no_interaction_reported',out['summary']['reporting_status'])
 def test_invalid_author_sequence_or_coordinates_rejected(self):
  s,r,a=fixture();b=prepare(s,r,a);header='seq1;seq2;start1;end1;start2;end2;E;ED1;ED2;E_hybrid;Etotal\n'
  for seq,start in [('CCCC',1),(a['reference_window_5to3'],0)]:
   with self.assertRaises(ValueError):parse_rows(header+f"{seq};{a['guide_5to3']};{start};20;1;20;-1;1;1;-3;-5\n",b)
 def test_timeout_after_parent_exit_with_descendant_pipe(self):
  s,r,a=fixture();cfg=configuration();cfg['timeout_seconds']=.3;actual=subprocess.Popen;launched=[]
  script="import subprocess,sys;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);Path('descendant.pid').write_text(str(p.pid))"
  def launch(command,**kw):
   p=actual([sys.executable,'-B','-c',script],**kw);launched.append(p);return p
  with tempfile.TemporaryDirectory()as t,patch('evida.rna_interaction.configuration',return_value=cfg),patch('evida.rna_interaction.subprocess.Popen',side_effect=launch):
   start=time.monotonic();work=Path(t)/'timeout'
   try:
    out=run(prepare(s,r,a),work);self.assertEqual(out['error'],'timeout');self.assertLess(time.monotonic()-start,3);child=int((work/'descendant.pid').read_text());stat=Path(f'/proc/{child}/stat')
    for _ in range(50):
     if not stat.exists()or stat.read_text().split()[2]=='Z':break
     time.sleep(.01)
    else:self.fail('descendant survived bounded process-group cleanup')
   finally:
    for p in launched:
     try:os.killpg(p.pid,signal.SIGKILL)
     except ProcessLookupError:pass
 def test_cancel_preserves_failure_input_files(self):
  s,r,a=fixture();actual=subprocess.Popen
  with tempfile.TemporaryDirectory()as t:
   work=Path(t)/'cancel'
   def launch(*args,**kw):
    (work/'intarna.cancel').write_text('operator');return actual(*args,**kw)
   with patch('evida.rna_interaction.subprocess.Popen',side_effect=launch):out=run(prepare(s,r,a),work)
  self.assertEqual(out['error'],'cancelled');self.assertIn('target.fa',[x['file']for x in out['retained_files']])
 def test_oversized_output_is_stream_hashed_without_loading(self):
  s,r,a=fixture();cfg=configuration();cfg['output_limit_bytes']=1024;actual=subprocess.Popen;old=Path.read_bytes;size=2*1024*1024
  script="from pathlib import Path;import os;Path('large.tmp').write_bytes(b'x'*(2*1024*1024));os.replace('large.tmp','author-output.csv')"
  def launch(command,**kw):return actual([sys.executable,'-B','-c',script],**kw)
  def read(path):
   if path.name=='author-output.csv':raise AssertionError('oversized CSV cannot be loaded')
   return old(path)
  with tempfile.TemporaryDirectory()as t,patch('evida.rna_interaction.configuration',return_value=cfg),patch('evida.rna_interaction.subprocess.Popen',side_effect=launch),patch.object(Path,'read_bytes',read):out=run(prepare(s,r,a),Path(t)/'oversized')
  self.assertEqual(out['error'],'output_limit');self.assertIsNone(out['raw_csv_text']);self.assertEqual(out['raw_csv_sha256'],sha(b'x'*size))
 def test_cache_includes_parameters_and_exact_sources(self):
  s,r,a=fixture();k=cache_key(ROOT,s,r,a);a['temperature_celsius']=36;self.assertNotEqual(k,cache_key(ROOT,s,r,a))
class RunnerTests(unittest.TestCase):
 def test_normal_runner_worker_retains_source_csv_reading_and_reuse(self):
  s,r,a=fixture()
  with tempfile.TemporaryDirectory()as t:
   store=Store(Path(t)/'test.sqlite3');wid=store.create('IntaRNA synthetic software fixture')['id'];rid=store.add_artifact(wid,'synthetic reference',r['kind'],r['content'],r['meta'],bump=False);s['meta']['consumed_artifacts']=[rid];sid=store.add_artifact(wid,'synthetic guides',s['kind'],s['content'],s['meta'],bump=False);a.update(artifact_id=sid,reference_id=rid)
   runner=Runner(ROOT,store,Gateway(json.loads((ROOT/'configs/api_policy.json').read_text()),False),Path(t)/'attempts')
   try:
    runner.validate_tool(wid,'rna_interactions',a);key=runner.cache_key(wid,'rna_interactions',a);jid=store.enqueue(wid,1,'rna_interactions',a,cache_key=key);aid=runner.run_tool_job(jid,False);self.assertIsNotNone(aid,str(store.snapshot(wid)['jobs']));artifact=store.artifact(wid,aid);body=json.loads(artifact['content']);self.assertEqual(body['status'],'succeeded');self.assertEqual(set(artifact['meta']['consumed_artifacts']),{sid,rid});self.assertNotIn('raw_csv_text',body)
    raw=store.artifact(wid,body['author_csv_artifact_id']);self.assertEqual(raw['sha256'],body['raw_csv_sha256']);self.assertEqual(len(list(csv.DictReader(io.StringIO(raw['content'].decode()),delimiter=';'))),3)
    view=runner.read_view(wid,'inspect_artifact',{'artifact_id':aid,'offset':0,'limit':1});self.assertEqual(view['result']['total_rows'],3);self.assertTrue(view['result']['has_more']);again=store.enqueue(wid,1,'rna_interactions',a,cache_key=key);self.assertEqual(runner.run_tool_job(again,False),aid)
   finally:runner.pool.shutdown(wait=True);runner.explanation_pool.shutdown(wait=True)
if __name__=='__main__':unittest.main()
