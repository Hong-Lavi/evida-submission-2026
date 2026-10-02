// Read-only presentation of the recorded workflow. No inferred causal edges,
// approval, stage completion, or scientific score is produced here.
const ROADMAP_STAGES = [
  {id:'goal',title:'구조화된 질문과 목표',hint:'무엇을 바꾸려는가'},
  {id:'mechanisms',title:'기전과 접근',hint:'어떤 방향을 검토하는가',kinds:['mechanism','target','approach','researcher_proposal']},
  {id:'candidates',title:'후보 발굴',hint:'무엇을 실제로 비교하는가',kinds:['source_candidate','molecule','rna_candidate','rna']},
  {id:'evidence',title:'근거와 계산',hint:'어디까지 확인했는가'},
  {id:'next',title:'EVIDA 실험 권고',hint:'다음에 무엇을 해볼까'},
];
// JSON objects have no key order; arrays retain their recorded order. Missing is
// distinct from explicit null. This compares records, not scientific meaning.
function roadmapSame(a,b){
  if(a===b)return true;
  if(a===null||b===null||typeof a!=='object'||typeof b!=='object')return false;
  if(Array.isArray(a)!==Array.isArray(b))return false;
  const ak=Object.keys(a),bk=Object.keys(b);
  return ak.length===bk.length&&ak.every(k=>Object.hasOwn(b,k)&&roadmapSame(a[k],b[k]));
}
function roadmapOptionKind(x){return x.kind??String(x.option_id??'').split(':')[0]}
function roadmapSummary(value,limit=70){
  const text=String(value??'').replace(/\s+/g,' ').trim();
  return text.length>limit?text.slice(0,limit)+'…':text;
}
function roadmapRecordDiff(before,after,fields){
  const valid=rows=>Array.isArray(rows)&&rows.every(x=>x&&typeof x.id==='string'&&x.id)&&new Set(rows.map(x=>x.id)).size===rows.length;
  if(!valid(before??[])||!valid(after??[]))return [{id:'ambiguous-record-ids',status:'unavailable',fields:[],before,after,reason:'항목 ID가 없거나 중복되어 정확히 대응할 수 없습니다.'}];
  const old=new Map((before??[]).map(x=>[x.id,x])),now=new Map((after??[]).map(x=>[x.id,x]));
  return [...new Set([...old.keys(),...now.keys()])].map(id=>{
    const a=old.get(id),b=now.get(id);
    const changed=fields.filter(key=>!roadmapSame(a?.[key],b?.[key]));
    return {id,before:a??null,after:b??null,fields:changed,
      status:!a?'added':!b?'omitted':changed.length?'changed':'unchanged'};
  });
}
function roadmapClaimRecords(decision){
  const rows=[];
  for(const h of decision?.research_loop?.hypotheses??[]){
    rows.push({...h,id:h.id,claim_id:h.id,hypothesis_id:h.id,level:'hypothesis'});
    for(const [level,items] of [['part',h.assessment_scope?.parts],['alternative',h.conditional_alternatives]]){
      for(const item of items??[])rows.push({...item,id:typeof h.id==='string'&&typeof item.id==='string'?`${h.id}/${level}/${item.id}`:null,claim_id:item.id,hypothesis_id:h.id,level});
    }
  }
  return rows;
}
function roadmapAssessmentPublication(snapshot,assessment){
  if(!assessment)return 'unreviewed';
  const artifact=(snapshot.artifacts??[]).find(a=>a.id===assessment.artifact_id);
  const job=(snapshot.jobs??[]).find(j=>j.id===artifact?.meta?.job_id);
  if(!job)return 'unknown';
  if(['succeeded','reused'].includes(job.status))return 'returned';
  return ['queued','running'].includes(job.status)?'draft':'unfinished';
}
function buildResearchRoadmap(snapshot,goalRows=[],history={status:'unread'}){
  const s=snapshot??{},d=s.discovery??{},dec=s.decision,loop=dec?.research_loop;
  const current=!!dec&&s.decision_rev===s.rev;
  const publication=(s.events??[]).filter(e=>e.kind==='decision_published').at(-1);
  const priorLink=(s.events??[]).find(e=>e.kind==='hypothesis_wording_compared'&&e.body.receipt_id===s.decision_id)?.body.reference;
  const previous=history.status==='ready'&&history.workspaceId===s.id&&history.currentId===s.decision_id&&history.previousId===priorLink?.decision_id?history.decision:null;
  const proposals=[...(d.reviewed_options??[]),...(d.recommendations??[]),...(d.reconsidered_options??[]),
    ...(d.selected_option?[d.selected_option]:[])];
  const seen=new Set();const options=proposals.filter(x=>!seen.has(x.option_id)&&seen.add(x.option_id));
  const selected=d.selected??null;
  const events=s.events??[],changes=s.input_changes??{},after=changes.after_event??0;
  const addedInputs=events.filter(e=>e.seq>after&&['message','observation','correction','intent_edit'].includes(e.kind));
  const intentChanged=addedInputs.some(e=>e.kind==='intent_edit');
  const hasNewInput=changes.phase==='pending_review'&&!!(changes.messages?.length||changes.intent_edits?.length||changes.sources?.length);
  const hypotheses=loop?.hypotheses??[],checks=loop?.next_checks??[];
  const running=(s.jobs??[]).some(j=>j.kind==='planner'&&j.based_rev===s.rev&&['queued','running'].includes(j.status));
  const diffs=previous?{
    goals:roadmapRecordDiff(previous.intent_records,dec.intent_records,['label','text','origin','source_refs']),
    hypotheses:roadmapRecordDiff(previous.research_loop?.hypotheses,hypotheses,['statement','expected_observation','assessment','rationale','evidence','assessment_scope','conditional_alternatives']),
    checks:roadmapRecordDiff(previous.research_loop?.next_checks,checks,['question','purpose','hypothesis_ids','operation','possible_outcomes','outcome_links','scope_targets']),
    claims:roadmapRecordDiff(roadmapClaimRecords(previous).filter(x=>x.level!=='hypothesis'),roadmapClaimRecords(dec).filter(x=>x.level!=='hypothesis'),['statement','expected_observation','assessment','rationale','evidence','conditions','prediction','prediction_origin','observable','part_ids','relations','unknowns']),
  }:null;
  const labelChanged=items=>items?.some(x=>['added','omitted','changed'].includes(x.status));
  const relevant=(kinds)=>options.filter(x=>kinds.includes(roadmapOptionKind(x)));
  const nodes=ROADMAP_STAGES.map(stage=>{
    const n={...stage,summary:'아직 기록 전',status:'기록 대기',mark:'empty',change:null};
    if(stage.kinds){
      n.options=relevant(stage.kinds);n.count=stage.kinds.reduce((sum,k)=>sum+(d.counts?.[k]??0),0);
      n.recommended=n.options.filter(x=>x.assessment?.current_conditions===true&&x.assessment?.status==='recommended'&&roadmapAssessmentPublication(s,x.assessment)==='returned');
      n.reviewed=n.options.filter(x=>x.assessment&&roadmapAssessmentPublication(s,x.assessment)==='returned');
      n.drafts=n.options.filter(x=>['draft','unfinished'].includes(roadmapAssessmentPublication(s,x.assessment)));
      const key=selected&&roadmapOptionKind(selected);
      n.selected=selected&&stage.kinds.includes(key)?selected:null;
      const selectedKnown=selected&&n.options.find(x=>x.option_id===selected.option_id);
      if(!n.selected&&selectedKnown)n.selected=selected;
      const found=stage.id==='mechanisms'?'기전·접근':'후보';
      n.summary=n.selected?n.selected.label
        :n.recommended.length?`${n.recommended[0].label}${n.recommended.length>1?` 외 추천 ${n.recommended.length-1}개`:''}`
        :n.reviewed.length?`${n.reviewed[0].label} · ${n.reviewed[0].assessment.status==='needs_evidence'?'근거 확인 필요':n.reviewed[0].assessment.status==='deferred'?'현재 보류':'검토 기록 있음'}`
        :n.count?`${found} ${n.count}개를 찾았고 아직 순위를 매기지 않았습니다`:`${found}을 아직 찾지 못했습니다`;
      n.status=n.selected?'연구자 선택':n.recommended.length?`추천 ${n.recommended.length}개`:n.reviewed.length?`검토 기록 ${n.reviewed.length}개`:n.count?`찾은 것 ${n.count}개`:'아직 없음';
      n.mark=n.selected?'selected':n.recommended.length?'proposed':n.count?'recorded':'empty';
      if(!n.selected&&!n.recommended.length&&n.drafts.length){n.status=`검토 중 ${n.drafts.length}개`;n.mark='draft'}
      if(n.selected?.state_rev<s.rev||(!n.recommended.length&&!n.drafts.length&&n.options.some(x=>x.assessment?.current_conditions===false))){n.status='이전 조건의 판단';n.mark='earlier'}
      if(addedInputs.some(e=>stage.kinds.includes(roadmapOptionKind(e.body.discovery_selection??{}))))n.change='선택 추가';
      if(stage.id==='mechanisms'&&previous&&!roadmapSame(previous.alternatives,dec.alternatives))n.change='비교안 변경';
    }
    if(stage.id==='goal'){
      const goal=goalRows.find(r=>r.origin==='researcher')??goalRows[0];
      const first=events.find(e=>e.kind==='message');
      n.summary=goal?.text??first?.body.text??'질환과 바꾸려는 결과를 알려주세요';
      n.status=goal?(goal.origin==='researcher'?'연구자가 적은 목표':goal.origin==='unknown'?'조건 미확인':'모델이 정리한 목표'):first?'원 요청만 있음':'입력 대기';
      n.mark=goal||first?'recorded':'empty';
      if(intentChanged)n.change='의도 수정';else if(labelChanged(diffs?.goals))n.change='조건 기록 변경';
    }
    if(stage.id==='evidence'){
      n.summary=dec?`가설 ${hypotheses.length}개와 그 근거·적용 조건`:s.artifacts?.length?`자료 ${s.artifacts.length}개를 모았고 해석 전입니다`:'근거를 찾고 계산 결과를 대조합니다';
      n.status=dec?(current?`가설 ${hypotheses.length}개`:'이전 판단'):s.artifacts?.length?`자료 ${s.artifacts.length}개 · 판단 전`:'확인 전';
      n.mark=dec?(current?'recorded':'earlier'):s.artifacts?.length?'recorded':'empty';
      if(labelChanged(diffs?.hypotheses))n.change='판단 기록 변경';
      else if(changes.sources?.length)n.change='자료 추가';
    }
    if(stage.id==='next'){
      n.summary=checks[0]?.question??dec?.next_actions?.[0]??'근거를 비교한 뒤 다음 확인을 제안합니다';
      n.status=checks.length?(current?`제안 ${checks.length}개`:'이전 조건의 제안'):dec?.next_actions?.length?(current?'후속 제안':'이전 조건의 제안'):'아직 제안 전';
      n.mark=dec?(current?'proposed':'earlier'):'empty';
      const run=checks.length&&(s.research_checks??[]).find(x=>x.decision_id===s.decision_id&&x.check_id===checks[0].id);
      const job=run&&(s.jobs??[]).find(j=>j.id===run.job_id);
      if(job){n.jobStatus=job.status;n.status=['running','queued'].includes(job.status)?'확인 실행 중':['succeeded','reused'].includes(job.status)?'결과 해석 확인':'실행 상태 확인'}
      if(labelChanged(diffs?.checks)||previous&&!roadmapSame(previous.next_actions,dec.next_actions))n.change='다음 확인 변경';
    }
    if(running&&!current&&stage.id!=='goal'&&n.mark==='empty'){n.status='조사 중 · 판단 전';n.mark='working'}
    return n;
  });
  // A result the researcher entered is the point of the loop, so the judgement that followed it
  // should not be two clicks away. This only reports order of record: it does not claim the
  // observation caused the change.
  const lastObservation=(s.events??[]).filter(e=>e.kind==='observation').at(-1);
  const answeredObservation=lastObservation&&Number.isInteger(publication?.seq)
    &&publication.seq>lastObservation.seq?lastObservation:null;
  return {nodes,current,running,hasNewInput,selected,previous,priorLink,diffs,publication,answeredObservation,
    currentDecisionId:s.decision_id??null,historyStatus:previous?'ready':history.status==='ready'?'unavailable':history.status,
    changedNodes:nodes.filter(n=>n.change).map(n=>n.id)};
}

// Match by the exact result artifact, never by a reused NC number or array order.
function currentResearchActivity(snapshot){
  const jobs=snapshot?.jobs??[], active=j=>['queued','running'].includes(j.status);
  const recent=rows=>[...rows].sort((a,b)=>String(b.updated??b.created??'').localeCompare(String(a.updated??a.created??'')));
  const direct=recent(jobs.filter(j=>j.kind==='research_check'&&active(j)&&j.request?.check?.question))[0];
  if(direct)return {question:direct.request.check.question,checkJobId:direct.id,
    status:direct.status==='queued'?'선택한 확인 대기 중':'선택한 확인 실행 중'};
  const publication=(snapshot.events??[]).find(e=>e.kind==='decision_published'&&e.body?.receipt_id===snapshot.decision_id);
  const supersededPause=planner=>{
    const stopped=(snapshot.events??[]).filter(e=>e.kind==='job_finished'&&e.body?.job_id===planner.id&&e.body?.status==='paused').at(-1);
    // Publication need not increase the input revision. Match the actual receipt
    // and recorded event order; a later paused review must still be visible.
    return Number.isInteger(publication?.seq)&&Number.isInteger(stopped?.seq)&&stopped.seq<publication.seq;
  };
  for(const planner of recent(jobs.filter(j=>j.kind==='planner'&&(active(j)||j.status==='paused'&&j.based_rev===snapshot.rev&&!supersededPause(j))))){
    const sources=new Set((planner.request?.source_views??[]).map(v=>v.artifact_id));
    const check=recent(jobs.filter(j=>j.kind==='research_check'&&sources.has(j.output_id)&&j.request?.check?.question))[0];
    if(check)return {question:check.request.check.question,checkJobId:check.id,plannerJobId:planner.id,
      status:planner.status==='paused'?'해석 보류 · 원기록 보존':check.status==='failed'?'확인 실패 기록 검토 중':'새 결과 검토 중'};
  }
  return null;
}

// Which recorded tools were run, returned to the model, and cited by the published
// judgment. "Returned" is delivery, not reading; "cited" is a recorded link in the
// decision, not scientific validation. Results without a job (later re-runs or
// imports) and failed jobs without a result both stay visible.
const ROADMAP_NON_TOOL_JOBS=['planner','research_check','coordinator_review','execution_review','explanation'];
function roadmapCitedSources(decision){
  const ids=new Set((decision?.evidence_refs??[]).map(x=>String(x).split('#')[0]));
  for(const c of roadmapClaimRecords(decision))for(const e of c.evidence??[])if(e?.source_id)ids.add(String(e.source_id).split('#')[0]);
  return ids;
}
function roadmapArgumentText(args,limit=90){
  if(!args||typeof args!=='object')return '';
  const pairs=Object.entries(args).filter(([,v])=>v!==null&&v!==undefined&&v!=='').map(([k,v])=>`${k}: ${typeof v==='object'?JSON.stringify(v):v}`);
  return roadmapSummary(pairs.join(', '),limit);
}
function roadmapToolUsage(snapshot){
  const s=snapshot??{},artifacts=s.artifacts??[],jobs=s.jobs??[];
  const current=!!s.decision&&s.decision_rev===s.rev;
  const cited=roadmapCitedSources(s.decision);
  const returned=new Set();
  for(const a of artifacts)if(a.kind==='tool_reading'){
    const m=a.meta??{};
    for(const id of [m.source_artifact_id,m.arguments?.artifact_id,...(m.source_artifact_ids??[])])if(id)returned.add(id);
  }
  for(const j of jobs)for(const v of j.request?.source_views??[])if(v?.artifact_id)returned.add(v.artifact_id);
  const byOutput=new Map(jobs.filter(j=>j.output_id).map(j=>[j.output_id,j]));
  const groups=new Map();
  const group=kind=>{if(!groups.has(kind))groups.set(kind,{kind,runs:0,statuses:{},items:[],returned:0,cited:0});return groups.get(kind)};
  for(const a of artifacts){
    if(!a.meta?.result_status||['model_receipt','tool_reading'].includes(a.kind))continue;
    const g=group(a.kind),job=byOutput.get(a.id),status=a.meta.result_status;
    const item={id:a.id,status,input:roadmapArgumentText(a.meta.arguments??job?.request),created:a.created??null,
      jobId:job?.id??null,returned:returned.has(a.id),cited:cited.has(a.id)};
    g.runs++;g.statuses[status]=(g.statuses[status]??0)+1;g.items.push(item);
    if(item.returned)g.returned++;if(item.cited)g.cited++;
  }
  const results=new Set(artifacts.map(a=>a.id));
  for(const j of jobs){
    if(ROADMAP_NON_TOOL_JOBS.includes(j.kind)||(j.output_id&&results.has(j.output_id)))continue;
    const g=group(j.kind);g.runs++;g.statuses[j.status]=(g.statuses[j.status]??0)+1;
    g.items.push({id:null,status:j.status,input:roadmapArgumentText(j.request),created:j.created??null,jobId:j.id,returned:false,cited:false});
  }
  const models={};
  for(const a of artifacts)if(a.kind==='model_receipt'){const m=a.meta?.requested_model??'unknown';models[m]=(models[m]??0)+1}
  const tools=[...groups.values()].sort((a,b)=>b.cited-a.cited||b.returned-a.returned||b.runs-a.runs||a.kind.localeCompare(b.kind));
  return {tools,current,runs:tools.reduce((n,t)=>n+t.runs,0),
    returned:tools.reduce((n,t)=>n+t.returned,0),cited:tools.reduce((n,t)=>n+t.cited,0),
    citedOutsideTools:[...cited].filter(id=>!artifacts.some(a=>a.id===id&&a.meta?.result_status)).length,
    modelCalls:Object.entries(models).map(([model,count])=>({model,count})).sort((a,b)=>b.count-a.count)};
}

// What the running planner has actually recorded so far: its returned tool calls,
// completed model calls and the notes it saved before the latest operation. The
// notes are provisional working text, not findings or a judgment.
function roadmapLiveProgress(snapshot,nowMs=Date.now()){
  const s=snapshot??{},jobs=s.jobs??[];
  const planner=[...jobs].reverse().find(j=>j.kind==='planner'&&j.based_rev===s.rev&&['queued','running'].includes(j.status));
  if(!planner)return null;
  const mine=a=>a.meta?.job_id===planner.id;
  const functions={};
  for(const r of (s.artifacts??[]).filter(a=>a.kind==='tool_reading'&&mine(a))){const f=r.meta?.function??'unknown';functions[f]=(functions[f]??0)+1}
  const started=Date.parse(planner.created);
  const notes=s.research_progress?.job_id===planner.id?s.research_progress.notes:null;
  return {jobId:planner.id,status:planner.status,started:planner.created,
    elapsedMinutes:Number.isFinite(started)?Math.max(0,Math.floor((nowMs-started)/60000)):null,
    completedCalls:(s.artifacts??[]).filter(a=>a.kind==='model_receipt'&&mine(a)).length,
    functions,nextGoal:notes?.next_goal??null,findings:(notes?.findings??[]).length};
}
