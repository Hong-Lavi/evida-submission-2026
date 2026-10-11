"""Exploratory replay scorer: full structural gate precedes any gold read."""
from collections import Counter, defaultdict
import numpy as np
from acquisition import fractional_top_membership
from common import HERE, load, save, sha, frozen_protocol, verify_pins, utc
from run_selection import expected_keys, key

METRICS = ("id_top10_recall", "fractional_top10_recall", "best_any_capture",
           "best_id_capture", "fractional_best_capture", "best_activity", "simple_regret", "mean_activity")


def selection_metrics(y, ids, selected):
    y = np.asarray(y, dtype=float)
    if not np.isfinite(y).all() or len(y) != len(ids) or not selected:
        raise ValueError("invalid metric input")
    index = {name: i for i, name in enumerate(ids)}
    picked = [index[name] for name in selected]
    true_order = sorted(range(len(y)), key=lambda i: (-y[i], ids[i]))
    k = min(10, len(y))
    top = set(true_order[:k])
    fractional = fractional_top_membership(y[None, :], k)[0]
    best = y == y.max()
    value = float(y[picked].max())
    return {"id_top10_recall": len(top.intersection(picked)) / k,
            "fractional_top10_recall": float(fractional[picked].sum() / k),
            "best_any_capture": int(best[picked].any()),
            "best_id_capture": int(true_order[0] in picked),
            "fractional_best_capture": float(best[picked].sum() / best.sum()),
            "best_activity": value, "simple_regret": float(y.max() - value),
            "mean_activity": float(y[picked].mean())}


def gate(protocol, output, protocol_sha):
    verify_pins(protocol["source_pins"])
    verify_pins(protocol["input_pins"])
    seal = load(output / "selection-seal.json")
    if seal["protocol_sha256"] != protocol_sha or seal["gold_read"] is not False:
        raise ValueError("Bad selection seal")
    task_names = [t["task"] for t in protocol["tasks"]]
    if [r["task"] for r in seal["tasks"]] != task_names:
        raise ValueError("Incomplete or reordered terminal tasks")
    all_rows = []
    # Every late-task receipt and byte hash is verified before parsing selections.
    for terminal in seal["tasks"]:
        directory = output / terminal["task"]
        receipt_path = directory / "receipt.json"
        if sha(receipt_path) != terminal["receipt_sha256"]:
            raise ValueError("Receipt changed")
        receipt = load(receipt_path)
        if receipt != {k: v for k, v in terminal.items() if k != "receipt_sha256"}:
            raise ValueError("Terminal/per-task disagreement")
        verify_pins({str(directory / k): v for k, v in receipt["artifact_pins"].items()})
        if sha(directory / "selections.json") != receipt["selection_sha256"]:
            raise ValueError("Selection changed")
    for task, terminal in zip(protocol["tasks"], seal["tasks"]):
        packet = load(task["packet"])
        ids = packet["candidate_ids"]
        if len(ids) != len(set(ids)) or len(ids) != task["n"]:
            raise ValueError("Invalid pool identity")
        if not np.isfinite(packet["gp_mean"]).all() or not np.isfinite(packet["rf_mean"]).all():
            raise ValueError("Nonfinite baseline values")
        if sha(task["packet"]) != terminal["packet_sha256"]:
            raise ValueError("Packet/receipt disagreement")
        rows = load(output / task["task"] / "selections.json")
        if [key(r) for r in rows] != expected_keys(protocol, task["task"]):
            raise ValueError("Missing/duplicate/reordered selection rows")
        for row in rows:
            if row["status"] not in ("completed", "failed"):
                raise ValueError("Nonterminal row")
            for field in ("selected_ids", "fallback_selected_ids"):
                values = row[field]
                if len(values) != len(set(values)) or not set(values).issubset(ids):
                    raise ValueError("Invalid selected identity")
                if values and len(values) != row["batch"]:
                    raise ValueError("Invalid batch size")
            if row["status"] == "completed" and (not row["selected_ids"] or row["fallback_selected_ids"] or row["failure"]):
                raise ValueError("Invalid completed row")
            if row["status"] == "failed" and (row["selected_ids"] or not row["failure"]):
                raise ValueError("Invalid failure row")
            if row["fallback_selected_ids"] and not row["method"].startswith(("qPO_", "pTop10_")):
                raise ValueError("Unexpected fallback")
        completed = sum(r["status"] == "completed" for r in rows)
        expected_status = "completed" if completed == len(rows) else "partial" if completed else "failed"
        if terminal["planned_rows"] != len(rows) or terminal["completed_rows"] != completed or terminal["status"] != expected_status:
            raise ValueError("Receipt coverage disagreement")
        all_rows.extend(rows)
    if len(all_rows) != protocol["planned_selection_rows"] or [key(r) for r in all_rows] != expected_keys(protocol):
        raise ValueError("Full denominator mismatch")
    return all_rows


def score_after_gate(protocol, output, protocol_sha, gold_loader=load):
    rows = gate(protocol, output, protocol_sha)
    # No gold bytes, hash, or parser access occurs above this line.
    opened_at = utc()
    gold = {}
    for task in protocol["tasks"]:
        if sha(task["gold_path"]) != task["gold_sha256"]:
            raise ValueError("Gold changed")
    for task in protocol["tasks"]:
        packet = load(task["packet"])
        records = gold_loader(task["gold_path"])
        mapping = {r["candidate_id"]: r["p_activity"] for r in records}
        if len(records) != len(mapping) or set(mapping) != set(packet["candidate_ids"]):
            raise ValueError("Gold identity mismatch")
        y = np.asarray([mapping[i] for i in packet["candidate_ids"]], dtype=float)
        if not np.isfinite(y).all():
            raise ValueError("Nonfinite gold")
        gold[task["task"]] = (y, packet["candidate_ids"])
    scored = []
    for row in rows:
        y, ids = gold[row["task"]]
        raw = selection_metrics(y, ids, row["selected_ids"]) if row["status"] == "completed" else None
        fallback = selection_metrics(y, ids, row["fallback_selected_ids"]) if row["fallback_selected_ids"] else None
        scored.append({**row, "raw_metrics": raw, "fallback_metrics": fallback,
            "operational_zero_hit_metrics": raw if raw else {m: 0. if "recall" in m or "capture" in m else None for m in METRICS}})
    return scored, opened_at


def aggregate(rows, protocol):
    task_means, summary = {}, []
    for method in protocol["methods"]:
        for batch in protocol["batches"]:
            subset = [r for r in rows if r["method"] == method and r["batch"] == batch]
            by_task = defaultdict(list)
            for r in subset:
                by_task[r["task"]].append(r)
            modes = {}
            for mode in ("raw", "fallback_policy", "operational_zero_hit"):
                completed = {}
                for task, task_rows in by_task.items():
                    metrics = [(r["raw_metrics"] if mode == "raw" else
                                r["raw_metrics"] or r["fallback_metrics"] if mode == "fallback_policy" else
                                r["operational_zero_hit_metrics"]) for r in task_rows]
                    if len(metrics) == len(protocol["seeds"]) and all(m is not None for m in metrics):
                        completed[task] = {name: float(np.mean([m[name] for m in metrics]))
                                           if all(m[name] is not None for m in metrics) else None for name in METRICS}
                task_means[(method, batch, mode)] = completed
                modes[mode] = {"tasks": len(completed), "metric_task_counts": {
                    name: sum(v[name] is not None for v in completed.values()) for name in METRICS},
                    "task_macro": {name: float(np.mean([v[name] for v in completed.values() if v[name] is not None]))
                                   if any(v[name] is not None for v in completed.values()) else None for name in METRICS}}
            summary.append({"method": method, "batch": batch, "planned_rows": len(subset),
                "completed_rows": sum(r["status"] == "completed" for r in subset),
                "failed_rows": sum(r["status"] == "failed" for r in subset),
                "fallback_rows": sum(bool(r["fallback_selected_ids"]) for r in subset), "modes": modes})
    comparisons = []
    for mode in ("raw", "fallback_policy", "operational_zero_hit"):
        for left in protocol["methods"]:
            for right in ("gp_mean", "original_policy"):
                if left == right:
                    continue
                for batch in protocol["batches"]:
                    a, b = task_means[(left, batch, mode)], task_means[(right, batch, mode)]
                    for metric in METRICS:
                        tasks = sorted(t for t in set(a).intersection(b) if a[t][metric] is not None and b[t][metric] is not None)
                        groups = defaultdict(list)
                        for task in tasks:
                            groups[task.split("_")[0]].append(a[task][metric] - b[task][metric])
                        if groups:
                            names = sorted(groups)
                            sums = np.asarray([sum(groups[n]) for n in names])
                            counts = np.asarray([len(groups[n]) for n in names])
                            rng = np.random.default_rng(protocol["bootstrap_seed"])
                            indices = rng.integers(len(names), size=(protocol["bootstrap_repetitions"], len(names)))
                            boot = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
                            delta = float(sums.sum() / counts.sum())
                            interval = np.quantile(boot, [.025, .975]).tolist()
                        else:
                            delta, interval = None, None
                        comparisons.append({"left": left, "right": right, "batch": batch, "metric": metric,
                            "mode": mode, "tasks": len(tasks), "target_clusters": len(groups),
                            "mean_difference": delta, "cluster_ci95": interval,
                            "primary": left == "pTop10_latent" and batch == 10 and metric == "id_top10_recall" and mode == "raw"})
    return {"summary": summary, "comparisons": comparisons}


def main():
    protocol = frozen_protocol()
    output = HERE / "run-01"
    rows, opened_at = score_after_gate(protocol, output, sha(HERE / "protocol.json"))
    result = {"gold_opened_at": opened_at, "exploratory_previously_inspected_labels": True,
              "protocol_sha256": sha(HERE / "protocol.json"), "selection_seal_sha256": sha(output / "selection-seal.json"),
              "planned_tasks": 30, "planned_targets": 29, "planned_candidate_rows": 9802,
              "planned_selection_rows": 3600, "rows": rows, **aggregate(rows, protocol)}
    save(output / "scored-results.json", result)
    print({"rows": len(rows), "completed": sum(r["status"] == "completed" for r in rows)})


if __name__ == "__main__":
    main()
