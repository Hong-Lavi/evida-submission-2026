SCIENCE_LABELS.rna_candidate_space='RNA 전체 후보 구간';
SCIENCE_LABELS.rna_candidate_selection='선택한 RNA 후보 실제 계산';
let rnaSpaceSearch={artifact:null,query:''};

function candidateSpaceQuery(id){
 return rnaSpaceSearch.artifact===id?`&candidate_query=${encodeURIComponent(rnaSpaceSearch.query)}`:'';
}

async function candidateSpaceAction(action,node){
 if(action==='science-space-dialog'){
  const refs=state.artifacts.filter(a=>['rna_reference','rna_reference_archive'].includes(a.kind)&&a.meta.summary?.requires_transcript_selection===false);
  const previous=state.artifacts.filter(a=>['rna_candidate_generation','rna_sequence_evaluation'].includes(a.kind)&&a.meta.result_status==='succeeded');
  showDialog('어느 전사체에서 후보를 찾을까요?',`<p>선택한 참조의 모든 상보 영역을 보존합니다. 후보를 먼저 알 필요는 없습니다. 여러 참조를 고르면 같은 가이드의 모든 출처를 함께 볼 수 있습니다.</p>
   <fieldset><legend>실제 전사체 서열 · 같은 유전자/종/assembly</legend><div class="dock-candidates">${refs.map(a=>`<label><input type="checkbox" name="space-reference" value="${esc(a.id)}" ${node.dataset.reference===a.id?'checked':''}>${esc(a.meta.arguments?.ensembl_id??a.title)} · ${esc(a.meta.summary.length)}nt</label>`).join('')||'<p>먼저 전사체 서열을 받아 주세요.</p>'}</div></fieldset>
   <label>상보 영역 길이 · nt<input id="space-length" type="number" min="19" max="30" value="19"></label>
   <details><summary>이전 평가의 후보 ID도 연결하기 · 선택 사항</summary><div class="dock-candidates">${previous.map(a=>`<label><input type="checkbox" name="space-prior" value="${esc(a.id)}">${esc(artifactName(a.id))}</label>`).join('')||'<p>이전 평가가 없습니다.</p>'}</div><p class="small muted">연결하지 않은 이전 자료도 삭제되지 않습니다.</p></details>
   <p class="small muted">미확인 염기가 있는 창은 미확정으로 남깁니다. 목록 순서는 효능 순위가 아니며, 열역학·비표적·전달은 후보 선택 후 별도로 계산합니다.</p>
   <div class="dialog-actions">${button('science-space-run','전체 구간에서 후보 찾기','','primary')}</div>`);
  return;
 }
 if(action==='science-space-search'){
  rnaSpaceSearch={artifact:selected,query:document.getElementById('space-query').value.trim()};
  offset=0;await readDetail();return;
 }
 if(action==='science-space-pick'){
  const row=detail.result.rows.find(r=>r.id===node.dataset.candidate);
  if(!row)throw Error('후보를 다시 열어 주세요.');
  const origins=[...new Map(row.origins.map(o=>[o.reference_artifact_id,o])).values()];
  showDialog('선택한 후보를 실제로 계산합니다',`<p>${rnaNotation(row.guide_5to3,{strand:'guide',modifications:row.modifications,core_chemistry:row.source_core_chemistry})}</p><p>${row.origins.length}개 원위치가 있는 ${row.length}nt 상보 영역입니다. 후보 선택만으로 효능이 확인되지는 않습니다.</p>
   <label>접근성을 계산할 참조<select id="space-eval-reference">${origins.map(o=>`<option value="${esc(o.reference_artifact_id)}">${esc(o.transcript_id)}.${esc(o.version)} · ${o.start_1_based}–${o.end_1_based}</option>`).join('')}</select></label>
   <label>RNA 수식 상태<select id="space-eval-chemistry"><option value="unknown">미확인 · 무수식 서열 대리 계산</option><option value="unmodified">무수식 RNA</option><option value="modified">수식 있음 · 무수식 서열 대리 계산</option></select></label>
   <label>왜 이 후보를 확인하나요?<textarea id="space-eval-reason" placeholder="예: 기존 후보가 다루지 않은 구간의 접근성과 다른 전사체 대응을 비교하고 싶습니다."></textarea></label>
   <details><summary>모든 원위치·기존 계산 연결</summary>${candidateOriginDetails(row)}</details>
   <div class="dialog-actions">${button('science-space-evaluate','선택 후보 실제 계산',`data-id="${esc(selected)}" data-candidate="${esc(row.id)}"`,'primary')}</div>`);
  return;
 }
 busy=true;node.disabled=true;
 try{
  if(action==='science-space-run'){
   const reference_ids=[...document.querySelectorAll('[name="space-reference"]:checked')].map(x=>x.value);
   if(!reference_ids.length)throw Error('실제 전사체 서열을 하나 이상 선택해 주세요.');
   const prior_candidate_artifact_ids=[...document.querySelectorAll('[name="space-prior"]:checked')].map(x=>x.value);
   if(prior_candidate_artifact_ids.length>20)throw Error('한 번에 연결할 이전 평가를20개 이내로 골라 주세요. 원 결과는 모두 보존됩니다.');
   await runTool('rna_candidate_space',{reference_ids,paired_length:Number(document.getElementById('space-length').value),prior_candidate_artifact_ids});
  }else if(action==='science-space-evaluate'){
   const reason=document.getElementById('space-eval-reason').value.trim();
   if(!reason)throw Error('선택 이유를 남겨 주세요.');
   await runTool('rna_candidate_selection',{artifact_id:node.dataset.id,candidate_ids:[node.dataset.candidate],reference_id:document.getElementById('space-eval-reference').value,chemistry:document.getElementById('space-eval-chemistry').value,reason});
  }
  dialog.close();notice('작업을 시작했습니다. 원 후보와 기존 결과는 보존됩니다.');
 }finally{busy=false;node.disabled=false;render()}
}

function candidateOriginDetails(row){
 return `<ul>${row.origins.map(o=>`<li>${esc(o.transcript_id)}.${esc(o.version)} · ${o.start_1_based}–${o.end_1_based}${o.annotated_region?` · ${esc(regionLabel(o.annotated_region))}`:''} ${sourceLinks([o.reference_artifact_id])}</li>`).join('')}</ul>
 ${row.prior_evaluations.length?`<p>기존 평가: ${row.prior_evaluations.map(p=>`${esc(p.candidate_id)} ${sourceLinks([p.artifact_id])}`).join(' · ')}</p>`:'<p>이번 열거에 연결한 이전 평가 없음 · 효능 미평가</p>'}`;
}

function rnaSelectedCandidateSummary(result){
 const s=result.selection;
 return `<section class="panel"><h3>이 후보를 고른 이유</h3><p>${esc(s.reason)}</p>
  <p class="small muted">전체 ${s.source_pool_summary.unique_guide_sequences.toLocaleString()}개 서열 중 ${s.selected_candidate_ids.length}개를 이번 조건에서 실제 계산했습니다. 나머지 후보와 이전 결과는 보존됩니다.</p>
  <p>참조 ${esc(result.reference.transcript_id)}.${esc(result.reference.version)} · ${sourceLinks([s.reference_artifact_id])}</p></section>`;
}

function rnaCandidateSpaceTable(result){
 const s=result.summary;
 return `<p class="notice-inline">${s.selected_references}개 전사체의 ${s.known_base_origins.toLocaleString()}개 원위치 → ${s.unique_guide_sequences.toLocaleString()}개 가이드 서열</p>
  <p>모든 알려진 염기의 구간을 보존했습니다. 목록은 효능 순위가 아닙니다. 후보를 골라 실제 계산하고, 그 결과로 다음 판단을 갱신할 수 있습니다.</p>
  ${result.region_annotation?`<p>같은 버전의 기능 영역을 원위치별로 연결했습니다.</p><div class="detail-actions">${[['three_prime_utr','3′UTR 포함'],['five_prime_utr','5′UTR 포함'],['CDS','CDS 포함'],['','전체']].map(([query,label])=>button('science-region-filter',label,`data-query="${query}"`,'small')).join('')}</div>`:button('science-region-run','CDS·UTR 영역 확인',`data-id="${esc(selected)}"`,'small')}
  <label>후보 ID·서열·전사체·위치·영역으로 찾기<input id="space-query" value="${esc(result.candidate_query??'')}" placeholder="예: ENST00000237014:100-118 또는 가이드 서열"></label>
  ${button('science-space-search','전체 보존 후보에서 찾기','','small')}
  <p class="small muted">현재 ${result.total_rows.toLocaleString()}개 표시 대상 / 전체 ${s.unique_guide_sequences.toLocaleString()}개 · 미확인 염기 창 ${s.unknown_base_windows}개 · 선택 밖 참조는 미검색</p>
  <div class="table-scroll"><table><thead><tr><th>가이드 · 5′→3′</th><th>출처·이전 평가</th><th>현재 상태</th><th>다음 작업</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${rnaNotation(r.guide_5to3,{strand:'guide',modifications:r.modifications,core_chemistry:r.source_core_chemistry})}<small>${esc(r.id)}</small></td><td><details><summary>${r.origins.length}개 원위치 · 이전 평가 ${r.prior_evaluations.length}개</summary>${candidateOriginDetails(r)}</details></td><td>서열 열거 완료<br><span class="small muted">효능·조직 발현 미평가</span></td><td>${button('science-space-pick','이 후보 계산',`data-candidate="${esc(r.id)}"`,'small')}</td></tr>`).join('')}</tbody></table></div>
  ${!result.rows.length?'<p>일치하는 후보가 없습니다. 검색 조건 밖 후보도 모두 보존되어 있습니다.</p>':''}
  <div class="pagination"><span>${result.rows.length?result.offset+1:0}–${result.offset+result.rows.length} / ${result.total_rows}개</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div>
  <p class="limit">상보 영역의 목록이며 완성 siRNA 설계가 아닙니다. 선택한 후보의 접근성·전사체 대응·비표적을 따로 확인하세요.</p>`;
}
