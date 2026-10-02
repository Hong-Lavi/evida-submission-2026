Object.assign(SCIENCE_LABELS,{rna_tissue_context:'조직별 전사체 발현 조건',rna_variant_catalog:'참조 서열의 공개 변이',rna_allele_scenario:'변이 조건에서 후보 다시 비교'});
let rnaVariantSearch={artifact:null,query:''};
let rnaScenarioChoice=null;
const tissueStatusLabels={version_matched_reported:'같은 버전 · 정량 보고',version_matched_zero:'같은 버전 · 중앙값 0',version_mismatch:'버전 다름 · 값 미적용',not_in_returned_quantification:'정량 자료에 없음'};
const alleleEffectLabels={exact_site_lost:'정확 부위 소실',exact_site_gained:'정확 부위 새로 발견',exact_positions_changed:'정확 부위 위치 변경',exact_sites_unchanged:'정확 부위 동일',unresolved_unknown_bases:'미확인 염기로 부재 판단 보류'};

function rnaContextQuery(id){return rnaVariantSearch.artifact===id?`&candidate_query=${encodeURIComponent(rnaVariantSearch.query)}`:''}
function tissueOptionHtml(dataset){return (rnaTissueOptions[dataset]??[]).map(r=>`<option value="${esc(r.id)}" ${r.id==='Liver'?'selected':''}>${esc(r.id==='Liver'?'간 · Liver':r.label)}</option>`).join('')}
function contextPagination(r){return `<div class="pagination"><span>${r.rows.length?r.offset+1:0}–${r.offset+r.rows.length} / ${r.total_rows}행</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!r.has_more?'disabled':'','small')}</div></div>`}
function contextReviewButton(){return `<div class="detail-actions">${button('science-review','이 조건으로 다음 판단 갱신',`data-id="${esc(selected)}" ${busy?'disabled':''}`,'primary small')}</div>`}
function siteText(sites){return sites.map(s=>`${s.start_1_based}–${s.end_1_based}`).join(', ')||'정확 부위 없음'}

document.addEventListener('change',event=>{
 if(event.target.id==='context-dataset')document.getElementById('context-tissue').innerHTML=tissueOptionHtml(event.target.value);
 if(event.target.id==='scenario-evaluation')loadScenarioCandidates(event.target.value).catch(e=>notice(e.message));
});

async function loadScenarioCandidates(id){
 const node=document.getElementById('scenario-candidates');node.innerHTML='후보를 불러오는 중…';
 if(!id){node.innerHTML='비교할 기존 계산을 먼저 선택하세요.';return}
 const view=await api(`/api/workspaces/${state.id}/artifacts/${id}?limit=100`);
 if(document.getElementById('scenario-evaluation')?.value!==id)return;
 node.innerHTML=view.result.rows.map(r=>`<label><input type="checkbox" name="scenario-candidate" value="${esc(r.id)}">${esc(r.id)}<code class="sequence-text">${esc(r.guide_5to3)}</code></label>`).join('')+
  (view.result.has_more?'<p>현재 첫100개를 표시합니다. 나머지는 원 계산에 보존되며 도구에서 ID를 지정해 비교할 수 있습니다.</p>':'');
}

async function rnaContextAction(action,node){
 if(action==='science-context-tissue-dialog'){
  showDialog('이 후보의 전사체가 어느 조직에서 보고됐나요?',`<p>서열 대응 결과에 조직별 전사체 정량을 나란히 붙입니다. 데이터셋의 주석 버전부터 확인하며, 중앙값0·다른 버전·자료 없음을 구별합니다.</p>
   <label>정량 데이터셋<select id="context-dataset"><option value="gtex_v10">GTEx v10</option><option value="gtex_v8">GTEx v8 · 이전 주석 비교</option></select></label>
   <label>조직<select id="context-tissue">${tissueOptionHtml('gtex_v10')}</select></label>
   <p class="small muted">공여자의 bulk 조직 전사체 중앙 TPM입니다. 질환 세포·개별 환자의 억제 범위나 단백질 기여율이 아닙니다.</p>
   <div class="dialog-actions">${button('science-context-tissue-run','조직 근거 연결',`data-id="${esc(node.dataset.id)}"`,'primary')}</div>`);return;
 }
 if(action==='science-context-variant-dialog'){
  const refs=state.artifacts.filter(a=>['rna_reference','rna_reference_archive'].includes(a.kind)&&a.meta.summary?.requires_transcript_selection===false);
  showDialog('어느 참조의 변이 조건을 확인할까요?',`<p>보존 전사체의 exon 좌표와 공개 변이를 연결합니다. 변이 이름을 미리 알 필요는 없습니다. REF가 맞는 변이를 골라 별도의 서열 시나리오로 비교할 수 있습니다.</p>
   <label>실제 전사체 참조<select id="context-variant-reference">${refs.map(r=>`<option value="${esc(r.id)}" ${r.id===node.dataset.reference?'selected':''}>${esc(r.meta.arguments?.ensembl_id??r.title)} · ${esc(r.meta.summary.length)}nt</option>`).join('')}</select></label>
   <p class="small muted">인간 GRCh38·Ensembl115의 같은 버전 GTF가 필요합니다. 한 번에250kb 이하 전사체 영역을 조회하며, 환자 유전자형을 추정하지 않습니다.</p>
   <div class="dialog-actions">${button('science-context-variant-run','공개 변이 확인','','primary')}</div>`);return;
 }
 if(action==='science-context-variant-search'){
  rnaVariantSearch={artifact:selected,query:document.getElementById('variant-query').value.trim()};offset=0;await readDetail();return;
 }
 if(action==='science-context-scenario-dialog'){
  const row=detail.result.rows.find(r=>r.variant_key===node.dataset.variant);
  if(!row||row.mapping.status!=='ref_verified')throw Error('REF를 확인한 변이 행을 다시 선택해 주세요.');
  rnaScenarioChoice={catalog_id:selected,variant_key:row.variant_key};
  const evaluations=state.artifacts.filter(a=>['rna_sequence_evaluation','rna_candidate_generation'].includes(a.kind)&&a.meta.result_status==='succeeded');
  showDialog('이 변이 조건에서 후보를 다시 비교합니다',`<p><strong>${esc(row.variant_id)}</strong> · ${esc(row.source_record.seq_region_name)}:${row.source_record.start}–${row.source_record.end} · REF ${esc(row.source_record.alleles[0])}</p>
   <label>비교할 ALT · 공개 기록의 가닥 기준<select id="scenario-alt">${row.mapping.available_alternates.map(a=>`<option value="${esc(a)}">${esc(a==='-'?'삭제 (-)':a)}</option>`).join('')}</select></label>
   <label>후보를 가져올 기존 계산<select id="scenario-evaluation"><option value="">계산 결과 선택</option>${evaluations.map(a=>`<option value="${esc(a.id)}">${esc(artifactName(a.id))}</option>`).join('')}</select></label>
   <fieldset><legend>다시 대조할 후보 · 원 결과와 다른 후보도 유지</legend><div id="scenario-candidates" class="dock-candidates">기존 계산을 선택하면 후보가 나타납니다.</div></fieldset>
   <label>이 조건을 확인하려는 이유<textarea id="scenario-reason" placeholder="예: 삭제 때문에 원 후보의 부위가 없어지는지, 온전한 하류 부위는 위치만 바뀌는지 비교합니다."></textarea></label>
   <p class="small muted">연구자/환자의 관측이 아닌 공개 단일 allele 서열 시나리오입니다. 원 참조를 덮어쓰지 않으며, 정확 부위가 없다는 결과는 억제 실패 판정이 아닙니다.</p>
   <div class="dialog-actions">${button('science-context-scenario-run','원 참조와 변이 조건 실제 비교','','primary')}</div>`);return;
 }
 busy=true;node.disabled=true;
 try{
  if(action==='science-context-tissue-run')await runTool('rna_tissue_context',{artifact_id:node.dataset.id,dataset:document.getElementById('context-dataset').value,tissue:document.getElementById('context-tissue').value});
  else if(action==='science-context-variant-run')await runTool('rna_variant_catalog',{artifact_id:document.getElementById('context-variant-reference').value});
  else if(action==='science-context-scenario-run'){
   const ids=[...document.querySelectorAll('[name="scenario-candidate"]:checked')].map(x=>x.value),reason=document.getElementById('scenario-reason').value.trim();
   if(!ids.length||!reason)throw Error('비교할 후보와 이유를 선택해 주세요.');
   await runTool('rna_allele_scenario',{...rnaScenarioChoice,artifact_id:document.getElementById('scenario-evaluation').value,variant_key:rnaScenarioChoice.variant_key,alternate:document.getElementById('scenario-alt').value,candidate_ids:ids,reason});
  }
  dialog.close();notice('실제 근거 조회·계산을 시작했습니다. 원 참조·결과는 보존합니다.');
 }finally{busy=false;node.disabled=false;render()}
}

function rnaTissueTable(r){
 const s=r.summary;
 return `<p class="notice-inline">${esc(s.dataset)} · ${esc(s.tissue)} · ${s.selected_references}개 선택 전사체</p>
  <p>후보의 서열 일치와 조직 정량은 다른 확인입니다. 같은 버전의 정량만 붙이며, 다른 버전의 원값도 펼쳐 볼 수 있습니다.</p>
  <p class="small">${Object.entries(s.transcript_status_counts).map(([k,v])=>`${esc(tissueStatusLabels[k])} ${v}개`).join(' · ')}</p>
  <div class="table-scroll"><table><thead><tr><th>후보</th><th>전사체 · 주석</th><th>정확 부위</th><th>조직 중앙 TPM</th><th>대응 상태·원값</th></tr></thead><tbody>${r.rows.map(x=>`<tr><td>${esc(x.candidate_id)}</td><td>${esc(x.transcript_id)}.${esc(x.version)}<br>${esc(x.annotation_biotype??'미확인')}</td><td>${siteText(x.exact_sites)}</td><td>${x.tissue_context.median_tpm===null?'—':number(x.tissue_context.median_tpm)}</td><td>${esc(tissueStatusLabels[x.tissue_context.status])}<details><summary>왜 이 상태인가요?</summary><p>${esc(x.tissue_context.interpretation)}</p>${x.tissue_context.source_rows.map(a=>`<p>${esc(a.transcriptId)} · ${number(a.median)} ${esc(a.unit)}</p>`).join('')}${sourceLinks([x.reference_artifact_id])}</details></td></tr>`).join('')}</tbody></table></div>
  <p class="limit">환자·표본별 표적 보유 비율을 계산하지 않았습니다. 단백질 분비 기여·RISC·전달·기능은 별도 조건입니다.</p>${contextPagination(r)}${contextReviewButton()}`;
}

function rnaVariantTable(r){
 return `<p class="notice-inline">${esc(r.summary.transcript_accession)} · ${esc(r.summary.region)} · ${r.summary.variants_returned}개 공개 변이</p>
  <p>REF 대응 확인 ${r.summary.ref_verified}개 · 미적용 ${r.summary.not_applied}개. 모든 반환행을 보존하며 목록 순서는 추천 순위가 아닙니다.</p>
  <label>변이 ID·위치·적용 상태 검색<input id="variant-query" value="${esc(r.candidate_query??'')}" placeholder="예: rs 번호 또는 ref_verified"></label>${button('science-context-variant-search','보존 변이에서 찾기','','small')}
  <details><summary>참조 exon 좌표와 적용 조건</summary><p>${esc(r.reference.assembly)} · ${esc(r.reference.organism)} · 가닥 ${esc(r.geometry.strand)}</p><ul>${r.geometry.exons.map(e=>`<li>exon ${e.exon_number} · ${esc(e.chromosome)}:${e.start}–${e.end}</li>`).join('')}</ul>${sourceLinks([r.reference_artifact_id])}<p class="small muted">같은 버전·유전자·길이·서열 해시에 연결한 GTF 대응입니다. 환자 서열이나 스플라이싱 결과가 아닙니다.</p></details>
  <div class="table-scroll"><table><thead><tr><th>공개 변이</th><th>유전체 위치 · REF/ALT</th><th>서열 적용</th><th>다음 작업</th></tr></thead><tbody>${r.rows.map(x=>`<tr><td>${esc(x.variant_id)}</td><td>${esc(x.source_record.seq_region_name)}:${x.source_record.start}–${x.source_record.end}<br>${esc(x.source_record.alleles?.join(' / '))}</td><td>${esc(x.mapping.reason)}</td><td>${x.mapping.status==='ref_verified'?button('science-context-scenario-dialog','이 조건으로 비교',`data-variant="${esc(x.variant_key)}"`,'small'):'미적용 · 원행 보존'}</td></tr>`).join('')}</tbody></table></div>
  <p class="limit">공개 목록에 있다고 환자에게 그 변이가 있거나 질환 원인이라는 뜻은 아닙니다. exon 밖·경계 영향과 phase는 별도 검토합니다.</p>${contextPagination(r)}`;
}

function rnaAlleleTable(r){
 return `<p class="notice-inline">${esc(r.summary.variant_id)} · ALT ${esc(r.summary.alternate)} · 별도 단일 allele 시나리오</p><p>${esc(r.selection_reason)}</p>
  <p>원 ${esc(r.reference.transcript_id)}.${esc(r.reference.version)}과 비교 · cDNA 길이 변화 ${r.summary.length_change_nt}nt</p>
  <div class="table-scroll"><table><thead><tr><th>후보</th><th>원 참조의 정확 부위</th><th>시나리오의 정확 부위</th><th>차이</th></tr></thead><tbody>${r.rows.map(x=>`<tr><td>${esc(x.candidate_id)}</td><td>${siteText(x.original.exact_sites)}<details><summary>원 유전체 대응</summary>${x.original_genomic_sites.map(s=>`<p>${s.cdna_site.start_1_based}–${s.cdna_site.end_1_based}: ${s.genomic_blocks.map(b=>`${esc(b.chromosome)}:${b.start_1_based}–${b.end_1_based} (${esc(b.strand)}, exon${b.exon_number})`).join(' + ')}</p>`).join('')}</details></td><td>${siteText(x.scenario.exact_sites)}<br><span class="small muted">알려진 창 최소 불일치 ${x.scenario.minimum_gapless_mismatches??'미확정'}</span></td><td>${esc(alleleEffectLabels[x.effect])}</td></tr>`).join('')}</tbody></table></div>
  <p class="limit">원 참조와 다른 시나리오 좌표입니다. 위치 변경과 정확 부위 소실을 구분하며, 실제 억제·환자 유전자형·스플라이싱 효과는 계산하지 않았습니다.</p>${contextPagination(r)}${contextReviewButton()}`;
}
