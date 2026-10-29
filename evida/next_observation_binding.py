"""Bind optional selections to retained native decisions, sources and observation events."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import jsonschema

from .next_observation import CALCULATION_VERSION, SEMANTIC_TYPE, ids, require, schema_for, select, validate_problem, validate_version

TOOL = 'next_observation_selection'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def loads(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'JSON 객체 키가 중복됐습니다.')
            value[key] = item
        return value
    def constant(value):
        raise ValueError('유한하지 않은 JSON 숫자: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def validate_arguments(arguments, *, calculation_version=CALCULATION_VERSION):
    try:
        jsonschema.validate(arguments, schema_for(calculation_version))
    except jsonschema.ValidationError as exc:
        raise ValueError('다음 관측 선택 형식을 확인해 주세요: ' + exc.message[:400]) from None
    ids(arguments['source_artifact_ids'])
    ids([arguments['artifact_id']])
    if arguments['mode'] == 'plan':
        require(arguments['problem'] is not None and arguments['result'] is None, 'plan에는 조건표만 제공해 주세요.')
        validate_problem(arguments['problem'], calculation_version=calculation_version)
    else:
        require(arguments['problem'] is None and arguments['result'] is not None, '결과 검토는 원 선택 자료의 조건표를 사용합니다.')
        ids([arguments['result']['message_id']]); ids([arguments['result']['check_id']])


def prepare(store, wid, arguments, *, amendment_id=None, own_job=None, _history_only=False):
    """Read only; build the exact serializable snapshot used for cache and worker."""
    if amendment_id is not None:
        from .observation_amendment import prepare as prepare_amendment
        return prepare_amendment(store, wid, arguments, amendment_id, own_job=own_job)
    validate_arguments(arguments)
    state = store.snapshot(wid)
    records = {}
    source_message_ids = set()

    def source(sid):
        # Native review prediction sources may be saved messages as well as artifacts.
        # Keep their roles separate: a cited observation is not a newly applied result.
        ids([sid])
        matches = [e for e in state['events'] if e.get('body', {}).get('message_id') == sid]
        if matches:
            require(len(matches) == 1, '원 출처 메시지의 ID가 중복됐습니다.')
            source_message_ids.add(sid)
        else:
            get(sid)

    def get(aid):
        ids([aid])
        if aid not in records:
            artifact = store.artifact(wid, aid)
            records[aid] = {key: artifact[key] for key in ('id', 'kind', 'sha256', 'title', 'meta')}
            records[aid]['content_base64'] = base64.b64encode(artifact['content']).decode('ascii')
        if records[aid]['kind'] in ('decision_proposal', 'hypothesis_review', TOOL):
            return loads(base64.b64decode(records[aid]['content_base64']))
        return None  # Scientific source bytes may be non-JSON; hash them without reinterpretation.

    aid = arguments['artifact_id']
    message_ids = []
    amendment_event_ids = set()
    chain = []
    if arguments['mode'] == 'review_result':
        while aid:
            require(aid not in chain and len(chain) < 32, '선택 이력의 순환 또는 길이 범위를 확인해 주세요.')
            value = get(aid)
            require(records[aid]['kind'] == TOOL and value.get('status') == 'succeeded' and value.get('semantic_type') == SEMANTIC_TYPE,
                    '보존된 성공 선택 결과를 연결해 주세요.')
            require(any(j['kind'] == TOOL and j['status'] in ('succeeded', 'reused') and j.get('output_id') == aid for j in state['jobs']),
                    '실제 도구 작업이 보존한 선택 결과가 아닙니다.')
            chain.append(aid)
            message_ids.extend(value.get('binding', {}).get('observation_message_ids', []))
            amendment_event_ids.update(value.get('observation_amendment', {}).get('replay_event_ids', []))
            for source_id in value.get('provenance', {}).get('source_hashes', {}):
                get(source_id)
            for source_id in value.get('provenance', {}).get('source_message_hashes', {}):
                source(source_id)
            aid = value.get('binding', {}).get('prior_selection_id')
        root = get(chain[-1])
        decision_id = root.get('binding', {}).get('decision_id')
        message_ids.append(arguments['result']['message_id'])
    else:
        decision_id = aid
    decision = get(decision_id)
    review_id = records[decision_id]['meta'].get('finalization_records', {}).get('hypothesis_review')
    require(review_id, '원 판단에 결속된 가설 검토가 없습니다.')
    get(review_id)
    subject_binding_id = None
    if any('subject_refs' in c for c in decision['research_loop']['next_checks']):
        from .check_subject_binding import find
        with store.connect() as db:
            subject_record = find(db, wid, decision_id)
        require(subject_record is not None, '원 판단의 대상 결속이 없습니다.')
        subject_binding_id = subject_record['artifact_id']
        get(subject_binding_id)
        for check in subject_record['value']['checks']:
            for subject in check['subjects']:
                get(subject['artifact_id'])
    for source_id in arguments['source_artifact_ids']:
        get(source_id)
    # Bind every original review source too; no source list can hide counterevidence.
    review = get(review_id)
    source_ids = set()
    for step in review.get('review', {}).get('causal_steps', []):
        for group in step.get('evidence_groups', []):
            source_ids.update(a['artifact_id'] for a in group.get('anchors', []))
    for observation in review.get('review', {}).get('observations', []):
        for prediction in observation.get('predictions', []):
            source_ids.update(prediction.get('source_ids', []))
    for source_id in sorted(source_ids):
        source(source_id)
    selected_events = {}

    def event(mid, observation=False):
        matches = [e for e in state['events'] if e.get('body', {}).get('message_id') == mid]
        require(len(matches) == 1 and (not observation or matches[0]['kind'] == 'observation'),
                '원 관측/출처 메시지를 정확히 연결해 주세요.')
        if mid not in selected_events:
            selected_events[mid] = {k: copy.deepcopy(matches[0][k]) for k in ('seq', 'workspace', 'kind', 'body', 'created')}
            # Bind attached scientific bytes even when the model omits them from arguments.
            body = matches[0]['body']
            for ref in body.get('reported_subject_refs', []):
                get(ref['artifact_id'])
            for source_id in body.get('source_artifact_ids', []):
                get(source_id)
                require(records[source_id]['sha256'] == body.get('source_artifact_hashes', {}).get(source_id),
                        '관측에 보존한 원자료 해시가 다릅니다.')
            target = matches[0]['body'].get('provenance_correction', {}).get('target_message_id')
            if target:
                event(target)

    for mid in dict.fromkeys(message_ids):
        event(mid, observation=True)
    for mid in sorted(source_message_ids | amendment_event_ids):
        event(mid)
    # snapshot() attaches a current classification without changing the stored body.
    # Hash only immutable stored fields, and retain later correction receipts separately.
    for saved in state['events']:
        if saved['kind'] == 'correction' and saved['body'].get('provenance_correction', {}).get('target_message_id') in selected_events:
            event(saved['body']['message_id'])
    selected_events = sorted(selected_events.values(), key=lambda item: item['seq'])
    bundle = {'calculation_version': CALCULATION_VERSION,
              'arguments': copy.deepcopy(arguments), 'workspace_id': wid, 'decision_id': decision_id,
              'review_id': review_id, 'check_subject_binding_id': subject_binding_id, 'prior_chain': list(reversed(chain)), 'artifacts': records,
              'events': selected_events, 'source_message_ids': sorted(source_message_ids),
              'source_message_hashes': {e['body']['message_id']: digest(e) for e in selected_events
                                        if e['body']['message_id'] in source_message_ids},
              'published_decision_ids': [e['body']['receipt_id'] for e in state['events'] if e['kind'] == 'decision_published']}
    evaluate(bundle, _history_only=_history_only)  # Verify before enqueuing any work.
    return bundle


def evaluate(bundle, *, _history_only=False, _depth=0):
    """Verify transfer and recompute the immutable chain; return a new sidecar."""
    from .hypothesis_review import loop_sha256
    from .research_loop import validate_feedback
    from .input_provenance import annotate_events

    calculation_version = validate_version(bundle.get('calculation_version', '1'))
    args = bundle['arguments']; validate_arguments(args, calculation_version=calculation_version)
    records, values = bundle['artifacts'], {}
    for aid, record in records.items():
        raw = base64.b64decode(record['content_base64'], validate=True)
        require(aid == record['id'] and hashlib.sha256(raw).hexdigest() == record['sha256'], '전달된 원 자료의 ID 또는 해시가 다릅니다.')
        if record['kind'] in ('decision_proposal', 'hypothesis_review', TOOL):
            values[aid] = loads(raw)
    did, rid = bundle['decision_id'], bundle['review_id']
    require(did in bundle['published_decision_ids'] and records[did]['kind'] == 'decision_proposal', '실제 게시한 원 판단을 선택해 주세요.')
    decision, review = values[did], values[rid]
    loop = decision['research_loop']; loop_hash = loop_sha256(loop)
    require(records[did]['meta'].get('finalization_records', {}).get('hypothesis_review') == rid
            and records[rid]['kind'] == 'hypothesis_review' and review.get('schema_version') == '1'
            and review.get('decision_id') == did and records[rid]['meta'].get('decision_id') == did
            and review.get('loop_sha256') == loop_hash and records[rid]['meta'].get('loop_sha256') == loop_hash
            and review.get('based_rev') == decision.get('based_on_state_rev')
            and records[rid]['meta'].get('based_rev') == decision.get('based_on_state_rev'), '원 판단과 가설 검토의 결속이 다릅니다.')
    chain = bundle['prior_chain']
    problem = args['problem'] if args['mode'] == 'plan' else values[chain[0]]['problem']
    validate_problem(problem, calculation_version=calculation_version)
    hypotheses = {h['id']: h for h in loop['hypotheses']}
    checks = {c['id']: c for c in loop['next_checks']}
    reviewed = {o['check_id']: o for o in review['review']['observations']}
    for world in problem['worlds']:
        for member in world['members']:
            h = hypotheses.get(member['hypothesis_id'])
            require(h is not None and set(member['alternative_ids']) <= {a['id'] for a in h.get('conditional_alternatives', [])}
                    and set(member['part_ids']) <= {p['id'] for p in h.get('assessment_scope', {}).get('parts', [])}, '상황이 원 판단에 없는 가설/부분/설명을 참조합니다.')
    for action in problem['actions']:
        check = checks.get(action['check_id'])
        require(check is not None, '원 판단에 없는 다음 확인입니다.')
        require(all(i < len(check['possible_outcomes']) for i in action['adequate_outcome_indices']), '원 확인에 없는 결과 번호입니다.')
        declared_review = reviewed.get(action['check_id'])
        if action['design_validated'] and action['precision_plan_defined']:
            interpretations = {o['outcome_index']: o['interpretation'] for o in declared_review['outcomes']} if declared_review else {}
            require(declared_review and declared_review['validity_requirements'] and all(str(x).strip() for x in declared_review['validity_requirements'])
                    and declared_review['precision_requirement'].strip()
                    and all(interpretations.get(i) == 'adequate_measurement' for i in action['adequate_outcome_indices']),
                    '원 검토의 미확인/측정 실패 결과를 유효한 결과로 승격할 수 없습니다.')
        require(not action['available'] or check.get('operation', {}).get('kind') in ('tool', 'external_observation', 'researcher_input'),
                '연결되지 않은 방법을 사용 가능한 확인으로 표시할 수 없습니다.')
        for prediction in action['predictions']:
            require(set(prediction['source_artifact_ids']) <= set(records), '예상에 연결한 출처를 실제 보존 입력으로 지정해 주세요.')
    all_events = {e['body']['message_id']: e for e in bundle['events']}
    require(len(all_events) == len(bundle['events']) and all(e['workspace'] == bundle['workspace_id'] for e in bundle['events']),
            '전달된 메시지 ID 또는 연구 결속이 다릅니다.')
    source_message_ids = bundle.get('source_message_ids', [])
    require(isinstance(source_message_ids, list), '원 출처 메시지 ID 목록을 확인해 주세요.')
    # The small planning bound is not a limit on a native review's evidence history.
    ids(source_message_ids, maximum=len(source_message_ids))
    source_message_hashes = {mid: digest(all_events[mid]) for mid in source_message_ids if mid in all_events}
    require(set(source_message_ids) <= set(all_events) and source_message_hashes == bundle.get('source_message_hashes', {}),
            '전달된 원 출처 메시지의 해시가 다릅니다.')
    events = {mid: e for mid, e in all_events.items() if e['kind'] == 'observation'}
    from .check_subject_binding import verify_worker_binding, guarded_calculation_v2
    subject_comparisons = verify_worker_binding(bundle, records, decision)
    event_hashes = {mid: digest(event) for mid, event in events.items()}
    classifications = {e['body']['message_id']: e.get('effective_provenance')
                       for e in annotate_events(copy.deepcopy(bundle['events']))}
    from .measurement_report import preserved_fields, compare_report, guarded_calculation, SOURCE_KINDS
    for event in all_events.values():
        body = event['body']
        for source_id in body.get('source_artifact_ids', []):
            record = records.get(source_id)
            require(record and record['kind'] in SOURCE_KINDS
                    and record['sha256'] == body.get('source_artifact_hashes', {}).get(source_id),
                    '전달된 관측 원자료의 종류 또는 해시가 다릅니다.')

    def result_binding(result):
        event = events.get(result['message_id'])
        require(event is not None and event['kind'] == 'observation', '보존된 관측 메시지가 없습니다.')
        context = event['body'].get('research_context')
        require(context and context.get('decision_id') == did and context.get('check_id') == result['check_id'], '관측의 원 판단/확인이 다릅니다.')
        validate_feedback(context, decision)
        require(result['check_id'] in checks and (result['outcome_index'] is None or result['outcome_index'] < len(checks[result['check_id']]['possible_outcomes'])),
                '실제 관측의 결과 번호가 원 확인에 없습니다.')

    retained = None
    used_messages = []
    previous = None
    before_last = None
    for aid in chain:
        before_last = (copy.deepcopy(retained), list(used_messages), previous)
        old = values[aid]; bound = old['binding']
        old_calculation_version = validate_version(old.get('calculation_version', '1'))
        # Old artifacts keep the old numeric input domain as well as their outputs.
        validate_problem(old['problem'], calculation_version=old_calculation_version)
        require(records[aid]['kind'] == TOOL and old.get('semantic_type') == SEMANTIC_TYPE and old.get('status') == 'succeeded'
                and old.get('schema_version') == '1' and old.get('problem_sha256') == digest(problem)
                and old.get('problem') == problem and bound.get('decision_id') == did
                and bound.get('decision_sha256') == records[did]['sha256'] and bound.get('hypothesis_review_id') == rid
                and bound.get('hypothesis_review_sha256') == records[rid]['sha256'] and bound.get('loop_sha256') == loop_hash
                and bound.get('prior_selection_id') == previous, '선택 이력의 원 조건표 또는 판단 결속이 다릅니다.')
        for source_id, sha in old['provenance']['source_hashes'].items():
            require(source_id in records and records[source_id]['sha256'] == sha, '선택 이력의 출처 해시가 다릅니다.')
        for source_id, sha in old['provenance'].get('source_message_hashes', {}).items():
            require(source_message_hashes.get(source_id) == sha, '선택 이력의 원 출처 메시지 해시가 다릅니다.')
        assessment = old.get('result_assessment')
        if assessment is not None:
            result_binding(assessment)
            require(assessment['message_id'] not in used_messages, '같은 관측을 새로운 결과로 반복 적용할 수 없습니다.')
            used_messages.append(assessment['message_id'])
        # Replay each saved sidecar under its recorded rule; never retrofit old results.
        guard_version = old.get('report_guard_version')
        require(guard_version in (None, '1', '2'), '알 수 없는 관측 보고 보호 규칙입니다.')
        if old.get('observation_amendment'):
            from .observation_amendment import replay
            expected = replay(old, bundle, depth=_depth)
            require(all(old.get(key) == value for key, value in expected.items() if key != 'provenance'),
                    '선택 이력의 동일 관측 정정 계산이 다릅니다.')
            # evaluate returns scientific provenance; run additionally records the
            # historical execution. Compare the former exactly without replacing
            # retained input/code digests with this replay's current code hashes.
            provenance, expected_provenance = old['provenance'], expected['provenance']
            execution_keys = {'input_bundle_sha256', 'code_sha256'}
            extras = set(provenance) - set(expected_provenance)
            require(all(provenance.get(key) == value for key, value in expected_provenance.items())
                    and extras in (set(), execution_keys), '선택 이력의 정정 출처 또는 실행 기록이 다릅니다.')
            if extras:
                def is_sha256(value):
                    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)
                code_hashes = provenance['code_sha256']
                require(is_sha256(provenance['input_bundle_sha256'])
                        and isinstance(code_hashes, dict) and bool(code_hashes)
                        and all(isinstance(name, str) and name.endswith('.py') and is_sha256(sha)
                                for name, sha in code_hashes.items()), '선택 이력의 실행 입력 또는 코드 해시 형식이 다릅니다.')
        elif guard_version == '2':
            expected, expected_guard, expected_subject_guard = guarded_calculation_v2(problem, retained, assessment,
                events[assessment['message_id']]['body'] if assessment is not None else {},
                subject_comparisons.get(assessment['message_id']) if assessment is not None else None,
                calculation_version=old_calculation_version)
            require(old.get('report_guard') == expected_guard and old.get('subject_guard') == expected_subject_guard,
                    '선택 이력의 관측/대상 보호 기록이 다릅니다.')
        elif guard_version == '1':
            expected, expected_guard = guarded_calculation(problem, retained, assessment,
                events[assessment['message_id']]['body'] if assessment is not None else {},
                calculation_version=old_calculation_version)
            require(old.get('report_guard') == expected_guard, '선택 이력의 관측 보고 보호 기록이 다릅니다.')
        else:
            expected = select(problem, retained, assessment, calculation_version=old_calculation_version)
        if old_calculation_version == '2' and not old.get('observation_amendment'):
            require(all(old.get(key) == value for key, value in expected.items()),
                    '선택 이력의 비용·실행 조건 또는 조건부 계산이 다릅니다.')
        require(expected['summary'] == old['summary'] and bound.get('observation_message_ids') == used_messages
                and bound.get('observation_hashes') == {m: event_hashes[m] for m in used_messages}, '선택 이력의 조건부 계산 또는 관측 해시가 다릅니다.')
        retained = expected['summary']['retained_configuration_ids']
        previous = aid
    if _history_only:
        return {'retained': retained, 'used_messages': used_messages, 'previous': previous}
    amendment = None
    effective_body = None
    effective_comparison = None
    if bundle.get('observation_amendment_id'):
        from .observation_amendment import verify
        effective_body, effective_comparison, amendment = verify(bundle, values, records)
        require(previous == args['artifact_id'], '정정할 말단 결과가 다릅니다.')
        retained, used_messages, previous = before_last
    if args['mode'] == 'review_result':
        require(amendment is not None or previous == args['artifact_id'], '결과 검토의 마지막 원 선택 자료가 다릅니다.')
        result_binding(args['result'])
        require(args['result']['message_id'] not in used_messages, '같은 관측을 새로운 결과로 반복 적용할 수 없습니다.')
        used_messages.append(args['result']['message_id'])
    calculated, report_guard, subject_guard = guarded_calculation_v2(problem, retained, args['result'],
        effective_body if amendment is not None else events[args['result']['message_id']]['body'] if args['result'] is not None else {},
        effective_comparison if amendment is not None else subject_comparisons.get(args['result']['message_id']) if args['result'] is not None else None,
        calculation_version=calculation_version)
    source_hashes = {aid: r['sha256'] for aid, r in records.items()}
    return {'status': 'succeeded', 'schema_version': '1', 'semantic_type': SEMANTIC_TYPE, **calculated,
            **({'observation_amendment': amendment} if amendment is not None else {}),
            'problem': copy.deepcopy(problem), 'problem_sha256': digest(problem),
            'report_guard_version': '2', 'report_guard': report_guard, 'subject_guard': subject_guard,
            'check_subject_binding_id': bundle.get('check_subject_binding_id'),
            'checks': [{k: copy.deepcopy(checks[a['check_id']][k]) for k in ('id', 'question', 'possible_outcomes')} for a in problem['actions']],
            'result_assessment': copy.deepcopy(args['result']),
            'measurement_report_comparison': ([compare_report(events[args['result']['message_id']]['body'], args['result'])]
                if args['result'] is not None and 'measurement_report' in events[args['result']['message_id']]['body'] else []),
            'observed_events': [{'message_id': m, 'origin': events[m]['body'].get('origin', 'unknown'),
                                 'text': events[m]['body']['text'],
                                 **preserved_fields(events[m]['body']),
                                 'research_context': copy.deepcopy(events[m]['body'].get('research_context')),
                                 'effective_provenance': classifications[m],
                                 'event_sha256': event_hashes[m]} for m in used_messages],
            'source_events': [{'message_id': m, 'kind': all_events[m]['kind'],
                               'body': copy.deepcopy(all_events[m]['body']),
                               'effective_provenance': classifications[m],
                               'event_sha256': source_message_hashes[m]} for m in source_message_ids],
            'binding': {'decision_id': did, 'decision_sha256': records[did]['sha256'], 'hypothesis_review_id': rid,
                        'hypothesis_review_sha256': records[rid]['sha256'], 'loop_sha256': loop_hash,
                        'prior_selection_id': previous, 'observation_message_ids': used_messages,
                        'observation_hashes': {m: event_hashes[m] for m in used_messages},
                        'display_scope': 'preserved_decision_conditions_not_automatically_current_recommendation'},
            'provenance': {'source_hashes': source_hashes, 'source_message_hashes': source_message_hashes,
                           'argument_sha256': digest(args),
                           'observation_origins': {m: events[m]['body'].get('origin', 'unknown') for m in used_messages},
                           'observation_context_sha256': digest(bundle['events']),
                           'declaration_authority': 'Tool argument declarations; the requested kind does not authenticate researcher approval or experimental validity.',
                           'researcher_authority_verified': False, 'result_assessment_is_interpretation': True,
                           'scientific_validation': False,
                           'report_guard_meaning': 'Explicit reported failure or unknown cannot be promoted by model interpretation for exclusion; researcher reporting is not scientific validation.'}}


def stage(bundle, attempt):
    path = Path(attempt) / 'next-observation-input.json'
    raw = encoded(bundle); path.write_bytes(raw)
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
            'consumed_artifacts': list(bundle['artifacts']),
            'consumed_source_messages': list(bundle.get('source_message_ids', []))}


def run(request):
    transfer = request['next_observation_input']
    raw = Path(transfer['path']).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == transfer['sha256'], '선택 계산의 전체 입력 전달 해시가 다릅니다.')
    bundle = loads(raw)
    require(bundle['arguments'] == request['arguments'], '작업 인수와 보존 입력이 다릅니다.')
    result = evaluate(bundle)
    result['provenance']['input_bundle_sha256'] = transfer['sha256']
    result['provenance']['code_sha256'] = {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
        for name in ('next_observation.py', 'next_observation_binding.py', 'measurement_report.py', 'check_subject_binding.py', 'observation_amendment.py')}
    return result
