const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function render(value) {
  const escape=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const context={esc:escape,sourceLinks:ids=>ids.map(escape).join(' '),
    state:{decision:{research_loop:{next_checks:[{id:'check',question:'WRONG NEW DECISION',possible_outcomes:[{observation:'WRONG NEW OUTCOME'}]}]}}}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/next-observation-selection.js'),'utf8'),context);
  return context.nextObservationSelectionTable(value);
}

function fixture() {
  return {binding:{decision_id:'original-decision'},
    problem:{immediate_decision:'Choose the next useful check',
      worlds:[{id:'a',description:'Contribution only in the stated condition'},
        {id:'a_plus_b',description:'Contribution and a parallel mechanism'}],
      decisions:[{id:'continue',label:'Continue the shared next action'}],
      declaration:{kind:'synthetic_fixture',basis:'Explicit synthetic data',conditions:['Only the declared context']},actions:[]},
    checks:[{id:'check',question:'Original paired functional readout',possible_outcomes:[{observation:'Function preserved'}]}],
    summary:{selection_status:'conditional_plan',selected_check_ids:['check'],
      retained_configuration_ids:['a','a_plus_b'],cost:3,cost_unit:'synthetic effort'},
    rows:[{outcome_by_check:{check:0},retained_configuration_ids:['a','a_plus_b'],common_next_decisions:['continue']}]};
}

test('saved observation labels and coexisting explanations stay bound to their original decision',()=>{
  const html=render(fixture());
  assert.match(html,/Original paired functional readout: Function preserved/);
  assert.match(html,/Contribution and a parallel mechanism/);
  assert.match(html,/Continue the shared next action/);
  assert.doesNotMatch(html,/WRONG NEW/);
});

test('measurement failure presents repair with every retained configuration',()=>{
  const value=fixture();value.summary.selection_status='repair_readout';
  value.summary.selected_check_ids=[];value.rows=[];
  value.observed_events=[{origin:'synthetic',text:'The detector failed; no functional value is available.'}];
  value.result_assessment={check_id:'check',outcome_index:0,context_match:true,intervention_status:'validated',measurement_validity:'failed',precision:'unknown',assessment_basis:'Repair the detector before classification.'};
  const html=render(value);
  assert.match(html,/측정을 복구한 뒤 다시 판단/);
  assert.match(html,/Contribution only in the stated condition/);
  assert.match(html,/Contribution and a parallel mechanism/);
  assert.doesNotMatch(html,/<th>이 관측이 나오면/);
  assert.match(html,/The detector failed/);
  assert.match(html,/생물학적 결과 분류는 측정 조건 확인 후/);
  assert.doesNotMatch(html,/Original paired functional readout: Function preserved/);
});

test('declared source text is escaped and model assumptions remain labelled as declarations',()=>{
  const value=fixture();value.problem.immediate_decision='<script>sourceInstruction()</script>';
  value.problem.declaration.kind='model_assumptions';value.summary.declaration_kind='model_assumptions';
  const html=render(value);
  assert.match(html,/&lt;script&gt;sourceInstruction\(\)&lt;\/script&gt;/);
  assert.doesNotMatch(html,/<script>/);
  assert.match(html,/모델이 제시한 조건/);
  assert.match(html,/실제 관측을 연결할 때 측정의 성립 조건과 정밀도를 함께 검토/);
});

test('historical source messages preserve corrected provenance without becoming a new observed result',()=>{
  const value=fixture();
  value.source_events=[{kind:'observation',body:{origin:'researcher_report',text:'Earlier source <img onerror="execute()">'},effective_provenance:{origin:'synthetic',corrected_by:'correction'}}];
  const html=render(value);
  assert.match(html,/조건을 구성할 때 참조한 원문/);
  assert.match(html,/합성 사례의 저장 원문/);
  assert.match(html,/출처 정정을 반영한 분류/);
  assert.match(html,/Earlier source &lt;img/);
  assert.doesNotMatch(html,/<img|연결한 결과의 해석|연구자가 입력한 원문/);
  assert.match(html,/Contribution and a parallel mechanism/);
});

test('legacy repair zero remains in the original artifact without appearing as a quote',()=>{
  const value=fixture();value.summary.selection_status='repair_readout';
  value.summary.selected_check_ids=[];value.summary.cost=0;value.rows=[];
  const before=JSON.stringify(value),html=render(value);
  assert.match(html,/수리 견적은 미정/);
  assert.doesNotMatch(html,/비용: 0|소계: 0|예산 이내/);
  assert.equal(JSON.stringify(value),before);
});

test('a known useful choice remains visible alongside an alternative awaiting a quote',()=>{
  const value=fixture();value.calculation_version='2';
  value.resource_assessment={scope:'declared_plan',cost_status:'known',known_subtotal:3,
    unknown_component_ids:[],budget_status:'within_declared_budget',required_information:[]};
  value.checks.push({id:'alternative',question:'Alternative early readout',possible_outcomes:[]});
  value.pending_cost_options=[{check_ids:['alternative'],cost:null,known_subtotal:1,
    unknown_component_ids:['action:alternative'],budget_status:'unresolved',resolution:'full',
    distinguished_pair_count:2,required_information:['Obtain a quote for the alternative readout.']}];
  const html=render(value);
  assert.match(html,/선택한 확인의 선언 비용: 3 synthetic effort/);
  assert.match(html,/선언한 비용 기준으로 입력 예산 이내/);
  assert.match(html,/견적을 확인할 관측 대안 1개/);
  assert.match(html,/Alternative early readout/);
  assert.match(html,/선언된 비용의 소계: 1 synthetic effort · 총비용은 미정/);
  assert.match(html,/Obtain a quote/);
  assert.doesNotMatch(html,/action:alternative/);
});

test('new repair has unknown total and names the information needed before execution',()=>{
  const value=fixture();value.calculation_version='2';value.summary.selection_status='repair_readout';
  value.summary.selected_check_ids=[];value.summary.cost=null;value.rows=[];
  value.resource_assessment={scope:'repair',cost_status:'unknown',known_subtotal:null,
    unknown_component_ids:['readout_repair:check'],budget_status:'unresolved',
    required_information:['수리와 반복 측정 견적을 확인합니다.']};
  const html=render(value);
  assert.match(html,/수리비용은 미정/);
  assert.match(html,/수리와 반복 측정 견적/);
  assert.match(html,/실행 가능 여부는 비용 확인 후 판단/);
  assert.doesNotMatch(html,/비용: 0|소계: 0|예산 이내|readout_repair:check/);
});

test('unknown total with an already excessive subtotal keeps the definite budget conclusion',()=>{
  const value=fixture();value.summary.selection_status='needs_budget_adjustment';
  value.summary.selected_check_ids=[];value.summary.cost=null;value.rows=[];
  value.resource_assessment={scope:'declared_plan',cost_status:'unknown',known_subtotal:null,
    unknown_component_ids:['action:check'],budget_status:'over_declared_budget',required_information:[]};
  value.pending_cost_options=[{check_ids:['check'],cost:null,known_subtotal:10,
    unknown_component_ids:['action:check'],budget_status:'over_declared_budget',resolution:'partial',
    distinguished_pair_count:1,required_information:['<script>untrusted quote</script>']}];
  const html=render(value);
  assert.match(html,/현재 예산에 맞는 확인 방법을 정해야 합니다/);
  assert.match(html,/알려진 비용만으로 입력 예산을 초과합니다/);
  assert.match(html,/&lt;script&gt;untrusted quote&lt;\/script&gt;/);
  assert.doesNotMatch(html,/<script>|비용: 0/);
});

test('a reached decision region scopes zero to the absence of a further check',()=>{
  const value=fixture();value.summary.selection_status='decision_region_reached';
  value.summary.selected_check_ids=[];value.summary.cost=0;value.rows=[];
  const html=render(value);
  assert.match(html,/이 판단을 위한 추가 확인 없이 다음 단계/);
  assert.doesNotMatch(html,/비용: 0|총비용/);
});

test('absence of a usable check cannot look like a reached decision region',()=>{
  const value=fixture();value.summary.selection_status='stop_specific_claim';
  value.summary.selected_check_ids=[];value.summary.cost=0;value.rows=[];
  value.resource_assessment={scope:'no_further_check',cost_status:'not_applicable',known_subtotal:null,
    unknown_component_ids:[],budget_status:'not_applicable',required_information:[]};
  const html=render(value);
  assert.match(html,/이 판단을 가를 확인을 더 찾아야 합니다/);
  assert.doesNotMatch(html,/추가 확인 없이 다음 단계|비용: 0/);
});

test('all pending options remain accessible past the first twelve',()=>{
  const value=fixture();
  value.pending_cost_options=Array.from({length:14},(_,i)=>({check_ids:['check'],cost:null,
    known_subtotal:i,unknown_component_ids:['action:check'],budget_status:'unresolved',resolution:'full',
    distinguished_pair_count:1,required_information:[`Quote item ${i}`]}));
  const html=render(value);
  assert.match(html,/견적을 확인할 관측 대안 14개/);
  assert.match(html,/나머지 2개 대안 보기/);
  for(let i=0;i<14;i++)assert.match(html,new RegExp(`Quote item ${i}<`));
});
