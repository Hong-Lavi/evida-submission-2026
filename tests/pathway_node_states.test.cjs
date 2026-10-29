const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/pathway_node_states_display.json'),'utf8'));
const code=fs.readFileSync(path.join(__dirname,'../web/pathway-node-states.js'),'utf8');
const clone=value=>JSON.parse(JSON.stringify(value));
function setup(){
 const calls=[],notices=[],dialogs=[];
 const ctx={busy:false,state:{id:'workspace-one'},selected:'result-one',actionError:'',
  esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  number:value=>String(value),sourceLinks:ids=>ids.join(','),json:value=>JSON.stringify(value),
  button:(action,label,attributes='')=>`<button data-action="${action}" ${attributes}>${label}</button>`,
  notice:message=>notices.push(message),showDialog:(title,body)=>dialogs.push({title,body}),
  render:()=>{},runTool:async(tool,args)=>calls.push({tool,args}),
  document:{getElementById:()=>({value:'Check the stored explanation'})},
  dialog:{querySelectorAll:()=>[{value:'GSK3B'}],close:()=>{ctx.closed=true}},
  api:async()=>({result:{solver_package_summary:fixture.pathway_source_summary}})};
 vm.createContext(ctx);vm.runInContext(code,ctx);
 return {ctx,calls,notices,dialogs};
}

test('same score and per-TF fit retain the actual alternative and changing latent source',()=>{
 const {ctx}=setup();const html=ctx.pathwayNodeStatesTable(fixture.same_score_same_fit.result);
 assert.match(html,/같은 목적값·같은 입력 부호 적합도의 대안 경로/);
 assert.match(html,/PPP2CA/);assert.match(html,/GSK3B/);assert.match(html,/변화 미사용 \(0\)/);
 assert.match(html,/가상 시작점도 상승 \(\+1\)에서 하강 \(−1\)로 달라졌습니다/);
 assert.match(html,/"final_lower_bound":null/);assert.match(html,/"final_gap":null/);
});

test('equal total with a different TF fit is visibly different from equal explanation fit',()=>{
 const {ctx}=setup();const html=ctx.pathwayNodeStatesTable(fixture.same_score_changed_fit.result);
 assert.match(html,/목적값은 같고, 입력 부호 적합도는 달라진 경로/);
 assert.doesNotMatch(html,/같은 목적값·같은 입력 부호 적합도의 대안 경로/);
 assert.match(html,/입력 부호의 가중 오차<\/td><td>0<\/td><td>0.2/);
 assert.match(html,/변화 미사용 \(0\)/);
});

test('changed virtual-root connections do not invent a change in its unchanged signed state',()=>{
 const {ctx}=setup();const result=clone(fixture.same_score_same_fit.result);
 result.rows[0].graph.artificial_root.state=1;
 const html=ctx.pathwayNodeStatesTable(result);
 assert.match(html,/가상 시작점의 연결도 달라졌습니다/);
 assert.doesNotMatch(html,/가상 시작점도 상승/);
 assert.match(html,/Perturbation → TLX1/);
});

test('a valid witness from a time-limited run remains visible with its termination',()=>{
 const result=clone(fixture.same_score_same_fit.result);
 result.rows[0].status='partial';result.rows[0].solver.termination='solver_time_limit';
 const {ctx}=setup();const html=ctx.pathwayNodeStatesTable(result);
 assert.match(html,/계산 시간 제한/);assert.match(html,/같은 목적값·같은 입력 부호 적합도의 대안 경로/);
 assert.match(html,/PPP2CA/);
});

test('invalid solver output does not become a displayed scientific alternative',()=>{
 const result=clone(fixture.same_score_same_fit.result);
 result.rows[0].validation.valid=false;result.rows[0].reason='Inspect the preserved worker output';
 const {ctx}=setup();const html=ctx.pathwayNodeStatesTable(result);
 assert.match(html,/유효한 대안 해 확인 필요/);assert.match(html,/Inspect the preserved worker output/);
 assert.doesNotMatch(html,/PPP2CA|대안에서 달라진 설명/);
});

test('legacy results keep reading access and do not offer a query without its solver package',()=>{
 const {ctx}=setup();const html=ctx.pathwayQueryEntry({solver_package_summary:fixture.legacy_source_summary});
 assert.doesNotMatch(html,/data-action="science-pathway-node-dialog"/);
 assert.match(html,/원 계산 묶음을 함께 보존/);
 assert.match(ctx.pathwayQueryEntry({solver_package_summary:fixture.pathway_source_summary}),/data-artifact="result-one"/);
});

test('missing node or edge data is unknown, while an empty validated graph can denote zero states',()=>{
 const {ctx}=setup();
 assert.match(ctx.pathwayAlternativeStates({nodes:[{node:'A',state:1}]},{}),/유효한 상태 결과가 필요/);
 assert.match(ctx.pathwayAlternativeEdges({edges:[]},{}),/유효한 연결 결과가 필요/);
 assert.match(ctx.pathwayAlternativeStates({nodes:[{node:'A',state:1}]},{nodes:[]}),/변화 미사용 \(0\)/);
});

test('an explicitly missing state stays unknown and is distinct from an absent sparse row',()=>{
 const {ctx}=setup();
 for(const value of [null,undefined]){
  const html=ctx.pathwayAlternativeStates({nodes:[{node:'A',state:value}]},{nodes:[{node:'A',state:1}]});
  assert.match(html,/<td>A<\/td><td>계산 상태 확인 필요<\/td><td>상승/);
  const both=ctx.pathwayAlternativeStates({nodes:[{node:'A',state:value}]},{nodes:[{node:'A',state:value}]});
  assert.match(both,/계산 상태 확인 필요/);assert.doesNotMatch(both,/변화 상태가 같습니다/);
 }
});

test('unknown comparison flags do not become changed-fit conclusions',()=>{
 const {ctx}=setup();
 for(const field of ['same_objective','same_observation_fit']){
  for(const value of [null,undefined]){
   const row=clone(fixture.same_score_same_fit.result.rows[0]);row.comparison[field]=value;
   assert.equal(ctx.pathwayQueryConclusion(row),'목적값·입력 부호 적합도 비교 확인 필요');
  }
 }
});

test('names and reasons are escaped in scientific display and source selectors',async()=>{
 const {ctx,dialogs}=setup();const result=clone(fixture.same_score_same_fit.result);
 result.reason='<img src=x onerror=alert(1)>';
 result.rows[0].node_id='<svg onload=alert(1)>';
 const html=ctx.pathwayNodeStatesTable(result);
 assert.doesNotMatch(html,/<img|<svg/);assert.match(html,/&lt;img/);
 const summary=clone(fixture.pathway_source_summary);summary.selectable_nodes[0].node_id='A"><img src=x>';
 ctx.api=async()=>({result:{solver_package_summary:summary}});
 await ctx.pathwayNodeStatesAction('science-pathway-node-dialog',{disabled:false,dataset:{artifact:'source-one'}});
 assert.doesNotMatch(dialogs[0].body,/<img/);
});

test('a pending source read cannot open its dialog after the workspace changes',async()=>{
 const {ctx,dialogs}=setup();let finish;
 ctx.api=()=>new Promise(resolve=>{finish=resolve});
 const operation=ctx.pathwayNodeStatesAction('science-pathway-node-dialog',{disabled:false,dataset:{artifact:'source-one'}});
 ctx.state={id:'workspace-two'};finish({result:{solver_package_summary:fixture.pathway_source_summary}});
 await operation;assert.equal(dialogs.length,0);
});

test('an older source request cannot replace a newer dialog in the same workspace',async()=>{
 const {ctx,dialogs}=setup();const requests=[];
 ctx.api=()=>new Promise(resolve=>requests.push(resolve));
 const first=ctx.pathwayNodeStatesAction('science-pathway-node-dialog',{disabled:false,dataset:{artifact:'A'}});
 const second=ctx.pathwayNodeStatesAction('science-pathway-node-dialog',{disabled:false,dataset:{artifact:'B'}});
 requests[1]({result:{solver_package_summary:fixture.pathway_source_summary}});await second;
 requests[0]({result:{solver_package_summary:fixture.pathway_source_summary}});await first;
 assert.equal(dialogs.length,1);assert.match(dialogs[0].body,/data-artifact="B"/);
});

test('submission retains the exact dialog source and blocks changed workspace or excessive nodes',async()=>{
 const {ctx,calls,notices}=setup();
 const node={disabled:false,dataset:{artifact:'source-original',workspace:'workspace-one'}};
 ctx.selected='a-different-visible-result';
 await ctx.pathwayNodeStatesAction('science-pathway-node-run',node);
 assert.equal(calls.length,1);assert.equal(calls[0].tool,'pathway_node_states');
 assert.equal(calls[0].args.artifact_id,'source-original');assert.deepEqual([...calls[0].args.node_ids],['GSK3B']);
 assert.equal(ctx.closed,true);
 ctx.state={id:'workspace-two'};await ctx.pathwayNodeStatesAction('science-pathway-node-run',node);
 assert.equal(calls.length,1);assert.match(notices.at(-1),/연구가 바뀌었습니다/);
 ctx.state={id:'workspace-one'};ctx.dialog.querySelectorAll=()=>['A','B','C'].map(value=>({value}));
 await ctx.pathwayNodeStatesAction('science-pathway-node-run',node);
 assert.equal(calls.length,1);assert.match(notices.at(-1),/1~2개/);
});
