const reviewHarness=require('./ui_browser_fixture.cjs');
function reviewRun(code,ctx){return reviewHarness.run(code,ctx,require('node:path').join(__dirname,'../web'));}
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');

function fixture(){return {id:'workspace',jobs:[],artifacts:[],events:[{
  seq:195,kind:'observation',created:'2026-09-30T17:39:42Z',
  body:{message_id:'original-observation',origin:'researcher_report',synthetic:false,
    text:'sFlt-1 42%; 11.5일 대 12.1일; 95% CI −3.2~2.0'},
  effective_provenance:{origin:'synthetic',synthetic:true,original_origin:'researcher_report',
    empirical_status:'not_empirical_observation',corrected_by:{message_id:'classification-correction',
      event_seq:203,reason:'연구자가 분류를 정정함',researcher_reply:'가상 시연 입력이다'}}
},{seq:203,kind:'correction',created:'2026-10-01T19:00:00Z',
  body:{message_id:'classification-correction',origin:'researcher_report',synthetic:false,
    text:'원 관측의 출처 정정',provenance_correction:{target_message_id:'original-observation',corrected_synthetic:true}},
  effective_provenance:{origin:'researcher_report',synthetic:false,corrected_by:null}
}]};}

function load(){
  const node={addEventListener(){},classList:{add(){},remove(){}},querySelectorAll(){return []}};
  const context=vm.createContext({fixture:fixture(),SCIENCE_LABELS:{},
    document:{querySelector(){return node},addEventListener(){}},
    fetch:()=>new Promise(()=>{}),setTimeout,clearTimeout,URL,URLSearchParams,location:{pathname:'/'},localStorage:{},workspaceAction:async()=>false});
  const root=path.join(__dirname,'../web');
  const helper=path.join(root,'input-provenance.js');
  if(fs.existsSync(helper))reviewRun(fs.readFileSync(helper,'utf8'),context);
  for(const file of ['deployment.js','roadmap.js','app.js'])reviewRun(fs.readFileSync(path.join(root,file),'utf8'),context);
  reviewRun('state=fixture',context);
  return context;
}

test('Actual research view counts corrected synthetic observation, not its factual correction',()=>{
  const c=load();
  for(const name of ['providerNotice','renderContextChanges','renderRoadmap','roadmapObservationAnswer','roadmapRunLine','renderRoadmapComposer'])c[name]=()=>'';
  c.roadmapModel=()=>({});c.roadmapSummary=text=>text;
  const html=c.renderRoadmapResearch();
  assert.match(html,/가상 목표·입력 1건 포함/);
  assert.match(html,/data-id="original-observation"/);
  assert.doesNotMatch(html,/data-id="classification-correction"/);
  assert.equal(c.fixture.events[0].body.synthetic,false,'Rendering leaves original body unchanged');
});

test('Actual history view labels the effective provenance while preserving raw classification',()=>{
  const c=load(),html=c.historyPanel();
  assert.match(html,/가상 입력 · 출처 정정됨/);
  assert.match(html,/가상 시연 입력이다/);
  assert.match(html,/researcher_report/,'Stored original classification remains inspectable');
  assert.match(html,/42%/);
});

test('Source modal discloses the correction and never injects its markup',async()=>{
  const c=load();let shown='';
  c.fixture.events[0].effective_provenance.corrected_by.researcher_reply='<img src=x onerror=alert(1)> 가상 시연 입력이다';
  c.showDialog=(_title,html)=>{shown=html};
  c.roadmapAction=async()=>false;c.teamAction=async()=>false;c.scienceAction=async()=>false;
  c.discoveryAction=async()=>false;c.interactionAction=async()=>false;
  await c.act('message-source',{dataset:{id:'original-observation'}});
  assert.match(shown,/가상 입력 · 출처 정정됨/);
  assert.match(shown,/실제 측정/);
  assert.match(shown,/&lt;img/);assert.doesNotMatch(shown,/<img/);
  assert.match(shown,/data-id="classification-correction"/);
});
