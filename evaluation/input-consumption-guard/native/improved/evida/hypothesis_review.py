"""Retained evidence and prediction reviews, not a causal or probability oracle.

Exact anchors verify persisted text identity only. Pair separation is conditional
on model-authored, complete outcome sets and declared measurement requirements.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import re

import jsonschema


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def array(item, maximum=100):
    return {"type": "array", "items": item, "maxItems": maximum}


def enum(*values):
    return {"type": "string", "enum": list(values)}


TEXT = {"type": "string", "maxLength": 8000}
TEXTS = array(TEXT)
INDEX = {"type": "integer", "minimum": 0}
ANCHOR = obj({"artifact_id": TEXT,
              "path": {**TEXT, "description": "JSON pointer into the saved artifact itself, not the tool response wrapper. A saved rows array uses /rows/<index>/... rather than /result/rows/<index>/...."},
              "quote": TEXT})
EVIDENCE_GROUP = obj({
    "id": TEXT, "anchors": array(ANCHOR, 20), "reported_context": TEXT,
    "evidence_role": enum("association", "intervention", "mediator", "background", "unknown"),
    "text_support": enum("supports", "contradicts", "partial", "not_addressed", "unknown"),
    "text_support_rationale": TEXT,
    "causal_support": enum("supports_step", "association_only", "intervention_response_only", "not_established", "unknown"),
    "causal_support_rationale": TEXT,
    "applicability": enum("direct", "conditional", "mismatch", "unknown"),
    "applicability_rationale": TEXT, "missing_assumptions": TEXTS,
})
CAUSAL_STEP = obj({
    "id": TEXT, "hypothesis_id": TEXT,
    "part_id": {**TEXT, "description": "Use an empty string for the whole hypothesis; otherwise copy an exact assessment_scope.parts ID from this hypothesis. Do not invent a part ID."},
    "claim": TEXT,
    "target_context": TEXT, "missing_assumptions": TEXTS,
    "evidence_groups": array(EVIDENCE_GROUP, 20),
})
PREDICTION = obj({
    "hypothesis_id": TEXT, "alternative_id": TEXT, "outcome_indices": array(INDEX),
    "coverage": enum("complete", "partial", "unknown"),
    "origin": enum("prospective", "previously_recorded", "reconstructed_after_result"),
    "assumptions": TEXTS, "rationale": TEXT, "source_ids": TEXTS,
})
OUTCOME = obj({"outcome_index": INDEX, "interpretation": enum(
    "adequate_measurement", "measurement_failure", "insufficient_precision", "not_applicable")})
OBSERVATION = obj({
    "check_id": TEXT, "validity_requirements": TEXTS, "precision_requirement": TEXT,
    "outcomes": array(OUTCOME), "predictions": array(PREDICTION),
})
SCHEMA = obj({"schema_version": enum("1"), "causal_steps": array(CAUSAL_STEP, 60),
              "observations": array(OBSERVATION, 60)})
# Frozen v1 records remain readable. Current authors account for every declared
# item without asking the application to infer which claims are causal.
def _scope_row(id_field):
    return obj({id_field: TEXT, "status": enum("reviewed", "not_reviewed", "not_applicable"),
                "reason": {**TEXT, "minLength": 1}})


CURRENT_SCHEMA = obj({**SCHEMA["properties"], "schema_version": enum("2"),
                      "scope": obj({"hypotheses": array(_scope_row("hypothesis_id")),
                                    "checks": array(_scope_row("check_id"))})})
CURRENT_SCHEMA["description"] = (
    "Required in every new final response. Account for every final hypothesis and next check in scope. "
    "For applicable claims and observations author the linked causal_steps/observations now, using unknown "
    "assessments and empty anchors when evidence is absent. Explicit not_reviewed/not_applicable reasons "
    "remain visible as incomplete or outside scope, never as completed scientific validation. "
    "Only when the decision has no hypotheses/checks may all lists be empty.")
SEMANTIC_TYPE = "model_authored_hypothesis_review_not_scientific_validation"


def _key(value):
    return value["hypothesis_id"], value.get("alternative_id", "")


def _ref(value):
    return {"hypothesis_id": value["hypothesis_id"], "alternative_id": value.get("alternative_id", "")}


def _unique(values, label):
    if any(isinstance(v, str) and not v.strip() for v in values) or len(values) != len(set(values)):
        raise ValueError(label + " ID 또는 값이 비었거나 중복됐습니다.")


def _explanations(check, loop):
    """Use declared identities; free-text alternatives do not acquire invented IDs."""
    hypotheses = {h["id"]: h for h in loop["hypotheses"]}
    scope = {s["hypothesis_id"]: set(s["part_ids"]) for s in check.get("scope_targets", [])}
    rows = []
    for hid in check["hypothesis_ids"]:
        hypothesis = hypotheses[hid]
        alternatives = hypothesis.get("conditional_alternatives", [])
        for explanation in alternatives or [hypothesis]:
            parts = explanation.get("part_ids", [])
            if alternatives and hid in scope and parts and not scope[hid].intersection(parts):
                continue
            rows.append({"hypothesis_id": hid, "alternative_id": explanation["id"] if alternatives else "",
                         "statement": explanation["statement"], "part_ids": parts,
                         "conditions": explanation.get("conditions", [])})
    return rows


def validate(value, state, loop):
    """Validate structure and decision-local references; missing sources survive for review."""
    jsonschema.validate(value, CURRENT_SCHEMA if isinstance(value, dict) and value.get("schema_version") == "2" else SCHEMA)
    hypotheses = {h["id"]: h for h in loop["hypotheses"]}
    checks = {c["id"]: c for c in loop["next_checks"]}
    _unique([s["id"] for s in value["causal_steps"]], "인과 단계")
    _unique([o["check_id"] for o in value["observations"]], "관측 검토")
    for step in value["causal_steps"]:
        hypothesis = hypotheses.get(step["hypothesis_id"])
        if hypothesis is None:
            raise ValueError("인과 단계가 현재 판단의 가설을 참조하지 않습니다.")
        parts = {p["id"] for p in (hypothesis.get("assessment_scope") or {}).get("parts", [])}
        if step["part_id"] and step["part_id"] not in parts:
            raise ValueError("인과 단계의 부분 ID가 해당 가설에 없습니다.")
        if not step["claim"].strip():
            raise ValueError("검토할 인과 단계의 주장을 명시해 주세요.")
        _unique([g["id"] for g in step["evidence_groups"]], "근거 묶음")
    for observation in value["observations"]:
        check = checks.get(observation["check_id"])
        if check is None:
            raise ValueError("관측 검토가 현재 판단의 다음 확인에 없습니다.")
        allowed = {_key(r) for r in _explanations(check, loop)}
        _unique([_key(p) for p in observation["predictions"]], "설명 예측")
        _unique([o["outcome_index"] for o in observation["outcomes"]], "결과 검토")
        count = len(check["possible_outcomes"])
        for outcome in observation["outcomes"]:
            if outcome["outcome_index"] >= count:
                raise ValueError("관측 검토의 결과 번호가 해당 확인에 없습니다.")
        for prediction in observation["predictions"]:
            if _key(prediction) not in allowed:
                raise ValueError("예측의 가설·조건별 설명이 이 확인의 범위에 없습니다.")
            _unique(prediction["outcome_indices"], "예측 결과")
            _unique(prediction["source_ids"], "예측 출처")
            if any(index >= count for index in prediction["outcome_indices"]):
                raise ValueError("예측 결과 번호가 해당 확인에 없습니다.")
    if value["schema_version"] == "2":
        _validate_scope(value, loop)


def _validate_scope(value, loop):
    """Check declared coverage, not whether an authored scientific judgment is true."""
    for field, id_field, linked, label in (
            ("hypotheses", "hypothesis_id", value["causal_steps"], "가설"),
            ("checks", "check_id", value["observations"], "다음 확인")):
        rows = value["scope"][field]
        _unique([row[id_field] for row in rows], label + " 검토 범위")
        expected = {row["id"] for row in loop["hypotheses" if field == "hypotheses" else "next_checks"]}
        supplied = {row[id_field] for row in rows}
        if supplied != expected:
            raise ValueError(f"{label}별 검토 범위를 모두 기록해 주세요. 누락: {sorted(expected-supplied)!r}; "
                             f"현재 판단에 없는 ID: {sorted(supplied-expected)!r}. "
                             "검토하지 못한 항목은 사유와 not_reviewed를 명시하세요.")
        linked_ids = {row[id_field] for row in linked}
        for row in rows:
            if not row["reason"].strip():
                raise ValueError(f"{label} {row[id_field]!r}의 검토 범위와 사유를 명시해 주세요.")
            if (row["status"] == "reviewed") != (row[id_field] in linked_ids):
                raise ValueError(f"{label} {row[id_field]!r}의 검토 상태와 연결된 검토가 다릅니다. "
                                 "reviewed에는 실제 검토를 연결하고, 미검토를 완료로 표시하지 마세요.")
    checks = {c["id"]: c for c in loop["next_checks"]}
    for observation in value["observations"]:
        check = checks[observation["check_id"]]
        if {o["outcome_index"] for o in observation["outcomes"]} != set(range(len(check["possible_outcomes"]))):
            raise ValueError(f"다음 확인 {check['id']!r}의 모든 결과에 해석 조건을 기록해 주세요.")
        if {_key(p) for p in observation["predictions"]} != {_key(p) for p in _explanations(check, loop)}:
            raise ValueError(f"다음 확인 {check['id']!r}의 비교할 설명별 예상을 모두 기록해 주세요. "
                             "예상을 정할 수 없으면 coverage: unknown과 그 이유를 남기세요.")
        if any(not p["rationale"].strip() for p in observation["predictions"]):
            raise ValueError("설명별 예상 또는 미확인 이유를 명시해 주세요.")


def loop_sha256(loop):
    encoded = json.dumps(loop, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _pointer(document, path):
    if path == "":
        return document
    if not path.startswith("/") or re.search(r"~(?![01])", path):
        raise ValueError("invalid_json_pointer")
    node = document
    for token in path[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if token not in node:
                raise ValueError("path_not_found")
            node = node[token]
        elif isinstance(node, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token) or int(token) >= len(node):
                raise ValueError("path_not_found")
            node = node[int(token)]
        else:
            raise ValueError("path_not_found")
    return node


def check_anchor(store, wid, anchor):
    """Check the exact named string, never normalized text elsewhere in a row."""
    result = {**copy.deepcopy(anchor), "status": "rejected", "source_identity_only": True,
              "causal_support_automatically_verified": False}
    try:
        artifact = store.artifact(wid, anchor["artifact_id"])
    except KeyError:
        return {**result, "reason": "artifact_not_in_this_research"}
    except ValueError:
        return {**result, "reason": "stored_content_integrity_failed"}
    digest = hashlib.sha256(artifact["content"]).hexdigest()
    result.update(kind=artifact["kind"], source_sha256=digest)
    if digest != artifact["sha256"]:
        return {**result, "reason": "stored_content_integrity_failed"}
    if not anchor["quote"].strip():
        return {**result, "reason": "empty_quote"}
    try:
        document = json.loads(artifact["content"])
    except (ValueError, UnicodeError):
        return {**result, "reason": "source_not_json"}
    try:
        text = _pointer(document, anchor["path"])
    except ValueError as exc:
        return {**result, "reason": str(exc)}
    if not isinstance(text, str):
        return {**result, "reason": "anchor_target_not_string"}
    if anchor["quote"] not in text:
        return {**result, "reason": "quote_not_at_exact_path"}
    return {**result, "status": "verified", "match": "exact_substring_at_json_pointer"}


def _sources(store, wid, state, ids):
    messages = {e["body"]["message_id"]: e for e in state.get("events", []) if e["body"].get("message_id")}
    results = []
    for sid in ids:
        if sid in messages:
            results.append({"source_id": sid, "status": "present", "source_type": "message",
                            "identity_only": True})
            continue
        try:
            artifact = store.artifact(wid, sid)
        except KeyError:
            results.append({"source_id": sid, "status": "missing", "reason": "source_not_in_this_research"})
        except ValueError:
            results.append({"source_id": sid, "status": "rejected", "reason": "stored_content_integrity_failed"})
        else:
            results.append({"source_id": sid, "status": "present", "source_type": "artifact",
                            "source_sha256": artifact["sha256"], "kind": artifact["kind"], "identity_only": True})
    return results


def _explicit(text):
    return text.strip().casefold() not in {"", "unknown", "unspecified", "not established", "미확인", "미정", "알 수 없음"}


def _relations(left, right, loop):
    if left["hypothesis_id"] != right["hypothesis_id"]:
        return []
    hypothesis = next(h for h in loop["hypotheses"] if h["id"] == left["hypothesis_id"])
    pair = {left["alternative_id"], right["alternative_id"]}
    return [{"from_alternative_id": a["id"], **copy.deepcopy(r)}
            for a in (hypothesis.get("conditional_alternatives") or []) if a["id"] in pair
            for r in a.get("relations", []) if r["alternative_id"] in pair and r["alternative_id"] != a["id"]]


def _membership(row, index):
    prediction = row["prediction"]
    if prediction is None or prediction["coverage"] == "unknown":
        return "unknown"
    if index in prediction["outcome_indices"]:
        return "predicted"
    return "excluded" if prediction["coverage"] == "complete" else "unknown"


def _pair(left, right, index, guards, loop):
    relations = _relations(left, right, loop)
    # A prediction-set difference does not declare that biological explanations
    # exclude one another. Missing/cross-hypothesis relations stay unknown.
    declared = {r["relation"] for r in relations}
    exclusive = declared == {"exclusive_under_conditions"} and all(
        _explicit(r.get("conditions", "")) for r in relations)
    relation_status = "can_coexist" if "can_coexist" in declared else (
        "exclusive_under_conditions" if exclusive else "unknown")
    predictions = [left["prediction"], right["prediction"]]
    retrospective = any(p and p["origin"] == "reconstructed_after_result" for p in predictions)
    pair = {"left": _ref(left), "right": _ref(right), "status": "unresolved",
            "compatible_explanation": None, "excluded_explanation": None,
            "reasons": list(guards), "relations": relations, "requires_joint_prediction": False,
            "relationship_status": relation_status, "prediction_set_status": "unresolved",
            "retrospective": retrospective, "selection_eligible": False}
    if any(p is None for p in predictions):
        pair["reasons"].append("missing_prediction")
        return pair
    members = [_membership(r, index) for r in (left, right)]
    complete = all(p["coverage"] == "complete" for p in predictions)
    would_separate = complete and set(members) == {"predicted", "excluded"}
    pair["prediction_set_status"] = ("separating" if would_separate else
        "shared" if members == ["predicted", "predicted"] else
        "neither_predicted" if complete and members == ["excluded", "excluded"] else "unresolved")
    if would_separate and relation_status == "can_coexist":
        pair["requires_joint_prediction"] = True
        pair["reasons"].append("coexisting_explanations_require_joint_prediction")
    elif would_separate and not exclusive:
        pair["reasons"].append("explanation_relationship_unknown")
    if guards or pair["requires_joint_prediction"]:
        return pair
    if members == ["predicted", "predicted"]:
        pair["status"] = "shared"
    elif not complete:
        pair["reasons"].append("incomplete_or_unknown_prediction_set")
    elif members == ["excluded", "excluded"]:
        pair["status"] = "neither_predicted"
        pair["reasons"].append("outcome_outside_both_prediction_sets")
    elif would_separate:
        pair["status"] = "separating"
        pair["compatible_explanation"] = _ref(left if members[0] == "predicted" else right)
        pair["excluded_explanation"] = _ref(right if members[0] == "predicted" else left)
        missing_sources = any(s["status"] != "present" for r in (left, right) for s in r["source_checks"])
        pair["selection_eligible"] = exclusive and not retrospective and not missing_sources
        if retrospective:
            pair["reasons"].append("retrospective_prediction_not_prospective_discrimination")
        if missing_sources:
            pair["reasons"].append("prediction_source_unresolved")
    return pair


def _link_diagnostics(check, result):
    rows = {_key(r): r for r in result["explanations"]}
    outcomes = {o["outcome_index"]: o for o in result["outcomes"]}
    diagnostics = []
    for link in check.get("outcome_links", []):
        index = link["outcome_index"]
        outcome = outcomes.get(index)
        for effect in link["effects"]:
            for alt in effect["alternative_ids"] or [""]:
                target = {"hypothesis_id": effect["hypothesis_id"], "alternative_id": alt}
                row = rows.get(_key(target))
                status = "unresolved_comparison"
                if effect["relation"] == "unresolved":
                    status = "declared_unresolved"
                elif row is None:
                    status = "parent_effect_not_directly_comparable" if not alt else "missing_prediction"
                elif row["prediction"] is None:
                    status = "missing_prediction"
                elif outcome and not outcome["guard_reasons"]:
                    involved = [p for p in outcome["pairs"] if target in (p["left"], p["right"])]
                    member = _membership(row, index)
                    if any(p["requires_joint_prediction"] for p in involved):
                        status = "joint_prediction_required"
                    elif row["retrospective"]:
                        status = "retrospective_prediction"
                    elif row["prediction"]["coverage"] != "complete":
                        status = "incomplete_prediction_set"
                    elif (effect["relation"], member) in (("supports", "excluded"), ("challenges", "predicted")):
                        status = "conflicts_with_prediction_set"
                    elif effect["relation"] == "supports" and member == "predicted" and not any(p["status"] == "separating" for p in involved):
                        status = "compatible_but_not_discriminating"
                    else:
                        status = "consistent_with_prediction_set"
                diagnostics.append({"outcome_index": index, **target, "declared_relation": effect["relation"],
                                    "status": status, "automatic_rewrite": False,
                                    "meaning": "Prediction-set comparison only; not an evidential likelihood or causal verdict."})
    return diagnostics


def _observation(check, authored, loop, source_checks):
    predictions = {_key(p): p for p in authored["predictions"]} if authored else {}
    interpretations = {o["outcome_index"]: o["interpretation"] for o in authored["outcomes"]} if authored else {}
    rows = []
    for explanation in _explanations(check, loop):
        prediction = predictions.get(_key(explanation))
        sources = source_checks.get((check["id"], _key(explanation)), [])
        rows.append({**copy.deepcopy(explanation), "prediction": copy.deepcopy(prediction),
                     "source_checks": sources, "source_basis": "not_named" if not prediction or not prediction["source_ids"] else "recorded_references_only",
                     "retrospective": bool(prediction and prediction["origin"] == "reconstructed_after_result")})
    validity = bool(authored and authored["validity_requirements"] and all(_explicit(s) for s in authored["validity_requirements"]))
    precision = bool(authored and _explicit(authored["precision_requirement"]))
    result = {"check_id": check["id"], "status": "reviewed" if authored else "not_reviewed",
              "validity_requirements_explicit": validity, "precision_requirement_explicit": precision,
              "requirements_are_model_declarations": True, "explanations": rows,
              "missing_explanations": [_ref(r) for r in rows if r["prediction"] is None], "outcomes": []}
    for index, possible in enumerate(check["possible_outcomes"]):
        interpretation = interpretations.get(index)
        guards = []
        if interpretation != "adequate_measurement":
            guards.append(interpretation or "outcome_not_reviewed")
        if not validity:
            guards.append("measurement_validity_requirements_missing")
        if not precision:
            guards.append("precision_requirement_missing")
        pairs = [_pair(a, b, index, guards, loop) for a, b in itertools.combinations(rows, 2)]
        joint = {_key(ref) for pair in pairs if pair["requires_joint_prediction"] for ref in (pair["left"], pair["right"])}
        applicable = lambda row: not guards and _key(row) not in joint
        result["outcomes"].append({"outcome_index": index, "observation": possible["observation"],
                                   "interpretation": interpretation, "guard_reasons": guards,
                                   "predicted_explanations": [_ref(r) for r in rows if applicable(r) and _membership(r, index) == "predicted"],
                                   "excluded_explanations": [_ref(r) for r in rows if applicable(r) and _membership(r, index) == "excluded"],
                                   "unknown_explanations": [_ref(r) for r in rows if not applicable(r) or _membership(r, index) == "unknown"],
                                   "pairs": pairs})
    result["outcome_link_diagnostics"] = _link_diagnostics(check, result)
    return result


def prepare(store, wid, rev, value, loop):
    """Return one sidecar record for atomic publication; perform no writes."""
    state = store.snapshot(wid)
    jsonschema.validate(value, CURRENT_SCHEMA if value.get("schema_version") == "2" else SCHEMA)
    from .hypothesis_reference_resolution import resolve
    authored = copy.deepcopy(value)
    value, resolutions = resolve(store, wid, authored, loop)
    validate(value, state, loop)
    step_checks = []
    for step in value["causal_steps"]:
        groups = []
        for group in step["evidence_groups"]:
            anchors = [check_anchor(store, wid, anchor) for anchor in group["anchors"]]
            groups.append({"group_id": group["id"], "anchor_checks": anchors,
                           "all_anchors_verified": bool(anchors) and all(a["status"] == "verified" for a in anchors),
                           "source_identity_only": True, "causal_support_automatically_verified": False,
                           "issues": ([] if anchors else ["no_anchors"]) + [a["reason"] for a in anchors if a["status"] != "verified"]})
        step_checks.append({"step_id": step["id"], "hypothesis_id": step["hypothesis_id"], "part_id": step["part_id"],
                            "evidence_groups": groups, "issues": [] if groups else ["no_evidence_groups"]})
    reviews = {o["check_id"]: o for o in value["observations"]}
    source_checks = {(o["check_id"], _key(p)): _sources(store, wid, state, p["source_ids"])
                     for o in value["observations"] for p in o["predictions"]}
    observations = [_observation(c, reviews.get(c["id"]), loop, source_checks) for c in loop["next_checks"]]
    anchors = [a for s in step_checks for g in s["evidence_groups"] for a in g["anchor_checks"]]
    pairs = [p for o in observations for outcome in o["outcomes"] for p in outcome["pairs"]]
    summary = {"causal_steps": len(step_checks), "verified_anchors": sum(a["status"] == "verified" for a in anchors),
               "failed_anchors": sum(a["status"] != "verified" for a in anchors),
               "reviewed_checks": len(reviews), "unreviewed_check_ids": [o["check_id"] for o in observations if o["status"] == "not_reviewed"],
               "missing_prediction_rows": sum(len(o["missing_explanations"]) for o in observations),
               "separating_pair_outcomes": sum(p["status"] == "separating" for p in pairs),
               "eligible_pair_outcomes": sum(p["selection_eligible"] for p in pairs),
               "joint_prediction_required_pair_outcomes": sum(p["requires_joint_prediction"] for p in pairs),
               "retrospective_prediction_rows": sum(r["retrospective"] for o in observations for r in o["explanations"]),
               "reference_resolutions": len(resolutions), "scientific_validation": False}
    if value["schema_version"] == "2":
        summary["declared_scope"] = {field: {status: [row[id_field] for row in value["scope"][field]
            if row["status"] == status] for status in ("reviewed", "not_reviewed", "not_applicable")}
            for field, id_field in (("hypotheses", "hypothesis_id"), ("checks", "check_id"))}
    digest = loop_sha256(loop)
    return {"kind": "hypothesis_review", "title": "인과 근거·설명별 예상·구별할 관측 검토",
            "value": {"schema_version": "1", "semantic_type": SEMANTIC_TYPE, "based_rev": rev,
                      "loop_sha256": digest, "review": copy.deepcopy(value), "causal_step_checks": step_checks,
                      "observation_checks": observations, "summary": summary,
                      **({"authored_review": authored, "reference_resolutions": resolutions} if resolutions else {})},
            "meta": {"based_rev": rev, "loop_sha256": digest, "semantic_type": SEMANTIC_TYPE}}


def bind_record(record, decision_id):
    """Called inside atomic finalization with the preallocated exact decision ID."""
    if record.get("kind") != "hypothesis_review" or not isinstance(decision_id, str) or not decision_id.strip():
        raise ValueError("가설 검토를 연결할 판단 ID가 필요합니다.")
    bound = copy.deepcopy(record)
    bound["meta"]["decision_id"] = decision_id
    bound["value"]["decision_id"] = decision_id
    return bound


def view(store, wid, state):
    """Only the review explicitly attached to this exact published decision is current."""
    event = next((e for e in reversed(state["events"]) if e["kind"] == "decision_published"), None)
    if event is None:
        return None
    decision_id = event["body"]["receipt_id"]
    artifact_id = None
    def unavailable(reason):
        return {"status": "binding_mismatch", "artifact_id": artifact_id, "published_decision_id": decision_id,
                "is_current_input": False, "issues": [reason], "review": None,
                "causal_step_checks": [], "observation_checks": [], "summary": {}}
    try:
        decision = store.artifact(wid, decision_id)
        proposal = json.loads(decision["content"])
        if decision["kind"] != "decision_proposal" or proposal != state.get("decision"):
            return unavailable("published_decision_content_mismatch")
        artifact_id = decision["meta"].get("finalization_records", {}).get("hypothesis_review")
        if not artifact_id:
            return None
        artifact = store.artifact(wid, artifact_id)
        value = json.loads(artifact["content"])
        digest = loop_sha256(proposal["research_loop"])
        rev = proposal["based_on_state_rev"]
        if artifact["kind"] != "hypothesis_review" or value.get("schema_version") != "1":
            return unavailable("review_kind_or_version_mismatch")
        if value.get("decision_id") != decision_id or artifact["meta"].get("decision_id") != decision_id:
            return unavailable("review_bound_to_another_decision")
        if value.get("based_rev") != rev or artifact["meta"].get("based_rev") != rev or state.get("decision_rev") != rev:
            return unavailable("review_revision_mismatch")
        if value.get("loop_sha256") != digest or artifact["meta"].get("loop_sha256") != digest:
            return unavailable("review_loop_mismatch")
        validate(value["review"], state, proposal["research_loop"])
    except (KeyError, ValueError, TypeError, jsonschema.ValidationError):
        return unavailable("published_review_unavailable_or_invalid")
    return {**value, "status": "available", "artifact_id": artifact_id, "published_decision_id": decision_id,
            "decision_sha256": decision["sha256"], "current_revision": state["rev"],
            "is_current_input": state["rev"] == rev}
