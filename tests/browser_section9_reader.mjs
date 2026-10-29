/* Read-only saved-case check for evidence reader return paths and paper figures. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const repo=path.resolve(here,'../../../../..');
const require=createRequire(path.join(repo,'audit/evida-research-quality-20260924-63/product/package.json'));
const {chromium}=require('playwright-core');
const saved=JSON.parse(await fs.readFile(path.join(here,'fixtures/evidence_workbench_saved_cases.json'),'utf8'));
const base=process.env.EVIDA_UI_BASE??'http://127.0.0.1:8918';
const report={kind:'read_only_reader_context_and_paper_figures',cases:[],limits:[
 'Figure counts describe accessible images, captions, and source anchors in the copied UI; they do not validate the paper interpretation.',
 'The source-reader check uses the saved cases and makes no research write or model call.'
]};
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});

async function readerPosition(page){
 return page.locator('#research-reader-body').evaluate(n=>({scroll:n.scrollTop,max:n.scrollHeight-n.clientHeight}));
}
async function workbenchContext(page){
 const defects=[];
 await page.locator('.ui-stage[data-stage="evidence"]').click();
 await page.locator('.evidence-workbench').waitFor();
 const claim=page.locator('.ew-claim').filter({has:page.locator('[data-action="source"]')}).first();
 if(!await claim.count())return {status:'no_artifact_source_action'};
 await claim.locator('summary').click();
 const claimId=await claim.getAttribute('data-claim-id');
 const opener=claim.locator('[data-action="source"]').first(),sourceId=await opener.getAttribute('data-id');
 await opener.scrollIntoViewIfNeeded();
 await page.evaluate(()=>window.scrollBy(0,120));
 const beforeScroll=await page.evaluate(()=>window.scrollY);
 await opener.click();
 await page.locator('#research-reader').waitFor();
 await page.waitForFunction(()=>!!document.querySelector('.reader-original-result'));
 await page.locator('#research-reader-body').evaluate(n=>{n.scrollTop=Math.min(180,n.scrollHeight-n.clientHeight)});
 const openedScroll=await readerPosition(page);
 await page.locator('#research-reader [data-action="ui-reader-close"]').click();
 await page.locator('#research-reader').waitFor({state:'detached'});
 await page.waitForTimeout(80); // restoration is scheduled in requestAnimationFrame
 const afterClose=await page.evaluate(({claimId,sourceId})=>{
   const claim=[...document.querySelectorAll('.ew-claim')].find(n=>n.dataset.claimId===claimId);
   return {claimOpen:!!claim?.open,focusedTag:document.activeElement?.tagName,focusedElementId:document.activeElement?.id,
     focusedAction:document.activeElement?.dataset.action,focusedId:document.activeElement?.dataset.id,scrollY:window.scrollY};
 },{claimId,sourceId});
 if(!afterClose.claimOpen)defects.push('claim_collapsed_after_close');
 if(afterClose.focusedAction!=='source'||afterClose.focusedId!==sourceId)defects.push('focus_not_exact_opener_after_close');
 if(Math.abs(afterClose.scrollY-beforeScroll)>=80)defects.push('page_scroll_changed_after_close');
 const reopen=page.locator(`.ew-claim[data-claim-id="${claimId}"] [data-action="source"][data-id="${sourceId}"]`).first();
 await reopen.click();await page.locator('#research-reader').waitFor();
 await page.waitForFunction(()=>!!document.querySelector('.reader-original-result'));
 await page.locator('#research-reader-body').evaluate(n=>{n.scrollTop=Math.min(220,n.scrollHeight-n.clientHeight)});
 const historyScroll=await readerPosition(page);
 await page.evaluate(()=>history.back());
 await page.locator('#research-reader').waitFor({state:'detached'});
 await page.waitForTimeout(80);
 const afterBack=await page.evaluate(({claimId,sourceId})=>{
   const claim=[...document.querySelectorAll('.ew-claim')].find(n=>n.dataset.claimId===claimId);
   return {claimOpen:!!claim?.open,focusAction:document.activeElement?.dataset.action,
     focusId:document.activeElement?.dataset.id,scrollY:window.scrollY};
 },{claimId,sourceId});
 if(!afterBack.claimOpen)defects.push('claim_collapsed_after_history_back');
 if(afterBack.focusAction!=='source'||afterBack.focusId!==sourceId)defects.push('focus_not_exact_opener_after_history_back');
 await page.evaluate(()=>history.forward());
 await page.locator('#research-reader').waitFor();
 await page.waitForFunction(()=>!!document.querySelector('.reader-original-result'));
 const afterForward=await readerPosition(page);
 if(Math.abs(afterForward.scroll-historyScroll.scroll)>3)defects.push('source_scroll_not_restored_on_history_forward');
 await page.locator('#research-reader [data-action="ui-reader-close"]').click();
 return {status:defects.length?'defects':'passed',defects,claimId,sourceId,beforeScroll,openedScroll,afterClose,historyScroll,afterBack,afterForward};
}
async function figureCounts(page,artifact){
 await page.evaluate(id=>uiOpenSource(id),artifact.id);
 await page.locator('#research-reader').waitFor();
 await page.waitForFunction(()=>!!document.querySelector('.reader-original-result'));
 await page.locator('.article-figures').first().waitFor({state:'visible',timeout:5000}).catch(()=>{});
 const images=page.locator('#research-reader img.article-figure-image');
 for(let i=0;i<await images.count();i++){
  await images.nth(i).scrollIntoViewIfNeeded();
  await images.nth(i).evaluate(n=>n.decode().catch(()=>{}));
 }
 const data=await page.locator('#research-reader').evaluate(reader=>{
  const figures=[...reader.querySelectorAll('.article-figure')];
  return {figures:figures.length,cachedImages:figures.filter(f=>!!f.querySelector('img.article-figure-image')).length,
   loadedImages:figures.filter(f=>{const n=f.querySelector('img.article-figure-image');return !!n&&n.complete&&n.naturalWidth>0}).length,
   namedImages:figures.filter(f=>!!f.querySelector('img.article-figure-image[alt]')?.alt.trim()).length,
   captions:figures.filter(f=>!!f.querySelector('figcaption')?.textContent.trim()).length,
   sourceAnchors:figures.filter(f=>!!f.querySelector('figcaption a.source-link[href]')).length,
   missingImageNotices:figures.filter(f=>!!f.querySelector('p')?.textContent.includes('그림 파일은 아직 회수되지')).length};
 });
 await page.locator('#research-reader [data-action="ui-reader-close"]').click();
 await page.locator('#research-reader').waitFor({state:'detached'});
 return {artifactId:artifact.id,...data};
}
try{
 for(const [name,entry] of Object.entries(saved)){
  const context=await browser.newContext({viewport:{width:1440,height:900}});
  const page=await context.newPage(),writes=[],errors=[];
  page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(`${r.method()} ${r.url()}`)});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>route.request().method()==='GET'&&(route.request().url().startsWith(base)||route.request().url().startsWith('data:'))?route.continue():route.abort());
  await page.goto(`${base}/?workspace=${entry.id}`,{waitUntil:'networkidle'});
  await page.waitForFunction(id=>typeof state!=='undefined'&&state?.id===id,entry.id);
  const result={case:name,context:await workbenchContext(page),figures:[]};
  for(const artifact of entry.artifacts.filter(a=>a.kind==='article'))result.figures.push(await figureCounts(page,artifact));
  result.writes=writes;result.errors=errors;
  assert.deepEqual(result.context.defects,[],`${name}: reader context defects`);
  assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
  report.cases.push(result);await context.close();
 }
}finally{await browser.close()}
const output=path.join(here,'fixtures',new URL(base).pathname.startsWith('/preview')?'section9_reader_context_figures_prefix.json':'section9_reader_context_figures.json');
await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');console.log(output);
