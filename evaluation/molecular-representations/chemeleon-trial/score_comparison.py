"""Score every frozen follow-up task and preserve failed cases and coverage."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import numpy as np
from run_comparison import load_protocol, sha, save, HERE


def metrics(y, pred, ids, spearman):
    truth_top = sorted(range(len(y)), key=lambda i: (-y[i], ids[i]))[:10]
    pred_top = sorted(range(len(y)), key=lambda i: (-pred[i], ids[i]))[:10]
    return {"mae": float(np.mean(np.abs(y - pred))), "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "spearman": spearman(y.tolist(), pred.tolist()),
        "top10_recall": len(set(truth_top) & set(pred_top)) / len(truth_top),
        "best_true_activity_in_selected10": float(max(y[i] for i in pred_top))}


def interval(rows, left, right, metric, p):
    paired = [r for r in rows if r.get(left) is not None and r.get(right) is not None]
    if not paired:
        return None
    groups = defaultdict(list)
    for r in paired:
        groups[r["task"].split("_")[0]].append(r[left][metric] - r[right][metric])
    names = sorted(groups)
    rng = np.random.default_rng(p["bootstrap_seed"])
    bootstrap = [np.mean([d for name in rng.choice(names, len(names), replace=True) for d in groups[name]]) for _ in range(p["bootstrap_repetitions"])]
    differences = [r[left][metric] - r[right][metric] for r in paired]
    return {"mean_difference": float(np.mean(differences)), "ci95": np.quantile(bootstrap, [.025, .975]).tolist(),
        "tasks": len(paired), "target_clusters": len(names), "negative": sum(d < 0 for d in differences),
        "positive": sum(d > 0 for d in differences), "ties": sum(d == 0 for d in differences)}


def main():
    p = load_protocol()
    run = HERE / "run-01"
    seal = json.loads((run / "sealed-predictions.json").read_text())
    assert seal["protocol_sha256"] == sha(HERE / "protocol.json")
    assert [r["task"] for r in seal["tasks"]] == p["order"]
    for r in seal["tasks"]:
        assert r["status"] in {"completed", "failed", "timeout"}
        if r["prediction_sha256"]:
            assert sha(run / r["task"] / "predictions.json") == r["prediction_sha256"]
    sys.path.insert(0, p["frozen_product"])
    from evida.activity_model import _spearman
    rows, failures = [], []
    for receipt, task in zip(seal["tasks"], p["tasks"]):
        completed = receipt["status"] == "completed"
        if not completed:
            failures.append(receipt)
        pred_path = run / task["task"] / "predictions.json" if completed else Path(p["gp_run"]) / task["task"] / "predictions.json"
        if not completed:
            assert sha(pred_path) == p["gp_prediction_pins"][task["task"]]
        pred = json.loads(pred_path.read_text())
        path = Path(p["data"]) / task["task"] / "evaluation-only/test-gold.json"
        assert sha(path) == task["gold_sha256"]
        raw = json.loads(path.read_text())
        gold = {r["candidate_id"]: r["p_activity"] for r in raw}
        ids = [r["candidate_id"] for r in pred["rows"]]
        assert len(ids) == len(set(ids)) == len(raw) == task["official_test"]
        assert set(ids) == set(gold)
        y = np.asarray([gold[i] for i in ids], dtype=float)
        row = {"task": task["task"], "n": len(y), "seconds": receipt["seconds"], "chemeleon_completed": completed,
               "selected_policy_arm": pred["selected_policy_arm"], "prior_policy_arm": pred.get("prior_policy_arm", pred["selected_policy_arm"]),
               "policy_fallback_to_previous_on_technical_failure": not completed}
        for arm, key in [("rf", "native_rf"), ("gp", "author_gp"), ("chemeleon_rf", "chemeleon_rf")]:
            if arm == "chemeleon_rf" and not completed:
                row[arm], row[arm + "_usable"] = None, False
                continue
            values = np.asarray([r[arm + "_prediction"] for r in pred["rows"]], dtype=float)
            assert np.isfinite(values).all()
            row[arm] = metrics(y, values, ids, _spearman)
            row[arm + "_usable"] = pred[key]["usable"]
        row["policy"] = row.get(row["selected_policy_arm"])
        row["prior_policy"] = row.get(row["prior_policy_arm"])
        rows.append(row)
    names = ["mae", "rmse", "spearman", "top10_recall", "best_true_activity_in_selected10"]
    result = {"at_utc": datetime.now(timezone.utc).isoformat(), "status": "SCORED_FIXED_FOLLOWUP",
        "protocol_sha256": sha(HERE / "protocol.json"), "sealed_predictions_sha256": sha(run / "sealed-predictions.json"),
        "planned_tasks": len(p["tasks"]), "completed_pairs": sum(r["chemeleon_completed"] for r in rows),
        "completed_test_rows": sum(r["n"] for r in rows if r["chemeleon_completed"]),
        "baseline_tasks": len(rows), "baseline_test_rows": sum(r["n"] for r in rows),
        "failures": failures, "chronology": p["chronology"],
        "task_macro": {a: {m: float(np.mean([r[a][m] for r in rows if r[a] is not None]))
                            if any(r[a] is not None for r in rows) else None for m in names}
                       for a in ["rf", "gp", "chemeleon_rf"]} if rows else {},
        "macro_task_denominators": {a: sum(r[a] is not None for r in rows) for a in ["rf", "gp", "chemeleon_rf"]},
        "paired": {a + "_minus_" + b: {m: interval(rows, a, b, m, p) for m in names}
                   for a, b in [("chemeleon_rf", "rf"), ("chemeleon_rf", "gp"), ("policy", "prior_policy"), ("policy", "rf")]},
        "operational_coverage": {a: sum(r[a + "_usable"] for r in rows) for a in ["rf", "gp", "chemeleon_rf"]},
        "policy_selection": dict(Counter(r["selected_policy_arm"] for r in rows)), "tasks": rows,
        "gpu_used": False, "provider_calls": 0, "scope": p["scope"]}
    save(run / "scored-results.json", result)
    print(json.dumps({k: result[k] for k in ["planned_tasks", "completed_pairs", "completed_test_rows", "task_macro", "operational_coverage", "policy_selection"]}))


if __name__ == "__main__":
    main()
