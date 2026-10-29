// The stored review record, read by a person.
//
// This is what "선택지 검토" opens. It used to fall through to raw JSON, which is unreadable at
// exactly the moment someone is checking a judgement. Nothing here may summarise or reword the
// model's record: the reader is verifying it.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const context = vm.createContext({
  esc: s => String(s).replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])),
  sourceLinks: ids => `<span class="source-links">${ids.join(',')}</span>`,
  optionKinds: {mechanism: '질환 기전', molecule: '구조·활성 조회 물질'},
  optionStatus: {recommended: '추천', alternative: '대안', needs_evidence: '근거 확인 필요'},
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/review-record.js'), 'utf8'), context);
const {reviewRecordView} = context;

const basis = {
  grade: 'demonstrated',
  clauses: [{text: 'Galectin-3 억제가 폐섬유화를 줄인다', disease_match: 'animal_model',
             context: {disease: 'IPF', species: 'mouse', tissue: 'lung'},
             anchor: {artifact_id: 'art_paper', row_index: 0, quote: 'reduced bleomycin fibrosis'}}],
  missing_in_target_disease: [{claim: '사람 개입 연구 없음', reported_count: 0,
                               query_artifact_id: 'art_search'}],
};

const record = {
  question: '폐 기능 저하를 늦출 기전을 고른다',
  new_options: [{option_id: 'mechanism:gal3', kind: 'mechanism', label: 'Galectin-3 억제',
                 description: '섬유아세포 활성화를 낮춘다', source_ids: ['art_paper']}],
  assessments: [{option_id: 'mechanism:gal3', status: 'alternative', priority: null,
                 comparison_group: '', reason: '동물 개입 근거만 있다', next_action: '사람 1상을 찾는다',
                 support_source_ids: ['art_paper'], challenge_source_ids: ['art_against'],
                 uncertainties: ['용량이 확인되지 않았다'],
                 aspects: {disease_match: 0.75, clinical_precedent: 0.25,
                           evidence_grade: 0.75, actionability: null},
                 basis}],
  unsearched_scope: ['소아 환자'],
};

test('The review reads as a record, never as raw JSON', () => {
  const html = reviewRecordView(record, {});
  assert.doesNotMatch(html, /option_id|support_source_ids|\{"/, 'no field names leak to the reader');
  assert.match(html, /폐 기능 저하를 늦출 기전을 고른다/, 'the question it answered');
  assert.match(html, /Galectin-3 억제/);
  assert.match(html, /동물 개입 근거만 있다/, 'the recorded reason, unchanged');
  assert.match(html, /사람 1상을 찾는다/, 'the next action');
});

test('A clause shows the sentence it was anchored to, and where that observation came from', () => {
  const html = reviewRecordView(record, {});
  assert.match(html, /reduced bleomycin fibrosis/, 'the reader checks the paper, not us');
  assert.match(html, /IPF · mouse · lung/);
  assert.match(html, /동물 모델/, 'disease_match is named, not printed as a code');
  assert.doesNotMatch(html, /animal_model/);
  assert.match(html, /art_paper/, 'the source is reachable');
});

test('An unchecked axis reads as unchecked, never as a low score', () => {
  const html = reviewRecordView(record, {});
  assert.match(html, /미확인/);
  assert.doesNotMatch(html, /개입 가능성<\/span>\s*<span class="axis-value">가장 낮음/);
});

test('Target-disease gaps and the searches behind them are shown', () => {
  const html = reviewRecordView(record, {});
  assert.match(html, /목표 질환에서 비어 있는 것/);
  assert.match(html, /사람 개입 연구 없음/);
  assert.match(html, /조회 0건/);
  assert.match(html, /art_search/);
});

test('Contradicting evidence is shown beside the supporting evidence', () => {
  const html = reviewRecordView(record, {});
  assert.match(html, /반대 자료/);
  assert.match(html, /art_against/);
});

test('The basis check is reported as a comparison, not as a verdict on the science', () => {
  const clean = reviewRecordView(record, {basis_check: [
    {option_id: 'mechanism:gal3', status: 'passed', issues: [],
     clauses: [{clause_index: 0, status: 'verified'}], gaps: [{gap_index: 0, status: 'verified'}]}]});
  assert.match(clean, /모두 일치했습니다/);

  const failed = reviewRecordView(record, {basis_check: [
    {option_id: 'mechanism:gal3', status: 'issues_recorded', issues: ['clause_0_quote_not_in_row'],
     clauses: [{clause_index: 0, status: 'rejected', reason: 'quote_not_in_row', kind: 'article'}],
     gaps: []}]});
  assert.match(failed, /quote_not_in_row/);
  assert.match(failed, /주장이 틀렸다는 판정이 아닙니다/);
});

test('A record that only registered options says so rather than looking empty', () => {
  const html = reviewRecordView({question: 'q', new_options: record.new_options,
                                 assessments: [], unsearched_scope: []}, {});
  assert.match(html, /이번에 등록한 선택지 1개/);
  assert.match(html, /평가가 없다는 것이 제외라는 뜻은 아닙니다/);
});

test('An unsearched scope is recorded as unsearched, not as absence', () => {
  const html = reviewRecordView(record, {});
  assert.match(html, /소아 환자/);
  assert.match(html, /그곳에 아무것도 없다는 뜻이 아닙니다/);
});

test('Recorded text cannot inject markup', () => {
  const html = reviewRecordView({...record, question: '<img src=x onerror=alert(1)>'}, {});
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /&lt;img/);
});
