// Reading state belongs to the browser. Scientific records and their ordering stay unchanged.
const researchReaders = new Map(), experimentSelections = new Map(), candidateViews = new Map();
const researchSubjects = new Map(), outcomeSelections = new Map();
let workspaceWide=false, conversationOpen=false;
let readerRequest = 0, researchSearch = '', researchListMode = 'recent', researchRailCollapsed = true;
const readerHistoryFrames=new Map();
let renderedResearchPanel=null;
const workspaceTabs = [['','한눈에 보기'],['mechanisms','기전'],['candidates','후보'],['next','실험'],['evidence','근거']];
function uiIcon(name){
  const paths={menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',mechanism:'<rect x="9" y="2" width="6" height="5" rx="1"/><rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/><path d="M12 7v5M5 17v-5h14v5"/>',molecule:'<path d="m12 2 8.5 5v10L12 22l-8.5-5V7Z"/><path d="m6.5 8.5 5.5-3.2M17.5 9v6M12 18.5l-5.5-3.2"/>',experiment:'<path d="M8 2h8M10 2v7l-6.5 10A2 2 0 0 0 5.2 22h13.6a2 2 0 0 0 1.7-3L14 9V2M7 15h10"/>'};
  return `<svg class="ui-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]??paths.molecule}</svg>`;
}
function uiQuickLinks(){return `<nav class="ui-quick-links" aria-label="연구 바로가기">${[['mechanisms','mechanism','기전과 후보의 연결'],['candidates','molecule','후보 구조와 검토'],['next','experiment','실험 설계와 판독']].map(([stage,icon,label])=>button('ui-stage',`${uiIcon(icon)}<span>${label}</span>`,`data-stage="${stage}"`,'ui-quick-link')).join('')}</nav>`}
function readerState(){return state?researchReaders.get(state.id):null}
function currentReader(){return readerState()?.stack.at(-1)??null}
function uiText(value){return judgmentText(researcherWording(value))}
function uiEmpty(text){return `<p class="ui-missing">${esc(text)}</p>`}
function syntheticInputNotice(){const rows=state.events.filter(e=>['message','observation','correction'].includes(e.kind)&&inputProvenance(e).synthetic);return rows.length?`<details><summary>가상 목표·입력 ${rows.length}건 포함</summary>${rows.map(e=>button('message-source','입력 원문',`data-id="${esc(e.body.message_id)}"`,'link-button small')).join('')}<p>가상 시연 입력으로 구분해 보존했습니다.</p></details>`:''}
function uiRevision(a){return !a?'검토 전':a.current_conditions===true?'현재 조건':a.current_conditions===false?'이전 조건':'적용 조건 확인 필요'}
function uiExcerpt(value){
  // A labelled verbatim first paragraph/sentence, never an inferred scientific summary.
  const text=String(value??'').trim();
  const boundary=text.search(/(?:[.!?。](?=\s|$)|\n)/);
  return boundary>=0?text.slice(0,boundary+1):text;
}
function uiStage(){return tab==='research'?(roadmapChosen()??''):tab}
// Navigation preferences only. These IDs never enter a scientific ranking or a job.
const INITIAL_PINNED_RESEARCH=['ws_3c8fe9df9cd14339','ws_4475545a286541b2','ws_1ff05aa2d7c24e0e'];
// Exact manually seeded screen fixtures, verified against their original creation scripts.
// This is navigation metadata only: no title matching, job-state filtering or record deletion.
const ARCHIVED_RESEARCH_EXAMPLES=Object.freeze({
  ws_741a80721d08469f:'순위 화면 점검용 고정 자료',
  ws_05cd9d62e1664faa:'다섯 단계 화면 예시'
});
function isArchivedResearchExample(id){return Object.hasOwn(ARCHIVED_RESEARCH_EXAMPLES,id)}
function archivedResearchNotice(){
  if(!isArchivedResearchExample(state?.id))return '';
  return `<aside class="panel" data-archived-research="${esc(state.id)}" aria-label="보관된 개발 예시"><strong>보관된 개발 예시 · ${esc(ARCHIVED_RESEARCH_EXAMPLES[state.id])}</strong><p class="small">화면 점검용으로 직접 작성한 후보·판단입니다. 원 기록을 보존했습니다.</p>${button('project','실제 IPF 연구 열기','data-id="ws_3c8fe9df9cd14339"','link-button small')}</aside>`;
}
const RESEARCH_PIN_KEY='evida-pinned-research';
function pinnedResearchIds(){
  try{const saved=evidaStorage.getItem(RESEARCH_PIN_KEY);if(saved===null)return [...INITIAL_PINNED_RESEARCH];
    const ids=JSON.parse(saved);return Array.isArray(ids)?[...new Set(ids.filter(x=>typeof x==='string'))]:[];
  }catch{return []}
}
function researchRailGroups(){
  const q=researchSearch.toLocaleLowerCase(),pins=pinnedResearchIds(),rows=projects.filter(p=>!q||p.title.toLocaleLowerCase().includes(q));
  const pinned=pins.map(id=>rows.find(p=>p.id===id)).filter(Boolean),unpinned=rows.filter(p=>!pins.includes(p.id));
  const archived=unpinned.filter(p=>isArchivedResearchExample(p.id)),others=unpinned.filter(p=>!isArchivedResearchExample(p.id));
  return {pinned,archived,visibleTotal:pinned.length+others.length,others:researchListMode==='recent'&&!q?others.slice(0,8):others,hasMore:researchListMode==='recent'&&!q&&others.length>8};
}
function toggleResearchPin(id){
  if(!projects.some(p=>p.id===id))return false;
  const ids=pinnedResearchIds(),next=ids.includes(id)?ids.filter(x=>x!==id):[...ids,id];
  try{evidaStorage.setItem(RESEARCH_PIN_KEY,JSON.stringify(next));return true}
  catch{notice('이 브라우저에 고정 목록을 저장할 수 없습니다.');return false}
}
function researchRailRow(p,pinned){
  const pinIcon='<svg class="ui-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m9 3 6 0-1 6 4 4v2H6v-2l4-4-1-6ZM12 15v7"/></svg>';
  return `<div class="ui-project-row ${pinned?'is-pinned':''}" data-research-id="${esc(p.id)}">${button('project',`<span class="project-name">${esc(p.title)}</span><small class="project-status">${isArchivedResearchExample(p.id)?'개발 예시 · ':''}${Number.isInteger(p.rev)?'연구 기록 '+p.rev+' · ':''}${esc(({reviewed:'판단 기록 있음',needs_review:'판단 갱신 필요',awaiting_input:'입력 대기'})[p.review_status]??'상태 확인 필요')}</small>`,`data-id="${esc(p.id)}" aria-current="${p.id===state?.id?'page':'false'}"`,`project ${p.id===state?.id?'active':''}`)}${button('ui-pin-research',pinIcon,`data-id="${esc(p.id)}" aria-label="${esc(p.title)} · ${pinned?'고정 해제':'연구 고정'}" title="${pinned?'고정 해제':'연구 고정'}" aria-pressed="${pinned}"`,'ui-project-pin quiet small')}</div>`;
}
function uiDecisionRecord(id){
  const event=[...(state?.events??[])].reverse().find(e=>e.kind==='decision_published'&&e.body.receipt_id===id);
  if(!event)return null;
  const current=id===state.decision_id;
  return {id,rev:event.body.state_rev,current,title:`${current?'현재 게시 판단':'이전 판단'} · 연구 기록 ${event.body.state_rev}`};
}
function renderResearchRail(){
  const {pinned,others,archived,hasMore,visibleTotal}=researchRailGroups();
  return `<div class="rail-heading"><div class="brand">EVIDA</div>${button('ui-rail',uiIcon('menu'),`aria-label="연구 목록 ${researchRailCollapsed?'펼치기':'접기'}" aria-expanded="${!researchRailCollapsed}"`,'quiet small')}</div>
    ${button('new','＋ 새 연구','','new-button')}
    <div class="rail-browser"><label class="sr-only" for="research-search">저장된 연구 검색</label><input id="research-search" type="search" value="${esc(researchSearch)}" placeholder="연구 검색">
    <div class="rail-list-modes">${[['recent','최근 연구'],['all','전체 연구']].map(([id,label])=>button('ui-research-mode',label,`data-mode="${id}" aria-pressed="${researchListMode===id}"`,'quiet small')).join('')}</div>
    <div class="project-list"><nav aria-label="저장된 연구">${pinned.length?`<p class="rail-group-label">고정한 연구 <small>이 브라우저</small></p>${pinned.map(p=>researchRailRow(p,true)).join('')}`:''}${others.length?`<p class="rail-group-label">${researchListMode==='recent'&&!researchSearch?'최근 연구':'다른 연구'}</p>${others.map(p=>researchRailRow(p,false)).join('')}`:''}${!pinned.length&&!others.length?uiEmpty('일치하는 연구가 없습니다.'):''}</nav>
    ${hasMore?button('ui-research-mode',`연구 ${visibleTotal}개 보기`,'data-mode="all"','quiet small'):''}
    ${archived.length?`<details class="ui-secondary" data-detail-key="research-archive"><summary>개발 예시 보관함 · ${archived.length}개</summary><p class="small muted">화면 점검용 기록입니다. 원문과 후보를 그대로 보존합니다.</p><nav aria-label="보관된 개발 예시">${archived.map(p=>researchRailRow(p,false)).join('')}</nav></details>`:''}</div></div>`;
}
function renderDecisionWorkspace(){
  const stage=uiStage(),model=roadmapModel(),reading=currentReader();
  if(tab==='research'){queueMicrotask(()=>loadCandidateStructures());queueMicrotask(()=>loadMechanismRanking());queueMicrotask(()=>uiWarmSources())}
  const active=state.jobs.some(j=>['running','queued'].includes(j.status));
  const body=tab==='data'?dataView():tab==='history'?historyPanel():stage==='mechanisms'?renderResearchPath():stage==='candidates'?uiCandidates():stage==='next'?uiExperiments():stage==='evidence'?`${renderEvidenceWorkbench()}<details class="ui-secondary"><summary>계산·조회·근거의 전체 기록</summary>${roadmapEvidencePanel()}</details>`:stage==='goal'?roadmapGoalPanel():stage==='changes'?roadmapChangesPanel(model):uiOverview(model);
  return `${archivedResearchNotice()}<header class="ui-workspace-heading"><div><span class="ui-eyebrow">연구 워크스페이스</span><h1>${esc(state.title)}</h1><p>${esc(roadmapRevisionText(model))}</p></div><div class="ui-workspace-tools">${button('ui-question','질문하기',`aria-expanded="${conversationOpen}"`,'small ui-question-button')}${button('ui-wide',workspaceWide?'대화와 함께 보기':'넓게 보기',`aria-pressed="${workspaceWide}"`,'small quiet')}${button('ui-stage','목표·조건','data-stage="goal"','small quiet')}</div></header>
    ${quotaNotice()}${active?roadmapActivity():''}
    <div class="ui-research-layout"><aside class="ui-conversation" aria-label="연구 대화"><header class="ui-conversation-heading"><h2>연구 대화</h2>${button('ui-question-close','닫기','aria-label="연구 대화 닫기"','small quiet ui-conversation-close')}</header>${uiConversation()}${uiQuickLinks()}<div class="ui-conversation-compose">${uiComposer(active)}</div><details class="ui-secondary" data-detail-key="workspace-log"><summary>입력 변경·실행 기록</summary>${roadmapRunLine(active)}${renderInputChanges()}${syntheticInputNotice()}</details></aside>
    <div class="ui-work-product"><header class="ui-product-heading"><span>작업물</span><nav class="ui-stage-nav" aria-label="연구 작업 화면">${[...workspaceTabs,['data','원자료']].map(([id,label])=>button('ui-stage',label,`data-stage="${id}" aria-current="${stage===id?'page':'false'}"`,`ui-stage ${stage===id?'active':''}`)).join('')}</nav></header><div class="workspace-split ${reading?'with-reader':''}"><div class="workspace-content" id="workspace-content"><section id="roadmap-inspector" tabindex="-1">${body}</section></div>${reading?renderResearchPanel():''}</div></div></div>`;
}
function uiConversation(){
  const messages=state.events.filter(e=>['message','observation','correction'].includes(e.kind));
  const original=messages[0],latest=messages.at(-1),shown=original===latest?[original]:[original,latest];
  const source=e=>`${inputProvenanceNotice(e)}${button('message-source','입력 원문·출처',`data-id="${esc(e.body.message_id)}"`,'link-button small')}`;
  return `<div class="ui-conversation-thread">${original?`<article class="ui-conversation-message"><div class="ui-conversation-meta"><strong>연구자</strong><span>처음 요청</span></div><p class="prose">${esc(uiExcerpt(original.body.text))}</p>${String(original.body.text??'')!==uiExcerpt(original.body.text)?`<details><summary>입력 전문</summary><p class="prose">${esc(original.body.text)}</p></details>`:''}${source(original)}</article>`:uiEmpty('저장된 연구자 입력 확인 필요')}${latest&&latest!==original?`<details class="ui-latest-input"><summary>최근 입력·정정</summary><p class="prose">${esc(latest.body.text)}</p>${source(latest)}</details>`:''}<article class="ui-conversation-response"><div class="ui-conversation-meta"><strong>EVIDA</strong><span>${esc(uiDecisionScope())}</span></div>${state.decision?`<ul class="ui-conversation-paths">${uiPathSummary()}</ul><details><summary>판단 원문 앞부분</summary><p>${uiText(uiExcerpt(state.decision.recommendation))}</p></details>`:'<p>아직 판단이 기록되지 않았습니다.</p>'}${state.decision?button('ui-judgment','판단 전체·근거','','link-button small'):''}</article>${messages.length>shown.filter(Boolean).length?button('ui-stage',`중간 입력 ${messages.length-shown.filter(Boolean).length}건 · 변경 기록`,'data-stage="history"','link-button small'):''}</div>`;
}
function uiOverview(model){
  const d=state.decision,node=model.nodes.find(n=>n.id==='candidates'),mechanisms=model.nodes.find(n=>n.id==='mechanisms');
  const candidate=node?.recommended?.[0]??node?.options?.[0];
  const selected=candidate&&node?.recommended?.some(x=>x.option_id===candidate.option_id);
  const checks=d?.research_loop?.next_checks??[];
  const paths=uiCurrentPaths();
  const row=candidate&&candidateStructureRow(candidate.option_id),picture=row&&structureThumb(row),assessment=candidate?.assessment,parent=row?.transformed_from??row?.core_from;
  return `<section class="ui-overview" aria-label="연구 핵심 요약">
    <article class="ui-judgment"><span class="ui-eyebrow">${model.current?'현재 판단':'마지막으로 기록한 판단'}</span><h2>${d?esc(uiDecisionScope()):'연구 질문을 검토하고 있습니다.'}</h2>${d?`<p class="ui-overview-decision-text">${uiText(d.recommendation)}</p>`:''}
      <div class="ui-judgment-links">${d?'<span class="small muted">저장된 현재 검토와 다음 확인</span>':''}${d?button('ui-judgment','판단 전체·근거 보기','','link-button small'):uiEmpty('자료 조회 후 판단이 기록되면 이곳에서 확인할 수 있습니다.')}</div></article>
    <div class="ui-overview-grid"><div class="ui-overview-visual" ${candidate?`data-candidate-option="${esc(candidate.option_id)}"`:''}><div class="ui-candidate-picture">${picture||uiEmpty(candidate&&['rna','rna_candidate'].includes(optionKind(candidate))?'RNA 서열·전사체 조건':'2D 구조 확인 필요')}</div>${candidate?button('discovery-detail',`${esc(candidateDisplayName(candidate))} · 구조 상세`, `data-id="${esc(candidate.option_id)}"`,'link-button small'):''}</div>
    <article class="ui-overview-mechanisms"><h3>검토 기전·접근</h3>${paths.length?`<ul class="ui-path-list">${paths.map(p=>`<li><span class="ui-eyebrow">${esc(uiPathKind(p))}</span><strong>${esc(researcherWording(p.label))}</strong><span>${esc(optionStatus[p.assessment?.status??'unreviewed'])} · ${uiRevision(p.assessment)}</span>${p.assessment?.priority!=null?`<small>${esc(researcherWording(p.assessment.comparison_group??'기록한 비교 범위'))} · ${p.assessment.priority}</small>`:''}</li>`).join('')}</ul>`:uiEmpty('검토할 기전과 질환의 연결 근거 확인 필요')}${button('ui-stage',paths.length>1?`기전·접근 ${paths.length}개와 질환 연결 보기`:'질환과의 연결 보기','data-stage="mechanisms"','link-button small')}</article>
    <article class="ui-overview-candidate"><h3>${selected?'현재 추천에 포함된 후보':'확대해서 보는 후보'}</h3>${candidate?`<h4>${esc(candidateDisplayName(candidate))}</h4>${uiCandidateRole(candidate)}${uiGenerationLink(candidate)}${parent?`<p class="small muted">출발 화합물 ${esc(parent)}</p>`:''}<p class="small">${esc(optionStatus[assessment?.status??'unreviewed'])} · ${uiRevision(assessment)}</p>${candidate.origin==='generated_structure_proposal'?'<p class="small muted">설계 구조 · 생성 단계 활성 미측정</p>':''}`:uiEmpty('비교할 후보와 구조 확인 필요')}${button('ui-stage','후보 전체 비교','data-stage="candidates"','link-button small')}</article>
    <article class="ui-overview-next"><h3>다음 실험·확인</h3>${checks.length?`<ul class="ui-overview-checks">${checks.map(c=>`<li>${button('ui-overview-experiment',esc(uiExperimentAlias(c)),`data-id="${esc(c.id)}"`,'link-button')}<span class="small muted">${esc(uiExperimentStatus(c))}</span></li>`).join('')}</ul>`:uiEmpty('다음 실험 권고 확인 필요')}${button('ui-stage','대상·대조군·판독 검토','data-stage="next"','link-button small')}</article></div>
    ${d?`<div class="ui-overview-foot">${button('ui-stage','이전 판단과 비교','data-stage="changes"','quiet small')}<span class="small muted">추천·계산·실제 관측은 각 근거에서 확인합니다.</span></div>`:''}</section>`;
}
function uiCandidateTile(item,compact=false){
  const row=candidateStructureRow(item.option_id),picture=row&&structureThumb(row),a=item.assessment,parent=row?.transformed_from??row?.core_from;
  return `<article class="ui-candidate ${compact?'compact':''} ${readerState()?.stack[0]?.id===item.option_id?'is-selected':''}" data-candidate-option="${esc(item.option_id)}"><div class="ui-candidate-picture">${picture||uiEmpty(['rna','rna_candidate'].includes(optionKind(item))?'RNA 서열·전사체 조건':'2D 구조 확인 필요')}</div><div><h4>${esc(candidateDisplayName(item))}</h4>${uiCandidateRole(item)}${uiGenerationLink(item)}${parent?`<p class="small muted">출발 화합물 ${esc(parent)}</p>`:''}<p class="small">${esc(optionStatus[a?.status??'unreviewed'])} · ${uiRevision(a)}</p>${item.origin==='generated_structure_proposal'?'<p class="small muted">설계 구조 · 생성 단계 활성 미측정</p>':''}${a?.priority?`<p class="small muted">${esc(researcherWording(a.comparison_group))} 내 검토 순서 ${esc(a.priority)}</p>`:''}${button('discovery-detail','후보 상세',`data-id="${esc(item.option_id)}"`,'small')}</div></article>`;
}
function uiCandidates(){
  const all=candidateOptions(),mode=candidateViews.get(state.id)??'current',focus=mechanismFocus.get(state.id);
  const groups={current:all.filter(x=>x.assessment?.current_conditions===true&&x.assessment?.status!=='deferred'),earlier:all.filter(x=>x.assessment?.current_conditions!==true||x.assessment?.status==='deferred')};
  const rows=(groups[mode]??[]).filter(x=>!focus||candidateMechanismId(x)===focus);
  return `<section class="ui-candidates"><div class="ui-section-heading"><div><h2>후보·구조</h2><p>같은 이름도 출처와 기록 ID를 기준으로 구분합니다.</p></div>${button('discovery-propose','다른 후보·경로 제안','','small')}</div>
    <nav class="ui-subnav" aria-label="후보 범위">${[['current',`현재 검토 ${groups.current.length}건`],['earlier',`보류·이전·미확인 ${groups.earlier.length}건`],['all','발견 기록 전체']].map(([id,label])=>button('ui-candidate-view',label,`data-view="${id}" aria-pressed="${mode===id}"`,'small')).join('')}</nav>
    ${focus?`<p>연결 기전: ${esc(candidateMechanismLabel(focus))} ${button('roadmap-focus-clear','필터 해제','','small')}</p>`:''}
    ${mode==='all'?`<p class="small muted">전체 ${number(state.discovery?.total??0)}개 선택지 기록입니다. 기전·표적·접근도 포함하며, 화합물의 고유 개수와 구분합니다.</p>${renderOptionBrowser()}`:`<div class="ui-candidate-grid">${rows.map(x=>uiCandidateTile(x)).join('')||uiEmpty('이 범위의 후보 기록이 없습니다. 발견 기록 전체에서 미검토 후보를 확인할 수 있습니다.')}</div>`}
    ${state.artifacts.filter(a=>a.kind==='rna_candidate_space').map(a=>`<div class="ui-secondary"><strong>보존한 RNA 서열 ${number(a.meta.summary?.unique_guide_sequences)}개</strong>${sourceLinks([a.id])}</div>`).join('')}</section>`;
}
function experimentFields(check){
  const lines=String(check.operation?.request??'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean),found={},rest=[];
  for(const line of lines){const match=REQUEST_FIELDS.map(([key,re])=>[key,line.match(re)]).find(([,m])=>m);if(match){(found[match[0]]??=[]).push(match[1][1])}else rest.push(line)}
  return {found,rest};
}
function selectedExperiment(){
  const checks=state.decision?.research_loop?.next_checks??[];
  return checks.find(x=>x.id===experimentSelections.get(state.id))??checks[0]??null;
}
function uiExperimentStatus(check){
  const run=state.research_checks?.find(x=>x.decision_id===state.decision_id&&x.check_id===check.id),job=run&&state.jobs.find(x=>x.id===run.job_id);
  return job?jobLabels[job.status]??job.status:'제안됨 · 수행 결과 확인 전';
}
function uiExperiments(){
  const checks=state.decision?.research_loop?.next_checks??[],selected=selectedExperiment();
  return `<section class="ui-experiments"><div class="ui-section-heading"><div><h2>다음 실험·확인</h2><p>무엇을 비교하고, 어떤 결과에 따라 판단을 바꿀지 검토합니다.</p></div></div>
    ${!roadmapModel().current&&state.decision?uiEmpty('이전 조건의 권고입니다. 새 입력에 맞춘 검토가 필요합니다.'):''}
    ${uiExperimentReturns.has(state.id)?button('ui-candidate-return','← 후보 상세로 돌아가기','','quiet small'):''}<div class="ui-experiment-layout"><nav class="ui-experiment-list" aria-label="실험·확인 목록">${checks.map(c=>button('ui-experiment',`<span class="ui-eyebrow">${esc(CHECK_KIND[c.operation.kind])}</span><strong>${esc(uiExperimentAlias(c))}</strong><small>${esc(uiExperimentStatus(c))}</small>`,`data-id="${esc(c.id)}" aria-pressed="${selected?.id===c.id}"`,'ui-experiment-choice')).join('')||uiEmpty('실험·확인 제안이 아직 없습니다.')}</nav>${selected?uiExperimentDetail(selected):''}</div></section>`;
}
function uiExperimentDetail(check){
  const {found,rest}=experimentFields(check),op=check.operation,loop=state.decision.research_loop;
  const field=(key)=>found[key]?.map(x=>`<p>${uiText(x)}</p>`).join('')||uiEmpty('확인 필요 · 권고에 구분해 기록된 값이 없습니다.');
  const hypotheses=(check.hypothesis_ids??[]).map(id=>loop.hypotheses.find(h=>h.id===id)).filter(Boolean);
  const scopes=(check.scope_targets??[]).flatMap(t=>(loop.hypotheses.find(h=>h.id===t.hypothesis_id)?.assessment_scope?.parts??[]).filter(p=>t.part_ids.includes(p.id)).map(p=>p.statement));
  return `<article class="ui-experiment-detail" data-research-check="${esc(check.id)}"><header><span class="ui-eyebrow">판별 질문 · ${esc(CHECK_KIND[op.kind])} · 연구 기록 ${state.decision_rev}</span><h3>${esc(uiExperimentAlias(check))}</h3><p class="small muted">${esc(uiExperimentStatus(check))}</p></header>
    <details class="ui-check-question" data-detail-key="check-question:${esc(check.id)}"><summary>전체 질문·권고 목적·연결 가설</summary><h4>원 질문</h4><p>${uiText(check.question)}</p>${check.purpose?`<p>${uiText(check.purpose)}</p>`:''}${scopes.length?list(scopes.map(researcherWording)):hypotheses.length?list(hypotheses.map(h=>researcherWording(h.statement))):uiEmpty('연결된 가설 확인 필요')}</details>
    <div class="ui-experiment-fields"><section><h4>시험 대상·시료</h4>${field('측정 대상')}</section><section><h4>비교 대상·대조</h4>${field('조건·비교군')}</section></div>
    <section class="ui-experiment-readout"><h4>읽을 값·단위와 시점</h4>${field('판독 지표')}</section>
    <section class="ui-experiment-outcomes"><h4>결과별 다음 행동</h4>${uiOutcomeBranches(check)}</section>${uiExecutionConditions(check)}
    <details class="ui-check-conditions" data-detail-key="check-conditions:${esc(check.id)}"><summary>전체 조건·설계 원문</summary>${rest.length?rest.map(x=>`<p>${uiText(x)}</p>`).join(''):''}<p class="prose">${uiText(op.request??op.method??'연결된 도구로 자료를 확인하는 단계입니다.')}</p>${op.needed_inputs?list(op.needed_inputs):''}</details>
    <details class="ui-secondary" data-detail-key="check-sources:${esc(check.id)}"><summary>실험 제안에 연결된 원자료 ${op.grounded_in?.length??0}건</summary><p class="small">실험 기록 ID: <code>${esc(check.id)}</code></p>${op.grounded_in?.length?sourceLinks(op.grounded_in):uiEmpty('구체적인 근거 자료 연결 확인 필요')}</details>
    ${uiExperimentControls(check)}
    </article>`;
}
function uiOutcomeBranches(check){
  const outcomes=check.possible_outcomes??[],key=`${state.id}:${state.decision_id}:${check.id}`;
  const chosen=Math.min(outcomeSelections.get(key)??0,Math.max(0,outcomes.length-1));
  const label=(i)=>{const relations=[...new Set((check.outcome_links??[]).filter(x=>x.outcome_index===i).flatMap(x=>x.effects??[]).map(x=>x.relation))];return relations.map(x=>({supports:'가설에 부합',challenges:'재검토',unresolved:'판정 불가 · 추가 구별'})[x]).filter(Boolean).join(' · ')||`예상 결과 ${i+1}`};
  if(!outcomes.length)return uiEmpty('결과별 판단 분기 확인 필요');
  return `<nav class="ui-result-tabs" aria-label="예상 결과별 해석">${outcomes.map((o,i)=>button('ui-outcome',esc(label(i)),`data-key="${esc(key)}" data-index="${i}" aria-pressed="${chosen===i}" aria-controls="outcome-${i}"`,'small')).join('')}</nav><div class="ui-result-branches">${outcomes.map((o,i)=>`<article id="outcome-${i}" ${chosen!==i?'hidden':''}><span class="ui-eyebrow">${esc(label(i))} · 예상 결과, 실제 관측 전</span><h5>관측할 결과</h5><p>${uiText(o.observation)}</p><h5>판단·후속 확인</h5><p>${uiText(o.implication)}</p><details><summary>연결된 가설·판단 이유</summary>${renderOutcomeLinks(check,i)}</details></article>`).join('')}</div>`;
}
function uiExperimentControls(check){
  const current=roadmapModel().current,op=check.operation,running=state.jobs.some(j=>['running','queued'].includes(j.status)),ready=state.check_readiness?.[check.id];
  const run=state.research_checks?.find(x=>x.decision_id===state.decision_id&&x.check_id===check.id),job=run&&state.jobs.find(x=>x.id===run.job_id);
  return `<footer class="ui-experiment-actions"><div><strong>기존 자료 검토</strong>
    ${job?.output_id?sourceLinks([job.output_id]):op.kind==='tool'?button('run-check','자료 조회·결과 검토',`data-check="${esc(check.id)}" ${!current||busy||running||!ready?.executable?'disabled':''}`,'small'):['external_observation','researcher_input'].includes(op.kind)?button('delegate-check','기존 자료로 먼저 확인',`data-check="${esc(check.id)}" ${!current||busy?'disabled':''}`,'small'):uiEmpty('연결할 방법·자료 확인 필요')}</div><div class="ui-observation-action"><strong>${op.kind==='external_observation'?'새 관측 기록':'정보·정정 기록'}</strong>${button('check-feedback',op.kind==='external_observation'?'실험 결과 연결':'확인한 내용 연결',`data-check="${esc(check.id)}"`,'primary small')}</div></footer>`;
}

function readerSnapshot(){
  const current=currentReader();if(!current||current!==renderedResearchPanel)return;
  current.scroll=document.querySelector('#research-reader-body')?.scrollTop??0;
  current.openDetails=[...document.querySelectorAll('#research-reader-body details')].map((n,i)=>n.open?i:-1).filter(i=>i>=0);
}
function readerOpener(){
  const node=document.activeElement;
  if(!node?.dataset?.action)return null;
  const target={action:node.dataset.action,id:node.dataset.id??'',stage:node.dataset.stage??'',detailKey:node.closest('[data-detail-key]')?.dataset.detailKey??''};
  return {...target,index:readerOpenerMatches(target).indexOf(node)};
}
function readerOpenerMatches(target){
  if(!target)return [];
  return [...document.querySelectorAll('[data-action]')].filter(n=>n.dataset.action===target.action&&(n.dataset.id??'')===(target.id??'')&&(n.dataset.stage??'')===(target.stage??'')&&(target.detailKey===undefined||(n.closest('[data-detail-key]')?.dataset.detailKey??'')===target.detailKey));
}
function restoreReaderOpener(target){
  const matches=readerOpenerMatches(target),exact=matches[target?.index??0];
  // The same paper can appear in collapsed search records and several claims.
  // Restore the exact expanded claim's link, never a hidden duplicate.
  const opener=exact?.getClientRects().length?exact:matches.find(n=>n.getClientRects().length);
  (opener??document.querySelector('#roadmap-inspector'))?.focus({preventScroll:true});
}
function rememberWorkspaceView(push=false){
  history[push?'pushState':'replaceState']({evida_view:{workspace:state.id,tab,stage:roadmapChosen(),scroll:window.scrollY,opener:readerOpener()}},'',location.href);
}
async function openResearchPanel(panel){
  if(!state)return;
  if(['candidate','relation'].includes(panel.kind)&&panel.subject)researchSubjects.set(state.id,panel.subject);
  readerSnapshot();
  let reader=readerState();
  if(!reader){rememberWorkspaceView();reader={stack:[],opener:readerOpener(),pageScroll:window.scrollY};researchReaders.set(state.id,reader)}
  if(dialog.open)dialog.close();
  const item={...panel,workspace:state.id,rev:state.rev,scroll:0,openDetails:[]};
  // Switching between candidates keeps one inspector; following a citation preserves its parent.
  const replacing=panel.kind==='candidate'&&reader.stack[0]?.kind==='candidate';
  if(replacing)reader.stack=[item];else reader.stack.push(item);
  const token=crypto.randomUUID();readerHistoryFrames.set(token,{reader,stack:[...reader.stack],stage:roadmapChosen(),tab});
  history[replacing?'replaceState':'pushState']({evida_reader:{workspace:state.id,token}},'',location.href);
  render();
  requestAnimationFrame(()=>document.querySelector('#research-reader-title')?.focus({preventScroll:true}));
}
function closeResearchPanel(back=false,fromHistory=false){
  const reader=readerState();if(!reader)return;
  ++readerRequest;
  if(back&&reader.stack.length>1){reader.stack.pop();if(!fromHistory)history.back();render();requestAnimationFrame(()=>document.querySelector('#research-reader-title')?.focus({preventScroll:true}));return}
  if(!fromHistory&&history.state?.evida_reader?.workspace===state.id)history.go(-reader.stack.length);
  researchReaders.delete(state.id);render();
  requestAnimationFrame(()=>{window.scrollTo(0,reader.pageScroll);restoreReaderOpener(reader.opener)});
}
function renderResearchPanel(){
  const panel=currentReader(),reader=readerState();if(!panel)return '';
  const body=panel.kind==='generated-group'?uiGeneratedGroup(panel):panel.kind==='candidate'?uiCandidateDetail(panel):panel.kind==='source'?uiSourceDetail(panel):panel.body??'';
  return `<aside class="research-reader" id="research-reader" aria-labelledby="research-reader-title"><header class="reader-heading"><div>${reader.stack.length>1?button('ui-reader-back','← 돌아가기','','quiet small'):panel.historyContext?button('ui-history-return','← 같은 판단 이력으로','','quiet small'):''}<h2 id="research-reader-title" tabindex="-1">${esc(panel.title)}</h2></div>${button('ui-reader-close','닫기','aria-label="근거 상세 닫기"','small')}</header>
    <div class="reader-context"><span>${esc(panel.subject?.label??state.title)}</span><small>열어본 시점 · 연구 기록 ${panel.rev}${panel.rev!==state.rev?` · 현재 연구 기록 ${state.rev}, 새 판단 확인 필요`:''}</small>${panel.subject&&panel.kind!=='candidate'&&panel.kind!=='local-draft'?button('ui-subject','이 대상에 질문',`data-kind="${esc(panel.subject.kind)}" data-id="${esc(panel.subject.id)}" data-label="${esc(panel.subject.label)}"`,'link-button small'):''}</div>
    <div id="research-reader-body" class="reader-body">${body}</div></aside>`;
}
async function uiOpenCandidate(id){
  const token=++readerRequest,item=await getOption(id);if(token!==readerRequest)return;
  await loadCandidateStructures();if(token!==readerRequest)return;
  // The initial thumbnail page is bounded. Resolve an opened candidate by its exact
  // catalog ID and stored source relation, never a name guess or a changed ranking.
  let structureError=null;
  if(!candidateStructureRow(id)&&['molecule','rna_candidate'].includes(optionKind(item))){
    try{
    const key=candidateStructuresKey();
    const value=await api(`/api/workspaces/${encodeURIComponent(state.id)}/candidate-structures?option_id=${encodeURIComponent(id)}`);
    if(token!==readerRequest||candidateStructuresKey()!==key)return;
    if(candidateStructuresFor!==key){candidateStructures={rows:[]};candidateStructuresFor=key}
    candidateStructures??={rows:[]};candidateStructures.rows??=[];
    for(const row of value.rows??[])if(row.option_id===id&&!candidateStructures.rows.some(x=>x.option_id===id))candidateStructures.rows.push(row);
    }catch(error){if(token!==readerRequest)return;structureError='후보 구조를 읽지 못했습니다. 보존된 후보 정보와 원자료를 확인할 수 있습니다.'}
  }
  const mechanism=['mechanism','target','approach','researcher_proposal'].includes(optionKind(item));
  if(mechanism){await openResearchPanel({kind:'relation',id,title:item.label,subject:{kind:'mechanism',id,label:item.label},body:optionDetail(item)});return}
  await openResearchPanel({kind:'candidate',id,title:candidateDisplayName(item),item,structureError,section:'summary',subject:{kind:'candidate',id,label:candidateDisplayName(item)}});
  const panel=currentReader();if(panel?.id===id)void uiLoadParentStructures(panel);
  if(item.candidate_artifact_id)void uiLoadGeneration(item.candidate_artifact_id);
}
function uiCandidateDetail(panel){
  const item=panel.item,a=item.assessment,row=candidateStructureRow(item.option_id),section=panel.section??'summary';
  const name=candidateDisplayName(item),parent=row?.transformed_from??row?.core_from;
  const siblings=candidateOptions(),index=siblings.findIndex(x=>x.option_id===item.option_id);
  const tabs=[['summary','요약'],['evidence','근거'],['properties','구조·물성'],['experiments','관련 실험']];
  let content='';
  if(section==='summary')content=`<p>${esc(item.description??'')}</p>${a?`<h3>검토 이유</h3><p>${uiText(a.reason)}</p><h3>다음 확인</h3><p>${uiText(a.next_action)}</p>${a.priority?`<p class="small">비교 집합: ${esc(researcherWording(a.comparison_group))} · 검토 순서 ${a.priority}</p>`:''}`:uiEmpty('후보의 개별 검토 기록 확인 필요')}${parent?`<p>출발 화합물: <strong>${esc(parent)}</strong></p><p class="small muted">구조를 생성한 이력입니다. 기능 비교는 관련 실험에서 확인합니다.</p>`:''}${sourceCandidateInfo(item,true)}${rnaOptionContext(item)}`;
  if(section==='evidence')content=`<h3>평가의 지지 근거</h3>${sourceLinks(a?.support_source_ids)||uiEmpty('연결된 지지 근거 확인 필요')}<h3>반대 근거·적용 조건</h3>${sourceLinks(a?.challenge_source_ids)}${list(a?.uncertainties)}<h3>발견한 원자료</h3>${sourceLinks((item.sources??[]).map(x=>x.artifact_id))}${(row?.name_mentions??[]).filter(m=>state.artifacts.some(a=>a.id===m.artifact_id)&&/^rows\/\d+$/.test(m.locator??'')).length?`<h3>이름이 등장한 원문 구절</h3><p class="small muted">원문 이름 등장과 데이터베이스 구조 연결입니다. 효능·시료 동일성 확인은 아닙니다.</p>${(row.name_mentions??[]).filter(m=>state.artifacts.some(a=>a.id===m.artifact_id)&&/^rows\/\d+$/.test(m.locator??'')).map(m=>button('source',esc(artifactName(m.artifact_id))+' · 원문 '+esc(m.locator),`data-id="${esc(m.artifact_id)}" data-source-offset="${Number(m.locator.split('/')[1])}"`,'link-button small')).join('')}`:''}${sourceCandidateInfo(item,true)}${item.assessments?.length>1?`<details><summary>이전 검토 ${item.assessments.length-1}개</summary>${item.assessments.slice(0,-1).reverse().map(x=>`<p>${esc(optionStatus[x.status])} · ${uiRevision(x)}</p><p>${uiText(x.reason)}</p>${sourceLinks([x.artifact_id])}`).join('')}</details>`:''}`;
  if(section==='properties')content=row?`${uiCandidatePair(panel,row)}${uiCandidateProperties(row)}${item.candidate_artifact_id?sourceLinks([item.candidate_artifact_id]):''}`:uiEmpty('이 후보에 연결된 구조·물성 기록 확인 필요');
  if(section==='experiments')content=uiRelatedExperiments(item,row);
  return `${panel.structureError?`<p role="status">${esc(panel.structureError)}</p>`:''}<div class="reader-candidate-identity">${row&&structureThumb(row)?structureFigure(row.depiction,name):uiEmpty(['rna','rna_candidate'].includes(optionKind(item))?'RNA 서열과 참조 조건을 아래 근거에서 확인하세요.':'2D 구조 확인 필요')}<div><strong>${esc(name)}</strong>${uiCandidateRole(item)}${uiGenerationLink(item)}<p>${esc(optionStatus[a?.status??'unreviewed'])} · ${uiRevision(a)}</p>${item.origin==='generated_structure_proposal'?'<p>설계 구조 · 생성 단계 활성 미측정</p>':''}<details><summary>정확한 후보 식별자</summary><code>${esc(item.option_id)}</code>${item.label!==name?`<p>원 기록명: ${esc(item.label)}</p>`:''}</details></div></div>
    <nav class="ui-subnav" aria-label="후보 상세 항목">${tabs.map(([id,label])=>button('ui-candidate-tab',label,`data-section="${id}" aria-pressed="${section===id}"`,'small')).join('')}</nav>${content}
    <footer class="reader-candidate-footer">${index>0?button('discovery-detail','← 이전 후보',`data-id="${esc(siblings[index-1].option_id)}"`,'small'):''}${index>=0&&index<siblings.length-1?button('discovery-detail','다음 후보 →',`data-id="${esc(siblings[index+1].option_id)}"`,'small'):''}${button('ui-subject','이 후보에 질문·정정',`data-kind="candidate" data-id="${esc(item.option_id)}" data-label="${esc(name)}"`,'small')}</footer>`;
}
async function uiOpenSource(id,anchor={}){
  const wid=state.id,token=++readerRequest,artifact=state.artifacts.find(a=>a.id===id.split('#')[0]);
  if(!artifact)throw Error('현재 연구에서 이 자료를 찾을 수 없습니다.');
  const parent=currentReader(),subject=parent?.subject??researchSubjects.get(wid)??{kind:'research',id:wid,label:state.title};
  const start=Number.isInteger(anchor.offset)&&anchor.offset>=0?anchor.offset:0;
  const historyContext=dialog.open&&typeof evidenceHistorySelection!=='undefined'&&evidenceHistorySelection?.wid===wid&&dialog.querySelector('.history-evidence-decision')?{hypothesisId:evidenceHistorySelection.value.hypothesis_id,offset:evidenceHistorySelection.value.offset}:parent?.historyContext;
  await openResearchPanel({kind:'source',id:artifact.id,title:artifactName(artifact.id),subject,parentTitle:parent?.title??(workspaceTabs.find(([stage])=>stage===uiStage())?.[1]??'연구'),offset:start,loading:true,anchor,historyContext,quoteRef:id.includes('#')?id.split('#').slice(1).join('#'):null});
  try{const value=await api(`/api/workspaces/${wid}/artifacts/${artifact.id}?offset=${start}&limit=30`);if(state?.id!==wid||token!==readerRequest||currentReader()?.id!==artifact.id)return;Object.assign(currentReader(),{value,loading:false,title:sourceDisplayLabel(artifact,value.result,Number.isInteger(anchor.offset)?value.result?.rows?.[0]:undefined)});render()}catch(error){if(state?.id===wid&&token===readerRequest){Object.assign(currentReader(),{loading:false,error:error.message});render()}}
}
function uiRecordedDecisionView(result,artifact){
  const record=uiDecisionRecord(artifact.id),checks=result.research_loop?.next_checks??[],hypotheses=result.research_loop?.hypotheses??[];
  return `<section class="ui-recorded-decision" data-decision-id="${esc(artifact.id)}"><h3>${esc(record?.title??'게시 전 판단 제안')}</h3><p>${esc(result.recommendation??'')}</p><details><summary>당시 판단 이유·가설 ${hypotheses.length}개</summary><p>${esc(result.reason??'')}</p>${hypotheses.map(h=>`<article><h4>${esc(h.statement)}</h4><p>${esc(hypothesisLabels[h.assessment]??h.assessment)}</p><p>${esc(h.expected_observation)}</p>${sourceLinks((h.evidence??[]).filter(e=>e.source_type==='artifact').map(e=>e.source_id))}</article>`).join('')}</details><h3>당시의 다음 실험·확인</h3>${checks.map(check=>`<details class="ui-recorded-check" data-recorded-check="${esc(check.id)}"><summary>${esc(check.purpose||check.question)}</summary><p class="small">${esc(CHECK_KIND[check.operation.kind]??check.operation.kind)} · ${esc(check.id)}</p><h4>판별 질문</h4><p>${esc(check.question)}</p><h4>당시 기록한 대상·대조·판독</h4><p class="prose">${esc(check.operation.request??check.operation.method??'기록한 도구의 실행 조건은 원문에서 확인하세요.')}</p>${check.operation.needed_inputs?list(check.operation.needed_inputs):''}${sourceLinks(check.operation.grounded_in)}${(check.possible_outcomes??[]).map((outcome,i)=>`<article class="ui-recorded-outcome"><h4>당시 예상 결과 ${i+1}</h4><p>${esc(outcome.observation)}</p><p>${esc(outcome.implication)}</p></article>`).join('')}</details>`).join('')}<details class="ui-recorded-raw"><summary>원 판단 JSON·출처 그대로 보기</summary>${json(result)}<p class="small">저장 당시 자료명: ${esc(artifact.title)}</p><p class="mono">SHA256 ${esc(artifact.sha256)}</p></details>${button('download','원본·전체 결과 내려받기',`data-id="${esc(artifact.id)}"`,'small')}</section>`;
}
function uiSourceDetail(panel){
  if(panel.loading)return '<p role="status">보존한 원자료를 읽고 있습니다.</p>';
  if(panel.error)return `<p role="alert">${esc(panel.error)}</p>`;
  const artifact=state.artifacts.find(a=>a.id===panel.id),result=panel.value?.result;if(!artifact)return uiEmpty('자료 기록 확인 필요');
  // Existing readers preserve endpoint units and uncertainties. Their execution controls are
  // removed here: reading evidence cannot submit a job or change a selected research option.
  const old={selected,detail,offset};let html;
  try{selected=panel.id;detail=panel.value;offset=panel.offset;html=artifact.kind==='decision_proposal'&&result?.research_loop?uiRecordedDecisionView(result,artifact):artifactDetail()}finally{selected=old.selected;detail=old.detail;offset=old.offset}
  const template=document.createElement('template');template.innerHTML=html;normalizeSourceTitleNodes(template.content);
  const readable=new Set(['source','download','row','prev','next','article-section','article-references','transport-handle']);
  for(const node of template.content.querySelectorAll('[data-action]')){
    if(!readable.has(node.dataset.action)){node.remove();continue}
    if(node.dataset.action==='prev'||node.dataset.action==='next'){const direction=node.dataset.action==='prev'?-30:30;node.dataset.action='ui-source-page';node.dataset.offset=String(Math.max(0,panel.offset+direction))}
    if(node.dataset.action==='row')node.dataset.action='ui-source-row';
    if(node.dataset.action==='article-section'){node.dataset.action='ui-source-page'}
    if(node.dataset.action==='article-references')node.remove();
  }
  const total=result?.total_rows??result?.retained_total_rows??result?.rows?.length;
  const guidance=result?.next_steps??result?.next_actions??result?.recommendation;
  const decisionRecord=artifact.kind==='decision_proposal'?uiDecisionRecord(artifact.id):null;
  return `<div class="reader-source-role"><strong>${decisionRecord?esc(decisionRecord.title):'원자료 · '+esc(panel.parentTitle)+'에서 열었습니다'}</strong><p class="small">자료 저장: ${new Date(artifact.created).toLocaleString('ko-KR')}${decisionRecord?' · 당시 게시 기록':' · 현재 판단의 연구 기록 '+esc(state.decision_rev??'미기록')}</p>${panel.quoteRef?`<p>연결 위치: <code>${esc(panel.quoteRef)}</code></p>`:''}${sourceLocatorDetails(artifact,panel.anchor)}${panel.anchor?.quote?`<span class="ui-eyebrow">이 판단에 연결된 원문 인용</span><blockquote>${esc(panel.anchor.quote)}</blockquote>`:''}</div>${decisionRecord?'':`<section class="reader-current-recommendation"><strong>${roadmapModel().current?'현재 판단':'마지막 판단 · 새 입력 검토 필요'}</strong><p>${uiText(uiExcerpt(state.decision?.recommendation??'판단 확인 필요'))}</p>${button('ui-stage','현재 실험·확인 권고','data-stage="next"','link-button small')}</section>`}${['literature','article'].includes(artifact.kind)?sourceBibliographyView(result,Number.isInteger(panel.anchor?.offset)?result?.rows?.[0]:undefined):''}<section class="reader-original-result"><h3>자료 생성 당시의 결과·안내</h3><p class="small muted">아래 결과와 안내는 이 자료가 생성된 시점의 기록입니다.</p>${template.innerHTML}</section>
    ${guidance?`<details><summary>이 도구 결과에 기록된 후속 안내</summary>${typeof guidance==='string'?`<p>${esc(guidance)}</p>`:json(guidance)}<p class="small">이 자료 생성 시점의 안내입니다. 현재 권고는 ‘다음 실험’에서 확인합니다.</p></details>`:''}
    ${typeof total==='number'&&total>30?`<nav class="reader-pagination" aria-label="원자료 페이지">${button('ui-source-page','이전',`data-offset="${Math.max(0,panel.offset-30)}" ${panel.offset===0?'disabled':''}`,'small')}<span>${panel.offset+1}–${Math.min(panel.offset+30,total)} / ${total}행</span>${button('ui-source-page','다음',`data-offset="${panel.offset+30}" ${panel.offset+30>=total?'disabled':''}`,'small')}</nav>`:''}
    ${button('ui-full-source','자료 작업 화면에서 열기',`data-id="${esc(panel.id)}"`,'small')}`;
}
function uiCurrentSubject(){
  const explicit=researchSubjects.get(state.id);if(explicit)return explicit;
  const panel=currentReader();if(panel?.subject)return panel.subject;
  if(uiStage()==='mechanisms'){const id=mechanismFocus.get(state.id),item=pathMechanisms().find(x=>x.option_id===id);if(item)return {kind:'mechanism',id,label:item.label}}
  if(uiStage()==='next'){const c=selectedExperiment();if(c)return {kind:'check',id:c.id,label:c.question,decision_id:state.decision_id}}
  return researchSubjects.get(state.id)??{kind:'research',id:state.id,label:state.title};
}
function uiComposer(active){
  const subject=uiCurrentSubject();
  let original=renderRoadmapComposer(active).replace('이 지점에서 개입하기','질문·조건·관측 추가').replace('관측이나 아이디어로 방향을 바꿀 수 있어요.','새로 추가할 내용의 대상과 종류를 확인하세요.').replace('data-action="roadmap-send"','data-action="ui-send-preview"').replace(/(data-action="ui-send-preview"[^>]*?)disabled/g,'$1').replace('>보내기</button>','>초안 확인</button>');
  if(!status.gateway.available)original=`<section class="research-composer roadmap-composer"><label class="input-label" for="message">현재 대상에 질문하기</label><textarea id="message" placeholder="질문, 확인할 조건 또는 새로 관측한 내용을 적으세요.">${esc(draft)}</textarea><div class="roadmap-input-tools"><select id="input-kind" aria-label="추가 내용 종류">${[['message','질문·아이디어'],['observation','새 관측'],['correction','조건·해석 정정']].map(([v,label])=>`<option value="${v}" ${inputKind===v?'selected':''}>${label}</option>`).join('')}</select><div class="actions">${button('ui-send-preview','초안 확인','','primary small')}</div></div><p class="small muted">로컬 초안 · 연구에 저장하거나 실행하기 전입니다.</p></section>`;
  if(!status.gateway.available&&((state.explanations??[]).length||(state.jobs??[]).some(j=>j.kind==='explanation')))original+=`<details class="roadmap-help" data-detail-key="explain-question"><summary>저장된 연구 설명 보기</summary>${renderLiveInteraction()}</details>`;
  return `<div class="ui-composer-context"><span>입력 대상</span><strong>${esc(subject.kind==='check'&&state.decision?.research_loop?.next_checks?.find(c=>c.id===subject.id)?uiExperimentAlias(state.decision.research_loop.next_checks.find(c=>c.id===subject.id)):roadmapSummary(researcherWording(subject.label),64))}</strong><details><summary>연결 ID 확인</summary><code>${esc(subject.id)}</code></details>${subject.kind==='check'&&status.gateway.available?button('check-feedback','이 실험의 관측·정정 연결',`data-check="${esc(subject.id)}"`,'small'):subject.kind!=='research'?button('ui-subject-clear','연구 전체로 변경','','small'):''}</div>${original}`;
}
function uiPreparedInput(){
  const subject=uiCurrentSubject(),body=draft.trim();
  return subject.kind==='research'?body:`[연결 대상: ${researcherWording(subject.label)}]\n[기록 ID: ${subject.id}]\n${body}`;
}
function workspaceAfterRender(){
  document.body.classList.toggle('ui-rail-collapsed',researchRailCollapsed);
  document.body.classList.toggle('ui-reading',!!currentReader());
  document.body.classList.toggle('ui-workspace-wide',workspaceWide);
  document.body.classList.toggle('ui-conversation-open',conversationOpen);
  const panel=currentReader(),body=document.querySelector('#research-reader-body');
  renderedResearchPanel=panel;
  if(panel&&body){body.scrollTop=panel.scroll??0;for(const [i,node] of [...body.querySelectorAll('details')].entries())if(panel.openDetails?.includes(i))node.open=true}
  const mobile=matchMedia('(max-width: 1100px)').matches&&!!panel;
  for(const node of document.querySelectorAll('#workspace-content,.rail,.ui-stage-nav,.ui-workspace-heading,.ui-conversation'))node.inert=mobile;
  const conversationModal=matchMedia('(max-width:850px)').matches&&conversationOpen&&!panel;
  for(const node of document.querySelectorAll('.topbar,.ui-work-product'))node.inert=conversationModal;
  if(conversationModal)for(const node of document.querySelectorAll('.rail,.ui-workspace-heading'))node.inert=true;
  const conversation=document.querySelector('.ui-conversation');if(conversation){conversation.setAttribute('role',conversationModal?'dialog':'complementary');if(conversationModal)conversation.setAttribute('aria-modal','true')}
  const reader=document.querySelector('#research-reader');if(reader){reader.setAttribute('role',mobile?'dialog':'region');if(mobile)reader.setAttribute('aria-modal','true')}
  fitResearchReader();
}
function fitResearchReader(){const node=document.querySelector('#research-reader');if(!node)return;if(matchMedia('(max-width:1100px)').matches){node.style.height='';return}const top=Math.max(16,node.getBoundingClientRect().top);node.style.height=`${Math.max(200,innerHeight-top-16)}px`}
window.addEventListener('scroll',fitResearchReader,{passive:true});
async function workspaceAction(action,node){
  if(action.startsWith('path-')){await pathAction(action,node);return true}
  if(action==='discovery-detail'){await uiOpenCandidate(node.dataset.id);return true}
  if(action==='source'&&state){await uiOpenSource(node.dataset.id,{offset:node.dataset.sourceOffset===undefined?undefined:Number(node.dataset.sourceOffset),quote:node.dataset.sourceQuote});return true}
  if(action==='show-check'){researchSubjects.delete(state.id);experimentSelections.set(state.id,node.dataset.check);closeResearchPanel();tab='research';roadmapSelections.set(state.id,'next');render();return true}
  if(!action.startsWith('ui-'))return false;
  if(action==='ui-pin-research'){if(toggleResearchPin(node.dataset.id)){const id=node.dataset.id;render();[...document.querySelectorAll('[data-action="ui-pin-research"]')].find(n=>n.dataset.id===id)?.focus()}return true}
  if(action==='ui-history-return'){const previous=currentReader()?.historyContext;if(previous){closeResearchPanel();await openEvidenceHistory(previous.hypothesisId,previous.offset)}return true}
  if(action==='ui-stage'){
    const stage=node.dataset.stage;uiExperimentReturns.delete(state.id);researchSubjects.delete(state.id);researchReaders.delete(state.id);++readerRequest;
    tab=['data','history'].includes(stage)?stage:'research';roadmapSelections.set(state.id,tab==='research'?(stage||null):null);render();window.scrollTo(0,0);rememberWorkspaceView();document.querySelector('#roadmap-inspector')?.focus({preventScroll:true});return true;
  }
  if(action==='ui-wide'){workspaceWide=!workspaceWide;conversationOpen=false;render();return true}
  if(action==='ui-question'){conversationOpen=true;workspaceWide=false;render();document.querySelector('#message')?.focus();return true}
  if(action==='ui-question-close'){conversationOpen=false;render();document.querySelector('[data-action="ui-question"]')?.focus();return true}
  if(action==='ui-outcome'){outcomeSelections.set(node.dataset.key,Number(node.dataset.index));render();document.querySelector(`[data-action="ui-outcome"][data-index="${node.dataset.index}"]`)?.focus({preventScroll:true});return true}
  if(action==='ui-rail'){researchRailCollapsed=!researchRailCollapsed;render();return true}
  if(action==='ui-research-mode'){researchListMode=node.dataset.mode;render();return true}
  if(action==='ui-reader-close'||action==='ui-reader-back'){closeResearchPanel(action==='ui-reader-back');return true}
  if(action==='ui-judgment'){await openResearchPanel({kind:'judgment',title:'판단 전체와 근거',subject:{kind:'research',id:state.id,label:state.title},body:`<h3>판단 원문</h3><p>${uiText(state.decision.recommendation)}</p><h3>판단 이유</h3><p>${uiText(state.decision.reason)}</p>${sourceLinks(state.decision.evidence_refs)}${questions(state.decision.questions)}`});return true}
  if(action==='ui-candidate-view'){candidateViews.set(state.id,node.dataset.view);if(node.dataset.view==='all'){optionsOpen=true;optionsStage='candidates';optionsOffset=0;optionsKind='';optionsPage=null;render();await loadOptions()}else render();return true}
  if(action==='ui-candidate-tab'){readerSnapshot();Object.assign(currentReader(),{section:node.dataset.section,scroll:0,openDetails:[]});render();return true}
  if(action==='ui-generated-group'){await uiLoadGeneration(node.dataset.id);await openResearchPanel({kind:'generated-group',id:node.dataset.id,title:'같은 생성 집합',subject:uiCurrentSubject()});return true}
  if(action==='ui-candidate-return'){const saved=uiExperimentReturns.get(state.id);if(saved?.rev===state.rev){researchReaders.set(state.id,saved.reader);tab=saved.tab;roadmapSelections.set(state.id,saved.stage);render()}uiExperimentReturns.delete(state.id);return true}
  if(['ui-experiment','ui-related-experiment','ui-overview-experiment'].includes(action)){researchSubjects.delete(state.id);experimentSelections.set(state.id,node.dataset.id);if(action!=='ui-experiment'){if(action==='ui-related-experiment'){readerSnapshot();uiExperimentReturns.set(state.id,{reader:readerState(),rev:state.rev,tab,stage:roadmapChosen()})}researchReaders.delete(state.id);tab='research';roadmapSelections.set(state.id,'next')}render();return true}
  if(action==='ui-subject'){conversationOpen=true;workspaceWide=false;researchSubjects.set(state.id,{kind:node.dataset.kind,id:node.dataset.id,label:node.dataset.label});closeResearchPanel();render();document.querySelector('#message')?.focus();return true}
  if(action==='ui-subject-clear'){researchSubjects.set(state.id,{kind:'research',id:state.id,label:state.title});render();return true}
  if(action==='ui-source-page'){
    const p=currentReader(),next=Number(node.dataset.offset),wid=state.id,token=++readerRequest;
    if(!p||p.kind!=='source'||!Number.isInteger(next)||next<0)return true;
    const value=await api(`/api/workspaces/${wid}/artifacts/${p.id}?offset=${next}&limit=30`);
    if(state?.id===wid&&token===readerRequest&&currentReader()===p){Object.assign(p,{value,offset:next,scroll:0,openDetails:[]});render()}return true;
  }
  if(action==='ui-source-row'){const p=currentReader(),r=p?.value?.result,row=r?.rows?.[Number(node.dataset.index)];if(row!==undefined)await openResearchPanel({kind:'row',id:p.id,title:'원행의 전체 값',subject:p.subject,body:json(r.header?{header:r.header,row}:row)});return true}
  if(action==='ui-full-source'){researchReaders.delete(state.id);await chooseArtifact(node.dataset.id);return true}
  if(action==='ui-send-preview'){
    if(!draft.trim()){notice('추가할 내용을 입력해 주세요.');return true}
    const subject=uiCurrentSubject();
    if(!status.gateway.available){await openResearchPanel({kind:'local-draft',id:subject.id,title:'질문 초안',subject,body:`<h3>로컬 초안 · 저장·실행 전</h3><p>종류: ${esc(({message:'질문·아이디어',observation:'새 관측',correction:'조건·해석 정정'})[inputKind])}</p><p class="prose">${esc(uiPreparedInput())}</p><p class="small muted">이 미리보기에서는 연구 기록을 바꾸거나 모델을 실행하지 않습니다. 닫으면 입력으로 돌아갑니다.</p>`});return true}
    if(subject.kind==='check'&&['observation','correction'].includes(inputKind)){openResearchFeedback(subject.id,null);document.querySelector('#feedback-text').value=draft;document.querySelector('#feedback-kind').value=inputKind;return true}
    const prepared=uiPreparedInput();await openResearchPanel({kind:'input-preview',id:subject.id,title:'보내기 전에 확인',subject,prepared,originalDraft:draft,inputKind,sendMode,body:`<h3>저장할 내용</h3><p class="prose">${esc(prepared)}</p><p>종류: ${esc(({message:'질문·아이디어',observation:'새 관측',correction:'조건·해석 정정'})[inputKind])}</p><p>${sendMode==='record'?'기록만 저장합니다.':'자료와 연결된 도구를 사용해 검토합니다.'}</p>${button('ui-send-confirm','확인하고 보내기','','primary small')}`});return true;
  }
  if(action==='ui-send-confirm'){
    const panel=currentReader();if(!panel||panel.kind!=='input-preview'||panel.rev!==state.rev||panel.originalDraft!==draft||panel.inputKind!==inputKind||panel.sendMode!==sendMode)throw Error('입력 또는 연구 조건이 바뀌었습니다. 보낼 내용을 다시 확인해 주세요.');
    draft=panel.prepared;evidaStorage.setItem(draftKey(),draft);researchReaders.delete(state.id);await roadmapAction('roadmap-send',node);return true;
  }
  return true;
}
document.addEventListener('input',event=>{if(event.target.id==='research-search'){researchSearch=event.target.value;render()}});
document.addEventListener('keydown',event=>{
  if(!currentReader()&&conversationOpen&&matchMedia('(max-width:850px)').matches&&!dialog.open){
    if(event.key==='Escape'){event.preventDefault();conversationOpen=false;render();document.querySelector('[data-action="ui-question"]')?.focus();return}
    if(event.key==='Tab'){const nodes=[...document.querySelectorAll('.ui-conversation button:not([disabled]),.ui-conversation a[href],.ui-conversation textarea,.ui-conversation select,.ui-conversation summary')].filter(n=>n.getClientRects().length),first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}}
    return;
  }
  if(!currentReader()||dialog.open)return;
  if(event.key==='Escape'){event.preventDefault();closeResearchPanel(currentReader()?.kind==='source'&&readerState().stack.length>1);return}
  if(event.key==='Tab'&&matchMedia('(max-width: 1100px)').matches){const nodes=[...document.querySelectorAll('#research-reader button:not([disabled]),#research-reader a[href],#research-reader input,#research-reader select,#research-reader textarea,#research-reader summary')].filter(n=>n.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&(document.activeElement===first||document.activeElement.id==='research-reader-title')){event.preventDefault();last?.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}}
});
window.addEventListener('resize',()=>{if(typeof state!=='undefined'&&state)workspaceAfterRender()});
window.addEventListener('popstate',event=>{
  if(typeof state==='undefined'||!state)return;
  readerSnapshot();
  const key=event.state?.evida_reader,frame=key?.workspace===state.id&&readerHistoryFrames.get(key.token);
  const view=event.state?.evida_view;
  ++readerRequest;
  if(frame){frame.reader.stack=[...frame.stack];researchReaders.set(state.id,frame.reader);tab=frame.tab;roadmapSelections.set(state.id,frame.stage);render();requestAnimationFrame(()=>document.querySelector('#research-reader-title')?.focus({preventScroll:true}))}
  else if(view?.workspace===state.id){
    const reader=readerState();researchReaders.delete(state.id);tab=view.tab;roadmapSelections.set(state.id,view.stage);render();
    requestAnimationFrame(()=>{window.scrollTo(0,reader?.pageScroll??view.scroll??0);restoreReaderOpener(reader?.opener??view.opener)});
  }else if(readerState())closeResearchPanel(false,true);
});
