// Pure VM tests over actual candidate functions; no browser/server/model/network.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const p=require('path').resolve(__dirname,'../web')+'/';
const app=fs.readFileSync(p+'app.js','utf8'),onboarding=fs.readFileSync(p+'onboarding.js','utf8');
const chunk=app.slice(app.indexOf('let gatewayStatusPending='),app.indexOf('function checkGatewayWhenVisible'));
let calls=[],waiters=[];
const c=vm.createContext({console,AbortSignal,fetch:async(url)=>{calls.push(url);return new Promise(resolve=>waiters.push(resolve))},deploymentURL:x=>x,render:()=>{},state:{id:'six'},status:{gateway:{available:true,requests_remaining:0}},busy:false});
vm.runInContext(chunk+'\nthis.refresh=refreshGatewayStatus;this.display=gatewayDisplayState',c);
const ok=(left)=>({ok:true,json:async()=>({gateway:{available:true,maximum_requests:60,requests_remaining:left},planner_execution:{mode:'goal_completion',response_limit:null}})});
(async()=>{
 let a=c.refresh();assert.equal(calls[0],'/api/workspaces/six/execution-status');waiters.shift()(ok(60));await a;assert.equal(c.status.gateway.requests_remaining,60);
 let old=c.refresh();c.state={id:'new'};let fresh=c.refresh();waiters.shift()(ok(59));await old;
 await Promise.resolve();await Promise.resolve();assert.equal(calls.at(-1),'/api/workspaces/new/execution-status');waiters.shift()(ok(25));await fresh;assert.equal(c.status.gateway.requests_remaining,25);
 // A late prior-store failure must not disable the selected store.
 old=c.refresh();c.state=null;fresh=c.refresh();waiters.shift()({ok:false,json:async()=>({})});await old;await Promise.resolve();await Promise.resolve();assert.equal(calls.at(-1),'/api/status');waiters.shift()(ok(24));await fresh;assert.equal(c.status.gateway.requests_remaining,24);
 assert.notEqual(c.display({gateway:{available:true,requests_remaining:1}}),c.display({gateway:{available:true,requests_remaining:0}}));
 const funcs=onboarding.slice(onboarding.indexOf('function resourceAllowanceText'),onboarding.indexOf('function subscriptionCaution'));
 vm.runInContext(funcs+';this.allowance=resourceAllowanceText;this.competition=competitionStateText',c);
 c.status.planner_execution={mode:'finite',response_limit:16,maximum_responses_including_corrections:18};
 assert.match(c.competition({maximum_requests:60,requests_remaining:25}),/25 \/ 60회 남음/);
 assert.match(c.competition({maximum_requests:60,requests_remaining:25}),/최대 18회/);
 c.status.planner_execution={mode:'goal_completion',response_limit:null};assert.match(c.competition({competition_quota:{},maximum_requests:60,requests_remaining:25}),/HTTP 403/);assert.match(c.competition({maximum_requests:60,requests_remaining:25}),/목표 완료까지 계획 계속/);
 assert.match(c.allowance({maximum_requests:60,requests_remaining:59},true),/모든 저장소가 공유/);
 assert.equal(c.allowance({maximum_requests:null,requests_remaining:null}),'');
 // The actual dialog continues to require the existing explicit subscription confirmation.
 assert.match(onboarding,/function openSubscriptionCaution/);assert.match(onboarding,/confirm-model/);assert.match(onboarding,/모델은 자동으로 바뀌지 않습니다/);
 console.log(JSON.stringify({assertions:16,status:'PASS',external_requests:0,model_calls:0}));
})().catch(e=>{console.error(e);process.exitCode=1});
