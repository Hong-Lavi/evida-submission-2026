"""Offline integrity, denominator and core-code verification. No fitting/imported ML engines."""
from pathlib import Path
import ast
import hashlib
import json
import re

def canonical_ast(node):
    if isinstance(node, ast.AST):
        return [type(node).__name__, [[key, canonical_ast(value)] for key, value in ast.iter_fields(node) if value is not None and value != []]]
    if isinstance(node, list):return [canonical_ast(value) for value in node]
    return node

HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def require(ok,message):
    if not ok:raise ValueError(message)
def original_hash(relative):
    entries=read(HERE/'source-map.json')['files']
    return next(row['original_sha256'] for row in entries if row['public_path']==relative)

def verify():
    sources=read(HERE/'source-map.json')['files']
    for row in sources:
        require(sha(HERE/row['public_path'])==row['public_sha256'],'Packaged source changed: '+row['public_path'])
    manifest=HERE/'package-manifest.json'
    if manifest.exists():
        for name,digest in read(manifest)['files'].items():
            require(sha(HERE/name)==digest,'Package changed: '+name)
    for row in read(HERE/'provenance/portable-source-check.json')['files']:
        require(sha(HERE/row['source'])==row['original_file_sha256']==row['public_file_sha256'],'Core byte identity changed: '+row['source'])
        tree=ast.parse((HERE/row['source']).read_text())
        actual={n.name:hashlib.sha256(json.dumps(canonical_ast(n),ensure_ascii=False,separators=(',', ':')).encode()).hexdigest()
                for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
        require(actual==row['function_ast_sha256'],'Core function changed: '+row['source'])
    p=read(HERE/'chemeleon-trial/protocol.json')
    require(len(p['tasks'])==30 and [r['task'] for r in p['tasks']]==p['order'],'Frozen task denominator')
    run=HERE/'chemeleon-trial/run-01'
    seal=read(run/'sealed-predictions.json')
    require(seal['protocol_sha256']==original_hash('chemeleon-trial/protocol.json'),'Original protocol binding')
    require([r['task'] for r in seal['tasks']]==p['order'],'Terminal task coverage')
    for task,receipt in zip(p['tasks'],seal['tasks']):
        name=task['task'];out=run/name
        require(read(out/'receipt.json')==receipt,'Receipt/seal mismatch: '+name)
        require(receipt['status'] in ['completed','failed','timeout'],'Nonterminal frozen task')
        if receipt['prediction_sha256']:
            require(sha(out/'predictions.json')==receipt['prediction_sha256'],'Prediction changed: '+name)
        for file,key in [('train.json','train_sha256'),('test-features.json','features_sha256'),('evaluation-only/test-gold.json','gold_sha256')]:
            require(sha(HERE/'data'/name/file)==task[key],'Frozen data changed: '+name+'/'+file)
        require(sha(HERE/'tanimoto-trial/run-01'/name/'predictions.json')==p['gp_prediction_pins'][name],'Reference changed: '+name)
    f=read(HERE/'chemeleon-finetune-trial/protocol.json')
    require(len(f['tasks'])==30 and len(f['arms'])==2,'Neural planned denominator')
    for task in f['tasks']:
        require(sha(HERE/'chemeleon-finetune-trial/inputs'/(task['task']+'.json'))==task['input_sha256'],'Neural input changed')
    status=read(HERE/'finetune-status.json')
    if status['results_included']:
        run=HERE/'chemeleon-finetune-trial/run-01'
        completion=read(run/'completion.json')
        neural_seal=read(run/'sealed-predictions.json')
        neural_score=read(run/'scored-results.json')
        expected=[(t['task'],arm) for t in f['tasks'] for arm in f['arms']]
        require([(r['task'],r['arm']) for r in completion['attempts']]==expected,'Neural terminal denominator')
        require(completion['status']=='prediction_generation_finished','Neural run not finished')
        require(completion['protocol_sha256']==original_hash('chemeleon-finetune-trial/protocol.json'),'Neural protocol binding')
        require(completion['attempts']==neural_seal['all_expected_attempts'],'Neural seal/ledger mismatch')
        require(neural_score['prediction_seal_sha256']==sha(run/'sealed-predictions.json'),'Neural score/seal binding')
        require(neural_score['protocol_sha256']==completion['protocol_sha256'],'Neural score/protocol binding')
        terminal={'completed','failed','timed_out','failed_missing_predictions','not_started_resource_busy','not_started_time_budget'}
        completed=0
        for row in completion['attempts']:
            require(row['status'] in terminal,'Unknown/nonterminal neural status')
            require(read(run/row['task']/(row['arm']+'-receipt.json'))==row,'Individual neural receipt mismatch')
            if row['prediction_sha256']:
                require(sha(run/row['task']/row['arm']/'predictions.json')==row['prediction_sha256'],'Neural prediction changed')
            if row['status']=='completed':
                completed+=1
                require(bool(row['prediction_sha256']) and row['returncode']==0,'Completed neural hash/returncode missing')
                record=read(run/row['task']/row['arm']/'predictions.json')
                require(record['task']==row['task'] and record['arm']==row['arm'],'Neural model identity')
                data=read(HERE/'chemeleon-finetune-trial/inputs'/(row['task']+'.json'))
                require([r['candidate_id'] for r in record['rows']]==[r['candidate_id'] for r in data['prediction_rows']],'Neural candidate identity')
        require(neural_score['planned_neural_arms']==60 and neural_score['completed_neural_arms']==completed,'Neural score coverage')
        gate=read(HERE/'chemeleon-finetune-trial/review-neural-01/actual-pre-score-gate.json')
        require(gate['status']=='PASS' and gate['gold_files_opened']==0,'Independent pre-score gate missing')
        require(gate['completion_sha256']==sha(run/'completion.json'),'Gate/completion binding')
        require(len(gate['arms'])+len(gate['failed_arms'])==60,'Gate denominator')
    require(sha(HERE/'licenses/CheMeleon-MIT.txt')==sha(HERE/'chemeleon-trial/author/LICENSE'),'Author MIT notice mismatch')
    require(sha(HERE/'licenses/MoleculeACE-LICENCE.txt')==read(HERE/'dataset-pins.json')['license_sha256'],'MoleculeACE notice mismatch')
    figure=HERE/'figures'
    if figure.exists():
        receipt=read(figure/'receipt.json')
        require(sha(figure/'input.json')==receipt['input_sha256'],'Figure input changed')
        for name,digest in receipt['outputs'].items():require(sha(figure/name)==digest,'Figure output changed')
        for source in read(figure/'input.json')['sources'].values():
            require(sha(HERE/source['path'])==source['sha256'],'Figure source binding changed')
    return {'status':'PASS','source_files':len(sources),'frozen_planned_tasks':30,'frozen_terminal_tasks':len(seal['tasks']),
            'fine_tune_planned_arms':60,'fine_tune_results_included':status['results_included'],
            'model_calls':0,'GPU_used':False,'network_calls':0}

if __name__=='__main__':print(json.dumps(verify(),indent=2))
