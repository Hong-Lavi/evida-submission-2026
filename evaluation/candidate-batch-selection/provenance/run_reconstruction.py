"""All-task joint-posterior recovery and marginal parity; no acquisition scoring."""
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import time

import gpytorch
import numpy as np
import torch

from reconstruct_gp import BASE, reconstruct, sha

HERE = Path(__file__).resolve().parent
OUT = HERE / 'reconstruction-01'
OUT.mkdir(exist_ok=False)
protocol = json.loads((BASE / 'tanimoto-trial/protocol.json').read_text())
tasks = protocol['order']
pins = {str(p.relative_to(BASE)): sha(p) for p in [
    HERE / 'reconstruct_gp.py', Path(__file__).resolve(),
    BASE / 'repo/product/evida/vendor/tanimoto_gp/tanimoto_gp.py',
    BASE / 'repo/product/evida/vendor/tanimoto_gp/tanimoto_functions.py',
    BASE / 'tanimoto-trial/protocol.json',
]}
started = datetime.now(timezone.utc).isoformat()
records = []
(OUT / 'started.json').write_text(json.dumps({
    'at': started, 'task_ids': tasks, 'purpose': 'Recover joint posterior from already fitted model',
    'versions': {n: importlib.metadata.version(n) for n in ['numpy','torch','gpytorch','botorch','rdkit']},
    'code_pins': pins, 'external_test_labels_read': False,
    'score_or_policy_selection_performed': False, 'gpu_used': False,
    'tolerance_absolute': 1e-7,
}, indent=2) + '\n')
for task in tasks:
    began = time.monotonic()
    try:
        model, fit, features, ids, original, provenance = reconstruct(task)
        with torch.no_grad(), gpytorch.settings.fast_computations(False, False, False), gpytorch.settings.max_cholesky_size(10000):
            posterior = model(features)
            mean = posterior.mean.numpy() * fit['scale'] + fit['center']
            covariance = posterior.covariance_matrix.numpy() * fit['scale'] ** 2
        latent_sd = np.sqrt(np.diag(covariance))
        observation_sd = np.sqrt(np.diag(covariance) + fit['parameters_standardized']['noise'] * fit['scale'] ** 2)
        diffs = {name: float(np.max(np.abs(values - [r[key] for r in original['rows']])))
                 for name, values, key in [('mean',mean,'gp_prediction'), ('latent_sd',latent_sd,'gp_latent_std'),
                                           ('observation_sd',observation_sd,'gp_observation_std')]}
        assert all(np.isfinite(v).all() for v in [mean,covariance,latent_sd,observation_sd])
        assert max(diffs.values()) <= 1e-7, diffs
        asymmetry = float(np.max(np.abs(covariance - covariance.T)))
        minimum_eigenvalue = float(np.linalg.eigvalsh(covariance).min())
        assert asymmetry <= 1e-7 and minimum_eigenvalue >= -1e-7
        output = OUT / (task + '.npz')
        np.savez_compressed(output, candidate_ids=np.asarray(ids), mean=mean,
                            latent_covariance=covariance, observation_sd=observation_sd)
        record = {**provenance, 'status':'PASS', 'maximum_absolute_difference':diffs,
                  'covariance_maximum_asymmetry':asymmetry, 'minimum_covariance_eigenvalue':minimum_eigenvalue,
                  'joint_posterior_sha256':sha(output), 'bytes':output.stat().st_size}
    except Exception as error:
        record = {'task':task,'status':'FAILED','error':f'{type(error).__name__}: {error}'}
    record['elapsed_seconds'] = time.monotonic() - began
    records.append(record)
    (OUT / (task + '.receipt.json')).write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'task':task,'status':record['status'],'elapsed_seconds':record['elapsed_seconds'],
                      **({'error':record['error']} if 'error' in record else {})}), flush=True)
assert all(sha(BASE/name)==digest for name,digest in pins.items())
result = {'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),
          'tasks_planned':len(tasks),'tasks_passed':sum(r['status']=='PASS' for r in records),
          'rows':records,'gpu_used':False,'model_fits':0,'provider_calls':0,'external_test_labels_read':False,
          'interpretation':'Numerical model reconstruction only. No batch selections or performance outcomes evaluated.'}
(OUT / 'summary.json').write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(result['tasks_passed'] != len(tasks))
