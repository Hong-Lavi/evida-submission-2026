"""Locate the inputs of a review without substituting a summary for the sources."""
from __future__ import annotations

INTERNAL_KINDS = frozenset({
    "model_receipt", "decision_proposal", "research_notes", "tool_reading",
    "protocol_snapshot",
})


def review_inputs(state):
    events = state["events"]
    publications = [e for e in events if e["kind"] == "decision_published"]
    current = (bool(state.get("decision")) and state.get("decision_rev") == state["rev"]
               and bool(publications))
    # A completed review keeps its own input interval visible. A pending review
    # begins at the last published decision, including failed intervening work.
    end = publications[-1]["seq"] if current else state.get("event_cursor", 0)
    prior = publications[-2] if current and len(publications) > 1 else (
        publications[-1] if not current and publications else None)
    start = prior["seq"] if prior else 0
    artifacts = {a["id"]: a for a in state["artifacts"]}
    sources, messages, edits, provenance_corrections = [], [], [], []
    for event in events:
        if not start < event["seq"] <= end:
            continue
        body = event["body"]
        if event["kind"] == "artifact_added":
            artifact = artifacts.get(body["artifact_id"])
            if artifact and artifact["kind"] not in INTERNAL_KINDS:
                sources.append({key: artifact[key] for key in ("id", "title", "kind")})
        elif event["kind"] in ("message", "observation", "correction"):
            provenance = event.get("effective_provenance", {})
            messages.append({"id": body["message_id"], "kind": event["kind"],
                             "origin": provenance.get("origin", body.get("origin", "researcher_report")),
                             "stored_origin": body.get("origin", "researcher_report"),
                             "created": event["created"]})
            if event.get("provenance_correction_status", {}).get("status") == "applied":
                provenance_corrections.append({"correction_message_id": body["message_id"],
                                               **body["provenance_correction"]})
        elif event["kind"] == "intent_edit":
            edits.append({"event_seq": event["seq"], "created": event["created"]})
    return {"phase": "published_review" if current else "pending_review",
            "since_decision": prior["body"]["receipt_id"] if prior else None,
            "after_event": start, "through_event": end,
            "sources": sources, "messages": messages, "intent_edits": edits,
            "provenance_corrections": provenance_corrections,
            "meaning": "Input locations, not proof of reading or claim support. Provenance corrections reclassify the referenced original input without replacing it; use its effective_provenance. Select relevant original ranges; older evidence, conditions and counterevidence remain accessible."}
