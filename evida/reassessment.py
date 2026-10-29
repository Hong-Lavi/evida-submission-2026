"""Declared, versioned scientific reassessment for any research target.

The dependency engine requests interpretation; it does not generate biological
truth. Source delivery is recorded separately from the model's declared use.
Draft reviews become current only with the decision that publishes them.
"""
from copy import deepcopy
import hashlib
import json

from .store import dump, now, uid

VERSION = 'assessment-dependencies-v1'
EPHEMERAL = frozenset({
    'model_receipt', 'decision_proposal', 'research_notes', 'protocol_snapshot',
    'tool_reading', 'decision_validation_error', 'explanation_context',
    'explanation_answer', 'explanation_model_output', 'explanation_reading',
    'discovery_review', 'judgment_context', 'hypothesis_review',
    'intent_dependencies', 'reassessment_draft', 'reassessment_bundle',
    'reassessment_delivery', 'supervision_progress',
    'check_subject_binding', 'measurement_selection_plan', 'measurement_selection_evaluation',
})


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def _read(db, wid, aid):
    row = db.execute('SELECT * FROM artifacts WHERE workspace=? AND id=?', (wid, aid)).fetchone()
    if row is None:
        raise ValueError('재검토 자료가 이 연구에 없습니다: ' + str(aid))
    value = dict(row)
    if hashlib.sha256(value['content']).hexdigest() != value['sha256']:
        raise ValueError('재검토 원자료 해시가 일치하지 않습니다.')
    value['meta'] = json.loads(value['meta'])
    value['value'] = json.loads(value['content'])
    return value


def _state(store, db, wid):
    from .intent_dependencies import transaction_state
    state = transaction_state(store, db, wid)
    state['decision'] = json.loads(state['decision']) if state['decision'] else None
    return state


def snapshot(store, wid, db=None):
    """The same reader is used before and inside the publication transaction."""
    if db is None:
        with store.connect() as connection:
            return snapshot(store, wid, connection)
    from .intent_dependencies import records, input_snapshot
    state = _state(store, db, wid)
    published = next((e for e in reversed(state['events']) if e['kind'] == 'decision_published'), None)
    parent = published['body']['receipt_id'] if published else None
    sources, assessment_versions = {}, {}
    for row in db.execute('SELECT id,kind,sha256,meta FROM artifacts WHERE workspace=? ORDER BY created,id', (wid,)):
        value = dict(row)
        value['meta'] = json.loads(value['meta'])
        if value['kind'] not in EPHEMERAL:
            sources[value['id']] = {'kind': value['kind'], 'content_sha256': value['sha256'],
                                    'metadata': value['meta']}
        elif value['kind'] == 'discovery_review':
            assessment_versions[value['id']] = value['sha256']
    inputs = deepcopy(sources)
    for record in records(state):
        inputs['intent:' + record['id']] = {'kind': 'intent', 'record': record}
    for event in state['events']:
        if event['kind'] in ('message', 'correction', 'observation'):
            inputs['event:' + str(event['seq'])] = {
                'kind': 'measurement' if event['kind'] == 'observation' else event['kind'],
                'body': event['body'], 'authority': 'researcher_record',
                # Free text alone supplies no machine-verified assay assurance.
                'validity': event['body'].get('validity'),
                'precision': event['body'].get('precision'),
            }
    frame = next((e['body'] for e in reversed(state['events']) if e['kind'] == 'work_framed'), {})
    context = {'workspace': wid, 'question': frame.get('current_question'),
               'intent_ids': sorted(r['id'] for r in records(state)),
               'instructions': {k: v for k, v in inputs.items() if v['kind'] in ('message', 'correction')}}
    value = {'schema_version': VERSION, 'state_revision': state['rev'],
             'parent_decision_id': parent, 'intent_snapshot': input_snapshot(state)['snapshot_sha256'],
             'inputs': inputs, 'evidence': sources, 'context': context,
             'rules': {'version': VERSION, 'measurement_failure': 'hold_not_refutation'},
             'assessment_versions': assessment_versions}
    return {**value, 'snapshot_sha256': digest(value)}


def assessments(store, wid, db=None):
    """Immutable references identify exact rows, not whole review batches."""
    if db is None:
        with store.connect() as connection:
            return assessments(store, wid, connection)
    result = {}
    for row in db.execute("SELECT id,meta FROM artifacts WHERE workspace=? AND kind='discovery_review' ORDER BY created,id", (wid,)):
        artifact = _read(db, wid, row['id'])
        for index, item in enumerate(artifact['value'].get('assessments', [])):
            subject = 'option:' + item['option_id']
            result[subject] = {'subject': subject, 'kind': 'option', 'option_id': item['option_id'],
                'original_ref': row['id'] + '#/assessments/' + str(index),
                'original': item, 'original_hash': digest(item),
                'original_based_rev': artifact['meta'].get('based_rev')}
    state = _state(store, db, wid)
    published = next((e for e in reversed(state['events']) if e['kind'] == 'decision_published'), None)
    parent = published['body']['receipt_id'] if published else None
    for index, item in enumerate((state['decision'] or {}).get('research_loop', {}).get('hypotheses', [])):
        subject = 'hypothesis:' + item['id']
        result[subject] = {'subject': subject, 'kind': 'hypothesis', 'hypothesis_id': item['id'],
            'original_ref': str(parent) + '#/research_loop/hypotheses/' + str(index),
            'original': item, 'original_hash': digest(item), 'original_based_rev': state['decision_rev']}
    return result


def subscription(query, evidence):
    """Exact declared metadata queries, including empty and uncertain results.

Query fields are input descriptor fields, not inferred experimental conditions.
"""
    if not isinstance(query, dict) or set(query) != {'equals'} or not isinstance(query['equals'], dict):
        raise ValueError('근거 구독은 equals 객체로 정확한 필드를 선언하세요.')
    members, uncertain = {}, {}
    for key, value in sorted(evidence.items()):
        if any(field in value and value[field] != wanted for field, wanted in query['equals'].items()):
            continue
        missing = [field for field in query['equals'] if field not in value]
        if missing:
            uncertain[key] = {'missing_fields': missing, 'hash': digest(value)}
        else:
            members[key] = digest(value)
    return {'query_hash': digest(query), 'members': members, 'uncertain': uncertain}


def prior_bundle(store, wid, state_snapshot=None, db=None):
    if db is None:
        with store.connect() as connection:
            return prior_bundle(store, wid, state_snapshot, connection)
    snap = state_snapshot or snapshot(store, wid, db)
    parent = snap['parent_decision_id']
    if not parent:
        return None
    # Historical examples can retain a published decision in state/events while
    # predating artifact-backed publication. Absence means unknown consumption,
    # never an implicitly retained assessment. Existing/corrupt artifacts and
    # explicit bundle references still pass through strict _read/binding checks.
    if db.execute('SELECT 1 FROM artifacts WHERE workspace=? AND id=?', (wid, parent)).fetchone() is None:
        return None
    decision = _read(db, wid, parent)
    aid = decision['meta'].get('finalization_records', {}).get('reassessment_bundle')
    if not aid:
        return None
    bundle = _read(db, wid, aid)
    value = bundle['value']
    if bundle['kind'] != 'reassessment_bundle' or value.get('decision_id') != parent:
        raise ValueError('재검토 기록이 현재 판단에 연결되지 않았습니다.')
    return {**value, 'artifact_id': aid}


def build_plan(rows, snap, prior=None):
    reasons = {key: [] for key in rows}
    prior_rows = (prior or {}).get('reviews', {})
    for key, row in rows.items():
        previous = prior_rows.get(key)
        if not previous or previous.get('outcome') == 'unknown':
            reasons[key].append({'reason': 'consumption_history_unknown', 'path': [key]})
            continue
        trace = previous['trace']
        if trace.get('output_ref') != row['original_ref'] or trace.get('output_hash') != row['original_hash']:
            reasons[key].append({'reason': 'assessment_version_changed', 'path': [key]})
        if not trace.get('scope', {}).get('complete') or not trace.get('scope', {}).get('description', '').strip():
            reasons[key].append({'reason': 'declared_scope_incomplete', 'path': [key]})
        for name, value in (('context_hash', snap['context']), ('rules_hash', snap['rules'])):
            if trace.get(name) != digest(value):
                reasons[key].append({'reason': name + '_changed', 'path': [key]})
        for dependency, old_hash in trace.get('input_hashes', {}).items():
            if dependency not in snap['inputs'] or digest(snap['inputs'][dependency]) != old_hash:
                reasons[key].append({'reason': 'consumed_input_changed', 'path': [dependency, key]})
        for query_id, query in trace.get('queries', {}).items():
            current = subscription(query, snap['evidence'])
            if current.get('uncertain') or current != trace.get('query_results', {}).get(query_id):
                reasons[key].append({'reason': 'evidence_subscription_changed_or_unknown', 'path': [query_id, key]})
    # Full simple paths preserve why a downstream review is needed; cycles stop.
    changed = True
    while changed:
        changed = False
        for key in rows:
            dependencies = declared_upstreams(rows, key, prior)
            for upstream in dependencies:
                source_reasons = reasons.get(upstream, [{'reason': 'missing_upstream_assessment', 'path': [upstream]}])
                for reason in list(source_reasons):
                    if key in reason['path']:
                        continue
                    item = {'reason': 'upstream_review_required', 'path': reason['path'] + [key]}
                    if item not in reasons[key]:
                        reasons[key].append(item)
                        changed = True
    required = sorted(key for key in rows if reasons[key])
    return {'required': required, 'retained': sorted(set(rows) - set(required)),
            'reasons': {key: value for key, value in reasons.items() if value}}


def declared_upstreams(rows, subject, prior=None):
    """Existing explicit claim links imply review obligations, not past reading."""
    inputs = set((prior or {}).get('reviews', {}).get(subject, {}).get('trace', {}).get('upstream_subjects', []))
    original = rows[subject]['original']
    target = original.get('targets_mechanism')
    if target:
        inputs.add('option:' + target['option_id'])
    hypothesis = (original.get('basis') or {}).get('hypothesis_id')
    if hypothesis:
        inputs.add('hypothesis:' + hypothesis)
    return sorted(inputs - {subject})


def view(store, wid, *, job_id=None):
    with store.connect() as db:
        snap = snapshot(store, wid, db)
        rows = assessments(store, wid, db)
        prior = prior_bundle(store, wid, snap, db)
        for subject, row in rows.items():
            row['upstream_subjects'] = declared_upstreams(rows, subject, prior)
        drafts = []
        if job_id:
            for row in db.execute("SELECT id FROM artifacts WHERE workspace=? AND kind='reassessment_draft' ORDER BY created,id", (wid,)):
                draft = _read(db, wid, row['id'])
                if draft['meta'].get('job_id') == job_id and draft['value']['snapshot_sha256'] == snap['snapshot_sha256']:
                    drafts.append({'artifact_id': draft['id'], 'sha256': draft['sha256'], **draft['value']})
        return {'schema_version': VERSION, 'snapshot_sha256': snap['snapshot_sha256'],
                'parent_decision_id': snap['parent_decision_id'], 'state_revision': snap['state_revision'],
                'plan': build_plan(rows, snap, prior), 'assessments': rows,
                'input_ids': list(snap['inputs']), 'input_descriptors': snap['inputs'],
                'drafts': drafts, 'prior_bundle_id': (prior or {}).get('artifact_id'),
                'meaning': 'Declared evidence/condition consumption and version applicability. '
                    'A new model review supplies interpretation; tracking is not biological validation. '
                    'Missing historical consumption remains unknown; a new review establishes a new trace.'}


def delivery_manifest(conversation):
    """Bind exactly the views still present in the actual request conversation."""
    from .model_context import unpack
    manifest, binding, native_aliases = {}, None, {}
    for message in conversation:
        if message.get('role') == 'user' and isinstance(message.get('content'), str):
            try:
                context = unpack(json.loads(message['content']))
                for entry in context.get('COMPLETED_VIEWS', []):
                    if entry.get('call_id'):
                        native_aliases[entry['call_id']] = (entry['reading_id'], entry['sha256'])
            except (ValueError, TypeError, AttributeError, KeyError):
                pass
    for message in conversation:
        if not isinstance(message, dict):
            continue
        raw = message.get('content') if message.get('role') == 'user' else message.get('output')
        if not isinstance(raw, str):
            continue
        try:
            value = unpack(json.loads(raw))
        except (ValueError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        if 'REASSESSMENT' in value:
            binding = value['REASSESSMENT']['snapshot_sha256']
            for entry in value['REASSESSMENT'].get('drafts', []):
                manifest['draft:' + entry['artifact_id']] = {
                    'kind': 'assessment_result', 'sha256': digest(entry), 'value': entry}
        if message.get('type') == 'function_call_output':
            manifest['call:' + str(message['call_id'])] = {'kind': 'native_output', 'sha256': digest(value), 'value': value}
            alias = native_aliases.get(message['call_id'])
            if alias and alias[1] == digest(value):
                manifest[alias[0]] = {'kind': 'native_output', 'sha256': digest(value), 'value': value}
        for entry in value.get('WORKING_READINGS', []):
            if 'content' in entry:
                manifest[entry['reading_id']] = {'kind': 'saved_view', 'sha256': digest(entry['content']), 'value': entry['content']}
        restored = value.get('RESTORED_READING')
        if restored and 'content' in restored:
            manifest[restored['reading_id']] = {'kind': 'restored_view', 'sha256': digest(restored['content']), 'value': restored['content']}
        for entry in value.get('EXPLICIT_SOURCE_VIEWS', {}).get('views', []):
            manifest['explicit:' + entry['view_sha256']] = {'kind': 'explicit_view',
                'sha256': digest(entry['view']), 'value': entry['view']}
    return {'snapshot_sha256': binding, 'views': manifest}


def record_delivery(store, wid, job_id, received):
    return store.add_artifact(wid, '실제 재검토 입력 전달', 'reassessment_delivery', dump(received).encode(),
                              {'job_id': job_id, 'view_only': True}, bump=False)


def _source_ids(value):
    """Literal source addresses only; never infer a read from a catalog mention."""
    found = set()
    if isinstance(value, dict):
        for key in ('artifact_id', 'source_artifact_id'):
            if isinstance(value.get(key), str):
                found.add(value[key])
        # read_evidence_bundle provides actual source rows with explicit ancestry.
        # Nested bibliography or an upstream-ID list is not a delivered body.
        for row in value.get('rows', []):
            if isinstance(row, dict) and isinstance(row.get('source_artifact_id'), str):
                found.add(row['source_artifact_id'])
        if value.get('kind') == 'reassessment_draft_batch':
            found.update(row['artifact_id'] for row in value['results'] if row.get('status') == 'staged_not_published')
    return found


def hypothesis_claims(authored):
    return [authored] + authored.get('assessment_scope', {}).get('parts', []) + authored.get('conditional_alternatives', [])


def record_review(store, wid, rev, job_id, args, received):
    """Stage a new scientific interpretation; it is not published by this call."""
    from .discovery import ASSESSMENT_SHAPES
    from .research_loop import validate_hypotheses
    import jsonschema
    snap = snapshot(store, wid)
    if snap['state_revision'] != rev or received.get('snapshot_sha256') != snap['snapshot_sha256']:
        raise ValueError('재검토 요청 뒤 입력이 바뀌었습니다. 현재 입력을 다시 읽어 주세요.')
    rows = assessments(store, wid)
    subject = args['subject']
    if subject not in rows:
        raise ValueError('REASSESSMENT.assessments의 정확한 subject를 사용하세요.')
    original = rows[subject]
    if not args['reason'].strip() or not args['scope_description'].strip():
        raise ValueError('바뀐 조건에서의 과학적 판단 이유와 검토 범위가 필요합니다.')
    outcome = args['outcome']
    if outcome not in ('changed', 'retained', 'unknown'):
        raise ValueError('재검토 결과 유형을 확인하세요.')
    authored = json.loads(args['new_content_json']) if args['new_content_json'] else None
    if outcome == 'retained':
        if authored is not None and authored != original['original']:
            raise ValueError('retained는 원 판단을 그대로 유지합니다. 내용이 바뀌면 changed를 사용하세요.')
        authored = deepcopy(original['original'])
    elif outcome == 'changed':
        if not isinstance(authored, dict):
            raise ValueError('changed에는 새 평가/가설 객체가 필요합니다.')
        if original['kind'] == 'option':
            jsonschema.validate(authored, {'anyOf': ASSESSMENT_SHAPES})
            if authored['option_id'] != original['option_id']:
                raise ValueError('재검토로 선택지의 정체성을 바꾸지 마세요.')
        else:
            validate_hypotheses([authored], store.snapshot(wid))
            if authored['id'] != original['hypothesis_id']:
                raise ValueError('같은 가설의 해석 변경에는 기존 가설 ID를 유지하세요.')
    elif authored is not None:
        raise ValueError('unknown에는 새 확정 내용을 넣지 않습니다.')
    consumed = args['input_ids']
    if len(consumed) != len(set(consumed)) or not set(consumed) <= set(snap['inputs']):
        raise ValueError('현재 입력의 정확한 ID를 중복 없이 사용하세요.')
    views = args['delivered_view_ids']
    if not set(views) <= set(received['views']):
        raise ValueError('실제 받은 전달본 ID만 소비 기록으로 연결할 수 있습니다.')
    delivered_sources = set().union(*(_source_ids(received['views'][v]['value']) for v in views)) if views else set()
    for aid in consumed:
        if aid in snap['evidence'] and aid not in delivered_sources:
            raise ValueError('근거 목록은 본문 열람이 아닙니다. 소비할 자료의 실제 전달본을 연결하세요: ' + aid)
    if authored is not None:
        cited = (authored.get('support_source_ids', []) + authored.get('challenge_source_ids', [])
                 if original['kind'] == 'option' else
                 [e['source_id'] for claim in hypothesis_claims(authored)
                  for e in claim.get('evidence', []) if e['source_type'] == 'artifact'])
        missing_cited = sorted({ref.split('#', 1)[0] for ref in cited} - set(consumed))
        if missing_cited:
            raise ValueError('새 평가의 지지·반대 근거도 실제로 소비한 입력에 연결하세요. 누락: '
                             + ', '.join(missing_cited) + '. retained는 원 객체의 인용까지 재검토했다는 '
                             '뜻입니다. 이번 범위 밖의 선택지는 unknown과 그 이유로 보존할 수 있습니다. '
                             '그 경우 new_content_json은 빈 문자열이고 실제 소비한 입력만 적습니다. '
                             '이미 검토한 경로를 이어가기 위해 다른 경로의 원문까지 새로 조회할 필요는 없습니다.')
    if outcome != 'unknown' and (not consumed or not args['scope_complete']):
        raise ValueError('changed/retained에는 실제 입력과 scope_complete=true가 필요합니다. '
                         'scope_complete는 선언한 한정 범위의 검토 완료입니다. 미측정 조건은 내용에 '
                         '명시하고, 선언 범위의 검토 자체가 미완료라면 unknown으로 남기거나 검토를 마치세요.')
    queries = json.loads(args['queries_json'])
    if not isinstance(queries, dict):
        raise ValueError('queries_json은 구독 ID와 equals 조건의 객체여야 합니다.')
    query_results = {key: subscription(query, snap['evidence']) for key, query in queries.items()}
    upstream = []
    for aid in args['upstream_review_ids']:
        artifact = store.artifact(wid, aid)
        body = json.loads(artifact['content'])
        if (artifact['kind'] != 'reassessment_draft' or artifact['meta'].get('job_id') != job_id
                or body['snapshot_sha256'] != snap['snapshot_sha256'] or body['subject'] == subject):
            raise ValueError('상위 판단은 같은 입력의 다른 재검토 초안이어야 합니다.')
        if aid not in delivered_sources:
            available = sorted(view_id for view_id, view in received['views'].items()
                               if aid in _source_ids(view['value']))
            help_record = {
                'code': 'upstream_delivery_not_consumed', 'subject': subject,
                'upstream_artifact_id': aid, 'currently_delivered_view_ids': available,
                'next_step': ('Review the indicated draft body, then include its actual view ID in delivered_view_ids. '
                              'upstream_review_ids contains artifact IDs; delivered_view_ids contains view IDs. '
                              'Inspecting the plan again or leaving delivered_view_ids empty does not declare consumption.'
                              if available else
                              'Use inspect_artifact to read this exact upstream draft body, then include the returned actual view ID in delivered_view_ids.'),
                'saved': False, 'bypass_allowed': False,
            }
            raise ValueError('새 상위 판단의 실제 전달 결과를 먼저 받아야 합니다. '
                             + json.dumps(help_record, ensure_ascii=False, sort_keys=True))
        upstream.append({'subject': body['subject'], 'artifact_id': aid, 'sha256': artifact['sha256'], 'outcome': body['outcome']})
    previous = prior_bundle(store, wid, snap)
    prior_upstream = declared_upstreams(rows, subject, previous)
    required = set(build_plan(rows, snap, previous)['required'])
    if outcome != 'unknown' and not (set(prior_upstream) & required) <= {r['subject'] for r in upstream}:
        raise ValueError('영향받은 상위 평가의 새 초안을 먼저 검토하고 소비하세요.')
    arguments = json.loads(args['arguments_json'])
    if not isinstance(arguments, dict) or set(arguments) != {'supports', 'counterarguments'}:
        raise ValueError('arguments_json에 supports와 counterarguments 경로 목록을 모두 넣으세요.')
    evaluated, holds = {}, []
    for kind, paths in arguments.items():
        if not isinstance(paths, list):
            raise ValueError('논거의 각 경로는 입력 ID 목록으로 표현하세요.')
        evaluated[kind] = []
        for path in paths:
            if not isinstance(path, list) or not path or not set(path) <= set(consumed):
                raise ValueError('논거 경로에는 실제로 소비한 입력 ID가 필요합니다.')
            held = [key for key in path if snap['inputs'][key]['kind'] == 'measurement'
                    and (snap['inputs'][key].get('validity') != 'valid'
                         or snap['inputs'][key].get('precision') != 'sufficient')]
            evaluated[kind].append({'input_ids': path, 'usable': not held, 'held_inputs': held})
            holds.extend({'input_id': key, 'reason': 'measurement_validity_or_precision_unresolved',
                          'next': 'Review assay validity and precision; a held measurement does not refute biology.'} for key in held)
    accounted = {key for paths in arguments.values() for path in paths for key in path}
    unassigned_measurements = [key for key in consumed if snap['inputs'][key]['kind'] == 'measurement' and key not in accounted]
    if unassigned_measurements:
        holds.append({'reason': 'measurement_argument_role_unknown', 'input_ids': unassigned_measurements})
    # A held path cannot erase a separate usable support path, or create a refutation.
    all_supports_held = bool(evaluated['supports']) and not any(p['usable'] for p in evaluated['supports'])
    if any(item['outcome'] == 'unknown' for item in upstream):
        holds.append({'reason': 'upstream_review_unresolved'})
    challenged = bool(authored and original['kind'] == 'hypothesis'
        and any(claim.get('assessment') == 'challenged' for claim in hypothesis_claims(authored)))
    refutation_without_usable_counter = bool(challenged and evaluated['counterarguments']
        and not any(p['usable'] for p in evaluated['counterarguments']))
    if all_supports_held or unassigned_measurements or refutation_without_usable_counter or any(item['outcome'] == 'unknown' for item in upstream):
        outcome, authored = 'unknown', None
    trace = {'input_hashes': {key: digest(snap['inputs'][key]) for key in consumed},
             'delivered_views': {key: {'sha256': received['views'][key]['sha256'], 'kind': received['views'][key]['kind']} for key in views},
             'scope': {'description': args['scope_description'], 'complete': args['scope_complete']},
             'context_hash': digest(snap['context']), 'rules_hash': digest(snap['rules']),
             'queries': queries, 'query_results': query_results,
             'upstream_subjects': [item['subject'] for item in upstream], 'upstream_reviews': upstream,
             'arguments': arguments, 'argument_hash': digest(arguments)}
    body = {'schema_version': VERSION, 'snapshot_sha256': snap['snapshot_sha256'],
            'parent_decision_id': snap['parent_decision_id'], 'subject': subject,
            'original_ref': original['original_ref'], 'original_hash': original['original_hash'],
            'outcome': outcome, 'reason': args['reason'], 'content': authored,
            'content_hash': digest(authored), 'trace': trace, 'holds': holds, 'arguments': evaluated,
            'scientific_status': 'model_authored_interpretation'}
    aid = store.add_artifact(wid, '판단 재검토 초안 · ' + subject, 'reassessment_draft', dump(body).encode(),
                              {'based_rev': rev, 'job_id': job_id}, bump=False)
    return {'artifact_id': aid, 'sha256': digest(body), 'status': 'staged_not_published', **body}


def prepare_bundle(store, wid, proposal, discovery, review_ids, received, job_id):
    snap = snapshot(store, wid)
    if received.get('snapshot_sha256') != snap['snapshot_sha256']:
        raise ValueError('최종 응답이 받은 근거·조건 묶음이 현재 상태와 다릅니다.')
    rows = assessments(store, wid)
    previous = prior_bundle(store, wid, snap)
    plan = build_plan(rows, snap, previous)
    if not isinstance(review_ids, list) or len(review_ids) != len(set(review_ids)):
        raise ValueError('게시할 재검토 초안 ID를 중복 없이 지정하세요.')
    delivered = set().union(*(_source_ids(v['value']) for v in received['views'].values())) if received['views'] else set()
    reviews = {}
    for aid in review_ids:
        artifact = store.artifact(wid, aid)
        value = json.loads(artifact['content'])
        if (artifact['kind'] != 'reassessment_draft' or artifact['meta'].get('job_id') != job_id
                or value['snapshot_sha256'] != snap['snapshot_sha256'] or aid not in delivered):
            raise ValueError('실제 받은 같은 작업·입력의 재검토 초안만 게시할 수 있습니다.')
        if value['subject'] in reviews:
            raise ValueError('한 평가에는 최종 재검토 초안 하나만 지정하세요.')
        reviews[value['subject']] = {**value, 'draft_id': aid, 'draft_sha256': artifact['sha256']}
    outputs = {'hypothesis:' + h['id']: h for h in proposal['research_loop']['hypotheses']}
    outputs.update({'option:' + a['option_id']: a for a in (discovery or {}).get('assessments', [])})
    for subject, record in reviews.items():
        current_value = outputs.get(subject, rows.get(subject, {}).get('original'))
        if record['outcome'] != 'unknown' and digest(current_value) != record['content_hash']:
            raise ValueError('최종 가설·선택지 평가가 검토한 초안과 다릅니다: ' + subject)
        for upstream in record['trace']['upstream_reviews']:
            selected = reviews.get(upstream['subject'])
            if not selected or selected.get('draft_id') != upstream['artifact_id'] or selected.get('draft_sha256') != upstream['sha256']:
                raise ValueError('최종 상위 판단과 실제 소비한 상위 초안이 다릅니다.')
    for subject, row in rows.items():
        if subject in reviews:
            continue
        same = subject not in outputs or digest(outputs[subject]) == row['original_hash']
        if subject in plan['retained'] and same:
            reviews[subject] = deepcopy(previous['reviews'][subject])
            reviews[subject]['retention_reason'] = 'declared_scope_and_inputs_unchanged'
        else:
            reviews[subject] = {'subject': subject, 'outcome': 'unknown',
                'reason': 'review_not_returned' if same else 'new_content_without_staged_review',
                'original_ref': row['original_ref'], 'original_hash': row['original_hash'],
                'content': None, 'content_hash': digest(None), 'trace': {}, 'holds': []}
    # A final response may refine inferred intent. That is a new semantic input,
    # not evidence that a staged interpretation already consumed the new text.
    proposed_intents = {'intent:' + r['id']: {'kind': 'intent', 'record': r} for r in proposal['intent_records']}
    for review in reviews.values():
        changed = [key for key, old_hash in review.get('trace', {}).get('input_hashes', {}).items()
                   if key.startswith('intent:') and (key not in proposed_intents or digest(proposed_intents[key]) != old_hash)]
        if changed:
            review.update(outcome='unknown', reason='final_intent_changed_after_review', changed_inputs=changed)
    return {'kind': 'reassessment_bundle', 'title': '판단 변경·근거 사용·재검토 연결',
            'value': {'schema_version': VERSION, 'received_snapshot': snap,
                      'plan': plan, 'reviews': reviews, 'decision_id': None},
            'meta': {'semantic_type': 'declared_reassessment_not_empirical_validation'}}


def bind_bundle(record, decision_aid, discovery_aid, proposal, discovery):
    result = deepcopy(record)
    result['value']['decision_id'] = decision_aid
    outputs = {('hypothesis:' + h['id']): (h, decision_aid + '#/research_loop/hypotheses/' + str(i))
               for i, h in enumerate(proposal['research_loop']['hypotheses'])}
    if discovery_aid:
        outputs.update({('option:' + a['option_id']): (a, discovery_aid + '#/assessments/' + str(i))
                        for i, a in enumerate((discovery or {}).get('assessments', []))})
    for subject, review in result['value']['reviews'].items():
        if review['outcome'] == 'unknown':
            continue
        content, address = outputs.get(subject, (review['content'], review['original_ref']))
        review['trace'].update(output_ref=address, output_hash=digest(content))
    return result


def applicability(store, wid):
    value = view(store, wid)
    required = set(value['plan']['required'])
    return {subject: {'status': 'required_review' if subject in required else 'retained_under_current_inputs',
                      'current': subject not in required,
                      'reason_paths': value['plan']['reasons'].get(subject, []),
                      'original_ref': row['original_ref'], 'original_based_rev': row['original_based_rev'],
                      'snapshot_sha256': value['snapshot_sha256']}
            for subject, row in value['assessments'].items()}
