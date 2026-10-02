"""Validate a bounded final answer and optional records, then publish atomically."""
import hashlib

import jsonschema

from .contracts import DECISION, FINAL_DECISION
from .decision_preservation import DecisionPreservationError, check as check_preservation, preserve_rejection
from .discovery import validate_review, resolve_review_ids
from .judgment_context import validate as validate_context
from .research_loop import validate_loop
from .store import dump, now, uid


def requested_operations(state, value):
    """Validate an explicit routing correction, without inferring one from prose.

    The caller supplies exact existing check IDs and requested operation kinds.
    This does not grade or rewrite the underlying scientific proposal.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('다음 확인의 작업 유형 정정은 ID와 유형의 대응표여야 합니다.')
    known = {c['id'] for c in (state.get('decision') or {}).get('research_loop', {}).get('next_checks', [])}
    allowed = {'tool', 'researcher_input', 'external_observation', 'unconnected_method'}
    for check_id, kind in value.items():
        if check_id not in known:
            raise ValueError(f'작업 유형을 정정할 확인이 현재 판단에 존재하지 않습니다: {check_id!r}')
        if not isinstance(kind, str) or kind not in allowed:
            raise ValueError(f'요청한 작업 유형이 등록된 형식이 아닙니다: {check_id!r}')
    return dict(value)


def check_requested_operations(proposal, expected):
    actual = {c['id']: c['operation']['kind'] for c in proposal['research_loop']['next_checks']}
    for check_id, kind in expected.items():
        if actual.get(check_id) != kind:
            raise ValueError(
                f'명시한 작업 유형 정정이 최종 필드에 반영되지 않았습니다. 확인 {check_id!r}: '
                f'요청 유형 {kind!r}, 반환 유형 {actual.get(check_id)!r}. '
                '원 과학 문안·근거·결과 연결은 유지하고 요청한 operation을 실제 필드에 반영해 주세요.')


def prepare(store, wid, rev, value, framed, expected_operations=None, decision_preservation=None):
    # Check before schema correction: missing protected fields must not trigger
    # an automatic model rewrite of an explicitly bounded scientific revision.
    draft = value.get('decision', value) if isinstance(value, dict) else value
    check_preservation(store, wid, decision_preservation, draft)
    # Preserve old frozen responses and explicit-synthesis callers. The new
    # provider request itself uses FINAL_DECISION and is checked by the gateway.
    if 'decision' in value:
        jsonschema.validate(value, FINAL_DECISION)
        proposal = value['decision']
        discovery, context = value['discovery_review'], value['judgment_context']
    else:
        jsonschema.validate(value, DECISION)
        proposal, discovery, context = value, None, None
    if not framed:
        raise ValueError('의도·작업 분해 없이 반환된 판단은 게시하지 않았습니다.')
    if proposal['based_on_state_rev'] != rev:
        raise ValueError('모델 응답의 연구 상태 버전이 요청과 다릅니다.')
    state = store.snapshot(wid)
    expected = requested_operations(state, expected_operations)
    check_requested_operations(proposal, expected)
    validate_loop(proposal['research_loop'], state)
    known = {a['id'] for a in state['artifacts']}
    if any(ref.split('#',1)[0] not in known for ref in proposal['evidence_refs']):
        raise ValueError('존재하지 않는 근거 참조를 사용한 판단은 게시하지 않았습니다.')
    records = []
    if discovery is not None:
        discovery,mappings=resolve_review_ids(store,wid,discovery)
        validate_review(store, wid, rev, discovery)
        from .research_loop import verify_basis
        records.append({'kind':'discovery_review','title':'선택지 검토 · '+discovery['question'][:100],
                        'value':discovery,'meta':{'semantic_type':'model_assessment_not_scientific_validation',
                        'omission_deletes_options':False,'option_id_resolution':mappings,
                        'basis_check':verify_basis(store, wid, discovery, proposal['research_loop'])}})
    if context is not None:
        hypotheses=proposal['research_loop']['hypotheses']
        validate_context(context, state, hypotheses)
        previous=next((a['id'] for a in reversed(state['artifacts']) if a['kind']=='judgment_context'),None)
        records.append({'kind':'judgment_context','title':'가설 조건·관측·재검토 경로',
                        'value':{'schema_version':'1','context':context,'hypothesis_wording':hypotheses,
                                 'supersedes':previous,'semantic_type':'model_authored_context_and_review_links_not_scientific_validation'},
                        'meta':{'supersedes':previous}})
    return proposal, records


def commit(store, wid, rev, jid, proposal, records, model_receipts, protocol_id, decision_preservation=None):
    """No external work in the transaction; stale answers never apply sidecars."""
    def artifact(db, title, kind, value, meta):
        aid=uid('art');content=dump(value).encode()
        db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)',
            (aid,wid,title,kind,hashlib.sha256(content).hexdigest(),'application/json',now(),dump(meta),content))
        store.event(db,wid,'artifact_added',{'artifact_id':aid,'title':title,'kind':kind})
        return aid
    with store.connect(True) as db:
        # Rebind under the write lock: another publication may have occurred
        # since prepare, including one at the same state revision.
        preservation = check_preservation(store, wid, decision_preservation, proposal, db)
        current=store.workspace(db,wid)
        sidecars={}
        if current['rev']==rev:
            for record in records:
                sidecars[record['kind']]=artifact(db,record['title'],record['kind'],record['value'],
                    {**record['meta'],'based_rev':rev,'job_id':jid,'submission':'same_model_final_bundle'})
        aid=artifact(db,'현재 판단 제안','decision_proposal',proposal,
            {'based_rev':rev,'job_id':jid,'model_receipts':model_receipts,'protocol_id':protocol_id,
             'finalization_records':sidecars,'scientific_validation':False})
        if preservation is not None:
            store.event(db,wid,'decision_preservation_checked',
                {'receipt_id':aid,'contract':preservation,'status':'protected_fields_preserved'})
        published=store._publish_decision(db,wid,rev,proposal,aid)
        return aid,published


def finalize(store, wid, rev, jid, value, framed, model_receipts, protocol_id, expected_operations=None,
             decision_preservation=None):
    try:
        proposal, records=prepare(store,wid,rev,value,framed,expected_operations=expected_operations,
                                  decision_preservation=decision_preservation)
        return commit(store,wid,rev,jid,proposal,records,model_receipts,protocol_id,
                      decision_preservation=decision_preservation)
    except DecisionPreservationError as rejection:
        preserve_rejection(store,wid,rev,jid,value,decision_preservation,rejection,model_receipts,protocol_id)
        raise
