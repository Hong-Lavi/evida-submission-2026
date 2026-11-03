"""A bounded CPU adapter around Tripp et al.'s unchanged Tanimoto GP classes.

The only author-API substitution is the renamed modern BoTorch SciPy fitter.
Fingerprinting and inner training rows are supplied by the native EVIDA control.
"""
from pathlib import Path
import sys
import time

import gpytorch
import numpy as np
import torch
from botorch.optim.fit import fit_gpytorch_mll_scipy

sys.path.insert(0, str(Path(__file__).resolve().parent / 'author'))
from trf23.tanimoto_gp import TanimotoKernelGP, get_gp_hyperparameters


def fit_gp(x, y, seed=20260930, maxiter=100, timeout=180):
    torch.set_num_threads(2)
    torch.manual_seed(seed)
    center, scale = float(np.mean(y)), float(np.std(y))
    scale = scale if scale > 1e-8 else 1.0
    tx = torch.as_tensor(x, dtype=torch.float64, device='cpu')
    ty = torch.as_tensor((np.asarray(y) - center) / scale, dtype=torch.float64, device='cpu')
    model = TanimotoKernelGP(tx, ty, 'T_DP', gpytorch.means.ConstantMean()).double()
    model.covar_module.outputscale = 1.0
    model.likelihood.noise = 0.1
    model.mean_module.constant = 0.0
    model.train()
    mll = gpytorch.mlls.ExactMarginalLogLikelihood(model.likelihood, model)
    began = time.monotonic()
    with gpytorch.settings.fast_computations(False, False, False), gpytorch.settings.max_cholesky_size(10000):
        result = fit_gpytorch_mll_scipy(mll, options={'maxiter': maxiter, 'ftol': 1e-9}, timeout_sec=timeout)
    result_info = {key: str(getattr(result, key)) for key in ('status', 'message')}
    result_info.update({key: float(getattr(result, key)) for key in ('fval', 'runtime')})
    result_info['step'] = int(result.step)
    result_info['converged'] = str(result.status).endswith('SUCCESS')
    return model, {'center': center, 'scale': scale, 'fit_seconds': time.monotonic() - began,
                   'optimization': result_info, 'parameters_standardized': get_gp_hyperparameters(model)}


def predict_gp(model, fitted, x, batch_size=128):
    model.eval()
    model.likelihood.eval()
    means, latent, observation = [], [], []
    with torch.no_grad(), gpytorch.settings.fast_computations(False, False, False), gpytorch.settings.max_cholesky_size(10000):
        for offset in range(0, len(x), batch_size):
            tx = torch.as_tensor(x[offset:offset + batch_size], dtype=torch.float64, device='cpu')
            output = model(tx)
            observed = model.likelihood(output)
            means.extend((output.mean.numpy() * fitted['scale'] + fitted['center']).tolist())
            latent.extend((output.stddev.numpy() * fitted['scale']).tolist())
            observation.extend((observed.stddev.numpy() * fitted['scale']).tolist())
    return np.asarray(means), np.asarray(latent), np.asarray(observation)
