// Every structure on this screen is untested, and the screen has to say the things that are easy
// to leave out: that the model refused to score, that a number is an extrapolation, and that a
// docking comparison rejected a row.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const context = vm.createContext({
  esc: s => String(s).replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])),
  SCIENCE_LABELS: {},
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/proposal-table.js'), 'utf8'), context);
const {proposalTable, proposalRows, proposalModelVerdict, proposalSearchTrajectory} = context;

const usableModel = {
  usable: true,
  input_review: {selected_endpoint: 'IC50', point_fit_structures: 1983, retained_bound_records: 17},
  summary: {held_out_spearman: 0.58, minimum_spearman_to_use: 0.3, trained_on: 1488,
            held_out: 495, scaffolds: 873, sources: {chembl: 1983}, pooled_assay_types: []},
};
const row = (over = {}) => ({
  smiles: 'COc1ccc(C(=O)Nc2c(Cl)cncc2OC)cc1OCC1CC1', candidate_id: 'proposed-1',
  transformed_from: 'CHEMBL103', transformation: 'Cl[*:1]>>CO[*:1]', context_radius: 1,
  MolWt: 402.8, SA_score: 2.4, QED: 0.71, ...over});
const result = (over = {}) => ({
  method: 'crem_context_constrained_fragment_transformation',
  generator: {method: 'crem_context_constrained_fragment_transformation',
              fragment_database: {compounds: 24, radii: [1, 2, 3], set_name: 'retrieved'}},
  summary: {retrieved_inputs: 24, enumerated: 380, returned: 6,
            dropped: {property_window: 31, structural_alert: 172}},
  rows: [row()], limits: ['제안 구조는 열거 결과입니다.'], ...over});

test('It identifies structures proposed in this calculation and their next experimental check', () => {
  const html = proposalTable(result());
  assert.match(html, /계산으로 제안한 구조/);
  assert.match(html, /회수한 화합물 24개로 그때 만들었습니다/, 'the fragment source is stated');
  assert.match(html, /문맥 반경 1, 2, 3/);
});

test('Each row says which compound was changed and how', () => {
  const html = proposalRows(result());
  assert.match(html, /CHEMBL103/);
  assert.match(html, /Cl\[\*:1\]&gt;&gt;CO\[\*:1\]/, 'the exact transformation is readable');
  assert.match(html, /문맥 반경 1/);
});

test('A refused activity model is stated, and no score column appears', () => {
  const refused = result({activity_model: {usable: false, meaning: '미확인 골격을 예측하지 못했습니다.'}});
  const html = proposalTable(refused);
  assert.match(html, /활성 평가에 필요한 자료/);
  assert.match(html, /미확인 골격을 예측하지 못했습니다/);
  assert.doesNotMatch(html, /<th>예측 활성<\/th>/, 'no score column without scores');
});

test('A model that passed shows what it passed with, and calls the number an estimate', () => {
  const html = proposalModelVerdict(result({activity_model: usableModel}).activity_model
    ? {activity_model: usableModel} : {});
  assert.match(html, /순위 상관\s*0\.58/);
  assert.match(html, /기준 0\.3/);
  assert.match(html, /실제 활성은 후속 실험/);
});

test('A prediction outside the training chemistry is marked as extrapolation', () => {
  const scored = result({activity_model: usableModel,
                         rows: [row({predicted_p_activity: 7.4, nearest_training_similarity: 0.22,
                                     inside_applicability: false}),
                                row({candidate_id: 'proposed-2', predicted_p_activity: 6.9,
                                     nearest_training_similarity: 0.71, inside_applicability: true})]});
  const html = proposalRows(scored);
  assert.match(html, /적용 범위 밖 · 외삽/);
  assert.match(html, /학습 유사도 0\.71/);
});

test('The docking verdict is shown per row, including the rejection', () => {
  const docked = result({
    rows: [row(), row({candidate_id: 'proposed-2'})],
    proposal_comparison: {rows: [
      {candidate_id: 'proposed-1', keep: true, reason: '부모보다 낮은 점수입니다.'},
      {candidate_id: 'proposed-2', keep: false, reason: '크기로 설명되는 차이로 봅니다.'}]}});
  const html = proposalRows(docked);
  assert.match(html, /계산 비교 기준 통과/);
  assert.match(html, /계산 비교 기준 미충족/);
  assert.match(html, /크기로 설명되는 차이/);
});

test('A generated structure does not imply a pending docking step', () => {
  assert.doesNotMatch(proposalRows(result()), /도킹 전|계산상 포즈 비교/);
});

test('The actual input endpoint and preserved bounds are displayed', () => {
  const html = proposalModelVerdict({activity_model: usableModel});
  assert.match(html, /학습 측정 종류: IC50/);
  assert.match(html, /경계값 17건/);
});

test('Historical predictions retain their values and carry the data correction status', () => {
  const old = {...usableModel}; delete old.input_review;
  const data = result({activity_model: old, rows: [row({predicted_p_activity: 7.4})]});
  assert.match(proposalModelVerdict(data), /이전 데이터 처리 방식/);
  assert.match(proposalRows(data), /이전 활성 예측 · 재검토 대상/);
  assert.match(proposalRows(data), /7.4/);
});

test('The search trajectory shows each round and how much left the applicability limit', () => {
  const searched = result({activity_model: usableModel, guided_search: {
    ran: true, rows: [row({predicted_p_activity: 7.1, inside_applicability: true,
                           nearest_training_similarity: 0.6})],
    history: [{round: 1, proposed: 40, kept: 8, best_predicted_p_activity: 6.9,
               kept_inside_applicability: 8, median_nearest_training_similarity: 0.72},
              {round: 2, proposed: 30, kept: 8, best_predicted_p_activity: 7.1,
               kept_inside_applicability: 5, median_nearest_training_similarity: 0.41}],
    summary: {rounds: 2, best_predicted_p_activity: 7.1, best_measured_p_activity_in_training: 8.2,
              kept_outside_applicability: 3},
    reading: '점수가 오르면 탐색이 작동한 것입니다.'}});
  const html = proposalSearchTrajectory(searched);
  assert.match(html, /5 \/ 8/, 'how many of the kept rows stayed inside the limit');
  assert.match(html, /학습 화합물의 실제 최고값 8\.2/);
  assert.match(html, /적용 범위 밖 3개/);
});

test('A search that did not run says why instead of showing an empty table', () => {
  const html = proposalSearchTrajectory({guided_search: {ran: false, meaning: '모델이 기준 미달입니다.'}});
  assert.match(html, /돌지 않았습니다/);
  assert.match(html, /기준 미달/);
  assert.doesNotMatch(html, /<table/);
});

test('Shortlist size is not invented filter coverage and unknown execution order stays unknown', () => {
  const html = proposalTable(result({activity_model: {...usableModel, scoring: {scored: 1}}}));
  assert.match(html, /구조 기준으로 추린 6개/);
  assert.doesNotMatch(html, /필터 통과/);
  assert.match(html, /순서는 이 기록에 명시되지 않았습니다/);
  assert.doesNotMatch(html, /활성 예측값은 그 뒤에 붙였/);
});

test('An explicit structural shortlist precedes scores, but guided rows retain their different selection', () => {
  const data = result({activity_model: {...usableModel, scoring: {scored: 1}},
    proposal_selection: {shortlist_count: 6, filtered_count: 100,
      shortlist_basis: ['retrieved_structure_similarity', 'QED'], activity_scoring_stage: 'after_structural_shortlist'}});
  let html = proposalTable(data);
  assert.match(html, /필터 통과 100개 → 구조 기준으로 추린 6개/);
  assert.match(html, /구조 유사도와 QED 순서로 먼저 추린/);
  assert.match(html, /활성 예측값은 그 뒤에 붙였/);
  data.guided_search = {ran: true, rows: [], history: [], summary: {}};
  html = proposalTable(data);
  assert.doesNotMatch(html, /이 후보 목록을 활성 점수로 선택하거나 정렬한 것은 아닙니다/);
});

test('Source provenance is read from the bound artifact, not inferred from the parser key', () => {
  context.state = {artifacts: [{id: 'source-1', title: 'Public curated training pool',
    meta: {source_reading: 'Retained benchmark training split, not a live source query.'}}]};
  try {
    const html = proposalModelVerdict({source_artifact_id: 'source-1', activity_model: usableModel});
    assert.match(html, /Public curated training pool/);
    assert.match(html, /not a live source query/);
    assert.match(html, /입력 레코드 형식 chembl 1983/);
    assert.doesNotMatch(html, /자료원 chembl/);
  } finally { delete context.state; }
});
