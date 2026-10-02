// On-demand published relationships. Opening history starts no model or science job.
let evidenceHistorySelection = null;
const edgeHistoryLabels = {same_recorded_link:'이번 목록에도 같은 연결이 있음',recorded_link_changed:'이번 목록에서 관계·설명이 달라짐',not_in_current_list:'이번 근거 목록에는 없음'};

function evidenceHistoryButton(h, published) {
  if(!published || state.events.filter(e=>e.kind==='decision_published').length<2)return '';
  return `<div class="detail-actions">${button('evidence-history','이전 근거와 적용 조건 보기',`data-hypothesis="${esc(h.id)}" data-offset="0"`,'small')}</div>`;
}

function historyEvidenceRow(row) {
  const e=row.edge;
  return `<article class="evidence-relation"><div class="evidence-label">당시 ${esc(relationLabels[e.relation]??e.relation)} · ${esc(edgeHistoryLabels[row.comparison])}</div>${row.part_id?`<p>당시 부분 주장: ${esc(row.part_statement)}</p>`:''}${row.explanation_id?`<p>당시 설명: ${esc(row.explanation_statement)}</p>${list(row.explanation_conditions??[])}`:''}<p>${esc(e.detail)}</p><p class="limit">당시 적용 조건: ${esc(e.applicability)}</p>${e.source_type==='artifact'?sourceLinks([e.source_id]):button('message-source','당시 연구자 입력',`data-id="${esc(e.source_id)}"`,'small')}${row.comparison==='recorded_link_changed'?`<details><summary>이번 기록과 비교</summary>${row.current_links.map(c=>`<p>현재 기록: ${esc(relationLabels[c.edge.relation])}</p><p>${esc(c.edge.detail)}</p><p class="limit">현재 적용 조건: ${esc(c.edge.applicability)}</p>`).join('')}</details>`:''}</article>`;
}

async function openEvidenceHistory(hypothesisId,offset=0) {
  const wid=state.id,decisionId=state.decision_id;
  const value=await api(`/api/workspaces/${encodeURIComponent(wid)}/hypothesis-history?hypothesis_id=${encodeURIComponent(hypothesisId)}&offset=${offset}&limit=4`);
  if(state.id!==wid||state.decision_id!==decisionId)throw Error('판단이 바뀌었습니다. 최신 화면에서 다시 열어 주세요.');
  evidenceHistorySelection={wid,decisionId,value};
  showDialog('이전 근거와 적용 조건',`<p class="notice-inline">${esc(value.meaning)}</p>${value.current_content_status!=='available'?'<p class="limit">현재 판단의 원본을 확인하지 못했습니다. 비교 상태를 확정하지 마세요.</p>':''}${value.rows.map(r=>`<details class="history-evidence-decision" ${!r.is_current?'open':''}><summary>${r.is_current?'현재 판단':'이전 판단'} · 연구 기록 ${r.state_revision} · ${esc(time(r.created))}</summary>${r.content_status!=='available'?'<p class="limit">원 판단을 읽을 수 없거나 무결성 검사가 실패했습니다. 이는 과학적 반대 근거가 아닙니다.</p>':r.hypothesis?`<h3>${esc(r.hypothesis.statement)}</h3><p class="small">당시 예상: ${esc(r.hypothesis.expected_observation)}</p><p>당시 판단: ${esc(hypothesisLabels[r.hypothesis.assessment])}</p>${r.claim_comparison==='literal_claim_changed'?'<p class="notice-inline">현재 가설과 문구가 다릅니다. 아래 관계는 당시 주장에 대한 기록입니다.</p>':'<p class="small muted">같은 문구여도 대상·시험·조건이 달라질 수 있습니다. 현재 지지로 자동 승계하지 않습니다.</p>'}${r.evidence_comparison.length?r.evidence_comparison.map(historyEvidenceRow).join(''):'<p class="small muted">이 판단에는 근거 연결이 기록되어 있지 않습니다. 앞선 판단과 원자료는 계속 확인할 수 있습니다.</p>'}${r.context_artifact_id?`<p>당시 별도로 기록한 조건</p>${sourceLinks([r.context_artifact_id])}`:''}${sourceLinks([r.decision_id])}${button('history-evidence-feedback','이 근거를 현재 질문에서 다시 검토',`data-decision="${esc(r.decision_id)}"`,'small')}`:'<p class="small muted">이 판단에는 해당 ID의 가설이 없습니다. 기각으로 해석하지 않습니다.</p>'}</details>`).join('')}${value.lineage_gap?'<p class="limit">기록된 이전 판단 연결이 여기서 끊깁니다. 임의의 다른 판단으로 이어 붙이지 않았습니다.</p>':''}<div class="detail-actions">${offset?button('evidence-history','더 최근 판단',`data-hypothesis="${esc(hypothesisId)}" data-offset="${Math.max(0,offset-4)}"`,'small'):''}${value.has_more?button('evidence-history','더 이전 판단',`data-hypothesis="${esc(hypothesisId)}" data-offset="${offset+4}"`,'small'):''}</div><p class="small muted">이 화면을 열어도 새 조사나 평가 변경은 실행되지 않습니다.</p>`);
}

async function reviewHistoricalEvidence(decisionId) {
  const selected=evidenceHistorySelection;
  if(!selected||selected.wid!==state.id||selected.decisionId!==state.decision_id)throw Error('최신 판단에서 근거 이력을 다시 열어 주세요.');
  const row=selected.value.rows.find(r=>r.decision_id===decisionId&&r.content_status==='available'&&r.hypothesis);
  if(!row)throw Error('열람한 이전 판단을 선택해 주세요.');
  const previous=await api(`/api/workspaces/${encodeURIComponent(state.id)}/artifacts/${encodeURIComponent(decisionId)}?download=1`);
  if(selected.wid!==state.id||selected.decisionId!==state.decision_id)throw Error('판단이 바뀌었습니다. 다시 확인해 주세요.');
  openResearchFeedback(null,row.hypothesis.id,null,{decision:previous,decision_id:decisionId});
  dialog.querySelector('#feedback-kind').value='message';
  dialog.querySelector('#feedback-text').value=`이전 판단의 근거를 현재 질문에서 다시 검토해 주세요.\n당시 주장: ${row.hypothesis.statement}\n당시 판단: ${decisionId}\n원 적용 조건과 반대 근거를 보존하고, 현재 주장에 계속 쓸 수 있는 관계와 다시 확인할 부분을 구분해 주세요. 이는 새 관측이나 과거 판단의 자동 채택이 아닙니다.`;
  dialog.querySelector('[data-action="save-feedback"][data-review="true"]').textContent='이 근거 다시 검토';
}

function renderTransportHandle(part) {
  return button('transport-handle','전달 표기',`data-original="${esc(part)}" aria-label="원 응답의 자료 전달 표기 보기"`,'inline-source-link');
}
