#!/usr/bin/env python3
"""Recount publication metadata offline; no network, DB, model or private files."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
COUNTERS = ("unique_response_ids", "read_requests", "repeated_identical_reads", "automatic_compactions", "output_limit_continuations")


def main():
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def read(name):
        return json.loads((HERE / name).read_text(encoding="utf-8"))

    def rows(name):
        with (HERE / name).open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def total(items, key):
        return sum(int(r[key]) for r in items if r[key] != "")

    def trues(items, key):
        return sum(r[key] == "True" for r in items)

    manifest = read("manifest.json")
    for item in manifest["files"]:
        p = HERE / item["path"]
        check("hash:" + item["path"], p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == item["sha256"])
    expected_files = {r["path"] for r in manifest["files"]} | {"manifest.json"}
    check("exact_public_file_set", {p.name for p in HERE.iterdir() if p.is_file()} == expected_files)
    episodes, calls, summary = rows("episodes.csv"), rows("provider-calls.csv"), read("summary.json")
    check("unique_original_denominator_8", len({r["original_unit_id"] for r in episodes}) == summary["totals"]["original_unique_units"] == 8)
    check("all_rows_retained", len(episodes) == 16 and len(calls) == 17)
    check("12_attempts_not_12_independent_units", trues(episodes, "started") == 12 and trues(episodes, "independent_new_replicate") == 8 and trues(episodes, "manual_transport_repair_attempt") == 4)
    for item in summary["conditions"]:
        cid = item["condition"]
        es, cs = [r for r in episodes if r["condition"] == cid], [r for r in calls if r["condition"] == cid]
        check(cid + ":planned_started", len(es) == item["planned_rows"] and trues(es, "started") == item["started_execution_attempts"])
        check(cid + ":reservations", len(cs) == item["persistent_reservations"] == total(es, "persistent_reservations"))
        check(cid + ":actual_transmissions", trues(cs, "provider_transmitted") == item["provider_transmissions"] == total(es, "provider_transmissions"))
        check(cid + ":local_pre_admission_blocks", total(es, "local_gateway_attempts") - len(cs) == item["local_attempts_blocked_before_persistent_admission"])
        check(cid + ":provider_identity", trues(cs, "identity_verified") == item["identity_verified_provider_returns"])
        check(cid + ":native_wire_valid", trues(cs, "native_wire_valid") == item["native_wire_valid_responses"] == total(es, "native_wire_valid_responses"))
        for field in ("applied_frames", "public_lookup_bundles", "logical_public_lookups", "scientific_calculations"):
            check(cid + ":" + field, total(es, field) == item[field])
        for field in TOKENS + COUNTERS:
            check(cid + ":" + field, total(cs, field) == item["usage"][field])
        check(cid + ":zero_final_not_accuracy_zero", trues(es, "published") == item["published"] == 0 and all(r["final_quality"] == "NOT_ASSESSABLE_NO_FINAL_ANSWER" for r in es))
        observed_seconds = sum(float(r["elapsed_seconds"]) for r in cs if r["provider_transmitted"] == "True")
        check(cid + ":provider_elapsed", abs(observed_seconds - item["sum_transmitted_provider_elapsed_seconds"]) < 0.00001)
    for field in TOKENS + COUNTERS:
        check("total:" + field, total(calls, field) == summary["totals"]["usage"][field])
    check("all_sent_have_reported_usage", all(r["usage_status"] == "REPORTED" for r in calls if r["provider_transmitted"] == "True"))
    check("untransmitted_is_null_not_reported_zero", all(r[k] == "" for r in calls if r["provider_transmitted"] == "False" for k in TOKENS + COUNTERS))
    check("same_requested_route", all(r["requested_model"] == "claude-opus-5" and r["requested_effort"] == "high" for r in calls))
    check("observed_cli_route", all(r["observed_cli_model"] == "claude-opus-5" and r["observed_cli_effort"] == "high" for r in calls if r["provider_transmitted"] == "True"))
    check("no_automatic_retry", all(r["automatic_retry"] == "False" for r in calls))
    check("no_final_accuracy_ratio", summary["totals"]["final_source_claim_denominator"] == 0 and summary["totals"]["final_source_fidelity_proportion"] is None)
    audit = read("transport-audit.json")["03"]
    check("entry_increment_recount", audit["baseline_entry_bytes"] + audit["schema_increment_bytes"] == audit["typed_entry_bytes"] > audit["mandatory_entry_review_bound_bytes"])
    check("annotation_only_not_sufficient", audit["typed_entry_bytes"] - audit["annotation_only_reduction_bytes"] == audit["entry_after_annotation_only_reduction_bytes"] > audit["mandatory_entry_review_bound_bytes"])
    pins = read("source-pins.json")
    check("no_source_bodies_exported", not pins["private_bodies_exported"] and all(not p["body_in_public_export"] for p in pins["pins"]))
    code = pins["product_code"]
    check("only_planner_arm_difference", [p for p in sorted(code["A"]) if code["A"][p] != code["B"][p]] == ["configs/planner.md"])
    # Allowlist files rather than copying original runtime/provider directories.
    banned = ("/data/" + "user_home/", "Bearer" + " ", "-----BEGIN " + "PRIVATE KEY-----")
    check("no_private_paths_or_credential_markers", all(not any(marker in (HERE / p).read_text(encoding="utf-8") for marker in banned) for p in expected_files))
    print(json.dumps({"status": "PASS", "checks": len(checks), "checked": checks, "provider_calls": 0, "database_reads": 0, "network": 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
