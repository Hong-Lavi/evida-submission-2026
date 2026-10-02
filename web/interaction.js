// An explanation has its own saved snapshot and never edits research conditions.
const explanationDrafts = new Map();
let explanationSending = false;
document.addEventListener('input', event => {
  if(event.target.id === 'explanation-question' && state) explanationDrafts.set(state.id,event.target.value);
});

function publishedFollowthrough(current,request){
  if(!request||current.decision_rev!==current.rev||request.requested_rev>current.decision_rev)return null;
  const requestedJob=current.jobs.find(j=>j.id===request.job_id);
  if(request.status==='pending'||['queued','running'].includes(requestedJob?.status))return null;
  const artifact=current.artifacts.find(a=>a.id===current.decision_id&&a.kind==='decision_proposal');
  const job=artifact?.meta?.job_id?current.jobs.find(j=>j.id===artifact.meta.job_id):null;
  if(!job||job.kind!=='planner'||job.status!=='succeeded'||job.based_rev!==current.rev||artifact.meta.based_rev!==current.rev)return null;
  if(job.id!==request.job_id&&![job.request?.resume_from_job,job.request?.reviewed_source_job].includes(request.job_id))return null;
  // A later request at the same revision must not inherit an older completion.
  const published=Date.parse(artifact.created),requested=Date.parse(request.created);
  if(!Number.isFinite(published)||!Number.isFinite(requested)||published<requested)return null;
  return {job_id:job.id,recovered_from_other_job:job.id!==request.job_id};
}

// Citations belong to the explanation's saved snapshot, never today's event list.
function explanationArtifactLinks(answer){
 const refs=(answer.evidence_refs??[]).filter(ref=>typeof ref==='string'&&ref.startsWith('art_'));
 return sourceLinks(refs);
}
function explanationParagraphs(value){
 const text=String(value??''),segmenter=typeof Intl.Segmenter==='function'?new Intl.Segmenter('ko',{granularity:'sentence'}):null;
 // Preserve each character, including existing newlines and numeric punctuation.
 const lines=text.match(/[^\r\n]*(?:\r\n|\r|\n|$)/g)?.filter(Boolean)??[];
 return lines.flatMap(line=>segmenter?[...segmenter.segment(line)].map(x=>x.segment):[line]);
}
function explanationInlineText(value){
 // Consume the whole generated-candidate token before artifact linking. A suffix,
 // different source, or absent current candidate must never resolve by prefix.
 return String(value).split(/(\bmolecule:generated:[A-Za-z0-9_:./-]+)/g).map(part=>{
  if(!part.startsWith('molecule:generated:'))return judgmentText(part);
  const matches=candidateOptions().filter(item=>item.option_id===part);
  const item=matches.length===1?matches[0]:null,name=item?candidateDisplayName(item):'';
  return name?button('discovery-detail',esc(name),`data-id="${esc(part)}" aria-label="${esc(name)} · 후보 상세"`,'inline-source-link'):
   '<span class="small muted">후보 확인 필요 · 저장된 설명 원문 참조</span>';
 }).join('');
}
function explanationAnswerText(answer){
 const original=String(answer.answer??''),display=researcherWording(original);
 return `${explanationParagraphs(display).map(part=>`<p class="prose">${explanationInlineText(part)}</p>`).join('')}<details data-detail-key="explanation-original:${esc(answer.artifact_id??answer.context_artifact_id??'')}"><summary>저장된 설명 원문</summary><p class="prose">${esc(original)}</p></details>`;
}
function explanationEventDate(event){
 const parsed=new Date(event.created);return Number.isNaN(parsed.getTime())?String(event.created??''):parsed.toLocaleString('ko-KR');
}
function explanationEventLabel(event){return eventLabels[event.kind]??event.kind}
function explanationEventRecords(answer){
 const records=(answer.event_citations??[]).filter(e=>Number.isInteger(e.seq));
 if(!records.length)return '';
 return `<details class="explanation-event-records" data-detail-key="explanation-events:${esc(answer.artifact_id)}"><summary>설명에 사용한 연구 기록 ${records.length}건</summary><ul class="list">${records.map(event=>`<li>${button('interaction-event-record',`${esc(explanationEventLabel(event))} · ${esc(explanationEventDate(event))}`,`data-id="${esc(answer.artifact_id)}" data-event-seq="${event.seq}"`,'link-button small')}<small>저장 기록 #${event.seq}${['message','correction','observation'].includes(event.kind)?' · '+esc(inputProvenanceLabel(event)):''}</small></li>`).join('')}</ul></details>`;
}
function explanationEventBody(event){
 const body=event.body??{},text=value=>typeof value==='string'&&value?`<p class="prose">${esc(value)}</p>`:'';
 let content=text(body.text);
 if(event.kind==='work_framed'){
  const brief=Array.isArray(body.task_brief)?body.task_brief.map(task=>typeof task==='string'?text(task):`<article>${text(task?.question)}${text(task?.purpose)}${Array.isArray(task?.depends_on)&&task.depends_on.length?`<p class="small muted">함께 확인할 자료</p>${list(task.depends_on)}`:''}</article>`).join(''):text(body.task_brief);
  content=`${text(body.current_question)}${brief}`;
 }
 if(event.kind==='decision_published'){
  const receipt=typeof body.receipt_id==='string'?body.receipt_id:'';
  content+=receipt&&state.artifacts.some(a=>a.id===receipt)?sourceLinks([receipt]):receipt?`<p class="small muted">저장된 실행 기록: ${esc(receipt)}</p>`:'';
 }
 const input=['message','correction','observation'].includes(event.kind);
 return `<p class="small muted">${esc(explanationEventLabel(event))} · ${esc(explanationEventDate(event))} · 저장 기록 #${event.seq}</p>${input?`<p class="limit">${esc(inputProvenanceLabel(event))}</p>${inputProvenanceNotice(event)}`:''}${content}`;
}

function renderLiveInteraction(){
  const jobs=state.jobs.filter(j=>j.kind==='explanation'), pending=jobs.find(j=>['queued','running'].includes(j.status));
  const answers=state.explanations??[], latest=answers.at(-1), lastJob=jobs.at(-1);
  const live=state.jobs.some(j=>j.kind!=='explanation'&&['queued','running'].includes(j.status));
  const failure=lastJob&&!['queued','running','succeeded'].includes(lastJob.status)?lastJob.error:null;
  const text=explanationDrafts.get(state.id)??'';
  const request=state.followthrough_requests?.at(-1);
  const nextJob=request?.job_id?state.jobs.find(j=>j.id===request.job_id):null;
  const published=publishedFollowthrough(state,request);
  let follow='';
  if(request){
    let title,body;
    if(published){title='현재 조건의 판단이 도착했습니다';body=published.recovered_from_other_job?'중단 이후 이어서 검토한 결과입니다. 이전 중단 기록은 변경 기록에 보존되어 있습니다.':'아래 판단에서 바뀐 내용과 계속 유지한 내용을 확인할 수 있습니다.'}
    else if(request.status==='pending'){title='변경을 접수했습니다';body='현재 작업의 다음 경계에서 새 조건으로 이어서 검토합니다. 앞선 원자료와 결과도 함께 확인합니다.'}
    else if(request.status==='needs_confirmation'){title='이어서 검토할 조건을 확인해 주세요';body=request.error}
    else if(nextJob&&['queued','running'].includes(nextJob.status)){title='변경한 조건으로 검토 중입니다';body='새 질문과 이전 근거를 함께 보고, 영향을 받은 판단과 다음 행동을 다시 확인합니다.'}
    else if(nextJob?.status==='succeeded'){title='변경한 조건의 판단이 도착했습니다';body='아래 판단에서 바뀐 내용과 계속 유지한 내용을 확인할 수 있습니다.'}
    else if(nextJob){title='후속 검토의 기록을 확인해 주세요';body=nextJob.error??jobLabels[nextJob.status]??nextJob.status}
    if(title)follow=`<aside class="followthrough-status" role="status"><strong>${esc(title)}</strong><p>${esc(body??'')}</p>${request.status==='needs_confirmation'&&!published?button('interaction-review-current','현재 조건으로 이어서 검토',!status.gateway.available?'disabled':'','small'):''}</aside>`;
  }
  return `${follow}<section class="live-interaction"><div class="interaction-heading"><div><h2>${live?'조사 중에도 물어보세요':'판단을 이해하고 싶다면'}</h2><p>설명만 묻는 질문입니다. 조건을 바꾸려면 아래의 ‘이 지점에서 개입하기’를 사용하세요.</p></div></div>
  <label class="sr-only" for="explanation-question">저장된 판단과 진행 상황에 대한 설명 질문</label>
  <div class="explanation-composer"><textarea id="explanation-question" rows="2" placeholder="왜 이 방향을 보고 있나요? 지금 무엇이 아직 불확실한가요?">${esc(text)}</textarea>${button('interaction-explain','설명 물어보기',pending||explanationSending||!status.gateway.available?'disabled':'','small')}</div>
  ${pending?`<p class="interaction-pending" role="status">${pending.status==='queued'?'설명 질문을 접수했습니다.':'저장된 근거로 설명을 준비하고 있습니다.'} 조사 진행 상황은 아래에서 계속 확인할 수 있습니다.</p>`:''}
  ${failure?`<p class="notice-inline">설명을 마치지 못했습니다. ${esc(failure)}</p>`:''}
  ${latest?`<details class="latest-explanation"><summary>질문에 대한 설명 보기 · ${esc(latest.question.slice(0,70))}${latest.question.length>70?'…':''}</summary><article class="interaction-answer"><p class="interaction-question">${esc(latest.question)}</p>${explanationAnswerText(latest)}${explanationArtifactLinks(latest)}${explanationEventRecords(latest)}
    ${latest.not_established.length?`<details><summary>아직 확인하지 않은 점</summary>${list(latest.not_established)}</details>`:''}
    ${(latest.citation_provenance??[]).some(x=>x.delivery==='cited_in_saved_snapshot_not_reread')?'<p class="small muted">저장된 판단·메모가 연결한 출처를 포함합니다. 이번 설명에서 모든 원자료를 다시 확인한 것은 아닙니다.</p>':''}
    <p class="small muted">설명 기준: ${esc(new Date(latest.snapshot_captured_at??latest.created).toLocaleTimeString('ko-KR'))}${latest.based_rev!==state.rev?' · 이후 연구 조건이 바뀌었습니다.':''}</p>
    ${latest.suggested_condition_change?button('interaction-use-change','제안된 정정 문구를 입력창으로 가져오기',`data-id="${esc(latest.artifact_id)}"`,'small'):''}</article></details>`:''}
  ${answers.length>1?`<details><summary>이전 설명 ${answers.length-1}개</summary>${answers.slice(0,-1).reverse().map(a=>`<article class="interaction-answer"><strong>${esc(a.question)}</strong>${explanationAnswerText(a)}${explanationArtifactLinks(a)}${explanationEventRecords(a)}<p class="small muted">저장 당시 조건의 설명</p></article>`).join('')}</details>`:''}</section>`;
}

async function interactionAction(action,node){
  if(action==='interaction-event-record'){
    const answer=(state.explanations??[]).find(a=>a.artifact_id===node.dataset.id);
    const event=(answer?.event_citations??[]).find(e=>e.seq===Number(node.dataset.eventSeq));
    if(!event){notice('이 설명에 사용한 저장 기록을 확인할 수 없습니다.');return;}
    await openResearchPanel({kind:'explanation-event',id:`${answer.artifact_id}:event:${event.seq}`,title:'설명에 사용한 연구 기록',body:explanationEventBody(event)});return;
  }
  if(action==='interaction-use-change'){
    const answer=(state.explanations??[]).find(x=>x.artifact_id===node.dataset.id);
    if(!answer?.suggested_condition_change)return;
    draft=answer.suggested_condition_change;inputKind='correction';syntheticDraft=false;
    evidaStorage.setItem(draftKey(),draft);render();document.querySelector('#message')?.focus();return;
  }
  if(action==='interaction-review-current'){
    await api(`/api/workspaces/${state.id}/review-requests`,{expected_rev:state.rev,command_id:crypto.randomUUID()});
    await refresh();notice('현재 조건의 후속 검토를 접수했습니다.');return;
  }
  if(action!=='interaction-explain'||explanationSending)return;
  const wid=state.id,rev=state.rev,question=(explanationDrafts.get(wid)??'').trim();
  if(!question){notice('설명이 필요한 질문을 적어 주세요.');return}
  explanationSending=true;
  try{
    if(!await refreshGatewayStatus({force:true,renderChanges:false}))throw Error('현재 모델 연결을 사용할 수 없습니다. 설명 질문 초안은 그대로 남아 있습니다.');
    if(state?.id!==wid||state.rev!==rev||(explanationDrafts.get(wid)??'').trim()!==question)throw Error('연구 조건이나 질문이 바뀌었습니다. 현재 내용을 확인한 뒤 다시 보내 주세요.');
    await api(`/api/workspaces/${wid}/explanations`,{expected_rev:rev,command_id:crypto.randomUUID(),question});
    explanationDrafts.delete(wid);await refresh();notice('설명 질문을 접수했습니다.');
  }finally{explanationSending=false;render()}
}

async function submitResearchFollowthrough(){
  if(draft.trim()){
    const body={kind:inputKind,text:draft.trim(),synthetic:syntheticDraft,review_requested:true};
    await api(`/api/workspaces/${state.id}/commands`,{expected_rev:state.rev,command_id:crypto.randomUUID(),body});
    draft='';syntheticDraft=false;evidaStorage.removeItem(draftKey());
  }else{
    await api(`/api/workspaces/${state.id}/review-requests`,{expected_rev:state.rev,command_id:crypto.randomUUID()});
  }
  await refresh();notice('이 조건으로 검토하도록 접수했습니다.');
}
