"""Retain discovered options, assessments and human choices as different records.

The pool is a deterministic view of immutable source artifacts and review batches.
Omitting an option from a later recommendation never removes its source or history.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import re

import jsonschema


def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


TEXT={'type':'string'}
TEXTS={'type':'array','items':TEXT}
KINDS=('mechanism','target','approach','source_candidate','molecule','rna_candidate','researcher_proposal')
OPTION=obj({'option_id':{'type':'string','pattern':'^(mechanism|approach):.+$','description':'Stable namespaced ID: mechanism:your-id for a mechanism, approach:your-id for an approach. Reuse it exactly in assessments.'},'kind':{'type':'string','enum':['mechanism','approach']},
            'label':TEXT,'description':TEXT,'source_ids':TEXTS})
ASSESSMENT=obj({'option_id':{'type':'string','description':'Use the exact namespaced option_id from inspect_discovery_options (for example rna:...). A guide ID in a calculation is an entity identifier, not the catalog option_id.'},'status':{'type':'string','enum':['recommended','alternative','needs_evidence','deferred']},
                'priority':{'type':['integer','null'],'minimum':1},'comparison_group':TEXT,
                'reason':TEXT,'support_source_ids':TEXTS,'challenge_source_ids':TEXTS,
                'uncertainties':TEXTS,'next_action':TEXT})
# Candidate27 (team feedback A2/A3): an optional mechanism/approach profile. Legacy assessments
# stay valid. Axes are rubric levels or null (unchecked, never imputed); the server computes a
# dominance order from them. Basis clauses are anchored to stored source rows and checked
# mechanically after submission; a failed anchor is recorded, not rewritten.
AXIS={'anyOf':[{'type':'number','minimum':0,'maximum':1},{'type':'null'}]}
ASPECTS=obj({'disease_match':AXIS,'clinical_precedent':AXIS,'evidence_grade':AXIS,'actionability':AXIS})
DISEASE_MATCH={'type':'string','enum':['target_disease','related_disease','animal_model','in_vitro','none']}
CLAUSE=obj({'text':{'type':'string','minLength':1,'description':'One causal step (A->B, B->C or C->disease phenotype).'},
            'disease_match':DISEASE_MATCH,
            'context':obj({'disease':TEXT,'species':TEXT,'tissue':TEXT}),
            'anchor':obj({'artifact_id':TEXT,'row_index':{'type':'integer','minimum':0},
                          'quote':{'type':'string','minLength':1,'maxLength':2500,
                                   'description':'Exact substring of that stored source row, copied verbatim.'}})})
GAP=obj({'claim':{'type':'string','minLength':1,'description':'What is missing in the target disease, e.g. no interventional study of this step.'},
         'query_artifact_id':{'type':'string','description':'A search artifact actually run (literature, clinical_trial_search, drug_label_search, lens_literature).'},
         'reported_count':{'type':['integer','null'],'minimum':0,'description':'The total hit count recorded in that artifact, copied as is.'}})
BASIS=obj({'grade':{'type':'string','enum':['established','demonstrated','hypothesis'],
                    'description':'established: human interventional evidence in the target disease; demonstrated: target-disease animal/cell interventional evidence only; hypothesis: no interventional evidence in the target disease.'},
           'clauses':{'type':'array','minItems':1,'maxItems':3,'items':CLAUSE},
           'missing_in_target_disease':{'type':'array','maxItems':10,'items':GAP},
           'hypothesis_id':{'type':'string','description':'research_loop hypothesis ID for this mechanism, or empty.'}})
# A candidate is judged for a mechanism, but nothing in the record said which one: the comparison
# group is free text, and matching it by name would invent a link. This states it, or stays null.
TARGETS=obj({'option_id':{'type':'string','description':"The mechanism/approach option_id this candidate is meant to act on, exactly as inspect_discovery_options gives it."},
             'reason':{'type':'string','description':'Why this candidate is taken to act on that mechanism, from the evidence read.'}})
# Every property of obj() is required and extras are forbidden, so each optional addition is a
# separate accepted shape. All four combinations are listed: a candidate naming the mechanism it
# acts on has no reason to also carry the mechanism axes, and requiring them together would reject
# the whole judgement over a field the record did not need.
_PROFILE={'aspects':ASPECTS,'basis':{'anyOf':[BASIS,{'type':'null'}]},
          'challenge_applies':{'anyOf':[{'type':'boolean'},{'type':'null'}],
                               'description':'기록한 challenge_source_ids가 이 주장·이 결과에 적용되는가. '
                                             'true면 비교를 보류하고, false는 적용 범위를 검토해 벗어난다고 '
                                             '판단했다는 뜻이며, 아직 판단하지 못했으면 null. '
                                             'challenge_source_ids가 비어 있으면 null로 둔다.'}}
_TARGET={'targets_mechanism':{'anyOf':[TARGETS,{'type':'null'}]}}
PROFILED_ASSESSMENT=obj({**ASSESSMENT['properties'],**_PROFILE})
TARGETED_ASSESSMENT=obj({**ASSESSMENT['properties'],**_TARGET})
PROFILED_TARGETED_ASSESSMENT=obj({**ASSESSMENT['properties'],**_PROFILE,**_TARGET})
ASSESSMENT_SHAPES=[ASSESSMENT,PROFILED_ASSESSMENT,TARGETED_ASSESSMENT,PROFILED_TARGETED_ASSESSMENT]
REVIEW=obj({'question':TEXT,'new_options':{'type':'array','items':OPTION,'maxItems':100},
           'assessments':{'type':'array','items':{'anyOf':ASSESSMENT_SHAPES},'maxItems':100},'unsearched_scope':TEXTS})


def short_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _materialization_sources(artifacts, source_ids):
    """Follow only declared CSV materialization ancestry, never molecule-name guesses."""
    known={a['id']:a for a in artifacts}
    sources=list(dict.fromkeys(source_ids));seen=set(sources);links=[]
    for source_id in sources:
        artifact=known.get(source_id)
        if not artifact or artifact['kind']!='molecule_csv':continue
        meta=artifact['meta']
        parents=list(dict.fromkeys(s for s in
            [meta.get('source_pool_id'),*(meta.get('consumed_artifacts') or [])]
            if isinstance(s,str) and s))
        for parent in parents:
            upstream=known.get(parent)
            expected=meta.get('source_pool_sha256') if parent==meta.get('source_pool_id') else None
            status=('not_in_workspace' if upstream is None else
                    'source_pool_hash_mismatch' if expected and expected!=upstream['sha256'] else
                    'declared_materialization')
            links.append({'artifact_id':source_id,'source_artifact_id':parent,'status':status})
            if status=='declared_materialization' and parent not in seen:
                seen.add(parent);sources.append(parent)
    return sources,links


def catalog(store,wid,state=None):
    state=state or store.snapshot(wid)
    options={};coverage=[];reviews=[];rna_windows={};identity_links=[]

    def retain(key,kind,label,description,source_id=None,locator=None,**extras):
        if key not in options:
            options[key]={'option_id':key,'kind':kind,'label':label,'description':description,
                'sources':[],'assessments':[],'assessment':None,'review_status':'unreviewed',**extras}
        option=options[key]
        if source_id:
            ref={'artifact_id':source_id,'locator':locator}
            if ref not in option['sources']:option['sources'].append(ref)
        return option

    source_kinds={'disease_targets','source_candidates','compound_candidates','literature_compounds','binding_measurements','gtopdb_pharmacology','analogue_proposal','rna_candidate_generation','rna_sequence_evaluation','discovery_review'}
    for artifact in state['artifacts']:
        kind=artifact['kind']
        if kind not in source_kinds:continue
        value=json.loads(store.artifact(wid,artifact['id'])['content'])
        if kind=='discovery_review':
            reviews.append((artifact,value))
            for row in value.get('new_options',[]):
                option=retain(row['option_id'],row['kind'],row['label'],row['description'],
                    artifact['id'],'new_options/'+row['option_id'],origin='model_proposal')
                for source in row['source_ids']:
                    ref={'artifact_id':source,'locator':None}
                    if ref not in option['sources']:option['sources'].append(ref)
            continue
        summary=value.get('summary',{})
        if kind=='rna_candidate_generation' and value.get('generation'):
            gen=value['generation'];ref=value['reference'];key=(ref['sequence_sha256'],gen['paired_length'])
            space=rna_windows.setdefault(key,{'transcript_id':ref['transcript_id'],'version':ref.get('version'),'sequence_sha256':ref['sequence_sha256'],'paired_length':gen['paired_length'],'possible_windows':gen['total_possible_windows'],'positions':set()})
            space['positions'].update(range(gen['start_1_based'],gen['start_1_based']+gen['count']*gen['stride'],gen['stride']))
        coverage.append({'artifact_id':artifact['id'],'kind':kind,'summary':summary,
                         'status':value.get('status'),'query':value.get('variables',value.get('filters',value.get('query')))})
        rows=[(index,row,None) for index,row in enumerate(value.get('rows',[]))]
        if kind=='analogue_proposal':
            rows.extend((index,row,'guided_search') for index,row in
                        enumerate((value.get('guided_search') or {}).get('rows',[])))
        for index,row,branch in rows:
            if kind=='analogue_proposal':
                entity=row.get('candidate_id')
                if not isinstance(entity,str) or not entity:continue
                # Worker-local names (proposed-1, ...) recur in every generation. The
                # immutable result artifact scopes the identity, even for equal SMILES.
                source_ids=list(dict.fromkeys(s for s in
                    [value.get('source_artifact_id'),*(artifact['meta'].get('consumed_artifacts') or [])]
                    if isinstance(s,str) and s))
                source_ids,materializations=_materialization_sources(state['artifacts'],source_ids)
                # proposal_parents belongs to the main CSV branch. Guided rounds reuse
                # those local labels for different structures, including within a run.
                parents=(row.get('declared_comparators',[]) if branch else
                         (value.get('proposal_parents') or {}).get(entity,row.get('declared_comparators',[])))
                if isinstance(parents,str):parents=[parents]
                generation={'artifact_id':artifact['id'],'source_artifact_id':value.get('source_artifact_id'),
                    'source_artifact_ids':source_ids,'parent_candidate_ids':deepcopy(parents),
                    'materialization_links':materializations,
                    'declared_comparators':deepcopy(row.get('declared_comparators',[])),
                    'method':value.get('method'),'status':value.get('status'),
                    **{k:deepcopy(row.get(k)) for k in
                       ('transformed_from','core_from','substituent_from','transformation','context_radius')}}
                key='molecule:generated:'+artifact['id']+':'+entity
                locator='rows/'+str(index)
                extras={}
                if branch:
                    key=('molecule:generated:'+artifact['id']+':guided_search:round:'+
                         str(row.get('round','unknown'))+':row:'+str(index)+':'+entity)
                    locator='guided_search/rows/'+str(index)
                    generation.update(branch=branch,row_index=index,round=row.get('round'),
                        declared_parent_structure={'candidate_id':row.get('nearest_retrieved'),
                                                   'smiles':row.get('nearest_retrieved_smiles')})
                    extras['candidate_row_locator']=['guided_search','rows',index]
                option=retain(key,'molecule',
                    row.get('name') or entity,'생성된 구조 제안 · 이 생성 실행에서 활성은 측정되지 않았습니다.',
                    artifact['id'],locator,entity_id=entity,
                    context=value.get('source_artifact_id'),origin='generated_structure_proposal',
                    structure_status='available' if row.get('smiles') else 'not_available',
                    candidate_artifact_id=artifact['id'],generation=generation,
                    activity_evidence_status='not_measured_in_this_generation',**extras)
                for source_id in source_ids:
                    ref={'artifact_id':source_id,'locator':None}
                    if ref not in option['sources']:option['sources'].append(ref)
            elif kind=='source_candidates':
                option=retain(row['candidate_id'],'source_candidate',row['name'],row['membership_reason'],
                    artifact['id'],'rows/'+str(index),origin='source_anchored_candidate_assertion',
                    candidate_records=[],identity_links=[])
                option['candidate_records'].append({'artifact_id':artifact['id'],'row_index':index,'record':row})
                option.update({k:row[k] for k in ('modality','role','target_context','identity','conditions','next_check','structure_status')})
                option['candidate_artifact_id']=artifact['id']
                ref={'artifact_id':row['mention']['artifact_id'],'locator':row['mention']['locator']}
                if ref not in option['sources']:option['sources'].append(ref)
            elif kind=='disease_targets':
                target=row.get('target') or {};entity=target.get('id')
                if not entity:continue
                disease=(value.get('disease') or {}).get('id','unknown')
                retain('target:'+disease+':'+entity,'target',target.get('approvedSymbol') or entity,
                    target.get('approvedName') or '',artifact['id'],'rows/'+str(index),
                    entity_id=entity,context=disease,origin='database_association',
                    database_score=row.get('score'),database_score_meaning='association_not_intervention_priority')
            elif kind=='gtopdb_pharmacology':
                entity=row['ligand_id'];target=row['target_id'];species=row['target_species']
                retain(f'molecule:gtopdb:{target}:{species}:{entity}','molecule',row['ligand_name'] or str(entity),
                    'GtoPdb의 작용·측정 기록에서 회수한 물질 · 효능 미검토',artifact['id'],'rows/'+str(index),
                    entity_id=str(entity),context=f'gtopdb:{target}:{species}',origin='curated_pharmacology_record',
                    structure_status='not_requested',candidate_artifact_id=artifact['id'])
            elif kind in ('compound_candidates','literature_compounds','binding_measurements'):
                entity=row.get('candidate_id')
                if not entity:continue
                target=value.get('target_chembl_id',value.get('target_context','unknown'))
                retain('molecule:'+target+':'+entity,'molecule',row.get('name') or entity,
                    '공개 활성 기록에서 회수한 화합물' if kind in ('compound_candidates','binding_measurements') else ('원문 이름으로 회수한 데이터베이스 구조 · 원 시료와의 동일성은 별도 확인' if row.get('structure_status')=='available' else '원문에서 보존한 이름 · 구조 식별 확인 필요'),artifact['id'],'rows/'+str(index),
                    entity_id=entity,context=target,origin='public_activity_record' if kind in ('compound_candidates','binding_measurements') else 'public_literature_and_structure',
                    structure_status=row.get('structure_status'),candidate_artifact_id=artifact['id'])
                for source_id in row.get('source_candidate_ids',[]):
                    identity_links.append((source_id,{'artifact_id':artifact['id'],'row_index':index,
                        'candidate_id':entity,'structure_status':row.get('structure_status'),
                        'identity_status':row.get('identity_status'),'next_identity_check':row.get('next_identity_check')}))
            else:
                entity=row.get('candidate_id') or row.get('id')
                if not entity:continue
                guide=row.get('guide_5to3') or row.get('guide') or ''
                reference=value.get('reference',{})
                reference_key=json.dumps(reference,sort_keys=True,ensure_ascii=False)
                key='rna:'+short_hash(reference_key+'|'+str(entity)+'|'+guide)
                retain(key,'rna_candidate',str(entity),guide,artifact['id'],'rows/'+str(index),
                    entity_id=str(entity),origin='computed_sequence_candidate',candidate_artifact_id=artifact['id'])
    # Resolve a parent only through its exact local identifier AND a consumed source.
    # An unresolved parent stays visible; a same-named molecule elsewhere is not a match.
    parent_index={}
    for option in options.values():
        if option['kind']!='molecule' or option.get('origin')=='generated_structure_proposal':continue
        for source in option['sources']:
            parent_index.setdefault((source['artifact_id'],option.get('entity_id')),[]).append(option['option_id'])
    for option in options.values():
        generation=option.get('generation')
        if not generation:continue
        links=[]
        for parent in generation['parent_candidate_ids']:
            if generation.get('branch')=='guided_search' and any(
                    other.get('candidate_artifact_id')==generation['artifact_id'] and
                    other.get('origin')=='generated_structure_proposal' and
                    other.get('entity_id')==parent for other in options.values()):
                # The worker declares a local parent name and a structure string, but
                # not a branch/row identity. Retain both without binding it to a
                # same-named main or guided option. A later explicit link can resolve it.
                links.append({'candidate_id':parent,'option_ids':[],
                              'status':'unresolved_generated_parent'})
                continue
            matches=sorted({key for source_id in generation['source_artifact_ids']
                            for key in parent_index.get((source_id,parent),[])})
            links.append({'candidate_id':parent,'option_ids':matches,
                          'status':'resolved' if len(matches)==1 else 'ambiguous' if matches else 'not_in_catalog'})
        generation['parent_links']=links
    for event in state['events']:
        proposal=event['body'].get('discovery_proposal')
        if proposal:
            retain('proposal:'+event['body']['message_id'],'researcher_proposal',proposal['label'],
                   event['body']['text'],origin='researcher_proposal',message_id=event['body']['message_id'])
    for source_id,link in identity_links:
        if source_id in options:options[source_id]['identity_links'].append(link)
    unsearched=[];scope_review=None
    for artifact,value in reviews:
        for row in value.get('assessments',[]):
            if row['option_id'] not in options:continue
            assessment={**row,'artifact_id':artifact['id'],'based_rev':artifact['meta']['based_rev'],
                        'current_conditions':artifact['meta']['based_rev']==state['rev']}
            if 'aspects' in row:
                assessment['basis_check']=next((c for c in artifact['meta'].get('basis_check',[])
                                                if c['option_id']==row['option_id']),None)
            options[row['option_id']]['assessments'].append(assessment)
            options[row['option_id']]['assessment']=assessment
            options[row['option_id']]['review_status']=row['status']
        unsearched=value.get('unsearched_scope',[])
        scope_review={'artifact_id':artifact['id'],'based_rev':artifact['meta']['based_rev'],
            'current_conditions':artifact['meta']['based_rev']==state['rev'],
            'meaning':'The scope statement at this review; later source retrieval does not silently rewrite it.'}
    selections=[{**e['body']['discovery_selection'],'message_id':e['body']['message_id'],
                 'state_rev':e['body']['state_rev']} for e in state['events'] if e['body'].get('discovery_selection')]
    current=selections[-1] if selections else None
    for item in options.values():
        item['selected']=bool(current and current['option_id']==item['option_id'])
    rna_coverage=[{k:v for k,v in x.items() if k!='positions'}|{'generated_windows':len(x['positions']),'remaining_windows_not_generated':x['possible_windows']-len(x['positions'])} for x in rna_windows.values()]
    values=list(options.values())
    return {'options':values,'total':len(values),'counts':dict(Counter(x['kind'] for x in values)),
            'reviewed':sum(x['assessment'] is not None for x in values),
            'selected':current,'selection_history':selections,'coverage':coverage,'rna_search_coverage':rna_coverage,'unsearched_scope':unsearched,'scope_review':scope_review,
            'meaning':'Discovered and retained options, not an exhaustive mechanism universe or a validated efficacy ranking.'}


def inspect(store,wid,query='',kind='',offset=0,limit=20):
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
        raise ValueError('선택지의 조회 범위를 확인해 주세요.')
    if kind and kind not in KINDS:raise ValueError('선택지 종류를 확인해 주세요.')
    value=catalog(store,wid);term=query.casefold().strip()
    rows=[x for x in value.pop('options') if (not kind or x['kind']==kind)
          and (not term or term in json.dumps(x,ensure_ascii=False).casefold())]
    # A model's partial priorities are only meaningful within its comparison group.
    # No priority is invented for unassessed items; database scores do not rank them.
    rows.sort(key=lambda x:(not x['selected'], x['assessment'] is None,
                           (x['assessment'] or {}).get('comparison_group',''),
                           (x['assessment'] or {}).get('priority') or 10**9, x['label']))
    return {**value,'rows':rows[offset:offset+limit],'filtered_total':len(rows),'offset':offset,
            'has_more':offset+limit<len(rows),'query':query,'kind_filter':kind}


def resolve_review_ids(store,wid,value):
    """Resolve only a unique exact, product-generated RNA entity identifier.

    No fuzzy label, sequence resemblance or context-dependent choice. Preserve
    the original response and record every mechanical alias in the saved review.
    """
    resolved=deepcopy(value);mappings=[]
    pool=catalog(store,wid)['options'];known={r['option_id'] for r in pool}
    for row in resolved.get('assessments',[]):
        key=row['option_id']
        if key in known or not re.fullmatch(r'guide_[0-9a-f]{20}',key):continue
        matches=[r for r in pool if r['kind']=='rna_candidate' and r.get('entity_id')==key]
        if len(matches)!=1:
            raise ValueError('가이드 ID에 대응하는 선택지가 없거나 여러 참조에 있습니다. inspect_discovery_options의 정확한 option_id를 선택해 주세요.')
        target=matches[0]
        mappings.append({'returned_entity_id':key,'resolved_option_id':target['option_id'],
                         'basis':'unique_exact_product_generated_rna_entity_id',
                         'original_sources':target['sources']})
        row['option_id']=target['option_id']
    return resolved,mappings


def validate_review(store,wid,rev,value):
    jsonschema.validate(value,REVIEW)
    state=store.snapshot(wid)
    if state['rev']!=rev:
        from .store import Conflict
        raise Conflict('연구 조건이 바뀌어 이전 추천으로 갱신하지 않았습니다.')
    pool={x['option_id']:x for x in catalog(store,wid,state)['options']}
    known={a['id'] for a in state['artifacts']}
    new_ids=[]
    for row in value['new_options']:
        key=row['option_id'];new_ids.append(key)
        if not key.startswith(row['kind']+':') or not row['label'].strip() or not row['description'].strip():
            raise ValueError('새 기전 ID는 mechanism:이름, 접근 ID는 approach:이름 형식이어야 하며 설명이 필요합니다.')
        if not row['source_ids'] or not set(row['source_ids'])<=known:
            raise ValueError('기전/접근을 제안한 실제 자료를 연결해 주세요.')
        if key in pool and (pool[key]['kind']!=row['kind'] or pool[key]['label']!=row['label']):
            raise ValueError('기존 선택지의 종류/이름을 다른 개념으로 덮어쓰지 마세요. 새 ID가 필요합니다.')
        pool[key]=row
    if len(new_ids)!=len(set(new_ids)):raise ValueError('새 선택지 ID가 중복됐습니다.')
    seen=set();ranks=set()
    for row in value['assessments']:
        key=row['option_id']
        if key not in pool or key in seen:raise ValueError('평가한 선택지의 정확한 option_id를 중복 없이 사용해 주세요. 전체 후보를 모두 평가할 필요는 없습니다.')
        seen.add(key)
        sources=row['support_source_ids']+row['challenge_source_ids']
        if not set(sources)<=known:raise ValueError('선택지 평가의 출처가 이 연구에 없습니다.')
        if row['status']=='recommended' and not row['support_source_ids']:
            raise ValueError('추천에는 검토한 지지 자료가 필요합니다. 없으면 근거 확인 대상으로 남기세요.')
        if not row['reason'].strip() or not row['next_action'].strip():raise ValueError('평가 이유와 다음 행동이 필요합니다.')
        target=row.get('targets_mechanism')
        if target:
            if target['option_id'] not in pool:
                raise ValueError('후보가 겨냥한 기전의 정확한 option_id를 사용해 주세요.')
            # The pair table prints this in the mechanism column, so a link to a molecule or a
            # source would render that option's label as though it were a mechanism.
            from .research_loop import PROFILE_KINDS
            if not target['option_id'].startswith(PROFILE_KINDS):
                raise ValueError('후보는 기전·접근만 겨냥할 수 있습니다. 다른 후보나 자료는 연결하지 마세요.')
            if not target['reason'].strip():
                raise ValueError('후보를 그 기전에 연결한 이유가 필요합니다.')
        if row['priority'] is not None:
            rank=(row['comparison_group'],row['priority'])
            if not row['comparison_group'].strip() or rank in ranks:raise ValueError('같은 비교 안의 우선순위가 중복됐거나 비교 기준이 없습니다.')
            ranks.add(rank)
    return {'updated_options':len(seen),'new_options':len(new_ids)}


def record_review(store,wid,rev,jid,value):
    value,mappings=resolve_review_ids(store,wid,value)
    counts = validate_review(store,wid,rev,value)
    from .store import dump
    from .research_loop import verify_basis
    checks=verify_basis(store,wid,value)
    aid=store.add_artifact(wid,'선택지 검토 · '+value['question'][:100],'discovery_review',dump(value).encode(),
        {'based_rev':rev,'job_id':jid,'semantic_type':'model_assessment_not_scientific_validation','omission_deletes_options':False,'option_id_resolution':mappings,'basis_check':checks},bump=False)
    answer={'status':'recorded','artifact_id':aid,**counts,
            'all_other_options_retained':True,'scientific_validation':False}
    if checks:
        # Mechanical quotation/count/link results only; the record above is kept as submitted.
        answer['basis_check']=checks
    return answer


def overview(store,wid,state=None,*,for_ui=False):
    value=catalog(store,wid,state)
    fields=('modality','role','identity','identity_links')
    if for_ui:
        fields+=('candidate_artifact_id','entity_id','origin','structure_status')
    def project(x):
        return {'option_id':x['option_id'],'label':x['label'],'kind':x['kind'],
                'assessment':x['assessment'],**{k:x[k] for k in fields if k in x}}
    recommended=[project(x) for x in value['options'] if x['review_status']=='recommended']
    # An option losing its recommendation must not vanish from the main rationale.
    # Preserve the current assessment verbatim; this is not a second ranking.
    reconsidered=[project(x)
                  for x in value['options'] if x['review_status'] in ('needs_evidence','deferred')
                  and any(a['status']=='recommended' for a in x['assessments'][:-1])]
    # These IDs are needed for candidate-to-mechanism links even when no path
    # has ever been recommended. Preserve the assessed and unassessed paths.
    pathways=[{k:x[k] for k in ('option_id','label','kind','description','sources','assessment')}
              for x in value['options'] if x['kind'] in ('mechanism','approach')]
    result={'total':value['total'],'counts':value['counts'],'reviewed':value['reviewed'],
            'selected':value['selected'],'rna_search_coverage':value['rna_search_coverage'],'recommendations':recommended,'unsearched_scope':value['unsearched_scope'],'scope_review':value['scope_review'],
            'reconsidered_options':reconsidered,
            'mechanisms_and_approaches':pathways,
            'read_with':'inspect_discovery_options(query,kind,offset,limit); all discovered options retained, including unreviewed and nonrecommended'}
    if for_ui:
        # Pending evidence is a review outcome, not an absent candidate. These
        # repeated rows support the screen without enlarging the model request.
        result['reviewed_options']=[project(x) for x in value['options'] if x['assessment'] is not None]
        result['selected_option']=next((project(x) for x in value['options']
            if value['selected'] and x['option_id']==value['selected']['option_id']),None)
    return result


def choice_command(store,wid,body,proposal=False):
    if type(body.get('expected_rev')) is not int or not isinstance(body.get('command_id'),str):
        raise ValueError('선택 요청의 버전 또는 ID가 없습니다.')
    if type(body.get('review_requested',False)) is not bool:
        raise ValueError('후속 검토 선택을 확인해 주세요.')
    with store.connect() as db:
        prior=db.execute('SELECT payload,result FROM commands WHERE workspace=? AND id=?',(wid,body['command_id'])).fetchone()
    if prior:
        saved=json.loads(prior['payload']);old=saved.get('discovery_proposal') if proposal else saved.get('discovery_selection')
        requested_label=str(body.get('label','')).strip();requested_text=str(body.get('text','')).strip()
        if not old or saved.get('review_requested',False)!=body.get('review_requested',False) or (proposal and (old['label']!=requested_label or old['detail']!=requested_text)) or (not proposal and (old['option_id']!=body.get('option_id') or old['reason']!=requested_text)):
            from .store import Conflict
            raise Conflict('같은 요청 ID에 다른 선택이 들어왔습니다.')
        return json.loads(prior['result'])
    if proposal:
        label=str(body.get('label','')).strip()
        if not label or len(label)>240:raise ValueError('검토하고 싶은 경로를 240자 이내로 입력해 주세요.')
        detail=str(body.get('text','')).strip()
        command={'kind':'message','text':'연구자 새 경로 제안: '+label+('\n'+detail if detail else '')+
            '\n기존 추천/원근거를 보존하고, 이 제안의 근거·반대 조건·필요한 확인을 검토하여 다음 작업에 반영해 주세요.',
            'discovery_proposal':{'label':label,'detail':detail,'verification':'not_yet_reviewed'}}
    else:
        pool={x['option_id']:x for x in catalog(store,wid)['options']}
        key=body.get('option_id')
        if key not in pool:raise ValueError('발견 목록에서 선택할 항목을 확인해 주세요.')
        item=pool[key];reason=str(body.get('text','')).strip()
        command={'kind':'message','text':'연구자 선택: '+item['label']+' ('+key+')'+('\n선택 이유: '+reason if reason else '')+
            '\n기존 추천을 지우지 말고 이 경로를 우선 검토해 실제 다음 조회/계산으로 진행해 주세요. 선택은 효능 검증을 뜻하지 않습니다.',
            'discovery_selection':{'option_id':key,'label':item['label'],'reason':reason,
                'sources':item['sources'],'assessment_at_selection':item['assessment']}}
    if body.get('review_requested',False):
        command['review_requested']=True
    return store.command(wid,body['expected_rev'],body['command_id'],command)


def anchored_figures(store, wid, basis, limit=3, cache=None,
                     support_source_ids=(), challenge_source_ids=()):
    """Figures from articles explicitly cited by a mechanism clause or assessment.

    Only files already in the cache are offered: a screen render must not start a download, and a
    figure that is not there is simply absent rather than a broken image. Clause anchors take
    precedence. Direct support/challenge article references retain their article-level role;
    an unset clause basis does not imply that no source was cited.

    This does not claim the figure depicts the mechanism. Nothing here reads the image; it is the
    paper's own figure, named as such, next to the clause that cites that paper.
    """
    from .article_figures import index_for
    cache = Path(cache or Path(__file__).resolve().parents[1] / '.figure-cache')
    if not cache.is_dir():
        return []
    found, seen = [], set()
    links = []
    for position, clause in enumerate((basis or {}).get('clauses') or []):
        artifact_id = (clause.get('anchor') or {}).get('artifact_id')
        links.append((artifact_id, position, 'clause_source', None))
    # Actual assessments can cite a paper while leaving optional clause grades unset.
    # Preserve that weaker, article-level relation; do not manufacture a quote anchor.
    links += [(aid, None, 'assessment_source', 'support') for aid in support_source_ids or []]
    links += [(aid, None, 'assessment_source', 'challenge') for aid in challenge_source_ids or []]
    for artifact_id, position, link_kind, source_role in links:
        if not artifact_id or artifact_id in seen:
            continue
        seen.add(artifact_id)
        try:
            artifact = store.artifact(wid, artifact_id)
        except KeyError:
            continue
        if artifact['kind'] != 'article':
            continue
        value = json.loads(artifact['content'])
        if not isinstance(value.get('pmc_id'), str):
            continue
        for figure in index_for(value, value['pmc_id'], cache):
            name = next((f['file'] for f in figure['available'] if f['cached']), None)
            if not name:
                continue
            found.append({'artifact_id': artifact_id, 'file': name, 'clause_index': position,
                          'link_kind': link_kind, 'source_role': source_role,
                          'caption': figure.get('caption'), 'section': figure.get('section'),
                          'source_url': figure.get('source_url'),
                          'meaning': ('이 절을 앵커한 논문에 실린 그림입니다. ' if link_kind == 'clause_source' else
                                      '이 평가가 명시한 근거 논문에 실린 그림입니다. ') + '기전을 그린 것이라고 '
                                     '확인한 것이 아니며, 그림의 내용은 읽지 않았습니다.'})
            if len(found) >= limit:
                return found
    return found


CANDIDATE_KINDS = ('molecule', 'rna_candidate')


def candidate_structures_view(store, wid, state=None, limit=24, option_id=None):
    """The stored structure of each retained candidate, drawn, for the screen only.

    Kept out of `inspect` and out of `catalog` on purpose: those answer model requests, and a
    drawing there would spend context on something only a person can read. The candidate list on
    the roadmap needs the picture, so it asks for it here and nowhere else.

    Nothing is looked up: the SMILES is the one the record already stores, and a candidate whose
    record has no structure string is returned with its status rather than an invented drawing.
    """
    from .structure_depiction import attach
    root = Path(__file__).resolve().parents[1]
    value = catalog(store, wid, state)
    rows, seen = [], {}
    # A selected or assessed proposal must not be hidden behind the first 24 retrieved
    # compounds. The complete catalog remains in source order and is fully inspectable.
    candidates=sorted(value['options'],key=lambda o:(not o.get('selected'),
        o.get('assessment') is None,o.get('origin')!='generated_structure_proposal'))
    if option_id is not None:
        candidates = [option for option in candidates if option['option_id'] == option_id]
    for option in candidates:
        if option['kind'] not in CANDIDATE_KINDS or len(rows) >= limit:
            continue
        artifact_id = option.get('candidate_artifact_id')
        entity = option.get('entity_id')
        row = {'option_id': option['option_id'], 'candidate_id': entity, 'name': option['label'],
               'structure_status': option.get('structure_status')}
        if artifact_id and entity:
            if artifact_id not in seen:
                try:
                    seen[artifact_id] = json.loads(store.artifact(wid, artifact_id)['content'])
                except (KeyError, ValueError):
                    seen[artifact_id] = {}
            if option.get('candidate_row_locator'):
                stored=seen[artifact_id]
                try:
                    for part in option['candidate_row_locator']:
                        stored=stored[part]
                    if not isinstance(stored,dict) or stored.get('candidate_id')!=entity:
                        stored=None
                except (KeyError,IndexError,TypeError):
                    stored=None
            else:
                stored = next((r for r in (seen[artifact_id].get('rows') or [])
                               if isinstance(r, dict) and r.get('candidate_id') == entity), None)
            if stored:
                row = {**{k: v for k, v in stored.items() if k != 'depiction'}, **row}
        rows.append(row)
    if not rows:
        return {'status': 'no_candidates_retained', 'rows': [],
                'meaning': '구조를 그릴 후보가 이 연구에 아직 없습니다.'}
    drawn = attach({'rows': rows}, 'compound_candidates', root / '.structure-cache',
                   str(root / '.runtime/science/bin/python'), root)
    return {**drawn, 'status': 'computed', 'total_candidates': len(rows),
            'meaning': '기록된 구조 문자열을 그린 것입니다. 측정된 구조가 아니며 시료 동일성 확인도 아닙니다.'}



RANKED_KINDS = ('mechanism', 'approach')


def ranking_emptiness(options):
    """Which kind of empty stage 2 is, counted rather than guessed.

    A blank comparison screen hides its own cause. Nothing found, nothing reviewed and reviewed
    without axis values look identical to a reader, and the third is the one that happens: the
    model registers what it discovered and leaves the assessment list empty, so the screen has
    nothing to order and says so as if the evidence were the problem.
    """
    ranked = [o for o in options if o.get('kind') in RANKED_KINDS]
    reviewed = [o for o in ranked if o.get('assessment')]
    with_axes = [o for o in reviewed if isinstance((o.get('assessment') or {}).get('aspects'), dict)]
    counts = {'mechanism_options': len(ranked), 'reviewed': len(reviewed),
              'with_axis_values': len(with_axes)}
    if not ranked:
        return {**counts, 'reason': 'no_mechanism_options',
                'meaning': '아직 비교할 기전·접근이 발견되지 않았습니다. 조회를 더 하면 여기에 쌓입니다.'}
    if not reviewed:
        return {**counts, 'reason': 'none_reviewed',
                'meaning': f'기전·접근 {len(ranked)}개를 발견했지만 아직 검토된 것이 없습니다. '
                           '발견은 검토가 아닙니다.'}
    return {**counts, 'reason': 'reviewed_without_axis_values',
            'meaning': f'검토한 기전·접근 {len(reviewed)}개 중 축 값을 기록한 것이 없어 계산할 '
                       '순서가 없습니다. 근거가 우열을 가리지 못했다는 뜻이 아니라, 우열을 가릴 '
                       '값이 아직 기록되지 않았다는 뜻입니다.'}


def mechanism_ranking_view(store, wid, state=None, with_support=False):
    """The computed partial order over reviewed mechanisms and approaches, for the screen only.

    Kept out of overview() on purpose: that feeds the model context, and a computed order there
    invites the model to chase the order instead of reporting what the evidence says. The model's
    own priority is reported beside this, never replaced by it.
    """
    from .mechanism_ranking import compare_with_model_priority, rank
    value = catalog(store, wid, state)
    graded, assessments = [], []
    for option in value['options']:
        current = option.get('assessment')
        if not current or option['kind'] not in ('mechanism', 'approach'):
            continue
        if not isinstance(current.get('aspects'), dict):
            continue
        graded.append({'option_id': option['option_id'], 'aspects': current['aspects'],
                       'challenge_source_ids': current.get('challenge_source_ids') or [],
                       'support_source_ids': current.get('support_source_ids') or [],
                       'challenge_applies': current.get('challenge_applies'),
                       'targets_mechanism': current.get('targets_mechanism'),
                       'label': option['label'], 'kind': option['kind'],
                       'basis': current.get('basis'), 'status': current.get('status'),
                       'basis_check': current.get('basis_check'),
                       'reason': current.get('reason'), 'priority': current.get('priority'),
                       'comparison_group': current.get('comparison_group'),
                       'sources': option.get('sources', []),
                       'based_rev': current.get('based_rev'),
                       'current_conditions': current.get('current_conditions')})
        if current.get('priority') is not None and current.get('comparison_group'):
            assessments.append({'option_id': option['option_id'], 'priority': current['priority'],
                                'comparison_group': current['comparison_group']})
    if not graded:
        empty = ranking_emptiness(value['options'])
        return {'status': 'no_axis_values_recorded', 'rows': [], 'ranked': 0,
                'reviewed_options': value['reviewed'], 'total_options': value['total'],
                'emptiness': empty, 'meaning': empty['meaning']}
    if with_support:
        # Advisory only, and only when the screen asks: the first run loads a model. It never
        # blocks a judgement and never changes what the model recorded.
        from .entailment_support import annotate
        root = Path(__file__).resolve().parents[1]
        annotate([{'basis': row['basis'], 'check': row.get('basis_check')} for row in graded
                  if isinstance(row.get('basis'), dict)],
                 root / '.entailment-support-cache', root)
    ranking = rank(graded)
    detail = {row['option_id']: row for row in graded}
    rows = [{**row, **{k: detail[row['option_id']][k] for k in
                       ('label', 'kind', 'basis', 'status', 'reason', 'priority',
                        'comparison_group', 'sources', 'based_rev', 'current_conditions')},
             'figures': anchored_figures(store, wid, detail[row['option_id']].get('basis'),
                 support_source_ids=detail[row['option_id']].get('support_source_ids'),
                 challenge_source_ids=detail[row['option_id']].get('challenge_source_ids'))}
            for row in ranking['rows']]
    paired = mechanism_candidate_pairs(store, wid, ranking, state)
    return {**ranking, 'status': 'computed', 'rows': rows, 'ranked': len(graded),
            'mechanism_candidate_pairs': paired,
            'reviewed_options': value['reviewed'], 'total_options': value['total'],
            'model_priority_comparison': compare_with_model_priority(ranking, assessments)
            if assessments else None}


def mechanism_candidate_pairs(store, wid, ranking, state=None):
    """(mechanism, candidate) pairs, shown as their two parts rather than one invented score.

    A pair exists only where a candidate assessment states the mechanism it acts on. The two
    orders stay separate and visible: the mechanism's computed tier, and the candidate's recorded
    priority inside its own comparison group. Nothing multiplies them into a probability, because
    the two numbers do not share a scale and no evidence relates them.
    """
    value = catalog(store, wid, state)
    tiers = {row['option_id']: row['tier'] for row in ranking.get('rows', [])}
    labels = {option['option_id']: option['label'] for option in value['options']}
    pairs = []
    for option in value['options']:
        current = option.get('assessment') or {}
        target = current.get('targets_mechanism')
        if not target or target.get('option_id') not in labels:
            continue
        pairs.append({
            'candidate_id': option['option_id'], 'candidate_label': option['label'],
            'candidate_kind': option['kind'], 'candidate_priority': current.get('priority'),
            'candidate_comparison_group': current.get('comparison_group'),
            'candidate_status': current.get('status'), 'candidate_reason': current.get('reason'),
            'mechanism_id': target['option_id'], 'mechanism_label': labels[target['option_id']],
            'mechanism_tier': tiers.get(target['option_id']),
            'link_reason': target.get('reason'),
            'sources': option.get('sources', [])})
    # Sort by the mechanism's computed place, then the candidate's own recorded place. This is an
    # ordering of two separate records read together, not a combined score.
    pairs.sort(key=lambda p: (p['mechanism_tier'] if p['mechanism_tier'] is not None else 10 ** 9,
                              p['candidate_priority'] if p['candidate_priority'] is not None else 10 ** 9,
                              p['candidate_label']))
    return {'pairs': pairs, 'linked': len(pairs),
            'meaning': 'Each row shows a mechanism place and a candidate place as recorded, side '
                       'by side. They are not multiplied and no joint probability is formed: the '
                       'two orders come from different comparisons and nothing measured relates '
                       'them. A candidate appears only where its record names the mechanism.'}
