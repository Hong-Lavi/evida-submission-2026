SCIENCE_LABELS.rna_reference_panel='후보별 전사체·버전 대응';

document.addEventListener('change',event=>{
 if(event.target.id==='panel-focus-candidate')focusReferencePanel(event.target.value).catch(error=>notice(error.message));
});

async function focusReferencePanel(candidate){
 const id=selected,wid=state.id;
 offset=0;
 if(!candidate){await readDetail();return}
 const result=await api(`/api/workspaces/${wid}/artifacts/${id}?download=1`);
 if(selected!==id||state.id!==wid)return;
 const rows=result.rows.filter(row=>row.candidate_id===candidate);
 detail={artifact_id:id,result:{...result,rows,panel_focus_candidate:candidate,
   total_rows:rows.length,panel_total_rows:result.rows.length,offset:0,has_more:false}};
 render();
}

async function referencePanelAction(action,node){
 if(action==='science-reference-panel'){
  const view=await api(`/api/workspaces/${state.id}/artifacts/${node.dataset.id}?limit=100`);
  const refs=state.artifacts.filter(a=>['rna_reference','rna_reference_archive'].includes(a.kind)&&a.meta.summary?.requires_transcript_selection===false);
  showDialog('다른 전사체에도 같은 부위가 있을까요?',`<p>비교할 후보와 실제 서열을 선택합니다. 같은 유전자의 전사체 버전별 일치 부위를 계산하며, 조직 발현이나 억제 효과는 별도로 확인합니다.</p>
   <fieldset><legend>후보</legend><div class="dock-candidates">${view.result.rows.map(r=>`<label><input type="checkbox" name="panel-candidate" value="${esc(r.id)}">${esc(r.id)}<code class="sequence-text">${esc(r.guide_5to3)}</code></label>`).join('')}</div></fieldset>
   <fieldset><legend>대조할 전사체 서열</legend><div class="dock-candidates">${refs.map(r=>`<label><input type="checkbox" name="panel-reference" value="${esc(r.id)}">${esc(r.meta.arguments?.ensembl_id??r.title)} · ${esc(r.meta.summary.length)}nt</label>`).join('')||'<p>먼저 RNA 작업에서 필요한 전사체 서열을 받아 주세요.</p>'}</div></fieldset>
   <p class="small muted">선택 밖 isoform·변이는 이번 계산에서 확인하지 않습니다. 같은 전사체의 중복 사본은 하나만 선택하세요.</p>
   <div class="dialog-actions">${button('science-run-reference-panel','선택한 서열에 실제 대조',`data-id="${esc(node.dataset.id)}"`,'primary')}</div>`);
  return;
 }
 busy=true;node.disabled=true;
 try{
  const candidate_ids=[...document.querySelectorAll('input[name="panel-candidate"]:checked')].map(x=>x.value);
  const reference_ids=[...document.querySelectorAll('input[name="panel-reference"]:checked')].map(x=>x.value);
  if(!candidate_ids.length||!reference_ids.length)throw Error('후보와 전사체를 각각 하나 이상 선택해 주세요.');
  await runTool('rna_reference_panel',{artifact_id:node.dataset.id,candidate_ids,reference_ids});
  dialog.close();
 }finally{busy=false;node.disabled=false;render()}
}

function rnaReferencePanelTable(result){
 const statusNames={exact_site_present:'정확 일치 부위 있음',no_exact_site:'정확 일치 없음',unresolved_unknown_bases:'N 염기로 미확정'};
 return `${button('science-context-tissue-dialog','조직 발현 조건 함께 보기',`data-id="${esc(selected)}"`,'primary small')}${button('science-space-dialog','기존 후보 밖의 전체 구간 찾기','','small')}<p class="notice-inline">선택한 ${result.summary.selected_references}개 전사체의 서열 비교 · 조직 발현·효능은 별도 확인</p>
 <label>어떤 후보의 전사체 대응을 볼까요?<select id="panel-focus-candidate"><option value="">전체 ${result.summary.selected_candidates}개 후보 · ${result.summary.comparison_rows}개 비교</option>${result.candidate_summary.map(c=>`<option value="${esc(c.candidate_id)}" ${result.panel_focus_candidate===c.candidate_id?'selected':''}>${esc(c.candidate_id)} · 일치 ${c.references_with_exact_site} / ${result.summary.selected_references}${c.references_unresolved?` · 미확정 ${c.references_unresolved}`:''}</option>`).join('')}</select></label>
 <p class="small muted">일치 개수는 효능 순위가 아닙니다. 전사체 주석과 실제 조직 발현을 함께 확인하세요. 전체 결과는 그대로 보존됩니다.</p>
 <div class="table-scroll"><table><thead><tr><th>후보</th><th>전사체·버전</th><th>일치 상태</th><th>실제 위치 · 1부터</th><th>원 참조</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(r.candidate_id)}</td><td>${esc(r.transcript_id)}.${esc(r.version)}<br><span class="small muted">${esc(r.annotation_biotype??"주석 미확인")}</span></td><td>${esc(statusNames[r.match_status])}${r.unknown_windows?` · 미확정 창 ${r.unknown_windows}개`:''}</td><td>${r.exact_sites.map(s=>`${s.start_1_based}–${s.end_1_based}`).join(', ')||'—'}</td><td>${sourceLinks([r.reference_artifact_id])}</td></tr>`).join('')}</tbody></table></div>
 <p class="limit">일치하지 않는 서열과 미확정 항목도 보존했습니다. 일치 없음은 효과 없음이라는 실험 결과가 아닙니다. 선택 밖 전사체·변이는 아직 미확인입니다.</p>
 <div class="pagination"><span>${result.panel_focus_candidate?'선택 후보 · ':''}${result.offset+1}–${result.offset+result.rows.length} / ${result.total_rows}행</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div>
 <div class="detail-actions">${button('science-review','이 차이로 다음 판단 갱신',`data-id="${esc(selected)}" ${busy?'disabled':''}`,'primary small')}</div>`;
}
