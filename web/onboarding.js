// Product guidance and entry points. Guidance is local; scientific results require real jobs.
let intakeMode = 'question', intakeFile = null, intakeContext = '', intakeError = '', actionError = '', submitPhase = '';
let intakeDelimiter = ',', intakeSmiles = 'smiles', intakeId = 'cid';
// null keeps the server's current model. The server rechecks any explicit approved choice.
let chosenModel = null;
function offeredModels(){return [...new Set((status?.gateway?.approved_models??[]).filter(name=>typeof name==='string'&&name))]}
function modelDisplayName(name){return name==='claude-opus-5'?'Claude Opus 5':String(name??'모델 확인 필요')}
function modelEffortLabel(){return status?.gateway?.requested_effort??'설정 확인 필요'}
function modelAccessButton(){
  const g=status?.gateway??{},name=modelDisplayName(g.requested_model),short=name.replace(/^Claude /,'');
  return button('model-help',`${esc(short)} · ${esc(modelEffortLabel())}${g.available?'':' · 확인'}`,`aria-label="모델 이용 안내 · ${esc(name)} · ${esc(modelEffortLabel())}${g.available?' · 연결됨':' · 연결 상태 확인 필요'}" title="모델 이용 안내"`,'quiet small');
}
async function openModelAccessHelp(){
  await refreshGatewayStatus({force:true});
  const g=status.gateway??{},current=modelDisplayName(g.requested_model);
  showDialog('모델 이용 안내',`<dl><dt>현재 연결</dt><dd>${esc(current)} · ${esc(modelEffortLabel())}</dd><dt>연결 상태</dt><dd role="status">${g.available?'사용 가능':esc(g.message??'현재 모델 연결을 확인해야 합니다.')}</dd></dl><p>현재 Claude는 개발자 구독으로 제공 중입니다. 심사·지속 사용은 대회 API 크레딧 확보 후 연결을 권장합니다.</p><p><strong>대회 API · 할당량 소진</strong><br>크레딧 확보와 실제 연결 확인 후 사용할 수 있습니다.</p><details><summary>현재 연결에서 허용된 모델</summary>${list(offeredModels().map(modelDisplayName))||'<p>허용된 모델 확인 필요</p>'}</details>`);
}
function modelChoice(){
  const offered=offeredModels();
  const running=status.gateway?.requested_model,selected=chosenModel??running;
  return `<label class="model-choice">모델
    <select id="intake-model">${offered.map(name=>`<option value="${esc(name)}" ${
      selected===name?'selected':''}>${esc(modelDisplayName(name))}${name===running?' · '+esc(modelEffortLabel()):''}</option>`).join('')}${!offered.includes(selected)?'<option value="" selected disabled>연결 모델 확인 필요</option>':''}<option value="competition-api-unavailable" disabled>대회 API · 할당량 소진</option></select>
  </label>${button('model-help','모델 이용 안내','','quiet small')}`;
}
const ENTRY_PATHS = [
  {id:'molecule',name:'저분자 후보 평가',tag:'이미 후보가 있나요?',input:'후보 ID와 SMILES가 있는 CSV',output:'물성·ADMET, 구조가 있으면 도킹·실험 근거 비교',limit:'물성·ADMET와 알려진 구조 부위의 실제 도킹·포즈 검사를 연결합니다. 측정 활성·선택성 및 세포 효과는 해당 실험 근거로 따로 확인합니다.',example:'cache',workspace:'ws_3668b668abba4d89',placeholder:'어떤 후보를 다음에 검토할지 알고 싶어요. 표적과 선별 조건을 적어 주세요.'},
  {id:'rna',name:'siRNA 실험 결과 해석',tag:'처리 후 결과가 있나요?',input:'유전자별 차등발현 결과표 TSV 또는 TXT.GZ',output:'표적 유전자 변화, 대조군·조건 차이와 다음 확인',limit:'기존 처리표·seed/분포 분석입니다. RNA 서열 작업은 별도 시작 항목을 이용하세요. 효능·조직 전달을 처리표만으로 확정하지 않습니다.',example:'rna',workspace:'ws_97e175bb05cc4ece',placeholder:'표적 유전자, 종·조직, 처리군과 대조군, 지금 해석하려는 질문을 적어 주세요.'},
  {id:'question',name:'연구 질문부터 정리',tag:'어디서 시작할지 고민인가요?',input:'연구 목표, 표적·질환, 알려진 조건이나 궁금한 점',output:'접근·대안의 근거, 필요한 조사·분석과 다음 행동',limit:'자료가 없으면 실제 분석값이나 치료 경로의 우열을 만들어 내지 않습니다.',placeholder:'예: ATTR-CM 연구에서 저분자와 siRNA 접근을 검토하고 싶어요. 현재 확보한 자료는 … 이고, 먼저 결정할 것은 … 입니다.'}
];
ENTRY_PATHS.push({id:'sequence',name:'RNA 서열·후보 검토',tag:'유전자나 가이드가 있나요?',input:'종·표적 유전자 또는 전사체, 가이드 5′→3′ 서열과 수식 여부',output:'버전이 있는 참조, 결합 영역 후보·접근성· 비표적 비교',limit:'후보 뒤에는 전체 전사체 정렬·3′UTR seed/간 발현·탐색용 활성 모델 점수를 연결할 수 있습니다. 화학수식과 전달 효과는 원 조건의 근거·모형과 새 후보를 구별해 검토합니다.',placeholder:'예: 인간 TTR의 공개 전사체를 확인하고 지정 구간에서 RNA 후보를 만들어 접근성을 비교해 주세요. 조직·수식 조건은 … 입니다.'});
const RNA_COLUMNS = ['ensembl_gene_id','baseMean','log2FoldChange','lfcSE','stat','pvalue','padj','symbol'];
// The two cards above open workspaces named in this file, so on any server that does not mount
// those exact ids the panel offered nothing at all - which is what the public demo does, where the
// first two entries in the catalog are a guided example marked "실제 연구 결과 아님" and a
// screen-check fixture, both rebuilt at every start and therefore always holding the newest
// timestamps. This lists the research this server actually holds that reached a published
// judgment, so the first thing a visitor can click is a finished study. Workspaces without a
// judgment are left out: they are mid-run or stopped, and opening one first says nothing about
// what the product does. They remain in the left-hand list.
// The guided walkthrough carries a published judgment too, and it is rebuilt at every start so it
// holds the newest timestamp and would lead this list. It names itself as not a real result, and
// that is the marker used to sort it last rather than a guess about its contents.
const NOT_REAL_RESEARCH = '실제 연구 결과 아님';
function finishedResearch(limit = 6) {
  const done = (projects || []).filter(p => p.has_decision);
  if (!done.length) return '';
  const example = p => (p.title || '').includes(NOT_REAL_RESEARCH) ? 1 : 0;
  done.sort((a, b) => example(a) - example(b));
  const shown = done.slice(0, limit);
  return `<div class="finished-research"><h3>이 서버에 있는 완료된 연구 ${done.length}건</h3>
    <ul>${shown.map(p => `<li><a href="/?workspace=${esc(p.id)}">${esc(p.title)}</a></li>`).join('')}</ul>
    ${done.length > shown.length ? `<p class="small muted">나머지 ${done.length - shown.length}건은 왼쪽 목록에 있습니다.</p>` : ''}
    <p class="small muted">판단이 게시된 연구만 적었습니다. 진행 중이거나 판단 전에 멈춘 연구도 목록에서 열 수 있습니다.</p></div>`;
}
function entryPath(){return ENTRY_PATHS.find(p=>p.id===intakeMode)||ENTRY_PATHS[2]}
function isUsageQuestion(value){
  const text=String(value??'').trim().toLowerCase();
  if(text.length>160)return false;
  const compact=text.replace(/\s+/g,'');
  return /^(이거|여기|이앱|이사이트|이플랫폼|evida|에비다)(는|가|를|을|에서|에)?(어떻게(쓰|써|사용|시작)|뭐하는|무엇을하는|사용법|쓰는법)/.test(compact)
    || /^(어떻게(쓰|써|사용)|사용법|쓰는법|시작하는법)/.test(compact)
    || /^(how (do i|to) use|what (is|does) evida)/.test(text);
}
function usageGuide(question=''){
  // What the four tabs and the five stages are for. Before this the guide never named either,
  // so a reader could not tell why a screen existed or which one answered their question.
  const stages=[
    ['구조화된 질문과 목표','연구자가 적은 원 요청이 맨 위에 그대로 남고, 그 아래에 모델이 구조화한 목표·조건·모르는 것이 놓입니다. 두 가지를 나란히 두어 해석이 맞는지 볼 수 있습니다.'],
    ['기전과 접근','어떤 기전을 겨냥할지 비교합니다. 기록한 축으로 계산한 순서를 보여주고, 하나가 앞선다고 말할 수 없으면 그렇게 적습니다. 추천 1순위를 따를 의무는 없습니다 — 다른 순위를 고르면 그 경로로 연구가 이어집니다.'],
    ['후보 발굴','그 기전을 겨냥할 분자·서열을 실제로 찾아 구조·물성과 함께 보여줍니다. 추천 밖 후보도 목록에 남습니다.'],
    ['근거와 계산','앞 단계의 판단이 어떤 원자료와 계산에서 나왔는지 모읍니다. 임상시험은 1차 종점 값과 이상반응을, 계산은 무엇을 확인했고 수치가 얼마인지를 보여줍니다.'],
    ['EVIDA 실험 권고','연구자가 실제로 할 다음 행동입니다. 측정 대상·조건·비교군·판독 지표와, 결과가 A면 무엇이 바뀌고 B면 무엇이 바뀌는지를 함께 적습니다.'],
  ];
  const tabs=[
    ['연구','위 다섯 단계를 순서대로 봅니다. 평소에는 이 탭만 보면 됩니다.'],
    ['자료','회수한 원자료와 계산 결과를 하나씩 열어 봅니다. 단계에서 본 근거의 원본이 여기 있고, 맨 아래 <strong>직접 조회</strong>를 열면 표적·화합물·RNA를 이름으로 조회하거나 계산을 따로 돌릴 수 있습니다.'],
  ];
  return `<section class="usage-answer" aria-label="EVIDA 사용 안내"><div class="section-mark">사용 안내 · 현재 연결된 기능 기준</div>${question?`<p class="small muted">질문: ${esc(question)}</p>`:''}
    <h2>질환과 바꾸고 싶은 결과부터 적어 주세요.</h2>
    <p>표적도 후보도 정하지 않은 채 시작해도 됩니다. EVIDA가 공개 근거에서 기전을 찾고, 그 기전을 겨냥할 후보를 실제로 회수하거나 생성해, 다음에 해볼 실험까지 이어 줍니다. 이미 후보나 실험 자료가 있다면 그 지점부터 시작할 수도 있습니다.</p>
    <h3>연구 판단의 다섯 단계</h3>
    <ol class="usage-stages">${stages.map(([name,what])=>`<li><strong>${esc(name)}</strong> — ${esc(what)}</li>`).join('')}</ol>
    <p class="small muted">단계는 한 번 지나가면 끝나는 절차가 아닙니다. 새 관측이나 생각을 넣으면 앞 단계로 돌아가 판단이 다시 계산됩니다.</p>
    <h3>두 개의 탭</h3>
    <ul class="usage-tabs">${tabs.map(([name,what])=>`<li><strong>${esc(name)}</strong> — ${what}</li>`).join('')}</ul>
    <p class="small muted">무엇이 언제 바뀌었는지는 오른쪽 위 <strong>변경 기록</strong>에 시간순으로 남습니다.</p>
    <h3>연구자가 개입하는 곳</h3>
    <p>각 단계 아래의 <strong>이 지점에서 개입하기</strong>에 질문·새 관측·조건 정정을 넣습니다. 실험 결과를 넣으면 그 결과로 가설과 순위가 다시 검토됩니다. 추천을 따르지 않고 다른 경로를 골라도 원래 추천과 이유는 그대로 남습니다.</p>
    <p class="limit">화면의 순서와 점수는 기록한 근거를 정리한 것이지 성공 확률이 아닙니다. 확인하지 않은 것은 '미확인'으로 남고 0으로 바뀌지 않습니다. 조회에 실패한 것과 실제로 없는 것은 구분해 표시합니다.</p>
    <p><a href="/team.html">질환만으로 시작한 실제 저분자·siRNA 연구 열기 ↗</a></p>
    <div class="entry-help-actions">${ENTRY_PATHS.map(p=>button('choose-path',esc(p.name),`data-mode="${p.id}"`,'small')).join('')}</div>
    <details><summary>자료 입력용 CACHE·처리표 예제는 무엇인가요?</summary><p><strong>CACHE</strong>는 공개 화합물 발굴 평가 프로젝트의 자료 이름입니다. 여기서는 LRRK2 표적의 기존 후보73개로 물성·예측·실험 관측을 구분하는 흐름을 봅니다. EVIDA 기능명이나 ATTR-CM 치료 후보 세트가 아닙니다. <a href="https://zenodo.org/records/13820554" target="_blank" rel="noopener noreferrer">원자료</a></p><p><strong>처리표 입력용 RNA 예제</strong>는 랫드 간 Ttr 관련 처리표3개를 해석합니다. 첫 화면의 인간 ATTR 질환 출발 예시와 다른 자료입니다. 새 siRNA를 설계하는 기능과는 구분하며, 이 두 예제를 같은 질환의 직접 경로 비교로 사용하지 않습니다.</p></details></section>`;
}
function openUsageHelp(question=''){showDialog('EVIDA 사용 안내',usageGuide(question))}
function renderWelcome(){
  const p=entryPath();
  return `<div class="welcome intake-home"><div class="welcome-heading"><div><span class="eyebrow">연구 시작</span><h1>지금 어떤 일을 확인하고 싶으세요?</h1><p class="description">가진 자료에서 시작해, 다음 연구 판단까지 이어갑니다.</p></div>${button('usage-help','사용법 보기','','quiet small')}</div>
  <div class="entry-paths" role="group" aria-label="시작할 연구 작업">${ENTRY_PATHS.map(item=>`<button type="button" data-action="choose-path" data-mode="${item.id}" class="entry-path ${item.id===intakeMode?'selected':''}" aria-pressed="${item.id===intakeMode}"><span class="eyebrow">${esc(item.tag)}</span><strong>${esc(item.name)}</strong><span>${esc(item.output)}</span></button>`).join('')}</div>
  <section class="intake-panel" aria-label="연구 입력"><div class="intake-contract"><div><span class="section-mark">넣을 것</span><p>${esc(p.input)}</p></div><span aria-hidden="true">→</span><div><span class="section-mark">받을 것</span><p>${esc(p.output)}</p></div></div>
  ${['molecule','rna'].includes(p.id)?`<div class="intake-upload"><label class="input-label" for="intake-file">1. 분석할 파일</label><input type="file" id="intake-file" accept="${p.id==='molecule'?'.csv,.tsv,.txt':'.tsv,.txt,.gz'}"><p id="intake-file-name" class="small muted">${intakeFile?esc(intakeFile.name)+' 선택됨':'파일을 선택하세요. 아직 서버로 전송되지 않습니다.'}</p>${p.id==='molecule'?`<details><summary>CSV 열 이름·구분자 설정</summary><div class="upload-fields"><label>구분자<select id="intake-delimiter"><option value="," ${intakeDelimiter===','?'selected':''}>쉼표</option><option value=";" ${intakeDelimiter===';'?'selected':''}>세미콜론</option><option value="tab" ${intakeDelimiter==='tab'?'selected':''}>탭</option></select></label><label>후보 ID 열<input id="intake-id" type="text" value="${esc(intakeId)}"></label><label>SMILES 열<input id="intake-smiles" type="text" value="${esc(intakeSmiles)}"></label></div><a href="/templates/molecules.csv" download>빈 CSV 양식 받기</a></details>`:`<details><summary>지원하는 RNA 결과표 형식</summary><p class="small">UTF-8, 탭으로 구분된 DESeq2 결과표입니다. FASTQ나 raw count matrix는 이 입력에 해당하지 않습니다.</p><p class="mono">${RNA_COLUMNS.join(' · ')}</p><p class="small">열 이름을 확인하고, 결측은 NA로 유지하세요. 임의의 값이나 p값을 채우지 마세요.</p><a href="/templates/rna-results.tsv" download>빈 TSV 양식 받기</a></details>`}</div><label class="input-label" for="intake-context">2. 자료의 조건</label><textarea id="intake-context" class="short-input" placeholder="${p.id==='molecule'?'표적, 후보 출처, 측정값이 있다면 단위·측정 조건. 모르는 항목은 미확인으로 적어 주세요.':'표적 유전자, 종·조직, 처리군과 대조군, 용량·시점, 공유 대조군 여부. 모르는 항목은 미확인으로 적어 주세요.'}">${esc(intakeContext)}</textarea>`:''}
  <label class="input-label" for="message">${!['molecule','rna'].includes(p.id)?'지금 궁금한 질문': '3. 이번에 확인할 질문'}</label><textarea id="message" placeholder="${esc(p.placeholder)}">${esc(draft)}</textarea>
  ${intakeError?`<p class="form-error" role="alert">${esc(intakeError)}</p>`:''}
  <div class="input-bottom"><span class="small muted">${!['molecule','rna'].includes(p.id)?'접근·표적이 미정이어도 연구 목표와 질문으로 시작할 수 있습니다.':'원자료를 보존하고 실제 계산 결과를 연결합니다.'}</span>${modelChoice()}${button('create-message',!['molecule','rna'].includes(p.id)?'질문 검토 시작':'자료 분석 시작',busy?'disabled':'','primary')}</div><p class="small muted submit-note">분석·검토 시작은 실제 모델과 도구를 실행하며 수분이 걸릴 수 있습니다. 사용법 안내에는 모델을 호출하지 않습니다.</p>
  <details class="support-scope"><summary>현재 이 작업에서 가능한 범위</summary><p class="small">${esc(p.limit)}</p></details></section>
  <section class="try-examples"><div><h2>자료 없이 먼저 살펴보세요</h2><p class="small muted">완료한 결과를 보거나, 같은 공개 원자료로 새 분석을 시작할 수 있습니다.</p></div><div class="example-choices">${ENTRY_PATHS.filter(x=>x.example).map(x=>`<article><h3>${esc(x.name)}</h3><p class="small">${x.id==='molecule'?'LRRK2 공개 후보73개 · CACHE 자료':'랫드 간 Ttr 처리표3개 · 공개 RNA 자료'}</p><div class="detail-actions">${projects.some(p=>p.id===x.workspace)?`<a href="/?workspace=${x.workspace}&guide=${x.id==='molecule'?'molecule':'rna'}">완료 결과 열기</a>`:''}${button('intake-example','예제 자료로 새 분석',`data-id="${x.example}" ${!status.gateway.available||busy?'disabled':''}`,'small')}</div></article>`).join('')}</div>${finishedResearch()}</section></div>`;
}
function renderWorkflowStatus(){
  const current=Boolean(state.decision&&state.rev===state.decision_rev);
  const active=state.jobs.some(j=>['queued','running'].includes(j.status));
  const latest=[...state.jobs].reverse().find(j=>j.kind==='planner'&&j.based_rev===state.rev);
  const inputs=state.artifacts.filter(a=>!['model_receipt','decision_proposal','research_notes','tool_reading','protocol_snapshot'].includes(a.kind));
  const request=state.events.filter(e=>['message','observation','correction'].includes(e.kind)).at(-1)?.body.text??'';
  const guideOnly=!state.jobs.length&&isUsageQuestion(request);
  if(guideOnly)return usageGuide(request);
  const hasPrevious=Boolean(state.decision);
  const queued=latest?.status==='queued';
  const oldOnly=active&&!state.jobs.some(j=>j.based_rev===state.rev&&['queued','running'].includes(j.status));
  const title=current?'검토 결과가 준비됐습니다.':queued?'검토 실행을 기다리고 있습니다.':oldOnly?'이전 조건의 작업이 실행 중입니다.':active?'입력한 질문을 검토하고 있습니다.':latest?'이번 검토가 끝까지 완료되지 않았습니다.':hasPrevious?'새 근거가 추가됐습니다. 이전 판단과 비교해 보세요.':inputs.length?'자료가 준비됐습니다. 분석을 시작해 주세요.':'질문이 저장됐습니다. 검토를 시작해 주세요.';
  const body=current?'아래에서 판단과 근거를 확인하고, 추가 질문이나 새 관측으로 이어가세요.':queued?'요청은 저장됐습니다. 실행 순서를 기다리고 있으며 같은 질문을 다시 보내지 않아도 됩니다. 기존 자료와 판단은 지금도 확인할 수 있습니다.':oldOnly?'새 입력은 저장됐지만 현재 조건의 검토는 아직 시작되지 않았습니다. 실행 중인 작업의 결과는 원래 조건으로 보존합니다.':active?'진행 중에도 자료를 살펴볼 수 있습니다. 페이지를 새로고침해도 작업은 이어집니다.':latest?(latest.error||'완료한 자료와 이전 판단은 보존돼 있습니다. 실행 기록에서 현재 상태를 확인하세요.'):hasPrevious?'이전 판단과 모든 원자료는 보존돼 있습니다. 추가된 근거로 판단을 갱신하거나, 가정·관측을 더 입력할 수 있습니다.':'입력 저장만으로는 모델이 실행되지 않습니다. 아래 버튼을 누르면 실제 검토와 필요한 도구 실행을 시작합니다.';
  const content = `<ol class="workflow-steps"><li class="done">1 요청·자료</li><li class="${active&&!queued&&!oldOnly?'now':current?'done':''}">2 분석·근거 검토</li><li class="${current?'done':''}">3 판단·다음 행동</li><li>4 관측·정정 반영</li></ol><strong>${esc(title)}</strong><p>${esc(body)}</p>${workflowActivity(latest)}${renderSavedProgress()}${!current&&!active&&!latest?button('plan',hasPrevious?'새 근거로 판단 갱신':inputs.length?'이 자료 분석하기':'저장한 질문 검토하기',!status.gateway.available||busy?'disabled':'','primary small'):''}${!active&&latest&&!current?button('show-jobs','실행 상태 확인','','small'):''}`;
  if(current&&!active)return `<details class="workflow-status workflow-complete"><summary>검토 완료 · 조사 과정 보기</summary>${content}</details>`;
  return `<section class="workflow-status ${active?'working':''}" aria-live="polite">${content}</section>`;
}
function renderSavedProgress(){
  const progress=state.research_progress;
  if(!progress)return '';
  if(progress.status==='unavailable')return `<p class="small muted">${esc(progress.message)}</p>`;
  const notes=progress.notes, findings=notes.findings??[];
  const finding=item=>`<li><p>${judgmentText(item.text)}</p>${sourceLinks(item.source_ids.filter(id=>state.artifacts.some(a=>a.id===id)))}</li>`;
  return `<section class="saved-progress" aria-label="조사 중 기록"><div class="section-mark">조사 중 기록 · ${esc(time(progress.created))}</div>
    ${notes.next_goal?`<p><strong>확인하려는 질문</strong> · ${judgmentText(notes.next_goal)}</p>`:''}
    <p class="small muted">${progress.following_operation_returned?'이 질문의 도구 응답이 도착했습니다. 다음 해석을 준비하고 있습니다.':'다음 조회·계산을 위해 남긴 질문입니다. 아직 결과 확인과 구별해 주세요.'}</p>
    ${findings.length?`<div><strong>지금까지 남긴 잠정 발견</strong><ul class="list">${findings.slice(-2).map(finding).join('')}</ul>${findings.length>2?`<details><summary>이 메모의 나머지 발견 ${findings.length-2}개</summary><ul class="list">${findings.slice(0,-2).map(finding).join('')}</ul></details>`:''}</div>`:''}
    ${notes.open_questions?.length?`<details><summary>아직 풀리지 않은 질문 ${notes.open_questions.length}개</summary>${list(notes.open_questions)}</details>`:''}
    <p class="limit">완료 전 연구 메모입니다. 새 근거에 따라 달라질 수 있으며 최종 판단은 아래에 따로 표시합니다.</p></section>`;
}
function workflowActivity(planner){
  if(!planner||!['queued','running'].includes(planner.status))return '';
  const tools=state.jobs.filter(j=>!['planner','explanation'].includes(j.kind)&&j.based_rev===planner.based_rev&&j.created>=planner.created);
  const running=tools.filter(j=>j.status==='running').at(-1);
  const completed=tools.filter(j=>['succeeded','reused'].includes(j.status)&&j.output_id).sort((a,b)=>a.updated.localeCompare(b.updated)).at(-1);
  return `<div class="workflow-activity"><p>요청 시각 ${esc(time(planner.created))}${running?` · 현재 작업: ${esc(labels[running.kind]??'연결 도구')}`:''}</p>${completed?`<p>최근 완료: ${esc(labels[completed.kind]??'연결 도구')} · ${esc(time(completed.updated))}. 결과의 과학적 해석은 최종 판단에서 확인하세요.</p>${sourceLinks([completed.output_id])}`:''}</div>`;
}
function headerFields(text,delimiter){
  const fields=[];let field='',quoted=false;
  text=text.replace(/^\uFEFF/,'');
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(c==='"'){if(quoted&&text[i+1]==='"'){field+='"';i++}else quoted=!quoted}
    else if(!quoted&&c===delimiter){fields.push(field);field=''}
    else if(!quoted&&(c==='\n'||c==='\r')){fields.push(field);return fields}
    else field+=c;
  }
  if(quoted)throw Error('헤더의 따옴표가 닫히지 않았습니다. 파일 구분자와 첫 행을 확인해 주세요.');
  fields.push(field);return fields;
}
async function validateInputFile(file,kind,meta){
  if(!file)throw Error('먼저 분석할 파일을 선택해 주세요. 자료가 없으면 “연구 질문부터 정리”를 선택할 수 있습니다.');
  if(!file.size||file.size>10*1024*1024)throw Error('내용이 있는 10 MiB 이내 파일을 선택해 주세요.');
  if(kind==='rna_table'&&file.name.toLowerCase().endsWith('.gz'))return;
  let text;
  try{text=new TextDecoder('utf-8',{fatal:true}).decode(await file.slice(0,65536).arrayBuffer(),{stream:true})}catch{throw Error('파일을 UTF-8로 저장해 주세요. 원본은 변경하지 않았습니다.')}
  const fields=headerFields(text,kind==='rna_table'?'\t':meta.delimiter);
  const needed=kind==='rna_table'?RNA_COLUMNS:[meta.id_column,meta.smiles_column];
  const missing=needed.filter(n=>!n||fields.filter(f=>f===n).length!==1);
  if(missing.length)throw Error('필수 열이 없거나 중복됐습니다: '+missing.join(', ')+'. 파일 형식과 열 이름을 확인해 주세요.');
}
async function uploadInput(file,kind,meta){
  const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
  for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
  await api(`/api/workspaces/${state.id}/artifacts`,{title:file.name,kind,content_base64:btoa(binary),meta:{original_filename:file.name,encoding:'utf-8-sig',...meta}});
  await refresh();
}
function rememberWorkspace(){
  const u=new URL(location.href);u.searchParams.delete('guide');u.searchParams.set('workspace',state.id);history.replaceState(null,'',u);
  evidaStorage.setItem('evida-project',state.id);tab='research';selected=null;detail=null;
}
async function startIntake(){
  if(isUsageQuestion(draft)){openUsageHelp(draft);return}
  const p=entryPath();
  if(!draft.trim())throw Error('이번에 알고 싶은 질문을 적어 주세요. 사용법이 궁금하면 “사용법 보기”를 누르세요.');
  if(!await refreshGatewayStatus({force:true,renderChanges:false}))throw Error('현재 모델 연결을 사용할 수 없습니다. 입력 초안은 그대로 남아 있습니다.');
  const kind=p.id==='rna'?'rna_table':'molecule_csv';
  const meta={delimiter:p.id==='rna'?'\t':intakeDelimiter==='tab'?'\t':intakeDelimiter,smiles_column:intakeSmiles,id_column:intakeId,context:intakeContext.trim()||'자료 조건 미확인 — 연구자 확인 필요'};
  if(['molecule','rna'].includes(p.id))await validateInputFile(intakeFile,kind,meta);
  submitPhase='질문과 원자료를 저장하고 있습니다.';render();
  state=await api('/api/workspaces',{title:draft.trim().slice(0,50)});rememberWorkspace();inputKind='message';syntheticDraft=false;
  if(p.id==='question'&&goalApproach)draft+='\n연구자가 우선 지정한 접근: '+(goalApproach==='small_molecule'?'저분자':'siRNA')+'. 다른 접근의 유용한 근거는 대안으로 보존해 주세요.';
  await saveMessage();
  if(['molecule','rna'].includes(p.id))await uploadInput(intakeFile,kind,meta);
  projects=await api('/api/workspaces');intakeFile=null;intakeContext='';
  submitPhase='실제 검토를 시작하고 있습니다.';render();
  await runTool('planner',plannerOptions());
}
function plannerOptions(){
  // Omitted entirely when the reader kept the server's model, so a run that made no choice
  // carries no claim to have made one.
  return chosenModel&&chosenModel!==status.gateway?.requested_model?{model:chosenModel}:{};
}
async function startExample(id){
  if(!await refreshGatewayStatus({force:true,renderChanges:false}))throw Error('현재 모델 연결을 사용할 수 없습니다. 완료 결과는 바로 열 수 있습니다.');
  submitPhase='공개 원자료를 새 연구에 연결하고 있습니다.';render();
  state=await api('/api/team-examples',{id});rememberWorkspace();draft='';inputKind='message';syntheticDraft=false;
  projects=await api('/api/workspaces');submitPhase='예제의 실제 분석을 시작하고 있습니다.';render();
  await runTool('planner',plannerOptions());
}
function chooseEntry(mode){
  if(!ENTRY_PATHS.some(p=>p.id===mode))return;
  if(dialog.open)dialog.close();
  if(state){state=null;selected=null;detail=null;draft=evidaStorage.getItem('evida-draft-new')??'';history.replaceState(null,'',deploymentURL('/'));evidaStorage.removeItem('evida-project')}
  intakeMode=mode;intakeError='';actionError='';inputKind='message';syntheticDraft=false;render();
  document.querySelector('.intake-panel')?.scrollIntoView({behavior:'smooth',block:'start'});
}
document.addEventListener('input',event=>{
  const id=event.target.id,v=event.target.value;
  if(id==='intake-context')intakeContext=v;
  if(id==='intake-id')intakeId=v;
  if(id==='intake-smiles')intakeSmiles=v;
});
document.addEventListener('change',event=>{
  if(event.target.id==='intake-file'){intakeFile=event.target.files[0]??null;document.getElementById('intake-file-name').textContent=intakeFile?intakeFile.name+' 선택됨':'파일을 선택하세요.'}
  if(event.target.id==='intake-delimiter')intakeDelimiter=event.target.value;
  if(event.target.id==='intake-model'){
    if(offeredModels().includes(event.target.value))chosenModel=event.target.value;
    else{event.target.value=chosenModel??status.gateway?.requested_model??'';notice('현재 연결에서 허용된 모델만 선택할 수 있습니다.')}
  }
  if(event.target.id==='upload-kind')updateUploadKind();
});
function updateUploadKind(){
  const rna=dialog.querySelector('#upload-kind')?.value==='rna_table';
  for(const el of dialog.querySelectorAll('[data-molecule-field]'))el.hidden=rna;
  const d=dialog.querySelector('#upload-delimiter');if(d)d.value=rna?'tab':',';
  const help=dialog.querySelector('#upload-format-help');if(help)help.innerHTML=deploymentHTML(rna?`<p>UTF-8·탭 구분의 기존 차등발현 결과표입니다. 필수 열:</p><p class="mono">${RNA_COLUMNS.join(' · ')}</p><a href="/templates/rna-results.tsv" download>빈 TSV 양식 받기</a>`:'<p>후보 ID와 SMILES가 있는 CSV입니다. 열 이름과 구분자를 맞춰 주세요.</p><a href="/templates/molecules.csv" download>빈 CSV 양식 받기</a>');
}
