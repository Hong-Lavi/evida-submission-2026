"""Supplement v1 with all-planned RF availability, sealed before opening gold.

Do not execute until every original task has a terminal sealed receipt. The
original scorer computes the primary comparison unchanged. No fallback policy
is manufactured for an interrupted GP task. This file never fits a model.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_protocol(here=HERE):
    """No feature, prediction, or gold values are read here."""
    path = here / 'protocol.json'
    protocol = json.loads(path.read_text())
    require(sha(path) == json.loads((here / 'protocol-receipt.json').read_text())['sha256'],
            'Original frozen protocol receipt mismatch')
    for name, expected in protocol['source_pins'].items():
        require(sha(here / name) == expected, 'Original frozen source pin mismatch: ' + name)
    names = [t['task'] for t in protocol['tasks']]
    require(len(names) == len(set(names)) == 30 and names == protocol['order'], 'Expected the original 30 ordered tasks')
    return protocol


def verify_prediction_seal(protocol, run):
    """Validate all terminal receipts before any label access or RF supplement."""
    seal = json.loads((run / 'sealed-predictions.json').read_text())
    require(seal['protocol_sha256'] == sha(HERE / 'protocol.json'), 'Prediction seal protocol mismatch')
    require([r['task'] for r in seal['tasks']] == protocol['order'], 'Prediction seal does not contain all planned tasks in order')
    require(seal.get('test_gold_read') is False, 'Original seal must precede gold access')
    for receipt in seal['tasks']:
        require(receipt['status'] in ('completed', 'failed', 'timeout'), 'A task is not terminal')
        on_disk = json.loads((run / receipt['task'] / 'receipt.json').read_text())
        require(on_disk == receipt, 'Terminal task receipt differs from original seal')
        prediction_path = run / receipt['task'] / 'predictions.json'
        expected = receipt.get('prediction_sha256')
        if receipt['status'] == 'completed':
            require(receipt['returncode'] == 0 and bool(expected), 'Completed task lacks a successful hashed prediction')
        if expected:
            require(prediction_path.is_file() and sha(prediction_path) == expected, 'Prediction hash mismatch')
        else:
            require(not prediction_path.exists(), 'An unsealed prediction file appeared after the original terminal receipt')
    return seal


def supplemental_rf_seal(protocol, original_seal, run, amendment_sha256):
    """Hash even RF files from GP failures; no gold or prediction values read."""
    entries = []
    for receipt in original_seal['tasks']:
        directory = run / receipt['task']
        files = {}
        for name in ('rf-predictions.json', 'native-fit.json', 'started.json', 'receipt.json'):
            path = directory / name
            files[name] = {'sha256': sha(path), 'bytes': path.stat().st_size} if path.is_file() else None
        entries.append({'task': receipt['task'], 'original_task_status': receipt['status'], 'files': files})
    value = {'status': 'SEALED_BEFORE_V1_OR_V2_GOLD_ACCESS',
             'at_utc': datetime.now(timezone.utc).isoformat(), 'test_gold_read': False,
             'protocol_sha256': sha(HERE / 'protocol.json'),
             'scoring_amendment_sha256': amendment_sha256,
             'original_prediction_seal_sha256': sha(run / 'sealed-predictions.json'),
             'planned_tasks': len(protocol['tasks']), 'tasks': entries}
    save(run / 'supplemental-sealed-rf-v2.json', value)
    return value


def read_sealed_rf(run, item, task):
    stamp = item['files']['rf-predictions.json']
    if stamp is None:
        return None, 'not_produced'
    path = run / task['task'] / 'rf-predictions.json'
    require(sha(path) == stamp['sha256'], 'RF bytes changed after supplemental seal')
    try:
        data = json.loads(path.read_text())
        rows = data['rows']
        ids = [r['candidate_id'] for r in rows]
        predictions = np.asarray([r['prediction'] for r in rows], dtype=float)
        require(len(ids) == len(set(ids)) == task['official_test'], 'RF candidate count/uniqueness mismatch')
        require(all(isinstance(i, str) for i in ids), 'RF candidate IDs must be strings')
        require(np.isfinite(predictions).all() and np.isfinite(float(data['training_mean'])), 'Nonfinite RF prediction')
        require(type(data['usable']) is bool, 'RF usability flag missing or invalid')
        return data, 'available'
    except (ValueError, TypeError, KeyError) as error:
        return None, 'invalid_retained_file: ' + str(error)


def main():
    protocol = verify_protocol()
    amendment_path = HERE / 'scoring-amendment-v2.json'
    amendment = json.loads(amendment_path.read_text())
    require(amendment['status'] == 'FROZEN_BEFORE_EXTERNAL_GOLD_ACCESS', 'Scoring amendment was not frozen')
    require(amendment['protocol_sha256'] == sha(HERE / 'protocol.json'), 'Scoring amendment protocol mismatch')
    for name, expected in amendment['new_source_pins'].items():
        require(sha(HERE / name) == expected, 'Supplemental scorer source pin mismatch: ' + name)
    run = HERE / 'run-01'
    require(not (run / 'scored-results.json').exists(), 'v1 already scored; cannot retrospectively seal RF files before gold access')
    require(not (run / 'scored-results-v2.json').exists(), 'v2 is immutable; no automatic rescore')
    original_seal = verify_prediction_seal(protocol, run)
    extra_seal = supplemental_rf_seal(protocol, original_seal, run, sha(amendment_path))
    # Validate/classify every retained RF file while gold is still unopened.
    rf_files = [read_sealed_rf(run, item, task)
                for item, task in zip(extra_seal['tasks'], protocol['tasks'])]
    for receipt, (rf_data, _) in zip(original_seal['tasks'], rf_files):
        if receipt['status'] != 'completed':
            continue
        require(rf_data is not None, 'Completed paired task lacks a valid independently sealed RF file')
        combined = json.loads((run / receipt['task'] / 'predictions.json').read_text())
        left = {r['candidate_id']: r['prediction'] for r in rf_data['rows']}
        right = {r['candidate_id']: r['rf_prediction'] for r in combined['rows']}
        require(left == right and rf_data['usable'] == combined['native_rf']['usable'],
                'Paired RF and separately sealed RF disagree before gold access')
    # Original v1 code, protocol and pair/metric definitions stay unchanged.
    spec = importlib.util.spec_from_file_location('frozen_tanimoto_scorer_v1', HERE / 'score_comparison.py')
    v1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v1)
    v1.main()
    original_results_path = run / 'scored-results.json'
    original_results = json.loads(original_results_path.read_text())
    paired = {r['task']: r for r in original_results['tasks']}
    sys.path.insert(0, protocol['frozen_product'])
    from evida.activity_model import _spearman
    rows = []
    for task, receipt, item, (rf_data, rf_status) in zip(protocol['tasks'], original_seal['tasks'], extra_seal['tasks'], rf_files):
        name = task['task']
        row = {'task': name, 'original_task_status': receipt['status'], 'rf_prediction_status': rf_status,
               'rf_usable': rf_data['usable'] if rf_data is not None else None,
               'in_v1_successful_pairs': name in paired, 'rf_metrics': None,
               'selected_policy_arm': paired[name]['selected_policy_arm'] if name in paired else None,
               'policy_status': ('abstained' if paired[name]['selected_policy_arm'] == 'abstain' else 'selected')
                   if name in paired else 'not_produced_due_to_task_failure',
               'rf_prediction_sha256': (item['files']['rf-predictions.json'] or {}).get('sha256')}
        if rf_data is not None:
            # Verify again immediately before consuming the sealed prediction.
            require(sha(run / name / 'rf-predictions.json') == row['rf_prediction_sha256'], 'RF prediction changed during scoring')
            if name in paired:
                # Ensure the independent RF receipt agrees with the original
                # combined paired prediction before reusing its v1 metrics.
                combined = json.loads((run / name / 'predictions.json').read_text())
                left = {r['candidate_id']: r['prediction'] for r in rf_data['rows']}
                right = {r['candidate_id']: r['rf_prediction'] for r in combined['rows']}
                require(left == right and rf_data['usable'] == paired[name]['rf_usable'], 'Paired RF and separately sealed RF disagree')
                row['rf_metrics'] = paired[name]['rf']
            else:
                gold_path = Path(protocol['data']) / name / 'evaluation-only/test-gold.json'
                require(sha(gold_path) == task['gold_sha256'], 'Official gold hash mismatch')
                raw_gold = json.loads(gold_path.read_text())
                gold = {r['candidate_id']: r for r in raw_gold}
                ids = [r['candidate_id'] for r in rf_data['rows']]
                require(len(raw_gold) == len(gold) == len(ids) and set(ids) == set(gold), 'RF/gold IDs differ or gold has duplicates')
                y = np.asarray([gold[i]['p_activity'] for i in ids], dtype=float)
                p = np.asarray([r['prediction'] for r in rf_data['rows']], dtype=float)
                require(np.isfinite(y).all(), 'Nonfinite official labels')
                row['rf_metrics'] = v1.metrics(y, p, ids, _spearman)
        rows.append(row)
    observed_rf = [r for r in rows if r['rf_metrics'] is not None]
    metric_names = ['mae', 'rmse', 'spearman', 'top10_recall', 'best_true_activity_in_selected10']
    result = {
        'status': 'SCORED_WITH_PREDECLARED_COVERAGE_SUPPLEMENT', 'at_utc': datetime.now(timezone.utc).isoformat(),
        'protocol_sha256': sha(HERE / 'protocol.json'), 'scoring_amendment_sha256': sha(amendment_path),
        'supplemental_rf_seal_sha256': sha(run / 'supplemental-sealed-rf-v2.json'),
        'original_results': {'path': str(original_results_path), 'sha256': sha(original_results_path)},
        'primary_v1_unchanged': original_results['paired_gp_minus_rf'],
        'denominators': {'planned_tasks': len(rows), 'v1_successful_pairs': len(paired),
                         'v1_excluded_task_ids': [r['task'] for r in rows if not r['in_v1_successful_pairs']],
                         'rf_prediction_available': len(observed_rf)},
        'rf_all_planned': {'denominator': len(rows), 'predictions_available': len(observed_rf),
                          'operationally_usable': sum(r['rf_usable'] is True for r in rows),
                          'fitted_but_gate_abstained': sum(r['rf_usable'] is False for r in rows),
                          'unavailable_or_invalid': [r['task'] for r in rows if r['rf_metrics'] is None],
                          'task_macro_metrics_on_available': {metric: float(np.mean([r['rf_metrics'][metric] for r in observed_rf]))
                                                              for metric in metric_names} if observed_rf else {}},
        'policy_all_planned': {'denominator': len(rows), 'status_counts': dict(Counter(r['policy_status'] for r in rows)),
                              'selected_arm_counts': dict(Counter(r['selected_policy_arm'] for r in rows if r['selected_policy_arm'] is not None)),
                              'not_produced_task_ids': [r['task'] for r in rows if not r['in_v1_successful_pairs']],
                              'unexecuted_rf_fallback': [r['task'] for r in rows if not r['in_v1_successful_pairs'] and r['rf_usable'] is True]},
        'tasks': rows, 'gpu_used': False, 'provider_calls': 0,
        'meaning': 'The v1 paired metric and method selection are unchanged. RF-only rows expose availability outside successful GP/RF pairs; '
                   'their unpaired macro is not a GP effect estimate. A failed joint task has no selected policy; no retrospective RF fallback is scored.'}
    save(run / 'scored-results-v2.json', result)
    print(json.dumps({'status': result['status'], 'denominators': result['denominators'],
                      'rf_all_planned': result['rf_all_planned'], 'policy_all_planned': result['policy_all_planned']}))


if __name__ == '__main__':
    main()
