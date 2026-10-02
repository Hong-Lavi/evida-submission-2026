"""Recalculate published CReM counts and descriptive CIs; no generation or inference."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import math
import numpy as np

B=Path(__file__).resolve().parent

def main():
    summary=json.loads((B/'crem-summary.json').read_text())
    with (B/'crem-per-task-metrics.csv').open(newline='') as f:rows=list(csv.DictReader(f))
    assert len(rows)==20
    errors=[];checked=0
    def compare(path,got,expected):
        nonlocal checked
        checked+=1
        if isinstance(expected,(float,int)):
            if not math.isclose(got,expected,rel_tol=1e-12,abs_tol=1e-12):errors.append({'path':path,'actual':got,'expected':expected})
        elif got!=expected:errors.append({'path':path,'actual':got,'expected':expected})
    for condition,expected in summary['conditions'].items():
        rr=[r for r in rows if r['condition']==condition]
        assert len(rr)==10 and len({r['task'] for r in rr})==10
        native=[r for r in rr if r['native_return_available']=='1']
        compare(condition+'.statuses',dict(Counter(r['status'] for r in rr)),expected['statuses'])
        compare(condition+'.native_returns',len(native),expected['native_returns_available'])
        for scope,group in [('all_closed_observed_segments',rr),('completed_task_observed_segments',native),('returned',native),('native_filter_counts',native)]:
            for key,value in expected[scope].items():
                got=sum(int(r[key]) for r in group if r[key]!='')
                compare(condition+'.'+scope+'.'+key,got,value)
        if native:
            boot=expected['completed_task_bootstrap'];rng=np.random.default_rng(boot['seed'])
            ix=rng.integers(0,len(native),size=(boot['repetitions'],len(native)))
            for label,metric in boot['metrics'].items():
                v=np.asarray([float(r['returned_mean_pairwise_diversity']) if label=='internal_diversity' else int(r[metric['numerator']])/int(r[metric['denominator']]) for r in native])
                compare(condition+'.'+label+'.mean',float(v.mean()),metric['completed_task_macro_mean'])
                ci=np.quantile(v[ix].mean(axis=1),[.025,.975])
                for i in range(2):compare(condition+'.'+label+'.ci'+str(i),float(ci[i]),metric['ci95'][i])
        for r in rr:
            if r['native_return_available']=='0':
                assert r['returned_rows']=='' and r['native_result_sha256']==''
            else:
                assert r['native_generator']=='crem_context_constrained_fragment_transformation'
                assert r['native_generator_error']==''
                assert int(r['returned_rows'])<=60
                assert int(r['returned_exact_trace_matches'])<=int(r['returned_rows'])
                assert int(r['returned_unique_connectivity'])<=int(r['returned_unique_isomeric'])<=int(r['returned_rows'])
                assert int(r['returned_novel_train_connectivity'])<=int(r['returned_novel_input_connectivity'])
    receipt={'status':'PASS' if not errors else 'FAIL','metric_checks':checked,'task_condition_rows':len(rows),'errors':errors,
             'source_sha256':{p:hashlib.sha256((B/p).read_bytes()).hexdigest() for p in ['crem-per-task-metrics.csv','crem-summary.json']},
             'new_generation_inference_network':0,'meaning':'Arithmetic reproduction from saved per-task structural metrics, not a new molecular generation trial.'}
    print(json.dumps(receipt,indent=2));assert not errors

if __name__=='__main__':main()
