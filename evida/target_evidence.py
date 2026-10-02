"""Public target/disease evidence and assay records, without efficacy scoring."""
import json
import re
import urllib.parse

from .science import fetch


def identifier(value, pattern, label):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError(label + '의 확인된 식별자가 필요합니다.')
    return value


def page_number(value):
    if type(value) is not int or not 0 <= value <= 10000:
        raise ValueError('조회 페이지를 확인해 주세요.')
    return value


def graphql(query, variables):
    raw, source = fetch('https://api.platform.opentargets.org/api/v4/graphql',
                        {'query': query, 'variables': variables})
    body = json.loads(raw)
    return body, source


def disease_targets(arguments):
    disease = identifier(arguments['disease_id'], r'[A-Za-z][A-Za-z0-9]*_[0-9]+', '질환')
    page = page_number(arguments['page'])
    indirect = arguments['include_descendants']
    if type(indirect) is not bool:
        raise ValueError('하위 질환 포함 여부를 확인해 주세요.')
    query = '''query($d:String!,$p:Pagination,$indirect:Boolean){disease(efoId:$d){id name description
      associatedTargets(page:$p,enableIndirect:$indirect){count rows{score datasourceScores{id score}
      datatypeScores{id score} target{id approvedSymbol approvedName biotype tractability{label modality value}}}}}}'''
    variables = {'d': disease, 'p': {'index': page, 'size': 20}, 'indirect': indirect}
    body, receipt = graphql(query, variables)
    entity = (body.get('data') or {}).get('disease')
    data = (entity or {}).get('associatedTargets') or {}
    rows = data.get('rows', [])
    status = 'partial' if body.get('errors') else 'succeeded' if entity else 'input_missing'
    return {'status': status, 'semantic_type': 'curated_disease_target_associations',
            'source': receipt, 'query': query, 'variables': variables, 'response': body,
            'disease': {k: entity.get(k) for k in ('id', 'name', 'description')} if entity else None,
            'rows': rows, 'summary': {'returned': len(rows), 'total': data.get('count'), 'page': page,
                                    'include_descendants': indirect,
                                    'has_more': (page + 1) * 20 < data.get('count', 0)},
            'limits': ['통합 데이터베이스의 질환–표적 연관입니다. 인과 방향·치료 효능이나 성공 확률이 아닙니다.',
                       '점수의 출처별 구성을 확인하고 유전·약리·문헌 근거의 원전과 반대 관측을 대조해야 합니다.',
                       '현재 페이지 밖 후보는 미조회 상태이며 배제되지 않았습니다. 하위 질환 포함 여부에 따라 근거 범위가 달라집니다.']}


def target_disease_evidence(arguments):
    disease = identifier(arguments['disease_id'], r'[A-Za-z][A-Za-z0-9]*_[0-9]+', '질환')
    target = identifier(arguments['target_id'], r'ENSG[0-9]{11}', '인간 표적')
    cursor = arguments['cursor'] or None
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 20000):
        raise ValueError('근거 조회 커서를 확인해 주세요.')
    query = '''query($d:String!,$t:[String!]!,$cursor:String){disease(efoId:$d){id name
      evidences(ensemblIds:$t,enableIndirect:false,size:25,cursor:$cursor){count cursor rows{
      id datasourceId datatypeId score disease{id name} target{id approvedSymbol}
      directionOnTarget directionOnTrait targetModulation literature pubMedCentralIds
      studyId studyOverview studySampleSize biologicalModelId biologicalModelGeneticBackground
      diseaseFromSource cohortDescription confidence qualityControls warningMessage
      drug{id name} clinicalStage trialWhyStopped trialStopReasonCategories
      releaseVersion releaseDate evidenceDate publicationYear}}}}'''
    variables = {'d': disease, 't': [target], 'cursor': cursor}
    body, receipt = graphql(query, variables)
    entity = (body.get('data') or {}).get('disease')
    data = (entity or {}).get('evidences') or {}
    rows = data.get('rows', [])
    return {'status': 'partial' if body.get('errors') else 'succeeded' if entity else 'input_missing',
            'semantic_type': 'curated_target_disease_evidence_records', 'source': receipt,
            'query': query, 'variables': variables, 'response': body, 'rows': rows,
            'summary': {'target_id': target, 'disease_id': disease, 'returned': len(rows),
                        'total': data.get('count'), 'next_cursor': data.get('cursor'), 'direct_disease_only': True},
            'limits': ['개별 데이터베이스 근거 기록이며 원 논문을 새로 읽거나 독립 검증한 결과가 아닙니다.',
                       '작용 방향·임상 중단 사유·종/모형·코호트가 미제공이면 미확인으로 유지합니다.',
                       '유전적 연관이나 표적 결합을 특정 약물·siRNA의 효능으로 바꾸지 않습니다. PMID/PMC 원전을 이어 확인합니다.']}


def chembl_search(arguments):
    entity, query = arguments['entity'], arguments['query'].strip()
    if entity not in ('target', 'molecule') or not 1 <= len(query) <= 200:
        raise ValueError('화합물 또는 표적의 공개 이름을 입력해 주세요.')
    page = page_number(arguments['page'])
    url = 'https://www.ebi.ac.uk/chembl/api/data/' + entity + '/search.json?' + urllib.parse.urlencode(
        {'q': query, 'limit': 20, 'offset': page * 20})
    raw, receipt = fetch(url)
    body = json.loads(raw)
    rows = body.get('targets' if entity == 'target' else 'molecules', [])
    metadata = body.get('page_meta', {})
    return {'status': 'succeeded', 'semantic_type': 'chembl_identifier_candidates', 'source': receipt,
            'response': body, 'rows': rows,
            'summary': {'entity': entity, 'query': query, 'returned': len(rows),
                        'total': metadata.get('total_count'), 'page': page, 'has_more': bool(metadata.get('next'))},
            'limits': ['이름 검색 후보입니다. 표적의 종·복합체 유형, 화합물의 염/모체·입체화학을 확인한 뒤 선택합니다.',
                       '검색 순서나 이름 일치는 효능·선택성의 근거가 아닙니다.']}


def bioactivities(arguments):
    target, molecule = arguments['target_chembl_id'], arguments['molecule_chembl_id']
    if not target and not molecule:
        raise ValueError('확인한 ChEMBL 표적 또는 화합물 ID가 필요합니다.')
    filters = {'limit': 50, 'offset': page_number(arguments['page']) * 50}
    for key, value in [('target_chembl_id', target), ('molecule_chembl_id', molecule)]:
        if value:
            filters[key] = identifier(value, r'CHEMBL[0-9]+', 'ChEMBL')
    raw, receipt = fetch('https://www.ebi.ac.uk/chembl/api/data/activity.json?' + urllib.parse.urlencode(filters))
    body = json.loads(raw)
    rows = body.get('activities', [])
    # Fetch the actual assay metadata in one batch; keep the unaltered API rows.
    assay_ids = sorted({r['assay_chembl_id'] for r in rows if r.get('assay_chembl_id')})
    assay_response, assay_source, assay_error = None, None, None
    if assay_ids:
        try:
            params = {'assay_chembl_id__in': ','.join(assay_ids), 'limit': len(assay_ids)}
            raw_assays, assay_source = fetch('https://www.ebi.ac.uk/chembl/api/data/assay.json?' + urllib.parse.urlencode(params))
            assay_response = json.loads(raw_assays)
        except Exception as exc:
            assay_error = str(exc)[:500]
    metadata = body.get('page_meta', {})
    assays = {a['assay_chembl_id']: a for a in (assay_response or {}).get('assays', [])}
    unresolved = [aid for aid in assay_ids if aid not in assays]
    enriched_rows = [{**row, 'assay_context': assays.get(row.get('assay_chembl_id'))} for row in rows]
    return {'status': 'partial' if assay_error or unresolved else 'succeeded', 'semantic_type': 'published_bioactivity_records',
            'source': receipt, 'filters': filters, 'response': body, 'rows': enriched_rows,
            'assay_source': assay_source, 'assay_response': assay_response, 'assay_access_gap': assay_error,
            'assay_unresolved_ids': unresolved,
            'summary': {'returned': len(rows), 'total': metadata.get('total_count'),
                        'page': arguments['page'], 'has_more': bool(metadata.get('next')),
                        'assay_metadata_returned': len((assay_response or {}).get('assays', [])),
                        'selection_rule': 'All returned records retained, including nulls, inequalities, comments and data-validity flags'},
            'limits': ['원 기록의 standard_type·단위·관계기호·assay·종·표적 유형·유효성 표시를 함께 해석합니다.',
                       'Kd, Ki, IC50 및 세포 효능을 섞어 순위를 만들지 않습니다. 동등한 실험 조건이 없는 활성값 비율은 선택성 증거가 아닙니다.',
                       '검색되지 않은 표적에 대한 활성이 0이라는 뜻이 아니며 현재 페이지의 문헌은 전체 선택성 패널이 아닙니다.',
                       '보고된 문헌 측정값이며 이 앱에서 새로 실험한 결과가 아닙니다.']}
