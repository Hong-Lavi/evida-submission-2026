"""Prepare a NEW portable tree; never trains or alters archived outputs.
Core run/fit functions remain byte-identical. Path and explicitly supplied GPU/
deadline settings are resolved in new protocol copies, with new hashes.
"""
from pathlib import Path
import argparse
from datetime import datetime
import json
import shutil
from verify_package import HERE,read,sha,verify,require

def save(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def prepare(out,lane,weights=None,gpu_uuid=None,deadline=None,offline_check=False):
    verify();out=Path(out).resolve()
    require(not out.exists(),'Output must be new')
    if not offline_check:
        require(weights is not None,'Supply the verified official weight file')
        weights=Path(weights).resolve()
        require(sha(weights)==read(HERE/'weights.json')['sha256'],'Weight hash mismatch')
    if lane=='finetune' and not offline_check:
        require(bool(gpu_uuid) and bool(deadline),'Fine-tuning requires explicit assigned GPU UUID and UTC deadline')
        require(datetime.fromisoformat(deadline).tzinfo is not None,'Deadline needs timezone')
    out.mkdir(parents=True)
    for name in ['data','tanimoto-trial','chemeleon-trial','chemeleon-finetune-trial']:
        source=HERE/name
        ignore=shutil.ignore_patterns('run-01','__pycache__') if name!='tanimoto-trial' else shutil.ignore_patterns('__pycache__')
        shutil.copytree(source,out/name,ignore=ignore)
    # Data and reference predictions are copied byte-for-byte; no archive is overwritten.
    if weights:
        destination=out/'chemeleon-trial/weights/chemeleon_mp.pt';destination.parent.mkdir()
        shutil.copy2(weights,destination)
    changes={}
    for name in ['chemeleon-trial','chemeleon-finetune-trial']:
        folder=out/name;p=read(folder/'protocol.json');before=json.loads(json.dumps(p))
        if name=='chemeleon-trial':
            p['data']=str(out/'data');p['gp_run']=str(out/'tanimoto-trial/run-01')
            p['frozen_product']=str(out/'tanimoto-trial/frozen-product')
            p['gp_protocol_sha256']=sha(out/'tanimoto-trial/protocol.json')
        else:
            p['official_data']=str(out/'data')
            if lane=='finetune':
                p['gpu_uuid']=gpu_uuid or '<offline-not-runnable>'
                p['stop_starting_new_arms_at_utc']=deadline or '<offline-not-runnable>'
        for file in p['source_pins']:
            path=folder/file
            if path.exists():p['source_pins'][file]=sha(path)
            elif not offline_check:raise FileNotFoundError(path)
        save(folder/'protocol.json',p)
        save(folder/'protocol-receipt.json',{'sha256':sha(folder/'protocol.json'),'kind':'new portable reproduction protocol','original_protocol_sha256':read(HERE/name/'protocol-receipt.json')['sha256']})
        changes[name]={k:{'original_public_value':before.get(k),'reproduction_value':v} for k,v in p.items() if before.get(k)!=v}
        if name=='chemeleon-trial':
            amendment=read(folder/'review/scoring-amendment.json')
            amendment['original_protocol_sha256']=sha(folder/'protocol.json')
            amendment['original_scorer_sha256']=sha(folder/'score_comparison.py')
            amendment['gate_sha256']=sha(folder/'review/prescore_gate.py')
            amendment['gate_tests_sha256']=sha(folder/'review/test_prescore_gate.py')
            amendment['authorization']='Reproduction-local gate binding; historical amendment retained in original package.'
            amendment['required_environment']='Use explicitly installed reproduction dependencies.'
            amendment['operator_command']='python -B review/prescore_gate.py --score'
            save(folder/'review/scoring-amendment.json',amendment)
            save(folder/'review/scoring-amendment-receipt.json',{'sha256':sha(folder/'review/scoring-amendment.json'),'kind':'new reproduction gate binding'})
    receipt={'status':'OFFLINE_LAYOUT_CHECK_ONLY' if offline_check else 'READY_TO_RUN_EXPLICITLY',
             'lane':lane,'core_source_changes':False,'protocol_changes':changes,'training_calls':0,'GPU_used':False,
             'note':'Resource identity/deadline and path/source-container bindings differ; tasks, numerical methods, budgets, seeds, stopping rule, metrics and selection criteria are unchanged.'}
    save(out/'preparation.json',receipt)
    return {'status':receipt['status'],'out':str(out),'lane':lane,'training_calls':0}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--lane',choices=['frozen','finetune'],required=True)
    p.add_argument('--weights',type=Path);p.add_argument('--gpu-uuid');p.add_argument('--deadline');p.add_argument('--offline-check',action='store_true')
    print(json.dumps(prepare(**vars(p.parse_args())),indent=2))
