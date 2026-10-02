"""Join selected public evidence to the drug's reported mechanism, without voting.

Open Targets direction labels and ChEMBL action types describe different levels.
Preserve both, nulls, original evidence IDs, trial conditions and raw responses.
"""
from collections import Counter
import hashlib
import json
import urllib.parse

from .science import fetch
from .target_evidence import identifier


def page_coverage(returned, total, has_next, *, status='succeeded', consistent=True):
    known_total = type(total) is int and total >= 0
    if not consistent or (known_total and returned > total):
        state = 'inconsistent'
    elif status != 'succeeded' or has_next or (known_total and returned < total):
        state = 'partial'
    elif not known_total or has_next is None:
        state = 'unknown'
    else:
        state = 'complete'
    return {'status': state, 'returned_rows': returned,
            'reported_total': total if known_total else None,
            'has_next_page': has_next, 'complete_for_reported_query': state == 'complete'}


def audit(source, arguments):
    if source.get('semantic_type') != 'curated_target_disease_evidence_records':
        raise ValueError('실제로 받은 표적–질환 근거 자료를 선택해 주세요.')
    if source.get('status') not in ('succeeded', 'partial') or not isinstance(source.get('rows'), list):
        raise ValueError('반환된 근거 행과 원 조회 상태를 확인해 주세요.')
    scope = source.get('summary') or {}
    target = identifier(scope.get('target_id'), r'ENSG[0-9]{11}', '인간 표적')
    disease = identifier(scope.get('disease_id'), r'[A-Za-z][A-Za-z0-9]*_[0-9]+', '질환')
    for row in source['rows']:
        if not row.get('id') or (row.get('target') or {}).get('id') != target or (row.get('disease') or {}).get('id') != disease:
            raise ValueError('원 근거 ID·표적·질환과 조회 범위의 대응을 확인해 주세요.')
    selected = arguments['molecule_ids']
    if not isinstance(selected, list) or not all(isinstance(x, str) for x in selected) or not 1 <= len(selected) <= 20 or len(set(selected)) != len(selected):
        raise ValueError('중복 없는 약물 항목을 1–20개 선택해 주세요.')
    available = {(row.get('drug') or {}).get('id') for row in source.get('rows', [])}
    for value in selected:
        identifier(value, r'CHEMBL[0-9]+', '약물')
        if value not in available:
            raise ValueError('선택한 근거 자료에 실제로 등장하는 약물만 대조할 수 있습니다.')
    url = 'https://www.ebi.ac.uk/chembl/api/data/mechanism.json?' + urllib.parse.urlencode(
        {'molecule_chembl_id__in': ','.join(selected), 'limit': 1000})
    raw, receipt = fetch(url)
    body = json.loads(raw)
    mechanisms = body.get('mechanisms')
    if not isinstance(mechanisms, list):
        raise ValueError('ChEMBL 작용기전 응답 형식을 확인해야 합니다.')
    grouped = {key: [] for key in selected}
    unrequested = []
    for record in mechanisms:
        key = record.get('molecule_chembl_id')
        if key not in grouped:
            unrequested.append(record)
        else:
            grouped[key].append(record)
    page = body.get('page_meta') or {}
    source_scope = page_coverage(len(source['rows']), scope.get('total'),
        bool(scope['next_cursor']) if 'next_cursor' in scope else None,
        status=source['status'], consistent=(scope.get('returned', len(source['rows'])) == len(source['rows'])
            and len({r['id'] for r in source['rows']}) == len(source['rows'])))
    mechanism_scope = page_coverage(len(mechanisms), page.get('total_count'),
        bool(page['next']) if 'next' in page else None,
        consistent=not unrequested and page.get('offset', 0) == 0)
    coverage = {}
    for original in source['rows']:
        counts = coverage.setdefault(original.get('datasourceId') or 'unreported', Counter())
        counts['total'] += 1
        for field in ('directionOnTarget', 'directionOnTrait'):
            counts[field + ('_reported' if original.get(field) is not None else '_unreported')] += 1
    parents = {}
    for records in grouped.values():
        for record in records:
            parent = record.get('parent_molecule_chembl_id')
            if parent:
                item = parents.setdefault(parent, {'molecule_ids': set(), 'action_types': set()})
                item['molecule_ids'].add(record['molecule_chembl_id'])
                if record.get('action_type'):
                    item['action_types'].add(record['action_type'])
    rows = []
    for index, original in enumerate(source.get('rows', [])):
        drug = original.get('drug') or {}
        if drug.get('id') not in grouped:
            continue
        records = grouped[drug['id']]
        actions = list(dict.fromkeys(r.get('action_type') for r in records))
        context = ['약물 식별자 일치로 연결했습니다. 원 표적 ID·질환형·투여 조직의 대응은 별도로 확인합니다.']
        if 'STABILISER' in actions:
            context.append('안정화라는 작용 방식입니다. GoF 표기를 단백질 양을 늘리라는 지시로 바꾸지 않습니다.')
        if 'RNAI INHIBITOR' in actions:
            context.append('RNAi 억제 기전 기록입니다. 새 가이드의 효능·수식·전달을 검증한 결과가 아닙니다.')
        if original.get('datasourceId') == 'clinical_precedence':
            context.append('clinical precedence의 protect는 임상 개발 기전에서 부여한 방향입니다. 이 행의 임상 성공이나 승인 적응증 확인을 대신하지 않습니다.')
        if original.get('directionOnTarget') is None:
            context.append('표적 방향 미제공은 중립 또는 반대 근거가 아닙니다.')
        if original.get('trialWhyStopped') or original.get('trialStopReasonCategories'):
            context.append('연구 중단 사유를 원문대로 보존합니다. 중단 자체를 효능 실패 또는 성공으로 바꾸지 않습니다.')
        if page.get('next'):
            context.append('작용기전의 다음 페이지를 아직 조회하지 않았습니다. 이 약물의 전체 작용 목록이 아닐 수 있습니다.')
        if not source_scope['complete_for_reported_query']:
            context.append('원 표적–질환 근거는 전체 조회 완료로 확인되지 않았습니다. 이 자료에 받은 범위만 연결했습니다.')
        rows.append({'row_id': original['id'], 'source_row_index': index,
            'drug': drug, 'datasource_id': original.get('datasourceId'),
            'direction_on_target': original.get('directionOnTarget'),
            'direction_on_trait': original.get('directionOnTrait'),
            'action_types': actions, 'mechanisms': records,
            'mechanism_target_ids': sorted({r['target_chembl_id'] for r in records if r.get('target_chembl_id')}),
            'mechanism_target_correspondence': 'not_verified_by_molecule_id_join',
            'mechanism_records_complete': mechanism_scope['complete_for_reported_query'],
            'trial_stop': {'reason': original.get('trialWhyStopped'),
                           'categories': original.get('trialStopReasonCategories')},
            'source_evidence': original, 'interpretation_notes': context,
            'mechanism_status': 'reported_mechanism_found' if records else 'not_returned_not_negative'})
    pending = sorted((available - set(selected)) - {None})
    return {'status': 'succeeded' if source_scope['complete_for_reported_query'] and mechanism_scope['complete_for_reported_query'] else 'partial',
        'semantic_type': 'source_linked_intervention_direction_audit',
        'source': receipt, 'original_mechanism_response': body,
        'unrequested_records': unrequested,
        'explicit_parent_groups': [{'parent_molecule_id': k,
            'molecule_ids': sorted(v['molecule_ids']), 'action_types': sorted(v['action_types'])}
            for k, v in sorted(parents.items())],
        'source_evidence_receipt': source.get('source'),
        'source_evidence_status': source['status'],
        'source_evidence_canonical_sha256': hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'source_artifact_id': arguments['artifact_id'], 'rows': rows,
        'summary': {'selected_molecules': len(selected), 'evidence_rows': len(rows),
            'distinct_molecules_with_mechanism': sum(bool(x) for x in grouped.values()),
            'unselected_molecule_ids': pending, 'source_evidence_coverage': source.get('summary'),
            'source_query_coverage': source_scope, 'mechanism_query_coverage': mechanism_scope,
            'mechanism_next_page': page.get('next'),
            'direction_field_coverage': {k: dict(v) for k, v in sorted(coverage.items())},
            'unreported_direction_reason': 'not supplied; no missingness mechanism inferred',
            'distinct_explicit_parents': len(parents),
            'parent_unreported_mechanism_records': sum(not r.get('parent_molecule_chembl_id') for records in grouped.values() for r in records),
            'parent_action_counts': dict(Counter(a for v in parents.values() for a in v['action_types'])),
            'unrequested_mechanism_records': len(unrequested),
            'mechanism_action_counts': dict(Counter(a for records in grouped.values() for r in records if (a := r.get('action_type')))),
            'counts_are_not_independent_support': True},
        'rule_sources': ['https://platform-docs.opentargets.org/evidence#clinical-precedence',
                         'https://www.ebi.ac.uk/chembl/api/data/docs'],
        'limits': ['약물의 원 작용 방식과 데이터베이스 방향 표기를 대조합니다. 치료 방향·효능·안전성의 자동 판정은 아닙니다.',
            '원 약물·염 항목과 반복 임상 기록을 보존하며 독립 지지 개수로 합산하지 않습니다.',
            '선택한 근거 자료와 약물만 조회했습니다. 미선택 약물·다음 페이지와 기록이 없는 새 후보는 배제되지 않았습니다.',
            '단백질·전사체 표적의 동일성, 질환형·조직·변이·용량과 기능적 결과는 원전에서 이어 확인합니다.']}
