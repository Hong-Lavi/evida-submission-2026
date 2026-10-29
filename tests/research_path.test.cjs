const reviewHarness=require('./ui_browser_fixture.cjs');
function reviewRun(code,ctx){return reviewHarness.run(code,ctx,require('node:path').join(__dirname,'../web'));}
// Synthetic boundary cases for the UI projection, not model or biological outcomes.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const code=fs.readFileSync(path.join(__dirname,'../web/research-path.js'),'utf8');
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const assessment=(overrides={})=>({status:'needs_evidence',based_rev:4,current_conditions:true,
  support_source_ids:['article:trial'],challenge_source_ids:[],priority:null,comparison_group:'',
  reason:'조건을 확인할 경로',next_action:'같은 조건에서 기능 비교',basis:null,applicability:{current:overrides.current_conditions!==false},...overrides});
const mechanism=(id,overrides={})=>({option_id:id,kind:'mechanism',label:id.replace('mechanism:',''),
  sources:[],assessment:assessment(),...overrides});
function setup({options=[],candidates=[],ranking=null,intent=[]}={}){
  const opened=[];
  const state={id:'ws:pde',event_cursor:9,rev:4,title:'PDE4B · 표적 연구',intent,
    decision:{recommendation:'서술의 IPF → LPAR1라는 문자열을 인과 관계로 만들지 않는다.'},
    artifacts:[{id:'article:trial',title:'원 시험 논문'}],
    discovery:{mechanisms_and_approaches:options,selected:null},judgment_context:null};
  const context=vm.createContext({state,esc:escape,mechanismRanking:ranking,
    mechanismRankingFor:'ws:pde@9@4',candidateOptions:()=>candidates,
    candidateDisplayName:item=>item.label, researcherWording:s=>s,
    getOption:async id=>options.find(o=>o.option_id===id),
    openResearchPanel:async spec=>opened.push(spec),
    mechanismFigures:row=>`<figure data-original="${escape(row.figures[0].artifact_id)}">원문 그림</figure>`});
  context.artifactName=id=>context.state.artifacts.find(a=>a.id===id)?.title || id;
  context.mechanismRankingKey=()=>`${context.state.id}@${context.state.event_cursor}@${context.state.rev}`;
  reviewRun(code,context);
  return {context,opened};
}

test('Target-first study keeps the stored unknown disease and creates no edge from prose or name overlap',()=>{
  const m=mechanism('mechanism:pde4b');
  const candidate={option_id:'molecule:pde4b-name-overlap',label:'PDE4B 자유 텍스트 후보',kind:'molecule',
    assessment:assessment({reason:'PDE4B와 연결된 것처럼 읽히는 문장',targets_mechanism:null})};
  const {context}=setup({options:[m],candidates:[candidate],intent:[
    {id:'goal',label:'연구 목표',origin:'researcher',text:'PDE4B 기능과 PDE4D 선택성을 검토한다.'},
    {id:'unknown',label:'적용 조건',origin:'unknown',text:'적용 질환과 임상 평가변수는 미확인이다.'}]});
  const html=context.renderResearchPath();
  assert.match(html,/적용 질환과 임상 평가변수는 미확인/);
  assert.doesNotMatch(html,/IPF|LPAR1|PDE4B 자유 텍스트 후보/);
  assert.equal(context.pathLinkedCandidates(m.option_id).length,0);
});

test('Repeated local proposed-1 IDs link only through distinct complete typed option IDs',()=>{
  const a=mechanism('mechanism:a'),b=mechanism('mechanism:b');
  const candidates=['a','b'].map(name=>({option_id:`molecule:generated:art-${name}:proposed-1`,
    label:'설계 후보 1',entity_id:'proposed-1',kind:'molecule',origin:'generated_structure_proposal',
    assessment:assessment({targets_mechanism:{option_id:`mechanism:${name}`,reason:`${name}에 연결한 원 기록`}})}));
  const {context}=setup({options:[a,b],candidates});
  const before=JSON.stringify({state:context.state,candidates});
  const html=context.renderResearchPath();
  assert.equal(context.pathLinkedCandidates(a.option_id)[0].option_id,candidates[0].option_id);
  assert.equal(context.pathLinkedCandidates(b.option_id)[0].option_id,candidates[1].option_id);
  assert.match(html,/data-id="molecule:generated:art-a:proposed-1"/);
  assert.match(html,/data-id="molecule:generated:art-b:proposed-1"/);
  assert.match(html,/계산으로 제안한 구조 · 생성 단계 활성 미측정/);
  assert.equal(JSON.stringify({state:context.state,candidates}),before,'projection does not modify records');
});

test('Current recommendation, evidence comparison and previous-input record remain separate',()=>{
  const a=mechanism('mechanism:a',{assessment:assessment({status:'recommended'})});
  const b=mechanism('mechanism:b',{assessment:assessment({status:'recommended',based_rev:2,current_conditions:false})});
  const rows=[a,b].map(o=>({...o,...o.assessment,comparable:true}));
  const {context}=setup({options:[a,b],ranking:{status:'computed',rows,frontier:[a.option_id,b.option_id],
    single_leader:null,comparison_axes:['disease_match','evidence_grade']}});
  const html=context.renderResearchPath();
  assert.match(html,/이번에 검토할 경로/);
  assert.match(html,/앞선 기전·접근 2개 · 서로 순서 미정/);
  assert.match(html,/기준: 적용성·타당성 · 평가 연구 기록 4, 2/);
  assert.match(html,/이전 조건·검토 전 경로 1개/);
  assert.match(html,/연구 기록 2 · 근거·조건 재검토 필요/);
  assert.doesNotMatch(html,/최상위 후보|효능 1위|확률 점수/);
});

test('Zero comparable mechanisms explains missing comparison conditions while retaining a candidate',()=>{
  const m=mechanism('mechanism:pde4b');
  const c={option_id:'molecule:generated:art-x:proposed-2',label:'설계 후보 2',origin:'generated_structure_proposal',
    assessment:assessment({targets_mechanism:{option_id:m.option_id,reason:'효소 기능을 비교할 구조'}})};
  const {context}=setup({options:[m],candidates:[c],ranking:{status:'computed',rows:[{...m,...m.assessment,
    comparable:false,hold_reasons:['support_not_confirmed']}],frontier:[],single_leader:null,
    comparison_axes:['disease_match','evidence_grade']}});
  const html=context.renderResearchPath();
  assert.match(html,/기전 간 비교 조건 확인 중/);
  assert.match(html,/비교 조건을 갖춘 항목 0개/);
  assert.match(html,/설계 후보 2/);
  assert.doesNotMatch(html,/최상위 후보 0개|효능.*1위/);
});

test('Relation panel keeps original quotation apart from interpretation and preserves source role and row index',()=>{
  const m=mechanism('mechanism:a',{assessment:assessment({challenge_source_ids:['missing:id'],
    basis:{hypothesis_id:'H1',clauses:[{text:'모델의 연결 해석',disease_match:'animal_model',
      context:{disease:'모형 질환',species:'mouse',tissue:'lung'},
      anchor:{artifact_id:'article:trial',quote:'Literal <tag> & "quote"',row_index:7}}]}})});
  const {context}=setup({options:[m]});
  const html=context.pathEvidenceBody(m,null);
  assert.match(html,/모델의 연결 해석/);
  assert.match(html,/<blockquote>Literal &lt;tag&gt; &amp; &quot;quote&quot;<\/blockquote>/);
  assert.match(html,/모형 질환 · mouse · lung/);
  assert.match(html,/저장 원행 인덱스 7 · 0부터 셈/);
  assert.match(html,/지지 근거로 연결한 자료/);
  assert.match(html,/반대 근거로 연결한 자료/);
  assert.match(html,/data-id="article:trial"[^>]*>원 시험 논문/);
  assert.match(html,/data-id="article:trial" data-source-offset="7" data-source-quote="Literal &lt;tag&gt; &amp; &quot;quote&quot;"/);
  assert.doesNotMatch(html,/data-id="missing:id"/);
});

test('Source locators keep zero-based row zero and never derive a row from invalid or absent input',()=>{
  const {context}=setup();
  const first=context.pathSourceLinks(['article:trial'],{artifact_id:'article:trial',row_index:0,quote:'line zero'});
  assert.match(first,/data-source-offset="0" data-source-quote="line zero"/);
  for(const row of [undefined,null,-1,'7',0.5]){
    const html=context.pathSourceLinks(['article:trial'],{artifact_id:'article:trial',row_index:row,quote:'text'});
    assert.doesNotMatch(html,/data-source-offset|data-source-quote/);
  }
  const unrelated=context.pathSourceLinks(['article:trial'],{artifact_id:'other:article',row_index:3,quote:'other'});
  assert.doesNotMatch(unrelated,/data-source-offset|data-source-quote/);
});

test('Evaluation observations join only on the explicit hypothesis ID, retaining prior-context version',()=>{
  const m=mechanism('mechanism:a',{assessment:assessment({basis:{hypothesis_id:'H1',clauses:[]}})});
  const {context}=setup({options:[m]});
  context.state.judgment_context={context_revision:2,is_current_input:false,context:{
    contexts:[{id:'c1',organism:'human',tissue_cell:'stored cell',comparator:'vehicle'}],
    bindings:[{hypothesis_id:'H1',context_id:'c1',prediction:{observable:'LPAR1 calcium',unit:'%'}},
      {hypothesis_id:'H2',context_id:'c1',prediction:{observable:'UNRELATED_OUTCOME',unit:'kg'}}]}};
  const html=context.pathEvidenceBody(m,null);
  assert.match(html,/LPAR1 calcium/);
  assert.match(html,/연구 기록 2 · 이전 조건/);
  assert.doesNotMatch(html,/UNRELATED_OUTCOME/);
  assert.equal(context.pathBoundContexts(null),'');
});

test('Rendering is read-only and drops a ranking cached for another workspace',()=>{
  const {context}=setup({ranking:{status:'computed',rows:[{option_id:'mechanism:foreign',kind:'mechanism',
    label:'FOREIGN_STUDY',figures:[{artifact_id:'foreign-article',file:'foreign.png'}]}],frontier:[]}});
  context.mechanismRankingFor='ws:other@9@4';
  context.getOption=()=>{throw Error('render must not request anything');};
  const html=context.renderResearchPath();
  assert.doesNotMatch(html,/FOREIGN_STUDY|foreign-article|foreign.png/);
  assert.match(html,/기전별 관계와 기록된 추천/);
});

test('Evidence click opens the exact relation in the shared panel without changing study data',async()=>{
  const m=mechanism('mechanism:a');const {context,opened}=setup({options:[m]});
  const before=JSON.stringify(context.state);
  assert.equal(await context.pathAction('path-evidence',{dataset:{id:m.option_id}}),true);
  assert.equal(opened.length,1);
  assert.equal(opened[0].kind,'relation');assert.equal(opened[0].id,m.option_id);
  assert.equal(opened[0].subject.kind,'mechanism');assert.equal(opened[0].subject.id,m.option_id);
  assert.equal(JSON.stringify(context.state),before);
  assert.equal(await context.pathAction('source',{dataset:{id:'article:trial'}}),false);
});

test('A late relation response cannot replace the most recently clicked relation',async()=>{
  const a=mechanism('mechanism:a'),b=mechanism('mechanism:b');
  const {context,opened}=setup({options:[a,b]});const pending={};
  context.getOption=id=>new Promise(resolve=>{pending[id]=resolve;});
  const first=context.pathAction('path-evidence',{dataset:{id:a.option_id}});
  const second=context.pathAction('path-evidence',{dataset:{id:b.option_id}});
  pending[b.option_id](b);await second;pending[a.option_id](a);await first;
  assert.deepEqual(opened.map(p=>p.id),[b.option_id]);
});

test('A new workspace, revision or event cursor invalidates an in-flight relation request',async()=>{
  for(const field of ['id','rev','event_cursor']){
    const a=mechanism('mechanism:a');const {context,opened}=setup({options:[a]});let finish;
    context.getOption=()=>new Promise(resolve=>{finish=resolve;});
    const pending=context.pathAction('path-evidence',{dataset:{id:a.option_id}});
    context.state[field]=field==='id'?'ws:other':context.state[field]+1;
    finish(a);await pending;assert.equal(opened.length,0,field);
  }
});
