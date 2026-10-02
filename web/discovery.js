// Source-backed discovery and researcher choices. Recommendations never truncate the pool.
let goalApproach='', optionsOpen=false, optionsQuery='', optionsKind='', optionsOffset=0, optionsStage='';
let optionsPage=null, optionsError='', optionsWorkspace=null, optionsCursor=null, optionsLoadVersion=0;
const optionKinds={mechanism:'질환 기전',target:'표적',approach:'치료 접근',source_candidate:'문헌에서 찾은 후보·치료 참조',molecule:'구조·활성 조회 물질',rna_candidate:'RNA 후보·참조 조건',researcher_proposal:'연구자 제안'};
const optionStatus={recommended:'추천',alternative:'대안',needs_evidence:'근거 확인 필요',deferred:'현재 보류',unreviewed:'아직 미검토'};
function renderGoalWelcome(){
 if(intakeMode!=='question')return renderWelcome();
 return `<div class="welcome goal-home"><div class="welcome-heading"><div><span class="eyebrow">EVIDA · 연구 의사결정</span><h1>어떤 문제를 해결하고 싶으세요?</h1><p class="description">질환과 목표에서 출발해, 근거를 찾고 다음 실험을 결정합니다.</p></div></div>
 <section class="goal-start" aria-label="질환에서 연구 시작"><label class="input-label" for="message">연구할 질환·현상과 바꾸고 싶은 결과</label><textarea id="message" placeholder="예: 유전성 ATTR 아밀로이드증의 단백질 축적을 줄이고 싶어요. 관련 기전을 비교하고, 검토할 후보를 찾아 주세요.">${esc(draft)}</textarea>
 <fieldset class="approach-choices"><legend>우선 검토할 접근 <span class="muted">· 아직 정하지 않아도 됩니다</span></legend>${[['','함께 비교'],['small_molecule','저분자부터'],['sirna','siRNA부터']].map(([id,label])=>`<label class="approach-choice ${goalApproach===id?'selected':''}"><input type="radio" name="goal-approach" value="${id}" ${goalApproach===id?'checked':''}>${label}</label>`).join('')}</fieldset>
 <p class="goal-promise">후보 이름이나 서열이 없어도 시작할 수 있습니다. 기전과 표적의 근거를 찾고, 추천 이유와 다른 선택지를 함께 남깁니다.</p>
 ${intakeError?`<p class="form-error" role="alert">${esc(intakeError)}</p>`:''}<div class="input-bottom"><span class="small muted">공개 자료 조회와 실제 모델 검토가 시작됩니다.</span>${modelChoice()}${button('create-message','목표에서 연구 시작',busy?'disabled':'','primary')}</div></section>
 <div class="goal-journey" aria-label="연구 흐름">${[['01','구조화된 질문과 목표','무엇을, 왜 바꿀지'],['02','기전과 접근','어떤 방향을 검토할지'],['03','후보 발굴','무엇을 실제로 비교할지'],['04','근거와 계산','어디까지 확인했는지'],['05','EVIDA 실험 권고','다음에 무엇을 해볼지']].map(([n,t,d])=>`<div><span>${n}</span><strong>${t}</strong><p>${d}</p></div>`).join('')}</div>
 <section class="existing-entry"><h2>이미 진행 중인 연구가 있나요?</h2><p>가진 자료부터 시작하거나, 위 목표에 알려진 내용을 함께 적어 주세요.</p><div class="entry-help-actions">${ENTRY_PATHS.filter(x=>x.id!=='question').map(x=>button('choose-path',esc(x.name),`data-mode="${x.id}"`,'small')).join('')}${button('usage-help','사용법 보기','','quiet small')}</div></section>
 <section class="goal-examples"><h2>입력 예시</h2><div class="example-choices">${[['small_molecule','저분자 경로','유전성 ATTR 아밀로이드증의 축적을 줄이는 기전과 저분자 접근을 비교하고 싶어요. 후보가 없으니 근거로 찾고 실제 계산까지 이어 주세요.'],['sirna','siRNA 경로','간에서 만들어지는 TTR를 줄이는 접근이 유전성 ATTR 아밀로이드증에 타당한지 확인하고, 근거가 맞으면 실제 전사체에서 siRNA 후보를 만들어 비교해 주세요.']].map(([id,label,text])=>`<article><h3>${label}</h3><p>${text}</p>${button('discovery-example','이 질문으로 시작하기',`data-example="${id}"`,'small')}</article>`).join('')}</div><p class="small muted">예시 버튼은 질문을 채웁니다. 시작 버튼을 누르면 새 연구를 실행합니다.</p></section></div>`;
}
function rnaOptionContext(item){
 if(item.kind!=='rna_candidate'||!item.candidate_artifact_id)return '';
 const calculation=state.artifacts.find(a=>a.id===item.candidate_artifact_id);
 const reference=calculation?.meta.arguments?.artifact_id;
 if(!reference)return '';
 return `<p class="small muted">같은 가이드라도 전사체별 계산 조건은 다릅니다. 계산 참조: ${esc(artifactName(reference))}</p>`;
}
function optionKind(item){return item.kind??item.option_id.split(':')[0]}
function optionActionLabel(item,selected){const kind=optionKind(item);const base=({mechanism:'이 기전',target:'이 표적',approach:'이 접근',source_candidate:'이 문헌 후보',molecule:'이 화합물',rna_candidate:'이 RNA 후보',rna:'이 RNA 후보'})[kind]??'이 선택지';return base+(selected?'로 계속':' 검토하기')}
function groupedRecommendations(items){
 const groups=[['mechanism','target'],['approach'],['source_candidate','molecule','rna_candidate','rna'],['researcher_proposal']];
 const titles=['바꾸려는 기전과 표적','치료 접근','실제로 비교할 후보','연구자의 새 제안'];
 const known=new Set(groups.flat());
 return groups.map((kinds,i)=>{const rows=items.filter(x=>kinds.includes(optionKind(x)));return rows.length?`<section class="recommendation-stage"><h3>${titles[i]}</h3><div class="recommendation-grid">${rows.map(x=>discoveryCard(x,true)).join('')}</div></section>`:''}).join('')+
  `<div class="recommendation-grid">${items.filter(x=>!known.has(optionKind(x))).map(x=>discoveryCard(x,true)).join('')}</div>`;
}
function discoveryPreview(value){
 // Only frozen model-transport locators leave the card preview. Exact rationale
 // and its source links remain unchanged in the detail dialog and saved record.
 return String(value??'').replace(/\(D\d{4},\s*s-[a-f0-9]+-p\d+\.txt,[^)]*\)/g,'').trim();
}
function discoveryRecordLabel(assessment){
 if(!assessment)return '평가 기록 없음';
 const rev=Number.isInteger(assessment.based_rev)?`연구 기록 ${assessment.based_rev}`:'연구 기록 시점 미확인';
 return `${assessment.current_conditions===true?'현재 조건의 평가':assessment.current_conditions===false?'이전 조건의 평가':'평가 조건 확인 필요'} · ${rev}`;
}
function discoveryFirstDescription(item){
 if(!item.description)return '';
 const origin=(item.sources??[]).map(x=>state.artifacts.find(a=>a.id===x.artifact_id)).find(a=>a?.kind==='discovery_review');
 const rev=origin?.meta?.based_rev;
 return `<details class="discovery-first-description"><summary>처음 발견했을 때의 설명${Number.isInteger(rev)?' · 연구 기록 '+rev:' · 기록 시점 확인 필요'}</summary><p>${esc(item.description)}</p>${origin?sourceLinks([origin.id]):''}</details>`;
}
function discoveryCard(item,compact=false){
 const a=item.assessment,selected=item.selected??state.discovery?.selected?.option_id===item.option_id;
 const preview=discoveryPreview(a?.reason);
 const reviewJob=a?state.jobs.find(j=>j.id===state.artifacts.find(x=>x.id===a.artifact_id)?.meta?.job_id):null;const draftReview=reviewJob&&reviewJob.status!=='succeeded';
 return `<article class="option-card ${selected?'chosen':''}" data-option="${esc(item.option_id)}"><div class="option-heading"><div><span class="small muted">${esc(optionKinds[item.kind??item.option_id.split(':')[0]]??(item.option_id.startsWith('rna:')?'RNA 후보':'검토한 선택지'))}${a?.priority?` · ${a.priority}순위` :''}</span><h3>${esc(candidateDisplayName(item))}</h3></div><span class="option-tag ${esc(a?.status??'unreviewed')}">${selected?'연구자 선택':esc((a?.current_conditions===false?'이전 ':'')+optionStatus[a?.status??'unreviewed'])}</span></div>
 ${draftReview?`<p class="small revision-note">${['running','queued'].includes(reviewJob.status)?'검토 중인 추천안 · 최종 판단 전':'미완료 검토에서 보존한 추천안'}</p>`:''}${a?`<p class="small muted">${esc(discoveryRecordLabel(a))} · ${esc(optionStatus[a.status]??a.status)}</p><p>${judgmentText(compact&&preview.length>210?preview.slice(0,210)+'…':preview)}</p>${!a.current_conditions?'<p class="small revision-note">이전 조건의 검토 · 새 입력 반영 확인 필요</p>':''}`:`<p class="muted">발견 목록에 보존했습니다. 추천 여부는 아직 검토하지 않았습니다.</p>`}
 ${sourceCandidateInfo(item)}${rnaOptionContext(item)}${compact?'':discoveryFirstDescription(item)}<div class="detail-actions">${button('discovery-detail','근거·다음 확인',`data-id="${esc(item.option_id)}"`,'small')}${button('discovery-choose',optionActionLabel(item,selected),`data-id="${esc(item.option_id)}"`,'small')}${selected?'':button('discovery-run','이 경로로 연구 시작',`data-id="${esc(item.option_id)}" ${!status.gateway.available||busy?'disabled':''}`,'small primary')}</div></article>`;
}
function renderDiscovery(){
 const d=state.discovery;if(!d)return '';
 const recommended=(d.recommendations??[]).filter(item=>item.assessment?.current_conditions===true);
 const earlierRecommendations=(d.recommendations??[]).filter(item=>item.assessment?.current_conditions!==true);
 const spaces=state.artifacts.filter(a=>a.kind==='rna_candidate_space'&&a.meta.result_status==='succeeded');
 const listName=spaces.length?'기전·접근·개별 후보 목록':'발견한 선택지 전체';
 return `<section class="discovery-section" aria-label="추천과 전체 선택지"><div class="section-heading"><div><span class="section-mark">선택지를 보존하며 연구하기</span><h2>${recommended.length?'현재 조건에서 추천한 선택지':'선택지와 검토 기록'}</h2></div><span class="small muted">${spaces.length?'기전·접근·개별 후보':'발견'} ${d.total} · 검토 ${d.reviewed}</span></div>
 ${d.selected?`<div class="selected-path"><strong>${d.selected.state_rev<state.rev?'이전 입력의 선택 기록':'연구자의 선택 기록'}</strong> ${esc(d.selected.label)}${d.selected.reason?`<details><summary>선택 이유와 당시 조건</summary><p>${esc(d.selected.reason)}</p>${d.selected.state_rev<state.rev?'<p class="small">이번 입력보다 앞선 선택 기록입니다. 현재 적용 범위는 위 판단에서 확인하세요.</p>':''}</details>`:''}</div>`:''}
 ${recommended.length?`<div class="current-recommendations">${groupedRecommendations(recommended)}</div>`:`<p class="muted">${d.total?'현재 조건에서 추천으로 표시한 선택지는 없습니다. 아래에서 이전 추천과 보류 이유, 아직 평가하지 않은 선택지를 확인하고 다시 검토할 수 있습니다.':'질환의 근거를 조회하면 기전·표적·후보가 여기에 쌓입니다.'}</p>`}
 ${earlierRecommendations.length?`<details class="earlier-recommendations"><summary>이전 조건의 추천 ${earlierRecommendations.length}개 보기</summary><p class="small muted">당시 이유와 원 근거를 보존했습니다. 현재 목표의 추천과 구분해서 보고, 필요한 경로는 다시 선택할 수 있습니다.</p>${groupedRecommendations(earlierRecommendations)}</details>`:''}
 ${d.reconsidered_options?.length?`<section class="reconsidered-options"><h3>새 근거로 다시 확인할 접근·후보</h3><p class="small muted">앞서 추천했던 선택지의 현재 조건과 이유입니다. 후보는 보존하고, 추천이 바뀐 이유를 확인합니다.</p>${groupedRecommendations(d.reconsidered_options)}</section>`:''}
 <div class="discovery-controls">${button('discovery-toggle',optionsOpen?'목록 접기':`${listName} 보기 (${d.total})`,`aria-expanded="${optionsOpen}"`,'small')}${button('discovery-propose','다른 경로 제안하기','','small')}</div>
 ${spaces.length?`<section class="rna-retained-spaces" aria-label="보존한 전체 RNA 서열 후보"><h3>아직 고르지 않은 RNA 후보도 살펴보세요</h3><p class="small muted">위 목록의 수는 전체 서열 후보 수가 아닙니다. 아래에서 모든 후보를 검색하고, 추천 밖 후보도 골라 실제 계산할 수 있습니다.</p>${spaces.map(a=>{const s=a.meta.summary??{};return `<div class="discovery-controls">${button('source',`${s.region_annotated?'CDS·UTR로 살펴보기':'원 후보 목록 보기'} · ${Number(s.unique_guide_sequences).toLocaleString()}개`,`data-id="${esc(a.id)}"`,'small')}<span class="small muted">${s.selected_references}개 참조 · ${s.paired_length}nt · 원위치 ${Number(s.known_base_origins).toLocaleString()}개 · 효능 순위 아님</span></div>`}).join('')}</section>`:''}
 ${optionsOpen?renderOptionBrowser():''}<p class="small muted pool-scope">발견한 범위의 목록입니다. 추천 밖 항목도 검토할 수 있고, 아직 찾지 않은 기전·후보가 있을 수 있습니다.</p></section>`;
}
function renderOptionBrowser(){
 const ready=optionsPage&&optionsWorkspace===state.id&&optionsCursor===`${state.event_cursor}@${state.rev}`;
 return `<div class="option-browser"><div class="option-filters"><label>선택지 검색<input type="search" id="option-query" value="${esc(optionsQuery)}" placeholder="이름, 이유, 출처로 찾기"></label><label>종류<select id="option-kind"><option value="">모든 종류</option>${Object.entries(optionKinds).map(([k,v])=>`<option value="${k}" ${optionsKind===k?'selected':''}>${v}</option>`).join('')}</select></label>${button('discovery-search','찾기','','small')}</div>
 ${optionsError?`<p role="alert">${esc(optionsError)}</p>`:''}${ready?`<div class="option-range"><span>${optionsPage.filtered_total}개 중 ${optionsPage.rows.length?optionsPage.offset+1:0}–${optionsPage.offset+optionsPage.rows.length} 표시</span><div>${button('discovery-prev','이전',optionsOffset===0?'disabled':'','small')}${button('discovery-next','다음',!optionsPage.has_more?'disabled':'','small')}</div></div><div class="option-list">${optionsPage.rows.map(x=>discoveryCard(x)).join('')||'<p>이 검색에 맞는 항목이 없습니다. 다른 검색이나 새 경로 제안을 이용하세요.</p>'}</div>`:'<p>원자료에 연결된 목록을 불러오고 있습니다.</p>'}
 <details class="pool-coverage"><summary>찾은 범위와 아직 남은 탐색</summary>${state.discovery.scope_review?`<p class="small muted">${state.discovery.scope_review.current_conditions?'현재 조건에서 남긴 탐색 메모':'이전 조건에서 남긴 탐색 메모 · 이후 읽은 자료는 최신 판단과 함께 확인하세요.'}${sourceLinks([state.discovery.scope_review.artifact_id])}</p>`:''}${list(state.discovery.unsearched_scope)}${(state.discovery.rna_search_coverage??[]).map(c=>`<p class="small">${esc(c.transcript_id)} · ${c.paired_length}nt 결합 영역 ${c.possible_windows}개 중 ${c.generated_windows}개 생성 · ${c.remaining_windows_not_generated}개 미생성${c.version?` · 버전 ${esc(c.version)}`:""}</p>`).join("")}${ready?optionsPage.coverage.map(c=>`<p class="small">${esc(labels[c.kind]??c.kind)} · ${esc(c.summary?.rule??'보존된 원 조회 범위')}${c.summary?.has_more?' · 다음 페이지 있음':''}${sourceLinks([c.artifact_id])}</p>`).join(''):''}</details></div>`;
}
async function loadOptions(){
 if(!state||!optionsOpen)return;const wid=state.id,cursor=`${state.event_cursor}@${state.rev}`,version=++optionsLoadVersion;
 const params=new URLSearchParams({query:optionsQuery,kind:optionsKind,offset:String(optionsOffset),limit:'12'});
 const current=()=>state?.id===wid&&`${state.event_cursor}@${state.rev}`===cursor&&version===optionsLoadVersion;
 try{const value=await api(`/api/workspaces/${wid}/discovery-options?${params}`);if(!current())return;optionsPage=value;optionsWorkspace=wid;optionsCursor=cursor;optionsError=''}catch(e){if(current())optionsError=e.message}if(current())render();
}
async function getOption(id){
 const key=`${state.id}@${state.event_cursor}@${state.rev}`;
 const page=await api(`/api/workspaces/${state.id}/discovery-options?`+new URLSearchParams({query:id,limit:'100'}));
 if(!state||`${state.id}@${state.event_cursor}@${state.rev}`!==key)throw Error('연구가 바뀌었습니다. 현재 연구에서 다시 선택해 주세요.');
 const item=page.rows.find(x=>x.option_id===id);if(!item)throw Error('현재 선택지 목록에서 항목을 확인할 수 없습니다. 목록을 새로 불러와 주세요.');return item;
}
function optionDetail(item){
 const a=item.assessment;
 const drawn=typeof candidateStructureRow==='function'?candidateStructureRow(item.option_id):null;
 const picture=drawn&&structureThumb(drawn)?`<div class="candidate-detail-structure">${structureFigure(drawn.depiction,item.label)}<p class="small muted">${esc(drawn.depiction.formula??'')} · 기록된 구조의 2D 그림</p></div>`:'';
 return `${picture}<p class="small muted">${esc(optionKinds[item.kind])} · ${esc(optionStatus[item.review_status])}</p>${sourceCandidateInfo(item,true)}${rnaOptionContext(item)}${a?`<h3>${esc(discoveryRecordLabel(a))}</h3><p>${judgmentText(researcherWording(a.reason))}</p>${a.priority?`<p class="small">${esc(a.comparison_group)} 안의 ${a.priority}순위</p>`:''}<h3>지지 근거</h3>${sourceLinks(a.support_source_ids)}<h3>반대 근거·적용 조건</h3>${sourceLinks(a.challenge_source_ids)}${list(a.uncertainties)}<h3>다음 확인</h3><p>${esc(researcherWording(a.next_action))}</p>`:'<p>아직 추천 검토를 마치지 않은 항목입니다. 아래 원자료를 보거나 이 경로의 검토를 요청할 수 있습니다.</p>'}${discoveryFirstDescription(item)}<details><summary>발견한 원자료 ${item.sources.length}개</summary>${sourceLinks(item.sources.map(x=>x.artifact_id))}${item.message_id?button('message-source','연구자 원 제안',`data-id="${esc(item.message_id)}"`,'link-button'):''}</details>${item.assessments.length>1?`<details><summary>이전 검토 이력 ${item.assessments.length-1}개</summary>${item.assessments.slice(0,-1).reverse().map(x=>`<p class="small muted">${esc(discoveryRecordLabel(x))} · ${esc(optionStatus[x.status])}</p><p>${esc(x.reason)}</p>${sourceLinks([x.artifact_id])}`).join('')}</details>`:''}<div class="dialog-actions">${button('discovery-choose','이 경로 검토하기',`data-id="${esc(item.option_id)}"`,'primary')}</div>`;
}
async function discoveryAction(action,node){
 if(action==='discovery-example'){
  goalApproach=node.dataset.example;draft=goalApproach==='sirna'?'간에서 만들어지는 TTR를 줄이는 접근이 유전성 ATTR 아밀로이드증에 타당한지 확인하고, 근거가 맞으면 실제 전사체에서 siRNA 후보를 만들어 비교해 주세요.':'유전성 ATTR 아밀로이드증의 축적을 줄이는 기전과 저분자 접근을 비교하고 싶어요. 후보가 없으니 근거로 찾고 실제 계산까지 이어 주세요.';
  evidaStorage.setItem(draftKey(),draft);render();document.querySelector('#message')?.focus();return;
 }
 if(action==='discovery-toggle'){optionsOpen=!optionsOpen;render();if(optionsOpen)await loadOptions();return}
 if(['discovery-search','discovery-prev','discovery-next'].includes(action)){optionsQuery=document.querySelector('#option-query')?.value??optionsQuery;optionsKind=document.querySelector('#option-kind')?.value??optionsKind;optionsOffset=action==='discovery-search'?0:Math.max(0,optionsOffset+(action==='discovery-next'?12:-12));optionsPage=null;render();await loadOptions();return}
 if(action==='discovery-detail'){const item=await getOption(node.dataset.id);if(dialog.open)dialog.close();showDialog(candidateDisplayName(item),optionDetail(item));return}
 if(action==='discovery-choose'||action==='discovery-propose'){
  const propose=action==='discovery-propose';const item=propose?null:await getOption(node.dataset.id);
  if(dialog.open)dialog.close();const active=state.jobs.some(j=>['queued','running'].includes(j.status));
  showDialog(propose?'연구자의 새로운 경로':'검토할 경로 선택',`<p>${propose?'추천 목록에 없는 기전·표적·접근도 제안해 주세요. 근거를 확인하고 다음 작업에 반영합니다.':`${esc(item.label)}를 우선 검토합니다. 기존 추천과 원자료는 그대로 보존합니다.`}</p>${propose?'<label>검토할 경로<input id="option-proposal" maxlength="240" placeholder="예: 다른 기전, 표적 또는 조합 접근"></label>':''}<label>${propose?'아이디어의 근거·조건':'선택 이유 또는 추가 조건'}<textarea id="option-reason" placeholder="선행 지식이나 확인하고 싶은 점을 알려주세요. 모르는 부분은 비워 두어도 됩니다."></textarea></label><p class="small muted">선택·제안 자체가 과학적 타당성을 확정하지는 않습니다.</p>${active?'<p class="notice-inline">진행 중인 검토가 있습니다. 선택을 저장하면(어느 버튼이든) 그 검토는 판단을 내지 않고 ‘이전 조건의 작업’으로 닫힙니다. 모은 자료·계산은 보존되고 다음 검토에서 재사용됩니다. ‘이 경로로 검토 시작’은 새 조건으로 다시 검토하고, ‘선택만 저장’은 새 검토를 시작하지 않습니다. 첫 판단을 먼저 보려면 검토가 끝난 뒤 선택하세요.</p>':''}<div class="dialog-actions">${button('discovery-save','선택만 저장',`data-id="${esc(item?.option_id??'')}" data-proposal="${propose}"`)}${button('discovery-save','이 경로로 검토 시작',`data-id="${esc(item?.option_id??'')}" data-proposal="${propose}" data-review="true" ${!status.gateway.available?'disabled':''}`,'primary')}</div>`);return;
 }
 if(action==='discovery-run'){
  busy=true;node.disabled=true;
  try{
   await api(`/api/workspaces/${state.id}/discovery-select`,{expected_rev:state.rev,
     command_id:crypto.randomUUID(),text:'',option_id:node.dataset.id,review_requested:true});
   if(dialog.open)dialog.close();await refresh();
   notice('이 경로로 검토를 시작했습니다. 기존 추천과 원자료는 그대로 보존됩니다.');
  }finally{busy=false;render()}
  return;
 }
 if(action==='discovery-save'){
  const propose=node.dataset.proposal==='true',text=document.querySelector('#option-reason').value,label=document.querySelector('#option-proposal')?.value;
  busy=true;node.disabled=true;
  try{await api(`/api/workspaces/${state.id}/${propose?'discovery-proposals':'discovery-select'}`,{expected_rev:state.rev,command_id:crypto.randomUUID(),text,label,option_id:node.dataset.id,review_requested:node.dataset.review==='true'});dialog.close();await refresh();notice(node.dataset.review==='true'?'연구자의 경로와 후속 검토를 함께 접수했습니다.':'연구자의 경로와 원래 추천을 함께 보존했습니다.')}finally{busy=false;render()}return;
 }
}
document.addEventListener('change',event=>{if(event.target.name==='goal-approach'){goalApproach=event.target.value;render()}if(event.target.id==='option-kind')optionsKind=event.target.value});
document.addEventListener('input',event=>{if(event.target.id==='option-query')optionsQuery=event.target.value});

function sourceCandidateInfo(item,detail=false){
 if(item.kind!=='source_candidate')return '';
 const modality=({small_molecule:'저분자',sirna:'siRNA 치료 참조',other:'다른 치료 방식',unknown:'치료 방식 확인 중'})[item.modality]??'치료 방식 확인 중';
 const linked=(item.identity_links??[]).filter(x=>x.structure_status==='available');
 const identity=linked.length?'데이터베이스 구조 회수 · 원 시료 대응은 별도 확인':((item.identity_links??[]).length?'구조 조회 결과 미확인 · 원문 후보 보존':item.identity?.lookup_name?'원문 식별명 확보 · 구조 조회 전':'구조 식별 확인 필요');
 const brief=`<p class="small muted">${esc(modality)} · ${item.role==='reference_treatment'?'비교를 위한 치료 참조':'원문 후보'} · ${esc(identity)}</p>`;
 if(!detail)return brief;
 return brief+`<h3>목록에 남긴 이유와 적용 조건</h3>${list(item.conditions)}<p>${esc(item.next_check)}</p>${item.identity?.lookup_name?`<p>원문에서 확인한 조회명: ${esc(item.identity.lookup_name)}</p>`:''}<details><summary>정확한 원문 이름·위치와 식별 이력</summary>${(item.candidate_records??[]).map(x=>`<p>${esc(x.record.mention.row_id??x.record.mention.locator)}</p><blockquote>${esc(x.record.mention.quote)}</blockquote>${sourceLinks([x.record.mention.artifact_id])}`).join('')}${(item.identity_links??[]).map(x=>`<p>${esc(x.candidate_id)} · ${x.structure_status==='available'?'구조 반환':'식별 미확인'}</p>${x.next_identity_check?`<p>${esc(x.next_identity_check)}</p>`:''}${sourceLinks([x.artifact_id])}`).join('')}</details>`;
}
