const reviewHarness=require('./ui_browser_fixture.cjs');
function reviewRun(code,ctx){return reviewHarness.run(code,ctx,require('node:path').join(__dirname,'../web'));}
// Exact thin records from four isolated copies. Tests exercise presentation only.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/workspace_experiment_actual_cases.json'),'utf8'));
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function setup(name){
  const record=fixture.cases.find(c=>c.case===name);
  const context=vm.createContext({state:structuredClone(record.state),esc,
    list:items=>`<ul>${(items||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`,
    button:(action,label,attrs='',cls='')=>`<button data-action="${action}" ${attrs} class="${cls}">${label}</button>`,
    sourceLinks:ids=>(ids||[]).map(id=>`<button data-action="source" data-id="${esc(id)}">원자료</button>`).join(''),
    jobLabels:{succeeded:'완료',running:'실행 중'},busy:false,
    document:{addEventListener(){},querySelector(){return null},getElementById(){return null}},
    window:{addEventListener(){}},matchMedia:()=>({matches:false}),status:{gateway:{available:false}}});
  context.roadmapModel=()=>({current:context.state.rev===context.state.decision_rev});
  context.artifactName=id=>context.state.artifacts.find(a=>a.id===id)?.title||id;
  for(const file of ['research.js','workspace-ui.js'])reviewRun(fs.readFileSync(path.join(__dirname,'../web',file),'utf8'),context);
  return context;
}
const checks=ctx=>ctx.state.decision.research_loop.next_checks;

for(const name of ['ipf','pde4b','als','preeclampsia'])test(`${name}: actual fields and source/outcome references survive the experiment view`,()=>{
  const ctx=setup(name),before=JSON.stringify(ctx.state);
  for(const check of checks(ctx)){
    const fields=ctx.experimentFields(check);
    assert.equal(fields.rest.length,0,'these actual requests have exactly three explicitly labelled lines');
    for(const key of ['측정 대상','조건·비교군','판독 지표']){
      assert.equal(fields.found[key].length,1);
      assert.equal(fields.found[key][0],check.operation.request.split('\n').find(s=>s.startsWith(key+':')).slice(key.length+1).trim());
    }
    const html=ctx.uiExperimentDetail(check);
    assert.match(html,/제안됨 · 수행 결과 확인 전/);
    assert.match(html,/data-action="delegate-check"/);
    assert.match(html,/data-action="check-feedback"/);
    assert.doesNotMatch(html,/data-action="run-check"/,'external observation has no computational execute action');
    for(const id of check.operation.grounded_in)assert.ok(html.includes(`data-id="${id}"`));
    for(const outcome of check.possible_outcomes){
      assert.ok(html.includes(ctx.uiText(outcome.observation)));
      assert.ok(html.includes(ctx.uiText(outcome.implication)));
    }
    for(const link of check.outcome_links)for(const effect of link.effects)
      assert.ok(html.includes(ctx.uiText(effect.rationale)),'original effect rationale retained');
  }
  assert.equal(JSON.stringify(ctx.state),before,'view leaves scientific records untouched');
});

test('IPF keeps unspecified concentration/time and separates non-IPF five days from IPF tissue',()=>{
  const ctx=setup('ipf'),[lpar1,pcls]=checks(ctx);
  const fields=ctx.experimentFields(lpar1).found;
  assert.match(fields['측정 대상'][0],/실제 세포계·수용체 구성체.*기록/);
  assert.match(fields['조건·비교군'][0],/12개.*BindingDB 부모/);
  assert.match(fields['판독 지표'][0],/칼슘 반응\(%\)/);
  assert.match(fields['판독 지표'][0],/농도와 시점은 지정하지 않음/);
  const matrix=ctx.uiExperimentDetail(pcls);
  assert.match(matrix,/비IPF 폐의 5일 조건을 IPF 절편에 자동 적용하지 않고/);
  assert.match(matrix,/1650 cm⁻¹/);
  assert.match(matrix,/LOX 특이 교차결합을 확정하지 않음/);
});

test('PDE preserves construct names, exact starting compound and IC50 uncertainty without a disease claim',()=>{
  const ctx=setup('pde4b'),check=checks(ctx)[0],html=ctx.uiExperimentDetail(check);
  assert.match(html,/BDBM:14364/);assert.match(html,/PDE4B2·PDE4D2/);
  assert.match(html,/roflumilast/);assert.match(html,/30°C에서 1시간/);
  assert.match(html,/IC50\(nM\) 및 추정 불확실성/);
  assert.match(html,/설계 후보 2/);
  assert.doesNotMatch(html,/proposed-설계|BDBM:설계|n=3|1 µM/);
});

test('ALS preserves reported doses and marks donor/independent perturbation as the proposed extension',()=>{
  const ctx=setup('als'),[faah,stmn2]=checks(ctx);
  const html=ctx.uiExperimentDetail(faah);
  assert.match(html,/20·40 nM, 7일/);
  assert.match(html,/별도 FAAH 조절 대 비표적 대조는 제안된 확장/);
  assert.match(html,/원문에 제시되지 않은 FAAH 활성·지질 측정 단위.*측정 전에 확인/);
  const second=ctx.uiExperimentDetail(stmn2);
  assert.match(second,/rASO-5/);
  assert.match(second,/자연 발생 환자 모델과 원문의 유도 TDP-43 결핍 모델을 구분/);
  assert.match(second,/환자 모델의 농도·시점은 별도 확인/);
});

test('Preeclampsia retains the proposed concurrent comparator and both hypotheses affected by one outcome',()=>{
  const ctx=setup('preeclampsia'),check=checks(ctx)[0],html=ctx.uiExperimentDetail(check);
  assert.match(html,/동시 대조 비교는 이번에 제안한 설계/);
  assert.match(html,/실행 전 확정/);
  assert.match(html,/sFlt-1\(pg\/mL\)/);
  assert.match(html,/<strong>지지할 수 있음<\/strong>/);
  assert.match(html,/<strong>다시 검토할 근거<\/strong>/);
  assert.match(html,/연결된 관측: 아직 없음.*위 표는 가능한 결과의 예상과 결과별 다음 행동입니다/);
  assert.ok(html.includes(ctx.uiText(check.outcome_links[0].effects[0].rationale)));
  assert.ok(html.includes(ctx.uiText(check.outcome_links[0].effects[1].rationale)));
  assert.doesNotMatch(html,/42%|11\.5일 대 12\.1일/,'synthetic prior observations do not become proposed assay values');
});

test('A missing labelled measurement is displayed as missing rather than inferred from a free sentence',()=>{
  const ctx=setup('pde4b'),check=structuredClone(checks(ctx)[0]);
  check.operation.request='익숙한 세포계에서 보통 쓰는 시간과 농도를 생각할 수 있다.\n판독 지표: IC50 (단위 확인 필요)';
  const fields=ctx.experimentFields(check);
  assert.equal(fields.found['측정 대상'],undefined);
  assert.equal(fields.found['조건·비교군'],undefined);
  assert.equal(fields.rest[0],'익숙한 세포계에서 보통 쓰는 시간과 농도를 생각할 수 있다.');
  const html=ctx.uiExperimentDetail(check);
  assert.match(html,/확인 필요 · 권고에 구분해 기록된 값이 없습니다/);
  assert.doesNotMatch(html,/HEK293|24시간|n=3/);
});

test('New input retains the decision input version and visibly marks previous recommendations',()=>{
  const ctx=setup('pde4b');ctx.state.rev++;
  const html=ctx.uiExperiments();
  assert.match(html,/이전 조건의 권고입니다/);
  assert.match(html,/연구 기록 8/);
  assert.equal(ctx.uiRevision({applicability:{current:false}}),'근거·조건 재검토 필요');
  assert.equal(ctx.uiRevision({current_conditions:false}),'적용 조건 확인 필요','legacy boolean alone does not establish current applicability');
  assert.equal(ctx.uiRevision({applicability:{current:true}}),'현재 입력에서 검토 유지');
  assert.equal(ctx.uiRevision({current_conditions:true}),'적용 조건 확인 필요','legacy true does not silently imply reviewed current conditions');
  assert.equal(ctx.uiRevision({}),'적용 조건 확인 필요');
});
