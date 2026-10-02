/* Typed evidence projection. Recorded interpretations and optional local
   semantic reading order stay separate; neither changes the scientific state. */
const EVIDENCE_WORKBENCH_RELATION={supports:'지지',challenges:'반대·제약',context:'적용 맥락',uncertain:'판정 보류'};
const EVIDENCE_WORKBENCH_ASSESSMENT={consistent_in_context:'해당 조건에서 부합',challenged:'반대 근거 있음',inconclusive:'판정 미정',unassessed:'미평가'};
const semanticLiteratureViews=new Map();
function semanticView(wid){if(!semanticLiteratureViews.has(wid))semanticLiteratureViews.set(wid,{});return semanticLiteratureViews.get(wid)}
function semanticStop(wid,message){const view=semanticLiteratureViews.get(wid);if(!view)return;view.controller?.abort();clearTimeout(view.timer);view.version=(view.version??0)+1;view.loading=false;view.checking=false;view.preparing=false;view.timer=null;if(message)view.message=message;}
async function semanticRequest(wid,path,body){const view=semanticView(wid);view.controller?.abort();const controller=new AbortController();view.controller=controller;const response=await fetch(deploymentURL(`/api/workspaces/${encodeURIComponent(wid)}/semantic-literature${path}`),{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Evida-Request':'1'}:{},body:body?JSON.stringify(body):undefined,signal:controller.signal});const data=await response.json();if(!response.ok)throw Error(data.error||'문헌 준비 상태를 확인하지 못했습니다.');return data;}
function semanticPanelOpen(){return !!document.querySelector('[data-detail-key="semantic-literature"]')?.open}
function semanticAfterRender(){for(const wid of semanticLiteratureViews.keys())if(wid!==state?.id)semanticStop(wid,'다른 연구로 이동했습니다. 시작한 문헌 준비는 원래 연구에서 계속됩니다.');const wid=state?.id;if(!wid||!semanticPanelOpen())return;const view=semanticView(wid);if(view.paused)return;if(!view.status&&!view.checking&&!view.error)void semanticStatus(wid);else if(view.status?.running&&!view.timer&&!view.checking)semanticPoll(wid);}
function semanticPoll(wid){const view=semanticView(wid);clearTimeout(view.timer);view.timer=setTimeout(()=>{view.timer=null;if(state?.id===wid&&semanticPanelOpen())void semanticStatus(wid)},1500)}
async function semanticStatus(wid){const view=semanticView(wid);if(view.checking||view.loading||view.preparing)return;view.checking=true;const version=view.version??0;
 try{const status=await semanticRequest(wid,'/status');if(state?.id!==wid||version!==(view.version??0))return;view.status=status;if(!status.available)view.result=null;view.error=null;if(!status.running)view.message=null;}
 catch(error){if(error.name!=='AbortError'&&state?.id===wid&&version===(view.version??0))view.error=error.message;}
 finally{if(version===(view.version??0)){view.checking=false;if(state?.id===wid)render();}}
}
function semanticSourceButtons(row){const refs=row.all_source_locators?.length?row.all_source_locators:[row.source];return refs.filter(Boolean).map((source,i)=>{const offset=source.row_offset??source.row_index;return Number.isInteger(offset)&&offset>=0?button('source',refs.length>1?`원행 보기 ${i+1}`:'원행 보기',`data-id="${esc(source.artifact_id)}" data-source-offset="${offset}"`,'link-button small'):'<span class="small muted">원행 위치 확인 필요</span>'}).join(' ')}
function renderSemanticLiterature(snapshot){
 if(!snapshot?.semantic_literature)return '';const view=semanticView(snapshot.id),scope=view.status??snapshot.semantic_literature,result=scope.available===false?null:view.result;
 const indexed=Number(scope.indexed_documents??0),pending=Number(scope.pending_documents??0),retained=Number(scope.retained_documents??indexed),running=!!scope.running,ready=scope.available??(indexed>0&&!scope.stale_source_records);
 const states={unindexed:'문헌 내용 찾기 준비 전',ready:'문헌 내용 찾기 준비 완료',pending:'추가 문헌 준비 필요',building:'문헌 내용 찾기 준비 중',failed:'문헌 준비를 완료하지 못했습니다',empty:'검색할 제목·초록이 아직 없습니다'};
 const rows=(result?.rows??[]).map(row=>`<li><strong>${row.rank}. ${esc(row.title)}</strong><small>${esc(row.document_id)}</small>${semanticSourceButtons(row)}<details><summary>보존된 초록</summary><p>${esc(row.abstract||'이 반환 행에는 초록이 없습니다.')}</p></details></li>`).join('');
 return `<details class="ew-search" data-detail-key="semantic-literature"><summary>영문으로 문헌 내용 찾기 · 선택</summary>
 <p role="status">${view.checking&&!view.status?'보존 문헌의 검색 범위를 확인 중입니다.':states[scope.state]??(indexed?'문헌 내용 찾기 준비 완료':'보존 문헌의 준비 상태를 확인합니다.')}</p>
 <p>준비된 제목·초록 ${indexed}개 / 보존 문헌 ${retained}개${pending?` · 추가 준비 ${pending}개`:''}. 검색어와 가까운 순서로 읽습니다. 근거 강도나 치료 추천 순위와는 별개입니다.</p>
 ${scope.retained_search_records!==undefined?`<p class="small muted">보존 검색 기록 ${scope.retained_search_records}개 중 준비된 기록 ${scope.indexed_search_records??0}개.</p>`:''}
 ${scope.stale_source_records?'<p class="small muted">일부 출처가 현재 원자료와 달라 다시 준비해야 합니다. 해당 자료는 기존 원자료 보기에서 확인할 수 있습니다.</p>':''}
 ${running?'<p class="small muted">문헌을 준비하고 있습니다. 다른 연구로 이동해도 시작한 준비는 이 연구에서 계속됩니다.</p>':''}
 <div class="detail-actions">${scope.can_build&&!running?button('semantic-literature-prepare',view.preparing?'문헌 준비 요청 중…':indexed?'추가 보존 문헌으로 내용 찾기 준비':'보존 문헌으로 내용 찾기 준비',view.preparing?'disabled':'','small'):''}${button('semantic-literature-status','준비 상태 확인',view.checking||view.preparing?'disabled':'','quiet small')}</div>
 ${ready?`<label for="semantic-literature-query">영문 검색어</label><input type="search" id="semantic-literature-query" maxlength="1024" value="${esc(view.query??'')}" placeholder="예: microglia inflammasome cytokine" autocomplete="off"><div class="detail-actions">${button('semantic-literature-search',view.loading?'문헌 검색 중…':'내용으로 찾기',view.loading?'disabled':'','small')}${result?button('semantic-literature-clear','검색 결과 접기','','quiet small'):''}</div>`:''}
 ${view.loading||running||view.preparing?button('semantic-literature-cancel',view.loading?'현재 검색 취소':'준비 상태 기다림 닫기','','quiet small'):''}
 ${view.message?`<p role="status">${esc(view.message)}</p>`:''}${view.error?`<p role="alert">${esc(view.error)} 원자료와 기존 판단은 계속 확인할 수 있습니다.</p>`:''}
 ${result?`<p role="status">${esc(result.query)} · ${result.rows.length?result.offset+1:0}–${result.offset+result.rows.length} / 검색한 제목·초록 ${result.total_indexed}개</p><ul class="list">${rows}</ul><div class="detail-actions">${result.offset?button('semantic-literature-page','이전 문헌',`data-offset="${Math.max(0,result.offset-result.limit)}" ${view.loading?'disabled':''}`,'small'):''}${result.has_more?button('semantic-literature-page','다음 문헌',`data-offset="${result.offset+result.limit}" ${view.loading?'disabled':''}`,'small'):''}</div>`:''}</details>`;
}
async function semanticLiteratureAction(action,node){
 if(!action.startsWith('semantic-literature-'))return false;if(!state?.semantic_literature)return true;const wid=state.id,view=semanticView(wid);
 if(action==='semantic-literature-cancel'){const panel=node.closest?.('[data-detail-key="semantic-literature"]');if(panel)panel.open=false;semanticStop(wid,'화면의 기다림을 닫았습니다. 이미 시작한 문헌 준비는 이 연구에서 계속됩니다.');view.paused=true;render();return true;}
 if(action==='semantic-literature-clear'){semanticStop(wid);view.result=null;render();return true;}
 if(action==='semantic-literature-status'){view.paused=false;await semanticStatus(wid);return true;}
 if(view.loading||view.preparing)return true;semanticStop(wid);view.paused=false;view.error=null;view.message=null;const version=view.version;
 if(action==='semantic-literature-prepare'){view.preparing=true;render();try{const status=await semanticRequest(wid,'/index',{});if(state?.id===wid&&view.version===version)view.status=status;}catch(error){if(error.name!=='AbortError'&&state?.id===wid&&view.version===version)view.error=error.message;}finally{if(view.version===version){view.preparing=false;if(state?.id===wid)render();}}return true;}
 const query=action==='semantic-literature-page'?view.result?.query:document.querySelector('#semantic-literature-query')?.value??'';const offset=action==='semantic-literature-page'?Number(node.dataset.offset):0;
 view.query=query;view.loading=true;render();try{const result=await semanticRequest(wid,'?'+new URLSearchParams({query,offset,limit:10}));if(state?.id===wid&&view.version===version)view.result=result;}catch(error){if(error.name!=='AbortError'&&state?.id===wid&&view.version===version)view.error=error.message;}finally{if(view.version===version){view.loading=false;if(state?.id===wid)render();}}return true;
}

function evidenceWorkbenchText(value,fallback='확인 필요'){
  return typeof value==='string'&&value.trim()?value.trim():fallback;
}
function evidenceWorkbenchClaims(decision){
  if(typeof roadmapClaimRecords==='function')return roadmapClaimRecords(decision);
  const rows=[];
  for(const hypothesis of decision?.research_loop?.hypotheses??[]){
    rows.push({...hypothesis,claim_id:hypothesis.id,level:'hypothesis'});
    for(const part of hypothesis.assessment_scope?.parts??[])rows.push({...part,claim_id:part.id,level:'part',hypothesis_id:hypothesis.id});
    for(const alternative of hypothesis.conditional_alternatives??[])rows.push({...alternative,claim_id:alternative.id,level:'alternative',hypothesis_id:hypothesis.id});
  }
  return rows;
}
function evidenceWorkbenchScope(snapshot){
  const artifacts=Array.isArray(snapshot?.artifacts)?snapshot.artifacts:[];
  const searches=artifacts.filter(a=>a&&['literature','clinical_trial_search','drug_label_search','entity_search'].includes(a.kind)
    && Number.isInteger(a.meta?.summary?.returned) && a.meta.summary.returned>=0);
  const fullText=artifacts.filter(a=>a?.kind==='article'
    && a.meta?.semantic_type==='published_full_text'
    && a.meta?.summary?.content_scope==='body_available'
    && ['succeeded','reused'].includes(a.meta?.result_status));
  const claims=evidenceWorkbenchClaims(snapshot?.decision);
  const evidence=claims.flatMap(c=>Array.isArray(c.evidence)?c.evidence:[]);
  const artifactIds=new Set(artifacts.map(a=>a.id));
  const linked=[...new Set(evidence.filter(e=>e?.source_type==='artifact'&&artifactIds.has(e.source_id)).map(e=>e.source_id))];
  return {searches,fullText,claims,evidence,linked};
}
function evidenceWorkbenchSource(row,snapshot){
  const id=typeof row?.source_id==='string'?row.source_id:'';
  if(!id)return '<span class="ew-gap">출처 ID 확인 필요</span>';
  if(row.source_type==='artifact'){
    if(!(snapshot.artifacts??[]).some(a=>a.id===id))return `<span class="ew-gap">현재 연구에 연결된 원자료 확인 필요 · <code>${esc(id)}</code></span>`;
    return sourceLinks([id]);
  }
  if(row.source_type==='message'){
    const exists=(snapshot.events??[]).some(e=>e?.body?.message_id===id);
    return exists?button('message-source','연구자 입력 원문',`data-id="${esc(id)}"`,'link-button small'):
      `<span class="ew-gap">입력 원문 연결 확인 필요 · <code>${esc(id)}</code></span>`;
  }
  return `<span class="ew-gap">출처 유형 확인 필요 · <code>${esc(id)}</code></span>`;
}
function evidenceWorkbenchQuote(row){
  const anchor=row?.anchor;
  const valid=anchor&&anchor.artifact_id===row.source_id&&typeof anchor.quote==='string'&&anchor.quote.trim();
  const location=valid&&Number.isInteger(anchor.offset)&&anchor.offset>=0?` · 원행 ${anchor.offset}`:'';
  return valid?`<blockquote>${esc(anchor.quote)}</blockquote><p class="ew-locator">원문 인용${location}</p>`:
    '<p class="ew-gap">확인 필요 · 원문 인용과 행 위치는 출처 상세에서 대조하세요.</p>';
}
function evidenceWorkbenchRow(row,snapshot){
  const relation=EVIDENCE_WORKBENCH_RELATION[row?.relation]??'관계 확인 필요';
  return `<article class="ew-row" data-source-id="${esc(row?.source_id??'')}">
    <header><strong>${esc(relation)}</strong><div class="ew-source">근거 출처: ${evidenceWorkbenchSource(row,snapshot)}</div></header>
    <dl><div><dt>대상·적용 조건</dt><dd>${esc(evidenceWorkbenchText(row?.applicability))}</dd></div>
      <div><dt>판단 기록의 해석</dt><dd>${esc(evidenceWorkbenchText(row?.detail))}</dd></div></dl>
    ${evidenceWorkbenchQuote(row)}</article>`;
}
function evidenceWorkbenchSearchItem(artifact){
  const summary=artifact.meta.summary;
  const query=artifact.meta?.arguments?.query??artifact.meta?.arguments?.condition??artifact.meta?.arguments?.entity??'';
  const more=summary.has_more===true||!!summary.next_cursor||!!summary.next_page_token;
  return `<li><strong>${esc(artifactName(artifact.id))}</strong><span>이 요청의 반환 ${summary.returned}행${more?' · 다음 페이지 있음':''}</span>
    ${query?`<small>검색 조건: ${esc(String(query))}</small>`:''}${sourceLinks([artifact.id])}</li>`;
}
function renderEvidenceWorkbench(snapshot=state){
  const scope=evidenceWorkbenchScope(snapshot),current=!!snapshot?.decision&&snapshot.decision_rev===snapshot.rev;
  const body=scope.claims.map(claim=>{
    const rows=Array.isArray(claim.evidence)?claim.evidence:[];
    const label={hypothesis:'가설',part:'부분 주장',alternative:'조건부 설명'}[claim.level]??'주장';
    return `<details class="ew-claim" data-detail-key="ew:${esc(claim.hypothesis_id??claim.id)}:${esc(claim.level)}:${esc(claim.claim_id)}" data-claim-id="${esc(claim.claim_id??'')}"><summary><span class="ew-kind">${label}</span>
      <strong>${esc(researcherWording(evidenceWorkbenchText(claim.statement,'주장 문장 확인 필요')))}</strong><span class="ew-state">${esc(EVIDENCE_WORKBENCH_ASSESSMENT[claim.assessment]??'판단 상태 확인 필요')}</span></summary>
      <div class="ew-claim-body"><p class="ew-id">기록 ID <code>${esc(claim.claim_id??'확인 필요')}</code>${claim.hypothesis_id&&claim.level!=='hypothesis'?` · 연결 가설 <code>${esc(claim.hypothesis_id)}</code>`:''}</p>
      <dl class="ew-claim-context"><div><dt>확인할 관측</dt><dd>${esc(researcherWording(evidenceWorkbenchText(claim.expected_observation)))}</dd></div>
      <div><dt>판단과 남은 조건</dt><dd>${esc(researcherWording(evidenceWorkbenchText(claim.rationale)))}</dd></div></dl>
      ${Array.isArray(claim.alternatives)&&claim.alternatives.length?`<section class="ew-uncertainty"><h4>경쟁 설명·남은 불확실성</h4><ul>${claim.alternatives.map(x=>`<li>${esc(evidenceWorkbenchText(x))}</li>`).join('')}</ul></section>`:''}
      <h4>이 주장에 직접 연결한 판독 ${rows.length}행</h4>${rows.length?rows.map(r=>evidenceWorkbenchRow(r,snapshot)).join(''):
        '<p class="ew-gap">확인 필요 · 이 주장에 직접 연결한 판독 기록</p>'}</div></details>`;
  }).join('');
  const searches=scope.searches.map(evidenceWorkbenchSearchItem).join('');
  return `<section class="evidence-workbench" aria-label="질문별 근거 검토와 판독 범위">
    <header class="ew-heading"><h3>주장과 원자료를 함께 검토</h3><p>${current?'현재 입력의 게시 판단':'이전 입력의 판단 또는 새 판단 전 기록'} · 검색 반환, 원문 회수, 판단 연결은 서로 다른 단계입니다.</p></header>
    <div class="ew-scope" aria-label="기록된 자료 범위"><div><span>검색 반환</span><strong>${scope.searches.length?scope.searches.length+'개 검색 기록':'기록 확인 필요'}</strong><small>반환 행 수는 각 검색 원자료에서 확인</small></div>
      <div><span>원문 본문 회수</span><strong>${scope.fullText.length?scope.fullText.length+'개 자료':'본문 반환 기록 확인 필요'}</strong><small>본문 파일을 회수한 기록</small></div>
      <div><span>판단에 연결한 근거</span><strong>${scope.evidence.length?scope.evidence.length+'개 판단 행':'판단 연결 확인 필요'}</strong><small>출처 ID 기준 원자료 ${scope.linked.length}개</small></div></div>
    <details class="ew-search" data-detail-key="ew-search"><summary>검색별 반환과 남은 페이지 ${scope.searches.length}건</summary>
      <p>각 검색의 반환 행과 남은 페이지를 검토합니다. 원문 회수와 판단 연결 현황은 위에 구분했습니다.</p>
      ${scope.searches.length?`<ul>${searches}</ul>`:'<p class="ew-gap">검색 반환 수를 기록한 원자료를 확인해야 합니다.</p>'}</details>
    ${renderSemanticLiterature(snapshot)}
    <div class="ew-claims"><h4>질문·주장별 근거</h4><p>기록된 적용 조건과 판단 해석을 그대로 놓았습니다. 원문 인용·원행은 출처 상세에서 대조하세요.</p>
      ${body||'<p class="ew-gap">확인 필요 · 구조화된 가설과 부분 주장</p>'}</div>
    <p class="ew-foot">효능 판단에 필요한 조건과 실제 관측은 연결된 원자료에서 확인합니다.</p>
  </section>`;
}
