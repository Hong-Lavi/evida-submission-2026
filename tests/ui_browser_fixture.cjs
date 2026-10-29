// Load all actual index.source.html scripts in document order. No new scientific/UI renderer stubs.
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const loaded=new WeakMap();
function run(code,ctx,web){
 if(!loaded.has(ctx)){
  const texts=new Set();const initial={...ctx};
  const node={addEventListener(){},removeEventListener(){},querySelector(){return null},querySelectorAll(){return []},classList:{add(){},remove(){},toggle(){}},dataset:{},style:{},innerHTML:'',showModal(){},close(){},contains(){return false}};
  ctx.document=Object.assign({querySelector:()=>node,querySelectorAll:()=>[],getElementById:()=>node,addEventListener(){},removeEventListener(){},createElement:()=>({...node})},ctx.document??{});
  // Existing tests often explicitly returned null for roots. Real app expects these two nodes.
  const query=ctx.document.querySelector;ctx.document.querySelector=s=>s==='#app'||s==='#editor'?node:query(s);
  ctx.window=Object.assign({addEventListener(){},removeEventListener(){},scrollTo(){},location:{href:''}},ctx.window??{});
  ctx.location??={pathname:'/'};ctx.localStorage??={getItem:()=>null,setItem(){},removeItem(){}};
  for(const [k,v]of Object.entries({getItem:()=>null,setItem(){},removeItem(){}}))ctx.localStorage[k]??=v;
  ctx.fetch??=()=>new Promise(()=>{});ctx.setInterval=()=>0;ctx.clearInterval=()=>{};ctx.setTimeout??=()=>0;ctx.clearTimeout??=()=>{};ctx.URL??=URL;ctx.URLSearchParams??=URLSearchParams;ctx.matchMedia??=()=>({matches:false,addEventListener(){}});
  const html=fs.readFileSync(path.join(web,'index.source.html'),'utf8');const scripts=[...html.matchAll(/<script\b[^>]*src="([^"]+)"[^>]*>/g)].map(x=>x[1]);
  for(const file of scripts){const original=fs.readFileSync(path.join(web,file),'utf8');vm.runInContext(original,ctx,{filename:file});texts.add(original);}
  ctx.__fixtureValues=initial;
  if(!('status' in initial))vm.runInContext('status={gateway:{available:false}}',ctx);
  // Restore only authored fixture data and original I/O test doubles, after real state initialization.
  const keys=['state','status','projects','busy','mechanismRanking','mechanismRankingFor','candidateOptions','candidateDisplayName','researcherWording','getOption','openResearchPanel','mechanismFigures','mechanismRankingKey','roadmapModel','api','notice','render'];
  for(const key of keys)if(key in initial){vm.runInContext(`${key}=__fixtureValues[${JSON.stringify(key)}]`,ctx);}
  for(const key of ['state','status','projects','busy','tab','mechanismRanking','mechanismRankingFor']){
   // Expose actual browser lexical state to the existing test assertions/setters.
   const exists=vm.runInContext(`typeof ${key}!=='undefined'`,ctx);if(!exists&&!(key in initial))continue;
   Object.defineProperty(ctx,key,{configurable:true,get(){return vm.runInContext(key,ctx)},set(value){ctx.__assignFixture=value;vm.runInContext(`${key}=__assignFixture`,ctx);delete ctx.__assignFixture;}});
  }
  loaded.set(ctx,texts);
 }
 // Skip only exact text of an already-loaded actual module. Never ignore test snippets.
 if(loaded.get(ctx).has(code))return;
 return vm.runInContext(code,ctx);
}
module.exports={run};
