/* Read-only acceptance of the hooked evidence workbench on saved local cases. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const repo=path.resolve(here,'../../../../..');
const require=createRequire(path.join(repo,'audit/evida-research-quality-20260924-63/product/package.json'));
const {chromium}=require('playwright-core');
const cases=JSON.parse(await fs.readFile(path.join(here,'fixtures/evidence_workbench_saved_cases.json'),'utf8'));
const base='http://127.0.0.1:8917';
const report={kind:'saved_case_read_only_evidence_workbench',cases:[]};
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
try{
 for(const [name,saved] of Object.entries(cases))for(const width of [1440,390,320]){
  const context=await browser.newContext({viewport:{width,height:900}});
  const page=await context.newPage(),writes=[],errors=[];
  page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(`${r.method()} ${r.url()}`)});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>route.request().url().startsWith(base)||route.request().url().startsWith('data:')?route.continue():route.abort());
  await page.goto(`${base}/?workspace=${saved.id}`,{waitUntil:'networkidle'});
  await page.waitForFunction(id=>typeof state!=='undefined'&&state?.id===id,saved.id);
  await page.locator('.ui-stage[data-stage="evidence"]').click();
  await page.locator('.evidence-workbench').waitFor();
  const claims=(saved.decision?.research_loop?.hypotheses??[]).flatMap(h=>[h,...(h.assessment_scope?.parts??[]),...(h.conditional_alternatives??[])]);
  const evidence=claims.flatMap(c=>c.evidence??[]);
  const actual={case:name,width,claims:await page.locator('.ew-claim').count(),rows:await page.locator('.ew-row').count(),
    overflow:await page.evaluate(()=>Math.max(0,document.documentElement.scrollWidth-innerWidth)),writes,errors};
  assert.equal(actual.claims,claims.length);
  assert.equal(actual.rows,evidence.length);
  await page.evaluate(()=>document.querySelectorAll('.ew-claim').forEach(node=>node.open=true));
  for(const row of evidence)assert.ok((await page.locator('.evidence-workbench').innerText()).includes(row.applicability));
  assert.equal(actual.overflow,0);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
  if(['pde4b','preeclampsia'].includes(name)){
   const image=path.join(here,'fixtures',`evidence_workbench_${name}_${width}.png`);
   await page.screenshot({path:image});actual.screenshot=path.basename(image);
  }
  const source=page.locator('.ew-row [data-action="source"]').first();
  if(await source.count()){
   await source.click();await page.locator('#research-reader').waitFor();
   actual.sourceReader=await page.locator('#research-reader').isVisible();
   assert.equal(actual.sourceReader,true);
  }
  report.cases.push(actual);await context.close();
 }
}finally{await browser.close()}
const output=path.join(here,'fixtures/evidence_workbench_browser.json');
await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');console.log(output);
