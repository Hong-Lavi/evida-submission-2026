// Read-only capture of persisted live outputs; no command/job submission.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';

const out=path.resolve('docs/verification'), base='http://127.0.0.1:8765';
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
const page=await browser.newPage({viewport:{width:1440,height:1040}}), errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
const results=[];
try {
 await page.goto(base,{waitUntil:'networkidle'});
 for(const [name,id] of [['cache','ws_47b70c930f0c42b8'],['rna','ws_0ea93e93b1e5469d']]) {
  await page.evaluate(id=>localStorage.setItem('evida-project',id),id);
  await page.reload({waitUntil:'networkidle'});
  const s=await (await page.request.get(`${base}/api/workspaces/${id}`)).json();
  assert.ok(s.decision?.research_loop);
  assert.ok(!s.jobs.some(j=>['running','queued'].includes(j.status)));
  await page.evaluate(()=>scrollTo(0,0));
  await page.screenshot({path:path.join(out,`downstream-${name}-desktop.png`),fullPage:true});
  results.push({case:name,workspace:id,decision_id:s.decision_id,hypotheses:s.decision.research_loop.hypotheses.length,
    checks:s.decision.research_loop.next_checks.length,active_jobs:0});
  if(name==='rna') {
   assert.equal(s.decision.research_loop.hypotheses.find(h=>h.id==='H7').assessment,'inconclusive');
   const h2=page.locator('.hypothesis').nth(1);
   await h2.locator(':scope > summary').click();
   await h2.locator('details.outcome-details > summary').click();
   await h2.scrollIntoViewIfNeeded();
   await page.screenshot({path:path.join(out,'downstream-rna-hypothesis.png')});
   await h2.locator('[data-action="hypothesis-feedback"]').click();
   assert.equal(await page.locator('#feedback-text').count(),1);
   await page.evaluate(()=>document.querySelector('dialog[open]').close());
   await page.reload({waitUntil:'networkidle'});
   await page.setViewportSize({width:390,height:844});
   await page.evaluate(()=>scrollTo(0,0));
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:path.join(out,'downstream-rna-mobile.png'),fullPage:true});
  }
 }
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(out,'downstream-live-browser.json'),JSON.stringify({mode:'read_only_persisted_live_results',results,errors},null,2)+'\n');
 console.log(JSON.stringify({passed:true,results,errors}));
} finally {await browser.close()}
