function reasoningPrediction(p){
  if(p.kind==='direction')return {increase:'증가',no_change:'변화 없음',decrease:'감소',presence:'검출됨',absence:'검출되지 않음'}[p.value];
  return `${p.lower_inclusive?'[':'('}${p.lower??'−∞'}, ${p.upper??'∞'}${p.upper_inclusive?']':')'}`;
}

function renderReasoningDesign(h){
  const d=h?.reasoning_design;
  if(!d)return '';
  const review=state.reasoning_design_review;
  const cards=[...(review?.context?.cards??[]),...(review?.context?.perspectives??[])];
  const roles={intervention:'개입군',reference:'기준군'};
  const outcomes={supports:'예상과 맞음',refutes:'가설을 반박함',inconclusive:'아직 구별되지 않음',experiment_failure:'실험이 유효하지 않음'};
  return `<section class="reasoning-design" data-reasoning-design="${esc(h.id)}">
    <h4>이 설명을 어떻게 시험하는가</h4>
    <p><strong>가설</strong> ${esc(d.H1)}</p><p><strong>비교할 설명</strong> ${esc(d.H0)}</p>
    <p><strong>시험 대상</strong> ${esc(d.specimen)}</p>
    <div class="table-scroll reasoning-condition-scroll"><table class="reasoning-conditions"><thead><tr><th scope="col">조건</th>${d.arms.map(a=>`<th scope="col">${roles[a.role]}</th>`).join('')}<th scope="col">비교 방식</th></tr></thead><tbody>${d.factors.map(f=>`<tr><th scope="row">${esc(f.name)}</th>${d.arms.map(a=>`<td data-label="${roles[a.role]}">${esc(a.levels.find(x=>x.factor_id===f.id)?.value??'미확인')}</td>`).join('')}<td data-label="비교 방식">${f.id===d.changed_variable_id?'이 조건만 바꿈':'동일하게 유지'}</td></tr>`).join('')}</tbody></table></div>
    <p><strong>측정</strong> ${esc(d.readout.name)} · ${esc(d.readout.contrast)} · ${esc(d.readout.unit)} · ${esc(d.readout.timepoint)}</p>
    <div class="table-scroll"><table><thead><tr><th>설명</th><th>같은 측정에서의 예상</th></tr></thead><tbody><tr><td>${esc(d.H1)}</td><td>${esc(reasoningPrediction(d.predictions.H1))}</td></tr><tr><td>${esc(d.H0)}</td><td>${esc(reasoningPrediction(d.predictions.H0))}</td></tr></tbody></table></div>
    <p class="small muted">${d.prediction_basis.origin==='proposed'?'검증할 설계 가정입니다.':'연결한 원자료에서 보고한 예상입니다.'} ${esc(d.prediction_basis.rationale)}</p>
    <details class="outcome-details"><summary>비교가 유효하기 위한 통제</summary>${d.controls.map(c=>`<p><strong>${esc(c.description)}</strong><br>${esc(c.validity_criterion)}</p>`).join('')}</details>
    <p><strong>가설을 반박하는 결과</strong> 위 통제가 모두 유효하고, 같은 측정에서 ‘${esc(reasoningPrediction(d.predictions.H0))}’가 사전 판정 기준을 충족함.</p>
    <p><strong>실험 자체의 실패</strong> 위 통제 중 하나라도 유효성 기준을 충족하지 못하면 가설 반박으로 해석하지 않습니다.</p>
    <details class="outcome-details"><summary>모델의 결과 해석 설명 · 위 판정과의 일치 검토 필요</summary><p>${esc(d.refuting_result.description)}</p><p>${esc(d.experiment_failure.description)}</p></details>
    <details class="outcome-details"><summary>결과별 다음 행동</summary>${Object.entries(outcomes).map(([k,label])=>`<p><strong>${label}</strong><br>${esc(d.next_actions[k])}</p>`).join('')}</details>
    ${d.unresolved_requirements.length?`<h4>실행 전에 정할 것</h4>${list(d.unresolved_requirements)}`:''}
    <details class="outcome-details"><summary>이 비교로 알 수 있는 범위</summary>${list(d.interpretation_limits)}<p class="small muted">두 설명의 예측과 고정 조건을 함께 확인하세요. 실행할 모델·대조군·측정법은 아래 적용 범위에 맞춰 정합니다.</p></details>
    ${d.cards_used.length?`<details class="outcome-details reasoning-cards"><summary>이 가설에 사용한 추론 관점 ${d.cards_used.length}개</summary>${d.cards_used.map(use=>{const originalCard=cards.find(c=>c.id===use.id);const card=typeof reasoningCardView==='function'?reasoningCardView(originalCard):originalCard;return `<article><h4>${esc(card?.title_ko??'원래 실행의 카드 확인 필요')}</h4><p>${esc(use.application)}</p>${card?`<p class="small muted">${esc(card.principle)}</p><p class="small">이 관점의 적용 조건과 원출처를 확인할 수 있습니다.</p>${originalCard?.detail_function==='read_reasoning_principle'?button('ui-reasoning-principle','적용 조건·판단 흐름·원출처 보기',`data-id="${esc(use.id)}"`,'link-button small'):''}${card.worked_examples.map(e=>`<details><summary>${esc(e.case_id)} 사례와 한계</summary><p>${esc(e.observation_to_decision)}</p>${Array.isArray(e.limits)?list(e.limits):`<p>${esc(e.limits)}</p>`}${e.source_refs.map(s=>`<p><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a></p>`).join('')}</details>`).join('')}`:''}</article>`;}).join('')}</details>`:''}
  </section>`;
}

function reasoningCheckHypothesis(check){
  return state.decision?.research_loop?.hypotheses?.find(h=>h.id===check.design_hypothesis_id);
}
