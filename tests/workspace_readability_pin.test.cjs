const reviewHarness=require('./ui_browser_fixture.cjs');
function reviewRun(code,ctx){return reviewHarness.run(code,ctx,require('node:path').join(__dirname,'../web'));}
// UI-only boundary tests. Scientific content below comes from preserved actual decisions.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const original=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/workspace_als_recorded_decisions.json'),'utf8'));
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const defaultIds=['ws_3c8fe9df9cd14339','ws_4475545a286541b2','ws_1ff05aa2d7c24e0e'];
function setup(pathname='/',storage=new Map()){
  const current=original.records.at(-1);
  const state={id:original.workspace_id,rev:15,decision_rev:15,decision_id:current.id,
    decision:structuredClone(current.result),artifacts:original.records.map(r=>({id:r.id,kind:'decision_proposal',title:'현재 판단 제안',sha256:r.artifact_sha256})),
    events:original.records.map(r=>({seq:r.published_sequence,kind:'decision_published',body:{receipt_id:r.id,state_rev:r.revision}}))};
  const localStorage={getItem:k=>storage.has(k)?storage.get(k):null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
  const context=vm.createContext({state,projects:[...defaultIds.map((id,i)=>({id,title:'핵심 연구 '+i,rev:[4,15,8][i]})),{id:'ws_arbitrary',title:'연구자가 고른 별도 연구',rev:3}],
    location:{pathname},localStorage,esc,json:v=>`<pre>${esc(JSON.stringify(v,null,2))}</pre>`,
    button:(action,label,attrs='',cls='')=>`<button data-action="${action}" ${attrs} class="${cls}">${label}</button>`,
    list:items=>`<ul>${(items||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`,sourceLinks:ids=>(ids||[]).map(id=>`<button data-action="source" data-id="${esc(id)}">원자료</button>`).join(''),
    document:{addEventListener(){},querySelector(){return null},querySelectorAll(){return []},getElementById(){return null}},window:{addEventListener(){}},matchMedia:()=>({matches:false}),
    api:()=>{throw Error('UI preference or stored rendering must not submit a request')},notice:()=>{},render:()=>{},
    candidateOptions:()=>[],status:{gateway:{available:false}}});
  for(const file of ['deployment.js','research.js','workspace-ui.js','research-path.js','roadmap.js'])reviewRun(fs.readFileSync(path.join(__dirname,'../web',file),'utf8'),context);
  context.candidateOptions=()=>[];
  return {context,storage};
}
const plain=v=>JSON.parse(JSON.stringify(v));

test('Any stored research can be pinned; unpinning every initial suggestion remains empty after reload',()=>{
  const {context:c,storage}=setup(),before=JSON.stringify(c.state);
  assert.deepEqual(plain(c.researchRailGroups().pinned.map(p=>p.id)),defaultIds);
  assert.equal(c.toggleResearchPin('ws_arbitrary'),true);
  assert.ok(c.renderResearchRail().includes('aria-label="연구자가 고른 별도 연구 · 고정 해제"'));
  assert.equal(c.toggleResearchPin('ws_not_in_this_list'),false);
  for(const id of [...defaultIds,'ws_arbitrary'])c.toggleResearchPin(id);
  assert.deepEqual(plain(setup('/',storage).context.researchRailGroups().pinned),[]);
  assert.equal(JSON.stringify(c.state),before);
});

test('Pinned research survives recent-list truncation; search keeps real identities with no duplicates',()=>{
  const {context:c}=setup();
  c.projects=[...Array.from({length:12},(_,i)=>({id:'recent'+i,title:'최근 연구 '+i})),...c.projects];
  assert.deepEqual(plain(c.researchRailGroups().pinned.map(p=>p.id)),defaultIds);
  assert.equal(c.researchRailGroups().others.length,8);
  assert.equal(c.researchRailGroups().hasMore,true);
  reviewRun("researchSearch='핵심 연구 1'",c);
  assert.deepEqual(plain(c.researchRailGroups().pinned.map(p=>p.id)),[defaultIds[1]]);
  assert.equal(c.researchRailGroups().others.length,0);
  reviewRun("researchSearch=''; researchListMode='all'",c);
  const all=[...c.researchRailGroups().pinned,...c.researchRailGroups().others];
  assert.equal(new Set(all.map(p=>p.id)).size,c.projects.length);
});

test('Preview pin settings are isolated by the actual deployment helper and cannot change main pins',()=>{
  const shared=new Map(),main=setup('/',shared).context,preview=setup('/preview/',shared).context;
  main.toggleResearchPin('ws_arbitrary');preview.toggleResearchPin(defaultIds[0]);
  assert.equal(main.pinnedResearchIds().includes('ws_arbitrary'),true);
  assert.equal(preview.pinnedResearchIds().includes('ws_arbitrary'),false);
  assert.equal(main.pinnedResearchIds().includes(defaultIds[0]),true);
  assert.equal(preview.pinnedResearchIds().includes(defaultIds[0]),false);
  assert.deepEqual([...shared.keys()].sort(),['evida-pinned-research','evida-preview:evida-pinned-research']);
});

test('Published decision identity determines research record 2/14/15; an unrelated draft gets no historical label',()=>{
  const {context:c}=setup(),before=JSON.stringify(c.state);
  for(const row of original.records){const record=c.uiDecisionRecord(row.id);
    assert.equal(record.rev,row.revision);assert.equal(record.current,row.revision===15);
    assert.equal(record.title,`${row.revision===15?'현재 게시 판단':'이전 판단'} · 연구 기록 ${row.revision}`);
  }
  assert.equal(c.uiDecisionRecord('art_unpublished'),null);
  assert.equal(JSON.stringify(c.state),before);
});

test('Actual ALS historical cards retain every original question, operation, outcome and source without execution controls',()=>{
  const {context:c}=setup(),before=JSON.stringify(c.state);
  for(const row of original.records){const raw=JSON.stringify(row.result),artifact=c.state.artifacts.find(a=>a.id===row.id),html=c.uiRecordedDecisionView(row.result,artifact);
    assert.ok(html.includes(`${row.revision===15?'현재 게시 판단':'이전 판단'} · 연구 기록 ${row.revision}`));
    for(const check of row.result.research_loop.next_checks){
      assert.ok(html.includes(`data-recorded-check="${check.id}"`));
      assert.ok(html.includes(esc(check.question)));
      assert.ok(html.includes(esc(check.operation.request??check.operation.method??'')));
      for(const id of check.operation.grounded_in??[])assert.ok(html.includes(`data-id="${id}"`));
      for(const outcome of check.possible_outcomes??[]){assert.ok(html.includes(esc(outcome.observation)));assert.ok(html.includes(esc(outcome.implication)));}
    }
    assert.ok(html.includes(esc(JSON.stringify(row.result,null,2))),'complete original remains inspectable');
    assert.doesNotMatch(html,/data-action="(?:run-check|delegate-check|check-feedback|save-feedback)"/);
    assert.equal(JSON.stringify(row.result),raw);
  }
  assert.equal(JSON.stringify(c.state),before);
});

test('Selecting a visible mechanism changes only browser focus and retains old and unreviewed mechanisms',async()=>{
  const {context:c}=setup();
  c.state.discovery={mechanisms_and_approaches:[
    {option_id:'mechanism:a',kind:'mechanism',label:'원 기전 A',assessment:{based_rev:15,status:'recommended',priority:1}},
    {option_id:'mechanism:b',kind:'mechanism',label:'원 기전 B',assessment:{based_rev:15,status:'alternative',priority:2}},
    {option_id:'mechanism:older',kind:'mechanism',label:'이전 기전',assessment:{based_rev:2,status:'needs_evidence'}},
    {option_id:'mechanism:unread',kind:'mechanism',label:'미검토 기전'}]};
  const before=JSON.stringify(c.state);
  await c.pathAction('path-select',{dataset:{id:'mechanism:b'}});
  let html=c.renderResearchPath();assert.match(html,/data-id="mechanism:b" aria-pressed="true"/);
  assert.match(html,/질환·목표의 근거와 후보의 기능 확인을 각각 살펴보세요./);
  for(const id of ['a','b','older','unread'])assert.ok(html.includes(`data-path-option="mechanism:${id}"`));
  await c.pathAction('path-select',{dataset:{id:'mechanism:foreign'}});
  assert.match(c.renderResearchPath(),/data-id="mechanism:b" aria-pressed="true"/);
  assert.equal(JSON.stringify(c.state),before);
});

test('Actual IPF BindingDB source parent wording changes only the display while family parents and raw text remain exact',()=>{
  const {context:c}=setup(),fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/workspace_experiment_actual_cases.json'),'utf8'));
  const ipf=fixture.cases.find(x=>x.case==='ipf'),before=JSON.stringify(ipf),question=ipf.state.decision.research_loop.next_checks[0].question;
  assert.ok(question.includes('BindingDB 출처 부모'));
  assert.ok(c.researcherWording(question).includes('BindingDB에 기록된 출발 화합물'));
  assert.equal(c.researcherWording('BindingDB 부모 12개'),'BindingDB에 기록된 출발 화합물 12개');
  assert.equal(c.researcherWording('BindingDB 조회와 부모 및 환자의 유전형은 다른 문맥이다.'),'BindingDB 조회와 부모 및 환자의 유전형은 다른 문맥이다.');
  assert.equal(c.researcherWording('부모–제안 쌍의 화합물 비교'),'출발 화합물–제안 쌍의 화합물 비교');
  assert.equal(c.judgmentText('BindingDB 출처 부모'), 'BindingDB 출처 부모');
  assert.equal(JSON.stringify(ipf),before);
});

test('Research record labels derive from the selected study and retain stale-input distinction',()=>{
  const {context:c}=setup();
  assert.equal(c.roadmapRevisionText({current:true}),'연구 기록 15 · 현재 조건의 판단');
  c.state.rev=8;c.state.decision_rev=8;
  assert.equal(c.roadmapRevisionText({current:true}),'연구 기록 8 · 현재 조건의 판단');
  c.state.rev=9;
  assert.match(c.roadmapRevisionText({current:false}),/이전 판단 · 연구 기록 8 \/ 현재 연구 기록 9/);
});
