"""Bind the pure selection kernel to delivered evidence and published judgments."""
from copy import deepcopy
import hashlib
import json

from .store import dump
from . import measurement_selection as kernel
from . import reassessment


def pointer(value, path):
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('측정 선택 근거의 JSON pointer가 필요합니다.')
    try:
        for token in path[1:].split('/'):
            token = token.replace('~1', '/').replace('~0', '~')
            value = value[int(token)] if isinstance(value, list) else value[token]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError('측정 선택 근거의 원문 위치를 확인해 주세요: ' + path) from exc
    return value


def read(store, wid, aid, kind=None):
    artifact = store.artifact(wid, aid)
    if kind and artifact['kind'] != kind:
        raise ValueError('측정 선택 자료의 종류가 다릅니다.')
    if hashlib.sha256(artifact['content']).hexdigest() != artifact['sha256']:
        raise ValueError('측정 선택 원자료 해시가 다릅니다.')
    if artifact['kind'] == 'molecule_csv':
        # Match the original-row view delivered by Runner.inspect. Bind the
        # preserved CSV hash and deterministic row value without rewriting it.
        from .science import molecule_rows
        header, rows = molecule_rows(artifact['content'], artifact['meta'])
        return artifact, {'semantic_type': 'source_table_values', 'header': header,
                          'rows': rows, 'total_rows': len(rows)}
    try:
        body = json.loads(artifact['content'])
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError('측정 선택 근거를 구조화된 원자료 위치에 연결하세요: '
                         + aid + ' (' + artifact['kind'] + '). '
                         '원본 문서는 보존된 source_document 추출 결과를 읽고 참조하세요.') from exc
    return artifact, body


def bind_sources(store, wid, value, received):
    """Resolve literal records, preserving interpretation as an authored declaration."""
    delivered = set().union(*(reassessment._source_ids(v['value'])
        for v in received['views'].values())) if received['views'] else set()
    bindings = {}

    def walk(item):
        if isinstance(item, list):
            return [walk(x) for x in item]
        if not isinstance(item, dict):
            return item
        if 'artifact_id' in item and 'json_pointer' in item:
            if set(item) - {'artifact_id', 'json_pointer', 'sha256'}:
                raise ValueError('근거 참조는 원자료 ID·pointer·선택적 해시만 포함합니다.')
            aid = item['artifact_id']
            if not isinstance(aid, str) or not aid.strip():
                raise ValueError('근거 원자료 ID를 확인하세요.')
            if aid not in delivered:
                raise ValueError('측정 선택에 쓰는 근거의 실제 전달본을 먼저 읽어 주세요: ' + aid)
            artifact, body = read(store, wid, aid)
            if item.get('sha256', artifact['sha256']) != artifact['sha256']:
                raise ValueError('선언한 측정 선택 근거 해시가 원자료와 다릅니다.')
            selected = pointer(body, item['json_pointer'])
            address = aid + '#' + item['json_pointer']
            bindings[address] = {'artifact_id': aid, 'sha256': artifact['sha256'],
                'json_pointer': item['json_pointer'], 'value_sha256': kernel.digest(selected),
                'artifact_kind': artifact['kind']}
            return {**item, 'sha256': artifact['sha256']}
        return {key: walk(part) for key, part in item.items()}

    return walk(value), bindings


def freeze(store, wid, rev, job_id, spec, received):
    snap = reassessment.snapshot(store, wid)
    if not received or received['snapshot_sha256'] != snap['snapshot_sha256'] or snap['state_revision'] != rev:
        raise ValueError('현재 근거·조건을 다시 받은 뒤 측정 선택을 고정하세요.')
    spec, sources = bind_sources(store, wid, spec, received)
    predictions = spec.pop('prediction_bindings', {})
    expected_arms = {arm['id'] for arm in spec['arms'] if arm['kind'] == 'prediction'}
    if not isinstance(predictions, dict) or set(predictions) != expected_arms:
        raise ValueError('계산 순위는 실제 저장된 예측값·후보·구조 위치에 prediction_bindings로 연결하세요.')
    candidates = {row['id']: row for row in spec['candidates']}
    for arm in spec['arms']:
        if arm['kind'] != 'prediction':
            continue
        mapping = predictions[arm['id']]
        if not isinstance(mapping, dict) or set(mapping) != set(arm['scores']):
            raise ValueError('각 계산 점수에 후보·구조·예측값 원위치가 필요합니다.')
        for cid, refs in mapping.items():
            if set(refs) != {'score_ref', 'candidate_ref', 'structure_ref', 'direction'} or refs['direction'] not in ('higher', 'lower'):
                raise ValueError('prediction_bindings의 세 원위치와 점수 방향을 확인하세요.')
            values = {}
            for key in ('score_ref', 'candidate_ref', 'structure_ref'):
                artifact, body = read(store, wid, refs[key]['artifact_id'])
                if artifact['kind'] not in ('activity_prediction', 'analogue_proposal', 'guided_candidate_proposal', 'rna_activity_score'):
                    raise ValueError('계산 순위는 실제 활성 예측 결과 자료에 연결하세요.')
                values[key] = pointer(body, refs[key]['json_pointer'])
            if values['candidate_ref'] != cid or values['structure_ref'] != candidates[cid]['structure_id']:
                raise ValueError('예측값의 후보·구조가 선택 후보와 다릅니다.')
            number = kernel._number(values['score_ref'])
            expected = number if refs['direction'] == 'higher' else -number
            if kernel._number(arm['scores'][cid]) != expected:
                raise ValueError('계산 점수가 보존된 원 예측값과 다릅니다.')
    reviews = []
    for explanation in spec['next_check']['engine2_refs']:
        ref = explanation['source_ref']
        artifact, review = read(store, wid, ref['artifact_id'], 'reassessment_draft')
        if (artifact['meta'].get('job_id') != job_id or review['snapshot_sha256'] != snap['snapshot_sha256']
                or explanation['id'] != review['subject'] or explanation['revision'] != review['content_hash']):
            raise ValueError('설명은 같은 작업에서 실제 받은 재검토 초안의 subject·content_hash에 연결하세요.')
        reviews.append({'subject': review['subject'], 'artifact_id': artifact['id'],
            'sha256': artifact['sha256'], 'content_hash': review['content_hash'], 'outcome': review['outcome']})
    if not reviews:
        raise ValueError('측정 선택을 설명별 재검토 초안에 먼저 연결하세요.')
    plan = kernel.freeze_plan(spec)
    result = {'schema_version': '1', 'plan': plan, 'evaluation': kernel.evaluate(plan),
        'handoff': kernel.handoff(plan), 'source_bindings': sources, 'prediction_bindings': predictions,
        'binding': {'state_revision': rev, 'snapshot_sha256': snap['snapshot_sha256'],
            'context_hash': reassessment.digest(snap['context']),
            'parent_decision_id': snap['parent_decision_id'], 'engine2_reviews': reviews},
        'interpretation': 'Source locations and hashes are verified. Condition extraction, readiness and scientific interpretation are authored declarations; no biological result is created.'}
    aid = store.add_artifact(wid, '측정할 후보·조건·예산과 다음 관측', 'measurement_selection_plan',
        dump(result).encode(), {'based_rev': rev, 'job_id': job_id, 'derived_plan': True,
                              'scientific_validation': False}, bump=False)
    artifact = store.artifact(wid, aid)
    return {'artifact_id': aid, 'sha256': artifact['sha256'], 'kind': artifact['kind'], 'result': result}


def evaluate(store, wid, rev, job_id, plan_id, outcome_id, received):
    if not received or not received.get('views'):
        raise ValueError('평가할 측정 자료와 고정 계획의 실제 전달본을 먼저 읽어 주세요.')
    delivered = set().union(*(reassessment._source_ids(v['value']) for v in received['views'].values()))
    if not {plan_id, outcome_id} <= delivered:
        raise ValueError('평가할 측정 자료와 고정 계획의 실제 전달본을 먼저 읽어 주세요.')
    artifact, frozen = read(store, wid, plan_id, 'measurement_selection_plan')
    observation, outcome = read(store, wid, outcome_id, 'measurement_outcomes')
    if observation['meta'].get('origin') not in ('researcher', 'source_dataset'):
        raise ValueError('평가에는 연구자가 제공했거나 출처 자료에서 가져온 실제 관측 자료가 필요합니다.')
    # Origin is a provenance record, not independent scientific verification.
    outcome, bindings = bind_sources(store, wid, outcome, received)
    # This adapter has no independently administered label embargo. Preserve the
    # source's claim separately; a timestamp alone cannot make old data held out.
    declared_inspection = outcome['inspection_status']
    outcome['inspection_status'] = 'retrospective'
    result = {'plan_id': plan_id, 'plan_sha256': artifact['sha256'], 'outcome_id': outcome_id,
              'outcome_sha256': observation['sha256'], 'source_bindings': bindings,
              'evaluation': kernel.evaluate(frozen['plan'], outcome),
              'declared_inspection_status': declared_inspection,
              'inspection_status_reason': 'No independently verified embargo in this native adapter.',
              'meaning': 'Finite-pool arithmetic on supplied observations; actual validity and precision remain source-qualified.'}
    aid = store.add_artifact(wid, '고정 예산의 실제 측정 선택 비교', 'measurement_selection_evaluation',
        dump(result).encode(), {'based_rev': rev, 'job_id': job_id, 'derived_evaluation': True}, bump=False)
    return {'artifact_id': aid, 'sha256': store.artifact(wid, aid)['sha256'], 'result': result}


def validate_final(store, wid, proposal, records, received, job_id):
    bundle = next((r['value'] for r in records if r['kind'] == 'reassessment_bundle'), None)
    for check in proposal['research_loop']['next_checks']:
        aid = check.get('measurement_selection_id')
        if not aid:
            continue
        artifact, value = read(store, wid, aid, 'measurement_selection_plan')
        if (not bundle or not received or artifact['meta'].get('job_id') != job_id
                or value['binding']['snapshot_sha256'] != received['snapshot_sha256']):
            raise ValueError('다음 관측에는 같은 입력에서 고정한 측정 선택과 재검토 묶음이 필요합니다.')
        delivered = set().union(*(reassessment._source_ids(v['value']) for v in received['views'].values()))
        if aid not in delivered:
            raise ValueError('측정 선택 결과를 실제로 받은 뒤 다음 관측에 연결하세요.')
        kernel.handoff(value['plan'])  # Recheck seal and internal consistency.
        for source in value['source_bindings'].values():
            original, content = read(store, wid, source['artifact_id'])
            if original['sha256'] != source['sha256'] or kernel.digest(pointer(content, source['json_pointer'])) != source['value_sha256']:
                raise ValueError('측정 선택이 고정한 근거가 달라졌습니다.')
        for review in value['binding']['engine2_reviews']:
            selected = bundle['reviews'].get(review['subject'], {})
            if selected.get('draft_id') != review['artifact_id'] or selected.get('draft_sha256') != review['sha256']:
                raise ValueError('실험 설계가 소비한 설명과 최종 게시할 설명이 다릅니다.')
        if check['operation']['kind'] != 'external_observation':
            raise ValueError('측정 후보 선택은 새 외부 관측 제안에 연결하세요.')


def view(store, wid, state):
    result = {}
    snap = reassessment.snapshot(store, wid)
    applicable = reassessment.applicability(store, wid)
    for check in (state.get('decision') or {}).get('research_loop', {}).get('next_checks', []):
        aid = check.get('measurement_selection_id')
        if not aid:
            continue
        _, value = read(store, wid, aid, 'measurement_selection_plan')
        binding = value['binding']
        current = (binding['state_revision'] == state['rev']
            and binding['context_hash'] == reassessment.digest(snap['context'])
            and all(applicable.get(r['subject'], {}).get('current') for r in binding['engine2_reviews']))
        result[check['id']] = {'artifact_id': aid, 'current': current,
            'handoff': deepcopy(value['handoff']), 'evaluation': deepcopy(value['evaluation']),
            'arms': deepcopy(value['plan']['arms']), 'meaning': value['interpretation']}
    return result
