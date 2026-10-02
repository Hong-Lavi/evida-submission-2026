"""Source-specific target context; no pooled safety/efficacy score or ranking."""
import base64
import json
from pathlib import Path
import re

from .science import fetch


FIELDS = {
    'genetic_constraint': '''geneticConstraint{constraintType exp obs score oe oeLower oeUpper upperRank upperBin upperBin6}''',
    'essentiality': '''isEssential depMapEssentiality{tissueId tissueName screens{
        depmapId cellLineName diseaseCellLineId diseaseFromSource mutation geneEffect expression}}''',
    'safety_liabilities': '''safetyLiabilities{event eventId datasource url literature
        studies{description type name} effects{direction dosing}
        biosamples{cellLabel tissueId cellId tissueLabel cellFormat}}''',
    'baseline_expression': '''baselineExpression(page:$page){count rows{targetId targetFromSourceId
        datatypeId datasourceId unit min median max q1 q3 qualityControls specificity_score distribution_score
        celltypeBiosampleFromSource tissueBiosampleFromSource
        tissueBiosample{biosampleId biosampleName} tissueBiosampleParent{biosampleId biosampleName}
        celltypeBiosample{biosampleId biosampleName} celltypeBiosampleParent{biosampleId biosampleName}}}''',
}
PAGE_SIZE = 20
LIMITS = [
    '유전적 제약은 집단에서 관측한 변이 통계입니다. 조직별 부분 억제·양대립유전자 결손·치료 안전성을 같은 것으로 판단하지 않습니다.',
    'DepMap은 암 세포주에서의 유전자 교란과 세포 적합도입니다. isEssential=false는 모든 정상 조직에서 안전하다는 뜻이 아닙니다.',
    '안전성 기록이 없다는 것은 이 출처가 반환한 기록이 없다는 뜻입니다. 위험 없음이나 허가된 용법으로 바꾸지 않습니다.',
    '발현은 출처·세포/조직·단위·정량법마다 해석합니다. 단위가 다른 값을 합치거나 발현을 전달·표적 관여·효능으로 바꾸지 않습니다.',
    '이 자료는 질환–표적의 개입 방향·임상 조건·실험 근거와 함께 검토합니다. 결측·API 오류·미조회는 음성 결과가 아닙니다.',
]


def query_for(arguments):
    target = arguments.get('target_id')
    sections = arguments.get('sections')
    page = arguments.get('expression_page')
    if not isinstance(target,str) or not re.fullmatch(r'ENSG[0-9]{11}',target):
        raise ValueError('확인된 인간 Ensembl 표적 ID가 필요합니다.')
    if (not isinstance(sections,list) or not 1 <= len(sections) <= 4
            or any(not isinstance(s,str) or s not in FIELDS for s in sections)
            or len(set(sections)) != len(sections)):
        raise ValueError('서로 다른 표적 맥락 항목을 1–4개 선택해 주세요.')
    if type(page) is not int or not 0 <= page <= 10000:
        raise ValueError('발현 자료 페이지를 확인해 주세요.')
    paged = 'baseline_expression' in sections
    declaration = 'query($id:String!,$page:Pagination)' if paged else 'query($id:String!)'
    query = declaration + '{meta{dataVersion{year month iteration} apiVersion{x y z suffix}} target(ensemblId:$id){id approvedSymbol approvedName biotype ' + ' '.join(FIELDS[s] for s in sections) + '}}'
    variables = {'id':target}
    if paged: variables['page'] = {'index':page,'size':PAGE_SIZE}
    return query, variables


def interpret(body, arguments):
    """Flatten source rows with exact native paths; keep raw values and sections."""
    target = (body.get('data') or {}).get('target')
    rows, coverage = [], {}
    errors = body.get('errors') or []
    if target is not None and target.get('id') != arguments['target_id']:
        raise ValueError('반환 표적이 요청한 공식 식별자와 다릅니다.')
    field_names = {'genetic_constraint':'geneticConstraint', 'essentiality':'depMapEssentiality',
                   'safety_liabilities':'safetyLiabilities','baseline_expression':'baselineExpression'}
    for section in arguments['sections']:
        field = field_names[section]
        relevant_errors = [e for e in errors if not e.get('path') or e['path'][:2]==['target',field]
                           or (section=='essentiality' and e['path'][:2]==['target','isEssential'])
                           or e['path']==['target']]
        value = target.get(field) if target else None
        if target is None or value is None:
            coverage[section] = {'status':'source_error' if relevant_errors else 'not_returned',
                                 'returned_rows':0, 'errors':relevant_errors}
            # An independently returned essentiality flag still has its own value.
            if section=='essentiality' and target and 'isEssential' in target:
                rows.append({'context_type':'common_essential_flag', 'source_pointer':['data','target','isEssential'],
                             'value':target['isEssential']})
            continue
        start = len(rows)
        if section=='essentiality':
            rows.append({'context_type':'common_essential_flag','source_pointer':['data','target','isEssential'],
                         'value':target.get('isEssential')})
            for i,tissue in enumerate(value):
                for j,screen in enumerate(tissue.get('screens') or []):
                    rows.append({'context_type':'cancer_cell_dependency',
                        'source_pointer':['data','target',field,i,'screens',j],
                        'tissue_id':tissue.get('tissueId'),'tissue_name':tissue.get('tissueName'),'value':screen})
        elif section=='baseline_expression':
            records = value.get('rows')
            if records is None:
                coverage[section] = {'status':'not_returned','returned_rows':0,'errors':relevant_errors}
                continue
            rows.extend({'context_type':section,'source_pointer':['data','target',field,'rows',i],
                         'value':v} for i,v in enumerate(records))
        else:
            rows.extend({'context_type':section,'source_pointer':['data','target',field,i],
                         'value':v} for i,v in enumerate(value))
        coverage[section] = {'status':'source_error_with_rows' if relevant_errors else
                             'returned_rows' if len(rows)>start else 'returned_no_records',
                             'returned_rows':len(rows)-start,'errors':relevant_errors}
        if section=='baseline_expression':
            count = value.get('count')
            valid = type(count) is int and count >= 0
            coverage[section].update(total=count, page=arguments['expression_page'],page_size=PAGE_SIZE,
                has_more=(arguments['expression_page']*PAGE_SIZE+len(value['rows']) < count) if valid else None,
                complete_collection=valid and arguments['expression_page']==0 and len(value['rows'])==count and not relevant_errors)
    status = 'partial' if errors else 'succeeded' if target else 'input_missing'
    return {'status':status,'semantic_type':'source_conditioned_target_context',
        'target':{k:target.get(k) for k in ('id','approvedSymbol','approvedName','biotype')} if target else None,
        'rows':rows,'section_coverage':coverage,'source_version':(body.get('data') or {}).get('meta'),
        'summary':{'target_id':arguments['target_id'],'symbol':target.get('approvedSymbol') if target else None,
                   'requested_sections':arguments['sections'],'returned_rows':len(rows),
                   'expression_page':arguments['expression_page'],'automatic_rank_or_exclusion':False},
        'limits':LIMITS}


def retrieve(arguments, source_directory=None):
    query, variables = query_for(arguments)
    raw, receipt = fetch('https://api.platform.opentargets.org/api/v4/graphql',
                         {'query':query,'variables':variables})
    if source_directory is not None:
        directory = Path(source_directory)
        directory.mkdir(parents=True,exist_ok=True)
        (directory/'response.bin').write_bytes(raw)
        (directory/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False))
        (directory/'request.json').write_text(json.dumps({'query':query,'variables':variables},ensure_ascii=False))
    body = json.loads(raw)
    result = interpret(body,arguments)
    result.update(source=receipt,query=query,variables=variables,response=body,
                  original_response_base64=base64.b64encode(raw).decode())
    return result
