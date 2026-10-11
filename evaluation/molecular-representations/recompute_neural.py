"""Run the unchanged neural scorer body on the complete public archive.

Only archival path/protocol-byte bindings and output destination are adapted.
The package verifier substitutes for the original verifier's absent weight file:
weights/checkpoints are intentionally not required for scoring saved predictions.
This is post-score reproduction, not a new pre-outcome sealing experiment.
"""
import argparse
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from verify_package import HERE,read,sha,original_hash,verify,require
from recompute import compare

def run(out):
    verify();out=Path(out);require(not out.exists(),'Recalculation output must be new')
    require(read(HERE/'finetune-status.json')['results_included'],'No terminal neural archive')
    lane=HERE/'chemeleon-finetune-trial'
    protocol_path=lane/'protocol.json';original_text=protocol_path.read_text()
    protocol=json.loads(original_text);protocol['official_data']=str(HERE/'data')
    saved=[]
    with patch.dict(sys.modules):
        for name in ('run_comparison','metrics_common'):sys.modules.pop(name,None)
        sys.path.insert(0,str(lane))
        try:
            spec=importlib.util.spec_from_file_location('archived_neural_scorer',lane/'score_comparison.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.HERE=lane;module.BASE=HERE
            module.verify=lambda p:verify()
            module.json=SimpleNamespace(loads=lambda text:dict(protocol) if text==original_text else json.loads(text),dumps=json.dumps)
            module.sha=lambda p:original_hash('chemeleon-finetune-trial/protocol.json') if Path(p)==protocol_path else sha(p)
            module.create=lambda path,value:saved.append((Path(path).name,value))
            with contextlib.redirect_stdout(io.StringIO()):module.main()
        finally:sys.path.pop(0)
    require([n for n,v in saved]==['sealed-predictions.json','scored-results.json'],'Unexpected scorer outputs')
    actual=saved[-1][1];expected=read(lane/'run-01/scored-results.json');compare(expected,actual)
    out.mkdir(parents=True)
    (out/'scored-results.json').write_text(json.dumps(actual,indent=2)+'\n')
    metrics=('mae','rmse','spearman','top10_recall','best_true_activity_in_selected10')
    arms=('rf','gp','chemeleon_finetuned','matched_random','validation_policy')
    with (out/'per-task.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['task','test_rows','selected_policy_arm',*[a+'_'+m for a in arms for m in metrics]])
        for r in actual['tasks']:w.writerow([r['task'],r['n'],r['selected_policy_arm'],*[r[a][m] if a in r else '' for a in arms for m in metrics]])
    with (out/'paired-ci.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['comparison','metric','difference','ci95_low','ci95_high','tasks','target_clusters'])
        for name,values in actual['paired_comparisons'].items():
            for m,v in values.items():
                if v:w.writerow([name,m,v['mean_difference'],*v['ci95'],v['tasks'],v['target_clusters']])
    result={'status':'PASS','archived_score_agreement_atol':1e-12,'planned_neural_arms':actual['planned_neural_arms'],
            'completed_neural_arms':actual['completed_neural_arms'],'task_coverage':actual['task_coverage'],
            'rows_by_arm':actual['completed_test_rows_by_arm'],'scorer_function_body':'unchanged',
            'bindings':['official_data path','original protocol hash','package verifier for archived pins without omitted weights','new in-memory outputs'],
            'model_calls':0,'GPU_used':False,'network_calls':0}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    print(json.dumps(run(p.parse_args().out),indent=2))
