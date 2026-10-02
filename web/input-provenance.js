// The server supplies effective classification; the preserved body stays inspectable.
function inputProvenance(event){
  if(event?.effective_provenance)return event.effective_provenance;
  const body=event?.body??{},synthetic=body.origin==='synthetic'||body.synthetic===true;
  return {origin:synthetic?'synthetic':body.origin??'researcher_report',synthetic,corrected_by:null};
}
function inputProvenanceLabel(event){
  const provenance=inputProvenance(event);
  return `${provenance.synthetic?'가상 입력':'연구자 입력'}${provenance.corrected_by?' · 출처 정정됨':''}`;
}
function inputProvenanceNotice(event){
  const provenance=inputProvenance(event),correction=provenance.corrected_by;
  if(!correction)return '';
  return `<p class="limit">${provenance.synthetic?'출처 정정에 따라 가상 시연 입력으로 분류합니다. 실제 측정이나 임상 효과의 근거가 아닙니다.':'출처 정정에 따라 연구자 보고로 분류합니다. 이 분류가 관측의 독립 검증을 뜻하지는 않습니다.'} 원문과 당시 출처 표기는 보존했습니다.</p><p class="small muted">연구자 확인: ${esc(correction.researcher_reply)} · ${esc(correction.reason)} ${button('message-source','출처 정정 기록',`data-id="${esc(correction.message_id)}"`,'link-button small')}</p>`;
}
function inputSourceView(event){
  if(!event)return '입력 기록을 찾지 못했습니다.';
  return `<p class="prose">${esc(event.body.text)}</p><p class="limit">${esc(inputProvenanceLabel(event))} · ${esc(event.created)}</p>${inputProvenanceNotice(event)}${event.effective_provenance?.corrected_by?`<details class="meta-details"><summary>정정 전 원 입력 기록</summary>${json(event.body)}</details>`:''}`;
}
