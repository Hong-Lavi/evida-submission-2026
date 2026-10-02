"""Connect public scientific rationale to checks without inventing a causal oracle.

Reference validation checks identity, not whether a claim is scientifically true.
Tool completion never changes a hypothesis assessment: a new interpretation is
required, and both the old interpretation and new observation remain available.
"""
from __future__ import annotations

import jsonschema

from .contracts import FRAME, RESEARCH_LOOP, SCOPE_TARGETS


def validate_hypotheses(hypotheses, state):
    jsonschema.validate(hypotheses, FRAME["properties"]["hypotheses"])
    ids = [h["id"] for h in hypotheses]
    if any(not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("가설에는 중복되지 않는 ID가 필요합니다.")
    artifacts = {a["id"] for a in state["artifacts"]}
    messages = {e["body"]["message_id"] for e in state["events"] if e["body"].get("message_id")}
    for hypothesis in hypotheses:
        parts = hypothesis.get("assessment_scope", {}).get("parts", [])
        part_ids = [p["id"] for p in parts]
        if any(not p.strip() for p in part_ids) or len(set(part_ids)) != len(part_ids):
            raise ValueError("가설의 부분 판단에는 가설 안에서 중복되지 않는 ID가 필요합니다.")
        alternatives = hypothesis.get('conditional_alternatives', [])
        alt_ids = [a['id'] for a in alternatives]
        if any(not i.strip() for i in alt_ids) or len(set(alt_ids)) != len(alt_ids):
            raise ValueError('조건별 설명의 ID는 해당 가설 안에서 비어 있거나 중복될 수 없습니다.')
        for a in alternatives:
            if not a['statement'].strip() or not a['observable'].strip() or not a['prediction'].strip():
                raise ValueError('조건별 설명의 주장·관측 대상·예상을 명시해 주세요.')
            if len(set(a['part_ids'])) != len(a['part_ids']) or not set(a['part_ids']).issubset(part_ids):
                raise ValueError('조건별 설명이 존재하지 않는 부분 판단을 참조합니다.')
            if any(r['alternative_id'] not in alt_ids or r['alternative_id'] == a['id'] for r in a['relations']):
                raise ValueError('설명 간 관계가 해당 가설의 다른 설명에 연결되어야 합니다.')
        for link in hypothesis["evidence"] + [e for p in parts for e in p["evidence"]] + [e for a in alternatives for e in a['evidence']]:
            known = artifacts if link["source_type"] == "artifact" else messages
            if link["source_id"] not in known:
                raise ValueError("가설에 연결한 근거가 이 연구의 자료 또는 메시지에 없습니다.")
    return set(ids)


def validate_scope_targets(targets, hypotheses, allowed_ids):
    """Check references within this exact decision, not scientific relevance."""
    try:
        jsonschema.validate(targets, SCOPE_TARGETS)
    except jsonschema.ValidationError as exc:
        raise ValueError("부분 판단의 연결 형식이 올바르지 않습니다.") from exc
    by_id = {h["id"]: h for h in hypotheses}
    seen = set()
    for target in targets:
        hid, ids = target["hypothesis_id"], target["part_ids"]
        if hid not in allowed_ids or hid not in by_id or hid in seen:
            raise ValueError("부분 판단이 연결 대상 가설에 없거나 중복됐습니다.")
        seen.add(hid)
        known = {p["id"] for p in by_id[hid].get("assessment_scope", {}).get("parts", [])}
        if len(set(ids)) != len(ids) or not set(ids).issubset(known):
            raise ValueError(
                f"연결한 부분 판단이 해당 가설에 없거나 중복됐습니다. 가설 {hid!r}: "
                f"요청 부분 {ids!r}, 이번 판단에 정의한 부분 {sorted(known)!r}. "
                "전체 가설을 확인할 때는 scope_targets를 생략하고 "
                "outcome_links.effects의 part_ids=[]로 연결할 수 있습니다.")


def experiment_grounding(check):
    """Which retrieved sources an experiment recommendation names, if it is one.

    Source IDs connect an experiment recommendation to retained records. This
    identity check complements scientific review of whether those sources
    actually justify each proposed condition and readout.
    """
    operation = check.get('operation') or {}
    if operation.get('kind') != 'external_observation':
        return {'is_experiment': False, 'grounded': None, 'grounded_in': [], 'meaning': None}
    sources = list(operation.get('grounded_in') or [])
    return {'is_experiment': True, 'grounded': bool(sources), 'grounded_in': sources,
            'meaning': ('이 실험 권고가 근거로 지목한 이 연구의 자료입니다.' if sources else
                        '이 실험 권고는 조회한 자료를 지목하지 않았습니다. 권고가 틀렸다는 뜻이 '
                        '아니라, 어느 원자료에서 나왔는지 되짚을 수 없다는 뜻입니다.')}


def validate_loop(loop, state):
    jsonschema.validate(loop, RESEARCH_LOOP)
    hypotheses = validate_hypotheses(loop["hypotheses"], state)
    ids = [c["id"] for c in loop["next_checks"]]
    if any(not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("다음 확인에는 중복되지 않는 ID가 필요합니다.")
    held = {a["id"] for a in state.get("artifacts", [])}
    for check in loop["next_checks"]:
        if not set(check["hypothesis_ids"]).issubset(hypotheses):
            raise ValueError("다음 확인이 존재하지 않는 가설을 참조합니다.")
        grounded_in = (check.get("operation") or {}).get("grounded_in")
        if grounded_in is not None:
            if len(set(grounded_in)) != len(grounded_in):
                raise ValueError("실험 권고의 근거 자료가 중복됐습니다.")
            if not set(grounded_in).issubset(held):
                raise ValueError("실험 권고가 근거로 지목한 자료가 이 연구에 없습니다.")
        if "scope_targets" in check:
            validate_scope_targets(check["scope_targets"], loop["hypotheses"], check["hypothesis_ids"])
        for link in check.get('outcome_links', []):
            if link['outcome_index'] >= len(check['possible_outcomes']):
                raise ValueError('결과별 연결이 이 확인의 가능한 결과에 없습니다.')
            if not set(link['followup_check_ids']).issubset(ids):
                raise ValueError('결과별 후속 확인이 이 판단에 없습니다.')
            for effect in link['effects']:
                hid = effect['hypothesis_id']
                if hid not in check['hypothesis_ids']:
                    raise ValueError('결과별 영향 가설을 이 확인의 대상에 명시해 주세요.')
                h = next(h for h in loop['hypotheses'] if h['id'] == hid)
                if not set(effect['alternative_ids']).issubset({a['id'] for a in h.get('conditional_alternatives', [])}):
                    raise ValueError('결과별 연결이 해당 가설에 없는 설명을 참조합니다.')
                known_parts = {p['id'] for p in h.get('assessment_scope', {}).get('parts', [])}
                if not set(effect['part_ids']).issubset(known_parts):
                    raise ValueError('결과별 연결이 해당 가설에 없는 부분을 참조합니다.')
                if check.get('scope_targets'):
                    allowed = {p for t in check['scope_targets'] if t['hypothesis_id'] == hid for p in t['part_ids']}
                    if not effect['part_ids'] or not set(effect['part_ids']).issubset(allowed):
                        raise ValueError('결과별 영향의 부분 범위를 이 확인의 범위 안에 명시해 주세요.')


def decision_id(state):
    return next((e["body"]["receipt_id"] for e in reversed(state["events"])
                 if e["kind"] == "decision_published"), None)


def compare_hypothesis_wording(before, after):
    """Compare literal claims/predictions; do not infer semantic equivalence.

    IDs are matched only within the explicitly recorded pair of decisions/frames.
    An omitted hypothesis is not a scientifically rejected hypothesis.
    """
    previous = {h['id']: h for h in before}
    current = {h['id']: h for h in after}
    comparisons = []
    for hid, hypothesis in current.items():
        if hid not in previous:
            comparisons.append({'id': hid, 'status': 'not_in_reference', 'changed_fields': []})
            continue
        changes = [{'field': field, 'before': previous[hid][field], 'after': hypothesis[field]}
                   for field in ('statement', 'expected_observation')
                   if previous[hid][field] != hypothesis[field]]
        comparisons.append({'id': hid, 'status': 'wording_changed' if changes else 'literal_unchanged',
                            'changed_fields': changes})
    comparisons.extend({'id': hid, 'status': 'not_in_current', 'changed_fields': []}
                       for hid in previous if hid not in current)
    return comparisons


def active_check(state, check_id):
    if state["decision"] is None or state["decision_rev"] != state["rev"]:
        raise ValueError("현재 자료를 반영한 판단에서 다음 확인을 선택해 주세요.")
    check = next((c for c in state["decision"].get("research_loop", {}).get("next_checks", [])
                  if c["id"] == check_id), None)
    if check is None:
        raise ValueError("이 판단에 해당하는 다음 확인이 없습니다.")
    return check


def validate_feedback(context, proposal):
    """Feedback may refer to an older decision; never relabel it as current."""
    required = {"decision_id", "check_id", "hypothesis_ids", "comparison"}
    if not isinstance(context, dict) or not required.issubset(context) or set(context) - required - {"scope_targets"}:
        raise ValueError("관측이 어떤 판단과 연결되는지 확인해 주세요.")
    if context["comparison"] not in ("consistent", "different", "unclear"):
        raise ValueError("관측과 예상의 비교가 올바르지 않습니다.")
    loop = proposal.get("research_loop", {})
    hypotheses = {h["id"] for h in loop.get("hypotheses", [])}
    if not isinstance(context["hypothesis_ids"], list) or not all(isinstance(x, str) for x in context["hypothesis_ids"]):
        raise ValueError("관측의 가설 참조가 올바르지 않습니다.")
    if not set(context["hypothesis_ids"]).issubset(hypotheses):
        raise ValueError("관측이 참조하는 가설이 해당 판단에 없습니다.")
    if context["check_id"] is not None and context["check_id"] not in {c["id"] for c in loop.get("next_checks", [])}:
        raise ValueError("관측이 참조하는 확인이 해당 판단에 없습니다.")
    if "scope_targets" in context:
        validate_scope_targets(context["scope_targets"], loop.get("hypotheses", []), context["hypothesis_ids"])
    if context["check_id"] is not None:
        check = next(c for c in loop["next_checks"] if c["id"] == context["check_id"])
        if not set(context["hypothesis_ids"]).issubset(check["hypothesis_ids"]):
            raise ValueError("관측의 가설이 해당 다음 확인에 연결되어 있지 않습니다.")
        if "scope_targets" in check:
            allowed = {(t["hypothesis_id"], p) for t in check["scope_targets"] for p in t["part_ids"]}
            linked = {(t["hypothesis_id"], p) for t in context.get("scope_targets", []) for p in t["part_ids"]}
            if not linked or not linked.issubset(allowed):
                raise ValueError("이 확인에 연결할 관측의 부분 판단 범위를 유지해 주세요.")


# Candidate27 (team feedback A3): deterministic checks of anchored mechanism clauses.
# They check quotation identity, recorded search counts and check links only, never the
# scientific truth of a clause. A failure is recorded beside the model's unchanged record
# and shown; publication is not blocked and the model is not asked to rewrite.
ANCHOR_KINDS = {'article', 'literature', 'lens_literature', 'repository_document', 'clinical_trial',
                'clinical_trial_search', 'drug_label', 'drug_label_search', 'target_disease_evidence',
                'binding_measurements', 'gtopdb_pharmacology', 'compound_candidates'}
COUNT_FIELDS = {'literature': 'hit_count', 'clinical_trial_search': 'total',
                'drug_label_search': 'total', 'lens_literature': 'source_total'}
PROFILE_KINDS = ('mechanism:', 'approach:')


def _plain(text):
    import html
    import re
    return re.sub(r'\s+', ' ', re.sub(r'</?[A-Za-z][^<>]{0,40}>', '', html.unescape(text))).strip()


def _source_links(value, row):
    links = {k: row[k] for k in ('pmid', 'pmcid', 'doi', 'nct_id', 'setid', 'source_url')
             if isinstance(row.get(k), str) and row[k]}
    if isinstance(value.get('pmc_id'), str):
        links.setdefault('pmcid', value['pmc_id'])
    summary = value.get('summary') if isinstance(value.get('summary'), dict) else {}
    for key in ('nct_id', 'setid'):
        if isinstance(summary.get(key), str):
            links.setdefault(key, summary[key])
    return links


def check_anchor(store, wid, anchor):
    from .source_candidates import strings
    import json
    try:
        artifact = store.artifact(wid, anchor['artifact_id'])
    except KeyError:
        return {'status': 'rejected', 'reason': 'artifact_not_in_this_research'}
    if artifact['kind'] not in ANCHOR_KINDS:
        return {'status': 'rejected', 'reason': 'not_a_public_source_row', 'kind': artifact['kind']}
    value = json.loads(artifact['content'])
    rows = value.get('rows') if isinstance(value.get('rows'), list) else []
    if anchor['row_index'] >= len(rows):
        return {'status': 'rejected', 'reason': 'row_not_found', 'kind': artifact['kind']}
    row = rows[anchor['row_index']]
    texts = strings(row)
    base = {'kind': artifact['kind'], 'source_sha256': artifact['sha256'],
            'locator': 'rows/' + str(anchor['row_index']), 'links': _source_links(value, row if isinstance(row, dict) else {})}
    if any(anchor['quote'] in t for t in texts):
        return {**base, 'status': 'verified', 'match': 'exact'}
    quote = _plain(anchor['quote'])
    if quote and any(quote in _plain(t) for t in texts):
        return {**base, 'status': 'verified', 'match': 'whitespace_or_inline_markup_normalized'}
    return {**base, 'status': 'rejected', 'reason': 'quote_not_in_row'}


def check_gap(store, wid, gap):
    import json
    try:
        artifact = store.artifact(wid, gap['query_artifact_id'])
    except KeyError:
        return {'status': 'rejected', 'reason': 'query_not_in_this_research'}
    field = COUNT_FIELDS.get(artifact['kind'])
    if field is None:
        return {'status': 'rejected', 'reason': 'not_a_search_record', 'kind': artifact['kind']}
    value = json.loads(artifact['content'])
    recorded = (value.get('summary') or {}).get(field) if value.get('status') == 'succeeded' else None
    if type(recorded) is not int:
        return {'status': 'rejected', 'reason': 'search_has_no_recorded_total', 'kind': artifact['kind']}
    if gap['reported_count'] != recorded:
        return {'status': 'rejected', 'reason': 'count_differs_from_record', 'recorded_count': recorded, 'kind': artifact['kind']}
    return {'status': 'verified', 'recorded_count': recorded, 'kind': artifact['kind']}


def challenge_link(loop, hypothesis_id):
    if loop is None:
        return 'pending_final_decision'
    if not hypothesis_id or hypothesis_id not in {h['id'] for h in loop['hypotheses']}:
        return 'hypothesis_not_in_decision'
    observations = [c for c in loop['next_checks'] if c['operation']['kind'] == 'external_observation'
                    and hypothesis_id in c['hypothesis_ids']]
    if not observations:
        return 'no_external_observation'
    if any(e['hypothesis_id'] == hypothesis_id and e['relation'] == 'challenges'
           for c in observations for link in c.get('outcome_links', []) for e in link['effects']):
        return 'linked'
    return 'no_challenging_outcome'


def verify_basis(store, wid, review, loop=None):
    """One record per profiled assessment; the submitted review itself is never changed."""
    results = []
    for row in review.get('assessments', []):
        if 'aspects' not in row:
            continue
        basis = row.get('basis')
        result = {'option_id': row['option_id'], 'profile_kind_applicable': row['option_id'].startswith(PROFILE_KINDS)}
        if basis is None:
            results.append({**result, 'basis': None})
            continue
        clauses = [{'clause_index': i, 'disease_match': c['disease_match'], **check_anchor(store, wid, c['anchor'])}
                   for i, c in enumerate(basis['clauses'])]
        gaps = [{'gap_index': i, **check_gap(store, wid, g)} for i, g in enumerate(basis['missing_in_target_disease'])]
        outside_target = basis['grade'] != 'established' or any(c['disease_match'] != 'target_disease' for c in basis['clauses'])
        link = challenge_link(loop, basis['hypothesis_id'])
        problems = [f'clause_{c["clause_index"]}_{c["reason"]}' for c in clauses if c['status'] != 'verified']
        problems += [f'gap_{g["gap_index"]}_{g["reason"]}' for g in gaps if g['status'] != 'verified']
        if outside_target and not gaps:
            problems.append('missing_in_target_disease_required')
        if basis['grade'] == 'hypothesis' and link not in ('linked', 'pending_final_decision'):
            problems.append('challenging_external_observation_' + link)
        results.append({**result, 'grade': basis['grade'], 'clauses': clauses, 'gaps': gaps,
                        'target_disease_gap_required': outside_target, 'challenge_check': link,
                        'status': 'passed' if not problems else 'issues_recorded', 'issues': problems})
    return results
