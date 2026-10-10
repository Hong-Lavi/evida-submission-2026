"""Check sealed review integrity from permitted blinded inputs; never grade semantics."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
BLIND = BASE / "attempt-03/blind-review"
MANIFEST = BASE / "attempt-03/blind-file-manifest.json"
EXPECTED_MANIFEST_SHA = "9dccbfad1d2b0fe6856e0ec9870e646edea2884153e2420833145b4bc9e67ebf"
EXPECTED_REVIEW_SEAL_SHA = "554f5cb13ed77e9ea990e631284407a28bd2081a7c9bf96a72d8fb396fc510e2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pointer(value, path):
    for token in path.strip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


assert sha(MANIFEST) == EXPECTED_MANIFEST_SHA
manifest = json.loads(MANIFEST.read_text())
expected_paths = {f"B{i:02d}/{name}" for i in range(1, 19)
                  for name in ("answer.txt", "visible-case.json")}
assert set(manifest["file_sha256"]) == expected_paths
assert {key: manifest[key] for key in ("planned_responses", "terminal_receipts", "returned_identity_accepted")} == {
    "planned_responses": 18, "terminal_receipts": 18, "returned_identity_accepted": 18}
for relative, expected in manifest["file_sha256"].items():
    assert sha(BLIND / relative) == expected

criterion_seal = json.loads((HERE / "criterion-interpretation-01.seal.json").read_text())
for relative, expected in criterion_seal["files"].items():
    assert sha(BASE / relative) == expected
criterion_sha = sha(HERE / "criterion-interpretation-01.json")
source = json.loads((BASE / "frozen-source.json").read_text())
records = {}
for path in sorted(HERE.glob("manual-batch-*.seal.json")):
    batch = json.loads(path.read_text())
    assert not batch["key_opened"]
    draft = HERE / path.name.replace(".seal.json", ".json")
    assert sha(draft) == batch["manual_draft_sha256"]
    for row in batch["judgments"]:
        assert row["blind_id"] not in records
        record_path = HERE / row["judgment_path"]
        assert sha(record_path) == row["judgment_sha256"]
        records[row["blind_id"]] = json.loads(record_path.read_text())
assert set(records) == {f"B{i:02d}" for i in range(1, 19)}

quote_count = 0
source_anchor_count = 0
structured_count = 0
for blind_id, record in records.items():
    assert record["criterion_interpretation_sha256"] == criterion_sha
    assert not record["key_opened"] and not record["arm_identity_known"]
    for name, field in (("answer.txt", "answer_sha256"), ("visible-case.json", "visible_case_sha256")):
        assert record[field] == manifest["file_sha256"][f"{blind_id}/{name}"]
    answer = (BLIND / blind_id / "answer.txt").read_text()
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError:
        parsed = None
    for criterion in record["criteria"]:
        for evidence in criterion["evidence"]:
            quote = evidence["quote"]
            assert quote in answer
            assert hashlib.sha256(quote.encode()).hexdigest() == evidence["quote_utf8_sha256"]
            start = answer.index(quote)
            assert answer.count("\n", 0, start) + 1 == evidence["answer_line_start"]
            assert answer.count("\n", 0, start + len(quote)) + 1 == evidence["answer_line_end"]
            if "json_pointer" in evidence:
                assert quote in pointer(parsed, evidence["json_pointer"])
            quote_count += 1
    if parsed is None:
        continue
    structured_count += 1
    for step in parsed.get("hypothesis_review", {}).get("causal_steps", []):
        for group in step.get("evidence_groups", []):
            for anchor in group.get("anchors", []):
                if anchor.get("artifact_id") == "source_packet":
                    value = pointer(source, anchor["path"])
                    assert isinstance(value, str) and anchor["quote"] in value
                    source_anchor_count += 1

review_seal_path = HERE / "blinded_review_final.seal.json"
assert sha(review_seal_path) == EXPECTED_REVIEW_SEAL_SHA
review_seal = json.loads(review_seal_path.read_text())
assert not review_seal["identity_key_opened"]
for relative, expected in review_seal["files"].items():
    assert sha(HERE / relative) == expected
report = json.loads((HERE / "blinded_review_final.json").read_text())
assert report["reviewed"] == 18 and report["pending"] == 0
for row in report["rows"]:
    assert row["review"] == records[row["blind_id"]]
case_counts = Counter(r["case_id"] for r in records.values())
assert len(case_counts) == 6 and set(case_counts.values()) == {3}

result = {
    "status": "PASS",
    "at_utc": datetime.now(timezone.utc).isoformat(),
    "identity_key_opened": False,
    "allowed_input_boundary": "Only fixed guide/criteria/scientific packet, blind visible-case/answer files, owner-authorized hash-only manifest, and independent-review artifacts were read.",
    "coverage": {key: manifest[key] for key in ("planned_responses", "terminal_receipts", "returned_identity_accepted")},
    "reviewed": 18,
    "pending": 0,
    "primary_counts": dict(Counter(r["primary_result"] for r in records.values())),
    "criterion_counts": dict(Counter(c["status"] for r in records.values() for c in r["criteria"])),
    "case_counts": dict(sorted(case_counts.items())),
    "verified_visible_files": len(expected_paths),
    "verified_exact_judgment_quotations": quote_count,
    "supplementary_source_anchor_check": {
        "structured_answers": structured_count,
        "exact_source_path_and_quote_occurrences": source_anchor_count,
        "mismatches": 0,
        "scope": "String/path integrity only, not semantic completeness or an additional scientific score. Prose formatting receives no penalty."
    },
    "criterion_interpretation_sha256": criterion_sha,
    "blind_file_manifest_sha256": sha(MANIFEST),
    "final_review_seal_sha256": sha(review_seal_path),
    "verifier_sha256": sha(Path(__file__)),
    "prior_attempts": "Outside this blinded review; no claim that attempt-03 counts cover earlier execution attempts."
}
out = HERE / "final-integrity-verification.json"
with out.open("x") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps(result, ensure_ascii=False))
