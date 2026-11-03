"""Prepare a reviewable draft and label-free packets, without selecting candidates."""
from collections import Counter
import importlib.metadata
from pathlib import Path
import sys
import numpy as np
from common import HERE, BASE, load, save, sha, verify_pins, utc
from acquisition import METHODS


def refresh_draft(revision_name):
    """Refresh reviewed-prototype pins without parsing any real candidate data."""
    if (HERE / "protocol.json").exists() or (HERE / "run-01").exists():
        raise ValueError("Cannot revise a frozen or executed protocol")
    revision = (HERE / revision_name).resolve()
    revision.relative_to(HERE.resolve())
    revision.mkdir(exist_ok=True)
    draft_path = HERE / "protocol-draft.json"
    previous_bytes = draft_path.read_bytes()
    previous_hash = sha(draft_path)
    previous = load(draft_path)
    # Byte hashes only: no NPZ/real prediction/features/gold parser is invoked.
    verify_pins(previous["input_pins"])
    with (revision / "previous-draft.json").open("xb") as handle:
        handle.write(previous_bytes)
    current = {**previous, "at": utc(),
        "source_pins": {str(p): sha(p) for p in HERE.glob("*.py")},
        "prototype_revision": {"previous_draft_sha256": previous_hash,
            "reason": "P2: recover artifact-level truncated/invalid worker outputs; preserve bytes and worker failure; keep every planned row/task; source/input integrity remains fail-closed",
            "real_candidate_values_parsed": False, "gold_read": False}}
    for p in revision.rglob("*"):
        if p.is_file():
            current["input_pins"][str(p)] = sha(p)
    updated = revision / "updated-draft.json"
    save(updated, current)
    # Prior exact bytes and update proposal both remain preserved.
    draft_path.write_bytes(updated.read_bytes())
    save(revision / "draft-refresh-receipt.json", {"at": utc(),
         "previous_sha256": previous_hash, "updated_sha256": sha(draft_path),
         "candidate_input_hashes_verified_only": True, "actual_candidate_values_parsed": False,
         "gold_read": False, "selection_started": False, "frozen": False})
    print({"draft_sha256": sha(draft_path), "source_pins": len(current["source_pins"]),
           "input_pins": len(current["input_pins"]), "frozen": False, "real_selection": False})


def main():
    oldbase = BASE / "tanimoto-trial"
    oldpath = oldbase / "protocol.json"
    old = load(oldpath)
    if sha(oldpath) != load(oldbase / "protocol-receipt.json")["sha256"]:
        raise ValueError("Original protocol changed")
    verify_pins({str(oldbase / k): v for k, v in old["source_pins"].items()})
    sealpath = oldbase / "run-01/sealed-predictions.json"
    seal = load(sealpath)
    assert seal["protocol_sha256"] == sha(oldpath)
    assert [r["task"] for r in seal["tasks"]] == old["order"]
    recon = HERE.parent / "reconstruction-01"
    summary = load(recon / "summary.json")
    assert [r["task"] for r in summary["rows"]] == old["order"]
    pins = {str(p): sha(p) for p in (oldpath, oldbase / "protocol-receipt.json", sealpath,
                                    recon / "summary.json", recon / "started.json")}
    pins.update({str(oldbase / k): v for k, v in old["source_pins"].items()})
    reconstruction_start = load(recon / "started.json")
    pins.update({str(BASE / k): v for k, v in reconstruction_start["code_pins"].items()})
    verify_pins(pins)
    # Full hash/receipt gate completes before parsing any prediction packet.
    for row, rr in zip(seal["tasks"], summary["rows"]):
        task = row["task"]
        pred = oldbase / "run-01" / task / "predictions.json"
        assert row["status"] == "completed" and row["prediction_sha256"]
        assert sha(pred) == row["prediction_sha256"] == rr["original_predictions_sha256"]
        receipt = recon / (task + ".receipt.json")
        npz = recon / (task + ".npz")
        assert load(receipt) == rr and rr["status"] == "PASS"
        assert sha(npz) == rr["joint_posterior_sha256"]
        for p in (pred, receipt, npz):
            pins[str(p)] = sha(p)
    packets = HERE / "inputs"
    packets.mkdir(exist_ok=False)
    tasks, policies = [], []
    for task_spec in old["tasks"]:
        task = task_spec["task"]
        predpath = oldbase / "run-01" / task / "predictions.json"
        pred = load(predpath)
        features = Path(old["data"]) / task / "test-features.json"
        assert sha(features) == task_spec["features_sha256"]
        features_data = load(features)
        ids = [r["candidate_id"] for r in pred["rows"]]
        assert len(ids) == len(set(ids)) == task_spec["official_test"]
        assert ids == [r["candidate_id"] for r in features_data]
        npzpath = recon / (task + ".npz")
        with np.load(npzpath, allow_pickle=False) as posterior:
            assert posterior["candidate_ids"].tolist() == ids
            for field in ("mean", "latent_covariance", "observation_sd"):
                assert np.isfinite(posterior[field]).all()
            assert np.max(np.abs(posterior["mean"] - [r["gp_prediction"] for r in pred["rows"]])) <= 1e-7
        policy = pred["selected_policy_arm"]
        assert policy in ("gp", "rf", "abstain")
        policies.append(policy)
        packet = {"task": task, "candidate_ids": ids,
                  "gp_mean": [r["gp_prediction"] for r in pred["rows"]],
                  "rf_mean": [r["rf_prediction"] for r in pred["rows"]],
                  "selected_policy_arm": policy, "posterior_path": str(npzpath),
                  "posterior_sha256": sha(npzpath), "prediction_sha256": sha(predpath)}
        assert np.isfinite(packet["gp_mean"]).all() and np.isfinite(packet["rf_mean"]).all()
        packetpath = packets / (task + ".json")
        save(packetpath, packet)
        pins[str(packetpath)] = sha(packetpath)
        pins[str(features)] = sha(features)
        tasks.append({"task": task, "target_cluster": task.split("_")[0],
                      "n": len(ids), "packet": str(packetpath),
                      "gold_path": str(Path(old["data"]) / task / "evaluation-only/test-gold.json"),
                      "gold_sha256": task_spec["gold_sha256"]})
    assert len(tasks) == 30 and len({r["target_cluster"] for r in tasks}) == 29
    assert sum(r["n"] for r in tasks) == 9802
    assert Counter(policies) == {"gp": 25, "rf": 5}
    source_pins = {str(p): sha(p) for p in HERE.glob("*.py")}
    for p in (HERE / "author-fetch-receipt.json", HERE / "author-fetch-attempt-02.json",
              HERE / "author-synthetic-result.json", HERE / "synthetic-worker/receipt.json",
              HERE / "synthetic-tests.stderr"):
        pins[str(p)] = sha(p)
    research = BASE.parents[1] / ".research-os/rounds/20261010-224145-evida-feasible-next-observations-and-out"
    for p in [research / "digest.md", *[research / "blind" / (f"R{i:02d}.md") for i in range(1, 5)]]:
        pins[str(p)] = sha(p)
    protocol = {"status": "DRAFT_AWAITING_ROOT_REVIEW", "at": utc(), "tasks": tasks,
        "methods": list(METHODS), "batches": [5, 10, 20], "seeds": list(range(5)),
        "mc_draws": 8192, "planned_tasks": 30, "planned_target_clusters": 29,
        "planned_candidates": 9802, "planned_selection_rows": 3600,
        "cpu_threads": 2, "worker_concurrency": 1, "task_timeout_seconds": 180,
        "automatic_retry": False, "gpu": False, "model_calls": 0,
        "historical_labels_previously_inspected": True,
        "scope": "Exploratory fixed-pool single-batch replay; no refit, no new observations, no prospective validation.",
        "primary": {"method": "pTop10_latent", "batch": 10,
                    "comparators": ["gp_mean", "original_policy"], "metric": "id_top10_recall"},
        "qpo_objective": "best_any_capture; unique winners give additive fixed-b optimum; nonunique winners use paper S1 greedy coverage approximation",
        "tie_rules": {"gold_primary": "Exact original (-p_activity, candidate_id) top10 ordering",
            "gold_sensitivity": "Fractional boundary membership under uniform tied ordering; no favorable choice after results",
            "acquisition_top10": "Fractional exact sample-boundary ties; rank by inclusion probability, saved GP mean, candidate_id",
            "acquisition_qpo": "Winner-set greedy uncovered coverage; rank marginal gain, saved GP mean, candidate_id",
            "numerical_equality": "64*eps*n*max(1,covariance infinity norm); mean uses 64*eps*n*max(1,maxabs(mean)); complete-link groups; roundoff eigenvalue projection, never jitter"},
        "sampling": "NumPy PCG64 SeedSequence([20261011, seed, stream]); latent stream1, independent observation noise stream2; random stream3. Same draws shared across batch sizes and acquisitions.",
        "observation_sensitivity": "same latent draws plus independent Gaussian noise with saved observation_sd squared minus latent diagonal; named separately",
        "fallback": "Separate gp_mean fallback selection only for posterior acquisition failure; original failure remains. No replacement of raw method success denominator.",
        "aggregate": "Within-task seed means, then equal-task macro; paired intervals resample 29 target clusters, retaining both CHEMBL237 endpoints together. Complete-seed tasks for raw paired analysis; report partial denominators and operational zero-hit failures separately.",
        "bootstrap_seed": 20261011, "bootstrap_repetitions": 5000,
        "label_gate": "Validate protocol/all source and input pins, full 30 task output seals/receipts, exact all3600 row keys, candidate uniqueness/membership/size/finiteness BEFORE opening any gold. All gold hashes then checked before scoring.",
        "author_code": {"commit": "ba4f72a4439634a2ff4909cf00205d2260c94750",
                        "scope": "Unchanged AST function bounded synthetic probe only; no product/public copying. Replay implementation independent from paper."},
        "versions": {n: importlib.metadata.version(n) for n in ("numpy", "scipy", "rdkit")},
        "python": sys.version, "python_executable": sys.executable,
        "calibration": "No posterior recalibration. Inclusion scores are Monte Carlo estimates under the preserved GP, not calibrated experimental hit probabilities.",
        "interpretation_rule": "Report both fixed primary comparisons and every prespecified sensitivity; no switching of preferred arm/tie metric after results. Exploratory evidence only; no automated adoption from this replay.",
        "source_pins": source_pins, "input_pins": pins}
    save(HERE / "protocol-draft.json", protocol)
    print({"tasks": len(tasks), "candidates": 9802, "rows_planned": 3600, "policy": dict(Counter(policies)), "selected": 0, "gold_opened": False})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-draft", help="Preserve old draft and refresh pins into this revision directory; hash inputs only")
    args = parser.parse_args()
    if args.refresh_draft:
        refresh_draft(args.refresh_draft)
    else:
        main()
