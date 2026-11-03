"""Compare retained pathway explanations without fitting or assigning probabilities."""
from __future__ import annotations

from collections import Counter
import hashlib
import itertools
import json
import math

ARG_SCHEMA = {
    "type": "object",
    "properties": {"artifact_ids": {"type": "array", "items": {"type": "string", "minLength": 1},
                                     "minItems": 2, "maxItems": 8, "uniqueItems": True}},
    "required": ["artifact_ids"], "additionalProperties": False,
}
SCHEMA = ARG_SCHEMA
_ROOT = "Perturbation"
_KNOWN_STATUSES = {"succeeded", "partial", "failed", "unassessed"}
_IO_OPTIONS = {"solverPath", "outputFolder", "workdir", "lpFilename", "cleanTmpFiles", "keepLPFiles"}
_REQUIRED_OPTIONS = {"solver", "betaWeight", "poolrelGap", "timelimit", "threads"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _edges(rows):
    if not isinstance(rows, list):
        raise ValueError("상호작용 행을 확인할 수 없습니다.")
    result = []
    for row in rows:
        source, target = row.get("source", row.get("Node1")), row.get("target", row.get("Node2"))
        sign = row.get("interaction", row.get("sign", row.get("Sign")))
        if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
            raise ValueError("상호작용의 출발·도착 노드가 없습니다.")
        if not _number(sign) or sign not in (-1, 1):
            raise ValueError("상호작용 부호가 -1 또는 1이 아닙니다.")
        if source != _ROOT and target != _ROOT and not row.get("artificial_root_edge", False):
            result.append((source, int(sign), target))
    return result


def _measurements(rows):
    if not isinstance(rows, list) or not rows:
        return None
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("source"), str) or not row["source"] or not _number(row.get("score")):
            return None
        result.append((row["source"], float(row["score"])))
    return result if len({r[0] for r in result}) == len(result) else None


def _single_resource(rows):
    values = {r.get("resource") for r in rows if isinstance(r, dict) and r.get("resource")}
    return next(iter(values)) if len(values) == 1 else None


def _known_sha(value):
    return value if isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value) else None


def _object(value):
    return value if isinstance(value, dict) else {}


def _invalid_constant(value):
    raise ValueError("JSON의 수가 유한하지 않습니다.")


def _inputs(content):
    extra = content.get("comparison_inputs") or {}
    issues = []
    if not isinstance(extra, dict):
        extra = {}
        issues.append("comparison_inputs_not_an_object")
    original_rows = content.get("selected_inferred_observations", [])
    original_rows = original_rows if isinstance(original_rows, list) else []
    original_measurements = _measurements(original_rows)
    measurements = _measurements(extra.get("measurements")) if "measurements" in extra else original_measurements
    if original_measurements is not None and measurements is not None and sorted(original_measurements) != sorted(measurements):
        measurements = None
        issues.append("recorded_measurements_disagree_with_result")
    network = None
    if "network" in extra:
        try:
            network = _edges(extra["network"])
        except (ValueError, TypeError, AttributeError):
            issues.append("recorded_prior_unreadable")
    binding = _object(content.get("source_binding"))
    resource = extra.get("regulon", {})
    resource = resource if isinstance(resource, dict) else {}
    resource_name = resource.get("name") or binding.get("resource") or _single_resource(original_rows)
    dataset = extra.get("dataset", {})
    dataset = dataset if isinstance(dataset, dict) else {}
    options = extra.get("solver_options")
    options = {k: v for k, v in options.items() if k not in _IO_OPTIONS} if isinstance(options, dict) and options else None
    if options is not None and not _REQUIRED_OPTIONS.issubset(options):
        options = None
        issues.append("operative_solver_options_incomplete")
    fingerprint = _object(content.get("resource_fingerprint"))
    files = _object(fingerprint.get("files"))
    versions = _object(content.get("versions"))
    engine = extra.get("engine") or {
        "R": versions.get("R"), "CARNIVAL": versions.get("CARNIVAL"),
        "cbc_sha256": files.get("cbc"), "CARNIVAL_rdb_sha256": files.get("CARNIVAL_R_CARNIVAL.rdb"),
    }
    engine = engine if isinstance(engine, dict) and all(engine.get(k) for k in ("R", "CARNIVAL", "cbc_sha256", "CARNIVAL_rdb_sha256")) else None
    identities = [r[0] for r in measurements] if measurements is not None else None
    signs = sorted((tf, 1 if score > 0 else -1 if score < 0 else 0) for tf, score in measurements) if measurements is not None else None
    facts = {
        "prior_signed_edges": _digest(sorted(set(network))) if network is not None else None,
        "prior_order": _digest(network) if network is not None else None,
        "selected_tf_ids": sorted(identities) if identities is not None else None,
        "selected_tf_order": identities,
        "selected_tf_scores": sorted(measurements) if measurements is not None else None,
        "selected_tf_signs": signs,
        "regulon_name": resource_name,
        "regulon_definition": _known_sha(resource.get("sha256")),
        "dataset": _known_sha(dataset.get("sha256")),
        "solver_options": options,
        "engine": engine,
    }
    return facts, network, issues


def _decode(artifact):
    raw = artifact.get("content")
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != artifact.get("sha256"):
        raise ValueError("비교할 저장 자료의 원문 해시가 일치하지 않습니다.")
    if artifact.get("kind") != "pathway_hypotheses":
        raise ValueError("저장한 경로 후보 결과를 선택해 주세요.")
    try:
        content = json.loads(raw, parse_constant=_invalid_constant)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("저장한 경로 결과를 JSON으로 읽을 수 없습니다.") from exc
    if not isinstance(content, dict) or content.get("semantic_type") != "conditional_pathway_hypotheses":
        raise ValueError("경로 결과의 자료 종류를 확인할 수 없습니다.")
    return content


def _runs(artifact, content):
    facts, prior, input_issues = _inputs(content)
    prior_nodes = {n for edge in prior for n in (edge[0], edge[2])} if prior is not None else None
    status = content.get("status", "unassessed")
    status = status if status in _KNOWN_STATUSES else "unassessed"
    author = _object(content.get("author_result"))
    sifs, attributes = author.get("sifAll"), author.get("attributesAll")
    has_solutions = isinstance(sifs, list) and bool(sifs)
    solutions = sifs if has_solutions else [None]
    if not isinstance(attributes, list):
        attributes = []
    solver = _object(content.get("solver_review"))
    objective = solver.get("objective_value")
    objective = float(objective) if _number(objective) else None
    result = []
    for index, solution in enumerate(solutions):
        issues = list(input_issues)
        edges, nodes = set(), {}
        readable = solution is not None
        node_readable = False
        try:
            if readable:
                edges = set(_edges(solution))
            else:
                issues.append("returned_network_unavailable")
        except (ValueError, TypeError, AttributeError):
            readable, edges = False, set()
            issues.append("returned_network_unreadable")
        node_rows = attributes[index] if index < len(attributes) else None
        if not isinstance(node_rows, list):
            issues.append("signed_node_states_unavailable")
        else:
            try:
                for row in node_rows:
                    name, activity = row.get("Nodes"), row.get("Activity")
                    if name == _ROOT:
                        continue
                    if not isinstance(name, str) or not name or not _number(activity) or activity not in (-1, 0, 1):
                        raise ValueError("저장한 노드 상태를 해석할 수 없습니다.")
                    if name in nodes and nodes[name] != int(activity):
                        raise ValueError("노드 상태가 중복되어 다릅니다.")
                    nodes[name] = int(activity)
                node_readable = {n for e in edges for n in (e[0], e[2])}.issubset(nodes)
                if not node_readable:
                    issues.append("signed_node_states_incomplete")
            except (ValueError, TypeError, AttributeError):
                nodes = {}
                issues.append("signed_node_states_unreadable")
        if prior is not None and not edges.issubset(set(prior)):
            issues.append("returned_edges_outside_recorded_prior")
            facts = {**facts, "prior_signed_edges": None, "prior_order": None}
            prior, prior_nodes = None, None
        run_status = status if readable or status in {"failed", "unassessed"} else "unassessed"
        assessed = readable and run_status in {"succeeded", "partial"}
        result.append({
            "run_id": f"{artifact['id']}/network/{index + 1}",
            "artifact_id": artifact["id"], "artifact_sha256": artifact["sha256"],
            "title": artifact.get("title") or content.get("title") or artifact["id"],
            "network_index": index + 1, "status": run_status, "output_assessed": assessed,
            "node_states_assessed": assessed and node_readable,
            "origin": content.get("origin", {"kind": "native_saved_result"}),
            "source_records": content.get("source_records", []),
            "source_binding": content.get("source_binding"),
            "source_conditions": content.get("source_conditions", []),
            "conditions": content.get("conditions", []),
            "selection_reason": content.get("selection_reason"),
            "search_scope": content.get("search_scope", {}),
            "solver_review": {**solver, "objective_value": objective, "unique_optimum_established": False},
            "input_facts": facts, "input_issues": issues,
            "selected_input_nodes": facts["selected_tf_ids"],
            "input_coverage": {"full_selected_prior_recorded": prior is not None,
                "exact_selected_scores_recorded": facts["selected_tf_scores"] is not None,
                "solver_options_recorded": facts["solver_options"] is not None},
            "biological_nodes": [{"node": n, "state": state} for n, state in sorted(nodes.items())],
            "biological_edges": [{"source": s, "sign": v, "target": t} for s, v, t in sorted(edges)],
            "_nodes": nodes, "_edges": edges, "_prior_nodes": prior_nodes, "_prior_edges": set(prior) if prior is not None else None,
        })
    return result


def _axis(left, right):
    return {"status": "unknown" if left is None or right is None else "same" if left == right else "different",
            "left": left, "right": right}


def _pair(left, right):
    axes = {key: _axis(left["input_facts"][key], right["input_facts"][key]) for key in left["input_facts"]}
    changed = [k for k, v in axes.items() if v["status"] == "different"]
    unknown = [k for k, v in axes.items() if v["status"] == "unknown"]
    groups = []
    for name, keys in [
        ("prior", {"prior_signed_edges"}), ("prior_order", {"prior_order"}),
        ("input", {"selected_tf_ids", "selected_tf_order", "selected_tf_scores", "selected_tf_signs"}),
        ("regulon", {"regulon_name", "regulon_definition"}),
        ("dataset", {"dataset"}), ("solver", {"solver_options", "engine"}),
    ]:
        if set(changed) & keys and not (name == "prior_order" and "prior" in groups):
            groups.append(name)
    if not groups:
        kind = "same_recorded_settings" if not unknown else "unresolved_settings"
    elif len(groups) > 1:
        kind = "multiple_axes_changed"
    elif groups == ["solver"]:
        kind = "solver_only" if not unknown else "solver_change_with_unresolved_axes"
    else:
        kind = "changed_" + groups[0] + ("_with_unresolved_axes" if unknown else "")
    assessed = left["output_assessed"] and right["output_assessed"]
    left_nodes, right_nodes = left["_nodes"], right["_nodes"]
    nodes_assessed = left["node_states_assessed"] and right["node_states_assessed"]
    common = set(left_nodes) & set(right_nodes) if nodes_assessed else set()
    same_nodes = sorted(n for n in common if left_nodes[n] == right_nodes[n])
    changed_nodes = [{"node": n, "left_state": left_nodes[n], "right_state": right_nodes[n]}
                     for n in sorted(common) if left_nodes[n] != right_nodes[n]]
    objective_left = left["solver_review"]["objective_value"]
    objective_right = right["solver_review"]["objective_value"]
    objective_equal = None if objective_left is None or objective_right is None else objective_left == objective_right
    def edges(values):
        return [{"source": s, "sign": sign, "target": t} for s, sign, t in sorted(values)]
    return {
        "left_run_id": left["run_id"], "right_run_id": right["run_id"],
        "comparison_kind": kind, "axes": axes, "changed_axes": changed, "unexamined_axes": unknown,
        "output_comparison_status": "complete" if assessed and nodes_assessed and left["status"] == right["status"] == "succeeded" else "partial" if assessed else "unassessed",
        "node_comparison_status": "complete" if nodes_assessed and left["status"] == right["status"] == "succeeded" else "partial" if nodes_assessed else "unassessed",
        "edge_comparison_status": "complete" if assessed and left["status"] == right["status"] == "succeeded" else "partial" if assessed else "unassessed",
        "conserved_signed_nodes": same_nodes, "different_signed_nodes": changed_nodes,
        "left_only_nodes": sorted(set(left_nodes) - set(right_nodes)) if nodes_assessed else [],
        "right_only_nodes": sorted(set(right_nodes) - set(left_nodes)) if nodes_assessed else [],
        "conserved_signed_edges": edges(left["_edges"] & right["_edges"]) if assessed else [],
        "left_only_edges": edges(left["_edges"] - right["_edges"]) if assessed else [],
        "right_only_edges": edges(right["_edges"] - left["_edges"]) if assessed else [],
        "objective_comparison": {"left": objective_left, "right": objective_right,
            "equal_recorded_value": objective_equal, "unique_optimum_established": False,
            "equality_is_not_a_probability_or_unique_mechanism": True},
    }


def _state(run, item, kind):
    if not run["output_assessed"] or (kind == "node" and not run["node_states_assessed"]):
        return {"run_id": run["run_id"], "status": "unassessed", "run_status": run["status"]}
    selected = run["_nodes"] if kind == "node" else run["_edges"]
    if item in selected:
        return {"run_id": run["run_id"], "status": "returned", "run_status": run["status"],
                **({"state": run["_nodes"][item]} if kind == "node" else {})}
    prior = run["_prior_nodes"] if kind == "node" else run["_prior_edges"]
    return {"run_id": run["run_id"], "run_status": run["status"],
            "status": "not_returned_scope_unknown" if prior is None else "not_selected" if item in prior else "outside_search_scope"}


def compare_artifacts(artifacts):
    """Pure worker API. Content hashes are verified; no paths, DBs or solvers opened."""
    if not isinstance(artifacts, list) or not 2 <= len(artifacts) <= 8:
        raise ValueError("저장한 경로 결과 2~8개를 선택해 주세요.")
    ids = [a.get("id") for a in artifacts]
    if any(not isinstance(aid, str) or not aid for aid in ids) or len(set(ids)) != len(ids):
        raise ValueError("서로 다른 저장 자료를 선택해 주세요. 복사 횟수를 지지도로 세지 않습니다.")
    runs = []
    for artifact in artifacts:
        runs.extend(_runs(artifact, _decode(artifact)))
    rows = []
    for node in sorted(set().union(*(set(r["_nodes"]) for r in runs))):
        states = [_state(r, node, "node") for r in runs]
        for state, run in zip(states, runs):
            selected = run["selected_input_nodes"]
            state["is_selected_input"] = node in selected if selected is not None else None
        values = {s["state"] for s in states if s["status"] == "returned"}
        complete = all(s["status"] == "returned" and s["run_status"] == "succeeded" for s in states)
        classification = "different_signed_state" if len(values) > 1 else "conserved_signed_state" if complete else "conditional_or_unassessed"
        rows.append({"record_type": "node", "node": node, "classification": classification, "states": states,
                     "selected_input_in_runs": [s["run_id"] for s in states if s["is_selected_input"] is True]})
    for edge in sorted(set().union(*(r["_edges"] for r in runs))):
        states = [_state(r, edge, "edge") for r in runs]
        complete = all(s["status"] == "returned" and s["run_status"] == "succeeded" for s in states)
        rows.append({"record_type": "edge", "source": edge[0], "sign": edge[1], "target": edge[2],
            "classification": "conserved_signed_edge" if complete else "conditional_or_unassessed", "states": states})
    pairwise = [_pair(left, right) for left, right in itertools.combinations(runs, 2)]
    counts = Counter(r["status"] for r in runs)
    return {
        "status": "succeeded", "semantic_type": "pathway_explanation_comparison", "schema_version": 1,
        "rows": rows, "runs": [{k: v for k, v in r.items() if not k.startswith("_")} for r in runs],
        "pairwise": pairwise,
        "summary": {"input_artifacts": len(artifacts), "returned_runs": len(runs),
            "run_status_counts": {status: counts[status] for status in sorted(_KNOWN_STATUSES)},
            "conserved_signed_nodes": sum(r["classification"] == "conserved_signed_state" for r in rows),
            "conserved_nodes_not_selected_as_input": sum(r["classification"] == "conserved_signed_state" and all(s.get("is_selected_input") is False for s in r["states"]) for r in rows),
            "different_signed_nodes": sum(r["classification"] == "different_signed_state" for r in rows),
            "conserved_signed_edges": sum(r["classification"] == "conserved_signed_edge" for r in rows),
            "changed_axes": sorted({k for p in pairwise for k in p["changed_axes"]}),
            "unexamined_axes": sorted({k for p in pairwise for k in p["unexamined_axes"]}),
            "all_outputs_succeeded": all(r["status"] == "succeeded" for r in runs),
            "all_node_states_assessed": all(r["node_states_assessed"] for r in runs),
            "new_optimization_runs": 0, "unique_optimum_established": False,
            "probability_estimation_performed": False, "independence_assessed": False},
        "limits": [
            "저장한 계산 조건과 반환된 설명을 비교합니다. 새 최적화나 생물학적 검증을 수행한 결과가 아닙니다.",
            "공통으로 반환된 노드·연결은 이 계산들에서의 일치입니다. 반복 횟수나 동일 목적값을 인과 확률·효능·유일한 기전으로 바꾸지 않습니다.",
            "선택되지 않음, 탐색 범위 밖, 실패·부분 결과, 원 입력 미확인은 서로 다른 상태입니다. 생물학적 부재로 합치지 않습니다.",
            "전체 원 입력이 없으면 바뀐 조건을 단정하지 않습니다. 가상 Perturbation 노드와 연결은 생물학적 비교에서 제외합니다.",
        ],
    }


def compare_saved_pathways(store, workspace_id, artifact_ids):
    """Store-bound validation wrapper; Store enforces workspace and raw-content SHA."""
    return compare_artifacts([store.artifact(workspace_id, aid) for aid in artifact_ids])
