"""Post-seal scorer. Its first data-dependent operation is the full label-free gate."""
from pathlib import Path
import argparse,collections,json,math
from trial_core import *
HERE=Path(__file__).resolve().parent

def all_ranks(scores):
 out={};ordered=sorted(scores,key=lambda s:scores[s]);i=0
 while i<len(ordered):
  j=i+1
  while j<len(ordered) and scores[ordered[j]]==scores[ordered[i]]:j+=1
  rank=(i+1+j)/2
  for tf in ordered[i:j]:out[tf]=rank
  i=j
 return out

def load_labels_after_gate(protocol):
 for name,h in protocol['source_pins'].items():
  if Path(name).name in LABEL_BASENAMES:assert sha(name)==h,('Label/source pin changed',name)
 x=load(protocol['label_path_scorer_only']);labels={v['opaque_id']:v for v in x['selected']}
 assert len(labels)==protocol['task_count']
 return labels

def comparison_specs(protocol):
 specs=[]
 for rep in ['stored_zero','omit_zero']:
  for prior in ['dorothea','collectri']:
   for comparator in ['mlm','wmean','own_expression']:
    a=f'{rep}__{prior}__ulm';b=f'{rep}__own_expression' if comparator=='own_expression' else f'{rep}__{prior}__{comparator}'
    specs.append({'id':f'within__{rep}__{prior}__ulm_vs_{comparator}','kind':'within_prior','scope':'primary' if rep=='stored_zero' else 'zero_omission_sensitivity','a':a,'b':b,'rep_a':rep,'rep_b':rep,'prior_a':prior,'prior_b':prior,'own':comparator=='own_expression'})
  for method in ['ulm','mlm','wmean']:
   specs.append({'id':f'cross_prior__{rep}__{method}','kind':'cross_prior','scope':'secondary','a':f'{rep}__dorothea__{method}','b':f'{rep}__collectri__{method}','rep_a':rep,'rep_b':rep,'prior_a':'dorothea','prior_b':'collectri','own':False})
 for prior in ['dorothea','collectri']:
  for method in ['ulm','mlm','wmean','own_expression']:
   a='stored_zero__own_expression' if method=='own_expression' else f'stored_zero__{prior}__{method}';b='omit_zero__own_expression' if method=='own_expression' else f'omit_zero__{prior}__{method}'
   specs.append({'id':f'cross_representation__{prior}__{method}','kind':'cross_representation','scope':'representation_sensitivity','a':a,'b':b,'rep_a':'stored_zero','rep_b':'omit_zero','prior_a':prior,'prior_b':prior,'own':method=='own_expression'})
 return specs

def run_score(protocol,run_dir,out_dir,verify_inputs=True,label_loader=load_labels_after_gate):
 records,packets,nets=gate(protocol,run_dir,verify_inputs=verify_inputs) # Must finish before label_loader is called.
 labels=label_loader(protocol);assert set(labels)==set(packets)
 out=Path(out_dir);out.mkdir(exist_ok=False);summaries=[];availability=[]
 arms={a['arm_id']:a for a in protocol['arms']};tasks=protocol['arms'][0]['task_order']
 for arm,task in planned(protocol):
  x=records[(arm['arm_id'],task)];target=labels[task]['metadata']['TF'];vals=view(packets[task],arm['representation']);sources=expected_sources(arm,vals,nets)
  reason='eligible'
  if target not in sources:
   if arm['method']=='own_expression':
    original={v['gene']:v['value'] for v in packets[task]['gene_values']}
    reason='unavailable_gene_absent' if target not in original else ('unavailable_zero_omitted' if arm['representation']=='omit_zero' and original[target]==0 else 'target_not_in_prior_union')
   elif target not in {r['source'] for r in nets[arm['prior']]}:reason='target_not_in_prior'
   else:reason='insufficient_represented_targets'
  availability.append({'arm_id':arm['arm_id'],'task_id':task,'structural_status':reason,'eligible_source_count':len(sources),'technical_status':x['status'],'target_usable':reason=='eligible' and x['status']=='succeeded'})
 for spec in comparison_specs(protocol):
  rows=[]
  for task in tasks:
   target=labels[task]['metadata']['TF'];va=view(packets[task],spec['rep_a']);vb=view(packets[task],spec['rep_b']);universe=set(eligible(va,nets[spec['prior_a']]))&set(eligible(vb,nets[spec['prior_b']]))
   if spec['own']:universe&={v['gene'] for v in va}&{v['gene'] for v in vb}
   universe=sorted(universe);a=records[(spec['a'],task)];b=records[(spec['b'],task)];res=pair_eval(a,b,universe,target)
   detail={'comparison':spec,'task_id':task,'target':target,'eligible_size_a':len(eligible(va,nets[spec['prior_a']])),'eligible_size_b':len(eligible(vb,nets[spec['prior_b']])),'universe':universe,**res}
   if res['status']=='paired_valid':
    sa={v['source']:v['score'] for v in a['score_rows'] if v['source'] in universe};sb={v['source']:v['score'] for v in b['score_rows'] if v['source'] in universe};ra=all_ranks(sa);rb=all_ranks(sb)
    detail['candidate_scores_ranks']=[{'source':tf,'score_a':sa[tf],'rank_a':ra[tf],'score_b':sb[tf],'rank_b':rb[tf]} for tf in universe]
   path=out/'comparisons'/spec['id']/(task+'.json');atomic_new(path,detail);rows.append(detail)
  valid=[x for x in rows if x['status']=='paired_valid'];counts=dict(collections.Counter(x['status'] for x in rows))
  summaries.append({'comparison':spec,'planned_tasks':len(tasks),'paired_valid_tasks':len(valid),'status_counts':counts,'mean_delta_b_minus_a':{metric:sum(x['delta_b_minus_a'][metric] for x in valid)/len(valid) if valid else None for metric in ['normalized_rank','reciprocal_rank','top1','top5']},'task_detail_directory':str(Path('comparisons')/spec['id'])})
 availability_counts={arm:dict(collections.Counter(x['technical_status'] for x in availability if x['arm_id']==arm)) for arm in arms}
 atomic_new(out/'availability.json',availability)
 result={'status':'SCORED_EXPLORATORY_COMPONENT_REPLAY','protocol_sha256':sha(HERE/'protocol.json'),'terminal_seal_sha256':sha(Path(run_dir)/'terminal-seal.json'),'planned_terminal_rows':len(records),'planned_tasks_per_arm':len(tasks),'availability_counts':availability_counts,'comparisons':summaries,'delta_interpretation':{'b_minus_a_normalized_rank':'positive favors a (lower rank is better)','b_minus_a_reciprocal_rank':'negative favors a (larger RR is better)','b_minus_a_topk':'negative favors a','RR':'1 / exact-tie midrank'},'scientific_scope':'published stored input representation primary; zero omission sensitivity separate; not original-measurement mask or native t/z validation'}
 atomic_new(out/'scored-results.json',result)
 atomic_new(out/'scoring-seal.json',{'status':'complete','files':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}})
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);p.add_argument('--out-dir',required=True);args=p.parse_args();result=run_score(load(HERE/'protocol.json'),args.run_dir,args.out_dir);print(json.dumps({'status':result['status'],'rows':result['planned_terminal_rows']}))
if __name__=='__main__':main()
