"""Append-only input classification corrections, separate from original event bodies."""
from __future__ import annotations

INPUT_KINDS = frozenset({"message", "observation", "correction"})
CORRECTION_FIELDS = frozenset({"target_message_id", "corrected_synthetic", "reason", "researcher_reply"})


def validate_correction(body, prior_events):
    correction = body.get("provenance_correction")
    if (body.get("kind") != "correction" or body.get("synthetic") is not False
            or not isinstance(correction, dict) or set(correction) != CORRECTION_FIELDS):
        raise ValueError("출처 정정은 연구자가 확인한 정정 입력으로 기록해 주세요.")
    if type(correction["corrected_synthetic"]) is not bool:
        raise ValueError("정정할 가상 입력 여부를 확인해 주세요.")
    for key in ("target_message_id", "reason", "researcher_reply"):
        if not isinstance(correction[key], str) or not correction[key].strip() or len(correction[key]) > 4000:
            raise ValueError("출처 정정에는 원 입력 ID, 정정 이유와 연구자의 확인 내용이 필요합니다.")
    target = next((event for event in prior_events
                   if event["kind"] in INPUT_KINDS
                   and event["body"].get("message_id") == correction["target_message_id"]), None)
    if target is None:
        raise ValueError("이 연구에 보존된 원 입력에만 출처 정정을 연결할 수 있습니다.")
    if "provenance_correction" in target["body"]:
        raise ValueError("출처 정정 기록 대신 분류를 바꿀 원 입력을 지정해 주세요.")
    return target


def _classification(synthetic):
    return {"origin": "synthetic" if synthetic else "researcher_report", "synthetic": synthetic,
            "empirical_status": "not_empirical_observation" if synthetic else "researcher_report_unverified"}


def annotate_events(events):
    """Keep every stored body intact; attach current classification and its receipts.

    A factual correction about a synthetic scenario is not itself a synthetic report.
    Reclassification as a researcher report never validates its scientific claims.
    """
    annotated, by_message = [], {}
    for original in events:
        event = dict(original)
        body = event["body"]
        if event["kind"] in INPUT_KINDS:
            synthetic = body.get("origin") == "synthetic" or body.get("synthetic") is True
            event["effective_provenance"] = {
                **_classification(synthetic),
                "original_origin": body.get("origin", "synthetic" if synthetic else "researcher_report"),
                "original_synthetic": body.get("synthetic"), "corrections": [], "corrected_by": None,
                "meaning": "Use this effective provenance when interpreting the preserved raw body. Synthetic input is a demonstration scenario, not empirical evidence; researcher reports remain unverified."}
            if "provenance_correction" in body:
                try:
                    validate_correction(body, annotated)
                except ValueError as error:
                    # An invalid historical record remains visible but cannot relabel another input.
                    event["provenance_correction_status"] = {"status": "invalid", "reason": str(error)}
                else:
                    correction = body["provenance_correction"]
                    target = by_message[correction["target_message_id"]]
                    receipt = {"message_id": body["message_id"], "event_seq": event["seq"],
                               "created": event["created"], **correction}
                    effective = target["effective_provenance"]
                    effective.update(_classification(correction["corrected_synthetic"]))
                    effective["corrections"].append(receipt)
                    effective["corrected_by"] = receipt
                    event["provenance_correction_status"] = {"status": "applied", "target_message_id": correction["target_message_id"]}
            if body.get("message_id"):
                by_message[body["message_id"]] = event
        annotated.append(event)
    return annotated
