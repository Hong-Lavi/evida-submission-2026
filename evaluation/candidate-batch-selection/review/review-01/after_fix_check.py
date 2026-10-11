"""After-fix evidence, separate from the unchanged original reproduction."""
from pathlib import Path
import sys,json,hashlib,tempfile,unittest.mock as mock,contextlib,io,collections
HERE=Path(__file__).resolve().parent;SRC=HERE.parent/'acquisition-01';sys.path.insert(0,str(SRC))
import acquisition as a,run_selection as run,score_selection as score
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text())
save=lambda p,x:Path(p).write_text(json.dumps(x))
old_repro_sha=sha(HERE/'independent_checks.py');old_result_sha=sha(HERE/'independent-result.json')
with tempfile.TemporaryDirectory(dir=HERE,prefix='after-fix-')as td:
 td=Path(td);tasks=[]
 for i in range(2):
  task=f'SYN{i}_Ki';packet=td/(task+'.json');save(packet,{'task':task,'candidate_ids':[f'C{j}'for j in range(20)],'gp_mean':list(range(20)),'rf_mean':list(range(20)),'selected_policy_arm':'gp'})
  tasks.append({'task':task,'packet':str(packet),'n':20})
 protocol={'tasks':tasks,'methods':list(a.METHODS),'seeds':list(range(5)),'batches':[5,10,20],'mc_draws':8192,'task_timeout_seconds':180,'source_pins':{},'input_pins':{},'planned_selection_rows':240}
 save(td/'protocol.json',protocol);launched=[]
 def worker(cmd,**kwargs):
  packet=load(cmd[3]);out=Path(cmd[4]);launched.append(packet['task'])
  if len(launched)==1:
   (out/'baseline.json').write_text('[{"task":');return type('Result',(),{'returncode':-9})()
  def rows(methods,seeds):
   return [{'task':packet['task'],'method':m,'seed':s,'batch':b,'status':'completed','selected_ids':packet['candidate_ids'][-b:][::-1],'fallback_selected_ids':[],'failure':None}for m in methods for s in seeds for b in [5,10,20]]
  save(out/'baseline.json',rows(a.METHODS[:4],range(5)))
  for seed in range(5):save(out/f'posterior-seed-{seed}.json',rows(a.METHODS[4:],[seed]))
  return type('Result',(),{'returncode':0})()
 with mock.patch.object(run,'HERE',td),mock.patch.object(run,'frozen_protocol',return_value=protocol),mock.patch.object(run.subprocess,'run',side_effect=worker),contextlib.redirect_stdout(io.StringIO()):run.main()
 seal=load(td/'run-01/selection-seal.json');ledger=score.gate(protocol,td/'run-01',sha(td/'protocol.json'))
 assert len(launched)==2 and len(seal['tasks'])==2 and len(ledger)==240
 assert [t['completed_rows']for t in seal['tasks']]==[0,120]
 original=td/'run-01/SYN0_Ki/baseline.json';assert original.read_bytes()==b'[{"task":'
 artifact=next(e for e in seal['tasks'][0]['artifact_errors']if e['artifact']=='baseline.json')
 assert artifact['original_sha256']==sha(original)and artifact['error_type']=='JSONDecodeError'
 failed=[r for r in ledger if r['status']=='failed'];assert len(failed)==120
 assert sum(bool(r['fallback_selected_ids'])for r in failed)==60
 assert all('invalid_worker_artifact:'in r['failure']for r in failed)
 replay={'status':'PASS','same_first_worker_truncation_and_exit_minus9':True,'fixture_note':'Added selected_policy_arm=gp to the synthetic packet because the revised collector validates baseline scope; original failure stimulus unchanged. Second worker emits valid synthetic results to test continuation.','planned_tasks':2,'worker_launches':2,'terminal_tasks':2,'planned_rows':240,'completed_rows':120,'failed_rows':120,'posterior_fallback_rows':60,'original_truncated_bytes_preserved_and_hashed':True,'scorer_structural_gate':'PASS','gold_reads':0}
draft=load(SRC/'protocol-draft.json');prior=load(SRC/'revision-02/prior/protocol-draft.json')
assert sha(SRC/'protocol-draft.json')=='c8c2c85bbc4537bb7aed43e94a76d35791419d668c49b6b48b36e546fe6e35e7'
added=set(draft['input_pins'])-set(prior['input_pins']);assert len(added)==1306
assert all(draft['input_pins'][p]==v for p,v in prior['input_pins'].items())
assert all(Path(p).is_relative_to(SRC/'revision-02')for p in added)
assert not any(Path(p).is_relative_to(SRC/'run-01')for p in draft['input_pins'])
assert not any('test-gold' in p or 'evaluation-only' in p for p in draft['input_pins'])
for p in added:assert sha(p)==draft['input_pins'][p]
for p,v in draft['source_pins'].items():assert sha(p)==v
categories=collections.Counter('/'.join(Path(p).relative_to(SRC).parts[:2])for p in added)
# Check all sealed synthetic terminal artifacts from author's real-SIGKILL regression; no actual pool.
synthetic=[]
for path in sorted((SRC/'revision-02').glob('synthetic-killed-*/regression-result.json')):
 result=load(path);sealpath=path.parent/'run-01/selection-seal.json';assert sha(sealpath)==result['seal_sha256'];seal=load(sealpath)
 assert len(seal['tasks'])==30 and sum(x['planned_rows']for x in seal['tasks'])==3600
 for t in seal['tasks']:
  directory=sealpath.parent/t['task'];assert sha(directory/'receipt.json')==t['receipt_sha256']
  for name,pin in t['artifact_pins'].items():assert sha(directory/name)==pin
 assert result['completed_rows']==sum(t['completed_rows']for t in seal['tasks']) and result['failed_rows']==3600-result['completed_rows'] and result['gold_reads']==0
 synthetic.append({'fixture':path.parent.name,'terminal_tasks':30,'rows':3600,'completed_rows':result['completed_rows'],'failed_rows':result['failed_rows'],'receipt_artifact_hashes':'PASS'})
assert len(synthetic)==3
assert sha(HERE/'independent_checks.py')==old_repro_sha and sha(HERE/'independent-result.json')==old_result_sha
report={'status':'PASS','original_reproduction_sha256':old_repro_sha,'original_result_sha256':old_result_sha,'draft_sha256':sha(SRC/'protocol-draft.json'),'runner_sha256':sha(SRC/'run_selection.py'),'independent_after_fix':replay,'pin_audit':{'old_count':len(prior['input_pins']),'new_count':len(draft['input_pins']),'added':len(added),'removed':0,'original_pins_unchanged':True,'all_added_pins_under_revision_02':True,'added_pin_hashes_verified':len(added),'source_hashes_verified':len(draft['source_pins']),'future_actual_run_output_pins':0,'gold_file_pins':0,'categories':dict(categories),'original_176_inputs':'Pin metadata compared unchanged; actual original candidate/input contents not parsed or selected.'},'author_synthetic_receipt_checks':synthetic,'scope':'No actual dataset parsing, actual candidate selection, gold reads, model/network/GPU calls. Source and synthetic fixtures only.'}
(HERE/'after-fix-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
