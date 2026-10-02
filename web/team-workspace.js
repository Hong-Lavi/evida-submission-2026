function teamGuide(){
  const id=new URLSearchParams(location.search).get('guide');
  const item=TEAM_EXAMPLES.find(e=>e.id===id&&e.workspace===state?.id);
  if(!item)return '';
  const refused=item.feedback&&Boolean(providerNotice());
  return `<details class="team-guide" open><summary>예시 따라가기 · ${esc(item.label)}</summary><ol>${item.steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ol>${sourceLinks(item.sources)}${refused?'<p class="small">최신 추가 검토는 서비스에서 거절됐습니다. 변경 기록에서 완료된 이전 정정과 이번 미완료 입력을 구별해 확인하세요.</p>':`${item.feedback?button('team-feedback','가상 후속 관측 입력해 보기','','small'):button('team-prompt','후속 질문 입력해 보기','','small')}<p class="small muted">입력 예시는 초안으로 열립니다. 저장·실행을 누르기 전에는 연구가 바뀌지 않습니다.</p>`}</details>`;
}
function renderInputChanges(){
  const change=state.input_changes;
  if(!change || !(change.sources.length||change.messages.length||change.intent_edits.length))return '';
  const published=change.phase==='published_review';
  return `<details class="input-changes"><summary>${published?'이번 판단까지 추가된':'이전 판단 이후 추가된'} 자료 ${change.sources.length}개 · 입력 ${change.messages.length+change.intent_edits.length}개</summary><p class="small muted">추가된 자료의 위치입니다. 모든 자료를 읽었거나 각 주장이 검증됐다는 뜻은 아닙니다. 이전 근거는 자료 목록에서 계속 확인할 수 있습니다.</p>${sourceLinks(change.sources.map(a=>a.id))}${change.messages.map(m=>button('message-source',`${m.kind==='correction'?'정정':m.kind==='observation'?'새 관측':'연구 요청'}${m.origin==='synthetic'?' · 개발용 가상 입력':''}`,`data-id="${esc(m.id)}"`,'link-button small')).join('')}${change.intent_edits.length?`<p class="small">연구 의도 수정 ${change.intent_edits.length}건 · 변경 기록에서 확인</p>`:''}</details>`;
}
function jobStatus(job){
  const diagnostic=[...state.events].reverse().find(e=>e.kind==='provider_response_diagnostic'&&e.body.job_id===job.id);
  return diagnostic?`${jobLabels[diagnostic.body.status]??diagnostic.body.status} · ${diagnostic.body.provider_error_code}`:(jobLabels[job.status]??job.status);
}
function providerNotice(){
  const job=[...state.jobs].reverse().find(j=>j.kind==='planner'&&j.based_rev===state.rev);
  if(!job||state.decision_rev===state.rev)return '';
  const diagnostic=[...state.events].reverse().find(e=>e.kind==='provider_response_diagnostic'&&e.body.job_id===job.id);
  if(!diagnostic&&job.status!=='refused')return '';
  return `<div class="provider-notice" role="status"><strong>새 판단을 완료하지 못했습니다.</strong><p>${esc(diagnostic?.body.message??job.error)}</p><p>새로 입력한 관측과 이전 판단은 남아 있습니다. 자료 조회와 계산 결과는 계속 확인할 수 있습니다.</p></div>`;
}
async function teamAction(action){
  const item=TEAM_EXAMPLES.find(e=>e.id===new URLSearchParams(location.search).get('guide')&&e.workspace===state?.id);
  if(!item)return;
  if(action==='team-prompt'){
    if(draft.trim()){notice('작성 중인 입력이 있습니다. 먼저 저장하거나 비운 뒤 예시를 넣어 주세요.');return;}
    draft=item.prompt;inputKind='message';syntheticDraft=item.synthetic===true;tab='research';evidaStorage.setItem(draftKey(),draft);render();document.querySelector('#message').focus();
  }else if(action==='team-feedback'){
    if(providerNotice()){notice('이 예시의 최신 추가 검토는 서비스에서 거절됐습니다. 원 입력과 이전 판단은 변경 기록에서 확인할 수 있습니다.');return;}
    const h=state.decision?.research_loop?.hypotheses.find(h=>h.id===item.hypothesis);
    if(!h){notice('현재 가설을 확인한 뒤 연결할 부분을 선택해 주세요.');return;}
    const part=h.assessment_scope?.parts.find(p=>p.id===item.part);
    openResearchFeedback(null,h.id,part?.id??null);
    dialog.querySelector('#feedback-text').value=item.feedback;
    dialog.querySelector('#feedback-synthetic').checked=true;
    dialog.querySelector('#feedback-comparison').value='different';
  }
}
