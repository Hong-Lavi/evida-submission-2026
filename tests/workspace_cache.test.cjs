const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const sourceRoot=process.env.EVIDA_CACHE_TEST_ROOT||path.resolve(__dirname,'..');
function harness(file){
  const requests=[];
  const ctx=vm.createContext({state:{id:'A',event_cursor:1,rev:1},render(){},
    esc:String,document:{addEventListener(){}},URLSearchParams,
    api:url=>new Promise((resolve,reject)=>requests.push({url,resolve,reject}))});
  vm.runInContext(fs.readFileSync(path.join(sourceRoot,'web',file),'utf8'),ctx);
  return {ctx,requests};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function rankHarness(){
  const h=harness('mechanism-rank.js');
  vm.runInContext('mechanismRankView=value=>JSON.stringify(value)',h.ctx);
  return h;
}
test('Changing research hides the previous ranking and fetches the new research',async()=>{
  const {ctx,requests}=rankHarness();
  const first=ctx.loadMechanismRanking();requests[0].resolve({marker:'효소 A 억제'});await first;
  assert.match(ctx.mechanismRankSection(),/효소 A/);
  ctx.state={id:'B',event_cursor:1,rev:1};
  assert.doesNotMatch(ctx.mechanismRankSection(),/효소 A/);
  assert.equal(requests.length,2);assert.match(requests[1].url,/B\/mechanism-ranking/);
  requests[1].resolve({marker:'PDE4B'});await tick();
  assert.match(ctx.mechanismRankSection(),/PDE4B/);
});
test('New events and input revisions invalidate the ranking within one research',async()=>{
  const {ctx,requests}=rankHarness();
  let run=ctx.loadMechanismRanking();requests[0].resolve({marker:'old'});await run;
  for(const [field,value] of [['event_cursor',2],['rev',2]]){
    ctx.state[field]=value;
    assert.doesNotMatch(ctx.mechanismRankSection(),/"old"/);
    requests.at(-1).resolve({marker:`new-${field}`});await tick();
    assert.match(ctx.mechanismRankSection(),new RegExp(`new-${field}`));
  }
  assert.equal(requests.length,3);
});
test('Repeated rendering keeps one pending ranking request alive',async()=>{
  const {ctx,requests}=rankHarness();
  ctx.mechanismRankSection();ctx.mechanismRankSection();ctx.mechanismRankSection();
  assert.equal(requests.length,1);
  requests[0].resolve({marker:'ready'});await tick();
  assert.match(ctx.mechanismRankSection(),/ready/);
});
test('A late ranking success or error cannot replace a newer research result',async()=>{
  for(const fails of [false,true]){
    const {ctx,requests}=rankHarness();
    const a=ctx.loadMechanismRanking();ctx.state={id:'B',event_cursor:2,rev:2};
    const b=ctx.loadMechanismRanking();requests[1].resolve({marker:'B-ready'});await b;
    fails?requests[0].reject(Error('old failure')):requests[0].resolve({marker:'A-late'});await a;
    assert.match(ctx.mechanismRankSection(),/B-ready/);assert.doesNotMatch(ctx.mechanismRankSection(),/old failure|A-late/);
  }
});
test('Support check from old conditions is not attached to the new input revision',async()=>{
  const {ctx,requests}=rankHarness();
  const a=ctx.loadMechanismRanking();requests[0].resolve({marker:'A'});await a;
  const support=ctx.loadMechanismSupport();ctx.state.rev=2;ctx.state.event_cursor=3;
  ctx.mechanismRankSection();requests[2].resolve({marker:'new conditions'});await tick();
  requests[1].resolve({marker:'old support'});await support;
  assert.match(ctx.mechanismRankSection(),/new conditions/);
});
test('Repeated renders do not cancel an in-flight structure drawing',async()=>{
  const {ctx,requests}=harness('roadmap.js');
  const first=ctx.loadCandidateStructures();await ctx.loadCandidateStructures();await ctx.loadCandidateStructures();
  assert.equal(requests.length,1);
  requests[0].resolve({rows:[{option_id:'molecule:shared',depiction:{formula:'C2H6O'}}]});await first;
  assert.equal(ctx.candidateStructureRow('molecule:shared')?.depiction.formula,'C2H6O');
});
test('Same candidate ID in another research never receives the old drawing',async()=>{
  const {ctx,requests}=harness('roadmap.js');
  const a=ctx.loadCandidateStructures();requests[0].resolve({rows:[{option_id:'molecule:shared',marker:'A'}]});await a;
  ctx.state={id:'B',event_cursor:2,rev:2};
  assert.equal(ctx.candidateStructureRow('molecule:shared'),null);
  const b=ctx.loadCandidateStructures();requests[1].resolve({rows:[{option_id:'molecule:shared',marker:'B'}]});await b;
  assert.equal(ctx.candidateStructureRow('molecule:shared').marker,'B');
  ctx.state.rev=3;assert.equal(ctx.candidateStructureRow('molecule:shared'),null);
});
test('Late structure response or error cannot clear new research drawings',async()=>{
  for(const fails of [false,true]){
    const {ctx,requests}=harness('roadmap.js');
    const a=ctx.loadCandidateStructures();ctx.state={id:'B',event_cursor:2,rev:2};
    const b=ctx.loadCandidateStructures();requests[1].resolve({rows:[{option_id:'x',marker:'B'}]});await b;
    fails?requests[0].reject(Error('old error')):requests[0].resolve({rows:[{option_id:'x',marker:'A'}]});await a;
    assert.equal(ctx.candidateStructureRow('x').marker,'B');
  }
});
test('Discovery result from an earlier revision is not stamped with the new revision',async()=>{
  const {ctx,requests}=harness('discovery.js');vm.runInContext('optionsOpen=true',ctx);
  const a=ctx.loadOptions();ctx.state.event_cursor=2;ctx.state.rev=2;
  requests[0].resolve({rows:[{label:'old input'}]});await a;
  assert.equal(vm.runInContext('optionsPage',ctx),null);
});
test('A late discovery error cannot hide the next research results',async()=>{
  const {ctx,requests}=harness('discovery.js');vm.runInContext('optionsOpen=true',ctx);
  const a=ctx.loadOptions();ctx.state={id:'B',event_cursor:2,rev:2};
  const b=ctx.loadOptions();requests[1].resolve({rows:[{label:'B'}]});await b;
  requests[0].reject(Error('old failure'));await a;
  assert.equal(vm.runInContext('optionsError',ctx),'');
  assert.equal(vm.runInContext('optionsPage.rows[0].label',ctx),'B');
});
test('A candidate detail clicked before switching research cannot open in the new research',async()=>{
  const {ctx,requests}=harness('discovery.js');
  const a=ctx.getOption('shared');ctx.state={id:'B',event_cursor:2,rev:2};
  requests[0].resolve({rows:[{option_id:'shared',label:'A'}]});
  await assert.rejects(a,/연구가 바뀌었습니다/);
});
test('A slow project click cannot overwrite the project selected afterwards',async()=>{
  const code=fs.readFileSync(path.join(sourceRoot,'web/app.js'),'utf8');
  const requests=[],statusRefreshes=[];
  const ctx=vm.createContext({URL,location:{href:'https://local.test/',pathname:'/'},history:{replaceState(){}},
    localStorage:{getItem(){return null},setItem(){}},projectLoadVersion:0,state:null,
    draftKey:()=>'',render(){},window:{scrollTo(){}},optionsOpen:false,
    async refreshGatewayStatus(){statusRefreshes.push(ctx.state.id)},
    api:url=>new Promise(resolve=>requests.push({url,resolve}))});
  vm.runInContext(fs.readFileSync(path.join(sourceRoot,'web/deployment.js'),'utf8'),ctx);
  // Run the actual project loader, omitting unrelated application bootstrap/DOM setup.
  vm.runInContext(code.slice(code.indexOf('async function loadProject('),code.indexOf('async function refresh(')),ctx);
  const first=ctx.loadProject('A'),second=ctx.loadProject('B');
  requests[1].resolve({id:'B'});await second;
  requests[0].resolve({id:'A'});await first;
  assert.equal(ctx.state.id,'B');
  assert.deepEqual(statusRefreshes,['B']);
});
