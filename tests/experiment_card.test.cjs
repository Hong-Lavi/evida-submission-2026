// Stage 5 is the experiment EVIDA recommends, so it has to read as one: what is measured,
// against what, read how, and what each possible result would change. Nothing here may fill in a
// field the model did not write.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const context = vm.createContext({
  esc: s => String(s).replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])),
  list: items => `<ul>${(items || []).map(i => `<li>${i}</li>`).join('')}</ul>`,
  button: (action, label, attrs = '', cls = '') =>
    `<button data-action="${action}" ${attrs} class="${cls}">${label}</button>`,
  sourceLinks: () => '',
  artifactName: id => context.state.artifacts.find(a => a.id === id)?.title || id,
  jobLabels: {},
  status: {gateway: {available: true}},
  busy: false,
  document: {addEventListener() {}, querySelector: () => null, getElementById: () => null},
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/reasoning-design.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/research.js'), 'utf8'), context);
const {renderCheck, experimentRequest, outcomeBranches} = context;

const REQUEST = ['측정 대상: 인간 폐 섬유아세포(IPF 환자 유래, n=3 공여자)',
                 '조건·비교군: PDE4B 억제제 1 µM 대 DMSO 대조, 공여자별 반복',
                 '판독 지표: 24시간 후 COL1A1 mRNA 상대 발현(qPCR, ΔΔCt)'].join('\n');

const check = (over = {}) => ({
  outcome_links: [],
  id: 'NC1', question: '섬유아세포에서 PDE4B 억제가 콜라겐 발현을 낮추는가',
  purpose: '기전이 목표 세포에서도 작동하는지 본다',
  operation: {kind: 'external_observation', request: REQUEST},
  possible_outcomes: [{observation: 'COL1A1이 유의하게 낮아진다', implication: '기전 가설이 유지된다'},
                      {observation: '변화가 없다', implication: '이 세포 맥락에서는 기전을 다시 본다'}],
  scope_targets: [], ...over});

context.state = {decision_id: 'd1', research_checks: [], jobs: [], check_readiness: {},
                 artifacts: [], decision: {research_loop: {hypotheses: []}}};

test('The three fields of an experiment request are laid out as fields', () => {
  const html = experimentRequest(REQUEST);
  assert.match(html, /<dt>측정 대상<\/dt>/);
  assert.match(html, /<dt>조건·비교군<\/dt>/);
  assert.match(html, /<dt>판독 지표<\/dt>/);
  assert.match(html, /COL1A1 mRNA 상대 발현/);
});

test('A request that does not carry the fields is shown as written, not reshaped', () => {
  const plain = experimentRequest('직접 측정이 필요하지만 조건을 아직 지정할 수 없습니다.');
  assert.doesNotMatch(plain, /<dl/);
  assert.match(plain, /조건을 아직 지정할 수 없습니다/);
  assert.doesNotMatch(plain, /측정 대상/, 'an empty field must not be invented');
});

test('Each possible result is shown next to what it would change', () => {
  const html = outcomeBranches(check());
  assert.match(html, /결과 A/);
  assert.match(html, /결과 B/);
  assert.match(html, /기전 가설이 유지된다/);
  assert.match(html, /이 세포 맥락에서는 기전을 다시 본다/);
});

test('A single outcome is not dressed up as a branching experiment', () => {
  assert.equal(outcomeBranches(check({possible_outcomes: [{observation: 'x', implication: 'y'}]})), '');
});

test('The first check says which kind of next step it is', () => {
  const html = renderCheck(check(), true, 0);
  assert.match(html, /class="check-kind external_observation">실험 권고/);
  assert.equal((html.match(/class="outcome-branches"/g)||[]).length,1,'one complete set of branches stays reachable');
  assert.match(html, /<details class="outcome-details"><summary>결과별 다음 결정 2가지/, 'the researcher opens the full outcome comparison');
});

test('A lookup is labelled a lookup, and keeps the folded outcome list', () => {
  const html = renderCheck(check({operation: {kind: 'tool', tool: 'literature', input: {}}}), true, 0);
  assert.match(html, /class="check-kind tool">자료 조회/);
  assert.match(html, /outcome-details/);
  assert.doesNotMatch(html, /outcome-branches/);
});

test('A later experiment stays folded so the recommended one stays first', () => {
  const html = renderCheck(check(), true, 2);
  assert.match(html, /<details class="further-check"/);
  assert.doesNotMatch(html, /outcome-branches/);
});

// The headline a researcher reads first has to say what to do. The three fields below it already
// carry that, so a collapsed check that shows only the question throws away what it knows: a
// question like "do the candidates lower the target transcript?" is a restatement of the
// hypothesis, not an instruction anyone can act on.
const {experimentHeadline} = context;

test('the headline names the sample, the comparison and the readout', () => {
  const line = experimentHeadline(REQUEST);
  assert.ok(line, 'no headline was built from a request that has all three fields');
  for (const part of ['섬유아세포', 'DMSO', 'COL1A1']) {
    assert.ok(line.includes(part), `the headline dropped ${part}: ${line}`);
  }
});

test('the headline stays one line', () => {
  assert.ok(!experimentHeadline(REQUEST).includes('\n'));
});

test('a request with no recognised fields yields no headline rather than a guess', () => {
  assert.equal(experimentHeadline('이 화합물을 세포에서 시험해 주세요'), '');
  assert.equal(experimentHeadline(''), '');
  assert.equal(experimentHeadline(null), '');
});

test('a partial request contributes only the fields it actually has', () => {
  const line = experimentHeadline('측정 대상: 환자 유래 1차 섬유아세포\n판독 지표: COL1A1 qPCR');
  assert.ok(line.includes('섬유아세포') && line.includes('COL1A1'));
  assert.ok(!line.includes('undefined') && !line.includes('null'));
});

test('a collapsed experiment check leads with the headline, not the bare question', () => {
  const vague = check({question: '회수한 후보와 제안 구조가 표적 전사체를 낮추는가?',
                       operation: {kind: 'external_observation', request: REQUEST}});
  const html = renderCheck(vague, 1);   // index 1 collapses into <details><summary>
  const summary = html.slice(html.indexOf('<summary>'), html.indexOf('</summary>'));
  assert.ok(summary.includes('COL1A1'),
            `the collapsed summary shows only the vague question: ${summary}`);
});

test('a check with no experiment request still shows its question when collapsed', () => {
  const tool = check({question: '이 표적의 활성 기록을 더 회수하면 제안이 넓어지는가?',
                      operation: {kind: 'tool', name: 'collect_compound_candidates', arguments: {}}});
  const html = renderCheck(tool, 1);
  const summary = html.slice(html.indexOf('<summary>'), html.indexOf('</summary>'));
  assert.ok(summary.includes('활성 기록'), summary);
});

// An outcome that is only prose and an outcome that is wired to what it changes look the same on
// screen, and across 136 recorded checks only 6 carried the wiring. A reader deciding whether to
// run the experiment needs to know which one they are looking at: if no hypothesis is linked to
// the falsifying branch, recording that result has nowhere to land and the next round cannot use
// it. So the branch says so rather than looking complete.
const {outcomeBranches: branches} = context;

const TWO = [{observation: 'COL1A1이 용매 대조 대비 낮아진다', implication: 'H1을 유지한다'},
             {observation: '차이가 없다', implication: 'H1을 다시 본다'}];

test('a branch with no link says the result is not connected to anything', () => {
  const html = branches(check({possible_outcomes: TWO, outcome_links: []}));
  assert.match(html, /가설 연결 필요/, html.slice(0, 400));
});

test('a branch that is linked does not carry the warning', () => {
  const linked = check({
    possible_outcomes: TWO,
    outcome_links: [{outcome_index: 1, followup_check_ids: [],
                     effects: [{hypothesis_id: 'H1', relation: 'challenges', part_ids: [],
                                alternative_ids: [], rationale: '이 결과는 H1과 양립하지 않는다'}]}],
  });
  const html = branches(linked);
  const second = html.slice(html.indexOf('결과 B'));
  assert.doesNotMatch(second, /가설 연결 필요/, second.slice(0, 400));
});

test('the warning names the falsifying branch as the one that matters', () => {
  const html = branches(check({possible_outcomes: TWO, outcome_links: []}));
  assert.match(html, /기각|반증/, html.slice(0, 600));
});

test('a single-outcome check still renders nothing', () => {
  assert.equal(branches(check({possible_outcomes: [TWO[0]], outcome_links: []})), '');
});

// Borrowed from Biomni's prohibition on inventing specifications, and turned into something the
// screen can show: an experiment either names the sources its sample, comparator and readout came
// from, or it says it named none. Two recommendations that differ in that respect used to render
// identically.
const {experimentGrounding} = context;

test('known experiment sources open the matching local artifact by readable title', () => {
  const prior = context.state.artifacts;
  context.state.artifacts = [{id: 'art_grounded', title: '원 실험 <조건> & 결과'}];
  try {
    const html = experimentGrounding({grounded_in: ['art_grounded', 'art_missing']});
    assert.match(html, /data-action="source"[^>]*data-id="art_grounded"/);
    assert.match(html, /원 실험 &lt;조건&gt; &amp; 결과/);
    assert.doesNotMatch(html, /data-id="art_missing"/);
    assert.match(html, /art_missing/);
  } finally {
    context.state.artifacts = prior;
  }
});

test('an experiment that names its sources lists them', () => {
  const html = experimentRequest(REQUEST, {kind: 'external_observation', request: REQUEST,
    grounded_in: ['art_1111', 'art_2222']});
  assert.match(html, /근거 자료 2건/);
  assert.match(html, /art_1111/);
  assert.match(html, /art_2222/);
  assert.ok(!html.includes('지목하지 않았습니다'));
});

test('an experiment that names none says so rather than staying silent', () => {
  const html = experimentRequest(REQUEST, {kind: 'external_observation', request: REQUEST});
  assert.match(html, /지목하지 않았습니다/);
  assert.match(html, /experiment-ungrounded/);
});

test('saying none were named does not call the recommendation wrong', () => {
  const html = experimentGrounding({kind: 'external_observation'});
  assert.match(html, /틀렸다는 뜻이 아니라/);
});

test('the fields still render when sources are named', () => {
  const html = experimentRequest(REQUEST, {kind: 'external_observation', request: REQUEST,
    grounded_in: ['art_1111']});
  assert.match(html, /<dt>측정 대상<\/dt>/);
  assert.match(html, /experiment-grounded/);
});

test('a request with no recognised fields still gets the grounding line', () => {
  const html = experimentRequest('조건을 아직 지정할 수 없습니다.',
    {kind: 'external_observation', request: '조건을 아직 지정할 수 없습니다.'});
  assert.match(html, /check-request/);
  assert.match(html, /지목하지 않았습니다/);
});

// The model was writing good experiment content as one unlabelled paragraph, so the card's field
// parser found nothing and fell back to plain text - the content was there and the screen could not
// lay it out. planner.md now demands the three labels as three lines and shows the exact format.
// These pin the parser against both shapes so the fallback stays correct and the labelled form
// keeps rendering as fields.
test('an unlabelled paragraph still renders, as plain text', () => {
  const prose = 'Ito 등의 3계열 결과와 독립적인 산발성 ALS 기증자 유래 iPSC 운동신경원에서 '
    + '기증자 계열을 반복 단위로 삼아 PF-04457845 20·40 nM 7일과 용매 대조를 비교한다.';
  const html = experimentRequest(prose, {kind: 'external_observation', request: prose});
  assert.match(html, /check-request/);
  assert.ok(!html.includes('<dt>'));
});

test('the three labelled lines become three fields', () => {
  const written = ['측정 대상: 독립 산발성 ALS 기증자 유래 iPSC 운동신경원',
                   '조건·비교군: PF-04457845 20·40 nM 7일 대 용매 대조',
                   '판독 지표: 7일 시점 생존율(%)과 축삭 길이(µm)'].join('\n');
  const html = experimentRequest(written, {kind: 'external_observation', request: written});
  assert.match(html, /<dt>측정 대상<\/dt>/);
  assert.match(html, /<dt>조건·비교군<\/dt>/);
  assert.match(html, /<dt>판독 지표<\/dt>/);
  assert.ok(!html.includes('check-request'));
});

test('the headline comes from the labelled fields', () => {
  const written = ['측정 대상: iPSC 운동신경원', '조건·비교군: 화합물 대 용매',
                   '판독 지표: 생존율'].join('\n');
  const line = experimentHeadline(written);
  assert.match(line, /iPSC 운동신경원/);
  assert.ok(!line.includes('\n'));
});
