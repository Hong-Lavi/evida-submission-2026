// Exercises real public downloads and CPU adapters. No model answer is simulated in the UI.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const base = process.env.EVIDA_TEST_BASE ?? 'http://127.0.0.1:8765';
const out = path.resolve('audit/browser-first-integration', new Date().toISOString().replaceAll(':','-'));
await fs.mkdir(out, {recursive:true});
const browser = await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
const page = await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];const checks=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',e=>{if(e.type()==='error')errors.push(e.text())});
page.setDefaultTimeout(20000);
const get = async url => {const r=await page.request.get(base+url);const j=await r.json();assert.equal(r.ok(),true,JSON.stringify(j));return j};
const post = async (url,body) => {const r=await page.request.post(base+url,{data:body,headers:{'X-Evida-Request':'1'}});const j=await r.json();assert.equal(r.ok(),true,JSON.stringify(j));return j};
const snapshot = wid => get('/api/workspaces/'+wid);
async function waitJob(wid,id){
 const deadline=Date.now()+180000;
 while(Date.now()<deadline){const s=await snapshot(wid);const j=s.jobs.find(j=>j.id===id);if(j&&!['queued','running'].includes(j.status))return j;await new Promise(r=>setTimeout(r,500))}
 throw Error('Tool did not complete within browser test observation window; server job is not cancelled.');
}
async function run(wid,tool,args){const s=await snapshot(wid);const started=await post(`/api/workspaces/${wid}/jobs`,{expected_rev:s.rev,tool,arguments:args});return waitJob(wid,started.job_id)}
async function capture(name){await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:path.join(out,name),fullPage:false});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert.equal(overflow,false,'horizontal document overflow')}
try{
 await page.goto(base,{waitUntil:'networkidle'});
 await page.getByRole('heading',{name:/다음 연구 판단을/}).waitFor();
 await capture('01-new-research.png');
 console.log('UI ready; importing actual public CACHE data');
 await page.locator('[data-action="example"][data-id="cache"]').click();
 await page.getByRole('heading',{name:'CACHE · 기존 분자 후보 검토',exact:true,level:1}).waitFor({timeout:180000});
 const cacheId=await page.evaluate(()=>localStorage.getItem('evida-project'));
 let s=await snapshot(cacheId);
 assert.equal(s.artifacts.filter(a=>a.kind==='molecule_csv').length,1,JSON.stringify(s.events));
 const input=s.artifacts.find(a=>a.kind==='molecule_csv');
 await page.locator('[data-action="tab"][data-id="data"]').first().click();
 await page.locator(`[data-action="source"][data-id="${input.id}"]`).first().click();
 await page.getByRole('button',{name:'물성 계산',exact:true}).click();
 let jid;
 for(let i=0;i<30;i++){s=await snapshot(cacheId);jid=s.jobs.find(j=>j.kind==='rdkit')?.id;if(jid)break;await page.waitForTimeout(200)}
 let job=await waitJob(cacheId,jid);assert.equal(job.status,'succeeded',job.error);
 let result=await get(`/api/workspaces/${cacheId}/artifacts/${job.output_id}?limit=100`);
 assert.equal(result.result.total_rows,73);assert.equal(result.result.summary.calculated,73);
 checks.push({name:'real CACHE RDKit through UI',rows:73,workspace:cacheId,job:job.id,status:job.status});
 await page.waitForFunction(id=>!!document.querySelector(`[data-action="source"][data-id="${id}"]`),job.output_id);
 await page.locator(`[data-action="source"][data-id="${job.output_id}"]`).first().click();
 await page.getByRole('button',{name:'ADMET 예측',exact:true}).waitFor();
 await capture('02-real-molecule-properties.png');
 console.log('RDKit 73 rows passed; running pretrained ADMET on CPU');
 await page.getByRole('button',{name:'ADMET 예측',exact:true}).click();
 for(let i=0;i<30;i++){s=await snapshot(cacheId);jid=s.jobs.find(j=>j.kind==='admet')?.id;if(jid)break;await page.waitForTimeout(200)}
 job=await waitJob(cacheId,jid);assert.equal(job.status,'succeeded',job.error);
 result=await get(`/api/workspaces/${cacheId}/artifacts/${job.output_id}?limit=100`);
 assert.equal(result.result.total_rows,73);assert.equal(result.result.summary.endpoints,41);
 checks.push({name:'real ADMET CPU',rows:73,endpoints:41,job:job.id,status:job.status});
 await page.waitForFunction(id=>!!document.querySelector(`[data-action="source"][data-id="${id}"]`),job.output_id);
 await page.locator(`[data-action="source"][data-id="${job.output_id}"]`).first().click();
 await page.getByRole('heading',{name:'ADMET 예측 · ADMET-AI',exact:true}).waitFor();
 await capture('03-real-admet-predictions.png');
 await page.locator('[data-action="tab"][data-id="research"]').click();
 await page.locator('#message').fill('개발 확인용 가상 정정: 원 관측의 단위가 아직 확인되지 않았습니다. 효능 비교 해석은 재검토하고 구조가 같은 물성 계산은 유지해 주세요.');
 await page.locator('#input-kind').selectOption('correction');
 await page.locator('#synthetic').check();
 await page.getByRole('button',{name:'내용 저장',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#message')?.value==='');
 s=await snapshot(cacheId);
 assert.equal(s.events.filter(e=>e.kind==='correction').at(-1).body.origin,'synthetic');
 assert.equal(s.review_status,'needs_review');
 job=await run(cacheId,'rdkit',{artifact_id:input.id});assert.equal(job.status,'reused');
 checks.push({name:'correction kept and unchanged computation reused',job:job.id,status:job.status});
 await page.reload({waitUntil:'networkidle'});
 assert.equal(await page.evaluate(()=>localStorage.getItem('evida-project')),cacheId);
 await page.locator('[data-action="tab"][data-id="history"]').click();
 await capture('04-correction-and-reuse.png');
 await page.setViewportSize({width:390,height:844});
 await capture('05-mobile-history.png');
 await page.setViewportSize({width:1440,height:1000});
 console.log('Correction/reuse/reload passed; importing real RNA tables');
 const rna=await post('/api/examples',{id:'rna'});
 const rnaInputs=rna.artifacts.filter(a=>a.kind==='rna_table');assert.equal(rnaInputs.length,3,JSON.stringify(rna.events));
 for(const a of rnaInputs){job=await run(rna.id,'rna_observations',{artifact_id:a.id});assert.equal(job.status,'succeeded',job.error);const r=await get(`/api/workspaces/${rna.id}/artifacts/${job.output_id}?limit=2`);assert.equal(r.result.total_rows,32883);assert.equal(r.result.rows[0].reference_mapping,'not_run');checks.push({name:'real RNA processed table',file:a.title,rows:r.result.total_rows,missing:r.result.summary.missing_by_column,job:job.id})}
 s=await snapshot(rna.id);await page.evaluate(id=>localStorage.setItem('evida-project',id),rna.id);await page.reload({waitUntil:'networkidle'});
 await page.locator('[data-action="tab"][data-id="data"]').first().click();
 const rnaResult=s.artifacts.find(a=>a.kind==='rna_observations');
 await page.locator(`[data-action="source"][data-id="${rnaResult.id}"]`).first().click();
 await page.getByRole('heading',{name:'RNA 관측 검토',exact:true}).waitFor();
 await capture('06-real-rna-observations.png');
 console.log('RNA tables preserved; checking public target and literature adapters');
 job=await run(rna.id,'open_targets',{target_id:'ENSG00000118271'});assert.equal(job.status,'succeeded',job.error);
 result=await get(`/api/workspaces/${rna.id}/artifacts/${job.output_id}`);assert.equal(result.result.summary.symbol,'TTR');checks.push({name:'Open Targets public query',job:job.id,summary:result.result.summary});
 job=await run(rna.id,'literature',{query:'TTR transthyretin stabilization gene silencing evidence',cursor:'*'});assert.equal(job.status,'succeeded',job.error);
 result=await get(`/api/workspaces/${rna.id}/artifacts/${job.output_id}`);assert.ok(result.result.summary.returned>0);checks.push({name:'Europe PMC public search',job:job.id,summary:result.result.summary});
 const unauthorized=await page.request.post(base+'/api/workspaces',{data:{title:'must not create'},headers:{Origin:'https://unrelated.example'}});assert.equal(unauthorized.status(),400);
 checks.push({name:'cross-origin mutation rejected',status:unauthorized.status()});
 assert.deepEqual(errors,[]);
 checks.push({name:'browser console and page errors',count:errors.length});
 console.log('Browser workflow checks passed. These are execution/integrity checks, not a scientific validation or model-quality result.');
}finally{
 await fs.writeFile(path.join(out,'results.json'),JSON.stringify({checked_at:new Date().toISOString(),checks,errors,model_calls:0,limits:['No live product model call; no scientific efficacy or time-saving validation.']},null,2));
 await browser.close();
}
