function nextObservationResourceView(result,checkName) {
  const summary=result.summary??{},problem=result.problem??{},assessment=result.resource_assessment;
  const selected=summary.selected_check_ids??[];
  const unit=summary.cost_unit??problem.cost_unit??'선언한 단위';
  const repair=['repair_readout','measurement_failure','repair_intervention','intervention_failure'].includes(summary.selection_status);
  const information=values=>values?.length?`<ul class="list">${values.map(value=>`<li>${esc(value)}</li>`).join('')}</ul>`:'';
  const budgetLabel={within_declared_budget:'선언한 비용 기준으로 입력 예산 이내',
    over_declared_budget:'알려진 비용만으로 입력 예산을 초과합니다',unresolved:'실행 가능 여부는 비용 확인 후 판단합니다'};
  let current='';
  if(summary.selection_status==='decision_region_reached'){
    current='<p class="small">이 판단을 위한 추가 확인 없이 다음 단계로 이어집니다.</p>';
  }else if(assessment){
    if(assessment.cost_status==='known'&&selected.length&&Number.isFinite(summary.cost)){
      current=`<p class="small">선택한 확인의 선언 비용: ${esc(summary.cost)} ${esc(unit)}</p>`;
    }else if(assessment.cost_status==='unknown'){
      current=`<p>${repair?'수리비용은 미정입니다. 복구 방법과 반복 측정까지의 비용을 확인해 주세요.':assessment.budget_status==='over_declared_budget'?'유용한 대안의 알려진 비용이 예산을 넘습니다. 검사 범위와 사용할 예산을 함께 검토해 주세요.':'총비용을 정하려면 미정 항목의 견적이 필요합니다.'}</p>`;
      if(Number.isFinite(assessment.known_subtotal))current+=`<p class="small">선언된 비용의 소계: ${esc(assessment.known_subtotal)} ${esc(unit)} · 미정 항목을 더하기 전 금액</p>`;
    }
    if(budgetLabel[assessment.budget_status])current+=`<p class="small">${esc(budgetLabel[assessment.budget_status])}</p>`;
    current+=information(assessment.required_information);
  }else if(repair){
    // Historical artifacts retain their original zero placeholder. It is not a
    // repair estimate, so present the recorded state without rewriting history.
    current='<p>이 기록의 수리 견적은 미정입니다. 복구 방법·견적과 반복 측정에 사용할 예산을 확인해 주세요.</p>';
  }else if(selected.length&&['conditional_plan','partial_only'].includes(summary.selection_status)&&Number.isFinite(summary.cost)){
    current=`<p class="small">선택한 확인의 선언 비용: ${esc(summary.cost)} ${esc(unit)}</p>`;
  }
  const options=result.pending_cost_options??[];
  const optionView=option=>`<div class="outcome"><strong>${esc((option.check_ids??[]).map(checkName).join(' + '))}</strong><p class="small">${esc(option.resolution==='full'?'명시한 결과별로 다음 판단을 정할 수 있는 조합':'남은 판단의 일부를 가르는 확인')}</p>${Number.isFinite(option.known_subtotal)?`<p class="small">선언된 비용의 소계: ${esc(option.known_subtotal)} ${esc(unit)} · 총비용은 미정</p>`:''}<p>${esc(budgetLabel[option.budget_status]??'필요한 견적을 확인한 뒤 실행 가능 여부를 판단합니다.')}</p>${information(option.required_information)}</div>`;
  const pending=options.length?`<details class="outcome-details"><summary>견적을 확인할 관측 대안 ${esc(options.length)}개</summary><p class="small">명시한 예상에서 판단을 가를 수 있는 대안입니다. 보존된 항목 순서로 표시합니다. 견적을 확인하면 비용을 비교할 수 있습니다.</p>${options.slice(0,12).map(optionView).join('')}${options.length>12?`<details class="outcome-details"><summary>나머지 ${esc(options.length-12)}개 대안 보기</summary>${options.slice(12).map(optionView).join('')}</details>`:''}</details>`:'';
  return current||pending?`<section data-next-observation-resources><h4>실행 조건과 비용</h4>${current}${pending}</section>`:'';
}

// Read the labels and conditions bound to this saved calculation, including
// historical checks. A newer workspace decision must not relabel its outcomes.
function nextObservationSelectionTable(result) {
  const problem=result.problem??{},summary=result.summary??{},binding=result.binding??{};
  const checks=result.checks??[],worlds=problem.worlds??[],decisions=problem.decisions??[];
  const checkName=id=>checks.find(c=>c.id===id)?.question??'확인 항목의 원문 필요';
  const worldName=id=>worlds.find(w=>w.id===id)?.description??'상황의 원문 필요';
  const decisionName=id=>decisions.find(d=>d.id===id)?.label??'다음 판단의 원문 필요';
  const items=(values,format)=>values?.length?`<ul class="list">${values.map(v=>`<li>${esc(format(v))}</li>`).join('')}</ul>`:'<p class="small muted">이 기록에서 정한 항목 없음</p>';
  const statuses={
    conditional_plan:'먼저 확인할 관측',
    decision_region_reached:'남은 설명들이 같은 다음 판단으로 이어집니다',
    partial_only:'판단의 일부를 가르는 확인',
    stop_specific_claim:'이 판단을 가를 확인을 더 찾아야 합니다',
    intervention_failure:'개입 조건을 복구한 뒤 다시 판단',
    repair_intervention:'개입 조건을 복구한 뒤 다시 판단',
    measurement_failure:'측정을 복구한 뒤 다시 판단',
    repair_readout:'측정을 복구한 뒤 다시 판단',
    validity_unresolved:'측정과 개입의 성립 조건 확인',
    insufficient_precision:'구별에 필요한 정밀도 확인',
    precision_check:'구별에 필요한 정밀도 확인',
    context_unresolved:'결과가 나온 조건과 원 관측의 연결 확인',
    model_gap:'원 예측표에 담기지 않은 설명과 조건 검토',
    unmeasured:'결과를 기다리는 확인',
    conditional_update:'입력한 결과에 따른 다음 판단',
    report_confirmation_required:'보고한 측정 조건을 먼저 확인해야 합니다',
    subject_confirmation_required:'관측한 후보·조건 기록을 먼저 확인해야 합니다',
    needs_cost_information:'유용한 확인의 비용을 먼저 알아야 합니다',
    needs_budget_adjustment:'현재 예산에 맞는 확인 방법을 정해야 합니다'
  };
  const declaration={model_assumptions:'모델이 제시한 조건',researcher_assumptions:'연구자 발언과 연결해 확인할 조건',synthetic_fixture:'합성 개발 사례의 조건'};
  const origins={prospective:'이 측정 결과 전에 제시한 예상',previously_recorded:'이전에 보존한 예상',reconstructed_after_result:'이 결과를 본 뒤 구성한 설명'};
  const selected=summary.selected_check_ids??[];
  const retained=summary.retained_configuration_ids??worlds.map(w=>w.id);
  const next=summary.common_next_decisions??[];
  const outcomeText=(id,index)=>{
    const check=checks.find(c=>c.id===id),outcome=check?.possible_outcomes?.[index];
    return `${checkName(id)}: ${outcome?.observation??'결과의 원문 확인 필요'}`;
  };
  const rows=result.rows??[];
  const savedObservations=(result.observed_events??[]).map(event=>{
    const effective=event.effective_provenance?.origin??event.origin;
    const label={synthetic:'합성 개발 사례의 관측 원문',researcher_report:'연구자가 입력한 관측 원문'}[effective]??'연결한 관측 원문';
    const correction=event.effective_provenance?.corrected_by?'<p class="small">출처 정정을 반영한 분류입니다. 입력 당시의 원문은 아래에 보존합니다.</p>':'';
    return `<details class="outcome-details"><summary>${esc(label)}</summary>${correction}<p class="prose">${esc(event.text??'')}</p>${typeof measurementReportView==='function'?measurementReportView(event):''}</details>`;
  }).join('');
  const sourceEvents=(result.source_events??[]).map(event=>{
    const effective=event.effective_provenance?.origin??event.body?.origin;
    const label=effective==='synthetic'?'합성 사례의 저장 원문':effective==='researcher_report'?'연구자가 입력한 원문':'연결한 저장 원문';
    const correction=event.effective_provenance?.corrected_by?'<p class="small">출처 정정을 반영한 분류입니다. 입력 당시의 원문은 아래에 보존합니다.</p>':'';
    return `<details class="outcome-details"><summary>${esc(label)}</summary>${correction}<p class="prose">${esc(event.body?.text??'')}</p></details>`;
  }).join('');
  const assessment=result.result_assessment;
  const reportComparison=result.observation_amendment?{measurement_report_comparison:[result.observation_amendment.effective_report_comparison].filter(Boolean)}:result;
  const usableResult=assessment?.context_match&&assessment.intervention_status==='validated'&&assessment.measurement_validity==='validated'&&assessment.precision==='adequate'&&!result.report_guard?.applied&&!result.subject_guard?.applied;
  const pendingResult=result.subject_guard?.applied?'관측한 후보·조건 기록을 확인한 뒤 결과를 연결합니다.':'생물학적 결과 분류는 측정 조건 확인 후 정합니다.';
  const observed=assessment?`<section><h4>연결한 결과의 해석</h4><p>${esc(checkName(assessment.check_id))}</p><p>${esc(!usableResult?pendingResult:assessment.outcome_index==null?'아직 유효한 결과에 대응시키지 않은 관측':outcomeText(assessment.check_id,assessment.outcome_index))}</p><p class="small">${esc([
    assessment.context_match?'원 관측과 조건이 일치한다고 해석':'원 관측과 조건의 일치 확인 필요',
    {validated:'개입 조건 성립으로 해석',failed:'개입 조건 실패로 해석',unknown:'개입 조건 확인 필요'}[assessment.intervention_status],
    {validated:'측정 성립으로 해석',failed:'측정 실패로 해석',unknown:'측정 성립 확인 필요'}[assessment.measurement_validity],
    {adequate:'구별에 충분한 정밀도로 해석',insufficient:'구별에 필요한 정밀도 부족',unknown:'정밀도 확인 필요'}[assessment.precision]
  ].filter(Boolean).join(' · '))}</p><p>${esc(assessment.assessment_basis??'')}</p></section>`:'';
  const sources=[binding.decision_id,binding.hypothesis_review_id,binding.prior_selection_id].filter(Boolean);
  const cost=nextObservationResourceView(result,checkName);
  const table=rows.length?`<div class="table-scroll"><table><thead><tr><th>이 관측이 나오면</th><th>남아 있는 상황</th><th>이어서 할 판단</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${items(Object.entries(row.outcome_by_check??{}),([id,index])=>outcomeText(id,index))}</td><td>${items(row.retained_configuration_ids,worldName)}</td><td>${row.common_next_decisions?.length?items(row.common_next_decisions,decisionName):'<p>남은 상황을 더 가를 확인이 필요합니다.</p>'}</td></tr>`).join('')}</tbody></table></div>`:'';
  const assumptions=problem.declaration??{};
  const actionDetails=(problem.actions??[]).map(action=>{
    const checksStatus=[action.available?'이용 가능하다고 기록':'가용성 확인 필요',action.design_validated?'설계 조건이 적절하다고 선언':'설계 조건 확인 필요',action.precision_plan_defined?'정밀도 계획 기록':'정밀도 계획 필요'];
    return `<details class="outcome-details"><summary>${esc(checkName(action.check_id))}</summary><p class="small">${esc(checksStatus.join(' · '))}</p><p>${esc(action.declaration_basis??'')}</p><p>${esc(action.precision_rule??'')}</p>${(action.predictions??[]).map(prediction=>`<div class="outcome"><strong>${esc(worldName(prediction.world_id))}</strong><p>${esc(origins[prediction.origin]??'예측 시점 확인 필요')} · ${esc({complete:'명시한 결과 범위를 검토',partial:'결과 범위 일부 검토',unknown:'결과 범위 확인 필요'}[prediction.coverage]??'결과 범위 확인 필요')}</p>${items(prediction.outcome_indices??[],index=>outcomeText(action.check_id,index))}<p class="small">${esc(prediction.condition_basis??'')}</p><p class="small">${esc(prediction.basis??'')}</p></div>`).join('')}</details>`;
  }).join('');
  return `<section data-next-observation-selection><h3>다음 확인을 고르는 근거</h3><p>${esc(problem.immediate_decision??'보존된 판단의 다음 확인을 검토합니다.')}</p><p class="small muted">이 계산이 참조한 판단과 원자료${sources.length?sourceLinks(sources):' · 연결 확인 필요'}</p>${savedObservations}${observed}${typeof measurementReportComparisonView==='function'?measurementReportComparisonView(reportComparison):''}<h4>${esc(statuses[summary.selection_status]??'계산 기록 확인 필요')}</h4>${selected.length?items(selected,checkName):''}${cost}${typeof observationAmendmentEntry==='function'?observationAmendmentEntry(result):''}${next.length?items(next,decisionName):''}<h4>현재 함께 남겨 둔 상황</h4>${items(retained,worldName)}${typeof observationAmendmentHistory==='function'?observationAmendmentHistory(result):''}${table?`<h4>관측에서 다음 판단까지</h4>${table}`:''}${result.has_more?'<p class="small">현재 페이지에 표시한 결과입니다. 나머지 결과는 다음 페이지에서 확인할 수 있습니다.</p>':''}<details class="outcome-details"><summary>선언한 조건과 근거</summary><p>${esc(declaration[summary.declaration_kind??assumptions.kind]??'조건의 작성 경위 확인 필요')}</p><p>${esc(assumptions.basis??'')}</p>${items(assumptions.conditions??[],v=>v)}${sourceEvents?`<h4>조건을 구성할 때 참조한 원문</h4>${sourceEvents}`:''}${actionDetails}</details><p class="small muted">이 판단은 위에 선언한 조건과 결과 범위에 대한 계산입니다. 실제 관측을 연결할 때 측정의 성립 조건과 정밀도를 함께 검토합니다.</p></section>`;
}
