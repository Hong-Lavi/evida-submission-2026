"""Read existing label-free posteriors; no candidate selection or gold access."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
from acquisition import posterior_factor,sample_latent
HERE=Path(__file__).resolve().parent

def deny(event,args):
 if event=='open'and isinstance(args[0],(str,bytes)):
  if any(x in str(args[0])for x in ['evaluation-only','test-gold','scored-results']):raise PermissionError('No gold/scored-output access in prefreeze equality verification')
sys.addaudithook(deny)
protocol=json.loads((HERE.parent/'acquisition-01/protocol.json').read_text());checks=[]
for task in protocol['tasks']:
 packet=json.loads(Path(task['packet']).read_text())
 with np.load(packet['posterior_path'],allow_pickle=False)as p:mean,cov=p['mean'],p['latent_covariance']
 adjusted,factor,diagnostic=posterior_factor(mean,cov)
 for seed in protocol['seeds']:
  if not diagnostic['equal_groups']:continue
  rng=np.random.default_rng(np.random.SeedSequence([20261011,seed,1]))
  samples=sample_latent(adjusted,factor,diagnostic['equal_groups'],rng,8192)
  for group in diagnostic['equal_groups']:
   assert all(np.array_equal(samples[:,group[0]],samples[:,i])for i in group)
   checks.append({'task':task['task'],'seed':seed,'indices':group,'bit_identical':True})
assert len(checks)==110
result={'status':'PASS','group_seed_checks':110,'all_bit_identical':True,'actual_selection_runs':0,'gold_reads':0,'scored_output_reads':0,'source_sha256':hashlib.sha256((HERE/'acquisition.py').read_bytes()).hexdigest(),'checks':checks}
with (HERE/'equality-prefreeze-result.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in result.items()if k!='checks'}))
