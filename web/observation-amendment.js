// A report amendment preserves the original physical observation and its interpretation.
let observationAmendmentDialog=null;
let observationAmendmentRequest=0;

function observationAmendmentEntry(result){
  if(!['report_confirmation_required','subject_confirmation_required'].includes(result.summary?.selection_status)
    ||!result.result_assessment||typeof selected!=='string'||!selected)return '';
  return `<section data-observation-amendment-entry><h4>확인한 대상·조건 반영</h4><p>이 관측의 대상이나 측정 조건을 확인했다면, 정정 근거를 남기고 같은 관측의 조건부 판단을 다시 계산할 수 있습니다.</p>${button('observation-amendment-open','이 관측의 대상·조건 확인',`data-artifact="${esc(selected)}"`,'small')}</section>`;
}

function observationAmendmentHistory(result){
  const amendment=result.observation_amendment;
  if(!amendment)return '';
  const original=(result.observed_events??[]).find(row=>row.message_id===amendment.original_observation_message_id);
  const before=original?.measurement_report,after=amendment.effective_measurement_report;
  const rows=after?Object.entries(measurementReportLabels).map(([field,label])=>`<tr><th>${esc(label)}</th><td>${esc(before?measurementReportValue(field,before[field]):'최초 보고 없음')}</td><td>${esc(measurementReportValue(field,after[field]))}</td></tr>`).join(''):'';
  const sources=[amendment.original_selection_id].filter(Boolean);
  const originalComparison=typeof measurementReportComparisonView==='function'?measurementReportComparisonView(result):'';
  return `<section data-observation-amendment-history><h4>같은 관측에서 확인한 보고</h4><p>원 관측과 모델의 결과 해석을 유지하고, 정정한 대상·조건으로 한 번 평가한 분기입니다.</p>${amendment.reason?`<p class="prose">${esc(amendment.reason)}</p>`:''}${rows?`<div class="table-scroll"><table><thead><tr><th>측정 조건</th><th>최초 보고</th><th>이 정정에서 적용한 보고</th></tr></thead><tbody>${rows}</tbody></table></div>`:''}${amendment.effective_subject_binding?reportedSubjectBindingView(amendment.effective_subject_binding):''}${originalComparison?`<details><summary>원 보고와 당시 해석의 차이</summary>${originalComparison}</details>`:''}${sources.length?`<p class="small">정정하기 전 계산${sourceLinks(sources)}</p>`:''}${amendment.amendment_message_id?button('message-source','정정 원문·근거 열기',`data-id="${esc(amendment.amendment_message_id)}"`,'link-button small'):''}</section>`;
}

function observationAmendmentForm(context,result,original){
  const assessment=result.result_assessment??{};
  const check=(result.checks??[]).find(row=>row.id===assessment.check_id);
  const question=check?.question??'보존된 관측';
  const outcome=assessment.outcome_index==null?'아직 결과 범주를 정하지 않은 해석':check?.possible_outcomes?.[assessment.outcome_index]?.observation??'원 결과 해석의 범주 확인 필요';
  const provenance=context.origin==='synthetic'?'합성 개발 사례의 관측':context.origin==='researcher_report'?'연구자가 보고한 관측':'출처 분류를 함께 확인할 관측';
  const expected=context.expected_subjects??[];
  const subjects=expected.length?`<section><h4>원래 확인하려던 대상</h4>${subjectRecordsView(expected)}<label class="checkbox"><input type="checkbox" id="amend-subject-enabled"> 대상에 대한 보고를 이번에 정정</label><fieldset id="amend-subject-fields" disabled hidden><legend>관측한 대상 확인</legend><label>확인한 내용<select id="amend-subject-state"><option value="">확인한 내용을 선택해 주세요</option><option value="expected">위 원기록을 대상으로 한 관측임을 확인</option><option value="unknown">관측한 대상을 아직 확인하는 중</option></select></label></fieldset></section>`:'';
  const originalView=original?`<details><summary>보존된 관측 원문·최초 보고</summary><p class="prose">${esc(original.text??'')}</p>${measurementReportView(original)}</details>`:'';
  return `<p class="feedback-question">${esc(question)}</p><p class="small muted">${esc(provenance)}</p><p>같은 측정에서 확인한 사실과 대상 기록을 정정합니다. 새로 측정한 결과는 ‘새 관측’으로 연결해 주세요.</p>${originalView}<details><summary>이번 계산이 유지할 원 결과 해석</summary><p>모델이 기록한 결과 범주: ${esc(outcome)}</p><dl class="context-facts">${Object.entries(measurementReportLabels).map(([field,label])=>`<div><dt>${esc(label)}</dt><dd>${esc(measurementReportValue(field,assessment[field]))}</dd></div>`).join('')}</dl><p class="prose small">${esc(assessment.assessment_basis??'')}</p></details>${subjects}${measurementReportForm()}<label>정정한 내용과 근거<textarea id="amend-reason" maxlength="4000" placeholder="예: 원 시료 기록을 확인해 이 관측의 대상이 같은 후보 행임을 확인했습니다."></textarea></label><p class="small muted">선택한 보고 항목만 바뀝니다. 원 관측·원자료·이전 계산은 함께 보존됩니다.</p><div class="dialog-actions">${button('observation-amendment-save','정정 저장·같은 관측 재계산','','primary')}</div>`;
}

function observationAmendmentPayload(context,report,subjectChange,subjectState,reason){
  const text=reason.trim();
  if(!text)throw Error('무엇을 확인해 정정하는지 근거와 함께 적어 주세요.');
  if(text.length>4000)throw Error('정정 이유는 4,000자 이내로 적어 주세요.');
  const updates={};
  for(const key of ['measurement_report','source_artifact_ids'])if(key in report)updates[key]=report[key];
  if(subjectChange){
    if(!['expected','unknown'].includes(subjectState))throw Error('관측한 대상에 대해 확인한 내용을 선택해 주세요.');
    if(subjectState==='expected'&&!(context.expected_subject_refs??[]).length)throw Error('확인할 원 대상 기록을 다시 불러와 주세요.');
    updates.reported_subject_refs=subjectState==='expected'?context.expected_subject_refs.map(ref=>({...ref})):[];
  }
  if(!('measurement_report' in updates)&&!('reported_subject_refs' in updates))throw Error('정정할 측정 조건 또는 대상 보고를 선택해 주세요.');
  return {kind:'correction',text,observation_amendment:{target_message_id:context.target_message_id,
    prior_selection_id:context.prior_selection_id,reason:text},...updates,recalculate_held_selection:true};
}

async function observationAmendmentAction(action,node){
  if(busy||node.disabled)return;
  if(action==='observation-amendment-open'){
    const request=++observationAmendmentRequest,wid=state.id,id=node.dataset.artifact;
    const visible=typeof currentReader==='function'?currentReader()?.id:selected;
    node.disabled=true;
    try{
      const [context,data]=await Promise.all([
        api(`/api/workspaces/${wid}/observation-amendments?selection_id=${encodeURIComponent(id)}`),
        api(`/api/workspaces/${wid}/artifacts/${encodeURIComponent(id)}`)
      ]);
      if(state?.id!==wid||request!==observationAmendmentRequest||visible!==(typeof currentReader==='function'?currentReader()?.id:selected))return;
      if(!context.eligible)throw Error(context.reason??'이 계산에 이어진 기록을 먼저 확인해 주세요.');
      if(!Number.isInteger(context.expected_rev))throw Error('연구의 현재 판본을 확인한 뒤 다시 열어 주세요.');
      const original=state.events.find(event=>event.body?.message_id===context.target_message_id)?.body;
      observationAmendmentDialog={...context,workspace_id:wid,command_id:crypto.randomUUID()};
      showDialog('이 관측의 대상·조건 확인',observationAmendmentForm(context,data.result,original));
      const report=context.effective_measurement_report;
      if(report){
        for(const field of Object.keys(measurementReportLabels)){
          const value=field==='context_match'?(report[field]===true?'true':report[field]===false?'false':'unknown'):report[field];
          dialog.querySelector(`#feedback-report-${field}`).value=value??'unknown';
        }
        dialog.querySelector('#feedback-report-basis').value=report.assessment_basis??'';
      }
      const enabled=dialog.querySelector('#feedback-report-enabled');
      enabled.parentElement.lastChild.textContent=' 측정 조건에 대한 보고를 이번에 정정';
    }catch(error){if(state?.id===wid&&request===observationAmendmentRequest){actionError=error.message;notice(error.message)}}
    finally{node.disabled=false}
    return;
  }
  if(action!=='observation-amendment-save')return;
  const context=observationAmendmentDialog;
  busy=true;node.disabled=true;
  try{
    if(!context||state?.id!==context.workspace_id)throw Error('열어 둔 연구가 바뀌었습니다. 정정할 관측을 다시 열어 주세요.');
    const body=observationAmendmentPayload(context,measurementReportInput(),
      dialog.querySelector('#amend-subject-enabled')?.checked??false,
      dialog.querySelector('#amend-subject-state')?.value??'',dialog.querySelector('#amend-reason').value);
    const response=await api(`/api/workspaces/${context.workspace_id}/commands`,{
      expected_rev:context.expected_rev,command_id:context.command_id,body});
    dialog.close();observationAmendmentDialog=null;
    if(state?.id===context.workspace_id){
      await refresh();
      const job=state.jobs.find(row=>row.id===response.job_id);
      if(job?.output_id)await chooseArtifact(job.output_id);
      notice('정정을 보존하고 같은 관측의 조건부 계산을 접수했습니다. 완료 결과에서 이전 계산과 비교할 수 있습니다.');
    }
  }catch(error){actionError=error.message;notice(error.message)}
  finally{busy=false;node.disabled=false;render()}
}

document.addEventListener('change',event=>{
  if(event.target.id!=='amend-subject-enabled')return;
  const fields=dialog.querySelector('#amend-subject-fields');
  if(fields){fields.disabled=!event.target.checked;fields.hidden=!event.target.checked;}
});
