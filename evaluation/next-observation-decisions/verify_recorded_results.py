#!/usr/bin/env python3
"""Verify this recorded comparison package; no model or experiment is run."""

import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((HERE / "manifest.json").read_text())
    results = json.loads((HERE / "results.json").read_text())
    assert manifest["recorded_response_count"] == 12
    assert manifest["case_stage_count"] == 4
    assert manifest["arm_count"] == 3
    assert len(manifest["responses"]) == len(results["rows"]) == 12
    assert len({r["code"] for r in results["rows"]}) == 12
    assert len({r["case_stage"] for r in results["rows"]}) == 4
    for record in manifest["responses"]:
        path = HERE / record["public_path"]
        assert path.is_file()
        assert sha256(path) == record["public_sha256"]
        assert record["original_sha256"] == record["public_sha256"]
    for record in manifest["judgments"]:
        path = HERE / record["public_path"]
        assert path.is_file()
        assert sha256(path) == record["public_sha256"]
        judgment = json.loads(path.read_text())
        assert judgment["blind_id"] == record["code"]
        assert judgment["primary_success"] == (judgment["overall"] == "pass")
    for record in manifest["derived_public_files"]:
        assert sha256(HERE / record["path"]) == record["public_sha256"]
    assert sha256(HERE / manifest["frozen_rubric"]["public_path"]) == manifest["frozen_rubric"]["public_sha256"]
    assert manifest["frozen_rubric"]["original_sha256"] == manifest["frozen_rubric"]["public_sha256"]
    judgments = {p.stem: json.loads(p.read_text()) for p in (HERE / "judgments").glob("Q*.json")}
    assert len(judgments) == 12
    counts = Counter()
    for row in results["rows"]:
        j = judgments[row["code"]]
        assert row["overall"] == j["overall"]
        assert row["primary_success"] == j["primary_success"]
        assert row["dimensions"] == {d["id"]: d["status"] for d in j["dimensions"]}
        counts[row["arm"], row["overall"]] += 1
    for arm in results["arms"]:
        name = arm["arm"]
        assert arm["planned"] == 4
        assert arm["primary_success"] == counts[name, "pass"] == 3
        assert counts[name, "partial"] == 1
    assert results["model_response_generations"] == 12
    assert results["reviewer_sessions"] == 1
    assert {row["actual_model"] for row in results["rows"]} == {"gpt-6-sol"}
    identity = json.loads((HERE / "model-identity.json").read_text())
    assert identity["recorded_provider_attempts"] == identity["terminal_slots"] == 12
    assert len(identity["records"]) == 12
    assert {r["code"] for r in identity["records"]} == {r["code"] for r in results["rows"]}
    assert all(r["actual_model"] == r["requested_model"] == "gpt-6-sol"
               and r["requested_effort"] == "medium" and r["identity_accepted"]
               and r["provider_attempts"] == 1 and r["automatic_retries"] == 0
               and r["model_switches"] == 0 for r in identity["records"])
    diagnostics = json.loads((HERE / "schema-diagnostics.json").read_text())
    by_code = {item["code"]: item for item in diagnostics["diagnostics"]}
    assert set(by_code) == {"Q09", "Q11"}
    assert by_code["Q09"]["frozen_error_count"] == 6
    assert by_code["Q09"]["current_publication_schema_error_count"] == 6
    assert by_code["Q11"]["frozen_error_count"] == 1
    assert by_code["Q11"]["current_publication_schema_error_count"] == 0
    assert all(item["scientific_status"] == judgments[item["code"]]["overall"]
               for item in by_code.values())
    print("Verified recorded 12/12 responses, 12 judgments, four case-stages, and 3/4 pass per arm.")
    print("This checks archived bytes and arithmetic; it does not regenerate responses or validate biology.")


if __name__ == "__main__":
    main()
