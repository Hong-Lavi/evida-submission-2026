"""Verify completed transport records and seal files without scientific adjudication."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "attempt-03"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def main():
    terminal = read(RUN / "component-terminal.json")
    protocol = read(ROOT / "component-protocol.json")
    amendment = read(RUN / "execution-amendment.json")
    controlled = read(RUN / "controlled-execution-receipt.json")
    assert digest(ROOT / "component-protocol.json") == read(ROOT / "component-protocol-receipt.json")["sha256"]
    assert controlled["driver_sha256"] == digest(ROOT / "execute_controlled.py")
    assert controlled["execution_amendment_sha256"] == digest(RUN / "execution-amendment.json")
    for path, expected in {**protocol["frozen_files"], **amendment["new_packet_file_sha256"]}.items():
        assert digest(path) == expected, "Frozen file changed: " + path
    order = protocol["order"]
    assert len(order) == len(set(order)) == 18
    receipts = terminal["receipts"]
    assert [r["blind_id"] for r in receipts] == order
    summaries = []
    for receipt in receipts:
        code = receipt["blind_id"]
        call = RUN / "component-calls" / code
        assert receipt == read(call / "receipt.json")
        assert digest(call / "request.json") == digest(ROOT / "component-calls" / code / "request.json")
        assert receipt["request_sha256"] == digest(call / "request.json")
        if receipt["status"] == "COMPLETED":
            assert receipt["actual_model"] == "gpt-6-astra"
            assert receipt["provider_attempts"] == 1
            assert "PROVIDER_EXECUTION_DEGRADED" not in receipt["quality_flags"]
            response = read(call / "provider-response.json")
            assert response["actual_model"] == "gpt-6-astra"
            assert response["payload"]["answer"] == (call / "answer.txt").read_text()
            assert digest(call / "answer.txt") == digest(RUN / "blind-review" / code / "answer.txt")
            visible = read(RUN / "blind-review" / code / "visible-case.json")
            request = read(call / "request.json")
            assert visible["case"] == request["case"]
            assert visible["scientific_request"] == request["scientific_request"]
            assert visible["source_sha256"] == digest(ROOT / "frozen-source.json")
        summaries.append({k: receipt.get(k) for k in (
            "blind_id", "status", "actual_model", "schema_status", "elapsed_seconds")})
    completed = sum(r["status"] == "COMPLETED" for r in receipts)
    assert terminal["observed_model_responses"] == completed
    blind_files = {str(p.relative_to(RUN / "blind-review")): digest(p)
                   for p in sorted((RUN / "blind-review").rglob("*")) if p.is_file()}
    blind_manifest = {"planned_responses": 18, "terminal_receipts": len(receipts),
        "returned_identity_accepted": completed, "file_sha256": blind_files}
    with (RUN / "blind-file-manifest.json").open("x") as handle:
        json.dump(blind_manifest, handle, indent=2)
        handle.write("\n")
    files = {str(p.relative_to(ROOT)): digest(p) for p in sorted(RUN.rglob("*"))
             if p.is_file() and p.name != "output-seal.json"}
    result = {"at_utc": datetime.now(timezone.utc).isoformat(),
        "seal_script_sha256": digest(__file__),
        "protocol_sha256": digest(ROOT / "component-protocol.json"),
        "review_rubric_sha256": digest(ROOT / "fixed-challenges.json"),
        "review_guide_sha256": digest(ROOT / "BLIND_REVIEW_GUIDE.md"),
        "planned_cases_per_arm": 6, "planned_arms": 3, "planned_responses": 18,
        "model_responses": completed,
        "status_counts": dict(Counter(r["status"] for r in receipts)),
        "schema_counts": dict(Counter(r.get("schema_status", "no_response") for r in receipts)),
        "scientific_adjudication_performed": False,
        "private_mapping_opened": False,
        "prior_setup_errors_count_as_model_answer_failures": False,
        "transport_summaries": summaries, "file_sha256": files}
    with (RUN / "output-seal.json").open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps({k: result[k] for k in ("planned_responses", "model_responses", "status_counts", "schema_counts")}))


if __name__ == "__main__":
    main()
