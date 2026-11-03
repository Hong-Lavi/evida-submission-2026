"""Inspect equality/winner/top10 masks; do not select new real candidates or score them."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
HERE=Path(__file__).resolve().parent;A=HERE.parent/'acquisition-01';sys.path.insert(0,str(A))
from acquisition import posterior_factor,fractional_top_membership
read=lambda p:json.loads(Path(p).read_text())
protocol=read(A/'protocol.json');findings=[];checked=0
for task in protocol['tasks']:
 diagnostic=read(A/'run-01'/task['task']/'posterior-diagnostic.json');groups=diagnostic['factorization']['equal_groups']
 if not groups:continue
 packet=read(task['packet'])
 with np.load(packet['posterior_path'],allow_pickle=False)as z:mean=z['mean'];cov=z['latent_covariance'];obs=z['observation_sd']
 adjusted,factor,_=posterior_factor(mean,cov)
 for seed in protocol['seeds']:
  rng=np.random.default_rng(np.random.SeedSequence([20261011,seed,1]));samples=adjusted+rng.standard_normal((8192,factor.shape[1]))@factor.T
  maximum=samples.max(axis=1);threshold=np.partition(samples,len(mean)-10,axis=1)[:,len(mean)-10]
  for g in groups:
   checked+=1;differences=np.ptp(samples[:,g],axis=1)
   if not np.any(differences):continue
   winner=samples[:,g]==maximum[:,None];above=samples[:,g]>threshold[:,None];below=samples[:,g]<threshold[:,None]
   split_winner=np.any(winner,axis=1)&~np.all(winner,axis=1)
   split_boundary=(np.any(above,axis=1)&~np.all(above,axis=1))|(np.any(below,axis=1)&~np.all(below,axis=1))
   findings.append({'task':task['task'],'seed':seed,'indices':g,'candidate_ids':[packet['candidate_ids'][i]for i in g],'nonidentical_draws':int(np.sum(differences>0)),'maximum_difference':float(differences.max()),'split_global_winner_draws':int(split_winner.sum()),'split_top10_boundary_draws':int(split_boundary.sum())})
# Find a small deterministic duplicate-factor counterexample, without actual pool data.
found=None
for n in [194,226,258,342]:
 for rank in [3,5,7,9,13,17]:
  rng=np.random.default_rng(123);factor=rng.normal(size=(n,rank));factor[-1]=factor[0];draws=rng.normal(size=(128,rank));sample=draws@factor.T
  if np.any(sample[:,0]!=sample[:,-1]):found=(n,rank,factor,draws);break
 if found:break
assert found is not None
n,rank,factor,draws=found
mean=np.full(n,-1000.);mean[[0,n-1]]=0
bad=mean+draws@factor.T
# Quotient columns computed once, then expanded. This is a proposed arithmetic repair only.
reps=np.arange(n-1);lookup=np.r_[np.arange(n-1),0];good=mean+(draws@factor[reps].T)[:,lookup]
assert np.array_equal(good[:,0],good[:,-1])
badw=bad==bad.max(axis=1)[:,None];goodw=good==good.max(axis=1)[:,None]
qpo={'split_winner_events_in_original':int(np.sum(badw[:,0]!=badw[:,-1])),'split_winner_events_in_quotient_prototype':int(np.sum(goodw[:,0]!=goodw[:,-1])),'original_individual_win_probabilities':[float(badw[:,i].mean())for i in [0,n-1]],'quotient_individual_win_probabilities':[float(goodw[:,i].mean())for i in [0,n-1]]}
# pTop10 version: nine surely-above candidates plus the two tied boundary candidates.
expanded_bad=np.column_stack([np.full((len(bad),9),1000.),bad[:,[0,n-1]]]);expanded_good=np.column_stack([np.full((len(good),9),1000.),good[:,[0,n-1]]])
pbad=fractional_top_membership(expanded_bad,10);pgood=fractional_top_membership(expanded_good,10)
ptop={'original_boundary_probabilities':pbad[:,-2:].mean(axis=0).tolist(),'quotient_boundary_probabilities':pgood[:,-2:].mean(axis=0).tolist(),'incorrect_per_draw_tie_allocations':int(np.sum(np.any(pbad[:,-2:]!=.5,axis=1)))}
report={'status':'NUMERICAL_CONTRACT_BUG_CONFIRMED','location':'acquisition.py:120 (expanded factor multiplication), consumed by exact equality at89–101 and75–86','all_actual_equal_group_seed_checks':checked,'actual_findings':findings,'actual_boundary_effect':{'split_global_winner_draws':sum(x['split_global_winner_draws']for x in findings),'split_top10_boundary_draws':sum(x['split_top10_boundary_draws']for x in findings)},'synthetic_counterexample':{'factor_shape':[n,rank],'draws':128,'duplicated_rows':[0,n-1],'maximum_difference':float(np.max(np.abs(bad[:,0]-bad[:,-1]))),'qpo':qpo,'pTop10':ptop,'fixture_seed':123,'fixture_generation':'default_rng(123): normal(factor_shape); overwrite last factor row with row0; then normal((128,rank)). Other candidate means=-1000, duplicate means=0.'},'interpretation':'Expanded duplicate factor rows need not yield bit-identical columns under BLAS. Exact winner/boundary masks can therefore violate declared equality semantics. Compute unique quotient samples once and expand via lookup. No actual alternative batch or score was generated, and original results remain unchanged.','implementation_sha256':hashlib.sha256((A/'acquisition.py').read_bytes()).hexdigest()}
(HERE/'equality-diagnosis.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='synthetic_counterexample'},indent=2));print(json.dumps({k:v for k,v in report['synthetic_counterexample'].items()if k not in ['factor','normal_draws']},indent=2))
