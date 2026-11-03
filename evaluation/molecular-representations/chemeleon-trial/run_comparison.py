"""Fixed follow-up: author frozen embeddings plus the unchanged RF regressor."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
def utc():
    return datetime.now(timezone.utc).isoformat()
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, value):
    with path.open("x") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")
def load_protocol():
    path = HERE / "protocol.json"
    assert sha(path) == json.loads((HERE / "protocol-receipt.json").read_text())["sha256"]
    protocol = json.loads(path.read_text())
    for name, digest in protocol["source_pins"].items():
        assert sha(HERE / name) == digest, name
    gp = HERE.parent / "tanimoto-trial"
    assert sha(gp / "protocol.json") == protocol["gp_protocol_sha256"]
    for name, digest in protocol["native_source_pins"].items():
        assert sha(gp / name) == digest, name
    return protocol


def worker(task_name, run_dir):
    p = load_protocol()
    task = next(t for t in p["tasks"] if t["task"] == task_name)
    out = run_dir / task_name
    save(out / "started.json", {"at": utc(), "task": task_name, "test_gold_read": False})
    data = Path(p["data"]) / task_name
    assert sha(data / "train.json") == task["train_sha256"]
    assert sha(data / "test-features.json") == task["features_sha256"]
    train = json.loads((data / "train.json").read_text())
    features = json.loads((data / "test-features.json").read_text())
    gp_path = Path(p["gp_run"]) / task_name / "predictions.json"
    assert sha(gp_path) == p["gp_prediction_pins"][task_name]
    previous = json.loads(gp_path.read_text())
    sys.path.insert(0, p["frozen_product"])
    import numpy as np
    import sklearn.ensemble
    import torch
    from encoder_adapter import LocalCheMeleonFingerprint
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator
    torch.set_num_threads(2)
    torch.manual_seed(p["seed"])
    captured = []
    original = sklearn.ensemble.RandomForestRegressor
    class RecordingRF(original):
        def fit(self, x, y, *args, **kwargs):
            fitted = super().fit(x, y, *args, **kwargs)
            captured.append((self, x.copy(), y.copy()))
            return fitted
    sklearn.ensemble.RandomForestRegressor = RecordingRF
    from evida.activity_model import fit, _spearman
    began = time.monotonic()
    native = fit(train, seed=p["seed"], endpoint=task["endpoint"])
    assert len(captured) == 1
    baseline, x_native, y = captured[0]
    assert sha_bytes(x_native.tobytes()) == previous["train_matrix_sha256"]
    assert sha_bytes(y.tobytes()) == previous["train_labels_sha256"]
    training_rows = native["_training_rows"]
    training_smiles = {r["smiles"] for r in training_rows}
    held = [r for r in native["_seed_rows"] if r["smiles"] not in training_smiles]
    y_held = np.asarray([r["p_activity"] for r in held], dtype=float)
    assert len(held) == native["summary"]["held_out"]
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)
    baseline_test = baseline.predict(np.asarray([list(generator.GetFingerprint(Chem.MolFromSmiles(r["smiles"]))) for r in features], dtype=float))
    assert [r["candidate_id"] for r in features] == [r["candidate_id"] for r in previous["rows"]]
    np.testing.assert_allclose(baseline_test, [r["rf_prediction"] for r in previous["rows"]], rtol=0, atol=1e-10)
    save(out / "baseline-reproduced.json", {"at": utc(), "same_native_training_matrix": True,
          "same_native_labels": True, "same_test_predictions_atol": 1e-10, "seconds": time.monotonic() - began,
          "native_summary": native["summary"], "usable": native["usable"]})
    encoder = LocalCheMeleonFingerprint(HERE / "weights/chemeleon_mp.pt")
    all_rows = training_rows + held + features
    smiles = sorted({r["smiles"] for r in all_rows})
    began = time.monotonic()
    embeddings = encoder.batches(smiles, batch_size=p["encoder"]["batch_size"])
    embedding_seconds = time.monotonic() - began
    np.savez_compressed(out / "embeddings.npz", smiles=np.asarray(smiles), embeddings=embeddings)
    positions = {s: i for i, s in enumerate(smiles)}
    def matrix(rows):
        return embeddings[[positions[r["smiles"]] for r in rows]]
    x_train, x_held, x_test = matrix(training_rows), matrix(held), matrix(features)
    model = original(n_estimators=300, min_samples_leaf=2, random_state=p["seed"], n_jobs=2)
    began = time.monotonic()
    model.fit(x_train, y)
    fit_seconds = time.monotonic() - began
    predicted_held, predicted_test = model.predict(x_held), model.predict(x_test)
    assert np.isfinite(predicted_held).all() and np.isfinite(predicted_test).all()
    inner_mae = float(np.mean(np.abs(predicted_held - y_held)))
    inner_rho = round(_spearman(predicted_held.tolist(), y_held.tolist()), 3)
    usable = bool(inner_rho >= .3 and inner_mae < previous["inner_mean_mae"])
    candidates = []
    for arm, key, priority in [("rf", "native_rf", 0), ("gp", "author_gp", 1)]:
        if previous[key]["usable"]:
            candidates.append((previous[key]["inner_mae"], priority, arm))
    if usable:
        candidates.append((inner_mae, 2, "chemeleon_rf"))
    policy = min(candidates)[2] if candidates else "abstain"
    result = {"task": task_name, "status": "completed", "at": utc(), "test_gold_read": False,
        "training_rows": len(y), "inner_held_out_rows": len(held), "test_rows": len(features),
        "native_rf": previous["native_rf"], "author_gp": previous["author_gp"],
        "chemeleon_rf": {"usable": usable, "inner_mae": inner_mae, "inner_spearman": inner_rho,
                         "embedding_seconds": embedding_seconds, "fit_seconds": fit_seconds},
        "selected_policy_arm": policy, "prior_policy_arm": previous["selected_policy_arm"],
        "embeddings_sha256": sha(out / "embeddings.npz"), "weights_sha256": p["weights_sha256"],
        "train_matrix_sha256": previous["train_matrix_sha256"], "train_labels_sha256": previous["train_labels_sha256"],
        "rows": [{**r, "chemeleon_rf_prediction": float(c)} for r, c in zip(previous["rows"], predicted_test)]}
    save(out / "predictions.json", result)


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def supervise(task, run_dir, timeout):
    out = run_dir / task
    out.mkdir(exist_ok=False)
    began = time.monotonic()
    with (out / "process.log").open("x") as log:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2",
                   MPLCONFIGDIR=str(HERE / "cache/matplotlib"))
        process = subprocess.Popen([sys.executable, "-B", __file__, "--worker", task, str(run_dir)], stdout=log,
                                   stderr=subprocess.STDOUT, env=env, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
            status = "completed" if code == 0 and (out / "predictions.json").exists() else "failed"
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code, status = process.returncode, "timeout"
    receipt = {"task": task, "status": status, "returncode": code, "seconds": time.monotonic() - began,
               "prediction_sha256": sha(out / "predictions.json") if (out / "predictions.json").exists() else None}
    save(out / "receipt.json", receipt)
    print(json.dumps(receipt), flush=True)
    return receipt


def main():
    p = load_protocol()
    run_dir = HERE / "run-01"
    run_dir.mkdir(exist_ok=False)
    save(run_dir / "started.json", {"at": utc(), "protocol_sha256": sha(HERE / "protocol.json"), "tasks": p["order"]})
    with ThreadPoolExecutor(max_workers=p["concurrency"]) as pool:
        jobs = [pool.submit(supervise, t, run_dir, p["timeout_task_seconds"]) for t in p["order"]]
        results = [future.result() for future in as_completed(jobs)]
    by_task = {r["task"]: r for r in results}
    save(run_dir / "sealed-predictions.json", {"at": utc(), "protocol_sha256": sha(HERE / "protocol.json"),
         "test_gold_read_by_fitting": False, "tasks": [by_task[t] for t in p["order"]]})
    print(json.dumps({"finished": len(results), "completed": sum(r["status"] == "completed" for r in results)}), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2], Path(sys.argv[3]))
    else:
        main()
