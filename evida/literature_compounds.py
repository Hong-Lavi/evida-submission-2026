"""Resolve publicly mentioned compound names; preserve every source and unresolved name."""
import hashlib,json,re,urllib.parse
from .science import fetch


def collect(arguments,sources):
    names=arguments['names']
    if not names or len(names)>20 or len(names)!=len(set(names)) or not arguments['reason'].strip():
        raise ValueError('공개 원문에서 확인한 이름과 회수 이유가 필요합니다.')
    evidence={};bindings={}
    for name in names:
        if not isinstance(name,str) or not 1<=len(name.strip())<=300:raise ValueError('공개 화합물 이름을 확인해 주세요.')
        mentions=[];bound=[]
        for source in sources:
            if source['kind'] not in ('article','literature','source_candidates'):raise ValueError('실제 공개 문헌 조회/원문 또는 원문에 연결한 후보만 사용할 수 있습니다.')
            value=source['value']
            if source['kind']=='source_candidates':
                for row in value.get('rows',[]):
                    identity=row['identity']
                    names_in_record={row['name'].strip().casefold()}
                    if identity.get('lookup_name'):
                        names_in_record.add(identity['lookup_name'].strip().casefold())
                    if name.strip().casefold() not in names_in_record:continue
                    mention=row['mention']
                    mentions.append({'artifact_id':mention['artifact_id'],'sha256':mention['source_sha256'],
                        'locator':mention['locator'],'row_id':mention.get('row_id'),
                        'candidate_record_artifact_id':source['artifact_id'],'source_candidate_id':row['candidate_id'],
                        'source_name':row['name'],'lookup_anchor':identity.get('lookup_anchor'),
                        'meaning':'source_membership_and_name_mapping_assertions_not_efficacy_confirmation'})
                    bound.append({'lookup_name':identity['lookup_name'],'modality':row['modality'],
                        'source_candidate_id':row['candidate_id'],'identity':identity})
                continue
            for i,row in enumerate(value.get('rows',[])):
                text=json.dumps(row,ensure_ascii=False)
                if re.search(r'(?<![\w-])'+re.escape(name.strip())+r'(?![\w-])',text,re.I):
                    mentions.append({'artifact_id':source['artifact_id'],'sha256':source['sha256'],'locator':'rows/'+str(i),'row_id':row.get('row_id'),'meaning':'name_mention_only_not_efficacy_or_target_confirmation'})
        if not mentions:raise ValueError('지정한 공개 문헌의 원행에서 확인되지 않은 이름: '+name)
        evidence[name]=mentions;bindings[name]=bound
    rows={};lookups=[]
    for name in names:
        bound=bindings[name]
        lookup_names=sorted({b['lookup_name'] for b in bound if b['lookup_name']})
        blocked=None
        if any(b['modality'] in ('sirna','other') for b in bound):
            blocked='이 치료 방식은 저분자 구조 계산 경로와 구분합니다. 원문 후보는 보존하고 해당 방식의 자료·서열·전달 조건을 검토하세요.'
        elif bound and not lookup_names:
            blocked='원문 후보의 화학 식별이 남아 있습니다. 논문 번호가 아닌 정확한 화학명·구조 근거를 확인하세요.'
        elif bound and len(lookup_names)!=1:
            blocked='같은 이름에 여러 원문 식별 대응이 있습니다. 원문별 후보를 나눠 조회하세요.'
        elif not bound and re.fullmatch(r'[A-Za-z]{1,3}\d{1,3}(?:-\d{1,3})?',name.strip()):
            blocked='짧은 물질 코드는 논문 안의 이름일 수 있습니다. record_source_candidates에서 공개 이름인지 또는 원문 화학명과의 대응을 먼저 기록하세요.'
        query=lookup_names[0] if len(lookup_names)==1 else name.strip()
        namespace=json.dumps(sorted((m['artifact_id'],m.get('sha256'),m['locator']) for m in evidence[name]),ensure_ascii=False)
        unresolved='unresolved:'+hashlib.sha256((namespace+'|'+name.casefold()).encode()).hexdigest()[:24]
        source_ids=[b['source_candidate_id'] for b in bound]
        modalities=sorted({b['modality'] for b in bound})
        if blocked:
            rows[unresolved]={'candidate_id':unresolved,'name':name,'smiles':None,'structure_status':'unavailable',
                'identity_status':'source_identity_check_needed','lookup_names':[], 'source_candidate_ids':source_ids,
                'modalities':modalities,'name_mentions':evidence[name],'activities':[],
                'review_status':'unreviewed','target_activity_verified':False,'next_identity_check':blocked}
            lookups.append({'name':name,'lookup_name':None,'attempted':False,'reason':blocked})
            continue
        url='https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/'+urllib.parse.quote(query,safe='')+'/property/SMILES,ConnectivitySMILES,InChIKey,IUPACName,Title/JSON'
        try:
            raw,receipt=fetch(url);value=json.loads(raw);lookups.append({'name':name,'lookup_name':query,'attempted':True,'source':receipt,'response':value,'error':None})
            properties=value.get('PropertyTable',{}).get('Properties',[])
            if not properties:raise ValueError('공식 구조 응답에 화합물 행이 없습니다.')
            for prop in properties:
                cid='PUBCHEM:'+str(prop['CID']);smiles=prop.get('SMILES')
                row=rows.setdefault(cid,{'candidate_id':cid,'name':prop.get('Title') or name,'smiles':smiles,
                    'structure_status':'available' if smiles else 'unavailable','molecule_type':'public_compound_identity',
                    'structure':prop,'lookup_names':[],'name_mentions':[],'structure_sources':[],
                    'source_candidate_ids':[],'modalities':[],
                    'identity_status':'database_name_match_not_source_sample_validation',
                    'activities':[],'review_status':'unreviewed','target_activity_verified':False})
                row['lookup_names'].append(query);row['name_mentions'].extend(evidence[name]);row['structure_sources'].append(receipt)
                row['source_candidate_ids']=sorted(set(row['source_candidate_ids']+source_ids))
                row['modalities']=sorted(set(row['modalities']+modalities))
        except Exception as exc:
            lookups.append({'name':name,'source':{'url':url},'response':None,'error':str(exc)[:400]})
            cid=unresolved
            rows[cid]={'candidate_id':cid,'name':name,'smiles':None,'structure_status':'unavailable','lookup_names':[name],
                'name_mentions':evidence[name],'source_candidate_ids':source_ids,'modalities':modalities,
                'identity_status':'lookup_not_resolved','activities':[],'review_status':'unreviewed','target_activity_verified':False}
    return {'status':'partial' if any(r['structure_status']!='available' for r in rows.values()) else 'succeeded',
        'semantic_type':'public_literature_names_and_pubchem_identity_not_activity_validation',
        'target_context':arguments['target_context'],'selection_reason':arguments['reason'],'rows':list(rows.values()),
        'lookups':lookups,'summary':{'requested_names':len(names),'candidates':len(rows),'unresolved':sum(r['structure_status']!='available' for r in rows.values()),
            'rule':'All requested public-source names and returned CIDs retained; not an exhaustive target screen or automatic substitute for failed ChEMBL assays.'},
        'limits':['공개 문헌의 이름 등장과 PubChem 이름→구조 대응을 확인한 목록입니다. 문맥상 표적·작용 방향·종·실험 조건은 별도 검토해야 합니다.',
            'ChEMBL 활성 서비스의 실패를 이 조회 성공으로 대체하지 않습니다. 실제 표적 결합·안정화·선택성 측정의 조회 공백은 남습니다.',
            'SMILES는 입체/동위원소 정보를 포함한 반환값 그대로이며 염/모체·입체화학·서로 다른 시료의 동일성을 자동 확정하지 않습니다.']}
