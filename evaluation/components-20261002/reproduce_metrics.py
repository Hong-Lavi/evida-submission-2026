"""Recompute aggregate metrics/CI from the accompanying public metric CSVs.

Requires NumPy. No models, source text, network, molecular inference, or training.
This recomputes aggregate arithmetic, not the original predictions or judgments.
"""
from pathlib import Path
import csv,json,math
import numpy as np

B=Path(__file__).resolve().parent
expected=json.loads((B/'methods-summary-stage1.json').read_text())
with (B/'nfcorpus-per-query-metrics.csv').open() as f:queries=list(csv.DictReader(f))
with (B/'moleculeace-per-task-metrics.csv').open() as f:tasks=list(csv.DictReader(f))
assert len(queries)==323 and len(tasks)==30
keys=['ndcg_at_10','recall_at_10','recall_at_100','mrr_at_10']
rng=np.random.default_rng(20261002)
delta=np.asarray([[float(r['medcpt_'+k])-float(r['bm25_'+k]) for k in keys] for r in queries])
boot=delta[rng.integers(0,323,(2000,323))].mean(axis=1)
retrieval={}
for i,k in enumerate(keys):
    result={'bm25':float(np.mean([float(r['bm25_'+k]) for r in queries])),
            'medcpt':float(np.mean([float(r['medcpt_'+k]) for r in queries])),
            'difference':float(delta[:,i].mean()),'paired_query_bootstrap95':np.quantile(boot[:,i],[.025,.975]).tolist()}
    for name,value in result.items():assert np.allclose(value,expected['retrieval']['metrics'][k][name],rtol=0,atol=1e-12)
    retrieval[k]=result
rng=np.random.default_rng(20261002);index=rng.integers(0,30,size=(2000,30))
rf={}
for metric in ['mae','rmse']:
    prediction=np.asarray([float(r[metric]) for r in tasks]);baseline=np.asarray([float(r['training_mean_'+metric]) for r in tasks])
    delta=baseline-prediction;interval=np.quantile(delta[index].mean(axis=1),[.025,.975]).tolist()
    rf[metric]={'native_rf':float(prediction.mean()),'training_mean':float(baseline.mean()),
                'improvement':float(delta.mean()),'paired_task_bootstrap95':interval}
    target=expected['activity_prediction']['metrics'];e=target['paired_task_bootstrap'][metric+'_improvement_over_mean']
    assert math.isclose(rf[metric]['native_rf'],target['macro'][metric],abs_tol=1e-12)
    assert math.isclose(rf[metric]['training_mean'],target['macro']['training_mean_'+metric],abs_tol=1e-12)
    assert np.allclose(interval,e['ci95'],rtol=0,atol=1e-12)
    assert math.isclose(float(delta.mean()),e['mean'],abs_tol=1e-12)
assert sum(int(r['official_test']) for r in tasks)==9802
assert sum(int(r['cliff_n']) for r in tasks)==3790
assert all(r['native_gate_usable']=='True' for r in tasks)
print(json.dumps({'status':'PASS','scope':'Aggregate arithmetic and registered bootstrap reproduced from saved metrics; no new scientific execution.',
                  'retrieval':retrieval,'activity_prediction':rf,'new_model_training_generation_network_calls':0},indent=2))
