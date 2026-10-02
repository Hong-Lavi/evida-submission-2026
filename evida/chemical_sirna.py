"""Conditional retrieval from a frozen public source, without an efficacy model."""
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re

MATCH_FIELDS = ('patent_ID', 'Target_Gene', 'Accession_number', 'Antisense_seqence',
                'Sense_seqence', 'Cell_Type', 'Concentration', 'Time_of_administration')
CHEM_FIELDS = ('Modification_Types_Antisense_strand', 'Modification_Types_Sense_strand')
REQUIRED = (*MATCH_FIELDS, *CHEM_FIELDS, 'ID', 'Inhibition', 'SD')


def retrieve(arguments, resource=None):
    gene = arguments['gene'].strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,39}', gene):
        raise ValueError('표적 유전자 이름을 입력하세요. 이 도구는 서열·질환 검색이 아닙니다.')
    if resource is None:
        resource = json.loads((Path(__file__).parents[1] / 'configs/rna-resources.json').read_text())['chemical_evidence']
    raw = Path(resource['path']).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != resource['sha256']:
        raise ValueError('수식 원자료가 검토한 고정판과 다릅니다.')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), delimiter='\t')
    if not reader.fieldnames or any(reader.fieldnames.count(k) != 1 for k in REQUIRED):
        raise ValueError('원 수식 자료의 열 대응을 확인해야 합니다.')
    columns = reader.fieldnames
    targets, rows, groups = Counter(), [], defaultdict(list)
    all_rows = 0
    for ordinal, row in enumerate(reader, 1):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f'원자료 {ordinal}행의 열 너비가 다릅니다. 원문을 보존하고 검토하세요.')
        targets[row['Target_Gene']] += 1
        all_rows += 1
        if row['Target_Gene'].casefold() != gene.casefold():
            continue
        item = {'row_id': f'{digest[:12]}:{ordinal}', 'source_record_1_based_after_header': ordinal,
                'raw': row, 'reported_target': row['Target_Gene'], 'reported_id': row['ID'],
                'condition_group_id': None, 'source_url': resource['url']}
        rows.append(item)
        if all(row[k] for k in MATCH_FIELDS):
            groups[tuple(row[k] for k in MATCH_FIELDS)].append(item)
    pairs = []
    for identity, members in groups.items():
        if len({tuple(m['raw'][k] for k in CHEM_FIELDS) for m in members}) < 2:
            continue
        group_id = 'recorded-' + hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:16]
        for member in members:
            member['condition_group_id'] = group_id
        pairs.append({'id': group_id, 'recorded_conditions': dict(zip(MATCH_FIELDS, identity)),
                      'row_ids': [m['row_id'] for m in members],
                      'meaning': '같은 기록 조건; delivery/control/experiment identity may differ. No chemical effect estimate.'})
    return {'status': 'succeeded', 'semantic_type': 'source_reported_chemical_assay_rows',
            'context': '원 표적·양 가닥·화학 표기·세포/동물 구분·농도 단위·시간을 보존한 조회이며 새 후보의 예측이 아닙니다.',
            'sources': [{'url': resource['url'], 'sha256': digest,
                         'retrieved_at': resource.get('retrieved_at'), 'source': 'CMsiRNAdb original TSV'}],
            'query': {'gene': gene, 'matching': 'case-insensitive exact gene label; no alias or cross-target expansion'},
            'columns': columns, 'rows': rows, 'condition_groups': pairs,
            'summary': {'source_rows': all_rows, 'matching_rows': len(rows), 'requested_gene': gene,
                        'available_target_counts': dict(sorted(targets.items())),
                        'same_recorded_conditions_different_chemistry_groups': len(pairs),
                        'coverage': 'Only this frozen database; zero rows is not biological absence.'},
            'limits': ['문헌·특허에서 수집한 원값입니다. 이 후보의 효능 예측이나 새 실험 결과가 아닙니다.',
                       '표적·두 가닥·세포/동물·농도 단위·시간·전달·대조가 다른 결과를 하나의 점수로 합치지 않습니다.',
                       '같은 기록 조건의 묶음에도 전달·대조·실험 구분이 빠져 있을 수 있습니다. 인과적 수식 효과로 해석하지 않습니다.',
                       '원 SD·단위·화학 표기·결측·중복을 변환하지 않았습니다. 표기 해석과 전사체는 원전을 확인해야 합니다.',
                       '다른 표적의 원행은 요청한 표적의 수식 설계 검증을 대신하지 않습니다.']}
