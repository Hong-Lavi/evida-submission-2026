"""Capture minimal, read-only saved-case inputs for the evidence workbench test."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

BASE = "http://127.0.0.1:8917"
CASES = {
    "ipf": "ws_3c8fe9df9cd14339",
    "pde4b": "ws_1ff05aa2d7c24e0e",
    "als": "ws_4475545a286541b2",
    "preeclampsia": "ws_4a5f487f62684885",
}
OUT = Path(__file__).with_name("fixtures") / "evidence_workbench_saved_cases.json"


def capture() -> None:
    rows = {}
    for name, workspace in CASES.items():
        with urlopen(f"{BASE}/api/workspaces/{workspace}", timeout=10) as response:
            saved = json.load(response)
        decision = saved.get("decision") or {}
        linked_ids = {
            evidence.get("source_id")
            for hypothesis in decision.get("research_loop", {}).get("hypotheses", [])
            for claim in [hypothesis, *(hypothesis.get("assessment_scope", {}).get("parts") or []),
                          *(hypothesis.get("conditional_alternatives") or [])]
            for evidence in claim.get("evidence", [])
            if evidence.get("source_type") == "artifact"
        }
        artifacts = []
        for artifact in saved.get("artifacts", []):
            if artifact.get("kind") not in {"literature", "clinical_trial_search", "drug_label_search", "entity_search", "article"} and artifact.get("id") not in linked_ids:
                continue
            meta = artifact.get("meta") or {}
            summary, arguments = meta.get("summary") or {}, meta.get("arguments") or {}
            artifacts.append({"id": artifact["id"], "kind": artifact["kind"], "meta": {
                "result_status": meta.get("result_status"), "semantic_type": meta.get("semantic_type"),
                "summary": {key: summary[key] for key in ("returned", "content_scope", "has_more", "next_cursor", "next_page_token") if key in summary},
                "arguments": {key: arguments[key] for key in ("query", "condition", "entity") if key in arguments},
            }})
        rows[name] = {
            "id": saved["id"],
            "title": saved["title"],
            "rev": saved["rev"],
            "decision_rev": saved.get("decision_rev"),
            "decision": {"research_loop": {"hypotheses": decision.get("research_loop", {}).get("hypotheses", [])}},
            "artifacts": artifacts,
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(OUT)


if __name__ == "__main__":
    capture()
