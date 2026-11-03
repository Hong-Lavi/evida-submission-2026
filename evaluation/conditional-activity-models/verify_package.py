"""Verify this self-contained result package without training or network access."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(root: Path = ROOT) -> dict:
    manifest = json.loads((root / "package-manifest.json").read_text())
    for name, expected in manifest["files"].items():
        path = root / name
        require(path.resolve().is_relative_to(root.resolve()), "Nonlocal manifest path")
        require(path.is_file() and not path.is_symlink(), "Missing or linked file: " + name)
        require(path.stat().st_size == expected["bytes"], "Size mismatch: " + name)
        require(sha(path) == expected["sha256"], "Hash mismatch: " + name)
    protocol = json.loads((root / "protocol.json").read_text())
    receipt = json.loads((root / "protocol-receipt.json").read_text())
    require(sha(root / "protocol.json") == receipt["sha256"], "Portable protocol mismatch")
    require(len(protocol["tasks"]) == len(set(protocol["order"])) == 30, "Task denominator mismatch")
    require([t["task"] for t in protocol["tasks"]] == protocol["order"], "Task order mismatch")
    for name, expected in protocol["source_pins"].items():
        require(sha(root / name) == expected, "Source pin mismatch: " + name)
    for task in protocol["tasks"]:
        for name, key in [("train.json", "train_sha256"), ("test-features.json", "features_sha256"),
                          ("evaluation-only/test-gold.json", "gold_sha256")]:
            require(sha(root / protocol["data"] / task["task"] / name) == task[key],
                    "Dataset pin mismatch: " + task["task"] + "/" + name)
    dataset = json.loads((root / "dataset-pins.json").read_text())
    for task in dataset["tasks"]:
        name = task["task"]
        path = root / "source-data" / (name + ".csv")
        require(sha(path) == task["input_sha256"], "Original CSV pin mismatch: " + name)
        with path.open(newline="") as stream:
            source_rows = list(csv.DictReader(stream))
        train, features, gold = [], [], []
        for index, row in enumerate(source_rows):
            identifier = name + ":" + str(index)
            value, nm = float(row["y [pEC50/pKi]"]), float(row["exp_mean [nM]"])
            require(math.isclose(value, 9 - math.log10(nm), abs_tol=1e-10), "Source activity units disagree")
            item = {"candidate_id": identifier, "smiles": row["smiles"]}
            if row["split"] == "train":
                item["activities"] = [{"standard_type": task["endpoint"], "standard_relation": "=",
                    "standard_units": "nM", "standard_value": nm, "pchembl_value": value,
                    "activity_id": identifier, "assay_context": "MoleculeACE curated per-compound aggregate. Individual assay/species conditions not provided in benchmark CSV; not inferred."}]
                train.append(item)
            elif row["split"] == "test":
                features.append(item)
                gold.append({"candidate_id": identifier, "p_activity": value, "cliff_mol": int(row["cliff_mol"])})
            else:
                raise ValueError("Unexpected source split")
        prepared = {"train.json": {"source": {"url": dataset["repository"] + "/tree/" + dataset["commit"]}, "rows": train},
                    "test-features.json": features, "evaluation-only/test-gold.json": gold}
        for filename, expected in prepared.items():
            actual = json.loads((root / protocol["data"] / name / filename).read_text())
            require(actual == expected, "Source/prepared row mismatch: " + name + "/" + filename)
    return {"status": "PASS", "verified_files": len(manifest["files"]),
            "planned_tasks": 30, "official_test_rows": sum(t["official_test"] for t in protocol["tasks"]),
            "all_source_csv_rows_reconciled": True,
            "model_fits": 0, "model_provider_calls": 0, "network_calls": 0, "gpu_used": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(verify(), indent=2))
