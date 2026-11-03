"""Freeze the representation follow-up before any task-specific embedding RF fit."""
from datetime import datetime, timezone
import json
from pathlib import Path
from run_comparison import HERE, sha, save

gp = HERE.parent / "tanimoto-trial"
prior = json.loads((gp / "protocol.json").read_text())
seal = json.loads((gp / "run-01/sealed-predictions.json").read_text())
preflight = json.loads((HERE / "preflight-result.json").read_text())
assert preflight["status"] == "passed"
assert len(seal["tasks"]) == 30 and all(t["status"] == "completed" for t in seal["tasks"])
for t in seal["tasks"]:
    assert sha(gp / "run-01" / t["task"] / "predictions.json") == t["prediction_sha256"]
files = ["encoder_adapter.py", "run_comparison.py", "score_comparison.py", "freeze_protocol.py",
         "author/chemeleon_fingerprint.py", "author/LICENSE", "weights/chemeleon_mp.pt"]
protocol = {
    "status": "FROZEN_BEFORE_REPRESENTATION_TASK_FITS", "at_utc": datetime.now(timezone.utc).isoformat(),
    "purpose": "Test whether a frozen author-learned molecular representation improves activity prediction and top10 selection with the same RF regressor.",
    "chronology": "The coordinator has seen the completed RF/GP benchmark results. This is a prespecified follow-up on the same 30 tasks, not a fresh independent validation dataset. No CheMeleon task outcome has been observed at freeze time.",
    "author_repository": "https://github.com/JacksonBurns/chemeleon", "author_commit": preflight["author_commit"],
    "author_license": "MIT", "weight_record": "https://zenodo.org/records/15460715", "weight_license": "MIT",
    "weights_sha256": preflight["weights_sha256"], "source_pins": {name: sha(HERE / name) for name in files},
    "data": prior["data"], "tasks": prior["tasks"], "order": prior["order"], "frozen_product": prior["frozen_product"],
    "native_source_pins": {name: value for name, value in prior["source_pins"].items() if name.startswith("frozen-product/")},
    "gp_run": str(gp / "run-01"), "gp_protocol_sha256": sha(gp / "protocol.json"),
    "gp_prediction_pins": {t["task"]: t["prediction_sha256"] for t in seal["tasks"]},
    "seed": 20260930, "bootstrap_seed": 20261011, "bootstrap_repetitions": 5000,
    "encoder": {"author_class": "CheMeleonFingerprint", "dimension": 2048, "weights": "frozen",
                "pooling": "author MeanAggregation", "device": "cpu", "threads": 2, "batch_size": 64,
                "adaptation": "Explicit private checkpoint path; same author __call__; no change to HOME or public runtime."},
    "regressor": "RandomForestRegressor 300 trees, min_samples_leaf2, seed20260930, n_jobs2 for both feature representations; all other installed-library defaults.",
    "splits": "Exactly the frozen native 75% inner scaffold training and inner holdout; official outer test unchanged. Reproduce and assert native RF matrix, labels and predictions before fitting the representation arm.",
    "primary": "30-task macro paired MAE difference CheMeleon-RF minus native Morgan-RF.",
    "secondary": ["Spearman", "RMSE", "top10 recall with candidate_id tie-break", "best true activity in selected10", "inner-selected three-method policy versus the previous RF/GP policy"],
    "policy": "Usable requires inner Spearman>=0.3 and inner MAE below training-mean MAE. Select the usable arm with smallest inner MAE, with tie priority RF then GP then CheMeleon-RF. A CheMeleon technical failure falls back to the previously selected RF/GP arm. Preserve raw predictions, failed cases and operational coverage separately.",
    "scope": "Reported target/endpoint activity across pooled source assay conditions; frozen feature use of the author's weights with native EVIDA RF, distinct from author fine-tuning experiments.",
    "failures": "No automatic retry. Preserve every planned task, native baseline, partial result and failure. Any technical repair receives a separate version and run.",
    "scoring": "Verify all source and prediction pins and all 30 terminal receipts before opening labels for this follow-up. Paired 29-target-cluster bootstrap5000 with complete-task and attempted-task denominators.",
    "concurrency": 2, "timeout_task_seconds": 1800, "gpu_used": False, "model_provider_calls": 0,
    "next_decision": "If the representation improves the intended candidate-selection outcome, test it in the native pipeline. Otherwise retain the measured conditional GP activity gain and move to another pipeline gap.",
}
save(HERE / "protocol.json", protocol)
save(HERE / "protocol-receipt.json", {"sha256": sha(HERE / "protocol.json"), "tasks": 30, "official_test_rows": 9802})
print(json.dumps({"status": protocol["status"], "sha256": sha(HERE / "protocol.json")}))
