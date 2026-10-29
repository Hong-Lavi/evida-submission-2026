// Retained measurements, generated structures and pending comparisons stay distinct.
const qualificationStatusLabels = {
  proposed_unmeasured: '출처·구조 연결됨 · 새 비교 전',
  stereo_resolution_needed: '입체정보 확인 필요',
  identity_hold: '구조 확인 전 비교 보류',
  source_or_parent_unresolved: '출처·측정 조건 확인 필요',
};
const qualificationIssueLabels = {
  assay_context_unresolved: '원 측정의 표적·시험 조건 확인 필요',
  assay_context_incomplete: '원 측정값은 연결됐지만 시험 조건이 불완전함',
  original_measurement_source_unresolved: '측정 원행과 구조의 연결 확인 필요',
  proposal_structure_unresolved: '후보 구조를 해석할 수 없어 확인 필요',
  actual_generation_parent_unresolved: '실제 생성 부모 확인 필요',
  protected_core_changed: '보존하기로 한 부모 골격이 달라짐',
  parent_core_stereo_lost_or_changed: '부모의 명시된 입체정보가 소실되거나 달라짐',
  parent_core_unavailable: '부모 골격 확인 필요',
};
if (typeof SCIENCE_LABELS !== 'undefined') SCIENCE_LABELS.proposal_qualification = '후보의 원 측정·구조 검토';

function qualificationRecord(proposalId) {
  if (typeof state === 'undefined' || !state) return null;
  return [...state.artifacts].reverse().find(a => a.kind === 'proposal_qualification'
    && a.meta?.result_status === 'succeeded' && a.meta?.arguments?.artifact_id === proposalId) || null;
}
function qualificationCounts(summary) {
  return Object.entries(summary?.status_counts || {}).map(([key, count]) =>
    `${qualificationStatusLabels[key] || key} ${count}개`).join(' · ');
}
function proposalQualificationEntry(proposalId) {
  if (!proposalId || typeof state === 'undefined' || !state) return '';
  const retained = qualificationRecord(proposalId);
  const pending = state.jobs?.some(j => j.kind === 'proposal_qualification'
    && ['queued', 'running'].includes(j.status) && j.request?.artifact_id === proposalId);
  return retained
    ? `<div class="proposal-qualification-entry"><p class="small">${esc(qualificationCounts(retained.meta?.summary))}</p>${button('source', '원 측정·구조 검토 보기', `data-id="${esc(retained.id)}"`, 'link-button small')}</div>`
    : `<div class="proposal-qualification-entry">${button('science-qualify-proposals', pending ? '원 측정·구조 확인 중' : '원 측정·구조 확인하기', `data-id="${esc(proposalId)}" ${pending || busy ? 'disabled' : ''}`, 'small')}<p class="small muted">생성 부모·보고된 측정·입체정보를 대조합니다.</p></div>`;
}
function proposalQualificationCollection() {
  if (typeof state === 'undefined' || !state) return '';
  const results = state.artifacts.filter(a => a.kind === 'proposal_qualification'
    && a.meta?.result_status === 'succeeded' && qualificationRecord(a.meta?.arguments?.artifact_id)?.id === a.id);
  const pending = state.artifacts.filter(a => a.kind === 'analogue_proposal'
    && a.meta?.result_status === 'succeeded' && a.meta?.summary?.returned > 0 && !qualificationRecord(a.id));
  if (!results.length && !pending.length) return '';
  return `<section class="panel" aria-label="후보의 원 측정과 구조 검토"><h3>후보의 원 측정·구조</h3>${results.map(a => `<p>${esc(qualificationCounts(a.meta?.summary))} ${button('source', '비교 조건 보기', `data-id="${esc(a.id)}"`, 'link-button small')}</p>`).join('')}${pending.length ? `<details ${!results.length ? 'open' : ''}><summary>원 측정 검토 전 생성 집합 ${pending.length}개</summary>${pending.map(a => `<p class="small">생성 후보 ${esc(a.meta.summary.returned)}개 · ${esc(new Date(a.created).toLocaleString('ko-KR'))}</p>${proposalQualificationEntry(a.id)}`).join('')}</details>` : ''}<p class="small muted">기존 추천 순서와 모든 후보를 보존합니다. 이 검토는 실제 활성 측정이 아닙니다.</p></section>`;
}
async function qualifyProposalsAction(node) {
  if (busy) return;
  const wid = state.id;
  busy = true; node.disabled = true; actionError = '';
  try {
  const view = await api(`/api/workspaces/${encodeURIComponent(wid)}/artifacts/${encodeURIComponent(node.dataset.id)}?offset=0&limit=1`);
  if (state?.id !== wid) throw Error('연구가 바뀌었습니다. 현재 연구에서 다시 선택해 주세요.');
  const sourceId = view.result?.source_artifact_id;
  if (!sourceId) throw Error('생성 결과의 원출처 연결을 먼저 확인해 주세요.');
  await runTool('proposal_qualification', {artifact_id: node.dataset.id, source_artifact_id: sourceId});
  } catch (error) { actionError = error.message; notice(error.message); }
  finally { busy = false; render(); }
}
function qualificationConditionFields(context) {
  if (!context || !Object.keys(context).length) return '<p class="small">원 측정 조건 미확인</p>';
  const values = {...context, ...(context.description_bound_conditions || {})};
  const labels = {assay_id:'시험 ID', assay_chembl_id:'시험 ID', target:'측정 표적', target_id:'표적 ID',
    description:'시험 설명', assay_description:'시험 설명', species:'종', organism:'종',
    target_organism:'표적 생물종', isoform:'단백질형', format:'측정 방식', substrate:'기질',
    substrate_concentration:'기질 농도', temperature:'온도', duration:'시간', incubation:'반응 시간',
    endpoint:'측정값', readout:'판독', source_url:'원문 주소', cAMP_final_nM:'cAMP 농도 · nM',
    enzyme_incubation:'효소 반응 조건', preincubation_minutes:'사전 반응 · 분', dose_points:'농도 수',
    replication_wording:'원문 반복 수 표기', buffer:'완충액', pH:'pH', document_id:'문서 ID', patent_id:'특허 ID'};
  const rows = Object.entries(labels).filter(([key]) => values[key] !== undefined && values[key] !== null && values[key] !== '')
    .map(([key, label]) => `<dt>${esc(label)}</dt><dd>${esc(typeof values[key] === 'object' ? JSON.stringify(values[key]) : values[key])}</dd>`).join('');
  return rows ? `<dl class="context-grid">${rows}</dl>${context.unresolved_before_experiment?.length ? '<p class="small">정확한 농도별 값·시료 준비·순도·측정 정밀도는 추가 확인이 필요합니다.</p>' : ''}` : '<p class="small">구체 시험 조건은 아래 원자료에서 확인하세요.</p>';
}
function qualificationParent(parent) {
  const original = parent.original_parent || {}, label = original.label || {};
  const values = label.source_values_nm || [];
  const observations = (parent.reported_measurements || parent.original_measurements || []).map(o => {
    const original = o.original_measurement || o;
    return {...(original.raw || {}), ...original, assay_id: o.assay_id || original.assay_id,
      assay_description: original.assay_description || o.assay_context?.assay_description || o.assay_context?.description,
      measurement_source_ref: o.source_ref};
  });
  const reports = values.length ? `<p><strong>원 보고값 · IC50</strong> ${values.map(x => `${esc(x)} nM`).join(' · ')}${label.activity_ids?.length ? ` <span class="small">(측정 기록 ${esc(label.activity_ids.join(', '))})</span>` : ''}</p>` : '';
  const observed = observations.length ? `<div class="table-scroll"><table><thead><tr><th>측정 종류</th><th>원 보고값</th><th>시험·조건</th></tr></thead><tbody>${observations.map(o => `<tr><td>${esc(o.standard_type || o.endpoint || o.affinity_type || '확인 필요')}</td><td>${esc(o.standard_relation || o.reported_relation || '')} ${esc(o.standard_value ?? o.reported_value_nm ?? o.raw_value ?? o.affinity ?? '확인 필요')} ${esc(o.standard_units || o.reported_units || (o.reported_value_nm !== undefined ? 'nM' : '단위 미확인'))}</td><td>${esc(o.assay_chembl_id || o.assay_id || '시험 ID 미확인')} ${esc(o.assay_description || '')}</td></tr>`).join('')}</tbody></table></div>` : '';
  const parentLabel = parent.exact_match ? '원출처의 동일 구조' : parent.parent_kind === 'generated_unmeasured' ? '출발 구조 · 생성 중간체' : '출발 화합물';
  return `<article class="source-paragraph"><h4>${parentLabel} · ${qualificationId(parent.parent_id)}</h4>${reports}${observed}${!reports && !observed ? '<p>이 구조의 원 측정값은 연결된 자료에서 확인이 필요합니다.</p>' : ''}${parent.source_ref?.artifact_id ? sourceLinks([parent.source_ref.artifact_id]) : ''}${sourceLinks([...new Set(observations.map(o=>o.measurement_source_ref?.artifact_id).filter(Boolean))])}${parent.assay_context || original.assay_context ? qualificationConditionFields(parent.assay_context || original.assay_context) : ''}<details><summary>구조·원 기록</summary><code class="proposal-smiles">${esc(original.smiles || '')}</code>${json(original)}</details></article>`;
}
function qualificationId(id) { return `<span title="${esc(id)}">${esc(id?.length > 24 ? id.slice(0, 12) + '…' : id)}</span>`; }
function qualificationCandidate(row) {
  const prediction = row.original_prediction || {};
  const p = prediction.predicted_pIC50 ?? prediction.predicted_p_activity;
  const exact = row.exact_source_matches || [];
  const problems = (row.issues || []).map(x => qualificationIssueLabels[x] || x);
  return `<details class="source-paragraph" data-qualification-candidate="${esc(row.candidate_id)}"><summary><strong>${qualificationId(row.candidate_id)}</strong> · ${esc(qualificationStatusLabels[row.proposal_status] || row.proposal_status)}</summary>
    ${typeof structureThumb === 'function' ? structureThumb(row) : ''}<code class="proposal-smiles">${esc(row.original_smiles || row.smiles || '')}</code>
    <p>${p !== null && p !== undefined ? `<strong>후보 예측값</strong> ${esc(Number.isFinite(Number(p)) ? Number(p).toFixed(3) : p)} · ${prediction.predicted_pIC50 !== undefined ? 'pIC50' : '원 모델의 p활성값'} · 새 측정값 아님` : '이 행에 저장된 후보 예측값 없음'}</p>
    ${exact.length ? `<p class="notice-inline">원출처의 동일 구조 ${exact.length}건과 일치합니다. 기존 측정은 아래에 남고, 이번 부모–후보 비교는 아직 수행되지 않았습니다.</p>${exact.map(m => qualificationParent({parent_id:m.parent_id,source_ref:m.source_ref,original_parent:m.original_parent,exact_match:true})).join('')}` : ''}
    ${problems.length ? `<ul>${problems.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    ${row.unspecified_stereo?.length ? `<p>정해지지 않은 입체정보 ${row.unspecified_stereo.length}곳을 확인해야 합니다.</p>` : ''}
    ${(row.actual_parents || []).map(qualificationParent).join('') || '<p>실제 생성 부모 연결이 미확인입니다. 최근접 구조를 생성 부모로 대신하지 않습니다.</p>'}
    ${Object.keys(row.reported_assay_context || {}).length ? qualificationConditionFields(row.reported_assay_context) : ''}
    <p><strong>다음 비교</strong> 부모의 원 측정값과 시료·시험 조건을 확인하고 같은 조건에서 후보와 비교합니다. 부모 결과 재현 여부와 판독 간섭도 함께 확인하세요.</p>
    ${row.original_row_locator?.artifact_id ? sourceLinks([row.original_row_locator.artifact_id]) : ''}
    <details><summary>변환·조건 검토의 전체 기록</summary>${json(row)}</details></details>`;
}
function proposalQualificationTable(result) {
  const summary = result.summary || {}, rows = result.rows || [];
  const aid = typeof selected !== 'undefined' ? selected : null;
  const chosen = result.selected_preview || [];
  const selection = chosen.length ? `<details open><summary>기존 선택 ${summary.selected ?? chosen.length}개 · 원 순서</summary><p class="small">${esc(qualificationCounts({status_counts: summary.selected_status_counts}))}</p><div class="table-scroll"><table><thead><tr><th>원 순서</th><th>후보</th><th>비교 전 확인</th></tr></thead><tbody>${chosen.map(r => `<tr><td>${esc(r.original_rank)}</td><td>${aid ? button('source', qualificationId(r.candidate_id), `data-id="${esc(aid)}" data-source-offset="${esc(r.row_index)}"`, 'link-button small') : qualificationId(r.candidate_id)}</td><td>${esc(qualificationStatusLabels[r.proposal_status] || r.proposal_status)}</td></tr>`).join('')}</tbody></table></div><p class="small">후보를 누르면 해당 구조와 출발 화합물의 측정값을 엽니다.</p></details>` : '';
  return `<section class="proposal-qualification-result"><h3>후보의 원 측정·구조 검토</h3><p>${esc(qualificationCounts(summary))}</p>
    <p>보고된 부모 측정과 후보 예측을 나란히 보며 다음 비교를 정합니다. 기존 추천 순서는 유지됩니다.</p>
    ${summary.core_preservation_required ? '<p class="small">원 생성 계약이 지정한 부모 골격·입체정보 보존 조건을 대조했습니다.</p>' : ''}
    ${selection}
    ${Object.keys(result.reported_assay_context || {}).length ? `<details><summary>원 측정의 표적·시험 조건</summary>${qualificationConditionFields(result.reported_assay_context)}</details>` : ''}
    ${rows.map(qualificationCandidate).join('')}
    <div class="pagination"><span>${esc((result.offset ?? 0) + (rows.length ? 1 : 0))}–${esc((result.offset ?? 0) + rows.length)} / ${esc(result.total_rows ?? summary.rows ?? rows.length)}개</span>${button('prev','이전',(result.offset ?? 0) === 0 ? 'disabled' : '', 'small')}${button('next','다음',result.has_more ? '' : 'disabled','small')}</div>
    <p class="limit">연결됨은 신규 활성이나 실험 준비 완료의 판정이 아닙니다. 원자료와 미확인 조건을 함께 보존합니다.</p></section>`;
}
