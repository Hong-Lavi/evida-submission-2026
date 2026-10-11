"""One explicitly assigned GPU, two matched neural arms, all fixed tasks, no retry."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def verify(protocol):
    receipt = json.loads((HERE / 'protocol-receipt.json').read_text())
    if sha(HERE / 'protocol.json') != receipt['sha256']:
        raise ValueError('Frozen protocol changed')
    for name, expected in protocol['source_pins'].items():
        if sha(HERE / name) != expected:
            raise ValueError('Frozen source changed: ' + name)
    if sha(BASE / 'chemeleon-trial/weights/chemeleon_mp.pt') != protocol['weights_sha256']:
        raise ValueError('Frozen author weights changed')
    for task in protocol['tasks']:
        if sha(HERE / 'inputs' / (task['task'] + '.json')) != task['input_sha256']:
            raise ValueError('Frozen task inputs changed')
        if sha(BASE / 'tanimoto-trial/run-01' / task['task'] / 'predictions.json') != task['reference_predictions_sha256']:
            raise ValueError('Frozen reference predictions changed')


def worker(task_name, arm, run_dir):
    import numpy as np
    from finetune_adapter import fit_predict
    from metrics_common import spearman
    protocol = json.loads((HERE / 'protocol.json').read_text())
    verify(protocol)
    data = json.loads((HERE / 'inputs' / (task_name + '.json')).read_text())
    out = Path(run_dir) / task_name / arm
    val, pred, fit = fit_predict(data['train'], data['validation'], data['prediction_rows'],
                                 BASE / 'chemeleon-trial/weights/chemeleon_mp.pt', out,
                                 pretrained=arm == 'chemeleon_finetuned', seed=protocol['seed'],
                                 epochs=protocol['maximum_epochs'], batch_size=protocol['batch_size'])
    y = np.asarray([row['p_activity'] for row in data['validation']])
    baseline = float(np.mean([row['p_activity'] for row in data['train']]))
    error = float(np.mean(np.abs(val - y)))
    mean_error = float(np.mean(np.abs(baseline - y)))
    rho = round(spearman(val.tolist(), y.tolist()), 3)
    result = {'task': task_name, 'arm': arm, 'status': 'completed', 'fit': fit,
              'usable': rho >= .3 and error < mean_error,
              'validation_mae': error, 'validation_spearman': rho, 'mean_validation_mae': mean_error,
              'validation_predictions': [{'candidate_id': row['candidate_id'], 'prediction': float(value)}
                                         for row, value in zip(data['validation'], val)],
              'rows': [{'candidate_id': row['candidate_id'], 'prediction': float(value)}
                       for row, value in zip(data['prediction_rows'], pred)],
              'input_sha256': sha(HERE / 'inputs' / (task_name + '.json')),
              'protocol_sha256': sha(HERE / 'protocol.json'), 'official_test_labels_read': False}
    save(out / 'predictions.json', result)


def main(run_dir):
    protocol = json.loads((HERE / 'protocol.json').read_text())
    verify(protocol)
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(exist_ok=False)
    if os.environ.get('CUDA_VISIBLE_DEVICES') != protocol['gpu_uuid']:
        raise ValueError('Run must use the exact GPU assigned in the frozen protocol')
    receipts = []
    stopped_for_resource = False
    for task in protocol['tasks']:
        name = task['task']
        task_dir = run_dir / name
        task_dir.mkdir()
        for arm in protocol['arms']:
            if stopped_for_resource:
                record = {'task': name, 'arm': arm, 'status': 'not_started_resource_busy',
                          'returncode': None, 'seconds': 0, 'prediction_sha256': None}
                receipts.append(record)
                save(task_dir / (arm + '-receipt.json'), record)
                continue
            if datetime.now(timezone.utc).isoformat() >= protocol['stop_starting_new_arms_at_utc']:
                record = {'task': name, 'arm': arm, 'status': 'not_started_time_budget',
                          'returncode': None, 'seconds': 0, 'prediction_sha256': None}
                receipts.append(record)
                save(task_dir / (arm + '-receipt.json'), record)
                continue
            # Stop before allocating an occupied GPU. Do not switch to another user's device.
            resource = subprocess.run(['nvidia-smi', '--id=' + protocol['gpu_uuid'],
                '--query-gpu=memory.used,utilization.gpu', '--format=csv,noheader,nounits'],
                text=True, capture_output=True, check=True)
            memory_used = int(resource.stdout.split(',')[0].strip())
            if memory_used > protocol['idle_memory_limit_mib']:
                save(run_dir / 'resource-stop.json', {'task': name, 'arm': arm, 'status': 'resource_busy',
                    'memory_used_mib': memory_used, 'completed': receipts})
                stopped_for_resource = True
                record = {'task': name, 'arm': arm, 'status': 'not_started_resource_busy',
                          'returncode': None, 'seconds': 0, 'prediction_sha256': None,
                          'resource_check': resource.stdout.strip()}
                receipts.append(record)
                save(task_dir / (arm + '-receipt.json'), record)
                continue
            began = time.monotonic()
            try:
                with (task_dir / (arm + '.log')).open('wb') as log:
                    result = subprocess.run([sys.executable, '-B', str(HERE / 'run_comparison.py'),
                        '--worker', name, '--arm', arm, '--out', str(run_dir)], cwd=HERE,
                        stdout=log, stderr=subprocess.STDOUT, timeout=protocol['maximum_seconds_per_arm'])
                code = result.returncode
                status = 'completed' if code == 0 else 'failed'
            except subprocess.TimeoutExpired:
                code, status = None, 'timed_out'
            prediction_path = task_dir / arm / 'predictions.json'
            if status == 'completed' and not prediction_path.exists():
                status = 'failed_missing_predictions'
            record = {'task': name, 'arm': arm, 'status': status, 'returncode': code,
                      'seconds': time.monotonic() - began, 'resource_check': resource.stdout.strip(),
                      'prediction_sha256': sha(prediction_path) if prediction_path.exists() else None}
            receipts.append(record)
            save(task_dir / (arm + '-receipt.json'), record)
            save(run_dir / 'progress.json', {'planned_arms': len(protocol['tasks']) * len(protocol['arms']),
                                            'completed': receipts})
            print(json.dumps(record), flush=True)
    save(run_dir / 'completion.json', {'status': 'prediction_generation_finished',
          'protocol_sha256': sha(HERE / 'protocol.json'), 'attempts': receipts,
          'official_test_labels_read': False, 'retries': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker')
    parser.add_argument('--arm')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.arm, args.out)
    else:
        main(args.out)
