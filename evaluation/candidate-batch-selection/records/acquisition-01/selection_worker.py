"""Label-blind bounded worker. Called once per task; no automatic retries."""
import os
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "2"
import argparse
import resource
import sys
import time
from pathlib import Path
import numpy as np
from acquisition import rank, posterior_orders
from common import load, save, sha


def deny_gold_and_network(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fsdecode(args[0])
        if "evaluation-only" in path or "test-gold" in path or "scored-results" in path:
            raise PermissionError("Selection worker cannot read evaluation labels")
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise PermissionError("Selection worker cannot use network")


def row(task, method, seed, batch, indices, ids):
    return {"task": task, "method": method, "seed": seed, "batch": batch,
            "status": "completed", "selected_ids": [ids[int(i)] for i in indices[:batch]],
            "fallback_selected_ids": [], "failure": None}


def work(packet, out, seeds, batches, draws):
    ids, task = packet["candidate_ids"], packet["task"]
    gp_order = rank(packet["gp_mean"], ids)
    rf_order = rank(packet["rf_mean"], ids)
    if len(ids) < max(batches) or len(set(ids)) != len(ids):
        raise ValueError("pool insufficient or duplicated")
    base = []
    for seed in seeds:
        orders = {"gp_mean": gp_order, "rf_mean": rf_order,
                  "random": np.random.default_rng(np.random.SeedSequence([20261011, seed, 3])).permutation(len(ids))}
        if packet["selected_policy_arm"] != "abstain":
            orders["original_policy"] = gp_order if packet["selected_policy_arm"] == "gp" else rf_order
        for method, order in orders.items():
            base.extend(row(task, method, seed, b, order, ids) for b in batches)
    save(out / "baseline.json", base)
    if sha(packet["posterior_path"]) != packet["posterior_sha256"]:
        raise ValueError("Posterior changed")
    with np.load(packet["posterior_path"], allow_pickle=False) as z:
        assert ids == z["candidate_ids"].tolist()
        mean, cov, obs = z["mean"], z["latent_covariance"], z["observation_sd"]
    # Factorization shared across seeds inside this call; no selection is refitted.
    orders, diagnostic = posterior_orders(ids, mean, cov, obs, seeds, draws, max(batches), packet["gp_mean"])
    save(out / "posterior-diagnostic.json", diagnostic)
    for seed in seeds:
        rows = [row(task, method, seed, b, order, ids)
                for method, order in orders[seed].items() for b in batches]
        save(out / (f"posterior-seed-{seed}.json"), rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--draws", type=int, default=8192)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU, (180, 181))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    sys.addaudithook(deny_gold_and_network)
    began = time.monotonic()
    try:
        work(load(args.packet), args.out, range(5), [5, 10, 20], args.draws)
    except Exception as error:
        save(args.out / "worker-error.json", {"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        save(args.out / "resource-usage.json", {"wall_seconds": time.monotonic() - began,
             "cpu_seconds": usage.ru_utime + usage.ru_stime, "peak_rss_kib_linux": usage.ru_maxrss,
             "memory_limit_bytes": 2 * 1024**3, "cpu_threads": 2})


if __name__ == "__main__":
    main()
