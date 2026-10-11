"""Offline independent rank/denominator check, Python standard library only.
Does not import the experimental scorer or launch R. Inputs/prior reconstruction
and biological target provenance cannot be verified without external source data.
"""
from pathlib import Path
import argparse,collections,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parents[1]
def load(name):
 p=ROOT/name
 return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def close(a,b):
 assert type(a) in (int,float) and type(b) in (int,float) and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12),(a,b)
def metrics(values,target):
 ordered=sorted(values.items(),key=lambda kv:kv[1]);ranks={};i=0
 while i<len(ordered):
  j=i+1
  while j<len(ordered) and ordered[j][1]==ordered[i][1]:j+=1
  for name,_ in ordered[i:j]:ranks[name]=(i+1+j)/2
  i=j
 value=values[target];below=sum(x<value for x in values.values());ties=sum(x==value for x in values.values());r=ranks[target];n=len(values)
 return dict(universe_size=n,rank=r,normalized_rank=(r-1)/(n-1),reciprocal_rank=1/r,top1=max(0,min(ties,1-below))/ties,top5=max(0,min(ties,5-below))/ties),ranks

def verify():
 manifest=ROOT/'package-manifest.json'
 if manifest.exists():
  for name,h in json.loads(manifest.read_text())['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
 results=load('data/terminal-records.json.gz');details=load('data/comparison-details.json.gz');summary=load('data/scored-results.json');availability=load('data/availability.json');panel=load('data/panel.json')
 assert len(results)==420 and len(details)==780 and len(availability)==420 and len(panel)==30
 records={(r['arm_id'],r['task_id']):r for r in results};assert len(records)==420
 tasks={p['task_id'] for p in panel};assert tasks=={f'T{i:02d}' for i in range(1,31)}
 arms={r['arm_id'] for r in results};assert len(arms)==14
 for arm in arms:assert {t for a,t in records if a==arm}==tasks
 counts=dict(collections.Counter(r['status'] for r in results));assert counts=={'succeeded':419,'failed_method':1}
 for arm,c in summary['availability_counts'].items():assert c==dict(collections.Counter(r['status'] for r in results if r['arm_id']==arm))
 assert len({(r['arm_id'],r['task_id']) for r in availability})==420
 for r in availability:
  assert r['technical_status']==records[r['arm_id'],r['task_id']]['status']
  assert r['target_usable']==(r['structural_status']=='eligible' and r['technical_status']=='succeeded')
 grouped=collections.defaultdict(list);checked_ranks=0
 for row in details:
  grouped[row['comparison']['id']].append(row);spec=row['comparison'];task=row['task_id'];u=row['universe'];target=row['target']
  assert len(set(u))==len(u) and u==sorted(u)
  a=records[spec['a'],task];b=records[spec['b'],task]
  status='target_unavailable' if target not in u else 'universe_less_than_two' if len(u)<2 else 'method_unusable' if a['status']!='succeeded' or b['status']!='succeeded' else 'paired_valid'
  assert row['status']==status,(spec['id'],task,status,row['status'])
  if status!='paired_valid':assert row['metrics_a'] is None and row['metrics_b'] is None;continue
  candidates={x['source']:x for x in row['candidate_scores_ranks']};assert set(candidates)==set(u)
  for arm,side in [(a,'a'),(b,'b')]:
   all_scores={x['source']:x['score'] for x in arm['score_rows']};assert len(all_scores)==len(arm['score_rows']) and set(u)<=set(all_scores)
   scores={tf:all_scores[tf] for tf in u};assert all(math.isfinite(v) for v in scores.values());expected,ranks=metrics(scores,target)
   for k,value in expected.items():close(row['metrics_'+side][k],value)
   for tf,c in candidates.items():assert c['score_'+side]==scores[tf];close(c['rank_'+side],ranks[tf]);checked_ranks+=1
  for metric,delta in row['delta_b_minus_a'].items():close(delta,row['metrics_b'][metric]-row['metrics_a'][metric])
 output=[]
 assert len(grouped)==len(summary['comparisons'])==26
 for s in summary['comparisons']:
  rows=grouped[s['comparison']['id']];assert len(rows)==30 and {r['task_id'] for r in rows}==tasks
  valid=[r for r in rows if r['status']=='paired_valid'];assert s['planned_tasks']==30 and s['paired_valid_tasks']==len(valid)
  assert s['status_counts']==dict(collections.Counter(r['status'] for r in rows))
  means={}
  for k,v in s['mean_delta_b_minus_a'].items():close(v,sum(r['metrics_b'][k]-r['metrics_a'][k] for r in valid)/len(valid))
  for side in ['a','b']:
   means[side]={m:sum(r['metrics_'+side][m] for r in valid)/len(valid) for m in ['normalized_rank','reciprocal_rank','top1','top5']}
  output.append({'id':s['comparison']['id'],'scope':s['comparison']['scope'],'planned':30,'valid':len(valid),'status_counts':s['status_counts'],'means':means,'deltas':s['mean_delta_b_minus_a'],'fractional_top5_totals':{side:sum(r['metrics_'+side]['top5'] for r in valid) for side in ['a','b']}})
 # Analytic tie control, independent of experimental fixture/scorer.
 m,_=metrics({'a':0,'b':0,'c':1},'a');assert m['rank']==1.5 and m['reciprocal_rank']==2/3 and m['top1']==.5
 return {'status':'PASS','terminal_records':420,'terminal_statuses':counts,'comparisons':26,'comparison_rows':780,'candidate_rank_checks':checked_ranks,'primary': [s for s in output if s['scope']=='primary'],'all_summaries':output,'scope':'Offline numeric consistency from preserved outputs; not independent method rerun, prior eligibility reconstruction, input/source authenticity, or unseen validation.','new_R_calls':0,'model_calls':0,'network_calls':0,'GPU_calls':0}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output');args=p.parse_args();result=verify()
 if args.output:Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ['primary','all_summaries']}))
