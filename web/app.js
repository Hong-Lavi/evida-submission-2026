const app = document.querySelector('#app');
const dialog = document.querySelector('#editor');
let status, projects = [], state = null, tab = 'research', selected = null, detail = null;
let offset = 0, query = '', busy = false, noticeTimer, draft = '', inputKind = 'message', syntheticDraft = false;
let intentEditBase = null;
let projectLoadVersion = 0;
const labels = {tool_reading:'확인한 원문·결과',public_method_background:'공개 방법 배경',source_visual_review:'원문 시각 검토',rna_seed_analysis:'RNA seed 분포 분석',rna_seed_reference:'RNA 참조 전사체',rna_guide:'출처가 확인된 RNA 서열',repository_document:'공개 자료 설명',protocol_snapshot:'판단 생성 방식',article:'공개 원문',entity_search:'표적·질환 후보',rna_gene_review:'RNA 유전자 관측 대조',evidence_view:'확인한 자료 범위',research_check:'후속 연구 확인',molecule_csv:'후보 원자료',rna_table:'RNA 원자료',rdkit:'계산 물성',admet:'모델 예측',rna_observations:'관측 검토',open_targets:'공개 표적 속성',literature:'문헌 검색',model_receipt:'모델 실행 기록',decision_proposal:'판단 제안'};
labels.rna_method_review = 'RNA 실제 방법 비교';
Object.assign(labels,{explanation:'저장된 판단 설명',explanation_context:'설명 기준',explanation_answer:'질문에 대한 설명',explanation_model_output:'설명 응답 기록',explanation_reading:'설명에 사용한 원문'});
Object.assign(labels,SCIENCE_LABELS);
labels.rna_seed_sensitivity = 'RNA 참조·발현 민감도';
const jobLabels = {queued:'대기',running:'실행 중',succeeded:'완료',reused:'기존 계산 재사용',failed:'실패',partial:'일부 반환',interrupted:'중단 기록',stale:'이전 조건의 작업',paused:'추가 실행 가능',refused:'서비스 응답 거절',input_missing:'입력 필요',outcome_unknown:'완료 여부 미확인',quota_or_rate_limit:'서비스 한도',identity_unverified:'모델 확인 필요'};
const eventLabels = {reading_focus_set:'현재 질문의 자료 선택',research_check_requested:'다음 확인 실행',research_check_review_pending:'확인 결과의 해석 대기',created:'연구 시작',message:'연구 요청',correction:'조건 정정',observation:'새 관측',intent_edit:'연구자의 의도 수정',artifact_added:'자료 저장',job_queued:'작업 요청',job_started:'작업 실행',job_finished:'실행 결과',work_framed:'의도와 작업 분해',decision_published:'판단 갱신',decision_stale:'이전 조건의 판단 보존',job_interrupted:'중단된 작업 보존',source_import_failed:'공개 자료 수신 오류'};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => value === null || value === undefined ? '—' : typeof value === 'number' ? (value!==0&&(Math.abs(value)<0.0001||Math.abs(value)>=1e8) ? value.toExponential(4) : Number.isInteger(value) ? value.toLocaleString('ko-KR') : value.toLocaleString('ko-KR',{maximumSignificantDigits:5})) : esc(value);
const button = (action, text, extra = '', klass = '') => `<button type="button" class="${klass}" data-action="${action}" ${extra}>${text}</button>`;
const list = values => values?.length ? `<ul class="list">${values.map(v=>`<li>${esc(v)}</li>`).join('')}</ul>` : '';
const json = value => `<pre class="raw">${esc(JSON.stringify(value,null,2))}</pre>`;
const time = value => new Date(value).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'});
Object.assign(labels,{chemical_sirna_evidence:'수식 siRNA 원자료',research_evidence:'시험·원전 조건 검토'});
const artifactName = id => {const a=state?.artifacts.find(a=>a.id===id.split('#')[0]);if(!a)return id;if(a.kind==='decision_proposal'&&typeof uiDecisionRecord==='function')return uiDecisionRecord(a.id)?.title??'게시 전 판단 제안';if(a.kind==='article'&&typeof a.source_title==='string'&&a.source_title.trim())return a.source_title;if(a.kind==='clinical_trial'&&a.meta.summary?.title)return a.meta.summary.title;if(a.kind==='gtopdb_pharmacology'&&a.meta.summary?.gene_symbol)return a.meta.summary.gene_symbol+' · '+a.title;if(a.kind==='target_context'&&a.meta.summary?.symbol)return `${a.meta.summary.symbol} · ${a.title}`;if(['rna_reference','rna_reference_archive'].includes(a.kind)&&a.meta.arguments?.ensembl_id)return `${a.title} · ${a.meta.arguments.ensembl_id}`;if(a.kind==='tool_reading'){const source=state.artifacts.find(x=>x.id===a.meta.source_artifact_id);return source?`${artifactName(source.id)} · 확인한 부분`:'확인한 원문·결과';}return a.title;};
const inputContext = a => a.meta.contrast ?? state?.artifacts.find(i=>i.id===a.meta.consumed_artifacts?.[0])?.meta.contrast;
function notice(message){clearTimeout(noticeTimer);const n=document.querySelector('#notice');n.textContent=message;n.classList.add('visible');noticeTimer=setTimeout(()=>n.classList.remove('visible'),7000)}
async function api(path,body){const response=await fetch(deploymentURL(path),{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Evida-Request':'1'}:{},body:body?JSON.stringify(body):undefined});const data=await response.json();if(!response.ok)throw Error(data.error||'요청을 완료하지 못했습니다.');return data}
let gatewayStatusPending=null;
function gatewayDisplayState(value){const g=value?.gateway??{};return JSON.stringify([g.available,g.message,g.requested_model,g.requested_effort,g.approved_models,value?.read_only_preview])}
async function refreshGatewayStatus({force=false,renderChanges=true}={}){
 if(gatewayStatusPending){if(!force)return gatewayStatusPending;await gatewayStatusPending}
 const pending=(async()=>{
  const before=gatewayDisplayState(status);
  try{
   const response=await fetch(deploymentURL('/api/status'),{cache:'no-store',signal:AbortSignal.timeout(5000)}),fresh=await response.json();
   if(!response.ok||typeof fresh.gateway?.available!=='boolean')throw Error('모델 연결 상태 확인 실패');
   status=fresh;
  }catch{
   status={...status,gateway:{...status?.gateway,available:false,message:'모델 연결 상태를 확인하지 못했습니다. 입력 초안은 유지됩니다.'}};
  }
  if(renderChanges&&before!==gatewayDisplayState(status)&&!busy)render();
  return status.gateway.available===true;
 })();
 gatewayStatusPending=pending;
 try{return await pending}finally{if(gatewayStatusPending===pending)gatewayStatusPending=null}
}
function checkGatewayWhenVisible(){if(status&&!document.hidden&&!busy)refreshGatewayStatus().catch(()=>{})}
window.addEventListener('focus',checkGatewayWhenVisible);
document.addEventListener('visibilitychange',checkGatewayWhenVisible);
Object.assign(labels,{literature_compounds:'문헌 후보의 공식 구조',structure_search:'표적의 실험 구조 목록',compound_candidates:'공개 화합물 후보',compound_selection:'계산할 후보 선정',discovery_review:'선택지 검토'});
function sourceLinks(refs){return refs?.length?`<div class="source-links">${refs.map(ref=>button('source',esc(sourceDisplayLabel(state.artifacts.find(a=>a.id===ref.split('#')[0]))),`data-id="${esc(ref)}"`,'link-button')).join('')}</div>`:''}
function draftKey(){return `evida-draft-${state?.id??'new'}`}
function latestFrame(){return state?.events.filter(e=>e.kind==='work_framed'&&e.body.based_rev===state.rev).at(-1)?.body}
function latestIntentEdit(){return state?.events.filter(e=>e.kind==='intent_edit').at(-1)?.body}
function editableIntents(){if(state?.intent.length||latestIntentEdit())return state.intent;return latestFrame()?.intent_records??state?.decision?.intent_records??[]}
function intents(){
 if(state?.decision_rev===state?.rev)return state?.intent??[];
 const records=latestFrame()?.intent_records??editableIntents(),edit=latestIntentEdit();
 const merged=new Map(records.map(r=>[r.id,r]));
 if(edit){
  const protectedIds=new Set(edit.protected_ids??edit.records.map(r=>r.id));
  for(const r of state.intent)if(protectedIds.has(r.id))merged.set(r.id,r);
  for(const id of edit.deleted_ids??[])merged.delete(id);
 }
 return [...merged.values()];
}
// Preserve the reader's expanded panels during progress refreshes. This is
// presentation state only; it cannot change research, source data or decisions.
const detailPanelStates = new Map();
let lastRenderedView = null;
function detailPanelKeys(){
  const counts=new Map();
  return [...app.querySelectorAll('details')].map(node=>{
    const titles=[];
    for(let p=node;p&&p!==app;p=p.parentElement){
      if(p.tagName==='DETAILS')titles.unshift(p.dataset.detailKey?'key:'+p.dataset.detailKey:p.querySelector(':scope > summary')?.textContent.trim()??'');
      if(p.dataset?.researchCheck)titles.unshift('check:'+p.dataset.researchCheck);
    }
    const base=JSON.stringify(titles),n=counts.get(base)??0;counts.set(base,n+1);
    return [base+':'+n,node];
  });
}
function previewReadOnly(){return EVIDA_BASE==='/preview'||status?.read_only_preview===true}
function renderPreviewNotice(){if(!previewReadOnly())return '';const url=location.origin+'/?'+new URLSearchParams(state?{workspace:state.id}:{});return `<aside class="ui-preview-notice" aria-label="미리보기 안내"><span>읽기 전용 미리보기 · 저장·실행 없음</span><a href="${esc(url)}" target="_blank" rel="noopener">운영 연구 열기 ↗</a></aside>`}
function render(){
  readerSnapshot();
  queueMicrotask(()=>loadRoadmapHistory());
  if(lastRenderedView)detailPanelStates.set(lastRenderedView,new Map(detailPanelKeys().map(([key,node])=>[key,node.open])));
  const focused=document.activeElement?.id, start=document.activeElement?.selectionStart;
  const active=state?.jobs.some(j=>['running','queued'].includes(j.status));
  app.innerHTML=deploymentHTML(`<div class="shell"><aside class="rail">${renderResearchRail()}</aside>
    <div class="main-shell"><header class="topbar"><div class="breadcrumb"><span>워크스페이스</span><span>/</span><strong>${esc(state?.title??'새 연구')}</strong></div><div class="top-actions">${previewReadOnly()||status.gateway.available?'':`<span class="gateway-warning" role="status">${esc(status.gateway.message??'모델 연결 확인 필요')}</span>`}${modelAccessButton()}${button('usage-help','도움말','','quiet small')}${state?button('tab','변경 기록',`data-id="history"`,'quiet small'):''}<span class="saved">${active?'작업 실행 중':state?'저장됨 · 연구 기록 '+state.rev:'연구 준비'}</span>${state?button('export','기록 내보내기','','small'):''}</div></header>
    <main class="page" id="main">${renderPreviewNotice()}${submitPhase?`<p class="submitting" role="status">${esc(submitPhase)}</p>`:''}${actionError?`<p class="action-error" role="alert">${esc(actionError)}</p>`:''}${state?teamGuide():''}${state?workspace():welcome()}</main></div></div>`);
  lastRenderedView=JSON.stringify([state?.id??'new',tab,tab==='data'?selected:null]);
  const panelStates=detailPanelStates.get(lastRenderedView);
  if(panelStates)for(const [key,node] of detailPanelKeys())if(panelStates.has(key))node.open=panelStates.get(key);
  if(!state&&intakeFile){const input=document.getElementById('intake-file');if(input){const transfer=new DataTransfer();transfer.items.add(intakeFile);input.files=transfer.files;}}
  if(focused){const target=document.getElementById(focused);if(target){target.focus({preventScroll:true});if(typeof start==='number'&&target.setSelectionRange)try{target.setSelectionRange(start,start)}catch{}}}
  workspaceAfterRender();
  semanticAfterRender();
}
function welcome(){return renderGoalWelcome()}
// Two tabs, not four. The research stages are what a researcher reads; everything retrieved or
// computed is one "자료" tab, with the tool-by-tool workbench a drawer inside it rather than a
// separate destination. The change log is a button in the top bar and appears as a tab only while
// it is open, so there is a way back without a permanent fourth tab.
function workspace(){return renderDecisionWorkspace()}
function research(){return renderRoadmapResearch()}
function questions(items){return items?.length?`<div class="questions">${items.map(q=>`<div class="question"><strong class="small">${esc(q.question)}</strong><small>${esc(q.affects)}</small></div>`).join('')}</div>`:''}
function quotaNotice(){return state.quota_resume?`<section class="notice-inline"><p>서비스 한도로 중단됐습니다. 완료한 조회는 저장돼 있습니다.</p>${button('resume-planner','중단한 판단 이어가기',`data-id="${esc(state.quota_resume.source_job)}" ${busy?'disabled':''}`,'small')}</section>`:''}
function jobsPanel(){return state.jobs.length?`<section class="panel"><h2>실행 기록</h2><div class="jobs">${state.jobs.slice(-6).reverse().map(j=>`<div><div class="job"><span class="job-name">${esc(j.kind==='planner'?'근거 검토와 판단':labels[j.kind]??j.kind)}</span><span class="status-word ${j.status}">${esc(jobStatus(j))}</span></div>${j.error?`<p class="job-error">${esc(j.error)}</p>`:''}</div>`).join('')}</div></section>`:''}
function dataView(){const artifacts=state.artifacts.filter(a=>!['model_receipt','decision_proposal','research_notes','tool_reading','protocol_snapshot','explanation_context','explanation_answer','explanation_model_output','explanation_reading'].includes(a.kind)&&(!query||[a.title,a.meta.arguments?.ensembl_id??''].join(' ').toLowerCase().includes(query.toLowerCase())));return `<div class="data-toolbar"><input id="artifact-search" type="text" placeholder="자료 이름으로 찾기" value="${esc(query)}" aria-label="자료 검색">${button('upload','＋ 자료 추가')}</div><div class="data-layout ${selected?'has-selection':''}"><div><div class="artifact-list">${artifacts.map(a=>button('source',`<span class="artifact-title">${esc(artifactName(a.id))}${inputContext(a)?`<span class="muted"> · ${esc(inputContext(a).candidate_label)} / ${esc(inputContext(a).cohort)}</span>`:''}</span><span class="artifact-meta"><span>${esc(labels[a.kind]??a.kind)}</span><span>${a.meta.result_status?esc(jobLabels[a.meta.result_status]??a.meta.result_status):'원자료'}</span></span>`,`data-id="${a.id}"`,`artifact ${selected===a.id?'active':''}`)).join('')||'<div class="panel empty">아직 연결된 자료가 없습니다.</div>'}</div><div class="rule"></div><details class="tool-drawer" data-detail-key="direct-lookup"><summary>직접 조회 · 도구 실행<small>필요할 때만 엽니다. 평소에는 연구 탭의 단계가 필요한 조회를 스스로 합니다.</small></summary><section class="panel"><h3>공개 문헌 찾기</h3><div class="tool-form"><label>과학 질문<input type="text" id="literature-query" placeholder="표적, 기전, 관측…"></label>${button('literature','검색',busy?'disabled':'')}</div><p class="limit">Europe PMC 문헌·초록을 조회합니다.</p></section><section class="panel"><h3>표적 속성 조회</h3><div class="tool-form"><label>인간 Ensembl ID<input type="text" id="target-id" placeholder="ENSG…"></label>${button('target','조회',busy?'disabled':'')}</div><p class="limit">Open Targets의 표적 수준 속성입니다.</p></section>${renderScienceWorkbench()}</details></div><div class="data-detail">${selected?artifactDetail():'<section class="panel empty"><strong>검토할 자료를 선택하세요.</strong>원자료를 보존한 상태에서 계산하거나 출처와 관측을 확인합니다.</section>'}</div></div>`}
function artifactDetail(){const a=state.artifacts.find(a=>a.id===selected);if(!a)return '';if(!detail||detail.artifact_id!==selected)return '<section class="panel">자료를 읽고 있습니다.</section>';const result=detail.result;const handledLimits=['target_context','gtopdb_pharmacology'].includes(a.kind)||result?.view_kind==='article_references';const total=result?.retained_total_rows??result?.panel_total_rows??result?.total_rows??result?.rows?.length;const capability=status.capabilities.find(c=>c.input_kind===a.kind&&['rdkit','admet','rna_observations','rna_weighted_distribution'].includes(c.id));return `<section class="panel"><div class="section-mark">${esc(labels[a.kind]??a.kind)}</div><h2>${esc(artifactName(a.id))}</h2><div class="source-summary"><span>${a.meta.source_mode==='public_download'?'공개 원자료 수신':a.meta.source_mode==='researcher_upload'?'연구자 업로드':a.meta.result_status?'실제 도구 실행':'보존 자료'}</span><span>${new Date(a.created).toLocaleString('ko-KR')}</span>${total!==undefined?`<span>${number(total)}행 보존</span>`:''}${result?.content_coverage?`<span>${result.content_coverage.scope==='body_available'?'본문 XML 포함':result.content_coverage.scope==='abstract_only'?'초록만 수신 · 본문 미반환':'본문 미반환'}</span>`:''}</div><div class="detail-actions">${capability?button('tool',capability.id==='rdkit'?'물성 계산':capability.id==='admet'?'ADMET 예측':capability.id==='rna_weighted_distribution'?'평균·분포 계산':'관측 검토',`data-tool="${capability.id}" data-id="${a.id}" ${busy?'disabled':''}`,'primary small'):''}${button('download','원본·전체 결과 내려받기',`data-id="${a.id}"`,'small')}</div>
 ${result?.error?`<div class="notice-inline">${esc(result.error)}</div>`:''}${result?.contrast?`<p class="small muted">${esc(result.contrast.candidate_label)} · ${esc(result.contrast.cohort)} · ${esc(result.context)}</p>`:''}${!handledLimits&&a.kind!=='rna_candidate_space'&&result?.limits?.[0]?`<p class="limit">${esc(result.limits[0])}</p>`:''}${a.kind==='rna_seed_analysis'?seedSummary(result):''}${a.kind==='source_image'?`<img class="source-original-image" alt="${esc(a.title)}" src="/api/workspaces/${state.id}/artifacts/${a.id}?image=1"><p class="limit">공개 원 이미지입니다. 자동 판독이나 새 실험 결과가 아닙니다.</p>`:a.kind==='public_lookup_bundle'?publicLookupBundleView(result):a.kind==='compound_selection'?compoundSelectionView(result):a.kind==='research_evidence'?researchEvidenceView(result):a.kind==='chemical_sirna_evidence'?chemicalSourceView(result):a.kind==='discovery_review'?reviewRecordView(result,a.meta):a.kind==='tool_reading'?readingSnapshotView(result):a.kind==='source_visual_review'&&result?.rows?sourceVisualReviewView(result):a.kind==='article'&&result?.rows?articleView(result):a.kind==='repository_document'&&result?.rows?repositoryDocumentView(result):result?.rows?renderTable(result,a.kind):result?.response?.data?.target?targetTable(result.response.data.target):detail.preview?`<p class="limit">원자료 앞부분입니다. 계산 결과가 아닙니다.</p><pre class="raw">${esc(detail.preview)}</pre>`:result?json(result):''}
 ${handledLimits?'':['rna_candidate_space','rna_duplex','rna_duplex_seed','rna_duplex_transcriptome','rna_delivery_response'].includes(a.kind)?`<details class="meta-details"><summary>계산 범위와 아직 확인하지 않은 조건</summary>${(result?.limits??[]).map(l=>`<p class="limit">${esc(l)}</p>`).join('')}</details>`:(result?.limits??a.meta.limits??[]).map(l=>`<p class="limit">${esc(l)}</p>`).join('')}
 ${a.meta.consumed_artifacts?.length?sourceLinks(a.meta.consumed_artifacts):''}
 <details class="meta-details"><summary>출처·조건·도구 버전</summary>${a.meta.source?.url?`<p class="limit"><a href="${esc(safeUrl(a.meta.source.url))}" target="_blank" rel="noopener noreferrer">공개 원자료 열기 ↗</a></p>`:''}${json(a.meta)}${result?.endpoint_metadata?json({endpoint_metadata:result.endpoint_metadata,versions:result.versions}):''}${result?.columns?json({columns:result.columns,versions:result.versions}):''}<p class="mono">SHA256 ${esc(a.sha256)}</p></details></section>`}
function seedSummary(result){const summary=result.summary;if(!summary)return '';return `<div class="source-summary"><span>참조 대응 ${number(summary.mapped_genes)}개</span><span>미대응 ${number(summary.unmapped_genes)}개</span><span>분포 비교 ${number(summary.distribution_eligible_genes)}개</span></div><p class="small muted">${esc(result.reference?.assembly)} · Ensembl ${esc(result.reference?.annotation_release)} · 기존 처리표에서 계산한 seed 일치군의 발현 변화</p><div class="table-scroll"><table><thead><tr><th>seed</th><th>일치군 / 배경군</th><th>log₂ FC 중앙값 · 일치군 / 배경군</th><th>KS 통계량</th><th>Holm 조정 p-value</th></tr></thead><tbody>${(summary.tests??[]).map(t=>`<tr><td>${esc(t.seed)}</td><td>${number(t.target_genes)} / ${number(t.background_genes)}</td><td>${number(t.target_median)} / ${number(t.background_median)}</td><td>${number(t.statistic)}</td><td>${number(t.pvalue_holm_two_seed_family)}</td></tr>`).join('')}</tbody></table></div><p class="limit">집단 분포의 비교이며 개별 유전자의 off-target이나 인과 기전을 입증하지 않습니다. 원행의 미대응·결측과 참조 선택 조건을 함께 확인하세요.</p>`}
function safeUrl(value){try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)?url.href:'#'}catch{return '#'}}
function targetTable(t){return `<h3>${esc(t.approvedSymbol)} · ${esc(t.approvedName)}</h3>${button('science-target-context-source','이 표적의 유전·안전성 조건 확인',`data-target-id="${esc(t.id)}"`,'small')}<div class="table-scroll"><table><thead><tr><th>평가 항목</th><th>접근 분류</th><th>DB 반환값</th></tr></thead><tbody>${t.tractability.map(r=>`<tr><td>${esc(r.label)}</td><td>${esc(r.modality)}</td><td>${r.value===true?'true':r.value===false?'false':'미확인'}</td></tr>`).join('')}</tbody></table></div>`}
function admetPredictionCell(row,endpoint,result){
 const flag=(result.prediction_domain_check?.flags??[]).find(f=>f.row_id===row.row_id&&f.endpoint===endpoint);
 return `${number(row.predictions?.[endpoint])}${flag?'<br><span class="limit">정의 범위 밖 · 수치 해석 보류</span>':''}`;
}
function admetEndpointTable(result){
 const rows=result.rows??[], endpoints=[...new Set(rows.flatMap(r=>Object.keys(r.predictions??{})))];
 if(!endpoints.length)return '<p class="limit">이번 범위에 반환된 예측값이 없습니다. 계산 상태와 원행의 사유를 확인하세요.</p>';
 const metadata=new Map((Array.isArray(result.endpoint_metadata)?result.endpoint_metadata:[]).map(m=>[m.id,m]));
 return `<details class="meta-details admet-endpoints"><summary>전체 예측 항목 ${number(endpoints.length)}개 비교${result.prediction_domain_check?.flags.length?` · 범위 확인 ${number(result.prediction_domain_check.flags.length)}건`:""}</summary><p class="limit">현재 페이지의 후보를 비교합니다. 좁은 화면에서는 표를 좌우로 밀어 값을 확인하세요. 정의 범위 밖의 값은 원 출력으로 보존하며, 그 값만으로 후보를 배제하지 않습니다. 분류 점수는 환자의 발생 확률이나 확인된 안전성 수치가 아닙니다. 항목마다 의미와 단위가 다르며, 빈 값은 0이 아닌 미반환입니다.</p><div class="table-scroll"><table><thead><tr><th>예측 항목 · 원 정의</th><th>유형 · 단위</th>${rows.map(r=>`<th>${esc(r.candidate_id||r.row_id)}<br><small>${esc(jobLabels[r.status]??r.status)}</small></th>`).join('')}</tr></thead><tbody>${endpoints.map(id=>{const m=metadata.get(id)??{},kind=m.task_type==='classification'?'분류 점수':m.task_type==='regression'?'회귀 예측':'유형 미기록',unit=m.task_type==='classification'?'무단위':m.units&&m.units!=='-'?m.units:'단위 미기록';return `<tr data-endpoint="${esc(id)}"><td><strong>${esc(id)}</strong>${m.name?`<br>${esc(m.name)}`:''}${m.url&&safeUrl(m.url)!=='#'?`<br><a href="${esc(safeUrl(m.url))}" target="_blank" rel="noopener noreferrer">원 항목 정의 ↗</a>`:''}</td><td>${esc(kind)}<br>${esc(unit)}</td>${rows.map(r=>`<td>${admetPredictionCell(r,id,result)}</td>`).join('')}</tr>`}).join('')}</tbody></table></div></details>`;
}
function renderTable(result,kind){const science= scienceTable(result,kind);if(science!==null)return science;const structures=hasDepictions(result)?structureTable(result):'';if(structures)return structures+genericTable(result,kind);return genericTable(result,kind);}
function genericTable(result,kind){if(kind==='rna_weighted_distribution'){return `<div class="table-scroll"><table><thead><tr>${['조건','비교군 수','평균 차이 · log₂ FC','CDF 차이 최댓값','CDF 차이 최솟값','전체 곡선 교차'].map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(r.case)}</td><td>${number(r.target_Q)}</td><td>${number(r.mean_difference)}</td><td>${number(r.maximum_positive_difference)}</td><td>${number(r.minimum_difference)}</td><td>${r.crosses?'있음':'관측되지 않음'}</td></tr>`).join('')}</tbody></table></div><p class="limit">전체 관측값에서 계산했습니다. 평균 감소와 분포 전체의 한쪽 이동은 다릅니다. 유의성·인과성 검정은 아닙니다.</p>`;}if(kind==='rna_method_review')return renderRnaMethodReview(result);if(kind==='rna_seed_sensitivity')return renderRnaSensitivity(result);const rows=result.rows;let headers,fields;if(kind==='rdkit'){headers=['후보','계산 상태','MolWt · g/mol','LogP','TPSA · Å²','QED'];fields=r=>[candidateLabel(r),esc(jobLabels[r.status]??r.status),...['MolWt','LogP','TPSA','QED'].map(k=>number(r.properties?.[k]))]}else if(kind==='admet'){const endpoints=Object.keys(rows.find(r=>r.predictions)?.predictions??{}).slice(0,3);headers=['후보','계산 상태',...endpoints];fields=r=>[candidateLabel(r),esc(jobLabels[r.status]??r.status),...endpoints.map(k=>number(r.predictions?.[k]))]}else if(kind==='rna_observations'){headers=['유전자','이름','log₂ FC','p-value','조정 p-value'];fields=r=>[esc(r.gene_id),esc(r.symbol),number(r.values.log2FoldChange),number(r.values.pvalue),number(r.values.padj)]}else if(kind==='rna_seed_analysis'){headers=['유전자','참조 대응','log₂ FC','7mer-m8','8mer','분포 비교 포함'];fields=r=>[esc(r.symbol||r.gene_id),r.reference_mapping==='mapped'?'대응':'미대응',number(r.values?.log2FoldChange),number(r.seed_counts?.mer7m8),number(r.seed_counts?.mer8),r.distribution_eligible?'포함':'제외 · 사유는 원행 확인']}else if(kind==='molecule_csv'){headers=['후보',...result.header];fields=r=>[esc(r.candidate_id??r.row_id),...r.raw_values.map(esc)]}else if(kind==='rna_gene_review'){headers=['유전자','자료','대응','log₂ FC','조정 p-value'];fields=r=>[esc(r.requested_gene),esc(artifactName(r.input_artifact_id)),r.status==='not_found_in_table'?'행 없음':r.matching_rows>1?`대응 ${r.matching_rows}행`:'원행',number(r.observation?.values.log2FoldChange),number(r.observation?.values.padj)]}else if(kind==='entity_search'){headers=['ID','이름','종류'];fields=r=>[esc(r.id),esc(r.name),esc(r.entity)]}else if(kind==='literature'){headers=['발행','문헌','저자'];fields=r=>[esc(r.pubYear),`<a href="https://europepmc.org/article/${encodeURIComponent(r.source)}/${encodeURIComponent(r.id)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>`,esc(r.authorString)]}else{headers=['항목','내용'];fields=r=>[esc(r.row_id??r.id??''),esc(JSON.stringify(r))]}
 return `<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((r,i)=>`<tr>${fields(r).map((v,j)=>`<td>${j===0?button('row',v,`data-index="${i}"`,'link-button small'):v}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="pagination"><span>${number(result.offset+1)}–${number(result.offset+rows.length)} / ${number(result.total_rows)}행 · 행 이름을 누르면 전체 값 확인</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div>${kind==='admet'?admetEndpointTable(result):''}`}
function historyPanel(){return `<div class="work-grid"><section class="panel"><h2>연구가 바뀐 과정</h2>${[...state.events].reverse().map(e=>`<article class="history-row"><div class="history-time">${time(e.created)}<br><span class="mono">#${e.seq}</span></div><div><h3>${esc(eventLabels[e.kind]??e.kind)}${inputProvenance(e).synthetic||e.effective_provenance?.corrected_by?' · '+esc(inputProvenanceLabel(e)):''}</h3><p>${esc(e.body.text??e.body.title??e.body.current_question??e.body.error??(e.body.status?jobLabels[e.body.status]??e.body.status:''))}</p>${inputProvenanceNotice(e)}${e.body.output_id?sourceLinks([e.body.output_id]):''}<details class="meta-details"><summary>세부 기록</summary>${json(e.body)}</details></div></article>`).join('')}</section><aside>${jobsPanel()}<section class="panel"><h2>기록 보존</h2><p class="small muted">정정 전 원문과 이전 결과도 남습니다. 새 조건을 반영하지 않은 판단은 현재 판단과 구별합니다.</p>${button('export','연구 기록 내보내기','','small')}</section></aside></div>`}
async function loadProject(id){
 if(state)semanticStop(state.id,'다른 연구로 이동했습니다. 시작한 문헌 준비는 원래 연구에서 계속됩니다.');
 const version=++projectLoadVersion,u=new URL(location.href);
 if(u.searchParams.get('workspace')!==id)u.searchParams.delete('guide');
 u.searchParams.set('workspace',id);history.replaceState(null,'',u);
 let fresh;
 try{fresh=await api(`/api/workspaces/${id}`)}catch(error){if(version!==projectLoadVersion)return;throw error}
 if(version!==projectLoadVersion)return;
 tab='research';state=fresh;evidaStorage.setItem('evida-project',id);draft=evidaStorage.getItem(draftKey())??'';
 selected=null;detail=null;offset=0;query='';optionsOffset=0;optionsPage=null;optionsWorkspace=null;
 render();if(optionsOpen)await loadOptions();if(version===projectLoadVersion)window.scrollTo(0,0);
}
async function refresh(){if(!state)return;const wid=state.id;const fresh=await api(`/api/workspaces/${wid}`);if(state?.id!==wid)return;const changed=fresh.event_cursor!==state.event_cursor;state=fresh;if(changed){projects=await api('/api/workspaces');render();if(optionsOpen)await loadOptions()}}
async function chooseArtifact(id){selected=id;offset=0;detail=null;tab='data';render();await readDetail()}
async function openArticleSection(node){articleReferenceModes.delete(selected);const next=Number(node.dataset.offset);if(!Number.isInteger(next)||next<0)return;offset=next;await readDetail();document.querySelector('.data-detail')?.scrollIntoView({block:'start'});}
async function readDetail(){const id=selected,data=await api(`/api/workspaces/${state.id}/artifacts/${id}?offset=${offset}&limit=${state.artifacts.find(a=>a.id===id)?.kind==='rna_delivery_response'?100:30}${candidateSpaceQuery(id)}${rnaContextQuery(id)}${articleReferenceQuery(id)}`);if(id===selected){detail=data;render()}}
async function saveMessage(){if(!draft.trim())return;const body={kind:inputKind,text:draft.trim(),synthetic:syntheticDraft};await api(`/api/workspaces/${state.id}/commands`,{expected_rev:state.rev,command_id:crypto.randomUUID(),body});draft='';syntheticDraft=false;evidaStorage.removeItem(draftKey());await refresh()}
async function runTool(tool,args){const response=await api(`/api/workspaces/${state.id}/jobs`,{expected_rev:state.rev,tool,arguments:args});await refresh();notice('작업을 시작했습니다. 결과와 원자료를 함께 보존합니다.');return response}
function showDialog(title,content){dialog.innerHTML=deploymentHTML(`<div class="dialog-title"><h2 id="editor-title">${esc(title)}</h2>${button('close-dialog','닫기','','quiet small')}</div>${content}`);dialog.showModal()}
function editIntents(){const records=structuredClone(editableIntents());intentEditBase={workspace:state.id,rev:state.rev,records};showDialog('연구 의도 수정',`<p class="small muted">저장된 의도를 편집합니다. 바꾼 항목만 연구자의 수정으로 기록하고, 나머지 내용과 출처는 유지합니다.</p><div id="intent-rows">${records.map(intentRow).join('')||intentRow({label:'',text:''})}</div><div class="dialog-actions">${button('add-intent','＋ 항목 추가')}${button('save-intent','수정 내용 저장','','primary')}</div>`)}
function intentRow(r={}){return `<div class="edit-row" data-record-id="${esc(r.id??'')}"><input type="text" class="intent-label" aria-label="의도 항목 이름" placeholder="예: 판단 기준" value="${esc(r.label??'')}"><textarea class="intent-text" aria-label="의도 항목 내용" placeholder="내용 또는 미확인 사항">${esc(r.text??'')}</textarea>${button('remove-intent','×','aria-label="이 항목 삭제"','quiet')}</div>`}
function uploadDialog(){showDialog('기존 자료 추가',`<p class="small muted">원본 파일을 보존합니다. 모르는 조건은 맥락에 미확인으로 적어 주세요.</p><label class="input-label" for="upload-file">자료 파일</label><input type="file" id="upload-file" accept=".csv,.tsv,.txt,.gz"><div class="upload-fields"><label>자료 종류<select id="upload-kind"><option value="molecule_csv">기존 분자 후보 CSV</option><option value="rna_table">기존 RNA 차등발현표</option></select></label><label data-molecule-field>CSV 구분자<select id="upload-delimiter"><option value=",">쉼표</option><option value=";">세미콜론</option><option value="tab">탭</option></select></label><label data-molecule-field>SMILES 열 이름<input type="text" id="upload-smiles" value="smiles"></label><label data-molecule-field>후보 식별자 열 이름<input type="text" id="upload-id" value="cid"></label></div><div id="upload-format-help" class="small muted"><p>후보 ID와 SMILES가 있는 CSV입니다. 열 이름과 구분자를 맞춰 주세요.</p><a href="/templates/molecules.csv" download>빈 CSV 양식 받기</a></div><label class="input-label" for="upload-context">자료의 대상·조건·출처</label><textarea id="upload-context" placeholder="어떤 후보 또는 시료의 자료인지, 단위·시점·대조군 등 알려진 내용을 적어 주세요."></textarea><div class="dialog-actions"><span class="small muted">파일당 10 MiB</span>${button('save-upload','자료 저장','','primary')}</div>`)}
async function act(action,node){
 if(await semanticLiteratureAction(action,node))return;
 if(await workspaceAction(action,node))return;
 if(busy && !['close-dialog','usage-help','model-help'].includes(action))return;
 if(action.startsWith('interaction-')){try{await interactionAction(action,node)}catch(e){notice(e.message)}return}
 if(action.startsWith('roadmap-')){await roadmapAction(action,node);return}
 if(action.startsWith('discovery-')){await discoveryAction(action,node);return}
 if(action==='mechanism-support'){await loadMechanismSupport();return}
 if(action==='mechanism-axis'){
  const row=((mechanismRanking||{}).rows||[]).find(r=>r.option_id===node.dataset.option);
  showDialog(`${row?row.label:'선택지'} · ${AXIS_LABEL[node.dataset.axis]??node.dataset.axis}`,
             mechanismAxisDetail(row,node.dataset.axis));return;
 }
 if(action==='context-edit'){openConditionEdit(node);return}
 if(action==='context-save'){await saveConditionEdit(node.dataset.review==='true');return}
 if(action.startsWith('science-')){await scienceAction(action,node);return}
 if(action==='usage-help'){openUsageHelp();return}
 if(action==='model-help'){await openModelAccessHelp();return}
 if(action==='choose-path'){chooseEntry(node.dataset.mode);return}
 if(action==='show-jobs'){tab='history';render();return}
 if(action==='plan'&&isUsageQuestion(draft)){openUsageHelp(draft);return}
 if(action==='team-prompt'||action==='team-feedback'){await teamAction(action);return}
 if(action==='close-dialog'){dialog.close();return}
 if(action==='remove-intent'){node.closest('.edit-row').remove();return}
 if(action==='add-intent'){document.querySelector('#intent-rows').insertAdjacentHTML('beforeend',intentRow());return}
 if(action==='row'){const row=detail.result.rows[Number(node.dataset.index)];showDialog('행의 전체 값과 출처',json(detail.result.header?{header:detail.result.header,row}:row));return}
 if(action==='edit-intent'){editIntents();return}
 if(action==='upload'){uploadDialog();return}
 if(action==='hypothesis-feedback'){openResearchFeedback(null,node.dataset.hypothesis,node.dataset.part??null);return}
 if(action==='check-feedback'){openResearchFeedback(node.dataset.check,null);return}
 if(action==='delegate-check'){openCheckDelegation(node.dataset.check);return}
 if(action==='evidence-history'){await openEvidenceHistory(node.dataset.hypothesis,Number(node.dataset.offset));return}
 if(action==='history-evidence-feedback'){await reviewHistoricalEvidence(node.dataset.decision);return}
 if(action==='transport-handle'){showDialog('원 응답의 자료 전달 표기',`<p class="prose">${esc(node.dataset.original)}</p><p class="limit">모델에 자료를 전달할 때 사용한 내부 위치입니다. 논문 인용이나 이해·주장 지지의 증거는 아닙니다. 연결된 원자료에서 실제 내용과 적용 조건을 확인하세요. 원 응답은 변경하지 않았습니다.</p>`);return}
 if(action==='historical-hypothesis'){await openHistoricalHypothesis(node.dataset.decision,node.dataset.hypothesis);return}
 if(action==='show-check'){tab='research';roadmapSelections.set(state.id,'next');render();const item=[...document.querySelectorAll('[data-research-check]')].find(el=>el.dataset.researchCheck===node.dataset.check);if(item){if(item.tagName==='DETAILS')item.open=true;item.scrollIntoView({behavior:'smooth',block:'center'})}return}
 if(action==='message-source'){const e=state.events.find(e=>e.body.message_id===node.dataset.id);showDialog('원래 입력',inputSourceView(e));return}
 if(action==='export'){window.location.href=deploymentURL(`/api/workspaces/${state.id}/export`);return}
 if(action==='download'){window.location.href=deploymentURL(`/api/workspaces/${state.id}/artifacts/${node.dataset.id}?download=1`);return}
 if(action==='new'){++projectLoadVersion;intakeError='';actionError='';intakeFile=null;intakeContext='';intakeMode='question';optionsOpen=false;inputKind='message';syntheticDraft=false;history.replaceState(null,'',deploymentURL('/'));state=null;selected=null;detail=null;draft=evidaStorage.getItem(draftKey())??'';tab='research';evidaStorage.removeItem('evida-project');render();return}
 if(action==='tab'){tab=node.dataset.id;render();window.scrollTo(0,0);return}
 if(action==='source'){if(dialog.open)dialog.close();await chooseArtifact(node.dataset.id);return}
 if(action==='article-section'){await openArticleSection(node);return}
 if(action==='article-references'){await openArticleReferences(node);return}
 if(action==='prev'||action==='next'){offset=Math.max(0,offset+(action==='next'?30:-30));await readDetail();return}
 if(action==='project'){await loadProject(node.dataset.id);return}
 busy=true;node.disabled=true;actionError='';intakeError='';
 try{
  if(action==='example'){notice('공개 원자료를 내려받아 조사 때의 내용과 대조하고 있습니다.');state=await api('/api/examples',{id:node.dataset.id});projects=await api('/api/workspaces');draft='';evidaStorage.setItem('evida-project',state.id);const failed=state.events.some(e=>e.kind==='source_import_failed');notice(failed?'일부 자료를 받지 못했습니다. 변경 기록에서 원인을 확인할 수 있습니다.':'공개 원자료를 저장했습니다. 자료와 도구에서 실제 계산을 시작할 수 있습니다.')}
  if(action==='create-message')await startIntake();
  if(action==='intake-example')await startExample(node.dataset.id);
  if(action==='run-check'){await api(`/api/workspaces/${state.id}/research-checks`,{expected_rev:state.rev,decision_id:state.decision_id,check_id:node.dataset.check});await refresh();notice('선택한 확인을 실행하고, 모델이 연결돼 있으면 결과를 이어 검토합니다.')}
  if(action==='save-feedback'){await saveResearchFeedback(node.dataset.review==='true')}
  if(action==='save-message'){await saveMessage();notice('내용을 저장했습니다. 이전 원문과 결과는 유지됩니다.')}
  if(action==='resume-planner'){await api(`/api/workspaces/${state.id}/resume-planner`,{expected_rev:state.rev,source_job:node.dataset.id});await refresh();notice('완료한 조회를 유지하며 중단한 판단을 이어갑니다.')}
  if(action==='plan'){await submitResearchFollowthrough()}
  if(action==='synthesize'){await saveMessage();await runTool('planner',{synthesis_only:true})}
  if(action==='tool'){await runTool(node.dataset.tool,{artifact_id:node.dataset.id})}
  if(action==='literature'){await runTool('literature',{query:document.querySelector('#literature-query').value,cursor:'*'})}
  if(action==='target'){await runTool('open_targets',{target_id:document.querySelector('#target-id').value.trim()})}
  if(action==='save-intent'){
   if(!intentEditBase||intentEditBase.workspace!==state.id)throw Error('현재 연구의 의도 편집을 다시 열어 주세요.');
   const records=[...dialog.querySelectorAll('.edit-row')].map(row=>({id:row.dataset.recordId||`intent_${crypto.randomUUID()}`,label:row.querySelector('.intent-label').value,text:row.querySelector('.intent-text').value}));
   const unchanged=records.length===intentEditBase.records.length&&records.every((r,i)=>['id','label','text'].every(k=>r[k]===intentEditBase.records[i][k]));
   if(unchanged){dialog.close();intentEditBase=null;notice('변경한 항목이 없습니다.');return;}
   await api(`/api/workspaces/${state.id}/commands`,{expected_rev:intentEditBase.rev,command_id:crypto.randomUUID(),body:{kind:'intent_edit',base_records:intentEditBase.records,records}});
   dialog.close();intentEditBase=null;await refresh();notice('수정한 항목을 저장했습니다. 다른 의도와 출처는 유지됩니다.');
  }
  if(action==='save-upload'){
    const file=dialog.querySelector('#upload-file').files[0], kind=dialog.querySelector('#upload-kind').value;
    const d=dialog.querySelector('#upload-delimiter').value;
    const meta={delimiter:kind==='rna_table'?'\t':d==='tab'?'\t':d,smiles_column:dialog.querySelector('#upload-smiles').value,id_column:dialog.querySelector('#upload-id').value,context:dialog.querySelector('#upload-context').value};
    await validateInputFile(file,kind,meta);await uploadInput(file,kind,meta);dialog.close();notice('원자료를 저장했습니다. 분석을 시작하면 실제 결과를 확인할 수 있습니다.');
  }
 }finally{busy=false;submitPhase='';render()}
}
document.addEventListener('click',event=>{const node=event.target.closest('[data-action]');if(!node||node.disabled)return;act(node.dataset.action,node).catch(e=>{busy=false;submitPhase='';if(state)actionError=e.message;else intakeError=e.message;notice(e.message);render()})});
document.addEventListener('input',event=>{if(event.target.id==='message'){draft=event.target.value;evidaStorage.setItem(draftKey(),draft)}if(event.target.id==='artifact-search'){query=event.target.value;render()}});
document.addEventListener('change',event=>{if(event.target.id==='input-kind')inputKind=event.target.value;if(event.target.id==='synthetic')syntheticDraft=event.target.checked});
document.addEventListener('input',event=>{if(event.target.id==='semantic-literature-query'&&state){const view=semanticView(state.id),wasLoading=view.loading;if(wasLoading)semanticStop(state.id,'검색어가 바뀌어 이전 검색 기다림을 닫았습니다.');view.query=event.target.value;if(wasLoading){view.result=null;render()}}});
document.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.id==='semantic-literature-query'){event.preventDefault();act('semantic-literature-search',event.target)}});
async function init(){[status,projects]=await Promise.all([api('/api/status'),api('/api/workspaces')]);const id=new URLSearchParams(location.search).get('workspace')??evidaStorage.getItem('evida-project');if(id&&projects.some(p=>p.id===id))await loadProject(id);else{draft=evidaStorage.getItem(draftKey())??'';render()}setInterval(()=>{if(state&&!busy)refresh().catch(()=>{})},2500);setInterval(checkGatewayWhenVisible,10000)}
init().catch(e=>{app.innerHTML=`<p class="boot">${esc(e.message)}</p>`});

function sourceVisualReviewView(result){return `<p class="limit">보존된 원문 페이지를 읽고 남긴 판독 기록입니다. 새 실험 결과나 독립 검증은 아닙니다.</p>${result.source_artifact_id?sourceLinks([result.source_artifact_id]):''}${result.rows.map(r=>`<article class="source-paragraph"><h3>${esc(r.page)}쪽 · ${esc(r.region_ko??r.region)}</h3><p class="prose">${esc(r.finding_ko??r.finding)}</p><p class="limit">${esc(r.limit_ko??r.limit)}</p></article>`).join('')}`;}

function readingSnapshotView(view){
  if(view?.semantic_type==='independent_saved_evidence_reads')return `<p class="limit">당시 함께 대조하려고 요청한 보존 원문입니다. 각 읽기의 목적·범위·실제 전달 상태를 구별합니다.</p>${view.rows.map(r=>`<details class="source-paragraph"><summary>${esc(r.purpose)} · ${r.status==='succeeded'?'원문 범위 전달':r.status==='same_immutable_view'?'동일 원문 범위 참조':r.status==='needs_narrower_read'?'범위를 좁혀 읽기 필요':'읽기 실패'}</summary>${sourceLinks([r.source_artifact_id])}${r.view?readingSnapshotView(r.view):`<p>${esc(r.message??`읽기 ${r.same_view_as_read+1}번과 같은 뷰입니다.`)}</p>`}<details><summary>요청 범위와 해시</summary>${json({arguments:r.arguments,source_sha256:r.source_sha256,view_sha256:r.view_sha256,status:r.status})}</details></details>`).join('')}`;
  const result=view?.result;
  const source=view?.artifact_id?sourceLinks([view.artifact_id]):'';
  if(!result)return source+json(view);
  if(result.selected_columns&&Array.isArray(result.rows)){
    const headers=result.selected_columns.map((p,i)=>{const cell=result.rows.find(r=>r.cells?.[i]?.source_cell)?.cells[i].source_cell;return cell?.coordinate?cell.coordinate.replace(/[0-9]+$/,'')+'열':p.join(' · ')});
    const rows=result.rows.map(r=>`<tr><td>${esc(r.identity?.sheet??'')} ${esc(r.identity?.row_number??r.identity?.row_id??r.identity?.candidate_id??'')}</td>${r.cells.map(c=>`<td>${!c.present?'열 없음':c.value===null?'비어 있음 (null)':esc(typeof c.value==='object'?JSON.stringify(c.value):String(c.value))}</td>`).join('')}</tr>`).join('');
    return `<p class="limit">당시 판단에 전달된 원행·열입니다. 원본 전체는 아래 출처에서 다시 열 수 있습니다. 빈 값·0·no·??는 그대로 구별합니다.</p>${source}<div class="table-scroll"><table><thead><tr><th>원 위치</th>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div><p class="limit">이번 전달 ${result.rows.length}행 · 전체 일치 ${esc(result.total_rows)}행${result.has_more?' · 뒤의 일치 행이 더 있습니다':''}</p><details class="meta-details"><summary>원 셀·조건·선택 범위 확인</summary>${json(result)}</details>`;
  }
  return source+json(result);
}

labels.rna_weighted_input = 'RNA 고정 가중치·관측';
labels.rna_weighted_distribution = 'RNA 평균·전체 분포 비교';

labels.source_candidates = "원문에서 찾은 후보·치료 참조";

document.addEventListener('toggle',event=>{if(!event.target.isConnected||event.target.dataset?.detailKey!=='semantic-literature'||!state)return;const view=semanticView(state.id);if(event.target.open){view.paused=false;semanticAfterRender();}else semanticStop(state.id);},true);
