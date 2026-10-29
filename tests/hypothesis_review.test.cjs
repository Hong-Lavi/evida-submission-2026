const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ref=id=>({hypothesis_id:'h1',alternative_id:id});
function fixture(){
  const check={id:'c1',question:'합성 확인 질문',purpose:'예상 비교',hypothesis_ids:['h1'],operation:{kind:'researcher_input',request:'기존 자료 확인'},possible_outcomes:[{observation:'지표 감소',implication:'조건부 해석'},{observation:'측정 실패',implication:'측정 확인'}],outcome_links:[0,1].map(outcome_index=>({outcome_index,effects:[{hypothesis_id:'h1',alternative_ids:['a'],part_ids:[],relation:'supports',rationale:'원래 기록한 합성 지지 이유'}],followup_check_ids:[]}))};
  const predictions=['a','b'].map((id,i)=>({...ref(id),outcome_indices:[i],coverage:'complete',origin:'prospective',assumptions:[],rationale:'시험 전 예상',source_ids:[]}));
  const pair={left:ref('a'),right:ref('b'),status:'separating',compatible_explanation:ref('a'),excluded_explanation:ref('b'),selection_eligible:true,requires_joint_prediction:false,retrospective:false};
  const observation={check_id:'c1',status:'reviewed',explanations:predictions.map((p,i)=>({...ref(p.alternative_id),statement:i?'설명 B':'설명 A',prediction:p})),missing_explanations:[],outcomes:[{outcome_index:0,interpretation:'adequate_measurement',guard_reasons:[],pairs:[pair]},{outcome_index:1,interpretation:'measurement_failure',guard_reasons:['measurement_failure'],pairs:[]}],outcome_link_diagnostics:[]};
  const h={id:'h1',statement:'게시한 원 가설',expected_observation:'원 예상',rationale:'합성 기록',assessment:'proposed',evidence:[],alternatives:[],conditional_alternatives:predictions.map((p,i)=>({id:p.alternative_id,statement:i?'설명 B':'설명 A',assessment:'proposed',rationale:'합성 설명',conditions:[],observable:'합성 관측',prediction:'합성 예상',prediction_origin:'prospective',evidence:[],relations:[],unknowns:[]}))};
  const state={id:'ws',rev:1,decision_rev:1,decision_id:'d1',events:[],artifacts:[],jobs:[],research_checks:[],hypothesis_review:{status:'available',published_decision_id:'d1',is_current_input:true,artifact_id:'review1',review:{causal_steps:[],observations:[{check_id:'c1',validity_requirements:['대조 확인'],precision_requirement:'사전에 정한 정밀도',predictions}]},observation_checks:[observation],causal_step_checks:[]},decision:{research_loop:{hypotheses:[h],next_checks:[check]}}};
  const ctx=vm.createContext({state,esc,number:String,json:x=>esc(JSON.stringify(x)),list:xs=>`<ul>${(xs??[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`,sourceLinks:()=>'',button:(_action,label,attrs='')=>`<button ${attrs}>${label}</button>`,artifactName:id=>id,document:{addEventListener:()=>{}},evidenceHistoryButton:()=>'',status:{gateway:{available:true}},busy:false,outcomeSelections:new Map(),uiText:esc,uiEmpty:esc});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/reasoning-design.js'),'utf8'),ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/research.js'),'utf8'),ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/hypothesis-review.js'),'utf8'),ctx);
  const workspace=fs.readFileSync(path.join(__dirname,'../web/workspace-ui.js'),'utf8');
  vm.runInContext(workspace.slice(workspace.indexOf('function uiOutcomeBranches('),workspace.indexOf('function uiExperimentControls(')),ctx);
  return {ctx,state,check,observation,pair,h};
}
const branch=(ctx,check,index)=>ctx.uiOutcomeBranches(check).match(new RegExp(`<article id="outcome-${index}"[^>]*>([\\s\\S]*?)</article>`))[1];
const withoutOriginal=html=>html.replace(/<details class="outcome-authored-needs-review">[\s\S]*?<\/details>/g,'');
test('a review attached to an older decision never appears as current',()=>{
  const {ctx,state,check}=fixture();state.decision_id='d2';
  assert.equal(ctx.currentHypothesisReview(),null);
  assert.match(ctx.renderObservationReview(check),/아직 검토하지 않았습니다/);
  assert.equal(ctx.renderHypothesisReviewSummary(),'');
});
test('binding failure is shown as unreviewed instead of crashing or using its payload',()=>{
  const {ctx,state,check}=fixture();state.hypothesis_review.status='binding_mismatch';state.hypothesis_review.review=null;
  assert.match(ctx.renderObservationReview(check),/아직 검토하지 않았습니다/);
  assert.equal(ctx.renderObservationOutcome(check,0),'');
});
test('a conditional difference identifies the matching explanation without changing stored records',()=>{
  const {ctx,state,check}=fixture(),before=JSON.stringify(state);
  assert.match(ctx.renderObservationOutcome(check,0),/더 잘 맞는 설명/);
  assert.match(ctx.renderObservationOutcome(check,0),/설명 A/);
  assert.match(ctx.renderObservationReview(check),/명시한 조건에서 일부 설명/);
  assert.equal(JSON.stringify(state),before);
});
test('failed measurement cannot display an explanation as preferred even with an inconsistent old pair',()=>{
  const {ctx,check,observation,pair}=fixture();observation.outcomes[1].pairs=[pair];
  const html=ctx.renderObservationOutcome(check,1);
  assert.match(html,/측정 실패/);assert.match(html,/어느 설명이 맞는지 정하지 않습니다/);
  assert.doesNotMatch(html,/더 잘 맞는 설명|<li>설명 A/);
});
test('shared predictions and missing predictions keep different meanings',()=>{
  const {ctx,check,observation,pair}=fixture();pair.status='shared';pair.selection_eligible=false;
  assert.match(ctx.renderObservationReview(check),/같은 결과를 예상/);
  observation.explanations[1].prediction=null;observation.missing_explanations=[ref('b')];pair.status='unresolved';
  const html=ctx.renderObservationReview(check);
  assert.match(html,/아직 예상하지 않은 설명/);assert.match(html,/비교 목록에 남겨/);
  assert.doesNotMatch(html,/기록된 설명들이 같은 결과/);
});
test('coexisting and retrospective explanations retain their interpretation limits',()=>{
  const {ctx,check,pair}=fixture();pair.selection_eligible=false;pair.requires_joint_prediction=true;pair.retrospective=true;
  const html=ctx.renderObservationOutcome(check,0);
  assert.match(html,/결합된 설명의 예상/);assert.match(html,/관측 뒤에 구성/);
  assert.doesNotMatch(html,/더 잘 맞는 설명/);
});
test('scientific text is escaped in the prediction matrix',()=>{
  const {ctx,check,observation}=fixture();observation.explanations[0].statement='<img src=x onerror=alert(1)>';
  const html=ctx.renderObservationReview(check);
  assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img/);
});

test('a new frame with a reused hypothesis ID cannot inherit the published causal review',()=>{
  const {ctx,state,h}=fixture();
  state.rev=2;state.hypothesis_review.is_current_input=false;
  state.hypothesis_review.review.causal_steps=[{id:'old-step',hypothesis_id:'h1',claim:'이전 판단에만 속한 인과 연결',target_context:'이전 조건',evidence_groups:[],missing_assumptions:[]}];
  const currentDraft={...h,statement:'새 초안의 다른 주장'};
  const before=JSON.stringify(state),html=ctx.renderHypothesis(currentDraft,false);
  assert.match(html,/새 초안의 다른 주장/);
  assert.doesNotMatch(html,/이전 판단에만 속한 인과 연결/);
  const published=ctx.renderHypothesisReviewSummary();
  assert.match(published,/이전 판단에만 속한 인과 연결/);
  assert.match(published,/해당 판단에 보존된 검토/);
  assert.equal(JSON.stringify(state),before);
});

test('the complete outcome UI retains favorable failed-measurement assertions only as original history',()=>{
  const {ctx,state,check,observation,pair}=fixture();
  check.possible_outcomes[1].implication='실패인데도 설명 A를 더 믿는다는 원래 문안';
  observation.outcomes[1].pairs=[pair]; // Defensive display even if a retained pair disagrees.
  const before=JSON.stringify(state),html=branch(ctx,check,1),current=withoutOriginal(html);
  assert.match(current,/측정 실패/);assert.match(current,/어느 설명이 맞는지 정하지 않습니다/);
  assert.doesNotMatch(current,/실패인데도 설명 A|지지할 수 있음|더 잘 맞는 설명/);
  assert.match(html,/<details class="outcome-authored-needs-review"><summary>원래 기록한 해석·근거 · 재검토 필요/);
  assert.match(html,/실패인데도 설명 A를 더 믿는다는 원래 문안/);
  assert.match(html,/원래 기록한 지지 관계 · 재검토 필요/);
  assert.doesNotMatch(ctx.renderOutcomeLinks(check,1),/<strong>지지할 수 있음<\/strong>/);
  assert.equal(JSON.stringify(state),before);
});

test('insufficient precision and undeclared precision cannot retain an unqualified current interpretation',()=>{
  for(const interpretation of ['insufficient_precision','adequate_measurement']){
    const {ctx,check,observation}=fixture();
    check.possible_outcomes[0].implication='설명 A를 지지한다는 원래 문안';
    observation.outcomes[0].interpretation=interpretation;
    observation.outcomes[0].guard_reasons=[interpretation==='adequate_measurement'?'precision_requirement_missing':'insufficient_precision'];
    const html=branch(ctx,check,0),current=withoutOriginal(html);
    assert.match(current,/정밀도/);assert.match(current,/어느 설명이 맞는지 정하지 않습니다/);
    assert.doesNotMatch(current,/지지한다는 원래 문안|더 잘 맞는 설명|지지할 수 있음/);
    assert.match(html,/지지한다는 원래 문안/);
  }
});

test('explicit prediction-link conflict is reviewed while a consistent valid case keeps its current interpretation',()=>{
  const {ctx,check,observation}=fixture();
  check.possible_outcomes[0].implication='원래 해석을 보존한다';
  observation.outcome_link_diagnostics=[{outcome_index:0,status:'conflicts_with_prediction_set'}];
  const conflicted=branch(ctx,check,0),current=withoutOriginal(conflicted);
  assert.match(current,/서로 맞지 않음/);
  assert.doesNotMatch(current,/원래 해석을 보존한다|지지할 수 있음/);
  assert.match(current,/설명 A \(비교 대상: 설명 B\)/,'the derived pair remains inspectable despite an inconsistent authored effect');
  observation.outcome_link_diagnostics[0].status='consistent_with_prediction_set';
  const valid=branch(ctx,check,0);
  assert.doesNotMatch(valid,/outcome-authored-needs-review/);
  assert.match(valid,/원래 해석을 보존한다/);assert.match(valid,/더 잘 맞는 설명/);
  assert.match(valid,/<strong>지지할 수 있음<\/strong>/);
});

test('legacy outcome and further-check renderers apply the same failure guard',()=>{
  const {ctx,check}=fixture();
  check.possible_outcomes[1].implication='실패 결과를 지지로 바꾼 원래 문장';
  for(const html of [ctx.outcomeBranches(check),ctx.renderCheck(check,true,1)]){
    assert.match(html,/실패 결과를 지지로 바꾼 원래 문장/);
    assert.doesNotMatch(withoutOriginal(html),/실패 결과를 지지로 바꾼 원래 문장/);
    assert.match(withoutOriginal(html),/측정 실패/);
  }
});

test('a legacy decision without a hypothesis review loads its original interpretation without invented review status',()=>{
  const {ctx,state,check}=fixture();delete state.hypothesis_review;
  const html=branch(ctx,check,0);
  assert.match(html,/조건부 해석/);assert.match(html,/<strong>지지할 수 있음<\/strong>/);
  assert.doesNotMatch(html,/outcome-authored-needs-review|더 잘 맞는 설명/);
  assert.doesNotThrow(()=>ctx.renderCheck(check,true,1));
});

test('identical complete prediction sets stay distinct from uncertainty when failure and outside-set outcomes exist',()=>{
  const {ctx,check,observation,pair}=fixture();
  observation.explanations.forEach(e=>e.prediction.outcome_indices=[0]);
  pair.status='shared';pair.selection_eligible=false;
  check.possible_outcomes.push({observation:'두 예측 모두에서 벗어난 결과',implication:'추가 설명 필요'});
  observation.outcomes.push({outcome_index:2,interpretation:'adequate_measurement',guard_reasons:[],pairs:[{...pair,status:'neither_predicted'}]});
  observation.outcomes[1].pairs=[{...pair,status:'unresolved'}];
  assert.match(ctx.renderObservationReview(check),/기록된 설명들이 같은 결과를 예상합니다/);
  observation.explanations[1].prediction.coverage='unknown';
  assert.doesNotMatch(ctx.renderObservationReview(check),/기록된 설명들이 같은 결과를 예상합니다/);
});

test('an unknown third explanation does not hide an independently eligible named pair comparison',()=>{
  const {ctx,state,check,observation,pair}=fixture();
  observation.explanations.push({...ref('c'),statement:'설명 C',prediction:null});
  observation.missing_explanations=[ref('c')];
  observation.outcomes[0].pairs.push(...['a','b'].map(id=>({...pair,left:ref(id),right:ref('c'),status:'unresolved',compatible_explanation:null,excluded_explanation:null,selection_eligible:false,reasons:['missing_prediction']})));
  const before=JSON.stringify(state),html=branch(ctx,check,0),current=withoutOriginal(html);
  assert.match(current,/설명 A \(비교 대상: 설명 B\)/);
  assert.match(current,/아직 비교할 수 없는 설명 쌍/);
  assert.match(current,/설명 A · 설명 C/);assert.match(current,/설명 B · 설명 C/);
  assert.match(current,/명시한 두 설명에만 해당/);
  assert.match(html,/outcome-authored-needs-review/);
  assert.equal(JSON.stringify(state),before);
  observation.outcomes[0].guard_reasons=['precision_requirement_missing'];
  const guarded=withoutOriginal(branch(ctx,check,0));
  assert.match(guarded,/어느 설명이 맞는지 정하지 않습니다/);
  assert.doesNotMatch(guarded,/더 잘 맞는 설명|설명 A \(비교 대상: 설명 B\)/);
});

test('unreviewed and inapplicable items remain visible with their exact reasons instead of a completed-review headline',()=>{
  const {ctx,state,check,h,observation}=fixture();
  const record=state.hypothesis_review;
  record.review.causal_steps=[];record.review.observations=[];observation.status='not_reviewed';
  record.review.scope={hypotheses:[{hypothesis_id:'h1',status:'not_reviewed',reason:'아직 매개 근거를 검토하지 않음 <img src=x>'}],checks:[{check_id:'c1',status:'not_applicable',reason:'이 확인은 원자료 위치를 찾는 질문임'}]};
  const before=JSON.stringify(state),summary=ctx.renderHypothesisReviewSummary();
  assert.match(summary,/마친 항목이 없습니다/);
  assert.match(summary,/아직 검토하지 않음/);assert.match(summary,/아직 매개 근거를 검토하지 않음/);
  assert.match(summary,/이번 검토 대상에 해당하지 않음/);assert.match(summary,/원자료 위치를 찾는 질문/);
  assert.doesNotMatch(summary,/구별 가능성을 검토했습니다|<img/);assert.match(summary,/&lt;img/);
  assert.match(ctx.renderHypothesisReview(h),/아직 매개 근거를 검토하지 않음/);
  assert.match(ctx.renderObservationReview(check),/원자료 위치를 찾는 질문/);
  assert.equal(JSON.stringify(state),before);
});

test('an authored unknown causal assessment with no quotation is visibly unsupported rather than source-verified',()=>{
  const {ctx,state,h}=fixture();
  state.hypothesis_review.review.causal_steps=[{id:'s1',hypothesis_id:'h1',claim:'합성 인과 주장',target_context:'조건 미확인',missing_assumptions:['인과성 미확인'],evidence_groups:[{id:'g1',anchors:[],reported_context:'시점 미확인',text_support:'unknown',text_support_rationale:'인용 없음',causal_support:'unknown',causal_support_rationale:'인과 판정 못함',applicability:'unknown',applicability_rationale:'조건 판정 못함',missing_assumptions:[]}]}];
  const html=ctx.renderHypothesisReview(h);
  assert.match(html,/연결한 원문 인용이 없습니다/);assert.match(html,/인과 검토 미확인/);
  assert.match(html,/시점 미확인/);assert.doesNotMatch(html,/보존 원문과 인용 위치 일치/);
});

test('a review scope attached to another decision is not inherited by a reused hypothesis or check ID',()=>{
  const {ctx,state,check,h}=fixture();
  state.hypothesis_review.review.scope={hypotheses:[{hypothesis_id:'h1',status:'not_reviewed',reason:'다른 판단의 미검토 사유'}],checks:[{check_id:'c1',status:'not_reviewed',reason:'다른 판단의 관측 사유'}]};
  state.decision_id='new-decision';
  assert.equal(ctx.renderHypothesisReview(h),'');
  assert.doesNotMatch(ctx.renderObservationReview(check),/다른 판단/);
  assert.equal(ctx.renderHypothesisReviewSummary(),'');
});

test('a verified quote describes agreement with the stored material without claiming publisher-original verification',()=>{
  const {ctx}=fixture();
  const html=ctx.hypothesisReviewSource({artifact_id:'source',path:'/rows/0/text',quote:'저장된 발췌문'}, {status:'verified'});
  assert.match(html,/저장 자료와 인용 위치 일치/);
  assert.doesNotMatch(html,/보존 원문과 인용 위치 일치|인과.*확인됨/);
});

test('different prediction sets with an unknown relationship remain visible without preferring a mechanism',()=>{
  const {ctx,state,check,pair}=fixture();
  pair.selection_eligible=false;pair.relationship_status='unknown';pair.prediction_set_status='separating';
  pair.reasons=['explanation_relationship_unknown'];
  const before=JSON.stringify(state),html=withoutOriginal(branch(ctx,check,0));
  assert.match(html,/예상 결과는 다르지만 설명들의 공존·배타 관계가 미확인/);
  assert.match(html,/아직 비교할 수 없는 설명 쌍/);
  assert.doesNotMatch(html,/더 잘 맞는 설명/);
  const matrix=ctx.renderObservationReview(check);
  assert.match(matrix,/설명 A/);assert.match(matrix,/설명 B/);assert.match(matrix,/지표 감소/);
  assert.equal(JSON.stringify(state),before);
});

test('an unknown cross-hypothesis relation does not hide an independently eligible pair',()=>{
  const {ctx,state,check,observation,pair}=fixture();
  const third={hypothesis_id:'h2',alternative_id:''};
  observation.explanations.push({...third,statement:'설명 C',prediction:{...third,outcome_indices:[1],coverage:'complete',origin:'prospective',assumptions:[],rationale:'합성 예상',source_ids:[]}});
  observation.outcomes[0].pairs.push({...pair,left:ref('a'),right:third,status:'separating',prediction_set_status:'separating',relationship_status:'unknown',selection_eligible:false,reasons:['explanation_relationship_unknown']});
  const before=JSON.stringify(state),html=withoutOriginal(branch(ctx,check,0));
  assert.match(html,/설명 A \(비교 대상: 설명 B\)/);
  assert.match(html,/예상 결과는 다르지만 설명들의 공존·배타 관계가 미확인/);
  assert.match(html,/설명 A · 설명 C/);
  assert.doesNotMatch(html,/설명 A \(비교 대상: 설명 C\)/);
  assert.equal(JSON.stringify(state),before);
});

function evidenceInterpretationFixture(text_support,causal_support,verified=false){
  const {ctx,state,h}=fixture();
  const group={id:'g1',anchors:[{artifact_id:'source',path:'/rows/0/text',quote:'보존한 합성 인용'}],reported_context:'원래 기록한 시험 조건',text_support,text_support_rationale:'원래 모델의 문장 해석',causal_support,causal_support_rationale:'원래 모델의 인과 판단',applicability:'conditional',applicability_rationale:'원래 모델의 적용 판단',missing_assumptions:[]};
  state.hypothesis_review.review.causal_steps=[{id:'s1',hypothesis_id:'h1',claim:'합성 인과 주장',target_context:'합성 조건',missing_assumptions:[],evidence_groups:[group]}];
  state.hypothesis_review.causal_step_checks=[{step_id:'s1',evidence_groups:[{group_id:'g1',all_anchors_verified:verified,anchor_checks:[{status:verified?'verified':'rejected'}]}]}];
  return {ctx,state,h,group};
}

test('opposition paired with unestablished or unknown causality gets a conditional review note without rewriting either assessment',()=>{
  for(const causal of ['not_established','unknown']){
    const {ctx,state,h,group}=evidenceInterpretationFixture('contradicts',causal),before=JSON.stringify(state);
    const html=ctx.renderHypothesisReview(h);
    assert.match(html,/<summary>미입증·반대 근거 구분 확인/);
    assert.match(html,/모델은 반대 근거로 읽음/);
    assert.match(html,/미입증과 반대 관측을 구분해 확인하세요/);
    for(const item of ['검출력','대조군','측정 시점','시험 조건'])assert.ok(html.includes(item));
    for(const text of [group.text_support_rationale,group.causal_support_rationale,group.applicability_rationale,group.reported_context,group.anchors[0].quote])assert.ok(html.includes(text));
    assert.equal(JSON.stringify(state),before);
  }
});

test('other counterevidence and support remain attributed and visible without receiving this specific review note',()=>{
  for(const [text,causal,label] of [['contradicts','intervention_response_only','모델은 반대 근거로 읽음'],['supports','not_established','모델은 지지 근거로 읽음'],['partial','unknown','모델은 일부만 다룬다고 읽음']]){
    const {ctx,state,h}=evidenceInterpretationFixture(text,causal),before=JSON.stringify(state);
    const html=ctx.renderHypothesisReview(h);
    assert.ok(html.includes(label));assert.match(html,/원래 모델의 문장 해석/);assert.match(html,/보존한 합성 인용/);
    assert.doesNotMatch(html,/data-evidence-interpretation-review|미입증·반대 근거 구분 확인/);
    assert.equal(JSON.stringify(state),before);
  }
});

test('a matched quotation does not remove the scientific interpretation check',()=>{
  const {ctx,state,h}=evidenceInterpretationFixture('contradicts','not_established',true),before=JSON.stringify(state);
  const html=ctx.renderHypothesisReview(h);
  assert.match(html,/저장 자료와 인용 위치 일치/);
  assert.match(html,/인용 위치의 일치가 이 과학적 해석의 타당성을 확인한 것은 아닙니다/);
  assert.match(html,/모델은 반대 근거로 읽음/);
  assert.equal(JSON.stringify(state),before);
});
