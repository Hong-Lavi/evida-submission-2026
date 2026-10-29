const hypothesisReviewLabels = {
  text:{supports:'모델은 지지 근거로 읽음',contradicts:'모델은 반대 근거로 읽음',partial:'모델은 일부만 다룬다고 읽음',not_addressed:'모델은 이 주장을 다루지 않는다고 읽음',unknown:'모델의 문장 관계 검토 미확인'},
  causal:{supports_step:'해당 인과 단계의 근거',association_only:'연관성까지 확인',intervention_response_only:'개입 뒤 변화까지 확인',not_established:'인과 연결 미확정',unknown:'인과 검토 미확인'},
  applicability:{direct:'기록한 조건에 적용',conditional:'추가 조건이 필요',mismatch:'적용 조건이 다름',unknown:'적용 조건 미확인'},
  interpretation:{adequate_measurement:'유효한 측정일 때',measurement_failure:'측정 실패 · 설명 판단 보류',insufficient_precision:'정밀도 부족 · 설명 판단 보류',not_applicable:'조건 불일치 · 설명 판단 보류'},
  origin:{prospective:'관측 전 예상',previously_recorded:'이전에 기록한 예상',reconstructed_after_result:'관측 뒤 구성한 예상'},
};

function currentHypothesisReview(){
  const review=state.hypothesis_review;
  return review?.status==='available'&&review?.review&&review.published_decision_id===state.decision_id ? review : null;
}

function hypothesisReviewScope(field,id,record=currentHypothesisReview()){
  const key=field==='hypotheses'?'hypothesis_id':'check_id';
  return record?.review?.scope?.[field]?.find(row=>row[key]===id)??null;
}

function hypothesisReviewScopeLabel(row){
  return {reviewed:'검토 기록 있음',not_reviewed:'아직 검토하지 않음',not_applicable:'이번 검토 대상에 해당하지 않음'}[row?.status]??'검토 범위 미확인';
}

function renderHypothesisReviewScope(row){
  if(!row)return '';
  return `<p class="small" data-review-scope="${esc(row.status)}"><strong>${esc(hypothesisReviewScopeLabel(row))}</strong> · ${esc(row.reason)}</p>`;
}

function hypothesisReviewSource(anchor,checked){
  const row=/^\/rows\/(\d+)(?:\/|$)/.exec(anchor.path??'');
  const source=state.artifacts.find(a=>a.id===anchor.artifact_id);
  const link=source?button('source',esc(artifactName(source.id)),`data-id="${esc(source.id)}"${row?` data-source-offset="${Number(row[1])}"`:''}`,'link-button small'):'<span>현재 연구에서 찾지 못한 출처</span>';
  const matched=checked?.status==='matched'||checked?.status==='verified';
  return `<div class="evidence-relation">${link}<blockquote>${esc(anchor.quote)}</blockquote><p class="small muted">${matched?'저장 자료와 인용 위치 일치':'저장 자료의 위치 대조 결과 확인 필요'}</p><details><summary>정확한 자료 위치·대조 기록</summary><p>${esc(anchor.path)}</p>${checked?json(checked):'<p>대조 기록 없음</p>'}</details></div>`;
}

function renderHypothesisReview(h,review=currentHypothesisReview()){
  const steps=review?.review?.causal_steps?.filter(s=>s.hypothesis_id===h.id)??[];
  const scope=renderHypothesisReviewScope(hypothesisReviewScope('hypotheses',h.id,review));
  if(!steps.length)return scope;
  return `<section class="hypothesis-causal-review" data-hypothesis-review="${esc(h.id)}"><h3>인과 연결마다 근거 확인</h3>${scope}${steps.map(step=>{
    const checks=review.causal_step_checks?.find(c=>c.step_id===step.id);
    return `<article><h4>${esc(step.claim)}</h4><p class="small">적용하려는 조건: ${esc(step.target_context||'미확인')}</p>${step.evidence_groups.map(group=>{
      const groupCheck=checks?.evidence_groups?.find(g=>g.group_id===group.id),anchors=groupCheck?.anchor_checks??[];
      const checkOpposition=group.text_support==='contradicts'&&['not_established','unknown'].includes(group.causal_support);
      const interpretationNote=checkOpposition?'<p class="notice-inline" data-evidence-interpretation-review="opposition-unestablished">미입증과 반대 관측을 구분해 확인하세요. 검출력·대조군·측정 시점·시험 조건이 이 해석을 뒷받침하는지 원자료에서 확인합니다. 인용 위치의 일치가 이 과학적 해석의 타당성을 확인한 것은 아닙니다.</p>':'';
      return `<details class="outcome-details"><summary>${checkOpposition?'미입증·반대 근거 구분 확인 · ':''}${groupCheck?.all_anchors_verified?'':'인용 위치 미확인 · '}${esc(hypothesisReviewLabels.causal[group.causal_support]??group.causal_support)} · ${esc(hypothesisReviewLabels.applicability[group.applicability]??group.applicability)}</summary><dl><dt>인용이 말하는 범위</dt><dd>${esc(hypothesisReviewLabels.text[group.text_support]??group.text_support)} · ${esc(group.text_support_rationale)}</dd><dt>인과 연결</dt><dd>${esc(group.causal_support_rationale)}</dd><dt>원 연구 조건</dt><dd>${esc(group.reported_context||'미확인')}</dd><dt>현재 조건에 옮길 때</dt><dd>${esc(group.applicability_rationale)}</dd></dl>${interpretationNote}${group.missing_assumptions.length?`<h4>확인할 가정</h4>${list(group.missing_assumptions)}`:''}${group.anchors.length?group.anchors.map((a,i)=>hypothesisReviewSource(a,anchors[i])).join(''):'<p>연결한 원문 인용이 없습니다. 근거를 확인해야 합니다.</p>'}</details>`;
    }).join('')}${!step.evidence_groups.length?'<p>이 연결의 근거 묶음은 아직 없습니다.</p>':''}${step.missing_assumptions.length?`<p><strong>남은 연결</strong></p>${list(step.missing_assumptions)}`:''}</article>`;
  }).join('')}<p class="small muted">근거·인과·적용 범위는 모델의 검토입니다. 저장 자료의 위치 대조와 구별해 표시합니다.</p></section>`;
}

function hypothesisReviewRecordTable(record){
  const ids=[...new Set([...(record.review?.causal_steps??[]).map(s=>s.hypothesis_id),...(record.review?.scope?.hypotheses??[]).map(s=>s.hypothesis_id)])];
  return `<section><h3>보존된 인과 근거·관측 검토</h3><p>해당 판단에 함께 기록한 검토입니다. 현재 판단으로 자동 승계하지 않습니다.</p>${ids.map(id=>renderHypothesisReview({id},record)).join('')}${(record.observation_checks??[]).map(o=>`<details><summary>구별할 관측 · ${esc(o.outcomes?.[0]?.observation??'검토 전')}</summary>${renderHypothesisReviewScope(hypothesisReviewScope('checks',o.check_id,record))}${o.explanations.map(e=>`<h4>${esc(e.statement)}</h4><p>${esc(e.prediction?.rationale??'예상 미확인')}</p>`).join('')}${o.outcomes.map(out=>`<p>${esc(out.observation)} · ${esc(hypothesisReviewLabels.interpretation[out.interpretation]??'해석 조건 미확인')}</p>`).join('')}</details>`).join('')}</section>`;
}

function renderHypothesisReviewSummary(){
  const review=currentHypothesisReview();
  if(!review)return '';
  const steps=review.review.causal_steps;
  const hs=state.decision?.research_loop?.hypotheses??[];
  const checks=state.decision?.research_loop?.next_checks??[],scopes=review.review.scope;
  if(!steps.length&&!review.review.observations.length&&!scopes?.hypotheses?.length&&!scopes?.checks?.length)return '';
  const headline=steps.length||review.review.observations.length?`인과 연결 ${number(steps.length)}개의 근거 검토와 다음 확인 ${number(review.review.observations.length)}개의 예상 비교가 있습니다.`:'이번 판단에는 인과 근거·관측 비교를 마친 항목이 없습니다. 아래에서 검토 범위와 남은 이유를 확인할 수 있습니다.';
  return `<section class="panel" data-science-review="hypotheses"><h3>가설과 근거의 연결</h3><p>${headline}</p>${review.is_current_input?'':'<p class="notice-inline">이 검토 뒤 연구 입력이 바뀌었습니다. 아래는 해당 판단에 보존된 검토입니다.</p>'}${hs.filter(h=>steps.some(s=>s.hypothesis_id===h.id)||hypothesisReviewScope('hypotheses',h.id)).map(h=>{const scope=hypothesisReviewScope('hypotheses',h.id);return `<details class="outcome-details"><summary>${esc(h.statement)}${scope?` · ${esc(hypothesisReviewScopeLabel(scope))}`:''}</summary>${renderHypothesisReview(h)}</details>`;}).join('')}${(scopes?.checks??[]).map(row=>`<div><h4>${esc(checks.find(c=>c.id===row.check_id)?.question??'다음 확인')}</h4>${renderHypothesisReviewScope(row)}</div>`).join('')}${sourceLinks([review.artifact_id])}</section>`;
}

function observationReview(check){
  return currentHypothesisReview()?.observation_checks?.find(c=>c.check_id===check.id)??null;
}

function outcomeInterpretationReview(check,index){
  const review=observationReview(check);
  if(!review)return null; // Legacy decisions have no new review to attribute to them.
  const outcome=review.outcomes?.find(o=>o.outcome_index===index);
  const reasons=new Set(outcome?.guard_reasons??[]);
  if(!outcome||review.status==='not_reviewed')reasons.add('outcome_not_reviewed');
  if(outcome?.interpretation!=='adequate_measurement')reasons.add(outcome?.interpretation??'outcome_not_reviewed');
  const pairs=outcome?.pairs??[];
  if(pairs.some(p=>p.requires_joint_prediction))reasons.add('joint_prediction_required');
  if(pairs.some(p=>p.retrospective))reasons.add('retrospective_prediction');
  for(const pair of pairs)for(const reason of pair.reasons??[]){
    if(['missing_prediction','incomplete_or_unknown_prediction_set','prediction_source_unresolved','explanation_relationship_unknown'].includes(reason))reasons.add(reason);
  }
  const diagnostics=(review.outcome_link_diagnostics??[]).filter(d=>d.outcome_index===index);
  for(const diagnostic of diagnostics){
    if(!['consistent_with_prediction_set','declared_unresolved'].includes(diagnostic.status))reasons.add(diagnostic.status);
  }
  if(pairs.length&&pairs.every(p=>p.status==='neither_predicted'))reasons.add('outcome_outside_all_prediction_sets');
  const labels={
    measurement_failure:'측정 실패 · 설명 판단 보류',insufficient_precision:'정밀도 부족 · 설명 판단 보류',
    not_applicable:'조건 불일치 · 설명 판단 보류',outcome_not_reviewed:'이 결과의 설명 구별 가능성 미검토',
    measurement_validity_requirements_missing:'측정의 유효 조건 미확인',precision_requirement_missing:'구별에 필요한 정밀도 미확인',
    conflicts_with_prediction_set:'원래 해석과 기록한 예상 결과가 서로 맞지 않음',
    joint_prediction_required:'공존 가능한 설명의 결합 예측 필요',retrospective_prediction:'관측 뒤 구성한 예상 · 사전 예측과 구분 필요',
    explanation_relationship_unknown:'예상 결과는 다르지만 설명들의 공존·배타 관계가 미확인',
    missing_prediction:'비교할 설명의 예상 누락',incomplete_or_unknown_prediction_set:'설명별 예상 범위 미확인',
    incomplete_prediction_set:'설명별 예상이 일부만 기록됨',prediction_source_unresolved:'예상 근거 출처 확인 필요',
    parent_effect_not_directly_comparable:'전체 가설 해석과 설명별 예측의 연결 확인 필요',
    unresolved_comparison:'기록한 해석과 예측의 관계 미확인',
    compatible_but_not_discriminating:'이 결과와 맞지만 특정 설명을 구별하지 못함',
    outcome_outside_all_prediction_sets:'기록한 모든 예상에서 벗어남 · 설명과 측정 재검토 필요',
  };
  return {needs_review:reasons.size>0,
    blocks_all_comparisons:!outcome||review.status==='not_reviewed'||outcome.interpretation!=='adequate_measurement'||(outcome.guard_reasons??[]).length>0,
    reasons:[...reasons],
    label:labels[[...reasons][0]]??'기록한 결과 해석 재검토 필요',
    explanations:[...reasons].map(reason=>labels[reason]??'결과 해석의 전제 확인 필요')};
}

function reviewExplanationLabel(ref,review){
  return review?.explanations?.find(e=>e.hypothesis_id===ref.hypothesis_id&&e.alternative_id===ref.alternative_id)?.statement??'설명 확인 필요';
}

function renderObservationReview(check){
  const review=observationReview(check);
  const scope=hypothesisReviewScope('checks',check.id);
  if(!review||review.status==='not_reviewed')return scope?`<div data-observation-review="unreviewed">${renderHypothesisReviewScope(scope)}</div>`:'<p class="small muted" data-observation-review="unreviewed">이 관측이 어떤 설명을 구별하는지는 아직 검토하지 않았습니다.</p>';
  const source=currentHypothesisReview().review.observations.find(o=>o.check_id===check.id);
  const pairs=(review.outcomes??[]).flatMap(o=>o.pairs??[]);
  const useful=pairs.some(p=>p.selection_eligible);
  const usable=(review.outcomes??[]).filter(o=>o.interpretation==='adequate_measurement'&&!(o.guard_reasons??[]).length).flatMap(o=>o.pairs??[]);
  const complete=review.explanations.length>1&&review.explanations.every(e=>e.prediction?.coverage==='complete');
  const same=complete&&usable.length&&usable.every(p=>['shared','neither_predicted'].includes(p.status));
  const patterns=review.explanations.map(e=>e.prediction).filter(p=>['partial','complete'].includes(p?.coverage)&&p.outcome_indices?.length).map(p=>JSON.stringify([...new Set(p.outcome_indices)].sort((a,b)=>a-b)));
  const differentPatterns=new Set(patterns).size>1;
  const headline=useful?'명시한 조건에서 일부 설명을 구별할 결과가 있습니다.':same?'기록된 설명들이 같은 결과를 예상합니다.':differentPatterns?'일부 예상 패턴은 다릅니다. 전체 예상·측정 조건·정밀도를 확인하기 전에는 판별 준비를 확정하지 않습니다.':'설명을 구별할 수 있는지 아직 정하지 못했습니다.';
  const outcomes=check.possible_outcomes??[];
  return `<section class="panel" data-observation-review="${esc(check.id)}"><h4>설명마다 어떤 결과를 예상하나</h4><p>${esc(headline)}</p><p class="small muted">예상 비교 · 실제 관측 결과와 구분합니다.</p>${review.explanations.some(e=>e.prediction?.origin==='reconstructed_after_result')?'<p class="ui-field-caution">관측 뒤에 구성한 예상이 포함됩니다. 독립적인 사전 예측 시험이 아닙니다.</p>':''}<div class="table-scroll"><table><thead><tr><th>비교할 설명</th><th>이 설명과 양립할 결과</th><th>예상의 범위</th></tr></thead><tbody>${review.explanations.map(e=>{
    const p=e.prediction;
    return `<tr><td>${esc(e.statement)}</td><td>${p?.outcome_indices?.length?p.outcome_indices.map(i=>`${i+1}. ${esc(outcomes[i]?.observation??'결과 확인 필요')}`).join('<br>'):p?.coverage==='complete'?'기록한 결과 중 없음':'예상 미확인'}</td><td>${p?`${esc({complete:'해당 조건의 전체 예상',partial:'일부 예상만 기록',unknown:'예상 범위 미확인'}[p.coverage])}<br>${esc(hypothesisReviewLabels.origin[p.origin])}`:'아직 예상하지 않은 설명'}</td></tr>`;
  }).join('')}</tbody></table></div>${review.missing_explanations?.length?`<p>예상을 기록하지 않은 설명 ${number(review.missing_explanations.length)}개도 비교 목록에 남겨 두었습니다.</p>`:''}<details><summary>구별에 필요한 조건·정밀도·예상 근거</summary><h4>먼저 확인할 측정 조건</h4>${source?.validity_requirements?.length?list(source.validity_requirements):'<p>미확인</p>'}<h4>예상 차이를 가를 정밀도</h4><p>${esc(source?.precision_requirement||'미확인 · 정밀도를 정하기 전에는 구별 가능성을 확정하지 않습니다.')}</p>${review.explanations.filter(e=>e.prediction).map(e=>`<h4>${esc(e.statement)}</h4><p>${esc(e.prediction.rationale)}</p>${list(e.prediction.assumptions)}${sourceLinks(e.prediction.source_ids)}`).join('')}</details><p class="small muted">예상 결과를 비교한 기록입니다. 측정 실패나 정밀도 부족은 설명의 반박으로 처리하지 않습니다.</p></section>`;
}

function renderObservationOutcome(check,index){
  const review=observationReview(check),outcome=review?.outcomes?.find(o=>o.outcome_index===index);
  if(!outcome)return '';
  const interpretation=outcomeInterpretationReview(check,index);
  const blocked=interpretation?.blocks_all_comparisons;
  const separating=blocked?[]:(outcome.pairs??[]).filter(p=>p.selection_eligible&&!p.requires_joint_prediction&&!p.retrospective);
  const unresolved=blocked?[]:(outcome.pairs??[]).filter(p=>p.status==='unresolved'||p.requires_joint_prediction||p.retrospective||(p.status==='separating'&&!p.selection_eligible));
  const warning=interpretation?.needs_review?`${blocked?'<p>이 결과로 어느 설명이 맞는지 정하지 않습니다. 기록한 해석의 전제를 먼저 확인합니다.</p>':'<p>원래 해석에는 재검토할 전제가 남아 있습니다. 아래 비교는 명시한 두 설명에만 해당합니다.</p>'}${list(interpretation.explanations)}`:'';
  const comparison=blocked?'':separating.length?`<p>명시한 예측과 조건이 성립하면, 비교한 두 설명 중 더 잘 맞는 설명:</p>${list(separating.map(p=>`${reviewExplanationLabel(p.compatible_explanation,review)} (비교 대상: ${reviewExplanationLabel(p.excluded_explanation,review)})`))}`:'<p>이 결과만으로 특정 설명을 더 지지할 근거가 정해지지 않았습니다.</p>';
  return `<section class="outcome-effect" data-observation-outcome="${index}"><strong>${esc(interpretation?.needs_review?interpretation.label:hypothesisReviewLabels.interpretation[outcome.interpretation]??'해석 조건 미확인')}</strong>${warning}${comparison}${unresolved.length?`<p>아직 비교할 수 없는 설명 쌍:</p>${list(unresolved.map(p=>`${reviewExplanationLabel(p.left,review)} · ${reviewExplanationLabel(p.right,review)}`))}`:''}${(outcome.pairs??[]).some(p=>p.requires_joint_prediction)?'<p>함께 성립할 수 있는 설명이 있습니다. 결합된 설명의 예상도 확인해야 합니다.</p>':''}${(outcome.pairs??[]).some(p=>p.retrospective)?'<p class="small muted">관측 뒤에 구성한 예상이 포함됩니다. 독립적인 사전 예측 시험과 구별해야 합니다.</p>':''}</section>`;
}
