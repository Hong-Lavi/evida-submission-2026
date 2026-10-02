"""Explicit small source views for a review whose tools may be disabled.

These are delivery evidence, not a claim that the model read or understood them.
No relevance selection or archive-wide automatic inclusion happens here.
"""
import hashlib
import json

MAX_PROVIDED_BYTES = 60000  # Local review boundary, not a provider context limit.


def completed_check(runner, wid, artifact_id):
    """Carry a small completed result, not an automatic archive relevance search.

    This supplies the exact stored presentation of the check the researcher
    chose. Large/binary results stay accessible through the source catalog;
    their first page is not silently substituted for the complete result.
    """
    record = {'artifact_id': artifact_id, 'original_preserved': True,
              'status': 'catalog_only', 'meaning': 'Delivery is not model reading or scientific validation.'}
    if artifact_id is None:
        return {}, {**record, 'reason': 'No result artifact was produced.'}
    artifact = runner.store.artifact(wid, artifact_id)
    if artifact['media_type'] != 'application/json':
        return {}, {**record, 'reason': 'Keep binary or non-JSON source access in its existing route.'}
    value = json.loads(artifact['content'])
    if not isinstance(value, dict):
        return {}, {**record, 'reason': 'The existing range-view contract expects an object.'}
    rows = value.get('rows')
    if isinstance(rows, list) and len(rows) > 100:
        return {}, {**record, 'reason': 'Result exceeds one explicit range; keep all rows selectable.', 'total_rows': len(rows)}
    specifications = [{'artifact_id': artifact_id, 'offset': 0,
                       'limit': max(1, len(rows)) if isinstance(rows, list) else 1}]
    try:
        delivered = build(runner, wid, specifications)
    except ValueError as exc:
        return {}, {**record, 'reason': str(exc), 'requires_range_selection': True}
    return {'source_views': specifications}, {**record,
        'status': 'exact_completed_presentation_supplied',
        'source_sha256': artifact['sha256'], 'encoded_bytes': delivered['encoded_bytes'],
        'specifications': specifications,
        'limit': 'Remote pagination, nested partial views and source limitations remain explicit in the supplied result.'}


def build(runner, wid, specifications):
    if not isinstance(specifications, list) or len(specifications) > 12:
        raise ValueError('명시적으로 전달할 원문 범위를 12개 이내로 선택해 주세요. 원자료는 삭제하지 않습니다.')
    views = []
    seen = set()
    for spec in specifications:
        if not isinstance(spec, dict) or set(spec) not in ({'artifact_id', 'offset', 'limit'}, {'artifact_id', 'offset', 'limit', 'section'}):
            raise ValueError('전달할 자료ID·행 시작·개수를 정확히 지정해 주세요.')
        if not isinstance(spec['artifact_id'], str):
            raise ValueError('전달할 자료ID를 확인해 주세요.')
        if type(spec['offset']) is not int or spec['offset'] < 0 or type(spec['limit']) is not int or not 1 <= spec['limit'] <= 100:
            raise ValueError('전달할 원문 행 시작과 개수를 확인해 주세요.')
        if 'section' in spec and not isinstance(spec['section'], str):
            raise ValueError('계산표 이름을 정확히 지정해 주세요.')
        key = (spec['artifact_id'], spec.get('section'), spec['offset'], spec['limit'])
        if key in seen:
            raise ValueError('동일한 원문 범위를 중복 전달하지 않습니다.')
        seen.add(key)
        artifact = runner.store.artifact(wid, spec['artifact_id'])
        if artifact['media_type'] != 'application/json':
            raise ValueError('이 경로는 JSON 원문·계산 결과의 범위 전달용입니다. PDF/그림의 바이너리를 텍스트로 치환하지 않습니다.')
        view = (runner.calculation_section(wid, spec['artifact_id'], spec['section'], spec['offset'], spec['limit'])
                if 'section' in spec else runner.inspect(wid, spec['artifact_id'], spec['offset'], spec['limit']))
        raw = json.dumps(view, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        views.append({'specification': dict(spec), 'source_sha256': artifact['sha256'],
            'view_sha256': hashlib.sha256(raw).hexdigest(), 'view': view,
            'status': 'explicitly_supplied_not_claimed_model_reading'})
    encoded = json.dumps(views, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    if len(encoded) > MAX_PROVIDED_BYTES:
        raise ValueError('명시 원문 전달이 현재 검토 범위를 넘었습니다. 범위를 나누거나 도구 읽기가 가능한 검토로 진행해 주세요. 조용히 잘라내지 않습니다.')
    return {'views': views, 'encoded_bytes': len(encoded),
        'policy': 'Exact application-selected views; originals and other ranges remain accessible. Delivery is not understanding, scientific validation or an exhaustive evidence set.'}
