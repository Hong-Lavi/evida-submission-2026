const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function environment(extra={}){
  const escape=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const context={esc:escape,selected:'held-original',busy:false,state:{id:'ws-original',rev:9,events:[],jobs:[]},
    document:{addEventListener(){}},crypto:{randomUUID:()=> 'command-fixed'},
    button:(action,label,attributes='')=>`<button data-action="${action}" ${attributes}>${label}</button>`,
    sourceLinks:ids=>ids.map(escape).join(' '),measurementReportLabels:{measurement_validity:'측정 성립',intervention_status:'개입',precision:'정밀도',context_match:'조건'},
    measurementReportValue:(field,value)=>String(value),measurementReportView:()=>'<p>original report</p>',
    subjectRecordsView:()=>'<p>expected subject</p>',reportedSubjectBindingView:()=>'<p>effective subject</p>',
    measurementReportForm:()=>'<input type="checkbox" id="feedback-report-enabled">',notice(){},render(){},...extra};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/observation-amendment.js'),'utf8'),context);
  return context;
}
const report=()=>({measurement_validity:'validated',intervention_status:'validated',precision:'insufficient',context_match:true,assessment_basis:'calibration checked'});
const binding=()=>({eligible:true,expected_rev:7,target_message_id:'physical-observation',prior_selection_id:'held-original',
  expected_subject_refs:[{role:'candidate',artifact_id:'candidate-source',json_pointer:'/rows/0'}]});
const plain=value=>JSON.parse(JSON.stringify(value));

test('only held report or subject results offer the amendment action',()=>{
  const context=environment();
  for(const status of ['report_confirmation_required','subject_confirmation_required']){
    const html=context.observationAmendmentEntry({summary:{selection_status:status},result_assessment:{message_id:'m'}});
    assert.match(html,/observation-amendment-open/);assert.match(html,/data-artifact="held-original"/);
  }
  for(const status of ['repair_readout','conditional_plan','decision_region_reached']){
    assert.equal(context.observationAmendmentEntry({summary:{selection_status:status},result_assessment:{message_id:'m'}}),'');
  }
});

test('report edits preserve outcome, interpretation, provenance and subject control on the server',()=>{
  const context=environment(),declared=report();
  const value=context.observationAmendmentPayload(binding(),{measurement_report:declared,source_artifact_ids:['source'],
    reported_subject_refs:[{artifact_id:'injected'}],outcome_index:0,synthetic:false},false,'',' Clarified the report ');
  assert.deepEqual(plain(value),{kind:'correction',text:'Clarified the report',observation_amendment:{
    target_message_id:'physical-observation',prior_selection_id:'held-original',reason:'Clarified the report'},
    measurement_report:declared,source_artifact_ids:['source'],recalculate_held_selection:true});
  assert.equal(declared.precision,'insufficient');
});

test('explicitly unknown subjects differ from leaving the prior subject report unchanged',()=>{
  const context=environment();
  const unknown=context.observationAmendmentPayload(binding(),{},true,'unknown','Still tracing sample identity');
  assert.deepEqual(plain(unknown.reported_subject_refs),[]);
  const inherit=context.observationAmendmentPayload(binding(),{measurement_report:report()},false,'unknown','Corrected precision');
  assert.equal('reported_subject_refs' in inherit,false);
});

test('confirmed subject references are copied only after explicit selection',()=>{
  const context=environment(),saved=binding(),before=JSON.stringify(saved);
  const value=context.observationAmendmentPayload(saved,{},true,'expected','Matched the original sample sheet');
  assert.deepEqual(plain(value.reported_subject_refs),saved.expected_subject_refs);
  value.reported_subject_refs[0].artifact_id='changed-local-copy';
  assert.equal(JSON.stringify(saved),before);
  assert.throws(()=>context.observationAmendmentPayload(saved,{},true,'','reason'),/선택/);
  assert.throws(()=>context.observationAmendmentPayload({...saved,expected_subject_refs:[]},{},true,'expected','reason'),/원 대상/);
});

test('attachments alone and an empty reason cannot authorize a report amendment',()=>{
  const context=environment();
  assert.throws(()=>context.observationAmendmentPayload(binding(),{source_artifact_ids:['source']},false,'','reason'),/정정할/);
  assert.throws(()=>context.observationAmendmentPayload(binding(),{measurement_report:report()},false,'',' '),/근거/);
});

test('amendment history displays original and effective reports without mutating the original observation',()=>{
  const context=environment(),value={observed_events:[{message_id:'physical',measurement_report:{...report(),precision:'unknown'}}],
    observation_amendment:{original_observation_message_id:'physical',original_selection_id:'original-hold',
      amendment_message_id:'amendment',reason:'<script>untrusted</script>',effective_measurement_report:report(),effective_subject_binding:{}}};
  const before=JSON.stringify(value),html=context.observationAmendmentHistory(value);
  assert.match(html,/최초 보고/);assert.match(html,/unknown/);assert.match(html,/insufficient/);
  assert.match(html,/original-hold/);assert.match(html,/data-id="amendment"/);
  assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
  assert.equal(JSON.stringify(value),before);
});

test('the form keeps both amendment choices unchecked and preserves the original interpretation',()=>{
  const context=environment(),html=context.observationAmendmentForm({...binding(),origin:'synthetic',expected_subjects:[{}]},
    {result_assessment:{...report(),check_id:'check'},checks:[{id:'check',question:'Original <readout>'}]},
    {text:'Original <measurement>'});
  assert.match(html,/Original &lt;readout&gt;/);assert.match(html,/Original &lt;measurement&gt;/);
  assert.match(html,/이번 계산이 유지할 원 결과 해석/);assert.match(html,/insufficient/);
  assert.match(html,/합성 개발 사례의 관측/);assert.match(html,/모델이 기록한 결과 범주/);
  assert.match(html,/id="amend-subject-fields" disabled hidden/);assert.doesNotMatch(html,/ checked[ >]/);
  assert.match(html,/새로 측정한 결과는 ‘새 관측’/);
});

test('a delayed open cannot move an old report into a newly selected workspace',async()=>{
  const context=environment();let resolveFirst,shown=false;
  context.api=()=>new Promise(resolve=>{if(!resolveFirst)resolveFirst=resolve;else resolve({result:{}})});
  context.showDialog=()=>{shown=true};
  const node={dataset:{artifact:'held-original'},disabled:false};
  const pending=context.observationAmendmentAction('observation-amendment-open',node);
  context.state.id='different-workspace';resolveFirst(binding());await pending;
  assert.equal(shown,false);assert.equal(node.disabled,false);
});

test('save uses the version seen when the dialog opened and one stable command ID',async()=>{
  const calls=[],context=environment({api:async(...args)=>{calls.push(args);return {job_id:'job'}},refresh:async()=>{},
    measurementReportInput:()=>({measurement_report:report()}),
    dialog:{querySelector:selector=>selector==='#amend-reason'?{value:'Read the calibration report'}:null,close(){}}});
  context.saved={...binding(),workspace_id:'ws-original',command_id:'same-command'};
  vm.runInContext('observationAmendmentDialog=saved',context);
  await context.observationAmendmentAction('observation-amendment-save',{disabled:false});
  assert.equal(calls.length,1);assert.equal(calls[0][1].expected_rev,7);assert.equal(context.state.rev,9);
  assert.equal(calls[0][1].command_id,'same-command');assert.equal(calls[0][1].body.recalculate_held_selection,true);
});
