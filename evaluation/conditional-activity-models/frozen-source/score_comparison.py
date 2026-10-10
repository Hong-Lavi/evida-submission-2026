"""Open official labels only after the complete prediction ledger is sealed."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def metrics(y, predictions, ids, spearman):
    top_true = sorted(range(len(y)), key=lambda i: (-y[i], ids[i]))[:10]
    top_predicted = sorted(range(len(y)), key=lambda i: (-predictions[i], ids[i]))[:10]
    return {'n': len(y), 'mae': float(np.mean(np.abs(y - predictions))),
            'rmse': float(np.sqrt(np.mean((y - predictions) ** 2))),
            'spearman': spearman(y.tolist(), predictions.tolist()),
            'top10_recall': len(set(top_true) & set(top_predicted)) / len(top_true),
            'best_true_activity_in_selected10': float(max(y[i] for i in top_predicted))}


def cluster_interval(rows, left, right, metric, protocol):
    groups = defaultdict(list)
    for row in rows:
        groups[row['task'].split('_')[0]].append(row[left][metric] - row[right][metric])
    names = sorted(groups)
    if not names:
        return None
    rng = np.random.default_rng(protocol['bootstrap_seed'])
    boot = [np.mean([v for name in rng.choice(names, len(names), replace=True) for v in groups[name]])
            for _ in range(protocol['bootstrap_repetitions'])]
    differences = np.asarray([r[left][metric] - r[right][metric] for r in rows])
    return {'mean_difference': float(np.mean(differences)), 'ci95': np.quantile(boot, [0.025, 0.975]).tolist(),
            'tasks': len(rows), 'target_clusters': len(names),
            'negative': int(np.sum(differences < 0)), 'positive': int(np.sum(differences > 0)),
            'ties': int(np.sum(differences == 0)), 'difference_order': left + ' minus ' + right}


def main():
    protocol_path = HERE / 'protocol.json'
    protocol = json.loads(protocol_path.read_text())
    assert sha(protocol_path) == json.loads((HERE / 'protocol-receipt.json').read_text())['sha256']
    assert sha(Path(__file__)) == protocol['source_pins']['score_comparison.py']
    sys.path.insert(0, protocol['frozen_product'])
    from evida.activity_model import _spearman
    run = HERE / 'run-01'
    seal = json.loads((run / 'sealed-predictions.json').read_text())
    assert seal['protocol_sha256'] == sha(protocol_path)
    assert [t['task'] for t in seal['tasks']] == protocol['order']
    for receipt in seal['tasks']:
        if receipt['prediction_sha256']:
            assert sha(run / receipt['task'] / 'predictions.json') == receipt['prediction_sha256']
    label_opened_at = datetime.now(timezone.utc).isoformat()
    measured, failures = [], []
    for receipt, task in zip(seal['tasks'], protocol['tasks']):
        if receipt['status'] != 'completed':
            failures.append(receipt)
            continue
        pred = json.loads((run / task['task'] / 'predictions.json').read_text())
        gold_path = Path(protocol['data']) / task['task'] / 'evaluation-only/test-gold.json'
        assert sha(gold_path) == task['gold_sha256']
        raw_gold = json.loads(gold_path.read_text())
        gold = {r['candidate_id']: r for r in raw_gold}
        ids = [r['candidate_id'] for r in pred['rows']]
        assert len(ids) == len(set(ids)) == len(gold) == task['official_test']
        assert set(ids) == set(gold)
        y = np.asarray([gold[i]['p_activity'] for i in ids])
        rf = np.asarray([r['rf_prediction'] for r in pred['rows']])
        gp = np.asarray([r['gp_prediction'] for r in pred['rows']])
        std = np.asarray([r['gp_observation_std'] for r in pred['rows']])
        policy = pred['selected_policy_arm']
        m = {'task': task['task'], 'n': len(y),
             'rf': metrics(y, rf, ids, _spearman), 'gp': metrics(y, gp, ids, _spearman),
             'training_mean': metrics(y, np.full_like(y, pred['training_mean']), ids, _spearman),
             'rf_usable': pred['native_rf']['usable'], 'gp_usable': pred['author_gp']['usable'],
             'selected_policy_arm': policy,
             'policy': metrics(y, rf if policy == 'rf' else gp, ids, _spearman) if policy != 'abstain' else None,
             'gp_90pct_predictive_coverage': float(np.mean(np.abs(y - gp) <= 1.6448536269514722 * std)),
             'gp_90pct_predictive_mean_width': float(np.mean(2 * 1.6448536269514722 * std)),
             'gp_optimizer': pred['author_gp']['optimization'], 'seconds': receipt['seconds']}
        measured.append(m)
    metric_names = ['mae', 'rmse', 'spearman', 'top10_recall', 'best_true_activity_in_selected10']
    summary = {
        'at': label_opened_at, 'protocol_sha256': sha(protocol_path),
        'sealed_predictions_sha256': sha(run / 'sealed-predictions.json'),
        'planned_tasks': 30, 'completed_pairs': len(measured), 'failures': failures,
        'completed_test_rows': sum(r['n'] for r in measured),
        'raw_backbone_task_macro': {arm: {m: float(np.mean([r[arm][m] for r in measured])) for m in metric_names}
                                    for arm in ('rf', 'gp', 'training_mean')} if measured else {},
        'paired_gp_minus_rf': {m: cluster_interval(measured, 'gp', 'rf', m, protocol) for m in metric_names},
        'operational_coverage': {'rf_usable': sum(r['rf_usable'] for r in measured),
                                 'gp_usable': sum(r['gp_usable'] for r in measured),
                                 'inner_policy': dict(Counter(r['selected_policy_arm'] for r in measured))},
        'policy_comparison_on_rf_usable_tasks': {m: cluster_interval([r for r in measured if r['rf_usable']], 'policy', 'rf', m, protocol) for m in metric_names},
        'uncertainty_diagnostic': {'task_macro_90pct_coverage': float(np.mean([r['gp_90pct_predictive_coverage'] for r in measured])) if measured else None,
                                  'task_macro_interval_width': float(np.mean([r['gp_90pct_predictive_mean_width'] for r in measured])) if measured else None},
        'tasks': measured,
        'scope': protocol['scope'], 'next_decision': protocol['next_decision'],
        'gpu_used': False, 'provider_calls': 0,
    }
    save(run / 'scored-results.json', summary)
    print(json.dumps({k: summary[k] for k in ('planned_tasks', 'completed_pairs', 'completed_test_rows', 'raw_backbone_task_macro', 'operational_coverage', 'paired_gp_minus_rf')}))


if __name__ == '__main__':
    main()
