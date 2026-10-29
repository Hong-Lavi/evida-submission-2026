// Synthetic software metadata only; load every actual UI module in actual order.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const HERE=__dirname,PRODUCT=path.resolve(HERE,'..');
const harness=require(path.join(PRODUCT,'tests/ui_browser_fixture.cjs'));const mapping=JSON.parse(fs.readFileSync(path.join(HERE,'fixtures/ui_computation_registry182.json'),'utf8')).rows;const candidate=fs.readFileSync(path.join(PRODUCT,'web/workspace-ui.js'),'utf8');
function setup(state,api=async()=>{throw Error('unexpected read')}){
 const listeners=[],ctx=vm.createContext({state,status:{gateway:{available:false}},projects:[],busy:false,api,render:()=>{},document:{querySelector:()=>null,querySelectorAll:()=>[],getElementById:()=>null,addEventListener:(name,fn)=>listeners.push({name,fn})},window:{addEventListener(){}},location:{pathname:'/'}});
 const read=fs.readFileSync;fs.readFileSync=function(file,...args){if(path.resolve(String(file))===path.join(PRODUCT,'web/workspace-ui.js'))return candidate;return read.call(this,file,...args)};
 try{harness.run('',ctx,path.join(PRODUCT,'web'));}finally{fs.readFileSync=read}
 return{ctx,listeners};
}
function stateFor(rows=mapping){return{id:'synthetic-software-ui182',rev:2,events:[],artifacts:rows.map((r,i)=>({id:'synthetic_'+i,kind:r.artifact_kind,sha256:'a'.repeat(64),meta:{synthetic_fixture:true,result_status:'succeeded',summary:{total_rows:1,calculated:0},based_rev:1,consumed_artifacts:[]}})),jobs:rows.map((r,i)=>({id:'synthetic_job_'+i,kind:r.worker_kind,status:'succeeded',output_id:'synthetic_'+i}))}}
test('all43 registered computational function outputs are visible with correct source IDs',()=>{
 const state=stateFor(),before=JSON.stringify(state),{ctx}=setup(state);assert.equal(ctx.uiCompletedComputations().length,43);const html=ctx.uiComputationSummary();
 for(let i=0;i<mapping.length;i++)assert.ok(html.includes(`data-id="synthetic_${i}"`),mapping[i].function);assert.ok(html.includes('다른 보존 결과 37개'));assert.ok(html.includes('계산 행 0'));assert.equal(JSON.stringify(state),before);
});
test('pocket docking alias keeps actual worker label and RNA aliases remain visible',()=>{
 const {ctx}=setup(stateFor());const h=ctx.uiComputationSummary();assert.ok(h.includes('명시 포켓 도킹'));assert.ok(h.includes('RNA 서열'));assert.ok(h.includes('단백질 동역학'));assert.ok(h.includes('역합성 경로'));
});
test('failed,partial,missing artifact and missing job are not completed',()=>{
 const s=stateFor(mapping.slice(0,5));s.jobs[0].status='failed';s.artifacts[0].meta.result_status='failed';s.jobs[1].status='partial';s.artifacts[1].meta.result_status='partial';s.jobs[2].output_id='missing';s.jobs[3].status='running';s.jobs[4].status='reused';const {ctx}=setup(s);
 assert.equal(ctx.uiCompletedComputations().length,1);const h=ctx.uiComputationSummary();for(const phrase of ['실패 결과','부분 결과','보존 결과 재사용','원결과 미확인','작업 연결 미확인'])assert.ok(h.includes(phrase),phrase);
});
test('rendering does not fetch any results; details lazy-load once with exact identity',async()=>{
 const s=stateFor(mapping.filter(r=>r.worker_kind==='molecular_docking'));let calls=0;const {ctx}=setup(s,async url=>{calls++;assert.ok(url.includes('/synthetic_0?offset=0&limit=3'));return{artifact_id:'synthetic_0',kind:'molecular_docking',result:{rows:[{affinity:-7.25}],units:{affinity:'kcal/mol'}}}});
 ctx.uiComputationSummary();assert.equal(calls,0);await ctx.uiLoadComputationResult('synthetic_0');await ctx.uiLoadComputationResult('synthetic_0');assert.equal(calls,1);const html=ctx.uiComputationSummary();assert.ok(html.includes('-7.25'));assert.ok(html.includes('kcal/mol'));assert.ok(html.includes('입력은 원순서의 앞 3개'));
});
test('wrong response identity remains read failure and never shows numerical result',async()=>{
 const s=stateFor(mapping.slice(0,1)),{ctx}=setup(s,async()=>({artifact_id:'wrong',kind:s.artifacts[0].kind,result:{rows:[{score:999}]}}));await ctx.uiLoadComputationResult('synthetic_0');const h=ctx.uiComputationSummary();assert.ok(h.includes('원결과 조회에 실패했습니다'));assert.ok(!h.includes('999'));
});
test('zero,negative and unknown-unit values preserved without inventing units or conversion',()=>{
 const {ctx}=setup(stateFor());const rows=ctx.uiComputationValues({rows:[{zero:0,negative:-4.5}],units:{zero:'nm'}});assert.equal(rows[0].value,0);assert.equal(rows[0].unit,'nm');assert.equal(rows[1].value,-4.5);assert.equal(rows[1].unit,'원기록에서 단위 확인');
});
test('toggle only reads expanded computation details; strings are escaped',async()=>{
 let calls=0;const s=stateFor(mapping.slice(0,1));s.artifacts[0].id='synthetic_<unsafe>';const {ctx,listeners}=setup(s,async()=>{calls++;throw Error('synthetic read failure')});const fn=listeners.find(x=>x.name==='toggle').fn;fn({target:{matches:()=>true,open:false,dataset:{computationResult:s.artifacts[0].id}}});await Promise.resolve();assert.equal(calls,0);const html=ctx.uiComputationSummary();assert.ok(!html.includes('data-id="synthetic_<unsafe>"'));assert.ok(html.includes('&lt;unsafe&gt;'));
});
test('known read scope and body locator use plain Korean; raw values/hashes remain in progressive record',()=>{
 const {ctx}=setup(stateFor());const row={id:'PMC_SYNTHETIC',locator:'body.p30;xml_id=Par19',read_scope:'Mainparagraphtext,not independent validation of its citedearlierwork',source_sha256:'a'.repeat(64),locator_sha256:'b'.repeat(64)},before=JSON.stringify(row);const h=ctx.uiReasoningPrincipleBody({section:'sources',principle_id:'synthetic',rows:[row],total_rows:1,offset:0});
 assert.ok(h.includes('본문 30번째 단락'));assert.ok(h.includes('읽은 문헌: 해당 논문의 본문 단락'));assert.ok(h.includes('추가 확인 대상: 본문에서 인용한 선행 연구의 원자료'));const details=h.slice(h.indexOf('<details>'));assert.ok(details.includes(row.locator));assert.ok(details.includes(row.read_scope));assert.ok(details.includes(row.source_sha256));assert.equal(JSON.stringify(row),before);
});
test('unknown scope/locator are not guessed, translated or discarded',()=>{
 const {ctx}=setup(stateFor());const scope='SYNTHETIC_UNKNOWN_SCOPE <keep>',locator='not-a-known-grammar';const h=ctx.uiReasoningPrincipleBody({section:'sources',principle_id:'synthetic',rows:[{id:'PMC_SYNTHETIC',read_scope:scope,locator,source_sha256:'a',locator_sha256:'b'}],total_rows:1,offset:0});assert.ok(h.includes('읽은 범위의 원기록은 아래에서 확인'));assert.ok(h.includes('SYNTHETIC_UNKNOWN_SCOPE &lt;keep&gt;'));assert.ok(h.includes(locator));assert.equal(ctx.uiSourceLocatorLabel('body.p0'),'원문 위치는 식별 기록에서 확인');
});
test('unrelated successful planner job is not computation proof',()=>{const s=stateFor(mapping.slice(0,1));s.jobs[0].kind='planner';const {ctx}=setup(s);assert.equal(ctx.uiCompletedComputations().length,0);assert.ok(ctx.uiComputationSummary().includes('작업 연결 미확인'));});
test('non-row numerical result arrays and explicit unit-bearing field names are retained',()=>{const {ctx}=setup(stateFor());const rows=ctx.uiComputationValues({guides:[{energy_hartree:-1.25}]});assert.equal(rows[0].value,-1.25);assert.equal(rows[0].unit,'Hartree · 필드명');});

test('display precision preserves raw scientific values, units and very small numbers',async()=>{const {ctx}=setup(stateFor());assert.equal(ctx.uiComputationDisplayValue(5.030900000000003),'5.0309');assert.equal(ctx.uiComputationDisplayValue(1.23456789e-12),'1.23457e-12');assert.equal(ctx.uiComputationDisplayValue(0),'0');assert.equal(ctx.uiComputationDisplayValue(-0),'-0');const a={id:'synthetic_float',kind:'rdkit',sha256:'a',meta:{}};const r={rows:[{properties:{MolWt:392.49900000000014}}],units:{MolWt:'g/mol'}};const x=setup({...stateFor([]),artifacts:[a]},async()=>({artifact_id:a.id,kind:a.kind,result:r}));await x.ctx.uiLoadComputationResult(a.id);const h=x.ctx.uiComputationResultView(a);assert.ok(h.includes('data-raw-value="392.49900000000014"'));assert.ok(h.includes('원값 392.49900000000014'));assert.ok(h.includes('<td>392.499</td>'));assert.ok(h.includes('g/mol'));assert.ok(h.includes('유효숫자 6자리'));});
