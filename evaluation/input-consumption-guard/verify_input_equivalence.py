"""Check the two arms received equal substantive scripted inputs, without rerunning them."""
import copy
import hashlib
import json
from pathlib import Path
import sys


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def main():
    attempt = Path(sys.argv[1]).resolve()
    plan = json.loads((attempt / "plan.json").read_text())
    rows = []
    for spec in plan["families"]:
        normalized, questions, source_hashes = {}, {}, {}
        for arm in ("current", "improved"):
            directory = attempt / arm / spec["id"]
            proposal = copy.deepcopy(json.loads((directory / "scripted-proposal.json").read_text()))
            has_metadata = "intent_review" in proposal
            if has_metadata != (arm == "improved"):
                raise ValueError("Unexpected interface metadata presence")
            proposal.pop("intent_review", None)
            state = json.loads((directory / "before-commit.json").read_text())
            sources = {a["id"]: a["sha256"] for a in state["artifacts"] if a["kind"] == "source_text"}
            if len(sources) != 1 or set(proposal["decision"]["evidence_refs"]) != set(sources):
                raise ValueError("Unexpected source references")
            proposal["decision"]["evidence_refs"] = [sources[ref] for ref in proposal["decision"]["evidence_refs"]]
            normalized[arm] = proposal
            questions[arm] = [e["body"]["current_question"] for e in state["events"] if e["kind"] == "work_framed"]
            source_hashes[arm] = sorted(sources.values())
        if normalized["current"] != normalized["improved"]:
            raise ValueError("Different substantive proposed decisions: " + spec["id"])
        if questions["current"] != questions["improved"] or source_hashes["current"] != source_hashes["improved"]:
            raise ValueError("Different questions or source bytes: " + spec["id"])
        rows.append({"family": spec["id"], "substantive_input_equal": True,
                     "normalized_proposal_sha256": hashlib.sha256(canonical(normalized["current"])).hexdigest(),
                     "source_sha256": source_hashes["current"], "question_sequence": questions["current"]})
    result = {"status": "PASS", "families": len(rows), "rows": rows,
              "normalization": "Remove improved-only declared-use metadata and replace random artifact IDs with the exact source-content SHA256. No scientific text, intent record, question or decision field is changed.",
              "model_calls": 0, "product_functions_rerun": False}
    with (attempt / "input-equivalence.json").open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "PASS", "families": len(rows), "substantive_inputs_equal": True}))


if __name__ == "__main__":
    main()
