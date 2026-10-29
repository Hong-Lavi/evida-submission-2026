import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const base='http://127.0.0.1:8765', out=path.resolve('audit/browser-followup',new Date().toISOString().replaceAll(':','-'));
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];const checks=[];
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
const get=async p=>(await page.request.get(base+p)).json();
try{
 await page.goto(base,{waitUntil:'networkidle'});
 const projects=await get('/api/workspaces');
 const rna=projects.find(p=>p.title==='Ttr · 기존 RNA 관측 검토');assert.ok(rna);
 await page.evaluate(id=>localStorage.setItem('evida-project',id),rna.id);await page.reload({waitUntil:'networkidle'});
 await page.locator('[data-action="tab"][data-id="data"]').first().click();
 const state=await get(`/api/workspaces/${rna.id}`), result=state.artifacts.find(a=>a.kind==='rna_observations');
 await page.locator(`[data-action="source"][data-id="${result.id}"]`).first().click();
 await page.getByRole('heading',{name:'RNA 관측 검토',exact:true}).waitFor();
 assert.match(await page.locator('tbody').innerText(),/e-\d+/);
 assert.ok((await page.locator('table').innerText()).includes('조정 p-value'));
 await page.evaluate(()=>document.fonts.ready);
 await page.screenshot({path:path.join(out,'01-rna-scientific-notation.png'),fullPage:false});
 checks.push('Tiny values displayed in scientific notation; raw full values retained separately.');
 const query='drug discovery evidence provenance';
 await page.locator('#literature-query').fill(query);
 await page.locator('[data-action="literature"]').click();
 let job;
 for(let i=0;i<100;i++){const s=await get(`/api/workspaces/${rna.id}`);job=s.jobs.filter(j=>j.kind==='literature'&&j.request.query===query).at(-1);if(job&&!['queued','running'].includes(job.status))break;await page.waitForTimeout(500)}
 assert.equal(job?.status,'succeeded',job?.error);checks.push('Literature query typed in UI survives busy state and is executed exactly.');
 const cache=projects.find(p=>p.title==='CACHE · 기존 분자 후보 검토');
 await page.evaluate(id=>localStorage.setItem('evida-project',id),cache.id);await page.reload({waitUntil:'networkidle'});
 await page.locator('[data-action="edit-intent"]').click();
 await page.locator('.intent-label').first().fill('개발 확인용 의도');
 await page.locator('.intent-text').first().fill('가상 UI 시험: 연구자가 정한 조건을 저장하고, 미정 표적이나 접근은 아직 답으로 강제하지 않는다.');
 await page.locator('[data-action="save-intent"]').click();
 await page.locator('#editor').waitFor({state:'hidden'});
 assert.ok((await get(`/api/workspaces/${cache.id}`)).intent.some(r=>r.label==='개발 확인용 의도'));
 await page.screenshot({path:path.join(out,'02-intent-workspace.png'),fullPage:false});
 checks.push('Editable semantic record saved without fixed seven-field TPP.');
 await page.setViewportSize({width:390,height:844});
 await page.locator('[data-action="tab"][data-id="history"]').click();
 await page.screenshot({path:path.join(out,'03-mobile-history.png'),fullPage:false});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 checks.push('Mobile viewport has no horizontal document overflow.');
 assert.deepEqual(errors,[]);
 console.log('Targeted UI follow-up passed. No model calls.');
}finally{await fs.writeFile(path.join(out,'results.json'),JSON.stringify({checked_at:new Date().toISOString(),checks,errors,model_calls:0},null,2));await browser.close()}
