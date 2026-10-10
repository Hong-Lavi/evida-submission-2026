"""Validate a bounded final answer and optional records, then publish atomically."""
import hashlib

import jsonschema

from .contracts import DECISION, FINAL_DECISION, REVIEWED_FINAL_DECISION, CURRENT_FINAL_DECISION
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


def prepare(store, wid, rev, value, framed, expected_operations=None, decision_preservation=None,
            *, legacy_response=False, require_intent_review=False, expected_intent_snapshot=None):
    # Check before schema correction: missing protected fields must not trigger
    # an automatic model rewrite of an explicitly bounded scientific revision.
    draft = value.get('decision', value) if isinstance(value, dict) else value
    check_preservation(store, wid, decision_preservation, draft)
    # Publishing a new response requires authored review coverage. Loading old
    # decisions never passes here; frozen-response replay must be explicit.
    if not legacy_response:
        if not isinstance(value, dict) or not isinstance(value.get('hypothesis_review'), dict):
            raise ValueError('새 판단에는 hypothesis_review 검토 객체가 필요합니다. 가설·다음 확인별로 '
                             '실제 검토 또는 명시적 미검토·적용 불가 사유를 기록하세요. '
                             '근거가 없으면 인용을 만들지 말고 unknown 평가와 빈 anchors를 사용하세요.')
        jsonschema.validate(value, CURRENT_FINAL_DECISION)
        proposal = value['decision']
        discovery, context = value['discovery_review'], value['judgment_context']
    elif 'decision' in value:
        jsonschema.validate(value, REVIEWED_FINAL_DECISION if 'hypothesis_review' in value else FINAL_DECISION)
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
    from .intent_dependencies import prepare as prepare_intents
    intent_record = prepare_intents(store, wid, state, proposal, value.get('intent_review'),
        required=require_intent_review, expected_snapshot=expected_intent_snapshot)
    if intent_record is not None:
        records.append(intent_record)
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
    if value.get('hypothesis_review') is not None:
        from .hypothesis_review import prepare as prepare_review
        records.append(prepare_review(store, wid, rev, value['hypothesis_review'], proposal['research_loop']))
    return proposal, records


def commit(store, wid, rev, jid, proposal, records, model_receipts, protocol_id, decision_preservation=None):
    """No external work in the transaction; stale answers never apply sidecars."""
    def artifact(db, title, kind, value, meta, aid=None):
        aid=aid or uid('art');content=dump(value).encode()
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
        decision_aid=uid('art')
        from .intent_dependencies import input_snapshot, transaction_state, protected_conflicts, digest
        locked_state = transaction_state(store, db, wid)
        intent_record = next((r for r in records if r['kind'] == 'intent_dependencies'), None)
        input_changed = bool(intent_record and intent_record['value'].get('received_input_snapshot', intent_record['value']['input_snapshot'])['snapshot_sha256']
                             != input_snapshot(locked_state)['snapshot_sha256'])
        conflicts = protected_conflicts(locked_state, proposal['intent_records'])
        if current['rev']==rev and not input_changed and not conflicts:
            for record in records:
                if record['kind'] == 'intent_dependencies':
                    record = {**record, 'value': {**record['value'], 'decision_id': decision_aid,
                                                  'decision_sha256': digest(proposal)}}
                if record['kind']=='hypothesis_review':
                    from .hypothesis_review import bind_record
                    record=bind_record(record, decision_aid)
                sidecars[record['kind']]=artifact(db,record['title'],record['kind'],record['value'],
                    {**record['meta'],'based_rev':rev,'job_id':jid,'submission':'same_model_final_bundle'})
        aid=artifact(db,'현재 판단 제안','decision_proposal',proposal,
            {'based_rev':rev,'job_id':jid,'model_receipts':model_receipts,'protocol_id':protocol_id,
             'finalization_records':sidecars,'scientific_validation':False}, aid=decision_aid)
        if preservation is not None:
            store.event(db,wid,'decision_preservation_checked',
                {'receipt_id':aid,'contract':preservation,'status':'protected_fields_preserved'})
        if input_changed and current['rev'] == rev:
            store.event(db, wid, 'decision_intent_snapshot_stale', {
                'receipt_id': aid, 'state_rev': rev, 'published': False,
                'reason': 'Intent input or published decision changed after preparation, including at the same revision.'})
            published = False
        else:
            published=store._publish_decision(db,wid,rev,proposal,aid)
        if published and intent_record and intent_record['value']['review_status'] == 'unknown':
            db.execute("UPDATE workspaces SET review_status='needs_review' WHERE id=?", (wid,))
        return aid,published


def finalize(store, wid, rev, jid, value, framed, model_receipts, protocol_id, expected_operations=None,
             decision_preservation=None, *, legacy_response=False, require_intent_review=False,
             expected_intent_snapshot=None):
    try:
        proposal, records=prepare(store,wid,rev,value,framed,expected_operations=expected_operations,
                                  decision_preservation=decision_preservation, legacy_response=legacy_response,
                                  require_intent_review=require_intent_review,
                                  expected_intent_snapshot=expected_intent_snapshot)
        return commit(store,wid,rev,jid,proposal,records,model_receipts,protocol_id,
                      decision_preservation=decision_preservation)
    except DecisionPreservationError as rejection:
        preserve_rejection(store,wid,rev,jid,value,decision_preservation,rejection,model_receipts,protocol_id)
        raise
