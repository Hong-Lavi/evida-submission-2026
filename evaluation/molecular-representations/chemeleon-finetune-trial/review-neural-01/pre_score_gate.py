"""Independent CPU gate; never opens test gold or invokes the frozen scorer.

All 60 terminal ledger entries must pass before individual receipts/predictions
are opened. Existing frozen sources are never edited. No model is instantiated.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import sys

TRIAL = Path(__file__).resolve().parent.parent
EXPECTED = '338a1e229ab3a848058eb694075159b8802ad3b873beb4949847a773932825ab'
TERMINAL = {'completed', 'failed', 'timed_out', 'failed_missing_predictions',
            'not_started_resource_busy', 'not_started_time_budget'}

def require(condition, message):
    if not condition: raise ValueError(message)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def load(path): return json.loads(Path(path).read_text())

def validate_terminal(protocol, completion):
    expected = [(t['task'], a) for t in protocol['tasks'] for a in protocol['arms']]
    require(len(expected) == 60 and len(set(expected)) == 60, 'Not the planned unique 60 arms')
    require(completion['status'] == 'prediction_generation_finished', 'Run not finished')
    require(completion['protocol_sha256'] == EXPECTED, 'Completion protocol mismatch')
    require(completion['retries'] == 0 and completion['official_test_labels_read'] is False,
            'Completion provenance mismatch')
    require([(r['task'], r['arm']) for r in completion['attempts']] == expected, 'Incomplete/changed ordered ledger')
    for r in completion['attempts']:
        require(r['status'] in TERMINAL, 'Unknown/nonterminal status')
        require(r['status'] != 'completed' or (r['returncode'] == 0 and bool(r['prediction_sha256'])),
                'Completed entry lacks successful return/hash')
        if r['status'].startswith('not_started_'):
            require(r['returncode'] is None and r['prediction_sha256'] is None, 'Skipped entry has output')
    return completion['attempts']

def validation_check(data, record):
    import numpy as np
    from scipy.stats import spearmanr
    train = np.asarray([r['p_activity'] for r in data['train']], dtype=float)
    y = np.asarray([r['p_activity'] for r in data['validation']], dtype=float)
    pred = np.asarray([r['prediction'] for r in record['validation_predictions']], dtype=float)
    require(len(train) > 0 and len(y) > 1 and len(y) == len(pred), 'Validation coverage')
    require(np.isfinite(train).all() and np.isfinite(y).all() and np.isfinite(pred).all(), 'Nonfinite validation data')
    mae = float(np.mean(np.abs(y - pred)))
    mean_mae = float(np.mean(np.abs(y - float(np.mean(train)))))
    rho = 0.0 if np.ptp(y) == 0 or np.ptp(pred) == 0 else round(float(spearmanr(y, pred).statistic), 3)
    require(abs(mae - record['validation_mae']) < 1e-12, 'Validation MAE mismatch')
    require(abs(mean_mae - record['mean_validation_mae']) < 1e-12, 'Training-mean validation baseline mismatch')
    require(rho == record['validation_spearman'], 'Validation Spearman mismatch')
    require(type(record['usable']) is bool and record['usable'] == (rho >= .3 and mae < mean_mae), 'Eligibility mismatch')
    return {'mae_recomputed': True, 'mean_baseline_recomputed': True,
            'spearman_independent_scipy': True, 'usable_recomputed': True}

def state_hash(state):
    h = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        h.update(name.encode()); h.update(str(tuple(tensor.shape)).encode())
        h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()

def run(result):
    require(sha(TRIAL/'protocol.json') == EXPECTED, 'Frozen protocol drift')
    require(load(TRIAL/'protocol-receipt.json')['sha256'] == EXPECTED, 'Protocol receipt drift')
    protocol = load(TRIAL/'protocol.json')
    completion_path = TRIAL/'run-01/completion.json'
    attempts = validate_terminal(protocol, load(completion_path))
    result['terminal_gate_passed_before_predictions'] = True
    result['completion_sha256'] = sha(completion_path)
    result['terminal_counts'] = dict(Counter(r['status'] for r in attempts))
    result['planned_rows_per_arm'] = sum(t['prediction_rows'] for t in protocol['tasks'])
    require(result['planned_rows_per_arm'] == 9802, 'Changed candidate denominator')
    for name, expected in protocol['source_pins'].items():
        require(sha(TRIAL/name) == expected, 'Frozen source drift: '+name)
    result['source_pins'] = protocol['source_pins']
    weight = TRIAL.parent/'chemeleon-trial/weights/chemeleon_mp.pt'
    require(sha(weight) == protocol['weights_sha256'], 'Author weights drift')
    # CPU deserialization of pinned weights only; never instantiate/train/predict a model.
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    import torch
    author = torch.load(weight, map_location='cpu', weights_only=True)
    author_encoder = state_hash(author['state_dict'])
    del author
    heads = {}; result['arms'] = []; result['failed_arms'] = []
    tasks = {t['task']:t for t in protocol['tasks']}
    data_cache = {}
    for name, task in tasks.items():
        p = TRIAL/'inputs'/f'{name}.json'
        require(sha(p) == task['input_sha256'], 'Input drift: '+name)
        data = load(p); data_cache[name] = data
        require(data['task'] == name and data['endpoint'] == task['endpoint'], 'Input task identity')
        groups = [[r['candidate_id'] for r in data[k]] for k in ('train','validation','prediction_rows')]
        for ids, count in zip(groups,[task['training_rows'],task['validation_rows'],task['prediction_rows']]):
            require(len(ids) == len(set(ids)) == count, 'Input ID/count mismatch')
        require(not(set(groups[0])&set(groups[1]) or set(groups[0])&set(groups[2]) or set(groups[1])&set(groups[2])), 'Overlapping input IDs')
        require(all(set(r) == {'candidate_id','smiles'} for r in data['prediction_rows']), 'Test feature payload contains extra data')
        ref = TRIAL.parent/'tanimoto-trial/run-01'/name/'predictions.json'
        require(sha(ref) == task['reference_predictions_sha256'], 'Baseline reference drift')
        reference = load(ref)
        require([r['candidate_id'] for r in reference['rows']] == groups[2], 'Reference candidate mismatch')
        require(all(math.isfinite(r[k]) for r in reference['rows'] for k in ('rf_prediction','gp_prediction')), 'Nonfinite reference')
        require(not reference['author_gp']['usable'] or reference['author_gp']['optimization']['converged'], 'GP usable without optimizer success')
    for entry in attempts:
        name, arm = entry['task'], entry['arm']; task = tasks[name]; data = data_cache[name]
        directory = TRIAL/'run-01'/name/arm
        receipt = directory.parent/(arm+'-receipt.json')
        require(load(receipt) == entry, 'Individual receipt differs: '+name+'/'+arm)
        p = directory/'predictions.json'
        require(p.exists() == bool(entry['prediction_sha256']), 'Prediction existence/hash disagreement')
        if p.exists(): require(sha(p) == entry['prediction_sha256'], 'Prediction hash drift')
        if entry['status'] != 'completed':
            result['failed_arms'].append({'task':name,'arm':arm,'status':entry['status'],
                                         'receipt_sha256':sha(receipt),'prediction_sha256':entry['prediction_sha256']})
            continue
        record = load(p); fit_path = directory/'fit.json'; fit = load(fit_path)
        require(record['status'] == 'completed' and record['task'] == name and record['arm'] == arm, 'Prediction identity/status')
        require(record['input_sha256'] == task['input_sha256'] and record['protocol_sha256'] == EXPECTED, 'Prediction source identity')
        require(record['official_test_labels_read'] is False, 'Worker reports gold access')
        for key, source in [('rows','prediction_rows'),('validation_predictions','validation')]:
            require([r['candidate_id'] for r in record[key]] == [r['candidate_id'] for r in data[source]], 'Prediction row identity/order')
            require(all(type(r['prediction']) in (int,float) and math.isfinite(r['prediction']) for r in record[key]), 'Nonfinite/non-numeric prediction')
        checks = validation_check(data, record)
        require(record['fit'] == fit, 'Embedded and standalone fit disagree')
        require(fit['pretrained'] == (arm == 'chemeleon_finetuned'), 'Wrong neural arm')
        require(fit['seed'] == protocol['seed'] and fit['batch_size'] == protocol['batch_size'] and fit['maximum_epochs'] == protocol['maximum_epochs'], 'Wrong training configuration')
        require(fit['GPU_used'] is True and fit['device'] == protocol['gpu_name'], 'Wrong recorded training device')
        require(all(fit['versions'][k] == protocol['environment'][k] for k in fit['versions']), 'Runtime version drift')
        require([fit[k] for k in ('training_rows','validation_rows','prediction_rows')] == [task[k] for k in ('training_rows','validation_rows','prediction_rows')], 'Fit row counts')
        require((fit['initial_encoder_sha256'] == author_encoder) == (arm == 'chemeleon_finetuned'), 'Initial encoder/weights identity')
        require(sha(directory/'checkpoint/best.ckpt') == fit['best_checkpoint_sha256'], 'Checkpoint hash drift')
        heads[name,arm] = fit['initial_head_sha256']
        result['arms'].append({'task':name,'arm':arm,'checks':checks,'prediction_sha256':sha(p),
                              'receipt_sha256':sha(receipt),'fit_sha256':sha(fit_path),
                              'checkpoint_sha256':fit['best_checkpoint_sha256']})
    paired = 0
    for name in tasks:
        if all((name,a) in heads for a in protocol['arms']):
            require(len({heads[name,a] for a in protocol['arms']}) == 1, 'Paired initial heads differ: '+name)
            paired += 1
    result['paired_identical_heads'] = paired
    # Recheck the entire sealed ledger and every observed file before reporting PASS.
    require(sha(completion_path) == result['completion_sha256'], 'Completion changed during review')
    for row in result['arms']+result['failed_arms']:
        d = TRIAL/'run-01'/row['task']/row['arm']
        require(sha(d.parent/(row['arm']+'-receipt.json')) == row['receipt_sha256'], 'Receipt changed during review')
        if row['prediction_sha256']: require(sha(d/'predictions.json') == row['prediction_sha256'], 'Prediction changed during review')
    for name, expected in protocol['source_pins'].items():
        require(sha(TRIAL/name) == expected, 'Source changed during review: '+name)
    for name, task in tasks.items():
        require(sha(TRIAL/'inputs'/f'{name}.json') == task['input_sha256'], 'Input changed during review')
        require(sha(TRIAL.parent/'tanimoto-trial/run-01'/name/'predictions.json') == task['reference_predictions_sha256'], 'Reference changed during review')
    result['status'] = 'PASS'

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True); args=parser.parse_args()
    require(not args.out.exists(), 'Refusing to overwrite a prior review')
    result={'status':'FAIL','protocol_sha256':EXPECTED,'gate_source_sha256':sha(__file__),
            'terminal_gate_passed_before_predictions':False,'gold_open_attempts':0,
            'gold_files_opened':0,'model_instantiations':0,'training_calls':0,'GPU_used_by_review':False}
    def guard(event, values):
        if event=='open' and isinstance(values[0],str) and ('evaluation-only' in values[0] or 'test-gold' in values[0]):
            result['gold_open_attempts']+=1
            raise PermissionError('Independent pre-score review forbids gold access')
    sys.addaudithook(guard)
    try: run(result)
    except Exception as exc: result['error']={'type':type(exc).__name__,'message':str(exc)}
    with args.out.open('x') as f: json.dump(result,f,indent=2,allow_nan=False); f.write('\n')
    print(json.dumps({'status':result['status'],'terminal_counts':result.get('terminal_counts'),
                      'completed_verified':len(result.get('arms',[])),'error':result.get('error'),'gold_files_opened':0}))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__': sys.exit(main())
