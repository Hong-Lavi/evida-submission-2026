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


def complete_rows(protocol, packet, partial, failure):
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
                "status": "failed", "selected_ids": [], "failure": failure or "policy_abstained",
                "fallback_selected_ids": [packet["candidate_ids"][int(i)] for i in gp[:batch]]
                    if method.startswith(("qPO_", "pTop10_")) else []})
    return rows


def main():
    protocol = frozen_protocol()
    output = HERE / "run-01"
    output.mkdir(exist_ok=False)
    save(output / "started.json", {"at": utc(), "protocol_sha256": sha(HERE / "protocol.json"),
                                    "planned_selection_rows": 3600, "gold_read": False})
    receipts = []
    env = dict(os.environ, OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2")
    for task in protocol["tasks"]:
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
        partial = []
        for path in [out / "baseline.json", *[out / f"posterior-seed-{s}.json" for s in protocol["seeds"]]]:
            if path.exists():
                partial.extend(load(path))
        rows = complete_rows(protocol, load(task["packet"]), partial, failure)
        selection = out / "selections.json"
        save(selection, rows)
        completed = sum(r["status"] == "completed" for r in rows)
        receipt = {"task": task["task"], "status": "completed" if completed == len(rows) else "partial" if completed else "failed",
            "planned_rows": len(rows), "completed_rows": completed, "failure": failure,
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
