"""Seal every planned arm and verify all predictions before opening test labels."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from metrics_common import metrics, cluster_interval, spearman
from run_comparison import verify

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def create(path, value):
    with Path(path).open('x') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')


def main():
    protocol = json.loads((HERE / 'protocol.json').read_text())
    assert sha(HERE / 'protocol.json') == json.loads((HERE / 'protocol-receipt.json').read_text())['sha256']
    verify(protocol)
    run = HERE / 'run-01'
    completion = json.loads((run / 'completion.json').read_text())
    assert completion['protocol_sha256'] == sha(HERE / 'protocol.json')
    expected = [(task['task'], arm) for task in protocol['tasks'] for arm in protocol['arms']]
    assert [(entry['task'], entry['arm']) for entry in completion['attempts']] == expected
    records = {(entry['task'], entry['arm']): entry for entry in completion['attempts']}
    predictions, inputs, references = {}, {}, {}
    failures, sealed = [], []
    for task in protocol['tasks']:
        name = task['task']
        inputs[name] = json.loads((HERE / 'inputs' / (name + '.json')).read_text())
        ids = [row['candidate_id'] for row in inputs[name]['prediction_rows']]
        assert len(set(ids)) == len(ids) == task['prediction_rows']
        references[name] = json.loads((BASE / 'tanimoto-trial/run-01' / name / 'predictions.json').read_text())
        assert [row['candidate_id'] for row in references[name]['rows']] == ids
        assert np.isfinite([[row['rf_prediction'], row['gp_prediction']]
                            for row in references[name]['rows']]).all()
        for arm in protocol['arms']:
            entry = records[name, arm]
            if entry['status'] != 'completed':
                failures.append(entry)
                sealed.append(entry)
                continue
            path = run / name / arm / 'predictions.json'
            assert sha(path) == entry['prediction_sha256']
            record = json.loads(path.read_text())
            assert record['input_sha256'] == task['input_sha256']
            assert record['protocol_sha256'] == sha(HERE / 'protocol.json')
            assert record['task'] == name and record['arm'] == arm
            assert [row['candidate_id'] for row in record['rows']] == ids
            assert [row['candidate_id'] for row in record['validation_predictions']] == [
                row['candidate_id'] for row in inputs[name]['validation']]
            assert np.isfinite([row['prediction'] for row in record['rows']]).all()
            y_val = np.asarray([row['p_activity'] for row in inputs[name]['validation']])
            p_val = np.asarray([row['prediction'] for row in record['validation_predictions']])
            assert np.isfinite(p_val).all()
            assert abs(float(np.mean(np.abs(y_val - p_val))) - record['validation_mae']) < 1e-12
            assert round(spearman(y_val.tolist(), p_val.tolist()), 3) == record['validation_spearman']
            assert record['usable'] == (record['validation_spearman'] >= .3 and
                                        record['validation_mae'] < record['mean_validation_mae'])
            predictions[name, arm] = record
            sealed.append(entry)
        left, right = [predictions.get((name, arm)) for arm in protocol['arms']]
        if left and right:
            assert left['fit']['initial_head_sha256'] == right['fit']['initial_head_sha256']
    create(run / 'sealed-predictions.json', {'sealed_at_utc': datetime.now(timezone.utc).isoformat(),
        'protocol_sha256': sha(HERE / 'protocol.json'), 'all_expected_attempts': sealed,
        'source_prediction_and_identity_gate': 'PASS', 'official_gold_opened_in_this_evaluation': False})
    # Recheck all files after the seal. No labels are read until this global gate completes.
    for entry in sealed:
        if entry['prediction_sha256']:
            assert sha(run / entry['task'] / entry['arm'] / 'predictions.json') == entry['prediction_sha256']
    rows = []
    for task in protocol['tasks']:
        name = task['task']
        ids = [row['candidate_id'] for row in inputs[name]['prediction_rows']]
        path = Path(protocol['official_data']) / name / 'evaluation-only/test-gold.json'
        assert sha(path) == task['official_gold_sha256']
        raw = json.loads(path.read_text())
        gold = {row['candidate_id']: row['p_activity'] for row in raw}
        assert len(raw) == len(gold) == len(ids) and set(ids) == set(gold)
        y = np.asarray([gold[cid] for cid in ids])
        ref = references[name]
        values = {arm: np.asarray([row[arm + '_prediction'] for row in ref['rows']]) for arm in ('rf', 'gp')}
        candidates = []
        if ref['native_rf']['usable']:
            candidates.append((ref['native_rf']['inner_mae'], 0, 'rf'))
        if ref['author_gp']['usable']:
            candidates.append((ref['author_gp']['inner_mae'], 1, 'gp'))
        for index, arm in enumerate(protocol['arms'], 2):
            record = predictions.get((name, arm))
            if record:
                values[arm] = np.asarray([row['prediction'] for row in record['rows']])
                if record['usable']:
                    candidates.append((record['validation_mae'], index, arm))
        chosen = min(candidates)[2] if candidates else None
        if chosen:
            values['validation_policy'] = values[chosen]
        row = {'task': name, 'n': len(ids), 'selected_policy_arm': chosen}
        row.update({arm: metrics(y, value, ids, spearman) for arm, value in values.items()})
        rows.append(row)
    names = ('mae', 'rmse', 'spearman', 'top10_recall', 'best_true_activity_in_selected10')
    all_arms = ['rf', 'gp', *protocol['arms'], 'validation_policy']
    macro = {arm: {metric: float(np.mean([row[arm][metric] for row in rows if arm in row]))
                   for metric in names} for arm in all_arms if any(arm in row for row in rows)}
    comparisons = {}
    for left, right in [('chemeleon_finetuned', 'rf'), ('chemeleon_finetuned', 'gp'),
                        ('chemeleon_finetuned', 'matched_random'), ('validation_policy', 'rf')]:
        complete = [row for row in rows if left in row and right in row]
        comparisons[left + '_minus_' + right] = {metric: cluster_interval(complete, left, right, metric, protocol)
                                                for metric in names}
    summary = {'planned_tasks': len(protocol['tasks']), 'planned_neural_arms': len(expected),
               'completed_neural_arms': len(predictions), 'failures': failures,
               'completed_test_rows_by_arm': {arm: sum(row['n'] for row in rows if arm in row) for arm in all_arms},
               'task_coverage': {arm: sum(arm in row for row in rows) for arm in all_arms},
               'task_macro': macro, 'paired_comparisons': comparisons,
               'policy_selection': dict(Counter(row['selected_policy_arm'] for row in rows)),
               'tasks': rows, 'protocol_sha256': sha(HERE / 'protocol.json'),
               'prediction_seal_sha256': sha(run / 'sealed-predictions.json'),
               'GPU_used': True if any(record['fit']['GPU_used'] for record in predictions.values())
                           else (None if any(not entry['status'].startswith('not_started_')
                                             for entry in completion['attempts']) else False),
               'model_calls': 0, 'scope': protocol['scope']}
    create(run / 'scored-results.json', summary)
    print(json.dumps({key: summary[key] for key in ('planned_tasks', 'completed_neural_arms', 'task_coverage',
                                                  'task_macro', 'policy_selection')}))


if __name__ == '__main__':
    main()
