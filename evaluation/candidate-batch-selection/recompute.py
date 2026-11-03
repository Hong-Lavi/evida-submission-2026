"""Independent offline score/CI recomputation from every preserved selection and label."""
from pathlib import Path
import argparse,collections,csv,hashlib,json
import numpy as np
ROOT=Path(__file__).resolve().parent

def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def assert_close(a,b):
 if a is None or b is None:assert a==b
 else:assert np.isclose(a,b,rtol=0,atol=1e-12),(a,b)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
 source=load(ROOT/'source-map.json');index={x['original_locator']:x for x in source['files']}
 # Check complete exported artifact integrity before scores.
 for e in source['files']:assert sha(ROOT/e['public_path'])==e['public_sha256'],e['public_path']
 def original(rel,want):assert index['@AUDIT/batch-selection-trial/'+rel]['original_sha256']==want,rel
 first=None;allsummary=[];allcomparisons=[];receipts=[]
 for version in ['acquisition-01','acquisition-02']:
  folder=ROOT/'records'/version;protocol=load(folder/'protocol.json');result=load(folder/'run-01/scored-results.json');seal=load(folder/'run-01/selection-seal.json')
  original(version+'/protocol.json',result['protocol_sha256']);original(version+'/run-01/selection-seal.json',result['selection_seal_sha256'])
  taskids=[t['task']for t in protocol['tasks']];assert len(taskids)==30 and len(set(t['target_cluster']for t in protocol['tasks']))==29
  rows=[]
  for terminal in seal['tasks']:
   task=terminal['task'];d=folder/'run-01'/task;original(version+'/run-01/'+task+'/receipt.json',terminal['receipt_sha256'])
   for name,digest in terminal['artifact_pins'].items():original(version+'/run-01/'+task+'/'+name,digest)
   rows+=load(d/'selections.json')
  expected=[(t,m,s,b)for t in taskids for m in protocol['methods']for s in protocol['seeds']for b in protocol['batches']]
  assert len(rows)==3600 and [(r['task'],r['method'],r['seed'],r['batch'])for r in rows]==expected
  assert all(r['status']=='completed'and not r['fallback_selected_ids']and r['failure']is None for r in rows)
  assert all(all(b[k]==v for k,v in a.items())for a,b in zip(rows,result['rows']))
  gold={t:{r['candidate_id']:r['p_activity']for r in load(ROOT/'data'/t/'gold.json')}for t in taskids}
  for t in protocol['tasks']:assert sha(ROOT/'data'/t['task']/'gold.json')==t['gold_sha256']
  values={};maxerror=0
  for r in result['rows']:
   t,m,s,b=r['task'],r['method'],r['seed'],r['batch'];g=gold[t];chosen=r['selected_ids'];order=sorted(g,key=lambda i:(-g[i],i))
   assert len(set(chosen))==b and set(chosen)<=set(g)
   threshold=g[order[9]];above=sum(v>threshold for v in g.values());ties=sum(v==threshold for v in g.values());best=max(g.values());bestids={i for i,v in g.items()if v==best};picked=[g[i]for i in chosen]
   metrics={'id_top10_recall':len(set(chosen)&set(order[:10]))/10,'fractional_top10_recall':sum(1 if g[i]>threshold else (10-above)/ties if g[i]==threshold else 0 for i in chosen)/10,'best_any_capture':int(bool(set(chosen)&bestids)),'best_id_capture':int(order[0]in chosen),'fractional_best_capture':len(set(chosen)&bestids)/len(bestids),'best_activity':max(picked),'simple_regret':best-max(picked),'mean_activity':sum(picked)/len(picked)}
   for name,value in metrics.items():assert_close(value,r['raw_metrics'][name]);maxerror=max(maxerror,abs(value-r['raw_metrics'][name]))
   assert r['raw_metrics']==r['operational_zero_hit_metrics']and r['fallback_metrics']is None
   values[(t,m,s,b)]=metrics
  taskmeans={};summaries=[]
  for row in result['summary']:
   m,b=row['method'],row['batch'];bytask={t:{metric:sum(values[(t,m,s,b)][metric]for s in protocol['seeds'])/len(protocol['seeds'])for metric in values[(t,m,0,b)]}for t in taskids};taskmeans[(m,b)]=bytask
   means={metric:sum(v[metric]for v in bytask.values())/30 for metric in next(iter(bytask.values()))}
   for mode in ['raw','fallback_policy','operational_zero_hit']:
    assert row['modes'][mode]['tasks']==30
    for metric,v in means.items():assert_close(v,row['modes'][mode]['task_macro'][metric])
   summaries.append({'attempt':version,'method':m,'batch':b,'tasks':30,'completed_rows':150,'failed_rows':0,**means})
  # Independent bootstrap via cluster multiplicities expanded to per-task weights.
  clusters=sorted({t['target_cluster']for t in protocol['tasks']});cluster_index={name:i for i,name in enumerate(clusters)};taskcluster={t['task']:t['target_cluster']for t in protocol['tasks']}
  rng=np.random.default_rng(protocol['bootstrap_seed']);draws=rng.integers(len(clusters),size=(protocol['bootstrap_repetitions'],len(clusters)))
  multiplicities=np.asarray([np.bincount(d,minlength=len(clusters))for d in draws]);weights=multiplicities[:,[cluster_index[taskcluster[t]]for t in taskids]];denominator=weights.sum(axis=1)
  compared=[]
  for c in result['comparisons']:
   delta=np.asarray([taskmeans[(c['left'],c['batch'])][t][c['metric']]-taskmeans[(c['right'],c['batch'])][t][c['metric']]for t in taskids]);point=float(delta.mean());interval=np.quantile((weights@delta)/denominator,[.025,.975]).tolist()
   assert c['tasks']==30 and c['target_clusters']==29;assert_close(point,c['mean_difference'])
   for x,y in zip(interval,c['cluster_ci95']):assert_close(x,y)
   compared.append({'attempt':version,**c})
  if first is None:first=result
  else:assert result['rows']==first['rows']and result['summary']==first['summary']and result['comparisons']==first['comparisons']
  allsummary+=summaries;allcomparisons+=compared;receipts.append({'attempt':version,'selection_rows':3600,'raw_metric_values':28800,'summaries':len(summaries),'paired_intervals':len(compared),'maximum_numeric_error':maxerror,'all_complete':True})
 with (args.out/'all-method-metrics.csv').open('w',newline='')as f:
  w=csv.DictWriter(f,fieldnames=list(allsummary[0]));w.writeheader();w.writerows(allsummary)
 (args.out/'all-paired-comparisons.json').write_text(json.dumps(allcomparisons,indent=2)+'\n')
 report={'status':'PASS','attempts':receipts,'all_scientific_rows_summaries_intervals_identical_between_attempts':True,'tolerance':1e-12,'implementation':'Independent sorting/counting and per-task expanded cluster bootstrap; original score functions not imported.','scope':'Offline metric recomputation from packaged labels and selections; no refit, sampling rerun, provider, network or GPU calls.'}
 (args.out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
