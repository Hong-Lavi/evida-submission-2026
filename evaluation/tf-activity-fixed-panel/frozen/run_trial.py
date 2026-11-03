"""Single approved CPU replay. Requires explicit reviewed execution receipt; no label loading."""
from pathlib import Path
import argparse,json,multiprocessing,os,signal,time,traceback
from trial_core import *
from worker_runtime import call_r,make_request,extract_scores,restrict
HERE=Path(__file__).resolve().parent

def artifact_refs(root,folder):
 return [{'path':str(p.relative_to(root)),'sha256':sha(p)} for p in sorted(folder.rglob('*')) if p.is_file()]

def write_record(root,protocol,arm,packet,status,error=None,scores=None,folder=None,terminal_origin="driver"):
 x=record_base(protocol,arm,packet);x.update(terminal_origin=terminal_origin,status=status,error=error,score_rows=scores or [],artifacts=artifact_refs(root,folder) if folder and folder.exists() else [])
 if folder:x['call_dir']=str(folder.relative_to(root))
 if arm['method']=='own_expression' and status=='succeeded':
  original={v['gene']:v['value'] for v in packet['gene_values']};names={z['source'] for rows in networks(protocol).values() for z in rows}
  x['unavailable']=[{'source':tf,'reason':'unavailable_gene_absent' if tf not in original else 'unavailable_zero_omitted'} for tf in sorted(names) if tf not in original or (arm['representation']=='omit_zero' and original[tf]==0)]
 atomic_new(root/result_name(arm['arm_id'],packet['task_id']),x)

def run_all(protocol,root):
 os.setsid() # Outer supervisor can stop all descendants in this private run group.
 restrict()
 packets=read_packets(protocol);nets=networks(protocol)
 try:
  config=verify_sources(protocol)
  for arm in protocol['arms']:
   verify_sources(protocol)
   arm_start=time.monotonic();deadline=arm_start+arm['wall_seconds']
   atomic_new(root/'arms'/arm['arm_id']/'started.json',{'arm_id':arm['arm_id'],'monotonic_start':arm_start,'wall_seconds':arm['wall_seconds']})
   if arm['method']=='own_expression':
    for task in arm['task_order']:
     if time.monotonic()>=deadline:break
     p=packets[task];vals=view(p,arm['representation']);expect=set(expected_sources(arm,vals,nets));scores=[{'source':v['gene'],'score':v['value']} for v in vals if v['gene'] in expect]
     write_record(root,protocol,arm,p,'succeeded',scores=scores)
   else:
    groups=[arm['task_order']] if arm['batching']=='one_30_column_matrix' else [[t] for t in arm['task_order']]
    for i,tasks in enumerate(groups):
     remaining=deadline-time.monotonic()
     if remaining<=0:break
     verify_sources(protocol)
     folder=root/'calls'/arm['arm_id']/f'call-{i+1:02d}'
     ps=[{'task_id':t,'gene_values':view(packets[t],arm['representation'])} for t in tasks]
     for t in tasks:atomic_new(root/'call-started'/arm['arm_id']/(t+'.json'),{'task_id':t,'arm_id':arm['arm_id'],'call_dir':str(folder.relative_to(root))})
     raw=None;receipt={};failure=None
     try:
      request=make_request(arm['method'],protocol['priors'][arm['prior']]['path'],ps)
      raw,receipt=call_r(request,folder,max(.001,deadline-time.monotonic()),config['rscript'])
      if raw is None:
       status='failed_timeout' if receipt.get('status')=='failed_timeout' else 'failed_method';failure=json.dumps(receipt)
      elif raw['status']!='succeeded':status=raw.get('status','failed_method');failure=str(raw.get('error','Method failed'))
      else:status='succeeded'
      if failure and any(z in failure.lower() for z in ('cannot allocate vector','cannot allocate memory','memory exhausted')):status='failed_memory'
     except Exception as e:
      status='failed_nonfinite_or_schema';failure=f'{type(e).__name__}: {e}'
      atomic_new(folder/'dispatch-error.json',{'error':failure})
     if status not in STATUSES:status='failed_nonfinite_or_schema'
     for task in tasks:
      scores=None;rowstatus=status;error=failure
      if status=='succeeded':
       try:
        scores=extract_scores(raw,arm['method'],task);x=record_base(protocol,arm,packets[task]);x['score_rows']=scores;validate_success(x,arm,packets[task],nets)
       except Exception as e:rowstatus='failed_nonfinite_or_schema';error=f'{type(e).__name__}: {e}';scores=None
      write_record(root,protocol,arm,packets[task],rowstatus,error,scores,folder)
   for task in arm['task_order']:
    if not (root/result_name(arm['arm_id'],task)).exists():write_record(root,protocol,arm,packets[task],'not_started_arm_deadline','Arm total deadline reached before this task was dispatched')
   atomic_new(root/'arms'/arm['arm_id']/'completed.json',{'arm_id':arm['arm_id'],'elapsed_seconds':time.monotonic()-arm_start})
 except BaseException as e:
  atomic_new(root/'runner-stop.json',{'error_type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc(),'source_integrity_stop':True})
  raise

def finalize_missing(protocol,root,reason,integrity_ok,packets=None):
 packets=packets or read_packets(protocol)
 for arm,task in planned(protocol):
  if (root/result_name(arm['arm_id'],task)).exists():continue
  marker=root/'call-started'/arm['arm_id']/(task+'.json');folder=None
  if not integrity_ok:status='skipped_source_integrity_stop'
  elif marker.exists():status='failed_timeout' if reason=='outer_deadline' else 'failed_nonfinite_or_schema'
  else:status='not_started_arm_deadline'
  if marker.exists():folder=secure_file(root,load(marker)['call_dir'])
  write_record(root,protocol,arm,packets[task],status,f'{reason}; dispatched={marker.exists()}',folder=folder,terminal_origin='supervisor_recovery')

def verify_freeze(protocol,approval):
 freeze=load(HERE/'execution-freeze.json')
 assert approval['execute_actual_panel'] is True and approval['independent_review_passed'] is True
 assert approval['protocol_sha256']==sha(HERE/'protocol.json')
 assert approval['execution_freeze_sha256']==sha(HERE/'execution-freeze.json')
 for name,h in freeze['files'].items():assert sha(HERE/name)==h,('Execution code changed',name)
 verify_sources(protocol)
 return freeze

def wait_supervised(proc,seconds):
 proc.join(seconds)
 if proc.is_alive():
  try:os.killpg(proc.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  proc.join(10)
  assert not proc.is_alive(),'Worker group did not terminate'
  return 'outer_deadline'
 return 'completed' if proc.exitcode==0 else 'runner_failed'

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--run-dir',required=True);parser.add_argument('--approval',required=True);args=parser.parse_args()
 protocol=load(HERE/'protocol.json');approval=load(args.approval);verify_freeze(protocol,approval)
 root=Path(args.run_dir).resolve();assert root.is_relative_to(HERE.parent.resolve());root.mkdir(exist_ok=False)
 packets=read_packets(protocol) # Input-only snapshots retained in parent for terminal recovery.
 atomic_new(root/'run-started.json',{'protocol_sha256':sha(HERE/'protocol.json'),'execution_freeze_sha256':sha(HERE/'execution-freeze.json'),'approval_sha256':sha(args.approval),'planned_rows':protocol['planned_terminal_rows'],'monotonic_start':time.monotonic()})
 proc=multiprocessing.get_context('fork').Process(target=run_all,args=(protocol,root));proc.start();start=time.monotonic();reason='completed'
 try:
  reason=wait_supervised(proc,protocol['limits']['outer_supervisor_seconds'])
 except BaseException:
  reason='supervisor_interrupted'
  try:os.killpg(proc.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  proc.join(10)
 finally:
  integrity_ok=True
  try:verify_freeze(protocol,approval)
  except Exception:integrity_ok=False
  if (root/'runner-stop.json').exists() and load(root/'runner-stop.json').get('source_integrity_stop'):integrity_ok=False
  finalize_missing(protocol,root,reason,integrity_ok,packets)
  names=[result_name(a['arm_id'],t) for a,t in planned(protocol)];assert all((root/n).exists() for n in names)
  atomic_new(root/'supervisor-receipt.json',{'reason':reason,'child_exitcode':proc.exitcode,'elapsed_seconds':time.monotonic()-start,'source_integrity_valid':integrity_ok,'terminal_rows':len(names)})
  files={str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
  atomic_new(root/'terminal-seal.json',{'status':'complete_terminal','protocol_sha256':sha(HERE/'protocol.json'),'source_integrity_valid':integrity_ok,'terminal_rows':len(names),'files':files})
  print(json.dumps({'reason':reason,'terminal_rows':len(names),'source_integrity_valid':integrity_ok,'terminal_seal_sha256':sha(root/'terminal-seal.json')}))
if __name__=='__main__':main()
