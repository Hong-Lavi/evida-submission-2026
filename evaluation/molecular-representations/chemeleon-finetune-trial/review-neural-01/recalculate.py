"""Independent CPU arithmetic after root's complete prediction seal and score.

No original metric/scoring functions imported. No fit, prediction or GPU calls.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr

HERE=Path(__file__).resolve().parent
TRIAL=HERE.parent
RUN=TRIAL/'run-01'
SEAL='56147cfba9a8e5008b8837092aaaaa5d0d9927d16ddf4e64eaae1adeed843897'
SCORE='d183e17032cc820c0891521563b99bd80d8be7c64696edcb81d4a8f622a64cbf'
GATE='ba46f1e889764bdcbeb2b2381e04bcd704bf011ec8fe3d3de4f8021e7656bde5'
METRICS=('mae','rmse','spearman','top10_recall','best_true_activity_in_selected10')

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def check(v,s):
    if not v:raise ValueError(s)
def avg(v):return math.fsum(v)/len(v)

def metrics(y,p,ids):
    errors=[a-b for a,b in zip(y,p)]
    truth=np.lexsort((np.asarray(ids),-np.asarray(y)))[:10]
    picked=np.lexsort((np.asarray(ids),-np.asarray(p)))[:10]
    rho=0. if len(set(y))==1 or len(set(p))==1 else float(spearmanr(y,p).statistic)
    return {'n':len(y),'mae':avg([abs(e) for e in errors]),
            'rmse':math.sqrt(avg([e*e for e in errors])),'spearman':rho,
            'top10_recall':len(set(truth)&set(picked))/len(truth),
            'best_true_activity_in_selected10':max(y[i] for i in picked)}

def interval(rows,left,right,key,protocol):
    groups={}
    differences=[]
    for r in rows:
        d=r[left][key]-r[right][key];differences.append(d)
        groups.setdefault(r['task'].split('_')[0],[]).append(d)
    names=sorted(groups); n=len(names)
    # Same frozen random draws; independent vector/count implementation of cluster resampling.
    rng=np.random.default_rng(protocol['bootstrap_seed'])
    draw=rng.choice(np.arange(n),size=(protocol['bootstrap_repetitions'],n),replace=True)
    sums=np.array([math.fsum(groups[k]) for k in names])
    counts=np.array([len(groups[k]) for k in names])
    boot=np.sum(sums[draw],axis=1)/np.sum(counts[draw],axis=1)
    ordered=sorted(boot)
    def percentile(q):
        pos=(len(ordered)-1)*q;lo=math.floor(pos);hi=math.ceil(pos)
        return float(ordered[lo]+(ordered[hi]-ordered[lo])*(pos-lo))
    return {'mean_difference':avg(differences),'ci95':[percentile(.025),percentile(.975)],
            'tasks':len(rows),'target_clusters':n,'negative':sum(d<0 for d in differences),
            'positive':sum(d>0 for d in differences),'ties':sum(d==0 for d in differences),
            'difference_order':left+' minus '+right}

def main():
    output=HERE/'independent-results.json'
    check(not output.exists(),'Preserve earlier independent result')
    check(sha(RUN/'sealed-predictions.json')==SEAL,'Seal mismatch')
    check(sha(RUN/'scored-results.json')==SCORE,'Root score mismatch')
    check(sha(HERE/'actual-pre-score-gate.json')==GATE,'Independent gate mismatch')
    protocol=load(TRIAL/'protocol.json');seal=load(RUN/'sealed-predictions.json')
    check(sha(TRIAL/'protocol.json')==seal['protocol_sha256'],'Protocol mismatch')
    for path,digest in protocol['source_pins'].items():check(sha(TRIAL/path)==digest,'Frozen source drift')
    completion=load(RUN/'completion.json')
    check(completion['attempts']==seal['all_expected_attempts'],'Completion/seal disagreement')
    expected=[(t['task'],a) for t in protocol['tasks'] for a in protocol['arms']]
    check([(x['task'],x['arm']) for x in completion['attempts']]==expected and len(expected)==60,'Denominator mismatch')
    sources={};neural={};reference={};timing={a:{'worker_wall_seconds':0.,'trainer_fit_seconds':0.,'epochs':0} for a in protocol['arms']}
    receipts={(r['task'],r['arm']):r for r in completion['attempts']}
    for task in protocol['tasks']:
        name=task['task'];p=TRIAL/'inputs'/f'{name}.json'
        check(sha(p)==task['input_sha256'],'Input drift');sources[name]=load(p)
        ids=[r['candidate_id'] for r in sources[name]['prediction_rows']]
        check(len(ids)==len(set(ids))==task['prediction_rows'],'Input IDs')
        p=TRIAL.parent/'tanimoto-trial/run-01'/name/'predictions.json'
        check(sha(p)==task['reference_predictions_sha256'],'Baseline drift');reference[name]=load(p)
        check([r['candidate_id'] for r in reference[name]['rows']]==ids,'Baseline IDs')
        for arm in protocol['arms']:
            e=receipts[name,arm];check(e['status']=='completed','Expected 60 completed')
            p=RUN/name/arm/'predictions.json';check(sha(p)==e['prediction_sha256'],'Prediction drift')
            check(load(RUN/name/(arm+'-receipt.json'))==e,'Receipt drift')
            record=load(p);neural[name,arm]=record
            check([r['candidate_id'] for r in record['rows']]==ids,'Neural IDs')
            check([r['candidate_id'] for r in record['validation_predictions']]==[r['candidate_id'] for r in sources[name]['validation']],'Validation IDs')
            check(record['task']==name and record['arm']==arm,'Model identity')
            check(record['input_sha256']==task['input_sha256'] and record['protocol_sha256']==seal['protocol_sha256'],'Prediction provenance')
            timing[arm]['worker_wall_seconds']+=e['seconds']
            timing[arm]['trainer_fit_seconds']+=record['fit']['fit_seconds']
            timing[arm]['epochs']+=record['fit']['epochs_completed']
    # All 60 hashes and identities checked before opening any official-test gold.
    rows=[];maximum_delta=0.;root=load(RUN/'scored-results.json');rootrows={r['task']:r for r in root['tasks']}
    for task in protocol['tasks']:
        name=task['task'];data=sources[name];ref=reference[name]
        ids=[r['candidate_id'] for r in data['prediction_rows']]
        p=Path(protocol['official_data'])/name/'evaluation-only/test-gold.json'
        check(sha(p)==task['official_gold_sha256'],'Gold pin mismatch')
        gold=load(p);mapping={r['candidate_id']:r['p_activity'] for r in gold}
        check(len(gold)==len(mapping)==len(ids) and set(mapping)==set(ids),'Gold membership')
        y=[float(mapping[cid]) for cid in ids]
        values={a:[r[a+'_prediction'] for r in ref['rows']] for a in ('rf','gp')}
        eligible=[]
        for a,rank,key in [('rf',0,'native_rf'),('gp',1,'author_gp')]:
            if ref[key]['usable']:eligible.append((ref[key]['inner_mae'],rank,a))
        prior=min(eligible)[2] if eligible else None
        check(prior==ref['selected_policy_arm'],'Original policy mismatch')
        if prior:values['original_policy']=values[prior]
        for rank,arm in enumerate(protocol['arms'],2):
            r=neural[name,arm];values[arm]=[v['prediction'] for v in r['rows']]
            val=[v['p_activity'] for v in data['validation']];vp=[v['prediction'] for v in r['validation_predictions']]
            baseline=avg([v['p_activity'] for v in data['train']])
            mae=avg([abs(a-b) for a,b in zip(val,vp)])
            mean_mae=avg([abs(v-baseline) for v in val])
            rho=0. if len(set(val))==1 or len(set(vp))==1 else round(float(spearmanr(val,vp).statistic),3)
            usable=rho>=.3 and mae<mean_mae
            check(abs(mae-r['validation_mae'])<1e-12 and abs(mean_mae-r['mean_validation_mae'])<1e-12,'Validation metric mismatch')
            check(usable==r['usable'] and rho==r['validation_spearman'],'Eligibility mismatch')
            # Use stored unrounded MAE after recomputation match to preserve exact-tie policy parity.
            if usable:eligible.append((r['validation_mae'],rank,arm))
        chosen=min(eligible)[2] if eligible else None
        if chosen:values['validation_policy']=values[chosen]
        check(chosen==rootrows[name]['selected_policy_arm'],'Expanded selector mismatch')
        check(all(math.isfinite(v) for v in y) and all(math.isfinite(v) for a in values.values() for v in a),'Nonfinite value')
        row={'task':name,'n':len(ids),'original_policy_arm':prior,'selected_policy_arm':chosen}
        for arm,pred in values.items():
            row[arm]=metrics(y,pred,ids)
            if arm!='original_policy':
                for metric in METRICS:
                    delta=abs(row[arm][metric]-rootrows[name][arm][metric]);maximum_delta=max(maximum_delta,delta)
                    check(delta<1e-12,'Task metric mismatch '+name+'/'+arm+'/'+metric)
        rows.append(row)
    arms=['rf','gp',*protocol['arms'],'validation_policy','original_policy']
    macro={a:{k:avg([r[a][k] for r in rows]) for k in METRICS} for a in arms}
    for arm in root['task_macro']:
        for key in METRICS:check(abs(macro[arm][key]-root['task_macro'][arm][key])<1e-12,'Macro mismatch')
    comparisons={};max_ci_delta=0.
    for name,existing in root['paired_comparisons'].items():
        left,right=name.split('_minus_');comparisons[name]={}
        for key in METRICS:
            v=interval(rows,left,right,key,protocol);comparisons[name][key]=v
            for field in ('tasks','target_clusters','negative','positive','ties','difference_order'):check(v[field]==existing[key][field],'Cluster metadata mismatch')
            for a,b in zip([v['mean_difference'],*v['ci95']],[existing[key]['mean_difference'],*existing[key]['ci95']]):
                max_ci_delta=max(max_ci_delta,abs(a-b));check(abs(a-b)<1e-12,'Cluster interval mismatch')
    posthoc={k:interval(rows,'validation_policy','original_policy',k,protocol) for k in METRICS}
    runtime={'neural_arms':timing,'total_gpu_worker_wall_seconds':sum(v['worker_wall_seconds'] for v in timing.values()),
             'total_trainer_fit_seconds':sum(v['trainer_fit_seconds'] for v in timing.values()),
             'historical_rf_fit_function_seconds':sum(r['native_rf']['fit_seconds'] for r in reference.values()),
             'historical_gp_fit_seconds':sum(r['author_gp']['fit_seconds'] for r in reference.values()),
             'meaning':'Worker wall sums include CPU startup/verification/IO and prediction. Trainer-fit wall sums include validation/checkpointing. Neither is GPU-kernel time or process CPU-time. Historical baselines were reused, not rerun. Coordinator overhead/scoring/preflight are not timed here.'}
    result={'status':'PASS','scope':'Independent full-data arithmetic after authorized root seal/score',
            'root_seal_sha256':SEAL,'root_score_sha256':SCORE,'independent_gate_sha256':GATE,
            'script_sha256':sha(__file__),'tasks':rows,'task_macro':macro,'paired_comparisons':comparisons,
            'maximum_task_metric_absolute_difference':maximum_delta,'maximum_CI_absolute_difference':max_ci_delta,
            'planned_tasks':30,'target_clusters':29,'neural_arms_verified':60,'rows_per_arm':sum(r['n'] for r in rows),
            'original_policy_selection':dict(Counter(r['original_policy_arm'] for r in rows)),
            'expanded_policy_selection':dict(Counter(r['selected_policy_arm'] for r in rows)),
            'post_score_descriptive_only':{'contrast':'expanded validation policy minus original RF/GP validation policy',
                'not_prespecified_primary':True,'metrics':posthoc,'rationale':'Explicit root request after original score; no changes to frozen primary/rubric or model training.'},
            'runtime':runtime,'training_calls':0,'model_inference_calls':0,'GPU_used':False}
    check(sha(RUN/'scored-results.json')==SCORE and sha(RUN/'sealed-predictions.json')==SEAL,'Root artifacts changed')
    with output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:result[k] for k in ('status','maximum_task_metric_absolute_difference','maximum_CI_absolute_difference','original_policy_selection','expanded_policy_selection')}))
    print(json.dumps({'original_policy':macro['original_policy'],'post_score_descriptive':posthoc,'runtime':runtime}))

if __name__=='__main__':main()
