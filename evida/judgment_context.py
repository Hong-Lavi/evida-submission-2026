"""Versioned explanatory context sidecar. Links request review, never infer truth."""
import json
import jsonschema


def obj(p):return {'type':'object','properties':p,'required':list(p),'additionalProperties':False}
T={'type':'string'}
TS={'type':'array','items':T}
def enum(*x):return {'type':'string','enum':list(x)}
def array(x,n=60):return {'type':'array','items':x,'maxItems':n}
CONTEXT=obj({'id':T,'organism':T,'target_construct_variant':T,'transcript_version':T,'tissue_cell':T,
    'intervention_chemistry_formulation':T,'dose_route':T,'time':T,'assay_buffer':T,'comparator':T,'unknowns':TS,'source_ids':TS})
PREDICTION=obj({'observable':T,'direction_or_range':T,'unit':T,'time':T,'comparator':T,
    'origin':enum('prospective','previously_recorded','reconstructed_after_result')})
BINDING=obj({'hypothesis_id':T,'part_id':T,'stage':enum('mechanism','target_intervention','approach','candidate'),
    'context_id':T,'assumption_ids':TS,'prediction':PREDICTION})
ASSUMPTION=obj({'id':T,'statement':T,'status':enum('proposed','checked_in_context','challenged','unknown'),
    'context_id':T,'source_ids':TS})
OBSERVATION=obj({'source_id':T,'hypothesis_id':T,'part_id':T,'context_id':T,
    'measurement_quality':T,'processing_validity':T,'applicability':T,'explanatory_adequacy':T,'next_check':T})
LINK=obj({'from_hypothesis_id':T,'review_upstream_hypothesis_id':T,'assumption_id':T,'reason':T})
SCHEMA=obj({'contexts':array(CONTEXT,30),'bindings':array(BINDING),'assumptions':array(ASSUMPTION),
    'observation_reviews':array(OBSERVATION),'review_links':array(LINK),'unresolved_context':TS})


def validate(value,state,hypotheses):
    jsonschema.validate(value,SCHEMA)
    known={a['id'] for a in state['artifacts']}|{e['body']['message_id'] for e in state['events'] if e['body'].get('message_id')}
    hs={h['id']:h for h in hypotheses}
    def unique(rows,label):
        ids=[x['id'] for x in rows]
        if any(not x.strip() for x in ids) or len(set(ids))!=len(ids):raise ValueError(label+' ID가 비었거나 중복됐습니다.')
        return set(ids)
    cs=unique(value['contexts'],'문맥');aa=unique(value['assumptions'],'가정')
    def target(h,p):
        if h not in hs:raise ValueError('현재 가설 ID와 다릅니다.')
        if p and p not in {x['id'] for x in hs[h].get('assessment_scope',{}).get('parts',[])}:raise ValueError('해당 가설의 부분 ID가 아닙니다.')
    for c in value['contexts']+value['assumptions']:
        if not set(c['source_ids']).issubset(known):raise ValueError('문맥/가정의 출처가 이 연구에 없습니다.')
    for a in value['assumptions']:
        if a['context_id'] not in cs:raise ValueError('가정 문맥이 없습니다.')
    seen=set()
    for b in value['bindings']:
        target(b['hypothesis_id'],b['part_id']);key=(b['hypothesis_id'],b['part_id'],b['context_id'])
        if key in seen:raise ValueError('같은 가설 부분·동일 문맥의 연결이 중복됐습니다. 다른 시험 조건은 서로 다른 context_id로 보존해 주세요: '+str(key))
        seen.add(key)
        if b['context_id'] not in cs or not set(b['assumption_ids']).issubset(aa):raise ValueError('문맥 또는 가정 ID를 확인해 주세요.')
    for o in value['observation_reviews']:
        target(o['hypothesis_id'],o['part_id'])
        if o['source_id'] not in known or o['context_id'] not in cs:raise ValueError('관측 원자료/문맥을 확인해 주세요.')
    for edge in value['review_links']:
        target(edge['from_hypothesis_id'],'');target(edge['review_upstream_hypothesis_id'],'')
        if edge['assumption_id'] and edge['assumption_id'] not in aa:raise ValueError('검토 경로의 가정이 없습니다.')


def review_impact(context,hypothesis_ids,part_targets=()):
    """Traverse only explicitly authored review links; no causal/Boolean update."""
    selected=set(hypothesis_ids);front=list(selected);paths=[]
    while front:
        current=front.pop()
        for edge in context.get('review_links',[]):
            if edge['from_hypothesis_id']!=current:continue
            paths.append(edge)
            nxt=edge['review_upstream_hypothesis_id']
            if nxt not in selected:selected.add(nxt);front.append(nxt)
    all_h={b['hypothesis_id'] for b in context.get('bindings',[])}
    return {'direct_hypotheses':list(hypothesis_ids),'direct_parts':list(part_targets),
        'upstream_review':sorted(selected-set(hypothesis_ids)),'review_paths':paths,
        'outside_explicit_review_paths':sorted(all_h-selected),'automatic_assessment_changes':False,
        'automatic_scientific_reexecution':False,'meaning':'review questions only; unchanged inputs may reuse completed calculations; no automatic rejection'}


def view(store,wid,state):
    artifact=next((a for a in reversed(state['artifacts']) if a['kind']=='judgment_context'),None)
    if not artifact:return None
    raw=store.artifact(wid,artifact['id']);v=json.loads(raw['content'])
    v.update(artifact_id=artifact['id'],current_revision=state['rev'],context_revision=artifact['meta']['based_rev'],
        is_current_input=artifact['meta']['based_rev']==state['rev'])
    decision_event=next((e for e in reversed(state['events']) if e['kind']=='decision_published'),None)
    v['published_decision_id']=None
    if decision_event:
        d=store.artifact(wid,decision_event['body']['receipt_id'])
        if d['meta'].get('job_id')==artifact['meta'].get('job_id'):
            try:validate(v['context'],state,json.loads(d['content'])['research_loop']['hypotheses'])
            except (ValueError,KeyError,jsonschema.ValidationError):pass
            else:v['published_decision_id']=d['id']
    changes=[]
    for e in state['events']:
        rc=e['body'].get('research_context')
        if rc and e['body'].get('state_rev',0)>artifact['meta']['based_rev'] and rc.get('decision_id')==v['published_decision_id']:
            changes.append({'message_id':e['body']['message_id'],'text':e['body']['text'],'kind':e['kind'],
                'impact':review_impact(v['context'],rc['hypothesis_ids'],rc.get('scope_targets',[]))})
    v['pending_changes']=changes
    return v
