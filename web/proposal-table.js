// Structures this run proposed, and what is known about each one.
//
// Everything on this screen is untested: the structures were assembled from what the research
// retrieved, the number beside them is a model's estimate of a public assay value, and none of
// them has been made. So the card leads with that, and each column says where its value came
// from - which compound was transformed, by what change, how far the result has drifted from the
// compounds the model learned on, and whether the docking comparison kept it.
//
// The verdict the screen must never hide is the refusal: when the activity model could not
// predict compounds whose scaffolds it had not seen, there are no scores at all, and saying so
// is the result.
if (typeof SCIENCE_LABELS !== 'undefined') SCIENCE_LABELS.analogue_proposal = '공개 화합물에서 설계한 후보';

function proposalModelVerdict(result) {
  const model = result.activity_model;
  if (!model) return '';
  const review = model.input_review;
  const preparation = review ? `<p class="small">학습 측정 종류: ${esc(review.selected_endpoint || '확인 중')} ·
    정확한 보고값의 구조 ${esc(review.point_fit_structures)}개 ·
    원자료에 보존한 경계값 ${esc(review.retained_bound_records)}건</p>` : '';
  if (!model.usable) {
    return `<p class="notice-inline proposal-refusal"><strong>활성 평가에 필요한 자료를 확인해 주세요.</strong>
      ${esc(model.meaning || '')}</p>${preparation}`;
  }
  const summary = model.summary || {};
  const sources = Object.entries(summary.sources || {}).map(([name, count]) => `${name} ${count}`).join(' · ');
  return `<div class="proposal-model">
    <p><strong>${review ? '골격을 나눈 공개 활성 자료 예측 시험' : '이전 데이터 처리 방식의 예측 기록 · 재검토 대상'}</strong> · 순위 상관
      ${esc(summary.held_out_spearman)} (기준 ${esc(summary.minimum_spearman_to_use)})</p>
    <p class="small muted">학습 ${esc(summary.trained_on)}개 · 시험 ${esc(summary.held_out)}개 ·
      골격 ${esc(summary.scaffolds)}종 · 자료원 ${esc(sources || '기록 없음')}
      ${summary.pooled_assay_types && summary.pooled_assay_types.length
        ? ` · 보고된 측정 종류 ${esc(summary.pooled_assay_types.join(', '))}` : ''}</p>
    ${preparation}<p class="limit">공개 시험 기록을 예측한 값입니다. 후보의 실제 활성은 후속 실험에서 확인합니다.</p></div>`;
}

function proposalSearchTrajectory(result) {
  const search = result.guided_search;
  if (!search) return '';
  if (!search.ran) {
    return `<p class="small muted">점수 유도 탐색은 돌지 않았습니다. ${esc(search.meaning || '')}</p>`;
  }
  const rows = (search.history || []).map(entry => `<tr>
    <td>${esc(entry.round)}</td><td>${esc(entry.proposed)}</td><td>${esc(entry.kept)}</td>
    <td>${entry.best_predicted_p_activity === null || entry.best_predicted_p_activity === undefined
          ? '—' : esc(entry.best_predicted_p_activity)}</td>
    <td>${entry.kept_inside_applicability === undefined ? '—'
          : `${esc(entry.kept_inside_applicability)} / ${esc(entry.kept)}`}</td>
    <td>${entry.median_nearest_training_similarity === null
          || entry.median_nearest_training_similarity === undefined
          ? '—' : esc(entry.median_nearest_training_similarity)}</td></tr>`).join('');
  const summary = search.summary || {};
  return `<details class="proposal-search" data-detail-key="guided-search"><summary>점수를 길잡이로 한 탐색 ${esc(summary.rounds ?? 0)}라운드</summary>
    <div class="table-scroll"><table><thead><tr><th>라운드</th><th>제안</th><th>남김</th>
      <th>최고 예측값</th><th>적용 범위 안</th><th>학습 집합과 유사도(중앙값)</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <p class="small">학습 화합물의 실제 최고값 ${esc(summary.best_measured_p_activity_in_training ?? '—')} ·
      탐색이 남긴 최고 예측값 ${esc(summary.best_predicted_p_activity ?? '—')} ·
      적용 범위 밖 ${esc(summary.kept_outside_applicability ?? 0)}개</p>
    <p class="limit">${esc(search.reading || '')}</p></details>`;
}

function proposalRows(result) {
  const rows = (result.guided_search && result.guided_search.ran && result.guided_search.rows.length)
    ? result.guided_search.rows : (result.rows || []);
  if (!rows.length) return '<p>제안된 구조가 없습니다.</p>';
  const comparison = ((result.proposal_comparison || {}).rows || [])
    .reduce((all, row) => Object.assign(all, {[row.candidate_id]: row}), {});
  const scored = rows.some(row => row.predicted_p_activity !== undefined);
  const compared = Object.keys(comparison).length > 0;
  const oldPredictions = result.activity_model && !result.activity_model.input_review;
  const cell = row => {
    const docked = comparison[row.candidate_id];
    return `<tr>
      <td>${typeof structureThumb === 'function' && row.smiles
            ? structureThumb({smiles: row.smiles, depiction: row.depiction}) : ''}
        <code class="proposal-smiles">${esc(row.smiles)}</code></td>
      <td>${esc(row.transformed_from || row.core_from || '—')}
        ${row.transformation ? `<small class="mono">${esc(row.transformation)}</small>` : ''}
        ${row.context_radius ? `<small class="muted">문맥 반경 ${esc(row.context_radius)}</small>` : ''}</td>
      <td>${esc(row.MolWt ?? '—')}<small class="muted">SA ${esc(row.SA_score ?? '—')} · QED ${esc(row.QED ?? '—')}</small></td>
      ${scored ? `<td>${row.predicted_p_activity === undefined ? '—' : esc(row.predicted_p_activity)}
        ${row.inside_applicability === false
          ? '<small class="proposal-outside">적용 범위 밖 · 외삽</small>'
          : row.nearest_training_similarity !== undefined
            ? `<small class="muted">학습 유사도 ${esc(row.nearest_training_similarity)}</small>` : ''}</td>` : ''}
      ${compared ? `<td>${docked ? (docked.keep === true ? '<strong>계산 비교 기준 통과</strong>'
                      : docked.keep === false ? '계산 비교 기준 미충족' : '비교 보류')
                   : '<span class="muted">계산 기록 없음</span>'}
        ${docked && docked.reason ? `<small class="muted">${esc(docked.reason)}</small>` : ''}</td>` : ''}</tr>`;
  };
  return `<div class="table-scroll"><table class="proposal-table"><thead><tr>
      <th>설계 구조</th><th>무엇을 바꿨나</th><th>계산 물성</th>${scored ? `<th>${oldPredictions ? '이전 활성 예측 · 재검토 대상' : '예측 활성'}</th>` : ''}
      ${compared ? '<th>출발 화합물과의 계산상 포즈 비교</th>' : ''}</tr></thead><tbody>${rows.map(cell).join('')}</tbody></table></div>`;
}

function proposalTable(result) {
  const summary = result.summary || {};
  const generator = result.generator || {};
  const database = generator.fragment_database;
  return `<section class="proposal-result">
    <p class="notice-inline"><strong>회수한 화합물에서 계산으로 제안한 구조입니다.</strong>
      출발 화합물 구조와 변형 내용을 따라가며, 합성·활성 확인은 후속 실험으로 연결합니다.</p>
    <p class="small">생성 방식: ${esc(generator.method || result.method || '기록 없음')}
      ${database ? ` · 조각 사전은 이 실행이 회수한 화합물 ${esc(database.compounds)}개로 그때 만들었습니다(문맥 반경 ${esc((database.radii || []).join(', '))})` : ''}
      ${result.generator_error ? ` · 첫 생성기가 실패해 대체 방식으로 돌았습니다: ${esc(result.generator_error)}` : ''}</p>
    <p class="small muted">회수 구조 ${esc(summary.retrieved_inputs ?? '—')}개 → 열거 ${esc(summary.enumerated ?? '—')}개 →
      필터 통과 ${esc(summary.returned ?? '—')}개
      ${summary.dropped ? ` · 걸러짐: ${esc(Object.entries(summary.dropped).map(([k, v]) => `${({property_window: '물성창', synthetic_accessibility: '합성 난이도', structural_alert: '구조 경보', unstable_motif: '불안정 구조'})[k] || k} ${v}`).join(' · '))}` : ''}</p>
    ${proposalModelVerdict(result)}
    ${proposalRows(result)}
    ${proposalSearchTrajectory(result)}
    ${(result.limits || []).length ? `<details class="proposal-limits"><summary>해석 범위와 다음 확인 ${esc(result.limits.length)}개</summary>
      <ul>${result.limits.map(line => `<li>${esc(line)}</li>`).join('')}</ul></details>` : ''}
  </section>`;
}
