const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/roadmap-model.js'),'utf8'),context);
const build=(...args)=>JSON.parse(JSON.stringify(context.buildResearchRoadmap(...args)));
const empty=()=>({id:'w',rev:0,decision_rev:null,events:[],artifacts:[],jobs:[]});
const hypothesis=(assessment='proposed')=>({id:'H1',statement:'同じ仮説',expected_observation:'unchanged prediction',assessment,evidence:[],rationale:'recorded reason'});
const decision=(h=hypothesis())=>({intent_records:[],alternatives:[],next_actions:[],research_loop:{hypotheses:[h],next_checks:[]}});
const withHistory=(now,old)=>{
 const s={...empty(),rev:4,decision_rev:4,decision_id:'now',decision:now,
   events:[{seq:1,kind:'hypothesis_wording_compared',body:{receipt_id:'now',reference:{decision_id:'old'}}}]};
 return [s,[],{status:'ready',workspaceId:'w',currentId:'now',previousId:'old',decision:old}];
};
test('An empty project never claims a completed scientific stage',()=>{
 const m=build(empty());assert.equal(m.nodes.length,5);assert(m.nodes.every(n=>n.mark==='empty'));assert.equal(m.current,false);
 assert(!JSON.stringify(m).includes('완료'));assert.equal(m.previous,null);
});
test('Researcher selection outside recommendations is retained without scientific approval',()=>{
 const s={...empty(),rev:2,discovery:{counts:{molecule:50},total:50,recommendations:[],
   selected:{option_id:'molecule:rank13',label:'Candidate13',state_rev:2,reason:'A different condition'}}};
 const m=build(s),n=m.nodes.find(x=>x.id==='candidates');
 assert.equal(n.summary,'Candidate13');assert.equal(n.count,50);assert.equal(n.mark,'selected');
 assert.equal(m.nodes.length,5);assert(!JSON.stringify(m).includes('검증됨'));
});
test('New needs-evidence candidate is visible under its recorded mechanism without becoming recommended',()=>{
 const option={option_id:'molecule:generated:a:proposed-1',kind:'molecule',label:'proposed-1',
   assessment:{status:'needs_evidence',current_conditions:true,artifact_id:'review',
     targets_mechanism:{option_id:'mechanism:lpar1',reason:'source target only'}}};
 const s={...empty(),rev:4,artifacts:[{id:'review',meta:{job_id:'j'}}],jobs:[{id:'j',status:'succeeded'}],
   discovery:{counts:{molecule:1338},recommendations:[],reconsidered_options:[],reviewed_options:[option]}};
 const n=build(s).nodes.find(x=>x.id==='candidates');
 assert.equal(n.options.length,1);assert.equal(n.options[0].assessment.status,'needs_evidence');
 assert.equal(n.options[0].assessment.targets_mechanism.option_id,'mechanism:lpar1');
 assert.equal(n.recommended.length,0);assert.equal(n.count,1338);
 assert.match(n.status,/검토 기록 1개/);
});
test('Selected unreviewed structure is visible and overlapping recommendation projections are deduplicated',()=>{
 const option={option_id:'molecule:x',kind:'molecule',label:'X',assessment:null};
 const s={...empty(),discovery:{counts:{molecule:12},selected:{option_id:'molecule:x',label:'X'},
   selected_option:option,reviewed_options:[],recommendations:[]}};
 let n=build(s).nodes.find(x=>x.id==='candidates');
 assert.equal(n.options.length,1);assert.equal(n.options[0].assessment,null);assert.equal(n.mark,'selected');
 s.discovery.recommendations=[option];s.discovery.reviewed_options=[option];
 n=build(s).nodes.find(x=>x.id==='candidates');assert.equal(n.options.length,1);
});
test('Outdated recommendation remains earlier even with a current unrelated decision',()=>{
 const s={...empty(),rev:5,decision_rev:5,decision:decision(),discovery:{counts:{target:1},recommendations:[
   {option_id:'target:x',kind:'target',label:'Target X',assessment:{status:'recommended',current_conditions:false}}]}};
 const m=build(s);assert.equal(m.current,true);assert.equal(m.nodes[1].mark,'earlier');assert.equal(m.nodes[1].recommended.length,0);
});
test('Changed assessment with unchanged wording highlights judgment, not all upstream decisions',()=>{
 const args=withHistory(decision(hypothesis('challenged')),decision(hypothesis()));
 const m=build(...args);assert.deepEqual(m.diffs.hypotheses[0].fields,['assessment']);
 assert.equal(m.nodes[3].change,'판단 기록 변경');assert.equal(m.nodes[1].change,null);assert.equal(m.nodes[4].change,null);
});
test('Omitted hypotheses remain explicit historical omissions, not scientific rejection',()=>{
 const now=decision();now.research_loop.hypotheses=[];
 const m=build(...withHistory(now,decision()));
 assert.equal(m.diffs.hypotheses[0].status,'omitted');assert.equal(m.diffs.hypotheses[0].before.assessment,'proposed');
});
test('Unloaded or mismatched previous decision cannot claim unchanged',()=>{
 const args=withHistory(decision(),decision());args[2].currentId='another';const m=build(...args);
 assert.equal(m.previous,null);assert.equal(m.diffs,null);assert.equal(m.nodes[3].change,null);
});
test('New input leaves published results stale until an actual judgment arrives',()=>{
 const args=withHistory(decision(),decision());args[0].rev=5;
 args[0].input_changes={phase:'pending_review',after_event:1,messages:[{id:'m'}],sources:[]};
 args[0].events.push({seq:2,kind:'correction',body:{message_id:'m',text:'new condition'}});
 const m=build(...args);assert.equal(m.current,false);assert.equal(m.hasNewInput,true);assert.equal(m.nodes[3].mark,'earlier');
});
test('An existing successful check is not incorrectly labelled unperformed',()=>{
 const s={...empty(),rev:1,decision_rev:1,decision_id:'d',decision:decision()};
 s.decision.research_loop.next_checks=[{id:'c',question:'q'}];
 s.research_checks=[{decision_id:'d',check_id:'c',job_id:'j'}];s.jobs=[{id:'j',status:'succeeded'}];
 const m=build(s);assert.equal(m.nodes[4].status,'결과 해석 확인');assert.equal(m.nodes[4].jobStatus,'succeeded');
});
test('Large discovered pool does not create a branching roadmap or change scientific rank',()=>{
 const rows=Array.from({length:50},(_,i)=>({option_id:'target:'+i,kind:'target',label:'T'+i,assessment:{status:'recommended',current_conditions:true,priority:i+1}}));
 const s={...empty(),discovery:{counts:{target:50},recommendations:rows}};const original=JSON.stringify(s),m=build(s);
 assert.equal(m.nodes.length,5);assert.equal(m.nodes[1].options.length,50);assert.equal(JSON.stringify(s),original);
});
test('Object key order is immaterial but array order and missing versus null remain visible',()=>{
 const old=decision(),now=decision();old.research_loop.hypotheses[0].evidence=[{detail:'same',relation:'context'}];
 now.research_loop.hypotheses[0].evidence=[{relation:'context',detail:'same'}];
 assert.equal(build(...withHistory(now,old)).diffs.hypotheses[0].status,'unchanged');
 assert.equal(context.roadmapSame([1,2],[2,1]),false);
 assert.equal(context.roadmapSame({value:null},{}),false);
});
test('A changed nested part is identified without marking its sibling as changed',()=>{
 const old=decision(),now=decision();
 old.research_loop.hypotheses[0].assessment_scope={parts:[{id:'P1',statement:'a',assessment:'proposed'},{id:'P2',statement:'b',assessment:'proposed'}]};
 now.research_loop.hypotheses[0].assessment_scope=JSON.parse(JSON.stringify(old.research_loop.hypotheses[0].assessment_scope));
 now.research_loop.hypotheses[0].assessment_scope.parts[1].assessment='inconclusive';
 const m=build(...withHistory(now,old));
 assert.equal(m.diffs.claims[0].status,'unchanged');assert.equal(m.diffs.claims[1].status,'changed');
 assert.deepEqual(m.diffs.claims[1].fields,['assessment']);assert.equal(m.diffs.claims[1].id,'H1/part/P2');
});
test('A removed nested claim remains an omission and ambiguous IDs are incomparable',()=>{
 const old=decision(),now=decision();old.research_loop.hypotheses[0].conditional_alternatives=[{id:'A1',statement:'a'}];
 assert.equal(build(...withHistory(now,old)).diffs.claims[0].status,'omitted');
 old.research_loop.hypotheses.push(hypothesis());
 assert.equal(build(...withHistory(now,old)).diffs.hypotheses[0].status,'unavailable');
});
test('A late response from a different workspace cannot be compared as this workspace history',()=>{
 const args=withHistory(decision(),decision());args[2].workspaceId='other';
 const m=build(...args);assert.equal(m.previous,null);assert.equal(m.historyStatus,'unavailable');
});
test('Running and failed producers remain drafts even if current_conditions is true',()=>{
 for(const status of ['running','failed']){
  const s={...empty(),rev:1,artifacts:[{id:'a',meta:{job_id:'j'}}],jobs:[{id:'j',status}],
   discovery:{counts:{target:1},recommendations:[{kind:'target',option_id:'target:x',label:'X',assessment:{artifact_id:'a',current_conditions:true,status:'recommended'}}]}};
  let n=build(s).nodes[1];assert.equal(n.mark,'draft');assert.equal(n.recommended.length,0);
  s.jobs[0].status='succeeded';n=build(s).nodes[1];assert.equal(n.mark,'proposed');assert.equal(n.recommended.length,1);
 }
});

test('Unresolved source candidates remain in the candidate stage without invented ranking',()=>{
 const s={...empty(),discovery:{counts:{source_candidate:17},recommendations:[],selected:{option_id:'source-candidate:paper-local',kind:'source_candidate',label:'C6',state_rev:0}}};
 const m=build(s),n=m.nodes.find(x=>x.id==='candidates');
 assert.equal(n.count,17);assert.equal(n.summary,'C6');assert.equal(n.mark,'selected');assert.equal(n.recommended.length,0);assert.equal(m.nodes.length,5);
});

const activity=s=>{const value=context.currentResearchActivity(s);return value?JSON.parse(JSON.stringify(value)):null};
test('Current check follows exact result provenance, not first recommendation or reused NC label',()=>{
 const s={rev:13,jobs:[
  {id:'old',kind:'research_check',status:'failed',output_id:'old-result',request:{check:{id:'NC3',question:'Old label question'}}},
  {id:'new',kind:'research_check',status:'failed',output_id:'new-result',request:{check:{id:'NC3',question:'Extension evidence'}}},
  {id:'planner',kind:'planner',status:'running',based_rev:13,request:{source_views:[{artifact_id:'new-result'}]}}
 ]};assert.equal(activity(s).question,'Extension evidence');assert.equal(activity(s).status,'확인 실패 기록 검토 중');assert.equal(activity(s).checkJobId,'new');
});
test('Old held planner is not shown as current activity after a newer decision',()=>{
 const s={rev:14,jobs:[{id:'c',kind:'research_check',status:'succeeded',output_id:'x',request:{check:{question:'Old'}}},{id:'p',kind:'planner',status:'paused',based_rev:13,request:{source_views:[{artifact_id:'x'}]}}]};assert.equal(activity(s),null);
});
test('Pending interpretation is distinct from scientific success',()=>{
 const s={rev:13,jobs:[{id:'c',kind:'research_check',status:'succeeded',output_id:'x',request:{check:{question:'Measured result'}}},{id:'p',kind:'planner',status:'running',based_rev:13,request:{source_views:[{artifact_id:'x'}]}}]};assert.equal(activity(s).status,'새 결과 검토 중');s.jobs[1].status='paused';assert.equal(activity(s).status,'해석 보류 · 원기록 보존');
});
test('Unlinked active planner does not invent a relationship to a check',()=>{
 assert.equal(activity({rev:13,jobs:[{id:'p',kind:'planner',status:'running',request:{}}]}),null);
});
test('Queued selected check has an explicit wait status',()=>{
 assert.equal(activity({jobs:[{id:'c',kind:'research_check',status:'queued',request:{check:{question:'Question'}}}]}).status,'선택한 확인 대기 중');
});

// Regression from the real candidate24 synthesis: same input revision, new publication.
test('A later publication supersedes an older paused review at the same revision',()=>{
 const s={rev:13,decision_rev:13,decision_id:'d2',jobs:[{id:'c',kind:'research_check',status:'failed',output_id:'x',request:{check:{question:'Original query'}}},{id:'p',kind:'planner',status:'paused',based_rev:13,request:{source_views:[{artifact_id:'x'}]}}],events:[{seq:10,kind:'job_finished',body:{job_id:'p',status:'paused'}},{seq:12,kind:'decision_published',body:{receipt_id:'d2',state_rev:13}}]};
 const saved=JSON.stringify(s);assert.equal(activity(s),null);assert.equal(JSON.stringify(s),saved);
 s.events[0].seq=14;assert.equal(activity(s).status,'해석 보류 · 원기록 보존');
});
test('A publication for a different receipt cannot hide a paused review',()=>{
 const s={rev:13,decision_id:'current',jobs:[{id:'c',kind:'research_check',status:'succeeded',output_id:'x',request:{check:{question:'Check'}}},{id:'p',kind:'planner',status:'paused',based_rev:13,request:{source_views:[{artifact_id:'x'}]}}],events:[{seq:10,kind:'job_finished',body:{job_id:'p',status:'paused'}},{seq:12,kind:'decision_published',body:{receipt_id:'another'}}]};
 assert.equal(activity(s).status,'해석 보류 · 원기록 보존');
});
test('An active review remains visible when an older decision exists',()=>{
 const s={rev:13,decision_id:'d2',jobs:[{id:'c',kind:'research_check',status:'succeeded',output_id:'x',request:{check:{question:'New check'}}},{id:'p',kind:'planner',status:'running',based_rev:13,request:{source_views:[{artifact_id:'x'}]}}],events:[{seq:10,kind:'job_finished',body:{job_id:'p',status:'paused'}},{seq:12,kind:'decision_published',body:{receipt_id:'d2'}}]};
 assert.equal(activity(s).status,'새 결과 검토 중');
});
const usage=s=>JSON.parse(JSON.stringify(context.roadmapToolUsage(s)));
test('Tool usage separates returned results from cited judgment evidence',()=>{
 const h={...hypothesis(),evidence:[{relation:'supports',source_type:'artifact',source_id:'art_cited#row:3'}]};
 const s={...empty(),rev:2,decision_rev:2,decision:decision(h),
  jobs:[{id:'j1',kind:'article',status:'succeeded',output_id:'art_cited',request:{pmc_id:'PMC1'}},
        {id:'j2',kind:'rdkit',status:'succeeded',output_id:'art_calc',request:{artifact_id:'art_x'}},
        {id:'p1',kind:'planner',status:'succeeded',output_id:'art_decision',request:{synthesis_only:true}}],
  artifacts:[{id:'art_cited',kind:'article',meta:{result_status:'succeeded',arguments:{pmc_id:'PMC1'}}},
             {id:'art_calc',kind:'rdkit',meta:{result_status:'succeeded',arguments:{artifact_id:'art_x'}}},
             {id:'r1',kind:'tool_reading',meta:{function:'read_open_article',source_artifact_id:'art_cited'}},
             {id:'r2',kind:'tool_reading',meta:{function:'compute_properties',source_artifact_id:'art_calc'}},
             {id:'m1',kind:'model_receipt',meta:{requested_model:'claude-opus-5'}}]};
 const u=usage(s);
 assert.equal(u.runs,2);assert.equal(u.returned,2);assert.equal(u.cited,1);assert.equal(u.current,true);
 const article=u.tools.find(t=>t.kind==='article'),rdkit=u.tools.find(t=>t.kind==='rdkit');
 assert.equal(article.cited,1);assert.equal(rdkit.returned,1);assert.equal(rdkit.cited,0);
 assert.equal(u.tools[0].kind,'article');assert.deepEqual(u.modelCalls,[{model:'claude-opus-5',count:1}]);
 assert(!u.tools.some(t=>['planner','tool_reading','model_receipt'].includes(t.kind)));
 assert.equal(article.items[0].input,'pmc_id: PMC1');
});
test('Tool usage keeps results without a job and failed jobs without a result',()=>{
 const s={...empty(),rev:3,decision_rev:2,decision:decision(),
  jobs:[{id:'j1',kind:'admet',status:'failed',output_id:null,request:{artifact_id:'art_mol'}}],
  artifacts:[{id:'art_rerun',kind:'admet',meta:{result_status:'succeeded',arguments:{artifact_id:'art_mol'}}}]};
 const u=usage(s),admet=u.tools.find(t=>t.kind==='admet');
 assert.equal(admet.runs,2);assert.deepEqual(admet.statuses,{succeeded:1,failed:1});
 assert.equal(admet.items.find(i=>i.status==='failed').id,null);assert.equal(admet.returned,0);
 assert.equal(u.current,false);
});
test('Explicit source views count as returned without implying citation',()=>{
 const s={...empty(),jobs:[{id:'p',kind:'planner',status:'running',request:{source_views:[{artifact_id:'art_k',offset:0,limit:1}]}}],
  artifacts:[{id:'art_k',kind:'kinetic_conditions',meta:{result_status:'succeeded'}}]};
 const t=usage(s).tools[0];assert.equal(t.returned,1);assert.equal(t.cited,0);
});
test('A running first review marks unrecorded stages as working, never complete',()=>{
 const s={...empty(),rev:2,jobs:[{id:'p',kind:'planner',status:'running',based_rev:2,created:'2026-09-29T11:03:52Z',request:{}}],
  artifacts:[{id:'m1',kind:'model_receipt',meta:{job_id:'p'}},{id:'r1',kind:'tool_reading',meta:{job_id:'p',function:'search_literature'}}],
  research_progress:{job_id:'p',notes:{next_goal:'Extract reported mechanisms',findings:[]}}};
 const m=build(s);assert.equal(m.running,true);assert.equal(m.nodes[0].id,'goal');
 const byId=Object.fromEntries(m.nodes.map(n=>[n.id,n]));
 for(const id of ['mechanisms','candidates','next'])assert.equal(byId[id].mark,'working'),assert.equal(byId[id].status,'조사 중 · 판단 전');
 assert.equal(byId.evidence.status,'자료 2개 · 판단 전');assert(!JSON.stringify(m).includes('완료'));
 const p=JSON.parse(JSON.stringify(context.roadmapLiveProgress(s,Date.parse('2026-09-29T11:23:52Z'))));
 assert.equal(p.elapsedMinutes,20);assert.equal(p.completedCalls,1);assert.deepEqual(p.functions,{search_literature:1});assert.equal(p.nextGoal,'Extract reported mechanisms');
 assert.equal(context.roadmapLiveProgress({...s,jobs:[{...s.jobs[0],status:'succeeded'}]}),null);
});

test('A judgement published after an entered result is reported as answering it',()=>{
 const s={...empty(),rev:3,decision_rev:3,decision_id:'d1',decision:decision(),
   events:[{seq:5,kind:'observation',created:'',body:{text:'실험 결과를 넣었습니다',message_id:'m1'}},
           {seq:9,kind:'decision_published',created:'',body:{receipt_id:'d1'}}]};
 const m=build(s);
 assert.equal(m.answeredObservation?.seq,5);
});

test('A result entered after the judgement is not reported as answered',()=>{
 const s={...empty(),rev:3,decision_rev:3,decision_id:'d1',decision:decision(),
   events:[{seq:9,kind:'decision_published',created:'',body:{receipt_id:'d1'}},
           {seq:12,kind:'observation',created:'',body:{text:'나중에 넣은 결과',message_id:'m2'}}]};
 assert.equal(build(s).answeredObservation,null);
});

test('With no entered result there is nothing to answer',()=>{
 assert.equal(build(empty()).answeredObservation,null);
});
