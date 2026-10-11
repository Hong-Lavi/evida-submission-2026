"""Reconstruct the fitted author GP from exact inputs and saved hyperparameters.

No fitting, acquisition policy, provider, or external-test-label access occurs.
The resulting joint posterior can support a separately specified batch trial.
"""
from pathlib import Path
import hashlib
import json
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'repo/product'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconstruct(task):
    import gpytorch
    import numpy as np
    import torch
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator
    from evida.vendor.tanimoto_gp.tanimoto_gp import TanimotoKernelGP

    torch.set_num_threads(2)
    source = BASE / 'tanimoto-trial/run-01' / task
    inputs = BASE / 'chemeleon-finetune-trial/inputs' / (task + '.json')
    packet = json.loads(inputs.read_text())
    original = json.loads((source / 'predictions.json').read_text())
    fit = json.loads((source / 'gp-fit.json').read_text())
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)

    def matrix(rows):
        mols = [Chem.MolFromSmiles(row['smiles']) for row in rows]
        if any(m is None for m in mols):
            raise ValueError('Invalid retained molecular structure')
        return np.asarray([list(generator.GetFingerprint(m)) for m in mols], dtype=float)

    x, y = matrix(packet['train']), np.asarray([r['p_activity'] for r in packet['train']], dtype=float)
    if hashlib.sha256(x.tobytes()).hexdigest() != original['train_matrix_sha256']:
        raise ValueError('Training matrix differs from the actual fitted GP')
    if hashlib.sha256(y.tobytes()).hexdigest() != original['train_labels_sha256']:
        raise ValueError('Training labels differ from the actual fitted GP')
    ids = [r['candidate_id'] for r in packet['prediction_rows']]
    if ids != [r['candidate_id'] for r in original['rows']] or len(set(ids)) != len(ids):
        raise ValueError('Prediction identities/order differ from the saved output')
    protocol = json.loads((BASE / 'tanimoto-trial/protocol.json').read_text())
    native_features = Path(protocol['data']) / task / 'test-features.json'
    spec = next(t for t in protocol['tasks'] if t['task'] == task)
    if sha(native_features) != spec['features_sha256']:
        raise ValueError('Original label-free test features changed')
    if packet['prediction_rows'] != json.loads(native_features.read_text()):
        raise ValueError('Prepared prediction structures differ from original features')
    tx = torch.as_tensor(x, dtype=torch.float64)
    ty = torch.as_tensor((y - fit['center']) / fit['scale'], dtype=torch.float64)
    model = TanimotoKernelGP(tx, ty, 'T_DP', gpytorch.means.ConstantMean()).double()
    parameters = fit['parameters_standardized']
    model.covar_module.outputscale = parameters['outputscale']
    model.likelihood.noise = parameters['noise']
    model.mean_module.constant = parameters['mean']
    model.eval()
    model.likelihood.eval()
    test_x = torch.as_tensor(matrix(packet['prediction_rows']), dtype=torch.float64)
    provenance = {
        'task': task, 'inputs_sha256': sha(inputs), 'fit_sha256': sha(source / 'gp-fit.json'),
        'original_predictions_sha256': sha(source / 'predictions.json'),
        'native_features_sha256': sha(native_features),
        'train_matrix_sha256': original['train_matrix_sha256'],
        'train_labels_sha256': original['train_labels_sha256'],
        'training_rows': len(x), 'candidate_rows': len(ids),
        'refitting_performed': False, 'test_labels_read': False,
    }
    return model, fit, test_x, ids, original, provenance
