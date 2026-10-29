// The order shown must be the order computed. No first place is manufactured, the assumptions
// behind the weighting stay visible, and an unchecked axis is never drawn as a low score.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const context = vm.createContext({
  esc: s => String(s).replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])),
  button: (action, label, attrs, cls) => `<button data-action="${action}" class="${cls}">${label}</button>`,
  artifactName: id => id,
  document: {addEventListener() {}},location:{pathname:'/'},localStorage:{},
});
for (const file of ['../web/deployment.js','../web/external-links.js', '../web/source-display.js', '../web/research.js', '../web/mechanism-rank.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), context);
}
const {mechanismRankView} = context;

const ORDER = [{at_least_as_heavy: 'disease_match', as: 'clinical_precedent'},
               {at_least_as_heavy: 'evidence_grade', as: 'actionability'}];

const row = (id, tier, extra) => ({
  option_id: id, tier, label: id.replace(/^mechanism:/, ''), kind: 'mechanism',
  aspects: {disease_match: 1.0, clinical_precedent: 0.75, evidence_grade: 1.0, actionability: 0.5},
  unchecked_axes: [], challenge_source_ids: [], contradicted: false, sources: [], ...extra,
});

const ranking = extra => ({status: 'computed', stated_axis_order: ORDER,
                           rows: [], frontier: [], single_leader: null, ...extra});

test('A certified first place is shown as first, with its clauses and quotes', () => {
  const lead = row('mechanism:pde4b', 1, {
    basis: {grade: 'established',
            clauses: [{text: 'PDE4B 억제가 섬유화를 늦춘다',
                       anchor: {quote: 'nerandomilast reduced FVC decline'},
                       disease_match: 'target_disease',
                       context: {disease: 'IPF', species: 'human', tissue: 'lung'}}],
            missing_in_target_disease: []}});
  const html = mechanismRankView(ranking({rows: [lead, row('mechanism:other', 2)],
                                          frontier: ['mechanism:pde4b'],
                                          single_leader: 'mechanism:pde4b'}));
  assert.match(html, /1순위/);
  assert.doesNotMatch(html, /1위 미정/);
  assert.match(html, /PDE4B 억제가 섬유화를 늦춘다/);
  assert.match(html, /nerandomilast reduced FVC decline/, 'the anchored sentence is shown');
  assert.match(html, /확립 · 사람 개입 근거/);
  assert.match(html, /아래 순위 1개/);
});

test('With no certified first place the screen says so as a result, not an error', () => {
  const html = mechanismRankView(ranking({
    rows: [row('mechanism:a', 1), row('mechanism:b', 1)],
    frontier: ['mechanism:a', 'mechanism:b']}));
  assert.match(html, /1위 미정/);
  assert.match(html, /최상위 후보 2개/);
  assert.match(html, /오류가 아니라 지금 근거로 말할 수 있는 전부입니다/);
  assert.doesNotMatch(html, /<span class="rank-badge">1순위<\/span>/);
});

test('A withheld leader states why and keeps the partial order', () => {
  const html = mechanismRankView(ranking({
    rows: [row('mechanism:a', 1, {contradicted: true, challenge_source_ids: ['art_null']})],
    frontier: ['mechanism:a'], single_leader: null,
    single_leader_withheld: 'contradicting_evidence_recorded'}));
  assert.match(html, /반대 근거가 기록되어 1순위로 올리지 않았습니다/);
  assert.match(html, /부분순서 자체는 그대로 둡니다/);
  assert.match(html, /반대 근거 기록됨/);
});

test('An unchecked axis reads as unchecked, never as a low score', () => {
  const html = mechanismRankView(ranking({
    rows: [row('mechanism:a', 1, {aspects: {disease_match: 1.0, clinical_precedent: null,
                                            evidence_grade: 0.5, actionability: null},
                                  unchecked_axes: ['clinical_precedent', 'actionability']})],
    frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
  assert.match(html, /미확인/);
  assert.match(html, /미확인 축 · 임상 선례, 개입 가능성/);
  assert.doesNotMatch(html, /임상 선례<\/span>\s*<span class="axis-value">가장 낮음/);
});

test('An axis cell opens what its value was read off, and says what was not checked', () => {
  const basis = {grade: 'demonstrated',
                 clauses: [{text: '표적 억제가 섬유화 표지를 낮춘다', disease_match: 'animal_model',
                            anchor: {quote: 'reduced collagen deposition'}},
                           {text: '그 표지가 폐 기능과 연결된다', disease_match: 'target_disease'}],
                 missing_in_target_disease: [{claim: '목표 질환에서 시험한 기록이 없다', reported_count: 0}]};
  const ranked = ranking({rows: [row('mechanism:a', 1, {basis, aspects: {disease_match: 0.5,
                                                                        clinical_precedent: 0.25,
                                                                        evidence_grade: 0.75,
                                                                        actionability: null}})],
                          frontier: ['mechanism:a'], single_leader: 'mechanism:a'});
  mechanismRankView(ranked);  // loads the ranking the detail panel reads
  const target = ranked.rows[0];
  const applicability = context.mechanismAxisDetail(target, 'disease_match');
  assert.match(applicability, /동물 모델/, 'the clause contexts that set the value');
  assert.match(applicability, /가장 낮은 절/, 'and the rule that picked among them');
  assert.match(applicability, /순서를 정하는 데 쓰입니다/);
  assert.match(applicability, /목표 질환에서 시험한 기록이 없다/);
  assert.match(applicability, /단계 선택 자체를 검증하지는 않습니다/,
               'the panel must not imply the level itself was verified');

  const operations = context.mechanismAxisDetail(target, 'actionability');
  assert.match(operations, /순서를 정하지 않습니다/);
  assert.match(operations, /미확인은 0점이 아니며/, 'an unrecorded axis says so instead of showing a step');
  assert.doesNotMatch(operations, /기록된 값/);
});

test('The axis cells are buttons that name the option and axis they open', () => {
  const html = mechanismRankView(ranking({rows: [row('mechanism:a', 1)],
                                          frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
  assert.match(html, /data-action="mechanism-axis"[^>]*data-axis="disease_match"/);
  assert.match(html, /data-option="mechanism:a"/);
});

test('The assumptions behind the weighting are printed so they can be rejected', () => {
  const html = mechanismRankView(ranking({rows: [row('mechanism:a', 1)],
                                          frontier: ['mechanism:a'],
                                          single_leader: 'mechanism:a'}));
  assert.match(html, /적용성가?\s*임상 선례보다 가볍지 않다/);
  assert.match(html, /측정된 가중치가 아니라 검토할 주장입니다/);
  assert.match(html, /확률이나 효능 추정이/);
});

test('The next action names the compared axis that is most often unchecked', () => {
  const html = mechanismRankView(ranking({
    rows: [row('mechanism:a', 1, {unchecked_axes: ['evidence_grade']}),
           row('mechanism:b', 1, {unchecked_axes: ['evidence_grade', 'actionability']})],
    frontier: ['mechanism:a', 'mechanism:b']}));
  assert.match(html, /타당성\s*2개/);
  assert.doesNotMatch(html, /개입 가능성\s*1개/, 'a badge cannot change the order');
  assert.match(html, /이미 정해진 순서가\s*뒤집히지는 않습니다/);
});

test('Nothing to rank is explained rather than shown as an empty list', () => {
  const html = mechanismRankView({status: 'no_axis_values_recorded',
                                  meaning: '축 값을 기록한 기전·접근이 없습니다.'});
  assert.match(html, /축 값을 기록한 기전·접근이 없습니다/);
  assert.doesNotMatch(html, /1순위/);
});

test('Whether a quote carries its clause is shown as advice, not a verdict', () => {
  const withSupport = status => row('mechanism:a', 1, {basis: {grade: 'established', clauses: [{
    text: '주장', anchor: {quote: 'an English sentence from the paper'},
    quote_supports_clause: {status, confidence: 0.87}}]}});
  const ok = mechanismRankView(ranking({rows: [withSupport('supported')],
    frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
  assert.match(ok, /인용문이 이 절을 뒷받침합니다/);

  const weak = mechanismRankView(ranking({rows: [withSupport('not_carried')],
    frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
  assert.match(weak, /이 인용문만으로는 이 절이 나오지 않습니다/);
  assert.doesNotMatch(weak, /틀렸|거짓/, 'not carried is not a claim that the clause is wrong');

  const against = mechanismRankView(ranking({rows: [withSupport('contradicted')],
    frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
  assert.match(against, /반대로 읽힙니다/);

  const none = mechanismRankView(ranking({rows: [row('mechanism:a', 1, {basis: {clauses: [
    {text: '주장', anchor: {quote: 'q'}}]}})], frontier: ['mechanism:a'],
    single_leader: 'mechanism:a'}));
  assert.doesNotMatch(none, /인용문이 이 절을/, 'no note when the check did not run');
});

test('Paired places are shown side by side and never combined', () => {
  const html = mechanismRankView(ranking({
    rows: [row('mechanism:a', 2)], frontier: ['mechanism:a'], single_leader: 'mechanism:a',
    mechanism_candidate_pairs: {linked: 1, pairs: [{
      mechanism_label: '기전 A', mechanism_tier: 2, candidate_label: '후보 X',
      candidate_priority: 1, candidate_comparison_group: 'HMBS 저분자',
      link_reason: '이 기전의 효소를 직접 억제한다'}]}}));
  assert.match(html, /기전과 후보를 함께 본 순서 · 1개/);
  assert.match(html, /계산된 2단계/);
  assert.match(html, /HMBS 저분자 1순위/);
  assert.match(html, /이 기전의 효소를 직접 억제한다/);
  assert.match(html, /곱하지 않았고 결합 확률을 만들지 않았습니다/);
});

test('With nothing linked the pair table is absent rather than empty', () => {
  const html = mechanismRankView(ranking({rows: [row('mechanism:a', 1)],
    frontier: ['mechanism:a'], single_leader: 'mechanism:a',
    mechanism_candidate_pairs: {linked: 0, pairs: []}}));
  assert.doesNotMatch(html, /기전과 후보를 함께 본 순서/);
});

test('Recorded text cannot inject markup', () => {
  const html = mechanismRankView(ranking({
    rows: [row('mechanism:a', 1, {label: '<img src=x>', reason: '<script>bad()</script>'})],
    frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
  assert.doesNotMatch(html, /<img src=x>/);
  assert.doesNotMatch(html, /<script>bad/);
  assert.match(html, /&lt;img/);
});

test('A single graded mechanism is not announced as first place', () => {
  // The frontier of one option is that option by construction; a 1순위 badge here would be a
  // claim about a comparison that never happened.
  const html = mechanismRankView(ranking({
    rows: [row('mechanism:a', 1)], frontier: ['mechanism:a'], single_leader: null,
    single_leader_withheld: 'only_one_option_graded'}));
  assert.match(html, /비교 대상 없음/);
  assert.doesNotMatch(html, /<span class="rank-badge">1순위<\/span>/);
  assert.doesNotMatch(html, /가중치 범위 전체에서 앞섭니다/);
  assert.match(html, /사례 초기의 정상적인 상태/);
});

test('A mechanism below first place keeps its clauses and gaps, reachable', () => {
  const basis = {grade: 'demonstrated', clauses: [{
    text: '동물에서 섬유화가 줄었다', anchor: {quote: 'bleomycin-treated mice'},
    disease_match: 'animal_model'}],
    missing_in_target_disease: [{claim: '사람 개입 연구 없음', reported_count: 0}]};
  const html = mechanismRankView(ranking({
    rows: [row('mechanism:a', 1), row('mechanism:b', 2, {basis})],
    frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
  assert.match(html, /동물에서 섬유화가 줄었다/, 'a lower mechanism still shows what it rests on');
  assert.match(html, /사람 개입 연구 없음/);
  assert.match(html, /근거 절 1개/, 'folded, with a summary that says what is inside');
  assert.match(html, /목표 질환 공백 1개/);
});

test('A quote that reads against its clause is named without opening the fold', () => {
  const basis = {grade: 'hypothesis', clauses: [{
    text: '주장', anchor: {quote: 'q'},
    quote_supports_clause: {status: 'contradicted', confidence: 0.9}}]};
  const html = mechanismRankView(ranking({
    rows: [row('mechanism:a', 1), row('mechanism:b', 2, {basis})],
    frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
  assert.match(html, /반대로 읽히는 인용문 1개/, 'a warning behind a closed fold is a warning nobody sees');
});

test('The quote-support check is offered rather than run on every open', () => {
  const html = mechanismRankView(ranking({rows: [row('mechanism:a', 1), row('mechanism:b', 2)],
                                          frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
  assert.match(html, /data-action="mechanism-support"/);
  assert.match(html, /참고용이며 순서를 바꾸지 않습니다/);
});

test('The leading mechanism shows the figure from the paper its clause cites', () => {
  context.state = {id: 'ws_1'};
  try {
    const figures = [{artifact_id: 'art_1', file: 'fig1.jpg', caption: 'Fibrosis over 52 weeks',
                      source_url: 'https://europepmc.org/article/MED/1'}];
    const html = mechanismRankView(ranking({
      rows: [row('mechanism:a', 1, {figures}), row('mechanism:b', 2, {figures})],
      frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
    assert.match(html, /artifacts\/art_1\?figure=fig1\.jpg/);
    assert.match(html, /Fibrosis over 52 weeks/);
    assert.match(html, /원문의 그림/, 'the figure is identified by its source article');
    assert.doesNotMatch(html, /기전 그림<\/figcaption>/);
  } finally { context.state = null; }
});

test('A card with no retrieved figure shows no image rather than a broken one', () => {
  context.state = {id: 'ws_1'};
  try {
    const html = mechanismRankView(ranking({rows: [row('mechanism:a', 1), row('mechanism:b', 2)],
                                            frontier: ['mechanism:a'], single_leader: 'mechanism:a'}));
    assert.doesNotMatch(html, /<img/);
  } finally { context.state = null; }
});

test('Approved axis-order statements say they were approved, and still not measured', () => {
  const html = mechanismRankView(ranking({
    rows: [row('mechanism:a', 1), row('mechanism:b', 2)], frontier: ['mechanism:a'],
    single_leader: 'mechanism:a',
    stated_axis_order_approval: {decision: 'docs/decisions/0038.md', approved_on: '2026-09-30'}}));
  assert.match(html, /연구자가 승인한 가정입니다\(결정 0038, 2026-09-30\)/);
  assert.match(html, /측정된 가중치는 아니며/);
  assert.doesNotMatch(html, /검토할 주장입니다/);
});
