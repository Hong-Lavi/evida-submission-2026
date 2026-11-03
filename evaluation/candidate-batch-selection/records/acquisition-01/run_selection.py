"""Run only after root-reviewed freeze; create full task and method denominators."""
import itertools
import os
from pathlib import Path
import subprocess
import sys
import time
from acquisition import rank
from common import HERE, frozen_protocol, load, save, sha, utc, verify_pins


def expected_keys(protocol, task=None):
    tasks = [task] if task else [t["task"] for t in protocol["tasks"]]
    return list(itertools.product(tasks, protocol["methods"], protocol["seeds"], protocol["batches"]))


def key(row):
    return row["task"], row["method"], row["seed"], row["batch"]


def complete_rows(protocol, packet, partial, failure, row_failures=None):
    existing = {}
    for r in partial:
        if key(r) in existing:
            raise ValueError("Duplicate worker row")
        existing[key(r)] = r
    expected = expected_keys(protocol, packet["task"])
    if set(existing) - set(expected):
        raise ValueError("Unexpected worker rows")
    gp = rank(packet["gp_mean"], packet["candidate_ids"])
    rows = []
    for k in expected:
        if k in existing:
            rows.append(existing[k])
        else:
            task, method, seed, batch = k
            rows.append({"task": task, "method": method, "seed": seed, "batch": batch,
                "status": "failed", "selected_ids": [],
                "failure": (row_failures or {}).get(k) or failure or "policy_abstained",
                "fallback_selected_ids": [packet["candidate_ids"][int(i)] for i in gp[:batch]]
                    if method.startswith(("qPO_", "pTop10_")) else []})
    return rows


def collect_worker_rows(protocol, packet, out, worker_failure):
    """Accept a complete valid artifact or fail its declared rows; never repair bytes."""
    task = packet["task"]
    expected = expected_keys(protocol, task)
    baseline = [k for k in expected if not k[1].startswith(("qPO_", "pTop10_"))
                and not (k[1] == "original_policy" and packet["selected_policy_arm"] == "abstain")]
    artifacts = [(out / "baseline.json", baseline)]
    artifacts.extend((out / f"posterior-seed-{seed}.json",
                      [k for k in expected if k[2] == seed and k[1].startswith(("qPO_", "pTop10_"))])
                     for seed in protocol["seeds"])
    partial, errors, row_failures = [], [], {}
    pool = set(packet["candidate_ids"])
    for path, scope in artifacts:
        if not scope:
            continue
        try:
            rows = load(path)
            if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                raise ValueError("Worker artifact must be a list of row objects")
            fields = {"task", "method", "seed", "batch", "status", "selected_ids", "fallback_selected_ids", "failure"}
            if any(set(r) != fields or type(r["seed"]) is not int or type(r["batch"]) is not int
                   or not isinstance(r["task"], str) or not isinstance(r["method"], str) for r in rows):
                raise ValueError("Worker row fields or scalar types differ from contract")
            keys = [key(r) for r in rows]
            if len(keys) != len(set(keys)) or set(keys) != set(scope):
                raise ValueError("Worker artifact row scope is missing, duplicated, or unexpected")
            for r in rows:
                selected = r["selected_ids"]
                if (r["status"] != "completed" or r["failure"] is not None or
                        r["fallback_selected_ids"] != [] or not isinstance(selected, list) or
                        any(not isinstance(i, str) for i in selected) or
                        len(selected) != r["batch"] or len(set(selected)) != len(selected) or
                        not set(selected).issubset(pool)):
                    raise ValueError("Invalid worker row status, identity, or batch size")
            partial.extend(rows)
        except (ValueError, TypeError, KeyError, FileNotFoundError) as error:
            # Include the untouched truncated/invalid bytes in the final artifact seal.
            detail = {"artifact": path.name, "error_type": type(error).__name__,
                      "message": str(error), "original_sha256": sha(path) if path.exists() else None,
                      "affected_rows": [list(k) for k in scope]}
            errors.append(detail)
            reason = (worker_failure + "; " if worker_failure else "") + "invalid_worker_artifact:" + path.name + ":" + type(error).__name__
            row_failures.update({k: reason for k in scope})
    return partial, errors, row_failures


def main():
    protocol = frozen_protocol()
    output = HERE / "run-01"
    output.mkdir(exist_ok=False)
    save(output / "started.json", {"at": utc(), "protocol_sha256": sha(HERE / "protocol.json"),
                                    "planned_selection_rows": 3600, "gold_read": False})
    receipts = []
    env = dict(os.environ, OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2")
    for task in protocol["tasks"]:
        # Source/input integrity violations remain fatal and never become method failures.
        verify_pins(protocol["source_pins"])
        verify_pins(protocol["input_pins"])
        out = output / task["task"]
        out.mkdir()
        began = time.monotonic()
        failure = None
        with (out / "stdout.txt").open("wb") as stdout, (out / "stderr.txt").open("wb") as stderr:
            try:
                result = subprocess.run([sys.executable, "-B", str(HERE / "selection_worker.py"),
                    task["packet"], str(out), "--draws", str(protocol["mc_draws"])],
                    stdout=stdout, stderr=stderr, env=env, timeout=protocol["task_timeout_seconds"])
                if result.returncode:
                    failure = "worker_exit_" + str(result.returncode)
            except subprocess.TimeoutExpired:
                failure = "timeout"
        verify_pins(protocol["source_pins"])
        verify_pins(protocol["input_pins"])
        packet = load(task["packet"])
        partial, artifact_errors, row_failures = collect_worker_rows(protocol, packet, out, failure)
        rows = complete_rows(protocol, packet, partial, failure, row_failures)
        selection = out / "selections.json"
        save(selection, rows)
        completed = sum(r["status"] == "completed" for r in rows)
        receipt = {"task": task["task"], "status": "completed" if completed == len(rows) else "partial" if completed else "failed",
            "planned_rows": len(rows), "completed_rows": completed,
            "failure": failure or ("invalid_worker_artifact" if artifact_errors else None),
            "worker_failure": failure, "artifact_errors": artifact_errors,
            "seconds": time.monotonic() - began, "selection_sha256": sha(selection),
            "packet_sha256": sha(task["packet"]),
            "artifact_pins": {p.name: sha(p) for p in out.iterdir() if p.is_file()}}
        save(out / "receipt.json", receipt)
        receipts.append({"task": task["task"], "receipt_sha256": sha(out / "receipt.json"), **receipt})
        print({"task": task["task"], "status": receipt["status"], "rows": completed}, flush=True)
    verify_pins(protocol["source_pins"])
    verify_pins(protocol["input_pins"])
    save(output / "selection-seal.json", {"at": utc(), "protocol_sha256": sha(HERE / "protocol.json"),
         "tasks": receipts, "gold_read": False, "planned_tasks": 30, "planned_rows": 3600})


if __name__ == "__main__":
    main()
