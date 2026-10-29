const measurementReportLabels={measurement_validity:'측정 성립',intervention_status:'개입·처리 적절성',precision:'구별에 필요한 정밀도',context_match:'원래 확인 조건과 일치'};
let feedbackSubjectRefs=[];
function checkSubjectBinding(decisionId,checkId){
  if(!decisionId||!checkId)return null;
  for(const binding of [...(state.check_subject_bindings??[])].reverse()){
    if(binding.decision_id!==decisionId)continue;
    const check=binding.checks?.find(item=>item.check_id===checkId);
    if(check)return check;
  }
  return null;
}
function subjectRecordsView(subjects){
  const roles={candidate:'측정 대상',comparator:'비교 대상',condition:'조건 원자료'};
  return (subjects??[]).map(subject=>{
    const display=subject.display??{},reference=subject.context?.reference??{};
    const transcript=display.transcript_id??reference.transcript_id;
    const version=display.version??reference.version;
    const facts=[display.guide_5to3?['가이드 서열 (5′→3′)',display.guide_5to3]:null,
      transcript?['전사체',`${transcript}${version!=null?` · 버전 ${version}`:''}`]:null,
      display.chemistry?['화학 수정',display.chemistry==='unknown'?'미확인':display.chemistry]:null].filter(Boolean);
    const row=String(subject.json_pointer??'').match(/^\/rows\/(\d+)$/);
    const attrs=`data-id="${esc(subject.artifact_id)}"${row?` data-source-offset="${Number(row[1])}"`:''}`;
    return `<article class="subject-record" data-subject-role="${esc(subject.role)}"><p class="small muted">${esc(roles[subject.role]??subject.role)}</p><strong>${esc(display.label??subject.artifact_title??'연결한 대상')}</strong>${facts.length?`<dl class="context-facts">${facts.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>`:''}<p class="small">${esc(subject.artifact_title??'')}${row?` · 원자료 ${Number(row[1])+1}행`:''}</p>${button('source',row?'대상 원자료의 이 행 열기':'대상 원자료 열기',attrs,'link-button small')}<details><summary>보존한 대상·조건의 원기록</summary>${display.smiles?`<p class="small">구조 (SMILES)</p><pre class="raw">${esc(display.smiles)}</pre>`:''}<pre class="raw">${esc(JSON.stringify({row:subject.snapshot,context:subject.context,source_context:subject.source_context},null,2))}</pre><p class="small">원자료 위치: <code>${esc(subject.json_pointer??'')}</code></p><p class="small">원자료 판본: <code>${esc(subject.artifact_sha256??'')}</code></p></details></article>`;
  }).join('');
}
function checkSubjectsView(check,decisionId=state.decision_id){
  const binding=checkSubjectBinding(decisionId,check?.id);
  if(!binding)return check?.subject_refs?.length?'<p class="small">이 확인의 대상 원기록을 불러와 대조해 주세요.</p>':'';
  return `<section class="check-subjects"><h4>이 확인에 연결한 후보·조건</h4>${subjectRecordsView(binding.subjects)}</section>`;
}
function subjectConfirmationForm(check,decisionId){
  feedbackSubjectRefs=[];
  const binding=checkSubjectBinding(decisionId,check?.id);
  if(!binding)return '';
  feedbackSubjectRefs=(binding.subject_refs??[]).map(ref=>({...ref}));
  return `<section class="feedback-subject-confirmation"><h4>원래 확인하려던 대상</h4>${subjectRecordsView(binding.subjects)}<label class="checkbox"><input type="checkbox" id="feedback-subject-confirm"> 위 후보·조건 기록을 대상으로 한 관측입니다</label><p class="small muted">대상이 다르거나 확인 중이면 새 내용에 적고 관련 자료를 연결해 주세요. 대상 기록이 확인되면 결과에 따른 판단 계산을 이어갑니다.</p></section>`;
}
function reportedSubjectBindingView(binding){
  if(!binding||binding.comparison?.status==='not_declared')return '';
  const labels={same_record:'연결한 대상 기록이 일치합니다',mismatch:'보고한 대상 기록이 원래 확인과 다릅니다',unknown:'어느 대상의 관측인지 확인이 필요합니다'};
  const expected=Array.isArray(binding.expected)?binding.expected:binding.expected?.subjects??[];
  const reported=Array.isArray(binding.reported)?binding.reported:binding.reported?.subjects??[];
  return `<section class="reported-subject-binding"><h4>${esc(labels[binding.comparison?.status]??'연결한 대상 기록 확인')}</h4><details><summary>원래 확인과 보고의 대상 대조</summary><h4>원래 확인의 대상</h4>${subjectRecordsView(expected)}${reported.length?`<h4>보고에 명시한 대상</h4>${subjectRecordsView(reported)}`:'<p class="small">관측한 후보·조건 기록을 확인해 연결하면 대조할 수 있습니다.</p>'}</details><p class="small">측정 조건의 성립은 보고한 조건과 원자료를 함께 확인합니다.</p></section>`;
}
function measurementReportValue(field,value){
  if(field==='context_match')return value===true?'일치':value===false?'불일치':'미확인';
  return {validated:'성립 확인',failed:'실패',adequate:'충분',insufficient:'부족',unknown:'미확인'}[value]??String(value??'미입력');
}
function measurementReportForm(check=null,decisionId=null){
  const allowed=new Set(status.observation_source_kinds??[]);
  const sources=(state.artifacts??[]).filter(a=>allowed.has(a.kind));
  const select=(field,options)=>`<label>${measurementReportLabels[field]}<select id="feedback-report-${field}">${options.map(([value,label])=>`<option value="${value}">${label}</option>`).join('')}</select></label>`;
  return `${subjectConfirmationForm(check,decisionId)}<section class="feedback-measurement-report">
    <label class="checkbox"><input type="checkbox" id="feedback-report-enabled"> 측정 조건에 대한 내 확인도 함께 기록</label>
    <fieldset id="feedback-report-fields" disabled hidden><legend>연구자가 보고하는 측정 조건</legend><div class="upload-fields">
      ${select('measurement_validity',[['unknown','미확인'],['validated','측정이 성립함을 확인'],['failed','측정 실패']])}
      ${select('intervention_status',[['unknown','미확인'],['validated','의도한 개입·처리가 이뤄짐을 확인'],['failed','개입·처리 실패']])}
      ${select('precision',[['unknown','미확인'],['adequate','예상들을 구별하기에 충분'],['insufficient','예상들을 구별하기에 부족']])}
      ${select('context_match',[['unknown','미확인'],['true','원래 확인 조건과 일치'],['false','원래 확인 조건과 다름']])}
    </div><label>판단한 근거·검출한계·대조 조건<textarea id="feedback-report-basis" maxlength="10000" placeholder="어떤 기준으로 확인했는지, 관련 원자료의 페이지·문단·행을 함께 적어 주세요."></textarea></label><p class="small muted">이 보고를 보존해 이후 모델 해석과 대조합니다.</p></fieldset>
    <details class="feedback-source-selection"><summary>함께 검토할 원자료·계산 결과 연결 (선택)</summary>${sources.length?`<label>자료 이름으로 찾기<input type="search" id="feedback-source-search" placeholder="자료 이름 또는 종류"></label><div class="feedback-source-list">${sources.map(a=>`<label class="checkbox" data-feedback-source><input type="checkbox" name="feedback-source" value="${esc(a.id)}"><span>${esc(artifactName(a.id))}<small>${esc(labels[a.kind]??a.kind)}</small></span></label>`).join('')}</div><p class="small muted">선택한 자료의 현재 판본과 원문을 이 관측에 함께 보존합니다.</p>`:'<p class="small muted">‘자료와 도구’에서 원자료를 추가하면 이 관측에 연결할 수 있습니다.</p>'}</details>
  </section>`;
}
function measurementReportInput(){
  const payload={},sourceIds=[...dialog.querySelectorAll('input[name="feedback-source"]:checked')].map(node=>node.value);
  if(sourceIds.length>24)throw Error('연결할 원자료는 24개 이내로 선택해 주세요.');
  if(sourceIds.length)payload.source_artifact_ids=sourceIds;
  if(dialog.querySelector('#feedback-subject-confirm')?.checked&&feedbackSubjectRefs.length)payload.reported_subject_refs=feedbackSubjectRefs.map(ref=>({...ref}));
  if(dialog.querySelector('#feedback-report-enabled')?.checked){
    const value=field=>dialog.querySelector(`#feedback-report-${field}`).value;
    const context=value('context_match');
    payload.measurement_report={measurement_validity:value('measurement_validity'),intervention_status:value('intervention_status'),precision:value('precision'),context_match:context==='true'?true:context==='false'?false:null,assessment_basis:dialog.querySelector('#feedback-report-basis').value.trim()};
  }
  return payload;
}
document.addEventListener('change',event=>{
  if(event.target.id!=='feedback-report-enabled')return;
  const fields=dialog.querySelector('#feedback-report-fields');if(fields){fields.disabled=!event.target.checked;fields.hidden=!event.target.checked;}
});
document.addEventListener('input',event=>{
  if(event.target.id!=='feedback-source-search')return;
  const query=event.target.value.trim().toLocaleLowerCase();
  for(const node of dialog.querySelectorAll('[data-feedback-source]'))node.hidden=!node.textContent.toLocaleLowerCase().includes(query);
});
function measurementReportView(body){
  const report=body?.measurement_report,refs=body?.source_artifact_refs??[];
  if(!report&&!refs.length&&!body?.subject_binding)return '';
  return `<section class="saved-measurement-report">${reportedSubjectBindingView(body?.subject_binding)}${report?`<h4>입력자가 보고한 측정 조건</h4><dl class="context-facts">${Object.entries(measurementReportLabels).map(([field,label])=>`<div><dt>${label}</dt><dd>${esc(measurementReportValue(field,report[field]))}</dd></div>`).join('')}</dl>${report.assessment_basis?`<p class="prose small">${esc(report.assessment_basis)}</p>`:''}`:''}${refs.length?`<h4>함께 보존한 원자료·계산 결과</h4>${sourceLinks(refs.map(ref=>ref.id))}<details><summary>연결 당시 자료 판본</summary>${refs.map(ref=>`<p class="small">${esc(ref.title??ref.id)} · ${esc(labels[ref.kind]??ref.kind)}<br><code>${esc(ref.sha256)}</code></p>`).join('')}</details>`:''}</section>`;
}
function measurementReportComparisonView(result){
  const comparisons=(result.measurement_report_comparison??[]).filter(item=>item.differences?.length);
  if(!comparisons.length)return '';
  return `<section class="measurement-report-comparison"><h4>관측 보고와 모델 해석이 다른 부분</h4>${comparisons.map(item=>`<div class="table-scroll"><table><thead><tr><th>항목</th><th>입력자가 보고한 조건</th><th>모델 해석</th></tr></thead><tbody>${item.differences.map(d=>`<tr><td>${esc(measurementReportLabels[d.field]??d.field)}</td><td>${esc(measurementReportValue(d.field,d.reported))}</td><td>${esc(measurementReportValue(d.field,d.interpreted))}</td></tr>`).join('')}</tbody></table></div>`).join('')}<p class="small">연결한 원자료와 측정 조건으로 이 차이를 먼저 확인하세요.</p></section>`;
}
