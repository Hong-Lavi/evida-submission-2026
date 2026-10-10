"""Versioned, declared intent consumption; not a semantic or scientific oracle.

Model-authored IDs/reasons are bound to server-read records and consumer content.
Only a sidecar owned by the current published decision is a prior consumption
record. Missing links are unknown, never evidence of independence.

Design attribution: Salsa's input revisions and tracked dependencies
(https://salsa-rs.github.io/salsa/reference/algorithm.html). This is an independent
Python declaration tracker, not Salsa runtime integration or automatic tracing
of a model's internal reasoning.
"""
import copy
import hashlib
import json

import jsonschema


def _obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


TEXT = {'type': 'string'}
CONSUMER = {'consumer_kind': {'type': 'string', 'enum': ['question', 'hypothesis', 'check', 'recommendation']},
            'consumer_id': TEXT}
SCHEMA = _obj({
    'uses': {'type': 'array', 'items': _obj({**CONSUMER,
        'intent_ids': {'type': 'array', 'items': TEXT}, 'reason': TEXT})},
    'reassessments': {'type': 'array', 'items': _obj({**CONSUMER,
        'outcome': {'type': 'string', 'enum': ['changed', 'retained', 'removed', 'unknown']}, 'reason': TEXT})},
})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def latest_frame(state):
    return next((e for e in reversed(state['events']) if e['kind'] == 'work_framed'), None)


def authority_digest(state):
    """Publication/edit identity, independent of a frame's own derived records.

    Ordinary continuation can retain an interpretation. A new publication,
    explicit edit or correction invalidates the old frame's provisional view.
    """
    relevant = {kind: next((e['seq'] for e in reversed(state['events']) if e['kind'] == kind), None)
                for kind in ('decision_published', 'intent_edit', 'correction')}
    return digest({'intent': {r['id']: r for r in state['intent']}, 'events': relevant})


def active_frame_binding(state):
    frame = latest_frame(state)
    binding = (frame or {}).get('body', {}).get('intent_dependencies')
    if binding and binding.get('authority_sha256') == authority_digest(state):
        return binding
    return None


def records(state):
    """Current valid frame interpretations never overwrite authoritative storage."""
    binding = active_frame_binding(state)
    if binding:
        return [copy.deepcopy(v['record']) for v in binding['input_snapshot']['intents'].values()]
    frame = latest_frame(state)
    if (frame or {}).get('body', {}).get('intent_dependencies'):
        # An invalidated provisional frame must not resurrect records after an
        # empty publication or a correction, even before any human intent edit.
        return state['intent']
    if state['intent'] or any(e['kind'] == 'intent_edit' for e in state['events']):
        return state['intent']
    return frame['body'].get('intent_records', []) if frame else []


def input_snapshot(state):
    publication = next((e for e in reversed(state['events']) if e['kind'] == 'decision_published'), None)
    frame = latest_frame(state)
    binding = active_frame_binding(state)
    inputs = (copy.deepcopy(binding['input_snapshot']['intents']) if binding else
              {r['id']: {'record': copy.deepcopy(r), 'content_sha256': digest(r),
                         'record_basis': 'workspace_intent_record', 'basis_authority_sha256': authority_digest(state)}
               for r in records(state)})
    value = {'state_revision': state['rev'], 'intents': inputs,
             'authority_sha256': authority_digest(state),
             'frame_event_sequence': frame['seq'] if frame else None,
             'publication': ({'event_sequence': publication['seq'],
                              'decision_id': publication['body']['receipt_id']} if publication else None)}
    return {**value, 'snapshot_sha256': digest(value)}


def structured_snapshot(received, declared, stage):
    """Hash the model's declared structure without calling it received evidence."""
    entries = {}
    for record in declared:
        rid = record['id']
        if rid in entries:
            raise ValueError('의도 구조의 ID는 중복 없이 기록하세요.')
        previous = received['intents'].get(rid)
        content_hash = digest(record)
        if previous and previous['content_sha256'] == content_hash:
            entries[rid] = copy.deepcopy(previous)
        else:
            entries[rid] = {'record': copy.deepcopy(record), 'content_sha256': content_hash,
                'record_basis': 'model_structured_in_' + stage,
                'received_record_sha256': previous['content_sha256'] if previous else None,
                'received_snapshot_sha256': received['snapshot_sha256'],
                'structure_origin': 'model_declared_not_researcher_confirmation'}
    value = {k: copy.deepcopy(v) for k, v in received.items() if k != 'snapshot_sha256'}
    value['intents'] = entries
    value['snapshot_kind'] = 'model_declared_semantic_structure'
    return {**value, 'snapshot_sha256': digest(value)}


def transaction_state(store, db, wid):
    state = store.workspace(db, wid)
    state['intent'] = json.loads(state['intent'])
    state['events'] = [{**dict(row), 'body': json.loads(row['body'])} for row in db.execute(
        'SELECT * FROM events WHERE workspace=? ORDER BY seq', (wid,))]
    return state


def protected_conflicts(state, proposed_records):
    from .intent_records import override_ids
    edit = next((e['body'] for e in reversed(state['events']) if e['kind'] == 'intent_edit'), None)
    protected, deleted = override_ids(edit)
    proposed = {r['id']: r for r in proposed_records}
    conflicts = [{'intent_id': r['id'], 'reason': 'protected_record_changed_or_omitted'}
                 for r in state['intent'] if r['id'] in protected and proposed.get(r['id']) != r]
    conflicts += [{'intent_id': rid, 'reason': 'deleted_record_reintroduced'} for rid in sorted(deleted & proposed.keys())]
    if len(proposed) != len(proposed_records):
        conflicts.append({'intent_id': '', 'reason': 'duplicate_intent_id'})
    return conflicts


def _key(value):
    return value['consumer_kind'], value['consumer_id']


def consumers(frame, proposal=None):
    result = {('question', 'current_question'): (frame or {}).get('current_question', '')}
    if proposal is not None:
        result[('recommendation', 'recommendation')] = {
            key: proposal.get(key) for key in ('action', 'recommendation', 'reason')}
        loop = proposal.get('research_loop', {})
        for kind, field in [('hypothesis', 'hypotheses'), ('check', 'next_checks')]:
            for item in loop.get(field, []):
                result[(kind, item['id'])] = item
    return result


def _published_record(store, wid, state):
    publication = next((e for e in reversed(state['events']) if e['kind'] == 'decision_published'), None)
    if not publication:
        return None, 'no_published_consumption_record'
    decision_id = publication['body']['receipt_id']
    try:
        decision = store.artifact(wid, decision_id)
        aid = decision['meta'].get('finalization_records', {}).get('intent_dependencies')
        if not aid:
            return None, 'legacy_decision_without_consumption_record'
        artifact = store.artifact(wid, aid)
        record = json.loads(artifact['content'])
        if (artifact['kind'] != 'intent_dependencies' or record.get('decision_id') != decision_id
                or record.get('decision_sha256') != decision['sha256']):
            return None, 'consumption_record_owner_mismatch'
        return {**record, 'artifact_id': aid}, 'available'
    except (KeyError, ValueError, TypeError):
        return None, 'consumption_record_unavailable_or_integrity_failure'


def view(store, wid, state=None, *, semantic_snapshot=None):
    state = state or store.snapshot(wid)
    snapshot = semantic_snapshot or input_snapshot(state)
    prior, status = _published_record(store, wid, state)
    changed, required = [], []
    if prior:
        old = prior['input_snapshot']['intents']
        new = snapshot['intents']
        changed = sorted(rid for rid in old.keys() | new.keys()
                         if old.get(rid, {}).get('content_sha256') != new.get(rid, {}).get('content_sha256'))
        for consumer in prior['consumers']:
            used = {r['intent_id'] for r in consumer['inputs']}
            # Unlinked consumers are explicitly unknown, even when other links exist.
            affected = sorted(used & set(changed))
            if affected or not used:
                required.append({**{k: consumer[k] for k in ('consumer_kind', 'consumer_id', 'content', 'content_sha256')},
                                 'changed_intent_ids': affected,
                                 'trigger': 'consumed_intent_changed' if affected else 'consumption_unknown'})
        for unresolved in prior.get('reassessments', []):
            if unresolved['outcome'] != 'unknown' or any(_key(c) == _key(unresolved) for c in required):
                continue
            consumer = next((c for c in prior['consumers'] if _key(c) == _key(unresolved)), None)
            required.append({'consumer_kind': unresolved['consumer_kind'], 'consumer_id': unresolved['consumer_id'],
                'content': consumer['content'] if consumer else None,
                'content_sha256': consumer['content_sha256'] if consumer else None,
                'changed_intent_ids': unresolved['changed_intent_ids'], 'trigger': 'prior_review_unknown'})
    frame_event = latest_frame(state)
    frame = frame_event['body'] if frame_event else {}
    binding = frame.get('intent_dependencies')
    frame_hashes = {rid: v['content_sha256'] for rid, v in (binding or {}).get('input_snapshot', {}).get('intents', {}).items()}
    current_hashes = {rid: v['content_sha256'] for rid, v in snapshot['intents'].items()}
    correction_seq = max((e['seq'] for e in state['events'] if e['kind'] == 'correction'), default=0)
    pub_seq = (snapshot['publication'] or {}).get('event_sequence', 0)
    correction_pending = correction_seq > pub_seq
    conflict = next((e for e in reversed(state['events'])
                     if e['kind'] == 'decision_intent_conflict' and e['seq'] > pub_seq), None)
    needs_frame = not binding or frame_hashes != current_hashes or correction_seq > (frame_event or {}).get('seq', 0)
    if not prior and pub_seq >= (frame_event or {}).get('seq', 0):
        needs_frame = True
    if prior and pub_seq > (frame_event or {}).get('seq', 0) and not correction_pending:
        # A final response may refine the frame's inferred structure, provided
        # it also reassesses this exact question. Its own publication is not a
        # subsequent external input change.
        question = next((c for c in prior['consumers'] if _key(c) == ('question', 'current_question')), None)
        prior_hashes = {rid: v['content_sha256'] for rid, v in prior['input_snapshot']['intents'].items()}
        if question and question['content_sha256'] == digest(frame.get('current_question', '')) and prior_hashes == current_hashes:
            needs_frame = False
    # Addition may alter the goal even if no old consumer linked that new ID.
    if not prior or changed or correction_pending:
        if not any(_key(c) == ('question', 'current_question') for c in required):
            previous_question = next((c for c in (prior or {}).get('consumers', [])
                                      if _key(c) == ('question', 'current_question')), None)
            required.insert(0, {'consumer_kind': 'question', 'consumer_id': 'current_question',
                'content': previous_question['content'] if previous_question else frame.get('current_question'),
                'content_sha256': previous_question['content_sha256'] if previous_question else None,
                'changed_intent_ids': changed, 'trigger': 'input_changed' if prior else 'consumption_history_unknown'})
    return {'schema_version': '1', 'input_snapshot': snapshot, 'prior_record_status': status,
            'prior_record_id': prior['artifact_id'] if prior else None,
            'changed_intent_ids': changed, 'required_reassessments': required,
            'question_reassessment_required': needs_frame,
            'latest_review_status': (prior or {}).get('review_status', 'unknown'),
            'latest_consumers': (prior or {}).get('consumers', []),
            'latest_reassessments': (prior or {}).get('reassessments', []),
            'latest_publication_conflict': ({'event_sequence': conflict['seq'],
                **{k: conflict['body'][k] for k in ('receipt_id', 'state_rev', 'conflicts', 'proposal_sha256')}}
                if conflict else None),
            'meaning': 'Declared use and literal version changes, not semantic independence or scientific validation. '
                       'Missing consumption is unknown. Retain a question with a reason under the new conditions when appropriate. '
                       'Original evidence, hypotheses and rejected proposals remain retrievable.'}


def model_view(store, wid, state=None):
    """Do not redeliver whole scientific claims already in PREVIOUS_DECISION."""
    scope = view(store, wid, state)
    scope['latest_consumers'] = [{k: c[k] for k in (
        'consumer_kind', 'consumer_id', 'content_sha256', 'intent_ids', 'reason', 'reason_origin', 'linkage_status')}
        for c in scope['latest_consumers']]
    scope['required_reassessments'] = [{k: v for k, v in c.items() if k != 'content'}
                                       for c in scope['required_reassessments']]
    return scope


def bind(review, snapshot, consumer_values, required, *, received_snapshot=None):
    jsonschema.validate(review, SCHEMA)
    received_snapshot = received_snapshot or snapshot
    seen, bound = set(), []
    for use in review['uses']:
        key = _key(use)
        if key in seen or key not in consumer_values or not use['reason'].strip():
            raise ValueError('의도 사용처는 실제 질문·가설·추천·확인 ID별로 한 번, 사용 이유와 함께 기록하세요.')
        seen.add(key)
        ids = use['intent_ids']
        if len(set(ids)) != len(ids) or any(rid not in snapshot['intents'] for rid in ids):
            raise ValueError('의도 소비기록에는 서버가 제시한 현재 intent ID만 중복 없이 사용하세요.')
        content = consumer_values[key]
        bound.append({**use, 'reason_origin': 'model_declared', 'content': copy.deepcopy(content),
                      'content_sha256': digest(content), 'inputs': [
                          {'intent_id': rid, **copy.deepcopy(snapshot['intents'][rid]),
                           'state_revision': snapshot['state_revision'],
                           'delivered_input_snapshot_sha256': received_snapshot['snapshot_sha256'],
                           'delivered_record_sha256': received_snapshot['intents'].get(rid, {}).get('content_sha256'),
                           'consumption_relation': ('received_record_used_unchanged'
                               if received_snapshot['intents'].get(rid, {}).get('content_sha256') == snapshot['intents'][rid]['content_sha256']
                               else 'model_structured_record')} for rid in ids],
                      'linkage_status': 'declared' if ids else 'unknown'})
    if seen != set(consumer_values):
        raise ValueError('현재 질문·가설·추천·다음 확인의 실제 사용처를 모두 기록하세요. 연결 미상은 빈 intent_ids와 사유로 남기세요.')
    expected = {_key(c): c for c in required}
    assessed, reassessments = set(), []
    for review_item in review['reassessments']:
        key = _key(review_item)
        if key in assessed or key not in expected or not review_item['reason'].strip():
            raise ValueError('INTENT_DEPENDENCIES.required_reassessments의 정확한 사용처와 재검토 이유가 필요합니다.')
        assessed.add(key)
        previous, current = expected[key], consumer_values.get(key)
        outcome = review_item['outcome']
        previous_hash = previous.get('content_sha256')
        if outcome == 'removed' and key in consumer_values:
            raise ValueError('남아 있는 사용처를 removed로 표시할 수 없습니다.')
        if outcome != 'removed' and key not in consumer_values and outcome != 'unknown':
            raise ValueError('사라진 사용처는 removed 또는 unknown과 사유로 남기세요.')
        if outcome == 'retained' and previous_hash and digest(current) != previous_hash:
            raise ValueError('내용이 바뀐 사용처는 retained가 아닌 changed 또는 unknown으로 기록하세요.')
        if outcome == 'changed' and previous_hash and digest(current) == previous_hash:
            raise ValueError('내용이 같은 사용처는 새 조건에서 유지하는 이유와 retained로 기록하세요.')
        reassessments.append({**review_item, 'reason_origin': 'model_declared',
                              'previous_content_sha256': previous_hash,
                              'current_content_sha256': digest(current) if key in consumer_values else None,
                              'trigger': previous['trigger'], 'changed_intent_ids': previous['changed_intent_ids']})
    if assessed != set(expected):
        raise ValueError('영향 받은 사용처의 재검토가 빠졌습니다. 판단 불가도 unknown과 사유로 기록할 수 있습니다.')
    unknown = any(c['linkage_status'] == 'unknown' for c in bound) or any(r['outcome'] == 'unknown' for r in reassessments)
    return {'schema_version': '1', 'input_snapshot': copy.deepcopy(snapshot), 'consumers': bound,
            'reassessments': reassessments, 'review_status': 'unknown' if unknown else 'declared_review_complete',
            'scientific_validation': False}


def bind_frame(store, wid, state, args, *, required=False):
    if 'intent_dependencies' in args:
        raise ValueError('의도 해시·버전 바인딩은 서버가 생성합니다. intent_review 선언만 보내세요.')
    if protected_conflicts(state, args['intent_records']):
        raise ValueError('연구자가 정정·삭제한 의도와 작업 질문의 의도 기록이 다릅니다. 현재 의도를 보존하세요.')
    if 'intent_review' not in args:
        if required:
            raise ValueError('새 frame_work에는 intent_review가 필요합니다.')
        return None
    scope = view(store, wid, state)
    received = input_snapshot(state)
    snapshot = structured_snapshot(received, args['intent_records'], 'frame')
    required_items = [c for c in scope['required_reassessments'] if c['consumer_kind'] == 'question']
    if not required_items and scope['question_reassessment_required']:
        required_items = [{'consumer_kind': 'question', 'consumer_id': 'current_question',
                           'content_sha256': None, 'trigger': 'question_binding_unknown', 'changed_intent_ids': []}]
    value = bind(args['intent_review'], snapshot, consumers(args), required_items, received_snapshot=received)
    value.update(received_input_snapshot=received, authority_sha256=authority_digest(state),
                 consumption_snapshot_kind='model_declared_semantic_structure')
    return value


def prepare(store, wid, state, proposal, review, *, required=False, expected_snapshot=None):
    if review is None:
        if required:
            raise ValueError('새 native 판단에는 intent_review 사용처·재검토 기록이 필요합니다.')
        return None  # Historical/internal bundles are readable, not backfilled as reviewed.
    scope = view(store, wid, state)
    received = scope['input_snapshot']
    if expected_snapshot and expected_snapshot != received['snapshot_sha256']:
        raise ValueError('모델이 받은 의도 또는 동일 버전의 게시 판단이 바뀌었습니다. 최신 입력을 검토하세요.')
    if required and scope['question_reassessment_required']:
        raise ValueError('의도 소비기록이 없거나 조건이 바뀌었습니다. frame_work로 현재 질문을 먼저 재검토하세요.')
    frame = (latest_frame(state) or {}).get('body', {})
    # Preserve the existing conflict publication path and original rejected
    # proposal; a conflicting structure never gets a published sidecar.
    conflicts = protected_conflicts(state, proposal['intent_records'])
    snapshot = received if conflicts else structured_snapshot(received, proposal['intent_records'], 'final')
    final_scope = scope if conflicts else view(store, wid, state, semantic_snapshot=snapshot)
    required_items = final_scope['required_reassessments']
    old = {rid: r['content_sha256'] for rid, r in received['intents'].items()}
    new = {rid: r['content_sha256'] for rid, r in snapshot['intents'].items()}
    if old != new and not any(_key(c) == ('question', 'current_question') for c in required_items):
        required_items = [{'consumer_kind': 'question', 'consumer_id': 'current_question',
            'content': frame.get('current_question', ''), 'content_sha256': digest(frame.get('current_question', '')),
            'trigger': 'final_structure_changed',
            'changed_intent_ids': sorted(rid for rid in old.keys() | new.keys() if old.get(rid) != new.get(rid))}, *required_items]
    value = bind(review, snapshot, consumers(frame, proposal), required_items, received_snapshot=received)
    value['received_input_snapshot'] = received
    value['consumption_snapshot_kind'] = 'model_declared_semantic_structure'
    value['prior_record_id'] = scope['prior_record_id']
    value['frame_event_sequence'] = (latest_frame(state) or {}).get('seq')
    return {'kind': 'intent_dependencies', 'title': '의도 정정과 판단 재검토', 'value': value,
            'meta': {'scientific_validation': False, 'reason_origin': 'model_declared'}}
