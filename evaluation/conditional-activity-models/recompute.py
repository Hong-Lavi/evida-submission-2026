"""Recalculate all declared metrics from saved predictions; never train a model.

The default archived run must reproduce the frozen numerical results. An explicit
--run accepts the output of the portable fitting script as a separate experiment.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys

import numpy as np

from verify_package import ROOT, require, sha, verify

METRICS = ["mae", "rmse", "spearman", "top10_recall", "best_true_activity_in_selected10"]
Z90 = 1.6448536269514722


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path, rows, empty_fields=None):
    require(bool(rows) or bool(empty_fields), "Empty table needs a declared schema")
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else empty_fields)
        writer.writeheader()
        writer.writerows(rows)


def compare(actual, expected, path="root"):
    """Numeric tolerance covers JSON/CSV round trips, not changed predictions."""
    if isinstance(expected, dict):
        require(set(actual) == set(expected), "Different fields: " + path)
        for key in expected:
            compare(actual[key], expected[key], path + "." + key)
    elif isinstance(expected, list):
        require(len(actual) == len(expected), "Different length: " + path)
        for index, (left, right) in enumerate(zip(actual, expected)):
            compare(left, right, path + "." + str(index))
    elif isinstance(expected, float):
        require(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12),
                "Numeric mismatch: " + path + ": " + repr((actual, expected)))
    else:
        require(actual == expected, "Value mismatch: " + path)


def calculate(run: Path, archived: bool):
    verification = verify()
    protocol = json.loads((ROOT / "protocol.json").read_text())
    scorer = load_module("frozen_metric_definitions", ROOT / "frozen-source/score_comparison.py")
    native = load_module("native_rank_definition", ROOT / "frozen-product/evida/activity_model.py")
    seal = json.loads((run / "sealed-predictions.json").read_text())
    expected_protocol = protocol["original_protocol_sha256"] if archived else sha(ROOT / "protocol.json")
    require(seal["protocol_sha256"] == expected_protocol, "Run uses a different protocol")
    require(seal["test_gold_read"] is False, "Prediction seal did not record label separation")
    require([r["task"] for r in seal["tasks"]] == protocol["order"], "Missing or reordered task receipts")
    measured, failures, export_rows = [], [], []
    for receipt, task in zip(seal["tasks"], protocol["tasks"]):
        name = task["task"]
        require(json.loads((run / name / "receipt.json").read_text()) == receipt, "Receipt/seal mismatch: " + name)
        require(receipt["status"] in ("completed", "failed", "timeout"), "Task is not terminal")
        prediction_path = run / name / "predictions.json"
        if receipt.get("prediction_sha256"):
            require(sha(prediction_path) == receipt["prediction_sha256"], "Prediction seal mismatch: " + name)
        else:
            require(not prediction_path.exists(), "Unsealed predictions: " + name)
        if receipt["status"] != "completed":
            failures.append(receipt)
            continue
        require(receipt["returncode"] == 0 and bool(receipt.get("prediction_sha256")), "Invalid completion")
        pred = json.loads(prediction_path.read_text())
        require(pred["test_gold_read"] is False, "Task did not record label separation")
        gold_rows = json.loads((ROOT / protocol["data"] / name / "evaluation-only/test-gold.json").read_text())
        gold = {r["candidate_id"]: r for r in gold_rows}
        ids = [r["candidate_id"] for r in pred["rows"]]
        require(len(ids) == len(set(ids)) == len(gold) == len(gold_rows) == task["official_test"], "Row count/identity mismatch")
        require(set(ids) == set(gold), "Gold and prediction identities differ")
        y = np.asarray([gold[i]["p_activity"] for i in ids])
        rf = np.asarray([r["rf_prediction"] for r in pred["rows"]])
        gp = np.asarray([r["gp_prediction"] for r in pred["rows"]])
        std = np.asarray([r["gp_observation_std"] for r in pred["rows"]])
        require(all(np.isfinite(a).all() for a in (y, rf, gp, std)) and np.all(std >= 0), "Nonfinite or invalid values")
        policy = pred["selected_policy_arm"]
        require(policy in ("rf", "gp", "abstain"), "Unknown selection policy")
        candidates = [(pred["native_rf"]["inner_mae"], 0, "rf")] if pred["native_rf"]["usable"] else []
        if pred["author_gp"]["usable"]:
            candidates.append((pred["author_gp"]["inner_mae"], 1, "gp"))
        require(policy == (min(candidates)[2] if candidates else "abstain"), "Policy is not the recorded inner-only selection")
        policy_pred = rf if policy == "rf" else gp if policy == "gp" else None
        m = {"task": name, "n": len(y),
             "rf": scorer.metrics(y, rf, ids, native._spearman),
             "gp": scorer.metrics(y, gp, ids, native._spearman),
             "training_mean": scorer.metrics(y, np.full_like(y, pred["training_mean"]), ids, native._spearman),
             "rf_usable": pred["native_rf"]["usable"], "gp_usable": pred["author_gp"]["usable"],
             "selected_policy_arm": policy,
             "policy": scorer.metrics(y, policy_pred, ids, native._spearman) if policy_pred is not None else None,
             "gp_90pct_predictive_coverage": float(np.mean(np.abs(y - gp) <= Z90 * std)),
             "gp_90pct_predictive_mean_width": float(np.mean(2 * Z90 * std)),
             "gp_optimizer": pred["author_gp"]["optimization"], "seconds": receipt["seconds"]}
        measured.append(m)
        for i, row in enumerate(pred["rows"]):
            export_rows.append({"task": name, "target_cluster": name.split("_")[0],
                                "candidate_id": ids[i], "gold_p_activity": float(y[i]),
                                "rf_prediction": float(rf[i]), "gp_prediction": float(gp[i]),
                                "training_mean_prediction": pred["training_mean"],
                                "policy_arm": policy, "policy_prediction": float(policy_pred[i]) if policy_pred is not None else "",
                                "gp_latent_std": row["gp_latent_std"], "gp_observation_std": float(std[i]),
                                "cliff_mol": gold[ids[i]]["cliff_mol"]})
    policy_rows = [r for r in measured if r["rf_usable"] and r["policy"] is not None]
    summary = {
        "planned_tasks": len(protocol["tasks"]), "completed_pairs": len(measured), "failures": failures,
        "completed_test_rows": sum(r["n"] for r in measured),
        "raw_backbone_task_macro": {a: {m: float(np.mean([r[a][m] for r in measured])) for m in METRICS}
                                    for a in ("rf", "gp", "training_mean")} if measured else {},
        "paired_gp_minus_rf": {m: scorer.cluster_interval(measured, "gp", "rf", m, protocol) for m in METRICS},
        "operational_coverage": {"rf_usable": sum(r["rf_usable"] for r in measured),
                                 "gp_usable": sum(r["gp_usable"] for r in measured),
                                 "inner_policy": dict(Counter(r["selected_policy_arm"] for r in measured))},
        "policy_comparison_on_rf_usable_tasks": {m: scorer.cluster_interval(policy_rows, "policy", "rf", m, protocol) for m in METRICS},
        "uncertainty_diagnostic": {"task_macro_90pct_coverage": float(np.mean([r["gp_90pct_predictive_coverage"] for r in measured])) if measured else None,
                                   "task_macro_interval_width": float(np.mean([r["gp_90pct_predictive_mean_width"] for r in measured])) if measured else None},
        "tasks": measured}
    if archived:
        frozen = json.loads((run / "scored-results.json").read_text())
        compare(summary, {k: frozen[k] for k in summary})
        supplement = json.loads((run / "scored-results-v2.json").read_text())
        compare(summary["paired_gp_minus_rf"], supplement["primary_v1_unchanged"])
        compare(summary["raw_backbone_task_macro"]["rf"], supplement["rf_all_planned"]["task_macro_metrics_on_available"])
        compare(supplement["denominators"], {"planned_tasks": 30, "v1_successful_pairs": 30,
                                             "v1_excluded_task_ids": [], "rf_prediction_available": 30})
        with (ROOT / "results/row-predictions.csv").open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        require(len(existing) == len(export_rows), "Published CSV denominator mismatch")
        for expected, actual in zip(export_rows, existing):
            require(set(expected) == set(actual), "Published CSV fields mismatch")
            for key, value in expected.items():
                if isinstance(value, (float, int)):
                    compare(float(actual[key]), float(value), "CSV." + key)
                else:
                    require(actual[key] == value, "Published CSV value mismatch: " + key)
        verification["frozen_results_reproduced"] = True
        verification["row_csv_reconciled"] = True
    summary["policy_task_macro_on_selected"] = {m: float(np.mean([r["policy"][m] for r in policy_rows])) for m in METRICS} if policy_rows else {}
    summary["policy_comparison_denominator"] = len(policy_rows)
    summary["bootstrap"] = {"unit": "target_cluster", "clusters": len({t["task"].split("_")[0] for t in protocol["tasks"]}),
                            "repetitions": protocol["bootstrap_repetitions"], "seed": protocol["bootstrap_seed"],
                            "interval": "percentile, 95%, unadjusted for multiple metrics"}
    summary["verification"] = verification
    summary["numpy_version"] = np.__version__
    summary["python_version"] = platform.python_version()
    return summary, export_rows


def tables(summary):
    per_task = []
    for task in summary["tasks"]:
        row = {"task": task["task"], "target_cluster": task["task"].split("_")[0], "test_rows": task["n"],
               "rf_usable": task["rf_usable"], "gp_usable": task["gp_usable"], "policy_arm": task["selected_policy_arm"]}
        for arm in ("rf", "gp", "training_mean", "policy"):
            for metric in METRICS:
                row[arm + "_" + metric] = task[arm][metric] if task[arm] else ""
        row.update({k: task[k] for k in ("gp_90pct_predictive_coverage", "gp_90pct_predictive_mean_width", "seconds")})
        row["gp_optimizer_converged"] = task["gp_optimizer"]["converged"]
        per_task.append(row)
    paired = []
    for comparison, field in [("gp_minus_rf", "paired_gp_minus_rf"), ("policy_minus_rf", "policy_comparison_on_rf_usable_tasks")]:
        for metric in METRICS:
            result = summary[field][metric]
            if result is not None:
                paired.append({"comparison": comparison, "metric": metric,
                               "favorable_difference": "negative" if metric in ("mae", "rmse") else "positive",
                               **{k: result[k] for k in ("mean_difference", "tasks", "target_clusters", "negative", "positive", "ties")},
                               "ci95_lower": result["ci95"][0], "ci95_upper": result["ci95"][1]})
    return per_task, paired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, help="Separate portable fitting output; default is the archived run")
    parser.add_argument("--output", type=Path, required=True, help="New output directory; refuses overwrite")
    args = parser.parse_args()
    run = args.run.resolve() if args.run else ROOT / "run-01"
    archived = run == ROOT / "run-01"
    require(not args.output.exists(), "Output directory already exists")
    summary, rows = calculate(run, archived)
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "summary.json", summary)
    per_task, paired = tables(summary)
    for filename, records in [("per-task.csv", per_task), ("paired-ci.csv", paired), ("row-predictions.csv", rows)]:
        with (ROOT / "results" / filename).open(newline="") as stream:
            fields = next(csv.reader(stream))
        write_csv(args.output / filename, records, fields)
    print(json.dumps({"status": "PASS", "archived_results_reproduced": archived,
                      "planned_tasks": summary["planned_tasks"], "completed_pairs": summary["completed_pairs"],
                      "test_rows": summary["completed_test_rows"], "model_fits": 0,
                      "model_provider_calls": 0, "network_calls": 0, "gpu_used": False}))


if __name__ == "__main__":
    main()
