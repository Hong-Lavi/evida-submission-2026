"""Paired actual native-RF/author-GP fits; this process never opens test gold."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
def utc():
    return datetime.now(timezone.utc).isoformat()
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
def load_protocol():
    path = HERE / 'protocol.json'
    assert sha(path) == json.loads((HERE / 'protocol-receipt.json').read_text())['sha256']
    protocol = json.loads(path.read_text())
    for name, expected in protocol['source_pins'].items():
        assert sha(HERE / name) == expected, name
    protocol['data'] = str(HERE / protocol['data'])
    protocol['frozen_product'] = str(HERE / protocol['frozen_product'])
    return protocol


def worker(task_name, run_dir):
    protocol = load_protocol()
    task = next(t for t in protocol['tasks'] if t['task'] == task_name)
    out = run_dir / task_name
    save(out / 'started.json', {'at': utc(), 'task': task_name, 'protocol_sha256': sha(HERE / 'protocol.json'),
                               'test_gold_read': False, 'pid': os.getpid()})
    data = Path(protocol['data']) / task_name
    assert sha(data / 'train.json') == task['train_sha256']
    assert sha(data / 'test-features.json') == task['features_sha256']
    train = json.loads((data / 'train.json').read_text())
    features = json.loads((data / 'test-features.json').read_text())
    sys.path.insert(0, protocol['frozen_product'])
    import numpy as np
    import sklearn.ensemble
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator
    from gp_adapter import fit_gp, predict_gp
    captured = []
    original = sklearn.ensemble.RandomForestRegressor
    class RecordingRF(original):
        def fit(self, x, y, *args, **kwargs):
            result = super().fit(x, y, *args, **kwargs)
            captured.append((self, x.copy(), y.copy()))
            return result
    sklearn.ensemble.RandomForestRegressor = RecordingRF
    from evida.activity_model import fit, _spearman
    began = time.monotonic()
    fitted = fit(train, seed=protocol['seed'], endpoint=task['endpoint'])
    rf_seconds = time.monotonic() - began
    save(out / 'native-fit.json', {k: v for k, v in fitted.items() if k not in ('model', 'fingerprint', '_seed_rows', '_training_rows')})
    if len(captured) != 1:
        raise ValueError('Native fit did not produce exactly one backbone; retain its gate result')
    rf, x_train, y_train = captured[0]
    assert (rf.n_estimators, rf.min_samples_leaf, rf.n_jobs, rf.random_state) == (300, 2, 2, 20260930)
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)
    def matrix(rows):
        mols = [Chem.MolFromSmiles(row['smiles']) for row in rows]
        if any(m is None for m in mols):
            raise ValueError('Invalid molecule in frozen matrix; do not silently drop a case')
        return np.asarray([list(generator.GetFingerprint(m)) for m in mols], dtype=float)
    training_rows = fitted['_training_rows']
    assert np.array_equal(matrix(training_rows), x_train)
    assert np.array_equal([r['p_activity'] for r in training_rows], y_train)
    train_smiles = {r['smiles'] for r in training_rows}
    held = [r for r in fitted['_seed_rows'] if r['smiles'] not in train_smiles]
    assert len(held) == fitted['summary']['held_out']
    x_held, y_held, x_test = matrix(held), np.asarray([r['p_activity'] for r in held]), matrix(features)
    rf_held = rf.predict(x_held)
    rf_test = rf.predict(x_test)
    training_mean = float(y_train.mean())
    rf_held_mae = float(np.mean(np.abs(rf_held - y_held)))
    mean_held_mae = float(np.mean(np.abs(training_mean - y_held)))
    save(out / 'rf-predictions.json', {'rows': [{'candidate_id': row['candidate_id'], 'prediction': float(pred)} for row, pred in zip(features, rf_test)],
                                     'training_mean': training_mean, 'usable': fitted['usable'], 'fit_seconds': rf_seconds})
    gp, gp_fit = fit_gp(x_train, y_train, seed=protocol['seed'])
    save(out / 'gp-fit.json', gp_fit)
    gp_held, _, _ = predict_gp(gp, gp_fit, x_held)
    gp_test, latent, observation = predict_gp(gp, gp_fit, x_test)
    assert all(np.isfinite(v).all() for v in (rf_test, gp_test, latent, observation))
    gp_mae = float(np.mean(np.abs(gp_held - y_held)))
    gp_rho = round(_spearman(gp_held.tolist(), y_held.tolist()), 3)
    gp_usable = gp_fit['optimization']['converged'] and gp_rho >= 0.3 and gp_mae < mean_held_mae
    candidates = [(rf_held_mae, 0, 'rf')] if fitted['usable'] else []
    if gp_usable:
        candidates.append((gp_mae, 1, 'gp'))
    policy = min(candidates)[2] if candidates else 'abstain'
    result = {'task': task_name, 'status': 'completed', 'at': utc(), 'gpu_used': False, 'test_gold_read': False,
              'training_rows': len(y_train), 'inner_held_out_rows': len(y_held), 'test_rows': len(features),
              'training_mean': training_mean, 'inner_mean_mae': mean_held_mae,
              'native_rf': {'usable': fitted['usable'], 'inner_mae': rf_held_mae, 'fit_seconds': rf_seconds},
              'author_gp': {'usable': bool(gp_usable), 'inner_mae': gp_mae, 'inner_spearman': gp_rho, **gp_fit},
              'selected_policy_arm': policy,
              'train_matrix_sha256': hashlib.sha256(x_train.tobytes()).hexdigest(),
              'train_labels_sha256': hashlib.sha256(y_train.tobytes()).hexdigest(),
              'rows': [{'candidate_id': row['candidate_id'], 'rf_prediction': float(r), 'gp_prediction': float(g),
                        'gp_latent_std': float(ls), 'gp_observation_std': float(obs)}
                       for row, r, g, ls, obs in zip(features, rf_test, gp_test, latent, observation)]}
    save(out / 'predictions.json', result)


def supervise(task, run_dir, timeout):
    out = run_dir / task
    out.mkdir(exist_ok=False)
    began = time.monotonic()
    with (out / 'process.log').open('w') as log:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2')
        process = subprocess.Popen([sys.executable, '-B', __file__, '--worker', task, str(run_dir)],
                                   stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
            status = 'completed' if code == 0 and (out / 'predictions.json').exists() else 'failed'
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code, status = process.returncode, 'timeout'
    result = {'task': task, 'status': status, 'returncode': code, 'seconds': time.monotonic() - began,
              'prediction_sha256': sha(out / 'predictions.json') if (out / 'predictions.json').exists() else None}
    save(out / 'receipt.json', result)
    print(json.dumps(result), flush=True)
    return result


def main(run_dir):
    protocol = load_protocol()
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(exist_ok=False)
    save(run_dir / 'started.json', {'at': utc(), 'protocol_sha256': sha(HERE / 'protocol.json'),
                                  'all_tasks_planned': protocol['order'], 'test_gold_read': False})
    receipts = []
    with ThreadPoolExecutor(max_workers=protocol['concurrency']) as pool:
        jobs = [pool.submit(supervise, task, run_dir, protocol['timeout_task_seconds']) for task in protocol['order']]
        for future in as_completed(jobs):
            receipts.append(future.result())
    by_task = {r['task']: r for r in receipts}
    receipts = [by_task[t] for t in protocol['order']]
    save(run_dir / 'sealed-predictions.json', {'at': utc(), 'protocol_sha256': sha(HERE / 'protocol.json'),
                                            'test_gold_read': False, 'tasks': receipts})
    print(json.dumps({'finished': len(receipts), 'completed': sum(r['status'] == 'completed' for r in receipts)}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        worker(sys.argv[2], Path(sys.argv[3]))
    else:
        import argparse
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--out', type=Path, help='New directory for a separate full fitting run')
        parser.add_argument('--verify-only', action='store_true', help='Verify protocol/source pins without fitting')
        args = parser.parse_args()
        if args.verify_only:
            load_protocol()
            print(json.dumps({'status': 'PASS', 'model_fits': 0}))
        elif args.out is None:
            parser.error('--out is required for model fitting')
        else:
            main(args.out)
