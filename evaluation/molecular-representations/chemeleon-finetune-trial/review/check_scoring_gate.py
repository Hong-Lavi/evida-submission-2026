"""Run the frozen scorer on synthetic files only; never fit or open real test gold.

The scorer and its verify function remain unmodified. Only their HERE/BASE roots
are pointed at each synthetic fixture. File hashes, the complete ordered ledger,
prediction identity checks and sealing are exercised by the actual functions.
"""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
TRIAL = HERE.parent
OUT = HERE / 'scoring-gate-fixtures'
EXPECTED_PROTOCOL = '338a1e229ab3a848058eb694075159b8802ad3b873beb4949847a773932825ab'
sys.path.insert(0, str(TRIAL))
import score_comparison as scorer
import run_comparison as runner


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


assert sha(TRIAL / 'protocol.json') == EXPECTED_PROTOCOL
actual_protocol = json.loads((TRIAL / 'protocol.json').read_text())
runner.verify(actual_protocol)
OUT.mkdir(exist_ok=False)

ARMS = ['chemeleon_finetuned', 'matched_random']
TASKS = [f'SYNTH{i:03d}_Ki' for i in range(29)] + ['SYNTH000_EC50']


def fixture(name, mode):
    base = OUT / name
    trial = base / 'trial'
    run = trial / 'run-01'
    weight = base / 'chemeleon-trial/weights/chemeleon_mp.pt'
    weight.parent.mkdir(parents=True)
    weight.write_bytes(b'SYNTHETIC HASH FIXTURE - NOT MODEL WEIGHTS\n')
    source = trial / 'frozen-placeholder.txt'
    source.parent.mkdir()
    source.write_text('SYNTHETIC SOURCE PIN\n')
    protocol = {'arms': ARMS, 'tasks': [], 'official_data': str(base / 'synthetic-gold'),
                'source_pins': {str(TRIAL / f): sha(TRIAL / f) for f in
                                ('score_comparison.py', 'run_comparison.py', 'metrics_common.py')},
                'weights_sha256': sha(weight), 'bootstrap_seed': 20261011,
                'bootstrap_repetitions': 20, 'scope': 'synthetic CPU scorer-gate fixture only'}
    protocol['source_pins']['frozen-placeholder.txt'] = sha(source)
    inputs, references = {}, {}
    for task in TASKS:
        data = {'train': [{'candidate_id': f'{task}-tr{i}', 'smiles': 'C', 'p_activity': float(i)} for i in range(3)],
                'validation': [{'candidate_id': f'{task}-val{i}', 'smiles': 'CC', 'p_activity': float(i)} for i in range(3)],
                'prediction_rows': [{'candidate_id': f'{task}-out{i:02d}', 'smiles': 'CCC'} for i in range(12)]}
        inputs[task] = data
        p_input = trial / 'inputs' / (task + '.json')
        save(p_input, data)
        tied = mode == 'tie'
        ref = {'rows': [{'candidate_id': row['candidate_id'], 'rf_prediction': float(i) + .5,
                         'gp_prediction': float(i) + .25} for i, row in enumerate(data['prediction_rows'])],
               'native_rf': {'usable': True, 'inner_mae': .125 if tied else .375},
               'author_gp': {'usable': True, 'inner_mae': .125 if tied else .25}}
        references[task] = ref
        p_ref = base / 'tanimoto-trial/run-01' / task / 'predictions.json'
        save(p_ref, ref)
        gold = [{'candidate_id': row['candidate_id'], 'p_activity': float(11 - i if mode == 'gold_reversed' else i)}
                for i, row in enumerate(data['prediction_rows'])]
        p_gold = base / 'synthetic-gold' / task / 'evaluation-only/test-gold.json'
        save(p_gold, gold)
        protocol['tasks'].append({'task': task, 'prediction_rows': 12,
                                  'input_sha256': sha(p_input), 'reference_predictions_sha256': sha(p_ref),
                                  'official_gold_sha256': sha(p_gold)})
    save(trial / 'protocol.json', protocol)
    psha = sha(trial / 'protocol.json')
    save(trial / 'protocol-receipt.json', {'sha256': psha})
    attempts = []
    for index, task in enumerate(TASKS):
        for arm in ARMS:
            skipped = mode in ('all_skipped', 'all_failed')
            if skipped:
                attempts.append({'task': task, 'arm': arm,
                    'status': 'failed' if mode == 'all_failed' else 'not_started_resource_busy',
                    'prediction_sha256': None, 'returncode': 1 if mode == 'all_failed' else None})
                continue
            offset = .125 if arm == ARMS[0] else .25
            data = inputs[task]
            record = {'task': task, 'arm': arm, 'status': 'completed',
                'input_sha256': protocol['tasks'][index]['input_sha256'], 'protocol_sha256': psha,
                'usable': True, 'validation_mae': offset, 'validation_spearman': 1.0,
                'mean_validation_mae': 2 / 3,
                'validation_predictions': [{'candidate_id': row['candidate_id'], 'prediction': row['p_activity'] + offset}
                                            for row in data['validation']],
                'rows': [{'candidate_id': row['candidate_id'], 'prediction': float(i) + offset}
                         for i, row in enumerate(data['prediction_rows'])],
                'fit': {'initial_head_sha256': 'SYNTHETIC_IDENTICAL_HEAD', 'GPU_used': True}}
            if index == 0 and arm == ARMS[0]:
                if mode == 'duplicate_id':
                    record['rows'][1]['candidate_id'] = record['rows'][0]['candidate_id']
                elif mode == 'nonfinite':
                    record['rows'][0]['prediction'] = None
                elif mode == 'wrong_protocol':
                    record['protocol_sha256'] = 'wrong'
                elif mode == 'false_validation_mae':
                    record['validation_mae'] = .1
                elif mode == 'wrong_head':
                    record['fit']['initial_head_sha256'] = 'SYNTHETIC_DIFFERENT_HEAD'
                elif mode == 'missing_prediction_row':
                    record['rows'].pop()
            p_record = run / task / arm / 'predictions.json'
            save(p_record, record)
            if index == 0 and arm == ARMS[0] and mode == 'nonfinite':
                p_record.write_text(p_record.read_text().replace('"prediction": null', '"prediction": NaN', 1))
            attempts.append({'task': task, 'arm': arm, 'status': 'completed', 'prediction_sha256': sha(p_record), 'returncode': 0})
    if mode == 'missing_attempt':
        attempts.pop()
    if mode == 'wrong_prediction_hash':
        attempts[0]['prediction_sha256'] = 'wrong'
    completion = {'protocol_sha256': 'wrong' if mode == 'wrong_completion_protocol' else psha, 'attempts': attempts}
    save(run / 'completion.json', completion)
    if mode == 'source_drift':
        source.write_text('MUTATED SYNTHETIC SOURCE PIN\n')
    if mode == 'input_drift':
        p = trial / 'inputs' / (TASKS[0] + '.json')
        p.write_text(p.read_text() + '\n')
    return base, trial, run


results = []
modes = ['valid', 'gold_reversed', 'tie', 'all_skipped', 'all_failed',
         'missing_attempt', 'duplicate_id', 'nonfinite', 'wrong_protocol',
         'false_validation_mae', 'wrong_head', 'missing_prediction_row',
         'wrong_prediction_hash', 'wrong_completion_protocol', 'source_drift', 'input_drift']
valid_modes = set(modes[:5])
original_open = Path.open
for mode in modes:
    base, trial, run = fixture(mode, mode)
    scorer.HERE, scorer.BASE, runner.HERE, runner.BASE = trial, base, trial, base
    gold_events, error = [], None
    def tracked_open(path, *args, **kwargs):
        resolved = path.resolve()
        if 'evaluation-only' in str(resolved) or 'test-gold' in str(resolved):
            if not resolved.is_relative_to(base / 'synthetic-gold'):
                raise PermissionError('Independent review cannot open official test labels')
            gold_events.append({'path': str(resolved.relative_to(base)),
                                'prediction_seal_exists': (run / 'sealed-predictions.json').is_file()})
        return original_open(path, *args, **kwargs)
    output = io.StringIO()
    with patch.object(Path, 'open', tracked_open), redirect_stdout(output):
        try:
            scorer.main()
        except Exception as exc:
            error = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    observed = {'case': mode, 'error': error, 'synthetic_gold_open_events': gold_events,
                'seal_exists': (run / 'sealed-predictions.json').exists(),
                'scored_results_exists': (run / 'scored-results.json').exists()}
    if mode in valid_modes:
        summary = json.loads((run / 'scored-results.json').read_text())
        expected_arm = 'rf' if mode == 'tie' else ('gp' if mode in ('all_skipped', 'all_failed') else ARMS[0])
        expected_gpu = False if mode == 'all_skipped' else (None if mode == 'all_failed' else True)
        observed['checks'] = {
            'completed_without_error': error is None,
            'global_seal_precedes_every_synthetic_gold_open': bool(gold_events) and all(e['prediction_seal_exists'] for e in gold_events),
            'fixed_denominator_60': summary['planned_neural_arms'] == 60,
            'expected_policy_only_validation': summary['policy_selection'] == {expected_arm: 30},
            'expected_completed_coverage': summary['completed_neural_arms'] == (0 if mode in ('all_skipped', 'all_failed') else 60),
            'failures_preserved': len(summary['failures']) == (60 if mode in ('all_skipped', 'all_failed') else 0),
            'GPU_provenance_from_synthetic_receipts': summary['GPU_used'] is expected_gpu}
        if mode not in ('all_skipped', 'all_failed'):
            observed['checks']['paired_endpoint_cluster_count_29'] = summary['paired_comparisons']['chemeleon_finetuned_minus_rf']['mae']['target_clusters'] == 29
    else:
        observed['checks'] = {'rejected': error is not None, 'no_gold_open': not gold_events,
                              'no_scored_results': not observed['scored_results_exists']}
    observed['status'] = 'PASS' if all(observed['checks'].values()) else 'FAIL'
    save(base / 'observed.json', observed)
    (base / 'scorer-stdout.txt').write_text(output.getvalue())
    results.append(observed)
scorer.HERE, scorer.BASE, runner.HERE, runner.BASE = TRIAL, TRIAL.parent, TRIAL, TRIAL.parent
receipt = {'status': 'PASS' if all(r['status'] == 'PASS' for r in results) else 'FAIL',
           'reviewed_protocol_sha256': EXPECTED_PROTOCOL, 'cases': results,
           'actual_scorer_sources': {f: sha(TRIAL / f) for f in ('score_comparison.py', 'run_comparison.py', 'metrics_common.py')},
           'fixture_information': 'All molecular rows, labels, predictions, model receipts and checkpoint bytes are synthetic. No model is instantiated.',
           'official_test_labels_read': False, 'model_fits': 0, 'GPU_used': False, 'network_calls': 0}
save(HERE / 'scoring-gate-review.json', receipt)
print(json.dumps({'status': receipt['status'], 'cases': len(results), 'official_test_labels_read': False}))
assert receipt['status'] == 'PASS'
