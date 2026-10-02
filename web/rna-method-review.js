// Actual analysis evidence; this view never publishes a research decision.
function renderRnaMethodReview(result) {
  const table = (headers, rows) => `<div class="table-scroll"><table><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(value => `<td>${typeof value === 'number' ? number(value) : esc(value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const groups = result.comparisons ?? {};
  const repaired = result.report_version >= 2;
  const lengthHeaders = ['조건','원 평균 차이','최근접 매칭', ...(repaired ? ['동점 배분 매칭'] : []), '층별 표준화','GAM'];
  return `<div class="rna-method-review">
    <p class="section-mark">실제 분석</p>
    <p class="limit">실제 계산의 검토 메모입니다. 이전 연구 판단은 보존되며 새 근거를 반영한 판단 검토가 필요합니다.</p>
    <h3>${esc(result.interpretation?.headline)}</h3>
    ${list(result.interpretation?.supported)}
    <h3>길이 차이를 보정해도 감소하는가</h3>
    <p class="small muted">같은 목표 유전자 집합에서 seed군−배경군의 평균 log₂ FC를 비교했습니다. 음수는 seed군의 상대적 감소를 뜻합니다.</p>
    ${table(lengthHeaders, (groups.length ?? []).map(r => [r.label, r.original, r.matching, ...(repaired ? [r.fractional_ties] : []), r.stratified, r.gam]))}
    <p class="limit">${repaired ? '동점 배분 매칭은 세 입력 순서에서 같은 결과였습니다. 수치 허용오차를 포함한 실제 저자 구현을 검산했으며, 이 수리가 모든 교란을 제거했다는 뜻은 아닙니다.' : '효과 크기는 대조 유전자 선택에 민감합니다.'} 이 표에는 동물 단위 p값이나 신뢰구간을 붙이지 않았습니다.</p>
    ${result.distribution_review ? list(result.distribution_review) : ''}
    <h3>동물 표본 변동을 고려해도 근거가 강한가</h3>
    ${table(['조건','CAMERA 방향','상관 추정 모드 양측 p','동물 점수 Holm p 범위'], (groups.dependence ?? []).map(r => [r.label, r.direction, r.camera_p, r.animal_holm_range]))}
    <p class="limit">CAMERA와 동물 점수는 서로 다른 질문의 검정입니다. CAMERA에는 길이 균형 가중치를 적용하지 않았고, 동물 배치의 교환가능성도 미확정입니다. 효과가 없다고 확정한 결과가 아닙니다.</p>
    <h3>특정 seed 서열이 두드러지는가</h3>
    ${table(['조건','cWords 감소 방향 순위','Sylamer 배경 보정 후 순위'], (groups.motif ?? []).map(r => [r.label, r.cwords_rank, r.sylamer_rank]))}
    <p class="limit">서열 후보의 탐색 순위입니다. 두 방법의 점수와 검정 조건이 달라 순위를 합산하지 않습니다. 동물 수준의 확증이나 직접 결합의 증거도 아닙니다.</p>
    ${result.reference_review ? `<h3>참조를 바꾸면 무엇이 달라지는가</h3>${list(result.reference_review)}` : ''}
    ${groups.a1 ? `<h3>새로 발견한 A1의 감소도 남는가</h3>
      <p class="small muted">A1-only와 세 선택 site가 없는 유전자를 비교한 후속 탐색입니다. 같은 참조 안에서 목표 집합을 고정했습니다.</p>
      ${table(['참조','A1 목표 유전자','범위 제외','길이 보정','길이·AU 보정'], groups.a1.map(r => [r.label,r.target_Q,r.excluded_target,r.length,r.length_AU]))}
      <p class="limit">발견에 사용한 자료로 다시 분석했습니다. AU 조정 뒤에도 감소 방향은 남지만, 직접 결합이나 독립 확증을 뜻하지 않습니다.</p>` : ''}
    ${groups.shrinkage ? `<h3>효과 크기는 추정 방식에 얼마나 민감한가</h3>
      ${table(['조건','축소 추정 MAP','비축소 추정 MLE'], groups.shrinkage.map(r => [r.label,r.MAP,r.MLE]))}
      <p class="limit">같은 유전자와 동점 배분 가중치를 사용한 평균 log₂ FC 차이입니다. MLE를 정답으로 취급하지 않습니다.</p>` : ''}
    <h3>새 관측이 바꾼 다음 확인</h3>
    ${list(result.next_actions)}
    <details class="meta-details"><summary>각 계산의 질문·조건·남은 한계</summary>${table(['계산','확인한 내용','남은 조건'], (result.rows ?? []).map(r => [r.method, r.observation, r.limit]))}</details>
  </div>`;
}
