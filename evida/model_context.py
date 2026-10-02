"""Lossless tabular encoding for model messages; stored scientific artifacts stay raw."""
from __future__ import annotations

import json


FORMAT = "evida-columns-v1"


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _leaves(value, prefix=()):
    if isinstance(value, dict) and value:
        return {path: item for key, child in value.items()
                for path, item in _leaves(child, prefix + (key,)).items()}
    return {prefix: value}


def pack(value):
    if isinstance(value, dict):
        if "table_format" in value or "object_format" in value:
            return {"object_format": "evida-key-values-v1",
                    "items": [[key, pack(item)] for key, item in value.items()]}
        return {key: pack(item) for key, item in value.items()}
    if not isinstance(value, list):
        return value
    normal = [pack(item) for item in value]
    if len(value) < 2 or not all(isinstance(item, dict) and item for item in value):
        return normal
    flat = [_leaves(item) for item in value]
    paths = sorted(flat[0])
    # Do not turn absent fields into null, or conflate a scalar with a nested object.
    if not all(set(row) == set(paths) for row in flat):
        return normal
    table = {"table_format": FORMAT, "columns": [list(path) for path in paths],
             "rows": [[pack(row[path]) for path in paths] for row in flat]}
    return table if len(compact_json(table)) < len(compact_json(normal)) else normal


def model_json(value):
    return compact_json(pack(value))


def artifact_overview(artifact):
    """List every available source without pretending its full content was inspected."""
    view = {key: artifact[key] for key in ("id", "title", "kind", "sha256", "meta")}
    view["artifact_id"] = view.pop("id")
    view["content_view"] = "catalog_only; use inspect_artifact for original content and rows"
    if artifact["media_type"] == "application/json":
        value = json.loads(artifact["content"])
        if isinstance(value, dict):
            # Keep scientific context, uncertainty and summary; rows remain explicitly retrievable.
            fields = ("status", "semantic_type", "summary", "limits", "context", "contrast",
                      "versions", "columns", "header", "reference_percentiles", "sources", "pmc_id", "permissions", "title")
            view["summary_view"] = {key: value[key] for key in fields if key in value}
            view["available_result_fields"] = list(value)
            if isinstance(value.get("rows"), list):
                view["total_rows"] = len(value["rows"])
                view["rows_loaded"] = False
    return view


def unpack(value):
    """Deterministic inverse used to verify the actual sent data, not to infer science."""
    if isinstance(value, list):
        return [unpack(item) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"object_format", "items"} and value["object_format"] == "evida-key-values-v1":
        return {key: unpack(item) for key, item in value["items"]}
    if set(value) == {"table_format", "columns", "rows"} and value["table_format"] == FORMAT:
        output = []
        for cells in value["rows"]:
            if len(cells) != len(value["columns"]):
                raise ValueError("Table column/value length mismatch")
            row = {}
            for path, item in zip(value["columns"], cells):
                node = row
                for key in path[:-1]:
                    node = node.setdefault(key, {})
                node[path[-1]] = unpack(item)
            output.append(row)
        return output
    return {key: unpack(item) for key, item in value.items()}


def select_columns(view, paths):
    """Exact projection with explicit absent-key markers; no scalar coercion."""
    import copy
    value = copy.deepcopy(view)
    result = value.get("result", {})
    if not isinstance(result.get("rows"), list):
        raise ValueError("열을 선택할 수 있는 JSON 표가 아닙니다.")
    identity = ["row_id", "candidate_id", "gene_id", "symbol", "status", "input_artifact_id", "requested_gene",
                "sheet", "row_number", "hidden_row", "source_url", "requires_original_review"]
    projected = []
    for row in result["rows"]:
        if not isinstance(row, dict): raise ValueError("객체 행으로 구성된 표가 필요합니다.")
        cells = []
        for path in paths:
            item, found = row, True
            for key in path:
                if isinstance(item, list) and key.isdecimal() and int(key) < len(item):
                    item = item[int(key)]; continue
                if not isinstance(item, dict) or key not in item:
                    found = False; break
                item = item[key]
            cell_view = {"present": found, "value": item if found else None}
            if (row.get('kind') == 'xlsx_row' and len(path) > 2 and path[0] == 'cells'
                    and path[1].isdecimal() and isinstance(row.get('cells'), list)
                    and int(path[1]) < len(row['cells'])):
                # A selected numeric value alone loses units encoded in the number
                # format, comments, or formula provenance. Preserve its source cell.
                cell_view['source_cell'] = row['cells'][int(path[1])]
            cells.append(cell_view)
        projected.append({"identity": {key: row[key] for key in identity if key in row}, "cells": cells})
    result["rows"] = projected
    result["selected_columns"] = paths
    result["view_policy"] = "Only explicitly selected paths plus row identity/location and selected XLSX source-cell metadata; present=false differs from null. Other columns remain retrievable. Selection is not independent scientific evidence."
    if 'selection' in result:
        result['view_policy'] += " Exact string selection preserves duplicate observations and source order; unmatched is not biological absence."
    return value


def find_rows(rows, column_path, values, offset, limit):
    """Exact string selection, retaining repeated observations and source row order."""
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('객체 행으로 구성된 표가 필요합니다.')
    if (not isinstance(column_path, list) or not column_path or
            any(not isinstance(k, str) or not k for k in column_path)):
        raise ValueError('조회할 열의 정확한 키 경로가 필요합니다.')
    if not isinstance(values, list) or not 1 <= len(values) <= 100 or any(not isinstance(v, str) for v in values):
        raise ValueError('찾을 원문 문자열을 1–100개 지정해 주세요.')
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('자료 조회 범위가 올바르지 않습니다.')
    wanted = set(values)
    matches, positions, found, absent = [], [], set(), 0
    for position, row in enumerate(rows):
        value, present = row, True
        for key in column_path:
            if isinstance(value, list) and key.isdecimal() and int(key) < len(value):
                value = value[int(key)]
            elif isinstance(value, dict) and key in value:
                value = value[key]
            else:
                present = False
                break
        if not present:
            absent += 1
        elif isinstance(value, str) and value in wanted:
            matches.append(row)
            positions.append(position)
            found.add(value)
    return {'rows': matches[offset:offset + limit], 'total_rows': len(matches),
            'source_total_rows': len(rows), 'source_row_indices_0_based': positions[offset:offset + limit],
            'offset': offset, 'has_more': offset + limit < len(matches),
            'selection': {'column_path': column_path, 'values': values, 'match': 'exact_string',
                          'unmatched_values': [v for v in values if v not in found],
                          'rows_without_selected_path': absent},
            'view_policy': 'Exact original string match only; no case/alias normalization, no deduplication or ranking. '
                           'All original rows remain available. Unmatched is not biological absence.'}


def reading_focus(events, revision, job_ids):
    """A focus applies only within the framed question and its explicit resume chain."""
    jobs = set(job_ids)
    for event in reversed(events):
        body = event['body']
        if body.get('based_rev') != revision:
            continue
        if event['kind'] == 'work_framed':
            return None
        if event['kind'] == 'reading_focus_set' and body.get('job_id') in jobs:
            return body
    return None


def working_readings(artifacts, job_id, excluded_ids, read_artifact, focus=None):
    """Retain exact views from this job for cross-source decisions.

    Distinct pages/column selections remain distinct. An identical reread replaces
    only its delivery, not its source. Latest native tool outputs are excluded
    here to avoid duplicating them. Prior jobs remain available by artifact ID.
    """
    if job_id is None:
        return []
    job_ids = {job_id} if isinstance(job_id, str) else set(job_id)
    selected = set(focus['reading_ids']) if focus else set()
    previous = set(focus['existing_reading_ids']) if focus else set()
    latest, pinned = {}, {}
    for artifact in artifacts:
        meta = artifact['meta']
        if artifact['kind'] != 'tool_reading' or meta.get('function') == 'focus_readings':
            continue
        if artifact['id'] not in selected and meta.get('job_id') not in job_ids:
            continue
        if focus and artifact['id'] in previous and artifact['id'] not in selected:
            continue
        key = json.dumps([meta.get('function'), meta.get('source_artifact_id'),
                          meta.get('arguments')], sort_keys=True)
        if artifact['id'] in selected:
            pinned[artifact['id']] = artifact
        else:
            latest[key] = artifact
    keep = {a['id'] for a in latest.values()} | set(pinned)
    return [{'reading_id': a['id'], 'sha256': a['sha256'], 'meta': a['meta'],
             'content': json.loads(read_artifact(a['id'])['content'])}
            for a in artifacts if a['id'] in keep and a['id'] not in excluded_ids]


def next_model_context(context, latest_output, tool_outputs):
    """New application turn, latest complete model output/tool pair untouched."""
    reasoning_and_output = []
    for item in latest_output:
        if item.get("type") == "reasoning":
            if item.get("encrypted_content"):
                reasoning_and_output.append({k: item[k] for k in ("id", "type", "encrypted_content", "summary") if k in item})
        else:
            reasoning_and_output.append(item)
    return [{"role": "user", "content": model_json(context)}, *reasoning_and_output, *tool_outputs]


def hypothesis_index(hypothesis):
    """Keep exact claims discoverable without injecting every old evidence body."""
    fields = ("id", "statement", "expected_observation", "assessment", "alternatives")
    entry = {key: hypothesis[key] for key in fields if key in hypothesis}
    from .evidence_history import edges
    prior_edges = edges(hypothesis)
    entry['evidence_link_count'] = len(prior_edges)
    entry['evidence_source_ids'] = list(dict.fromkeys(r['edge']['source_id'] for r in prior_edges))
    entry['evidence_details_with'] = 'inspect_hypothesis_history or inspect_artifact(decision_id); navigation is not source reading or current support'
    if "assessment_scope" in hypothesis:
        scope = hypothesis["assessment_scope"]
        entry["assessment_scope"] = {"synthesis": scope["synthesis"],
            "parts": [{key: part[key] for key in fields if key in part} for part in scope["parts"]]}
    if 'conditional_alternatives' in hypothesis:
        entry['conditional_alternatives'] = [
            {key: alternative[key] for key in ('id','statement','part_ids','conditions','observable',
                                               'prediction','prediction_origin','assessment')}
            for alternative in hypothesis['conditional_alternatives']]
    return entry


def decision_history(events, load_artifact):
    """Index published hypotheses for retrieval, not as current scientific evidence.

    A short latest decision may omit an older explanation. Keep its exact question
    discoverable with the decision ID and revision; inspect_artifact retrieves the
    full alternatives, evidence links and next checks. Never merge by hypothesis ID
    across revisions or promote an unpublished/stale model draft into this history.
    """
    history = []
    for event in events:
        if event["kind"] != "decision_published":
            continue
        entry = {"decision_id": event["body"]["receipt_id"],
                 "state_revision": event["body"]["state_rev"],
                 "event_sequence": event["seq"]}
        try:
            artifact = load_artifact(entry["decision_id"])
            proposal = json.loads(artifact["content"])
            entry.update(sha256=artifact["sha256"], content_status="available",
                         hypotheses=[hypothesis_index(h)
                            for h in proposal.get("research_loop", {}).get("hypotheses", [])])
        except (KeyError, ValueError):
            # A missing/corrupt historical record must be visible, not silently
            # forgotten or converted to evidence against its scientific claim.
            entry.update(content_status="unavailable_or_integrity_failure", hypotheses=[])
        history.append(entry)
    return history
