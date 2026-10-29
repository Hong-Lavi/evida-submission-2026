const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function view(controls={},selected=[],state={}){
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const context={esc,state,labels:{source_file:'업로드한 원본'},button:(action,text,attrs)=>`<button data-action="${esc(action)}" ${attrs}>${text}</button>`,document:{addEventListener:()=>{}},sourceLinks:ids=>ids.map(esc).join(' '),dialog:{querySelector:selector=>controls[selector],querySelectorAll:()=>selected.map(value=>({value}))}};
  vm.createContext(context);
  for(const file of ['observation-report.js','next-observation-selection.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',file),'utf8'),context);
  return context;
}

test('an omitted measurement report stays absent, while an explicit unknown remains explicit',()=>{
  const controls={'#feedback-report-enabled':{checked:false}},context=view(controls,['original']);
  assert.deepEqual(JSON.parse(JSON.stringify(context.measurementReportInput())),{source_artifact_ids:['original']});
  controls['#feedback-report-enabled'].checked=true;
  for(const field of ['measurement_validity','intervention_status','precision','context_match'])controls[`#feedback-report-${field}`]={value:'unknown'};
  controls['#feedback-report-basis']={value:'  Positive control not provided  '};
  const input=JSON.parse(JSON.stringify(context.measurementReportInput()));
  assert.equal(input.measurement_report.context_match,null);assert.equal(input.measurement_report.precision,'unknown');
  assert.equal(input.measurement_report.assessment_basis,'Positive control not provided');
  assert.ok(!Object.hasOwn(input,'source_artifact_hashes'));
});

test('confirmation uses the historical check subject even when a later check reuses its local ID',()=>{
  const expected={role:'candidate',artifact_id:'original-proposal',json_pointer:'/rows/0'};
  const old={decision_id:'original-decision',checks:[{check_id:'check-1',subject_refs:[expected],subjects:[]}]};
  const state={decision_id:'later-decision',check_subject_bindings:[old,{decision_id:'later-decision',checks:[{check_id:'check-1',subject_refs:[{...expected,artifact_id:'other-proposed-1'}],subjects:[]}]}]};
  const before=JSON.stringify(state),controls={'#feedback-subject-confirm':{checked:true}};
  const context=view(controls,[],state);
  context.subjectConfirmationForm({id:'check-1'},'original-decision');
  const payload=JSON.parse(JSON.stringify(context.measurementReportInput()));
  assert.deepEqual(payload.reported_subject_refs,[expected]);
  assert.equal(JSON.stringify(state),before);
  assert.deepEqual(Object.keys(payload.reported_subject_refs[0]).sort(),['artifact_id','json_pointer','role']);
});

test('attaching source evidence does not silently confirm the measured candidate or condition',()=>{
  const refs=[{role:'candidate',artifact_id:'expected-source',json_pointer:'/rows/4'}];
  const state={check_subject_bindings:[{decision_id:'decision',checks:[{check_id:'check',subject_refs:refs,subjects:[]}]}]};
  const controls={'#feedback-subject-confirm':{checked:false}},context=view(controls,['expected-source','counterevidence'],state);
  context.subjectConfirmationForm({id:'check'},'decision');
  assert.deepEqual(JSON.parse(JSON.stringify(context.measurementReportInput())),{source_artifact_ids:['expected-source','counterevidence']});
  controls['#feedback-subject-confirm'].checked=true;
  assert.deepEqual(JSON.parse(JSON.stringify(context.measurementReportInput())).reported_subject_refs,refs);
  context.subjectConfirmationForm({id:'legacy-check'},'decision');
  assert.equal(Object.hasOwn(context.measurementReportInput(),'reported_subject_refs'),false);
});

test('RNA record identity retains unknown chemistry and version while unsafe source text stays text',()=>{
  const context=view(),subject={role:'candidate',artifact_id:'rna-source',artifact_title:'Candidate <script>change()</script>',artifact_sha256:'original-version',json_pointer:'/rows/0',snapshot:{id:'same-guide'},context:{reference:{transcript_id:'ENST1',version:8}},display:{label:'Same guide',guide_5to3:'ACGU',chemistry:'unknown'}};
  const html=context.subjectRecordsView([subject]);
  assert.match(html,/ENST1 · 버전 8/);assert.match(html,/미확인/);assert.match(html,/data-source-offset="0"/);
  assert.match(html,/original-version/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
  const unknown=context.measurementReportView({subject_binding:{comparison:{status:'unknown'},expected:[subject],reported:[]}});
  assert.match(unknown,/어느 대상의 관측인지 확인/);assert.match(unknown,/Same guide/);
  const changed=context.measurementReportView({subject_binding:{comparison:{status:'mismatch'},expected:[subject],reported:[{...subject,display:{...subject.display,chemistry:'modified'}}]}});
  assert.match(changed,/보고한 대상 기록이 원래 확인과 다릅니다/);assert.match(changed,/modified/);
});

test('saved reported conditions and bound source versions are escaped and distinguishable from interpretation',()=>{
  const context=view(),html=context.measurementReportView({measurement_report:{measurement_validity:'failed',intervention_status:'validated',precision:'insufficient',context_match:true,assessment_basis:'Detector <script>changeDecision()</script>'},source_artifact_refs:[{id:'original',title:'Assay export',kind:'source_file',sha256:'source-version-hash'}]});
  assert.match(html,/입력자가 보고한 측정 조건/);assert.match(html,/실패/);assert.match(html,/부족/);
  assert.match(html,/source-version-hash/);assert.match(html,/Assay export/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});

test('a conflicting model assessment retains the reported failure without displaying a usable biological classification',()=>{
  const context=view(),result={problem:{immediate_decision:'Which observation changes the next action?',worlds:[{id:'a',description:'One explanation'},{id:'both',description:'Coexisting explanations'}],actions:[]},checks:[{id:'check',question:'Paired readout',possible_outcomes:[{observation:'FUNCTIONAL EFFECT LOST'}]}],summary:{selection_status:'report_confirmation_required',retained_configuration_ids:['a','both']},rows:[],report_guard:{applied:true},result_assessment:{check_id:'check',outcome_index:0,context_match:true,intervention_status:'validated',measurement_validity:'validated',precision:'adequate',assessment_basis:'Model interpretation'},observed_events:[{origin:'researcher_report',text:'The readout failed.',measurement_report:{measurement_validity:'failed',intervention_status:'validated',precision:'unknown',context_match:true}}],measurement_report_comparison:[{message_id:'observation',differences:[{field:'measurement_validity',reported:'failed',interpreted:'validated'}]}]};
  const html=context.nextObservationSelectionTable(result);
  assert.match(html,/보고한 측정 조건을 먼저 확인/);assert.match(html,/관측 보고와 모델 해석이 다른 부분/);
  assert.match(html,/Coexisting explanations/);assert.match(html,/The readout failed/);
  assert.match(html,/모델 해석/);assert.doesNotMatch(html,/FUNCTIONAL EFFECT LOST/);
});

test('an unconfirmed candidate keeps alternatives visible and hides a passing model outcome',()=>{
  const context=view(),result={problem:{worlds:[{id:'a',description:'First explanation'},{id:'b',description:'Second explanation'}]},checks:[{id:'check',question:'Compare the recorded candidate',possible_outcomes:[{observation:'CANDIDATE OUTPERFORMS COMPARATOR'}]}],summary:{selection_status:'subject_confirmation_required',retained_configuration_ids:['a','b']},subject_guard:{applied:true,comparison:{status:'unknown'}},result_assessment:{check_id:'check',outcome_index:0,context_match:true,intervention_status:'validated',measurement_validity:'validated',precision:'adequate'}};
  const html=context.nextObservationSelectionTable(result);
  assert.match(html,/관측한 후보·조건 기록을 먼저 확인/);
  assert.match(html,/First explanation/);assert.match(html,/Second explanation/);
  assert.doesNotMatch(html,/CANDIDATE OUTPERFORMS COMPARATOR/);
});
