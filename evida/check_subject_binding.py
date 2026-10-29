"""Exact candidate/condition record binding, never biological sample equivalence."""
import copy
import hashlib
import json
import re

MAX_REFS = 12
MAX_VALUE_BYTES = 24 * 1024
ROLES = ('candidate', 'comparator', 'condition')
REF = {'type':'object','properties':{'role':{'type':'string','enum':list(ROLES)},
       'artifact_id':{'type':'string','minLength':1,'maxLength':128},
       'json_pointer':{'type':'string','maxLength':100}},
       'required':['role','artifact_id','json_pointer'],'additionalProperties':False}
REFS = {'type':'array','items':REF,'maxItems':MAX_REFS,
        'description':'Optional exact candidate/comparator/condition records. Use a canonical single /rows/N; condition may use /reference, /protocol or /assay_context. At least one candidate when declaring a check. Server preserves source and row hashes; this does not establish biological or assay equivalence.'}
CANDIDATE_KINDS = frozenset('''analogue_proposal compound_candidates literature_compounds binding_measurements
source_candidates benchmark_compound_pool rdkit admet bioactivities rna_candidate_generation
rna_candidate_selection rna_sequence_evaluation rna_author_full rna_author_mod rna_activity_score'''.split())
MEANING = 'Exact preserved records only; matching records do not verify biological material, assay equivalence, measurement validity or efficacy.'


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def validate_refs(refs, expected=False):
    import jsonschema
    try:
        jsonschema.validate(refs,REFS)
    except jsonschema.ValidationError as exc:
        raise ValueError("대상 원행 참조 형식이 다릅니다: " + exc.message[:300]) from None
    keys=[(r['role'],r['artifact_id'],r['json_pointer']) for r in refs]
    if len(keys)!=len(set(keys)):
        raise ValueError('같은 대상·역할의 원행 참조가 중복됐습니다.')
    if expected and not any(r['role']=='candidate' for r in refs):
        raise ValueError('대상 연결에는 하나 이상의 후보 원행이 필요합니다.')
    for ref in refs:
        path=ref['json_pointer']
        row=bool(re.fullmatch(r'/rows/(0|[1-9][0-9]{0,6})',path))
        context=ref['role']=='condition' and path in ('/reference','/protocol','/assay_context')
        if not row and not context:
            raise ValueError('단일 /rows/N 원행 또는 조건의 /reference,/protocol,/assay_context만 선택해 주세요.')


def bind_refs(db,wid,refs,expected=False):
    validate_refs(refs,expected)
    snapshots=[]
    for ref in refs:
        row=db.execute('SELECT * FROM artifacts WHERE workspace=? AND id=?',(wid,ref['artifact_id'])).fetchone()
        if row is None or row['media_type']!='application/json':
            raise ValueError('현재 연구에 보존된 JSON 후보·조건 자료를 선택해 주세요.')
        snapshots.append(bound_record(row,ref))
    return snapshots


def bound_record(row,ref):
    from .measurement_report import SOURCE_KINDS
    allowed=CANDIDATE_KINDS if ref['role'] in ('candidate','comparator') else SOURCE_KINDS | CANDIDATE_KINDS
    if row['kind'] not in allowed:
        raise ValueError('이 역할의 후보·조건 원자료 종류가 아닙니다.')
    if hashlib.sha256(row['content']).hexdigest()!=row['sha256']:
        raise ValueError('대상 원자료의 SHA가 다릅니다.')
    value=json.loads(row['content']);path=ref['json_pointer']
    if path.startswith('/rows/'):
        index=int(path.split('/')[-1]);rows=value.get('rows')
        if not isinstance(rows,list) or index>=len(rows):
            raise ValueError('대상 원행의 범위를 확인해 주세요.')
        selected=rows[index]
    else:selected=value.get(path[1:])
    if not isinstance(selected,dict) or not selected or len(encoded(selected))>MAX_VALUE_BYTES:
        raise ValueError('대상은 비어 있지 않은 24 KiB 이내 단일 원행·조건 객체여야 합니다.')
    context={k:copy.deepcopy(value[k]) for k in ('reference','protocol','assay_context','target_context') if k in value}
    meta=json.loads(row['meta'])
    source_context={k:copy.deepcopy(meta[k]) for k in ('assay_context','measurement_endpoint','source_mode','dataset','task') if k in meta}
    if len(encoded(context))+len(encoded(source_context))>MAX_VALUE_BYTES:
        raise ValueError('대상의 보존 조건이 24 KiB 범위를 넘습니다. 더 작은 명시 조건 자료를 선택해 주세요.')
    display={'label':str(selected.get('name') or selected.get('candidate_id') or selected.get('id') or row['title'])[:400]}
    for key in ('smiles','guide_5to3','chemistry','transcript_id','version'):
        if key in selected:display[key]=copy.deepcopy(selected[key])
    return {**ref,'artifact_sha256':row['sha256'],'artifact_kind':row['kind'],'artifact_title':row['title'],
        'row_sha256':digest(selected),'snapshot':copy.deepcopy(selected),'context':context,'source_context':source_context,
        'display':display,'biological_identity_verified':False}


def publish(store,db,wid,decision_id,proposal):
    """Called under the actual publication transaction, including legacy publishers."""
    checks=[c for c in proposal.get('research_loop',{}).get('next_checks',[]) if 'subject_refs' in c]
    if not checks:return None
    from .store import dump,uid,now
    decision=db.execute('SELECT content,sha256 FROM artifacts WHERE workspace=? AND id=?',(wid,decision_id)).fetchone()
    if decision is None or hashlib.sha256(decision['content']).hexdigest()!=decision['sha256'] or json.loads(decision['content'])!=proposal:
        raise ValueError('원 판단과 대상 연결의 결속을 확인해 주세요.')
    value={'schema_version':'1','decision_id':decision_id,'decision_sha256':decision['sha256'],
           'checks':[{'check_id':c['id'],'check_sha256':digest(c),'declaration_origin':'authored_check_declaration_not_researcher_approval','subject_refs':copy.deepcopy(c['subject_refs']),
                      'subjects':bind_refs(db,wid,c['subject_refs'],expected=True)} for c in checks],
           'meaning':MEANING,'scientific_validation':False}
    existing=find(db,wid,decision_id)
    if existing:
        if existing['value']!=value:raise ValueError('같은 판단의 보존 대상 결속이 다릅니다.')
        return existing['artifact_id']
    aid=uid('art');content=dump(value).encode();meta={'decision_id':decision_id,'server_generated':True,'scientific_validation':False}
    db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)',(aid,wid,'다음 확인의 원 대상 기록','check_subject_binding',
        hashlib.sha256(content).hexdigest(),'application/json',now(),dump(meta),content))
    store.event(db,wid,'artifact_added',{'artifact_id':aid,'title':'다음 확인의 원 대상 기록','kind':'check_subject_binding'})
    return aid


def find(db,wid,decision_id):
    found=[]
    for row in db.execute("SELECT id,sha256,content FROM artifacts WHERE workspace=? AND kind='check_subject_binding'",(wid,)):
        value=json.loads(row['content'])
        if value.get('decision_id')!=decision_id:continue
        if hashlib.sha256(row['content']).hexdigest()!=row['sha256']:raise ValueError('보존 대상 연결의 해시가 다릅니다.')
        found.append({'artifact_id':row['id'],'sha256':row['sha256'],'value':value})
    if len(found)>1:raise ValueError('원 판단의 대상 연결이 중복됐습니다.')
    return found[0] if found else None


def view(store,wid):
    with store.connect() as db:
        result=[]
        for row in db.execute("SELECT id,sha256,content FROM artifacts WHERE workspace=? AND kind='check_subject_binding' ORDER BY created",(wid,)):
            if hashlib.sha256(row['content']).hexdigest()!=row['sha256']:raise ValueError('보존 대상 연결의 해시가 다릅니다.')
            result.append({'artifact_id':row['id'],'sha256':row['sha256'],**json.loads(row['content'])})
        return result


def compare(expected,reported):
    key=lambda r:(r['role'],r['artifact_id'],r['artifact_sha256'],r['json_pointer'],r['row_sha256'])
    want={key(r) for r in expected};have={key(r) for r in reported}
    return {'status':'mismatch' if have-want else 'unknown' if want-have or not want else 'same_record',
            'missing':[r for r in expected if key(r) not in have],
            'different':[r for r in reported if key(r) not in want],
            'biological_identity_verified':False,'meaning':MEANING}


def bind_report(db,wid,body,event,proposal):
    if 'subject_binding' in body:raise ValueError('대상 검증 기록은 서버가 작성합니다.')
    context=body.get('research_context') or {};check_id=context.get('check_id')
    check=next((c for c in proposal.get('research_loop',{}).get('next_checks',[]) if c['id']==check_id),None)
    declared=check is not None and 'subject_refs' in check
    if 'reported_subject_refs' not in body and not declared:return
    if not check:raise ValueError('대상 보고를 원 판단의 다음 확인에 연결해 주세요.')
    reported=bind_refs(db,wid,body.get('reported_subject_refs',[]))
    saved=find(db,wid,context['decision_id']) if declared else None
    if declared and not saved:raise ValueError('원 판단의 서버 대상 연결이 없습니다.')
    expected=next(c['subjects'] for c in saved['value']['checks'] if c['check_id']==check_id) if saved else []
    # Revalidate original immutable source records, never substitute the current selection.
    if declared and bind_refs(db,wid,check['subject_refs'],expected=True)!=expected:
        raise ValueError('원 확인에 보존된 대상 원행 또는 조건이 달라졌습니다.')
    event['subject_binding']={'version':'1','decision_id':context['decision_id'],'check_id':check_id,
        'expected_binding_artifact_id':saved['artifact_id'] if saved else None,
        'expected_binding_sha256':saved['sha256'] if saved else None,
        'expected':expected,'reported':reported,
        'comparison':compare(expected,reported) if declared else {'status':'not_declared','biological_identity_verified':False,'meaning':MEANING}}


def verify_worker_binding(bundle,records,decision):
    """Rebuild server receipts from transferred bytes; attachments are not subjects."""
    import base64
    did=bundle['decision_id'];sid=bundle.get('check_subject_binding_id')
    declared={c['id']:c for c in decision['research_loop']['next_checks'] if 'subject_refs' in c}
    def refs(refs,expected=False):
        validate_refs(refs,expected)
        result=[]
        for ref in refs:
            record=records.get(ref['artifact_id'])
            if not record:raise ValueError('전달된 대상 원자료가 없습니다.')
            result.append(bound_record({**record,'content':base64.b64decode(record['content_base64'],validate=True),
                                       'meta':json.dumps(record['meta'])},ref))
        return result
    sidecar=None
    if declared:
        if sid not in records or records[sid]['kind']!='check_subject_binding':raise ValueError('전달된 원 판단의 대상 연결이 없습니다.')
        sidecar=json.loads(base64.b64decode(records[sid]['content_base64'],validate=True))
        expected={'schema_version':'1','decision_id':did,'decision_sha256':records[did]['sha256'],
           'checks':[{'check_id':c['id'],'check_sha256':digest(c),'declaration_origin':'authored_check_declaration_not_researcher_approval',
                      'subject_refs':copy.deepcopy(c['subject_refs']),'subjects':refs(c['subject_refs'],True)} for c in declared.values()],
           'meaning':MEANING,'scientific_validation':False}
        if sidecar!=expected:raise ValueError('원 판단과 대상 원행의 전달 결속이 다릅니다.')
    comparisons={}
    for event in bundle['events']:
        if event['kind']!='observation':continue
        body=event['body'];rc=body.get('research_context') or {}
        if rc.get('decision_id')!=did:continue
        cid=rc.get('check_id');expected=next((c['subjects'] for c in (sidecar or {}).get('checks',[]) if c['check_id']==cid),None)
        saved=body.get('subject_binding')
        if expected is not None or saved is not None:
            reported=refs(body.get('reported_subject_refs',[]))
            comparison=compare(expected or [],reported) if expected is not None else {'status':'not_declared','biological_identity_verified':False,'meaning':MEANING}
            reconstructed={'version':'1','decision_id':did,'check_id':cid,
                'expected_binding_artifact_id':sid if expected is not None else None,
                'expected_binding_sha256':records[sid]['sha256'] if expected is not None else None,
                'expected':expected or [],'reported':reported,'comparison':comparison}
            if saved is not None and saved!=reconstructed:raise ValueError('관측의 대상 비교 영수증이 원자료와 다릅니다.')
            comparisons[body['message_id']]=comparison
    return comparisons


def guarded_calculation_v2(problem,retained,assessment,body,comparison,*,calculation_version='1'):
    from .measurement_report import guarded_calculation
    from .next_observation import select,hold_calculation
    calculated,report_guard=guarded_calculation(problem,retained,assessment,body,calculation_version=calculation_version)
    subject_guard=None
    if assessment is not None and comparison is not None and comparison['status']!='not_declared':
        blocked=comparison['status']!='same_record'
        subject_guard={'version':'1','applied':blocked,'comparison':copy.deepcopy(comparison),'meaning':MEANING}
        if blocked:
            # Keep existing failure/precision repair directions if they already block elimination.
            preserve_status=calculated['summary']['selection_status'] in ('repair_intervention','repair_readout','validity_unresolved','precision_check','context_unresolved','report_confirmation_required')
            status=calculated['summary']['selection_status'] if preserve_status else 'subject_confirmation_required'
            calculated=select(problem,retained,None,calculation_version=calculation_version)
            if calculation_version=='2':
                hold_calculation(calculated,status,assessment['check_id'])
            else:
                calculated['summary'].update(selection_status=status,selected_check_ids=[],cost=0,common_next_decisions=[])
                calculated.update(rows=[],unresolvable_pairs=[],conditional_exclusions=[])
    return calculated,report_guard,subject_guard
