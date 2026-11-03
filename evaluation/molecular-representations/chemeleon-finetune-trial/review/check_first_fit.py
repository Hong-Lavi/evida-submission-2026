"""Inspect both completed first-task fits without fitting, GPU or test gold."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
TRIAL = HERE.parent
EXPECTED_PROTOCOL = '338a1e229ab3a848058eb694075159b8802ad3b873beb4949847a773932825ab'


def guard(event, args):
    if event == 'open' and isinstance(args[0], str) and ('evaluation-only' in args[0] or 'test-gold' in args[0]):
        raise PermissionError('Independent review cannot open official test labels')


sys.addaudithook(guard)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


assert sha(TRIAL / 'protocol.json') == EXPECTED_PROTOCOL
protocol = json.loads((TRIAL / 'protocol.json').read_text())
assert json.loads((TRIAL / 'protocol-receipt.json').read_text())['sha256'] == EXPECTED_PROTOCOL
source_checks = {name: sha(TRIAL / name) == expected for name, expected in protocol['source_pins'].items()}
assert all(source_checks.values())
task = protocol['tasks'][0]
assert task['task'] == 'CHEMBL1862_Ki'
p_input = TRIAL / 'inputs' / (task['task'] + '.json')
assert sha(p_input) == task['input_sha256']
data = json.loads(p_input.read_text())
train_y = np.asarray([row['p_activity'] for row in data['train']], dtype=np.float64)
train_float32 = np.asarray(train_y, dtype=np.float32).astype(np.float64)
val_y = np.asarray([row['p_activity'] for row in data['validation']], dtype=np.float64)
val_float32 = np.asarray(val_y, dtype=np.float32).astype(np.float64)
mean_baseline_mae = float(np.mean(np.abs(val_y - np.mean(train_y))))
results = []
head_hashes = []
for arm in protocol['arms']:
    directory = TRIAL / 'run-01' / task['task'] / arm
    p_prediction = directory / 'predictions.json'
    record = json.loads(p_prediction.read_text())
    fit = json.loads((directory / 'fit.json').read_text())
    receipt = json.loads((directory.parent / (arm + '-receipt.json')).read_text())
    val_pred = np.asarray([row['prediction'] for row in record['validation_predictions']])
    pred = np.asarray([row['prediction'] for row in record['rows']])
    with (directory / 'metrics/version_0/metrics.csv').open() as handle:
        metrics = list(csv.DictReader(handle))
    validation_epochs = [(int(float(row['epoch'])), float(row['val_loss'])) for row in metrics if row.get('val_loss')]
    best_epoch, best_loss = min(validation_epochs, key=lambda pair: pair[1])
    scaler_mean = float(np.mean(train_float32))
    scaler_scale = float(np.std(train_float32))
    scaled_mse = float(np.mean(((val_pred - val_float32) / scaler_scale) ** 2))
    mae = float(np.mean(np.abs(val_pred - val_y)))
    rho = round(float(spearmanr(val_y, val_pred).statistic), 3)
    checks = {
        'receipt_completed_and_hash_matches': receipt['status'] == 'completed' and receipt['returncode'] == 0 and receipt['prediction_sha256'] == sha(p_prediction),
        'record_uses_amended_protocol': record['protocol_sha256'] == EXPECTED_PROTOCOL,
        'record_uses_frozen_input': record['input_sha256'] == task['input_sha256'],
        'prediction_and_fit_metadata_identical': record['fit'] == fit,
        'validation_ids_and_order': [r['candidate_id'] for r in record['validation_predictions']] == [r['candidate_id'] for r in data['validation']],
        'prediction_ids_and_order': [r['candidate_id'] for r in record['rows']] == [r['candidate_id'] for r in data['prediction_rows']],
        'all_predictions_finite': bool(np.isfinite(val_pred).all() and np.isfinite(pred).all()),
        'expected_rows': (len(data['train']), len(val_pred), len(pred)) == (475, 158, 161),
        'scaler_mean_training_only': abs(fit['target_scaler']['mean'][0] - scaler_mean) < 1e-12,
        'scaler_scale_training_only': abs(fit['target_scaler']['scale'][0] - scaler_scale) < 1e-12,
        'validation_MAE_recomputed': abs(record['validation_mae'] - mae) < 1e-12,
        'validation_Spearman_independent_scipy': record['validation_spearman'] == rho,
        'mean_comparator_recomputed': abs(record['mean_validation_mae'] - mean_baseline_mae) < 1e-12,
        'eligibility_validation_only': record['usable'] == (rho >= .3 and mae < mean_baseline_mae),
        'best_checkpoint_file_matches_hash': sha(directory / 'checkpoint/best.ckpt') == fit['best_checkpoint_sha256'],
        'best_val_loss_is_minimum_logged': abs(fit['best_validation_loss'] - best_loss) < 1e-12,
        'unscaled_prediction_MSE_matches_best_normalized_loss': abs(scaled_mse - best_loss) < 1e-5,
        'all_fitted_epochs_logged': len(validation_epochs) == fit['epochs_completed'],
        'early_stop_matches_patience5': fit['epochs_completed'] == protocol['maximum_epochs'] or fit['epochs_completed'] == best_epoch + 6,
        'encoder_changed_during_fit': fit['initial_encoder_sha256'] != fit['fitted_encoder_sha256'],
        'bound_epoch_batch_seed': fit['maximum_epochs'] == 50 and fit['batch_size'] == 64 and fit['seed'] == protocol['seed'],
        'correct_arm': fit['pretrained'] == (arm == 'chemeleon_finetuned'),
        'worker_records_no_test_gold_read': record['official_test_labels_read'] is False,
    }
    head_hashes.append(fit['initial_head_sha256'])
    results.append({'arm': arm, 'checks': checks,
                    'epochs_completed': fit['epochs_completed'], 'best_epoch_zero_based': best_epoch,
                    'best_normalized_validation_MSE': best_loss, 'recomputed_normalized_validation_MSE': scaled_mse,
                    'prediction_sha256': sha(p_prediction), 'fit_sha256': sha(directory / 'fit.json'),
                    'checkpoint_sha256': sha(directory / 'checkpoint/best.ckpt')})
head_check = len(set(head_hashes)) == 1
frozen = HERE / 'amended-freeze'
frozen.mkdir(exist_ok=False)
copied = {}
for name in ('protocol.json', 'protocol-receipt.json', 'pretraining-amendment.json',
             'finetune_adapter.py', 'run_comparison.py', 'score_comparison.py', 'metrics_common.py',
             'prepare_data.py', 'metric-source-map.json', 'input-manifest.json'):
    shutil.copyfile(TRIAL / name, frozen / name)
    copied[name] = sha(frozen / name)
result = {'status': 'PASS' if head_check and all(all(r['checks'].values()) for r in results) else 'FAIL',
          'task': task['task'], 'amended_protocol_sha256': EXPECTED_PROTOCOL,
          'original_protocol_sha256': sha(HERE / 'original-freeze/protocol.json'),
          'all_protocol_source_pins_match': source_checks,
          'both_arms_identical_initial_head': head_check, 'arms': results,
          'amended_snapshot_sha256': copied,
          'scope': 'Independent review of saved first-task training and prediction artifacts; no outer performance evaluation.',
          'official_test_labels_read': False, 'model_fits': 0, 'GPU_used': False, 'network_calls': 0}
(HERE / 'first-fit-review.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'status': result['status'], 'task': task['task'], 'checks_per_arm': len(results[0]['checks']), 'official_test_labels_read': False}))
assert result['status'] == 'PASS'
