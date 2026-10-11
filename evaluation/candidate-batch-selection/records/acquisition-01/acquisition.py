"""Independent finite-pool implementation from qPO paper equations and S1.

No author implementation is imported. No label I/O occurs in this module.
"""
import numpy as np

METHODS = ("rf_mean", "gp_mean", "original_policy", "random", "qPO_latent",
           "qPO_observation", "pTop10_latent", "pTop10_observation")


def rank(values, ids, secondary=None):
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("nonfinite ranking values")
    secondary = np.zeros(len(ids)) if secondary is None else np.asarray(secondary)
    return np.lexsort((np.asarray(ids), -secondary, -values))


def posterior_factor(mean, covariance):
    """Quotient only numerical equality classes; remove roundoff eigenvalues.

    Tolerances scale with dimension and machine precision, not assay noise.
    Pairwise membership is checked against every member, avoiding chaining.
    """
    mean = np.asarray(mean, dtype=np.float64)
    cov = np.asarray(covariance, dtype=np.float64)
    n = len(mean)
    if mean.shape != (n,) or cov.shape != (n, n) or n == 0:
        raise ValueError("posterior shape")
    if not np.isfinite(mean).all() or not np.isfinite(cov).all():
        raise ValueError("nonfinite posterior")
    cov_tol = 64 * np.finfo(float).eps * n * max(1., np.linalg.norm(cov, ord=np.inf))
    mean_tol = 64 * np.finfo(float).eps * n * max(1., np.max(np.abs(mean)))
    asymmetry = float(np.max(np.abs(cov - cov.T)))
    if asymmetry > cov_tol:
        raise ValueError("asymmetric covariance")
    cov = (cov + cov.T) / 2
    eigenvalues = np.linalg.eigvalsh(cov)
    if eigenvalues[0] < -cov_tol:
        raise ValueError("materially indefinite covariance")
    groups = []
    for i in range(n):
        for group in groups:
            if all(abs(mean[i] - mean[j]) <= mean_tol and
                   np.max(np.abs(cov[i] - cov[j])) <= cov_tol and
                   abs(cov[i, i] + cov[j, j] - 2 * cov[i, j]) <= cov_tol for j in group):
                group.append(i)
                break
        else:
            groups.append([i])
    reps = [g[0] for g in groups]
    small = cov[np.ix_(reps, reps)]
    eigenvalues_small, vectors = np.linalg.eigh(small)
    if eigenvalues_small[0] < -cov_tol:
        raise ValueError("indefinite quotient")
    keep = eigenvalues_small > cov_tol
    reduced = vectors[:, keep] * np.sqrt(eigenvalues_small[keep])
    lookup = np.empty(n, dtype=int)
    for number, group in enumerate(groups):
        lookup[group] = number
    adjusted_mean = mean[reps][lookup]
    factor = reduced[lookup]
    reconstructed = factor @ factor.T
    return adjusted_mean, factor, {
        "covariance_tolerance": float(cov_tol), "mean_tolerance": float(mean_tol),
        "covariance_asymmetry": asymmetry, "minimum_eigenvalue": float(eigenvalues[0]),
        "quotient_rank": int(np.sum(keep)), "quotient_groups": len(groups),
        "equal_groups": [g for g in groups if len(g) > 1],
        "roundoff_projection_max_abs": float(np.max(np.abs(reconstructed - cov))),
        "mean_projection_max_abs": float(np.max(np.abs(adjusted_mean - mean))),
        "jitter_added": 0.,
    }


def fractional_top_membership(samples, k):
    """Per-draw expected membership under uniform ordering at exact ties."""
    samples = np.asarray(samples, dtype=float)
    if samples.ndim != 2 or not np.isfinite(samples).all():
        raise ValueError("invalid samples")
    k = min(k, samples.shape[1])
    if k < 1:
        raise ValueError("invalid top k")
    threshold = np.partition(samples, samples.shape[1] - k, axis=1)[:, -k:][:, :1]
    above, tied = samples > threshold, samples == threshold
    residual = k - above.sum(axis=1)
    return above.astype(float) + tied * (residual / tied.sum(axis=1))[:, None]


def qpo_order(samples, mean, ids, size):
    """Paper S1 greedy uncovered-winner coverage; unique case is additive qPO."""
    winners = samples == samples.max(axis=1)[:, None]
    uncovered = np.ones(len(samples), dtype=bool)
    selected, gain = [], []
    for _ in range(size):
        votes = winners[uncovered].sum(axis=0).astype(float)
        votes[selected] = -1
        pick = int(rank(votes, ids, mean)[0])
        selected.append(pick)
        gain.append(float(votes[pick] / len(samples)))
        uncovered &= ~winners[:, pick]
    return np.asarray(selected), {"nonunique_winner_draws": int(np.sum(winners.sum(axis=1) > 1)),
                                 "unconditional_incremental_coverage": gain}


def posterior_orders(ids, mean, covariance, observation_sd, seeds, draws=8192, max_batch=20, ranking_mean=None):
    mean = np.asarray(mean, dtype=float)
    ranking_mean = mean if ranking_mean is None else np.asarray(ranking_mean, dtype=float)
    observation_sd = np.asarray(observation_sd, dtype=float)
    adjusted, factor, diagnostic = posterior_factor(mean, covariance)
    noise = observation_sd ** 2 - np.diag(covariance)
    tol = diagnostic["covariance_tolerance"]
    if not np.isfinite(noise).all() or np.any(observation_sd < 0) or np.min(noise) < -tol:
        raise ValueError("invalid observation variance")
    noise = np.maximum(noise, 0.)
    all_orders, details = {}, {}
    for seed in seeds:
        # Independent streams; same latent draws for qPO/pTop10 and f/y sensitivity.
        f_rng = np.random.default_rng(np.random.SeedSequence([20261011, seed, 1]))
        e_rng = np.random.default_rng(np.random.SeedSequence([20261011, seed, 2]))
        latent = adjusted + f_rng.standard_normal((draws, factor.shape[1])) @ factor.T
        observed = latent + e_rng.standard_normal(latent.shape) * np.sqrt(noise)
        by_method, by_detail = {}, {}
        for suffix, samples in (("latent", latent), ("observation", observed)):
            qorder, qdiag = qpo_order(samples, ranking_mean, ids, max_batch)
            probabilities = fractional_top_membership(samples, 10).mean(axis=0)
            by_method["qPO_" + suffix] = qorder
            by_method["pTop10_" + suffix] = rank(probabilities, ids, ranking_mean)[:max_batch]
            by_detail[suffix] = {**qdiag, "top10_probability_sum": float(probabilities.sum()),
                "top10_probabilities": probabilities.tolist()}
        all_orders[seed], details[seed] = by_method, by_detail
    return all_orders, {"factorization": diagnostic, "seeds": details,
                        "noise_variance_min": float(noise.min()), "noise_variance_max": float(noise.max())}
