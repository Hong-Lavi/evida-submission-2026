"""Independent actual-result arithmetic and posterior diagnostics; no reselection."""
from pathlib import Path
import hashlib,json,collections,itertools
import numpy as np
HERE=Path(__file__).resolve().parent;A=HERE.parent/'acquisition-01';BASE=HERE.parents[1]
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def close(x,y):assert np.isclose(x,y,rtol=0,atol=1e-12),(x,y)
protocol=read(A/'protocol.json');result=read(A/'run-01/scored-results.json');seal=read(A/'run-01/selection-seal.json')
oldprotocol=read(BASE/'tanimoto-trial/protocol.json');old=read(BASE/'tanimoto-trial/run-01/scored-results.json');oldtasks={t['task']:t for t in old['tasks']}
assert sha(A/'protocol.json')==result['protocol_sha256']==seal['protocol_sha256'];assert sha(A/'run-01/selection-seal.json')==result['selection_seal_sha256']
assert [t['task']for t in protocol['tasks']]==oldprotocol['order']==[t['task']for t in seal['tasks']]
for field in ['source_pins','input_pins']:
 for path,digest in protocol[field].items():assert sha(path)==digest
rows=[]
for t in seal['tasks']:
 d=A/'run-01'/t['task'];assert sha(d/'receipt.json')==t['receipt_sha256'];assert sha(d/'selections.json')==t['selection_sha256']
 for rel,digest in t['artifact_pins'].items():assert sha(d/rel)==digest
 rows+=read(d/'selections.json')
expected=list(itertools.product(oldprotocol['order'],protocol['methods'],protocol['seeds'],protocol['batches']))
assert [(r['task'],r['method'],r['seed'],r['batch'])for r in rows]==expected
assert len(rows)==len(result['rows'])==3600 and all(r['status']=='completed' and not r['fallback_selected_ids'] and r['failure'] is None for r in rows)
for raw,scored in zip(rows,result['rows']):assert all(scored[k]==v for k,v in raw.items())
# All existing selection seals verified above before gold parsing.
gold={};packets={};policies=collections.Counter();posterior_checks=[]
for task in protocol['tasks']:
 name=task['task'];packet=read(task['packet']);packets[name]=packet;assert sha(task['gold_path'])==task['gold_sha256']
 records=read(task['gold_path']);gold[name]={r['candidate_id']:r['p_activity']for r in records};assert len(gold[name])==task['n'] and set(gold[name])==set(packet['candidate_ids'])
 original=read(BASE/'tanimoto-trial/run-01'/name/'predictions.json');assert sha(BASE/'tanimoto-trial/run-01'/name/'predictions.json')==packet['prediction_sha256']
 assert packet['candidate_ids']==[r['candidate_id']for r in original['rows']]
 for field,ofield in [('gp_mean','gp_prediction'),('rf_mean','rf_prediction')]:assert packet[field]==[r[ofield]for r in original['rows']]
 assert packet['selected_policy_arm']==original['selected_policy_arm']==oldtasks[name]['selected_policy_arm'];policies[packet['selected_policy_arm']]+=1
 assert sha(packet['posterior_path'])==packet['posterior_sha256']
 with np.load(packet['posterior_path'],allow_pickle=False)as z:
  mean=z['mean'];cov=z['latent_covariance'];obs=z['observation_sd'];assert z['candidate_ids'].tolist()==packet['candidate_ids']
 diagnostic=read(A/'run-01'/name/'posterior-diagnostic.json');f=diagnostic['factorization'];n=len(mean)
 std=np.asarray([r['gp_latent_std']for r in original['rows']]);oldobs=np.asarray([r['gp_observation_std']for r in original['rows']])
 reconstruction=read(HERE.parent/'reconstruction-01'/ (name+'.receipt.json'))
 differences={'mean':float(np.max(np.abs(mean-packet['gp_mean']))),'latent_sd':float(np.max(np.abs(np.sqrt(np.maximum(np.diag(cov),0))-std))),'observation_sd':float(np.max(np.abs(obs-oldobs)))}
 assert max(differences.values())<=1e-7
 for field,value in differences.items():close(value,reconstruction['maximum_absolute_difference'][field])
 assert np.max(np.abs(mean-packet['gp_mean']))<=1e-7
 tol=64*np.finfo(float).eps*n*max(1,np.linalg.norm(cov,ord=np.inf));close(tol,f['covariance_tolerance'])
 mtol=64*np.finfo(float).eps*n*max(1,np.max(np.abs(mean)));close(mtol,f['mean_tolerance'])
 sym=(cov+cov.T)/2;groups=f['equal_groups'];seen=set()
 for group in groups:
  assert len(group)>1 and not seen.intersection(group);seen.update(group)
  for i,j in itertools.combinations(group,2):
   assert abs(mean[i]-mean[j])<=mtol and np.max(np.abs(sym[i]-sym[j]))<=tol and abs(sym[i,i]+sym[j,j]-2*sym[i,j])<=tol
 allgroups=groups+[[i]for i in range(n)if i not in seen];allgroups.sort(key=lambda g:g[0]);assert len(allgroups)==f['quotient_groups']
 reps=[g[0]for g in allgroups];vals,vecs=np.linalg.eigh(sym[np.ix_(reps,reps)]);keep=vals>tol;assert sum(keep)==f['quotient_rank'];lookup=np.empty(n,int)
 for i,g in enumerate(allgroups):lookup[g]=i
 factor=(vecs[:,keep]*np.sqrt(vals[keep]))[lookup];adjusted=mean[reps][lookup]
 reconstructed=factor@factor.T;close(np.max(np.abs(reconstructed-sym)),f['roundoff_projection_max_abs']);close(np.max(np.abs(adjusted-mean)),f['mean_projection_max_abs']);assert f['jitter_added']==0
 noise=obs**2-np.diag(cov);assert noise.min()>=-tol;noise=np.maximum(noise,0);close(noise.min(),diagnostic['noise_variance_min']);close(noise.max(),diagnostic['noise_variance_max'])
 # Reconstruct seed-0 draws only for moment/equality diagnostics, without selecting/ranking candidates.
 rng=np.random.default_rng(np.random.SeedSequence([20261011,0,1]));latent=adjusted+rng.standard_normal((8192,factor.shape[1]))@factor.T
 erng=np.random.default_rng(np.random.SeedSequence([20261011,0,2]));observed=latent+erng.standard_normal(latent.shape)*np.sqrt(noise)
 equality_issues=[]
 for g in groups:
  diff=np.max(np.abs(latent[:,g]-latent[:,g[0],None]),axis=1)
  if np.any(diff):
   global_max=latent.max(axis=1);winner_mask=latent[:,g]==global_max[:,None]
   split_winner=int(np.sum(winner_mask.any(axis=1)&~winner_mask.all(axis=1)))
   threshold=np.partition(latent,n-10,axis=1)[:,n-10];above=latent[:,g]>threshold[:,None];below=latent[:,g]<threshold[:,None]
   split_boundary=int(np.sum((above.any(axis=1)&~above.all(axis=1))|(below.any(axis=1)&~below.all(axis=1))))
   equality_issues.append({'indices':g,'maximum_draw_difference':float(diff.max()),'nonidentical_draws':int(np.sum(diff>0)),'split_global_winner_draws':split_winner,'split_top10_boundary_draws':split_boundary})
 latvar=latent.var(axis=0,ddof=1);obsvar=observed.var(axis=0,ddof=1);theory=np.diag(reconstructed)
 positive=theory>tol;zlat=(latvar[positive]/theory[positive]-1)/np.sqrt(2/8191);zobs=(obsvar/np.diag(reconstructed+np.diag(noise))-1)/np.sqrt(2/8191)
 for kind,samples in [('latent',latent),('observation',observed)]:
  nonunique=int(np.sum((samples==samples.max(axis=1)[:,None]).sum(axis=1)>1));assert nonunique==diagnostic['seeds']['0'][kind]['nonunique_winner_draws']
 for seed,d in diagnostic['seeds'].items():
  for kind,detail in d.items():close(sum(detail['top10_probabilities']),10.);assert min(detail['top10_probabilities'])>=0 and max(detail['top10_probabilities'])<=1
 posterior_checks.append({'task':name,'n':n,'equality_draw_issues':equality_issues,'equality_groups':len(groups),'candidates_in_equal_groups':len(seen),'latent_rank':int(sum(keep)),'covariance_projection_max_abs':f['roundoff_projection_max_abs'],'saved_marginal_sd_differences':differences,'saved_marginal_variance_max_abs_error':float(np.max(np.abs(np.diag(cov)-std**2))),'seed0_sample_latent_variance_max_standardized_deviation':float(max(abs(zlat),default=0)),'seed0_sample_observation_variance_max_standardized_deviation':float(max(abs(zobs))),'latent_nonunique_winner_draws':diagnostic['seeds']['0']['latent']['nonunique_winner_draws']})
assert policies=={'gp':25,'rf':5}
# Independent metric reconstruction: Python sorting/counts, no scorer import.
metrics={};maxerror=0.;baselinechecks=0
for r in result['rows']:
 g=gold[r['task']];ids=packets[r['task']]['candidate_ids'];chosen=r['selected_ids'];assert len(chosen)==r['batch']and len(set(chosen))==r['batch']and set(chosen)<=set(g)
 ordered=sorted(g,key=lambda i:(-g[i],i));threshold=g[ordered[9]];above=sum(v>threshold for v in g.values());tied=sum(v==threshold for v in g.values());maxgold=max(g.values());bestids={i for i,v in g.items()if v==maxgold};values=[g[i]for i in chosen]
 m={'id_top10_recall':len(set(chosen)&set(ordered[:10]))/10,'fractional_top10_recall':sum(1 if g[i]>threshold else (10-above)/tied if g[i]==threshold else 0 for i in chosen)/10,'best_any_capture':int(bool(set(chosen)&bestids)),'best_id_capture':int(ordered[0]in chosen),'fractional_best_capture':len(set(chosen)&bestids)/len(bestids),'best_activity':max(values),'simple_regret':maxgold-max(values),'mean_activity':sum(values)/len(values)}
 for k,v in m.items():close(v,r['raw_metrics'][k]);maxerror=max(maxerror,abs(v-r['raw_metrics'][k]))
 metrics[(r['task'],r['method'],r['seed'],r['batch'])]=m
 if r['method']in ['gp_mean','rf_mean','original_policy']:
  arm=packets[r['task']]['selected_policy_arm']if r['method']=='original_policy'else r['method'][:2]
  pred=dict(zip(ids,packets[r['task']][arm+'_mean']));assert chosen==sorted(ids,key=lambda i:(-pred[i],i))[:r['batch']]
  if r['batch']==10:
   original=oldtasks[r['task']]['policy'if r['method']=='original_policy'else arm];close(m['id_top10_recall'],original['top10_recall']);close(m['best_activity'],original['best_true_activity_in_selected10']);baselinechecks+=1
means={}
for summary in result['summary']:
 method,batch=summary['method'],summary['batch'];taskmeans={t['task']:{k:sum(metrics[(t['task'],method,s,batch)][k]for s in protocol['seeds'])/5 for k in metrics[(t['task'],method,0,batch)]}for t in protocol['tasks']};means[(method,batch)]=taskmeans
 for metric in next(iter(taskmeans.values())):
  avg=sum(v[metric]for v in taskmeans.values())/30
  for mode in ['raw','fallback_policy','operational_zero_hit']:close(avg,summary['modes'][mode]['task_macro'][metric])
primary=[]
for comparator in ['gp_mean','original_policy']:
 deltas={t:means[('pTop10_latent',10)][t]['id_top10_recall']-means[(comparator,10)][t]['id_top10_recall']for t in oldprotocol['order']};groups=collections.defaultdict(list)
 for spec in protocol['tasks']:groups[spec['target_cluster']].append(deltas[spec['task']])
 names=sorted(groups);rng=np.random.default_rng(protocol['bootstrap_seed']);draws=rng.integers(len(names),size=(5000,len(names)));boot=[]
 for sample in draws:
  allvalues=[v for j in sample for v in groups[names[j]]];boot.append(sum(allvalues)/len(allvalues))
 delta=sum(deltas.values())/30;ci=np.quantile(boot,[.025,.975]).tolist();existing=next(c for c in result['comparisons']if c['primary']and c['right']==comparator)
 close(delta,existing['mean_difference']);assert np.allclose(ci,existing['cluster_ci95'],rtol=0,atol=1e-12)
 primary.append({'right':comparator,'tasks':30,'clusters':len(groups),'delta':delta,'ci95':ci,'task_wins':sum(x>1e-12 for x in deltas.values()),'task_losses':sum(x< -1e-12 for x in deltas.values()),'task_ties':sum(abs(x)<=1e-12 for x in deltas.values())})
macro={m:sum(v['id_top10_recall']for v in means[(m,10)].values())/30 for m in protocol['methods']}
report={'status':'PASS','protocol_sha256':sha(A/'protocol.json'),'scored_results_sha256':sha(A/'run-01/scored-results.json'),'selection_seal_sha256':sha(A/'run-01/selection-seal.json'),'tasks':30,'clusters':29,'candidates':sum(t['n']for t in protocol['tasks']),'selection_rows':3600,'failed_rows':0,'original_policy_counts':dict(policies),'baseline_per_task_seed_parity_checks':baselinechecks,'all_raw_metric_values_recomputed':3600*8,'maximum_metric_numeric_difference':maxerror,'batch10_id_top10_recall':macro,'primary_independent_cluster_bootstrap':primary,'posterior_diagnostics':posterior_checks,'scientific_interpretation':'No clear advantage over either prespecified comparator. Both intervals include zero. This exploratory replay does not justify automatic selector replacement or retuning on the same test labels.','scope':'Read-only actual sealed result verification; CPU moment reconstruction only, no candidate reselection/refit, model/GPU/network calls or original mutation.'}
(HERE/'independent-actual-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='posterior_diagnostics'},indent=2))
