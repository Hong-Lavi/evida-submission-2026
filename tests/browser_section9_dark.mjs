import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const root=process.cwd();
const {chromium}=createRequire(path.join(root,'audit/evida-research-quality-20260924-63/product/package.json'))('playwright-core');
const base=process.env.EVIDA_UI_BASE??'http://127.0.0.1:8919/preview';
const out=path.join(root,'audit/evida-final-ui-20261002/section9-01/browser-dark-repair-01');
await fs.mkdir(out,{recursive:true});
const report={errors:[],non_get:[],non2xx:[],checks:[]};
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
try {
 const context=await browser.newContext({viewport:{width:1440,height:1000},colorScheme:'dark'});
 const page=await context.newPage();page.setDefaultTimeout(15000);
 page.on('pageerror',e=>report.errors.push(e.message));
 page.on('response',r=>{if(r.status()>=400)report.non2xx.push({url:r.url(),status:r.status()})});
 await page.route('**/*',r=>{if(r.request().method()!=='GET'){report.non_get.push(r.request().url());return r.abort()}return r.request().url().startsWith(base)||r.request().url().startsWith('data:')?r.continue():r.abort()});
 await page.goto(base+'/?workspace=ws_1ff05aa2d7c24e0e',{waitUntil:'networkidle'});
 await page.waitForFunction(()=>typeof state!=='undefined'&&state?.id==='ws_1ff05aa2d7c24e0e');
 await page.waitForFunction(()=>candidateStructuresFor===candidateStructuresKey()&&mechanismRankingFor===mechanismRankingKey());
 const before=await page.evaluate(()=>JSON.stringify({decision:state.decision,rev:state.rev,artifacts:state.artifacts.map(a=>[a.id,a.sha256])}));
 await page.locator('.ui-stage-nav [data-stage="mechanisms"]').click();
 report.path=await page.locator('.research-path').evaluate(el=>getComputedStyle(el).color);
 report.field=await page.locator('.path-field').first().evaluate(el=>getComputedStyle(el).color);
 assert.equal(report.path,'rgb(240, 242, 246)');assert.equal(report.field,'rgb(177, 183, 197)');
 await page.screenshot({path:path.join(out,'pde4b-dark-mechanisms.png'),fullPage:true});
 await page.locator('.ui-stage-nav [data-stage="candidates"]').click();
 report.molecule=await page.locator('.ui-candidate-picture').first().evaluate(el=>getComputedStyle(el).backgroundColor);
 assert.equal(report.molecule,'rgb(255, 255, 255)');
 await page.screenshot({path:path.join(out,'pde4b-dark-candidates.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>JSON.stringify({decision:state.decision,rev:state.rev,artifacts:state.artifacts.map(a=>[a.id,a.sha256])})),before);
 assert.deepEqual(report.errors,[]);assert.deepEqual(report.non_get,[]);assert.deepEqual(report.non2xx,[]);
 report.checks=['dark path/field computed contrast tokens','white native molecule surface','saved decision/revision/artifact records unchanged'];report.status='passed';
} catch(e){report.status='failed';report.error=e.stack;process.exitCode=1}
finally {await browser.close();await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report))}
