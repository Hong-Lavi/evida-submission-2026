"""Append-only factual amendments of a held observation; never a new measurement."""
from __future__ import annotations
import base64
import copy
import hashlib
import json

HOLDS = frozenset(('report_confirmation_required', 'subject_confirmation_required'))
VERSION = '1'
MEANING = 'Same measurement, amended researcher report only. Original outcome and model assessment are reused; neither the amendment nor matching records certifies experimental validity.'


def digest(value):
    from .next_observation_binding import digest
    return digest(value)


def record(db, wid, aid):
    row = db.execute('SELECT * FROM artifacts WHERE workspace=? AND id=?', (wid, aid)).fetchone()
    if row is None or row['kind'] != 'next_observation_selection' or hashlib.sha256(row['content']).hexdigest() != row['sha256']:
        raise ValueError('이 연구에 보존된 원 선택 결과를 확인해 주세요.')
    if not db.execute("SELECT 1 FROM jobs WHERE workspace=? AND output_id=? AND kind='next_observation_selection' AND status IN ('succeeded','reused')", (wid, aid)).fetchone():
        raise ValueError('실제 완료 작업의 선택 결과에만 보고 정정을 연결할 수 있습니다.')
    value = json.loads(row['content'])
    if value.get('status') != 'succeeded' or value.get('summary', {}).get('selection_status') not in HOLDS or not value.get('result_assessment'):
        raise ValueError('대상 또는 보고 확인을 기다리는 관측 결과만 정정할 수 있습니다.')
    return dict(row), value


def original_event(db, wid, value):
    mid = value['result_assessment']['message_id']
    rows = [dict(r) for r in db.execute("SELECT seq,workspace,kind,body,created FROM events WHERE workspace=? AND kind='observation'", (wid,)) if json.loads(r['body']).get('message_id') == mid]
    if len(rows) != 1:
        raise ValueError('정정할 원 관측을 정확히 연결해 주세요.')
    event = rows[0]; event['body'] = json.loads(event['body'])
    context = event['body'].get('research_context') or {}
    if context.get('decision_id') != value['binding']['decision_id'] or context.get('check_id') != value['result_assessment']['check_id']:
        raise ValueError('원 관측과 판단·확인의 연결이 다릅니다.')
    if value['binding'].get('observation_hashes', {}).get(mid) != digest(event):
        raise ValueError('원 관측의 저장 해시가 다릅니다.')
    return event


def assert_terminal(db, wid, aid, *, own_amendment=None, own_job=None):
    for row in db.execute("SELECT id,content FROM artifacts WHERE workspace=? AND kind='next_observation_selection'", (wid,)):
        value = json.loads(row['content'])
        if value.get('status') == 'succeeded' and (value.get('binding', {}).get('prior_selection_id') == aid or value.get('observation_amendment', {}).get('original_selection_id') == aid):
            raise ValueError('뒤에 계산이 이어진 결과는 일괄 정정하지 않습니다. 말단 보류 결과를 선택해 주세요.')
    for row in db.execute("SELECT body FROM events WHERE workspace=? AND kind='correction'", (wid,)):
        body = json.loads(row['body'])
        if body.get('observation_amendment', {}).get('prior_selection_id') == aid and body.get('message_id') != own_amendment:
            raise ValueError('이 보류 결과에는 이미 정정이 연결됐습니다. 정정 결과 또는 작업 상태를 확인해 주세요.')
    for row in db.execute("SELECT id,request FROM jobs WHERE workspace=? AND kind='next_observation_selection' AND status IN ('queued','running')", (wid,)):
        request = json.loads(row['request'])
        if row['id'] != own_job and request.get('artifact_id') == aid and (own_amendment is None or request.get('_observation_amendment_id') != own_amendment):
            raise ValueError('이 결과의 후속 계산이 진행 중입니다. 완료된 말단 결과에서 확인해 주세요.')


def effective_body(original, held):
    body = copy.deepcopy(original['body'])
    amendment = held.get('observation_amendment')
    if amendment:
        report = amendment['effective_measurement_report']
        if report is None:body.pop('measurement_report', None)
        else:body['measurement_report'] = copy.deepcopy(report)
        body['reported_subject_refs'] = copy.deepcopy(amendment['effective_reported_subject_refs'])
        body['subject_binding'] = copy.deepcopy(amendment['effective_subject_binding'])
    return body


def eligibility(store, wid, aid):
    state = store.snapshot(wid)
    result = {'eligible': False, 'reason': '', 'prior_selection_id': aid, 'expected_rev': state['rev'], 'latest_amendment_id': None}
    try:
        with store.connect() as db:
            raw, held = record(db, wid, aid); event = original_event(db, wid, held)
            assert_terminal(db, wid, aid)
        body = effective_body(event, held); subjects = body.get('subject_binding') or {}
        result.update(eligible=True, target_message_id=event['body']['message_id'], research_context=event['body']['research_context'],
            origin=event['body'].get('origin', 'unknown'), latest_amendment_id=held.get('observation_amendment', {}).get('amendment_message_id'),
            effective_measurement_report=body.get('measurement_report'), effective_reported_subject_refs=body.get('reported_subject_refs', []),
            expected_subjects=subjects.get('expected', []),
            expected_subject_refs=[{k:r[k] for k in ('artifact_id','json_pointer','role')} for r in subjects.get('expected', [])])
    except (ValueError, KeyError) as exc:result['reason'] = str(exc)
    return result


def bind_command(store, db, wid, body, event):
    """Validate and bind inside the command transaction, before the event is appended."""
    spec = body.get('observation_amendment')
    if body.get('kind') != 'correction' or not isinstance(spec, dict) or set(spec) != {'target_message_id','prior_selection_id','reason'}:
        raise ValueError('원 관측·말단 결과와 정정 이유를 지정해 주세요.')
    if not all(isinstance(spec[k], str) and 0 < len(spec[k]) <= (4000 if k == 'reason' else 128) and spec[k].strip() for k in spec):
        raise ValueError('정정 참조와 이유의 형식을 확인해 주세요.')
    if body.get('recalculate_held_selection') is not True or body.get('review_requested') or 'provenance_correction' in body or 'context_update' in body:
        raise ValueError('이 정정은 같은 관측의 CPU 재계산 요청으로 저장해 주세요. 모델 검토·다른 정정과 분리합니다.')
    if not ({'measurement_report','reported_subject_refs'} & set(body)):
        raise ValueError('이번에 확인·정정할 측정 조건 또는 대상 보고를 지정해 주세요.')
    if any(k in body for k in ('amendment_receipt','effective_measurement_report','effective_subject_binding')):
        raise ValueError('정정 결속 기록은 서버가 작성합니다.')
    raw, held = record(db, wid, spec['prior_selection_id']); original = original_event(db, wid, held)
    if spec['target_message_id'] != original['body']['message_id']:
        raise ValueError('정정 대상이 원 결과의 관측과 다릅니다.')
    assert_terminal(db, wid, raw['id'])
    from .next_observation_binding import prepare as prepare_history
    prepare_history(store, wid, {'mode':'review_result','artifact_id':raw['id'],'source_artifact_ids':[],
        'problem':None,'result':held['result_assessment']}, _history_only=True)
    context = original['body']['research_context']
    if 'research_context' in body and body['research_context'] != context:
        raise ValueError('원 관측과 같은 판단·확인에 정정을 연결해 주세요.')
    if 'synthetic' in body and body['synthetic'] != original['body'].get('synthetic', False):
        raise ValueError('정정으로 원 관측의 출처 분류를 바꿀 수 없습니다.')
    previous = effective_body(original, held)
    from .measurement_report import bind_command as bind_report
    from .check_subject_binding import bind_report as bind_subjects
    supplied = copy.deepcopy(body)
    supplied['research_context'] = copy.deepcopy(context)
    for field in ('measurement_report','reported_subject_refs'):
        if field not in supplied and field in previous:supplied[field] = copy.deepcopy(previous[field])
    # Effective report/subject are separately bound; original event bytes never change.
    effective = {'message_id': original['body']['message_id'], 'research_context':copy.deepcopy(context)}
    for field in ('measurement_report','reported_subject_refs'):
        if field in supplied:effective[field] = copy.deepcopy(supplied[field])
    bind_report(db, wid, supplied, effective)
    decision = db.execute('SELECT content FROM artifacts WHERE workspace=? AND id=?', (wid, context['decision_id'])).fetchone()
    if decision is None:raise ValueError('원 판단을 찾을 수 없습니다.')
    bind_subjects(db, wid, supplied, effective, json.loads(decision['content']))
    event.update(research_context=copy.deepcopy(context), origin=original['body'].get('origin','unknown'),
        synthetic=original['body'].get('synthetic',False))
    # Preserve only explicitly authored fields in the correction body; inherited data
    # belongs to the server receipt and must not appear as a newly authored report.
    for field in ('source_artifact_hashes','source_artifact_refs'):
        if field in effective:event[field] = effective[field]
    from .input_provenance import annotate_events
    history=[{**dict(r),'body':json.loads(r['body'])} for r in db.execute('SELECT seq,workspace,kind,body,created FROM events WHERE workspace=? ORDER BY seq',(wid,))]
    classification=next(e['effective_provenance'] for e in annotate_events(history) if e['body'].get('message_id')==original['body']['message_id'])
    event['amendment_receipt'] = {'original_effective_provenance':classification, 'version':VERSION, 'original_observation_sha256':digest(original),
        'original_selection_sha256':raw['sha256'], 'original_assessment_sha256':digest(held['result_assessment']),
        'previous_amendment_id':held.get('observation_amendment',{}).get('amendment_message_id'),
        'effective_measurement_report':effective.get('measurement_report'),
        'effective_reported_subject_refs':effective.get('reported_subject_refs',[]),
        'effective_subject_binding':effective.get('subject_binding'),
        'meaning':MEANING,'scientific_validation':False}
    return held


def enqueue(store, db, wid, rev, event, held):
    from .store import uid, now, dump
    jid, attempt = uid('job'), uid('attempt')
    request = {'mode':'review_result','artifact_id':event['observation_amendment']['prior_selection_id'],
        'source_artifact_ids':[], 'problem':None, 'result':copy.deepcopy(held['result_assessment']),
        '_observation_amendment_id':event['message_id']}
    db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,NULL,NULL,?,?)',
        (jid,wid,rev,'next_observation_selection',dump(request),'queued',now(),now(),None,attempt))
    store.event(db,wid,'job_queued',{'job_id':jid,'kind':'next_observation_selection','based_rev':rev,'same_measurement_amendment_id':event['message_id']})
    return jid


def prepare(store, wid, arguments, amendment_id, *, own_job=None):
    from .next_observation_binding import prepare as base_prepare, evaluate
    state = store.snapshot(wid)
    matches = [e for e in state['events'] if e['kind']=='correction' and e['body'].get('message_id') == amendment_id]
    if len(matches)!=1:raise ValueError('서버에 보존한 관측 정정이 없습니다.')
    correction = {k:copy.deepcopy(matches[0][k]) for k in ('seq','workspace','kind','body','created')}
    body=correction['body'];aid=body.get('observation_amendment',{}).get('prior_selection_id')
    with store.connect() as db:
        raw,held=record(db,wid,aid);assert_terminal(db,wid,aid,own_amendment=amendment_id,own_job=own_job)
    expected={'mode':'review_result','artifact_id':aid,'source_artifact_ids':[], 'problem':None,'result':held['result_assessment']}
    if arguments!=expected:raise ValueError('정정은 원 결과의 모델 해석을 그대로 재사용합니다.')
    bundle=base_prepare(store,wid,arguments,_history_only=True)
    bundle['observation_amendment_id']=amendment_id
    if not any(e['body']['message_id']==amendment_id for e in bundle['events']):bundle['events'].append(correction)
    refs=body['amendment_receipt']['effective_reported_subject_refs']
    for source_id in list(body.get('source_artifact_ids',[]))+[r['artifact_id'] for r in refs]:
        if source_id not in bundle['artifacts']:
            artifact=store.artifact(wid,source_id);bundle['artifacts'][source_id]={k:artifact[k] for k in ('id','kind','sha256','title','meta')}
            bundle['artifacts'][source_id]['content_base64']=base64.b64encode(artifact['content']).decode()
    # Prior amendments are audit dependencies even if they are outside the active branch.
    event_ids=set()
    for artifact in bundle['artifacts'].values():
        if artifact['kind']=='next_observation_selection':
            value=json.loads(base64.b64decode(artifact['content_base64']))
            event_ids.update(value.get('observation_amendment',{}).get('replay_event_ids',[]))
    for e in state['events']:
        if e['body'].get('message_id') in event_ids and not any(v['body']['message_id']==e['body']['message_id'] for v in bundle['events']):
            bundle['events'].append({k:copy.deepcopy(e[k]) for k in ('seq','workspace','kind','body','created')})
    bundle['events'].sort(key=lambda e:e['seq']);evaluate(bundle)
    return bundle


def verify(bundle, values, records):
    """Reconstruct the effective typed view from immutable raw events and sources."""
    from .measurement_report import validate_report
    from .check_subject_binding import verify_worker_binding
    mid=bundle['observation_amendment_id'];events={e['body']['message_id']:e for e in bundle['events']}
    correction=events.get(mid)
    if not correction or correction['kind']!='correction':raise ValueError('보존한 정정 이벤트를 전달해 주세요.')
    body=correction['body'];spec=body.get('observation_amendment') or {};aid=spec.get('prior_selection_id')
    if set(spec)!={'target_message_id','prior_selection_id','reason'} or not isinstance(spec['reason'],str) or not spec['reason'].strip():raise ValueError('정정 참조·이유가 다릅니다.')
    if not bundle['prior_chain'] or bundle['prior_chain'][-1]!=aid or aid not in values:raise ValueError('정정할 원 말단 선택이 다릅니다.')
    held=values[aid]
    if held['summary']['selection_status'] not in HOLDS or held.get('result_assessment')!=bundle['arguments']['result']:
        raise ValueError('원 보류 상태와 모델 해석을 그대로 연결해 주세요.')
    original=events.get(spec['target_message_id'])
    if not original or original['kind']!='observation' or held['result_assessment']['message_id']!=spec['target_message_id']:
        raise ValueError('원 관측과 정정 참조가 다릅니다.')
    if correction['seq']<=original['seq'] or body.get('research_context')!=original['body'].get('research_context'):
        raise ValueError('정정의 원 판단·시간 연결이 다릅니다.')
    if body.get('origin')!=original['body'].get('origin','unknown') or body.get('synthetic')!=original['body'].get('synthetic',False):
        raise ValueError('정정이 원 관측의 출처를 승격할 수 없습니다.')
    effective=effective_body(original,held)
    if not ({'measurement_report','reported_subject_refs'} & set(body)):raise ValueError('정정할 보고가 없습니다.')
    for key in ('measurement_report','reported_subject_refs'):
        if key in body:effective[key]=copy.deepcopy(body[key])
    if 'measurement_report' in effective:validate_report(effective['measurement_report'])
    receipt=body.get('amendment_receipt') or {}
    pseudo=copy.deepcopy(original);pseudo['body']=effective
    # Verify exact row identity by rebuilding the existing worker subject receipt.
    pseudo['body'].pop('subject_binding',None)
    if receipt.get('effective_subject_binding') is not None:
        pseudo['body']['subject_binding']=copy.deepcopy(receipt['effective_subject_binding'])
    isolated={**bundle,'events':[pseudo]}
    comparison=verify_worker_binding(isolated,records,values[bundle['decision_id']]).get(spec['target_message_id'])
    expected_subject=None
    if comparison is not None:
        sid=bundle.get('check_subject_binding_id') if comparison['status']!='not_declared' else None;sidecar=json.loads(base64.b64decode(records[sid]['content_base64'])) if sid else None
        check_id=held['result_assessment']['check_id']
        expected=next((c['subjects'] for c in (sidecar or {}).get('checks',[]) if c['check_id']==check_id),[])
        from .check_subject_binding import bound_record
        reported=[bound_record({**records[r['artifact_id']],'content':base64.b64decode(records[r['artifact_id']]['content_base64']), 'meta':json.dumps(records[r['artifact_id']]['meta'])},r) for r in effective.get('reported_subject_refs',[])]
        expected_subject={'version':'1','decision_id':bundle['decision_id'],'check_id':check_id,
            'expected_binding_artifact_id':sid,'expected_binding_sha256':records[sid]['sha256'] if sid else None,
            'expected':expected,'reported':reported,'comparison':comparison}
    from .input_provenance import annotate_events
    classification=next(e['effective_provenance'] for e in annotate_events(copy.deepcopy(bundle['events'])) if e['body'].get('message_id')==spec['target_message_id'])
    expected_receipt={'original_effective_provenance':classification,'version':VERSION,'original_observation_sha256':digest(original),
        'original_selection_sha256':records[aid]['sha256'],'original_assessment_sha256':digest(held['result_assessment']),
        'previous_amendment_id':held.get('observation_amendment',{}).get('amendment_message_id'),
        'effective_measurement_report':effective.get('measurement_report'),
        'effective_reported_subject_refs':effective.get('reported_subject_refs',[]),
        'effective_subject_binding':expected_subject,'meaning':MEANING,'scientific_validation':False}
    if receipt!=expected_receipt:raise ValueError('정정의 원 보고·대상·해시 결속이 다릅니다.')
    from .measurement_report import compare_report
    metadata={'version':VERSION,'amendment_message_id':mid,'amendment_event_sha256':digest(correction),
        'original_observation_message_id':spec['target_message_id'],'original_selection_id':aid,
        **copy.deepcopy(receipt),'reason':spec['reason'],
        'source_artifact_refs':copy.deepcopy(body.get('source_artifact_refs',[])),
        'source_artifact_hashes':copy.deepcopy(body.get('source_artifact_hashes',{})),
        'independent_observation_added':False,'original_model_assessment_reused':True,
        'effective_report_comparison':compare_report(effective,held['result_assessment']),
        'replay_arguments':copy.deepcopy(bundle['arguments']),
        'replay_event_ids':[e['body']['message_id'] for e in bundle['events']]}
    return effective, comparison, metadata


def replay(old, bundle, *, depth):
    """Verify a saved amendment branch using its original records, once per level."""
    from .next_observation_binding import evaluate
    if depth>=32:raise ValueError('정정 분기의 재생 길이를 확인해 주세요.')
    amendment=old['observation_amendment'];records=bundle['artifacts']
    selected={aid:records[aid] for aid in old['provenance']['source_hashes']}
    for aid,r in selected.items():
        if r['sha256']!=old['provenance']['source_hashes'][aid]:raise ValueError('정정 이력의 원자료 해시가 다릅니다.')
    events={e['body']['message_id']:e for e in bundle['events']}
    chain=[];cursor=amendment['original_selection_id']
    while cursor:
        if cursor in chain or len(chain)>=32:raise ValueError('정정 원 이력의 순환 또는 길이 범위입니다.')
        chain.append(cursor);value=json.loads(base64.b64decode(selected[cursor]['content_base64']));cursor=value['binding']['prior_selection_id']
    reconstructed={k:copy.deepcopy(bundle[k]) for k in ('workspace_id','decision_id','review_id','check_subject_binding_id','published_decision_ids')}
    reconstructed.update(calculation_version=old['calculation_version'],arguments=amendment['replay_arguments'],prior_chain=list(reversed(chain)),artifacts=selected,
        events=[events[mid] for mid in amendment['replay_event_ids']],source_message_ids=list(old['provenance'].get('source_message_hashes',{})),
        source_message_hashes=old['provenance'].get('source_message_hashes',{}),observation_amendment_id=amendment['amendment_message_id'])
    return evaluate(reconstructed,_depth=depth+1)
