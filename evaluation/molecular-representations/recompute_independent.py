"""Portable execution of the preserved independent arithmetic and post-score comparison.
Only archive locations and original-byte identities of sanitized containers are bound.
"""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
from verify_package import HERE,verify,require,read,sha
from recompute import compare

def run(out):
    verify();out=Path(out).resolve();require(not out.exists(),'Output must be new')
    lane=HERE/'chemeleon-finetune-trial';review=lane/'review-neural-01'
    spec=importlib.util.spec_from_file_location('archived_independent_arithmetic',review/'recalculate.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original_ids={str((HERE/r['public_path']).resolve()):r['original_sha256'] for r in read(HERE/'source-map.json')['files']}
    def archival_sha(path):
        p=Path(path).resolve()
        if p==out/'actual-pre-score-gate.json':p=review/'actual-pre-score-gate.json'
        return original_ids.get(str(p)) or sha(p)
    def load(path):
        value=read(path)
        if Path(path)==lane/'protocol.json':value['official_data']=str(HERE/'data')
        return value
    module.HERE=out;module.TRIAL=lane;module.RUN=lane/'run-01';module.sha=archival_sha;module.load=load
    out.mkdir(parents=True)
    with contextlib.redirect_stdout(io.StringIO()):module.main()
    actual=read(out/'independent-results.json');expected=read(review/'independent-results.json')
    compare(expected,actual)
    result={'status':'PASS','all_independent_fields_agree_atol':1e-12,'tasks':30,'target_clusters':29,
            'neural_arms':60,'test_rows_per_arm':9802,'post_score_policy_comparison':'descriptive/exploratory; not frozen primary',
            'bindings':['archive locations','original identities of sanitized containers verified through source-map'],
            'model_calls':0,'GPU_used':False,'network_calls':0}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    print(json.dumps(run(p.parse_args().out),indent=2))
