"""Bounded local R invocation; no corpus/labels knowledge."""
from pathlib import Path
import json,os,resource,subprocess,time
from trial_core import atomic_new,sha,load
HERE=Path(__file__).resolve().parent

def restrict():
 resource.setrlimit(resource.RLIMIT_AS,(8589934592,8589934592))
 cpus=sorted(os.sched_getaffinity(0));assert len(cpus)>=2,'Need two available CPUs'
 os.sched_setaffinity(0,cpus[:2])

def call_r(request,folder,seconds,rscript):
 start=time.monotonic();folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
 atomic_new(folder/'request.json',request)
 command=[str(rscript),'--vanilla',str(HERE/'method_worker.R'),str(folder/'request.json'),str(folder/'raw-result.json')]
 env=os.environ.copy()
 for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','GOTO_NUM_THREADS'):env[key]='2'
 receipt={'status':'started','timeout_seconds':seconds,'memory_bytes':8589934592,'cpu_affinity_count':2,'requested_math_threads':2,'method':request['method'],'task_ids':[x['task_id'] for x in request['tasks']],'request_sha256':sha(folder/'request.json'),'method_worker_sha256':sha(HERE/'method_worker.R')}
 atomic_new(folder/'started.json',receipt)
 with (folder/'stdout.txt').open('wb') as out,(folder/'stderr.txt').open('wb') as err:
  proc=subprocess.Popen(command,stdout=out,stderr=err,env=env,preexec_fn=restrict)
  receipt['pid']=proc.pid
  try:
   receipt['actual_cpu_affinity']=sorted(os.sched_getaffinity(proc.pid))
   proc.wait(timeout=max(.001,seconds-(time.monotonic()-start)));receipt.update(status='exited',returncode=proc.returncode)
  except subprocess.TimeoutExpired:
   proc.kill();proc.wait();receipt.update(status='failed_timeout',returncode=proc.returncode)
 receipt['elapsed_seconds']=time.monotonic()-start
 receipt['max_rss_kib_children_cumulative']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
 receipt['child_user_seconds_cumulative']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime
 receipt['child_system_seconds_cumulative']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime
 receipt['files']={p.name:sha(p) for p in folder.iterdir() if p.is_file() and p.name!='receipt.json'}
 atomic_new(folder/'receipt.json',receipt)
 if receipt['status']=='failed_timeout':return None,receipt
 if proc.returncode!=0:return None,receipt
 try:return load(folder/'raw-result.json'),receipt
 except (OSError,ValueError) as e:return {'status':'failed_nonfinite_or_schema','error':f'{type(e).__name__}: {e}'},receipt

def make_request(method,prior,packets):
 genes=[v['gene'] for v in packets[0]['gene_values']]
 assert all([v['gene'] for v in p['gene_values']]==genes for p in packets)
 return {'method':method,'network_path':str(prior),'genes':genes,'tasks':[{'task_id':p['task_id'],'values':[v['value'] for v in p['gene_values']]} for p in packets]}

def extract_scores(raw,method,task):
 assert raw['status']=='succeeded' and raw['method']==method
 assert raw['versions']=={'R':'4.4.3','decoupleR':'2.12.0'}
 return [{'source':x['source'],'score':x['score']} for x in raw['rows'] if x['condition']==task and x['statistic']==method]
