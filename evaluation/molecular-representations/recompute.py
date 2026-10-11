"""Re-execute the original frozen-feature scorer body against archived predictions.
Only path resolution, original-protocol byte binding, and output destination are
adapted. No fit, network, provider or GPU call. Does not open neural outcomes.
"""
from pathlib import Path
import argparse
import contextlib
import csv
import importlib.util
import io
import json
import math
import sys
from verify_package import HERE,read,sha,original_hash,verify,require

def compare(expected,actual,path=''):
    if isinstance(expected,dict):
        require(set(expected)==set(actual),'Keys differ: '+path)
        for key,value in expected.items():
            if key!='at_utc':compare(value,actual[key],path+'/'+key)
    elif isinstance(expected,list):
        require(len(expected)==len(actual),'Length differs: '+path)
        for index,(left,right) in enumerate(zip(expected,actual)):compare(left,right,path+'/'+str(index))
    elif isinstance(expected,(float,int)) and not isinstance(expected,bool):
        require(math.isclose(expected,actual,rel_tol=0,abs_tol=1e-12),'Number differs: '+path)
    else:require(expected==actual,'Value differs: '+path)

def run(out):
    verify();out=Path(out);require(not out.exists(),'Recalculation output must be new')
    lane=HERE/'chemeleon-trial';sys.path.insert(0,str(lane))
    spec=importlib.util.spec_from_file_location('original_frozen_feature_scorer',lane/'score_comparison.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    p=read(lane/'protocol.json')
    p['data']=str(HERE/'data');p['frozen_product']=str(HERE/'tanimoto-trial/frozen-product');p['gp_run']=str(HERE/'tanimoto-trial/run-01')
    module.load_protocol=lambda:p
    module.sha=lambda path:original_hash('chemeleon-trial/protocol.json') if Path(path)==lane/'protocol.json' else sha(path)
    saved=[];module.save=lambda path,value:saved.append((path,value))
    with contextlib.redirect_stdout(io.StringIO()):module.main()
    require(len(saved)==1,'Unexpected scorer output')
    actual=saved[0][1];expected=read(lane/'run-01/scored-results.json');compare(expected,actual)
    out.mkdir(parents=True)
    (out/'scored-results.json').write_text(json.dumps(actual,indent=2)+'\n')
    metrics=['mae','rmse','spearman','top10_recall','best_true_activity_in_selected10']
    arms=['rf','gp','chemeleon_rf','policy','prior_policy']
    with (out/'per-task.csv').open('w',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['task','test_rows','selected_policy_arm','chemeleon_completed',*[a+'_'+m for a in arms for m in metrics]])
        for row in actual['tasks']:writer.writerow([row['task'],row['n'],row['selected_policy_arm'],row['chemeleon_completed'],*[row[a][m] if row[a] else '' for a in arms for m in metrics]])
    with (out/'paired-ci.csv').open('w',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['comparison','metric','mean_difference','ci95_low','ci95_high','paired_tasks','target_clusters'])
        for name,values in actual['paired'].items():
            for metric,value in values.items():
                if value:writer.writerow([name,metric,value['mean_difference'],*value['ci95'],value['tasks'],value['target_clusters']])
    result={'status':'PASS','archived_score_agreement_atol':1e-12,'planned_tasks':actual['planned_tasks'],
            'completed_pairs':actual['completed_pairs'],'completed_test_rows':actual['completed_test_rows'],
            'scorer_function_body':'unchanged','neural_outcomes_read':False,'model_calls':0,'GPU_used':False,'network_calls':0}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    print(json.dumps(run(p.parse_args().out),indent=2))
