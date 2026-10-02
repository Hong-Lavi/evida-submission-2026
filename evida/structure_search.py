"""Public structure identifiers with explicit search scope; no automatic site selection."""
import json,re
from .science import fetch

def search(arguments):
    accession=arguments['uniprot_id'].strip()
    if not re.fullmatch(r'[A-Z0-9]{6,10}(?:-[0-9]+)?',accession):raise ValueError('확인한 UniProt accession이 필요합니다.')
    page=arguments['page']
    if type(page) is not int or page<0:raise ValueError('페이지는 0 이상이어야 합니다.')
    query={'query':{'type':'terminal','service':'text','parameters':{'attribute':'rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession','operator':'exact_match','value':accession}},
        'return_type':'entry','request_options':{'paginate':{'start':page*20,'rows':20},'results_content_type':['experimental']}}
    ligand=arguments.get('ligand_name','').strip()
    if len(ligand)>120:raise ValueError('공개 리간드 이름을 확인해 주세요.')
    if ligand:query['query']={'type':'group','logical_operator':'and','nodes':[query['query'],{'type':'terminal','service':'full_text','parameters':{'value':ligand}}]}
    raw,receipt=fetch('https://search.rcsb.org/rcsbsearch/v2/query',query)
    body=json.loads(raw) if raw.strip() else {};rows=body.get('result_set',[])
    return {'status':'succeeded','semantic_type':'experimental_structure_identifier_candidates','source':receipt,'query':query,'response':body,'rows':rows,
        'summary':{'uniprot_id':accession,'returned':len(rows),'total':body.get('total_count',0),'page':page,'has_more':(page+1)*20<body.get('total_count',0)},
        'limits':['UniProt 참조가 연결된 실험 구조 목록입니다. 변이·절단·종·조립체·부위·결합 성분과 측정 조건은 실제 구조를 가져와 확인해야 합니다.',
                  '검색 점수/순서는 도킹에 쓸 구조의 품질·적합성·후보 효능 순위가 아닙니다.']}
