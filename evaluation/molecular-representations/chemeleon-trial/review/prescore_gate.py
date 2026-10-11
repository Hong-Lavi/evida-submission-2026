"""Independent pre-score gate. Never opens gold; optionally calls frozen scorer.

Two phases: every planned receipt/source/prediction byte hash first, then
prediction structure and feature membership. No metric or selection changes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    return value


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')


def validate(root=ROOT):
    root = Path(root)
    manifest = {}
    def pin(path, expected=None):
        actual = sha(path)
        require(expected is None or actual == expected, 'Hash mismatch: ' + str(path))
        manifest[str(path)] = actual
        return actual
    amendment_path = root / 'review/scoring-amendment.json'
    pin(amendment_path, read(root / 'review/scoring-amendment-receipt.json')['sha256'])
    amendment = read(amendment_path)
    pin(root / 'review/prescore_gate.py', amendment['gate_sha256'])
    protocol_path = root / 'protocol.json'
    protocol_hash = pin(protocol_path, amendment['original_protocol_sha256'])
    require(read(root / 'protocol-receipt.json')['sha256'] == protocol_hash, 'Original protocol receipt mismatch')
    p = read(protocol_path)
    order = p['order']
    require(len(order) == 30 and len(set(order)) == 30, 'Require original 30 unique tasks')
    require([t['task'] for t in p['tasks']] == order, 'Protocol task/order mismatch')
    require(set(p['gp_prediction_pins']) == set(order), 'Prior prediction pin coverage mismatch')
    for name, expected in p['source_pins'].items():
        pin(root / name, expected)
    require(p['source_pins']['score_comparison.py'] == amendment['original_scorer_sha256'], 'Scorer amendment mismatch')
    gp = root.parent / 'tanimoto-trial'
    pin(gp / 'protocol.json', p['gp_protocol_sha256'])
    for name, expected in p['native_source_pins'].items():
        pin(gp / name, expected)
    run = root / 'run-01'
    require(not (run / 'scored-results.json').exists(), 'Original score already exists; pre-score gate cannot be retrospective')
    pin(run / 'started.json')
    started = read(run / 'started.json')
    require(started['protocol_sha256'] == protocol_hash and started['tasks'] == order, 'Run start mismatch')
    pin(run / 'sealed-predictions.json')
    seal = read(run / 'sealed-predictions.json')
    require(seal['protocol_sha256'] == protocol_hash, 'Seal protocol mismatch')
    require(seal.get('test_gold_read_by_fitting') is False, 'Missing fitting access declaration')
    require([r['task'] for r in seal['tasks']] == order, 'Terminal seal task coverage mismatch')
    # Finish EVERY task's byte-level check before parsing ANY prediction JSON.
    for receipt, task in zip(seal['tasks'], p['tasks']):
        name = task['task']; out = run / name
        pin(out / 'receipt.json')
        require(read(out / 'receipt.json') == receipt, 'Terminal receipt differs from seal: ' + name)
        require(receipt['status'] in {'completed', 'failed', 'timeout'}, 'Nonterminal task: ' + name)
        completed = receipt['status'] == 'completed'
        require(not completed or receipt.get('returncode') == 0, 'Completed return code mismatch: ' + name)
        require(not completed or bool(receipt.get('prediction_sha256')), 'Completed task has no prediction hash: ' + name)
        path = out / 'predictions.json'
        require(path.exists() == bool(receipt.get('prediction_sha256')), 'Unsealed/missing partial prediction: ' + name)
        if path.exists():
            pin(path, receipt['prediction_sha256'])
        for extra in ('baseline-reproduced.json', 'embeddings.npz', 'started.json', 'process.log'):
            file = out / extra
            if file.exists():
                pin(file)
        require(not completed or (out / 'baseline-reproduced.json').exists(), 'Missing baseline reproduction: ' + name)
        require(not completed or (out / 'embeddings.npz').exists(), 'Missing embedding artifact: ' + name)
        pin(Path(p['gp_run']) / name / 'predictions.json', p['gp_prediction_pins'][name])
        pin(Path(p['data']) / name / 'train.json', task['train_sha256'])
        pin(Path(p['data']) / name / 'test-features.json', task['features_sha256'])

    def finite(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    def policy(pred, include_embedding=False):
        choices = []
        arms = [('rf', 'native_rf'), ('gp', 'author_gp')]
        if include_embedding:
            arms.append(('chemeleon_rf', 'chemeleon_rf'))
        for priority, (arm, key) in enumerate(arms):
            meta = pred[key]
            require(type(meta['usable']) is bool and finite(meta['inner_mae']), 'Invalid inner policy metadata')
            if meta['usable']:
                choices.append((meta['inner_mae'], priority, arm))
        return min(choices)[2] if choices else 'abstain'
    def structure(pred, task, ids, embedding):
        require(pred['task'] == task['task'] and pred['status'] == 'completed', 'Prediction identity/status mismatch')
        require(pred.get('test_gold_read') is False, 'Missing prediction access declaration')
        require(pred['test_rows'] == task['official_test'], 'Prediction declared row count mismatch')
        rows = pred['rows']; actual = [r['candidate_id'] for r in rows]
        require(len(actual) == len(set(actual)) == len(ids) and set(actual) == set(ids), 'Prediction candidate coverage mismatch')
        keys = ['rf_prediction', 'gp_prediction', 'gp_latent_std', 'gp_observation_std']
        if embedding:
            keys.append('chemeleon_rf_prediction')
        require(all(finite(r[k]) for r in rows for k in keys), 'Non-finite prediction')
        require(pred['selected_policy_arm'] == policy(pred, embedding), 'Stored policy choice mismatch')
        return {r['candidate_id']: r for r in rows}
    for receipt, task in zip(seal['tasks'], p['tasks']):
        name = task['task']; out = run / name
        features = read(Path(p['data']) / name / 'test-features.json')
        require(all(set(r) == {'candidate_id', 'smiles'} for r in features), 'Unexpected feature fields')
        ids = [r['candidate_id'] for r in features]
        require(len(ids) == len(set(ids)) == task['official_test'], 'Feature ID/count mismatch')
        require(all(isinstance(i, str) and i for i in ids), 'Invalid feature ID')
        previous = read(Path(p['gp_run']) / name / 'predictions.json')
        old_rows = structure(previous, task, ids, False)
        require(finite(previous['inner_mean_mae']), 'Invalid training mean baseline metadata')
        if receipt['status'] != 'completed':
            continue  # Frozen policy deliberately falls back; partial artifacts stay sealed.
        pred = read(out / 'predictions.json')
        new_rows = structure(pred, task, ids, True)
        require(all({k: v for k, v in row.items() if k != 'chemeleon_rf_prediction'} == old_rows[cid]
                    for cid, row in new_rows.items()), 'Copied baseline prediction differs from frozen prior')
        for key in ('native_rf', 'author_gp', 'train_matrix_sha256', 'train_labels_sha256', 'training_rows', 'inner_held_out_rows'):
            require(pred[key] == previous[key], 'Changed prior/training metadata: ' + key)
        require(pred['prior_policy_arm'] == previous['selected_policy_arm'], 'Prior policy mismatch')
        require(pred['weights_sha256'] == p['weights_sha256'], 'Weight metadata mismatch')
        require(pred['embeddings_sha256'] == manifest[str(out / 'embeddings.npz')], 'Embedding hash mismatch')
        baseline = read(out / 'baseline-reproduced.json')
        require(baseline['same_native_training_matrix'] is True and baseline['same_native_labels'] is True
                and baseline['same_test_predictions_atol'] == 1e-10, 'Baseline reproduction failed')
        meta = pred['chemeleon_rf']
        require(finite(meta['inner_spearman']), 'Invalid inner Spearman')
        require(meta['usable'] == (meta['inner_spearman'] >= .3 and meta['inner_mae'] < previous['inner_mean_mae']),
                'Embedding usability differs from frozen policy')
    # Recheck all bytes at the gate boundary. No gold path occurs in manifest.
    for path, expected in manifest.items():
        require(sha(Path(path)) == expected, 'Input changed during gate: ' + path)
    return {'status': 'PRESCORE_GATE_PASSED', 'at_utc': datetime.now(timezone.utc).isoformat(),
            'planned_tasks': 30, 'completed_tasks': sum(r['status'] == 'completed' for r in seal['tasks']),
            'official_gold_opened_by_gate': False, 'prediction_values_reported': False,
            'protocol_sha256': protocol_hash, 'verified_file_sha256': manifest}


def guarded_score(root=ROOT, scorer=None):
    receipt = validate(root)
    save(Path(root) / 'review/prescore-gate-receipt.json', receipt)
    if scorer is None:
        sys.path.insert(0, str(root))
        spec = importlib.util.spec_from_file_location('chemeleon_original_frozen_scorer', Path(root) / 'score_comparison.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        scorer = module.main
    scorer()
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--score', action='store_true', help='After a successful gate, invoke unchanged original scorer')
    args = parser.parse_args()
    result = guarded_score() if args.score else validate()
    print(json.dumps({k: result[k] for k in ('status', 'planned_tasks', 'completed_tasks', 'official_gold_opened_by_gate')}))
