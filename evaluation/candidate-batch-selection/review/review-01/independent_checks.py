"""Independent synthetic-only review. No real candidate packet or label is read."""
from pathlib import Path
import sys,json,hashlib,itertools,tempfile,unittest.mock as mock
import numpy as np
HERE=Path(__file__).resolve().parent
SRC=HERE.parent/'acquisition-01'
sys.path.insert(0,str(SRC))
import acquisition as a
import run_selection as run
import score_selection as score

def save(p,x):p.write_text(json.dumps(x))
checks={}
# Independent brute-force permutation oracle for fractional boundary ties.
samples=np.asarray([[3,2,2,0],[0,0,0,0],[4,3,2,1]],float)
actual=a.fractional_top_membership(samples,2)
expected=[]
for sample in samples:
 accumulator=np.zeros(4)
 perms=list(itertools.permutations(range(4)))
 for perm in perms:
  # Stable rank supplies a uniformly random ordering within each equality group.
  order=sorted(perm,key=lambda i:-sample[i]);accumulator[order[:2]]+=1
 expected.append(accumulator/len(perms))
assert np.allclose(actual,expected)
checks['fractional_ties_match_exhaustive_uniform_orderings']='PASS'
# Unique sample-winner events: exact coverage optimum for every batch size.
rng=np.random.default_rng(5);draws=rng.normal(size=(37,6));ids=list('ABCDEF')
for size in [1,2,3,4]:
 order,_=a.qpo_order(draws,np.zeros(6),ids,size)
 utility=lambda group:np.isin(np.argmax(draws,axis=1),group).sum()
 assert utility(order)==max(utility(c)for c in itertools.combinations(range(6),size))
checks['unique_qpo_matches_exhaustive_coverage_optimum']='PASS'
# Nonunique events: oracle greedy marginal union coverage (not a global optimum claim).
s=np.asarray([[3,3,0,0],[3,3,0,0],[0,0,2,2],[0,1,0,1],[2,0,0,2]],float)
order,diag=a.qpo_order(s,np.zeros(4),list('ABCD'),3)
winners=[set(np.flatnonzero(row==max(row)))for row in s];chosen=[];covered=set()
for step in range(3):
 candidate=min(set(range(4))-set(chosen),key=lambda i:(-sum(i in w and j not in covered for j,w in enumerate(winners)),chr(65+i)))
 chosen.append(candidate);covered|={j for j,w in enumerate(winners)if candidate in w}
assert list(order)==chosen
checks['nonunique_qpo_matches_independent_greedy_union_oracle']='PASS'
# Fully equal latent candidates remain tied; nonzero measurement noise changes only y.
orders,diagnostic=a.posterior_orders(list('ABCD'),np.ones(4),np.ones((4,4)),np.ones(4)*np.sqrt(1.25),[0,1],8192,3)
assert diagnostic['factorization']['quotient_groups']==1
for d in diagnostic['seeds'].values():
 assert d['latent']['nonunique_winner_draws']==8192
 assert d['observation']['nonunique_winner_draws']==0
checks['8192_draw_latent_observation_separation']='PASS'
# Runner interruption during worker output write: synthetic protocol/tasks only.
with tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-') as td:
 td=Path(td);tasks=[]
 for i in range(2):
  task=f'SYN{i}_Ki';packet=td/(task+'.json');save(packet,{'task':task,'candidate_ids':[f'C{j}'for j in range(20)],'gp_mean':list(range(20)),'rf_mean':list(range(20))})
  tasks.append({'task':task,'packet':str(packet)})
 protocol={'tasks':tasks,'methods':list(a.METHODS),'seeds':list(range(5)),'batches':[5,10,20],'mc_draws':8192,'task_timeout_seconds':180,'source_pins':{},'input_pins':{}}
 (td/'protocol.json').write_text('{}');launched=[]
 def killed(cmd,**kwargs):
  launched.append(cmd[3]);out=Path(cmd[4]);(out/'baseline.json').write_text('[{"task":')
  return type('Result',(),{'returncode':-9})()
 error=None
 with mock.patch.object(run,'HERE',td),mock.patch.object(run,'frozen_protocol',return_value=protocol),mock.patch.object(run.subprocess,'run',side_effect=killed):
  try:run.main()
  except Exception as e:error={'type':type(e).__name__,'message':str(e)}
 checks['truncated_worker_json']={'observed_exception':error,'workers_launched':len(launched),'planned_tasks':2,'selection_seal_exists':(td/'run-01/selection-seal.json').exists(),'terminal_receipts':len(list((td/'run-01').glob('*/receipt.json'))),'expected_behavior':'Preserve truncated worker bytes, mark affected/missing rows failed, finish remaining tasks and denominator without provider/worker retry.'}
 assert error and error['type']=='JSONDecodeError' and len(launched)==1
# Independent cluster bootstrap oracle: seed averaging/task weighting then whole clusters.
protocol={'methods':['gp_mean','original_policy','pTop10_latent'],'batches':[10],'seeds':[0,1],'bootstrap_seed':11,'bootstrap_repetitions':1000}
rows=[]
for task,delta in [('SYN1_Ki',1.),('SYN1_EC50',3.),('SYN2_Ki',8.)]:
 for method in protocol['methods']:
  for seed in protocol['seeds']:
   metrics={name:(delta if method=='pTop10_latent'else 0.)for name in score.METRICS}
   rows.append({'task':task,'method':method,'seed':seed,'batch':10,'status':'completed','selected_ids':['synthetic'],'fallback_selected_ids':[],'raw_metrics':metrics,'fallback_metrics':None,'operational_zero_hit_metrics':metrics})
result=score.aggregate(rows,protocol)
primary=next(x for x in result['comparisons']if x['primary'] and x['right']=='gp_mean')
rng=np.random.default_rng(11);cluster_values=[[1.,3.],[8.]];boot=[]
for choices in rng.integers(2,size=(1000,2)):
 values=[v for c in choices for v in cluster_values[c]];boot.append(sum(values)/len(values))
assert primary['mean_difference']==4. and np.allclose(primary['cluster_ci95'],np.quantile(boot,[.025,.975]))
checks['cluster_bootstrap_independent_flattened_cluster_oracle']='PASS'
# Fail-closed final-task coverage before any gold hashing or reading, minimal fixture.
with tempfile.TemporaryDirectory(dir=HERE,prefix='gate-')as td:
 td=Path(td);save(td/'selection-seal.json',{'protocol_sha256':'synthetic','gold_read':False,'tasks':[{'task':'SYN1'}]})
 p={'source_pins':{},'input_pins':{},'tasks':[{'task':'SYN1'},{'task':'SYN2'}]};calls=[]
 with mock.patch.object(score,'sha',side_effect=lambda x:calls.append(str(x))):
  try:score.score_after_gate(p,td,'synthetic',lambda p:calls.append(str(p)))
  except ValueError:pass
  else:raise AssertionError('Incomplete gate accepted')
 assert calls==[]
checks['incomplete_final_task_blocks_hash_and_gold_parser']='PASS'
result={'scope':'Independent source review and synthetic data only; no actual selection, task packet, gold, GPU, model or network calls.','checks':checks,'source_sha256':{n:hashlib.sha256((SRC/n).read_bytes()).hexdigest()for n in ['acquisition.py','selection_worker.py','run_selection.py','score_selection.py','freeze_protocol.py','common.py','prepare_protocol.py','protocol-draft.json']}}
(HERE/'independent-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
