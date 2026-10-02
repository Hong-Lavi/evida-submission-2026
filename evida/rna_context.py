"""Source/version-aware tissue context for existing sequence comparisons.

No ratio of tissue medians is computed. Original source rows and every selected
reference remain accessible, including zero, mismatch and absent quantification.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlencode

from .science import fetch

GTEX = 'https://gtexportal.org/api/v2/'


def public_json(url, directory, label):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    raw, receipt = fetch(url)
    # Persist the exact response even if subsequent validation fails.
    name = label + '-' + hashlib.sha256(url.encode()).hexdigest()[:16]
    (directory / (name + '.json')).write_bytes(raw)
    (directory / (name + '-receipt.json')).write_text(json.dumps(receipt, ensure_ascii=False))
    return json.loads(raw), receipt


def paged(route, query, directory):
    rows, sources = [], []
    page, expected_total = 0, None
    while True:
        value, receipt = public_json(GTEX + route + '?' + urlencode({**query, 'page': page,
            'itemsPerPage': 1000}), directory, route.replace('/', '-'))
        sources.append({'response': value, 'receipt': receipt})
        info = value['paging_info']
        if (info['page'] != page or type(info['totalNumberOfItems']) is not int
                or info['totalNumberOfItems'] < 0 or info['totalNumberOfItems'] > 10000):
            raise ValueError('공개 자료의 페이지/크기를 확인해야 합니다. 받은 원응답은 실행 기록에 보존했습니다.')
        if expected_total is not None and expected_total != info['totalNumberOfItems']:
            raise ValueError('조회 중 공개 자료의 전체 행 수가 바뀌었습니다. 원응답을 확인해 주세요.')
        expected_total = info['totalNumberOfItems']
        rows.extend(value['data'])
        page += 1
        if page >= info['numberOfPages']:
            break
        if page >= 10 or not value['data']:
            raise ValueError('공개 자료 페이지를 완전히 받지 못했습니다. 누락을 발현0으로 처리하지 않습니다.')
    if len(rows) != expected_total:
        raise ValueError('공개 자료의 전체 행 수와 받은 행 수가 다릅니다.')
    return rows, sources


def join_tissue(panel, expression_rows, dataset, tissue, source_gene):
    if panel.get('semantic_type') != 'selected_transcript_exact_complementarity_panel':
        raise ValueError('먼저 후보별 전사체 대응 결과를 선택해 주세요.')
    indexed = {}
    for row in expression_rows:
        if (row.get('datasetId') != dataset or row.get('tissueSiteDetailId') != tissue
                or row.get('gencodeId') != source_gene or row.get('unit') != 'TPM'):
            raise ValueError('조직 발현 원행의 데이터셋·조직·유전자·단위가 요청과 다릅니다.')
        tid = row['transcriptId']
        if tid in indexed or not re.fullmatch(r'ENST\d+\.\d+', tid):
            raise ValueError('발현 전사체 버전이 없거나 중복입니다.')
        median = row.get('median')
        if type(median) not in (int, float) or not math.isfinite(median) or median < 0:
            raise ValueError('발현 정량값의 형식을 확인해야 합니다. 결측을0으로 바꾸지 않습니다.')
        indexed[tid] = row
    contexts = {}
    for ref in panel['reference_panel']:
        accession = f"{ref['transcript_id']}.{ref['version']}"
        exact = indexed.get(accession)
        others = [r for k, r in indexed.items() if k.split('.')[0] == ref['transcript_id']]
        if exact is not None:
            status = 'version_matched_zero' if exact['median'] == 0 else 'version_matched_reported'
            text = ('이 버전의 조직 중앙 TPM이0으로 보고됨. 모든 표본/세포에서 부재한다는 뜻은 아님.'
                    if exact['median'] == 0 else '같은 전사체 버전의 조직 중앙 TPM. 특정 세포·시료의 측정은 아님.')
        elif others:
            status, text = 'version_mismatch', '같은 ID의 다른 버전만 정량됨. 이 서열에 정량값을 옮기지 않음.'
        else:
            status, text = 'not_in_returned_quantification', '조회한 정량 자료에 이 전사체가 없음. 발현0이 아님.'
        contexts[ref['artifact_id']] = {'reference_artifact_id': ref['artifact_id'],
            'transcript_accession': accession, 'status': status,
            'median_tpm': exact['median'] if exact is not None else None,
            'source_rows': [exact] if exact is not None else others,
            'interpretation': text,
            'cross_release_sequence_identity': 'not_independently_reconstructed'}
    rows = [{**row, 'tissue_context': contexts[row['reference_artifact_id']]} for row in panel['rows']]
    return {'status': 'succeeded', 'semantic_type': 'tissue_context_on_exact_sequence_panel',
        'reference': panel['reference'], 'reference_panel': panel['reference_panel'],
        'rows': rows, 'transcript_contexts': list(contexts.values()),
        'source_transcripts_outside_selected_panel': [r for k, r in indexed.items()
            if k not in {v['transcript_accession'] for v in contexts.values()}],
        'summary': {'dataset': dataset, 'tissue': tissue, 'gene_id': source_gene,
            'selected_candidates': panel['summary']['selected_candidates'],
            'selected_references': len(contexts), 'comparison_rows': len(rows),
            'transcript_status_counts': dict(Counter(v['status'] for v in contexts.values())),
            'sample_site_fraction_calculated': False},
        'limits': ['GTEx 조직 전사체 중앙 TPM입니다. 질환 세포·환자·개별 표본의 발현이나 단백질 분비 기여가 아닙니다.',
            '중앙값들을 합치거나 나눠 후보가 억제하는 환자/표본 비율을 만들지 않습니다.',
            '같은 ID의 다른 버전·미반환·정량0을 구분합니다. 버전 일치도 서로 다른 주석의 서열 동일성 재구성을 대신하지 않습니다.',
            '서열 일치·조직 정량은 같은 참조에 연결된 조건입니다. 독립 효능 근거로 중복 가산하지 않습니다.']}


def tissue_context(panel, args, directory):
    ref = panel.get('reference', {})
    gene = (ref.get('gene_id') or '').split('.')[0]
    if (ref.get('organism') != 'homo_sapiens' or ref.get('assembly') != 'GRCh38'
            or not re.fullmatch(r'ENSG\d+', gene)):
        raise ValueError('이 GTEx 연결에는 인간 GRCh38 유전자 참조가 필요합니다.')
    dataset, tissue = args['dataset'], args['tissue']
    if dataset not in ('gtex_v8', 'gtex_v10') or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,100}', tissue):
        raise ValueError('지원하는 GTEx 데이터셋과 조직 식별자를 선택해 주세요.')
    metadata, receipt = public_json(GTEX + 'metadata/dataset?' + urlencode({'datasetId': dataset}), directory, 'dataset')
    if not isinstance(metadata, list):
        raise ValueError('GTEx 데이터셋 메타데이터 응답 형식을 확인해야 합니다.')
    data = metadata
    matching = [r for r in data if r['datasetId'] == dataset]
    if len(matching) != 1:
        raise ValueError('GTEx 데이터셋의 참조 주석을 하나로 확인할 수 없습니다.')
    dataset_meta = matching[0]
    if dataset_meta['genomeBuild'] != 'GRCh38/hg38':
        raise ValueError('GTEx와 선택한 참조의 genome build가 다릅니다.')
    genes, gene_sources = paged('reference/gene', {'geneId': gene,
        'gencodeVersion': dataset_meta['gencodeVersion'], 'genomeBuild': dataset_meta['genomeBuild']}, directory)
    hits = [g for g in genes if g['gencodeId'].split('.')[0] == gene]
    if len(hits) != 1:
        raise ValueError('해당 데이터셋의 유전자 버전 대응이 없거나 모호합니다.')
    source_gene = hits[0]['gencodeId']
    records, sources = paged('expression/medianTranscriptExpression', {'gencodeId': source_gene,
        'tissueSiteDetailId': tissue, 'datasetId': dataset}, directory)
    result = join_tissue(panel, records, dataset, tissue, source_gene)
    result.update(dataset_metadata=dataset_meta, source_gene=hits[0],
        original_responses=[{'response': metadata, 'receipt': receipt}, *gene_sources, *sources],
        sources=[receipt, *[s['receipt'] for s in gene_sources + sources]])
    return result
