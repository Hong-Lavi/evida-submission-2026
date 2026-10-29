const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

// Execute the real reader and its declared state, with manually deferred HTTP replies.
// No browser, network, copied implementation or timing-dependent sleeps are needed.
function reader(){
  const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
  const header=source.slice(0,source.indexOf('const labels ='));
  const body=source.slice(source.indexOf('async function readDetail('),source.indexOf('async function saveMessage('));
  assert.ok(body.includes('async function readDetail('),'native reader function exists');
  const requests=[];
  const context={document:{querySelector:()=>null},renders:0,
    candidateSpaceQuery:()=>'',rnaContextQuery:()=>'',articleReferenceQuery:()=>'',
    api:url=>new Promise((resolve,reject)=>requests.push({url,resolve,reject}))};
  context.render=()=>context.renders++;
  vm.createContext(context);vm.runInContext(header+'\n'+body,context);
  const set=code=>vm.runInContext(code,context);
  const get=()=>JSON.parse(set('JSON.stringify({state,selected,offset,detail})'));
  set("state={id:'w1',artifacts:[{id:'raw',kind:'source_file'}]};selected='raw';offset=0;detail=null");
  return {read:()=>context.readDetail(),requests,set,get,renders:()=>context.renders};
}

test('a late queued reply cannot overwrite the completed view for the same original',async()=>{
  const r=reader(),first=r.read(),second=r.read();
  r.requests[1].resolve({artifact_id:'raw',result:{extraction_job:{status:'succeeded'},source_document_artifact_ids:['text']}});
  await second;
  r.requests[0].resolve({artifact_id:'raw',result:{extraction_job:{status:'queued'},source_document_artifact_ids:[]}});
  await first;
  assert.equal(r.get().detail.result.extraction_job.status,'succeeded');
  assert.deepEqual(r.get().detail.result.source_document_artifact_ids,['text']);
  assert.equal(r.renders(),1);
});

test('a reply from a departed workspace cannot populate the current workspace',async()=>{
  const r=reader(),pending=r.read();
  r.set("state={id:'w2',artifacts:[{id:'raw',kind:'source_file'}]};detail=null");
  r.requests[0].resolve({artifact_id:'raw',result:{text:'old workspace'}});await pending;
  assert.equal(r.get().state.id,'w2');assert.equal(r.get().detail,null);assert.equal(r.renders(),0);
});

test('a previous page reply cannot replace the selected offset or later page text',async()=>{
  const r=reader(),pending=r.read();
  r.set('offset=30');
  r.requests[0].resolve({artifact_id:'raw',result:{offset:0,rows:[{text:'earlier page'}]}});await pending;
  assert.equal(r.get().detail,null);
  const current=r.read();assert.match(r.requests[1].url,/offset=30/);
  r.requests[1].resolve({artifact_id:'raw',result:{offset:30,rows:[{text:'later counterevidence'}]}});await current;
  assert.equal(r.get().detail.result.offset,30);
  assert.equal(r.get().detail.result.rows[0].text,'later counterevidence');assert.equal(r.renders(),1);
});

test('errors from superseded reads are quiet, while a current read error remains visible',async()=>{
  const r=reader(),obsolete=r.read(),current=r.read();
  r.requests[1].resolve({artifact_id:'raw',result:{extraction_job:{status:'succeeded'}}});await current;
  r.requests[0].reject(new Error('stale read failure'));await assert.doesNotReject(obsolete);
  assert.equal(r.get().detail.result.extraction_job.status,'succeeded');
  const fresh=r.read();r.requests[2].reject(new Error('current read failure'));
  await assert.rejects(fresh,/current read failure/);
});
