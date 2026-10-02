Object.assign(SCIENCE_LABELS,{rna_duplex:'가이드·보조 가닥 설계안',rna_region_annotation:'RNA 후보의 CDS·UTR 구간',rna_duplex_seed:'가닥별 seed 위치',rna_duplex_transcriptome:'가닥별 긴 상보성 검색',rna_delivery_response:'전달 모형의 시점별 민감도'});
const REGION_NAMES={CDS:'CDS',five_prime_utr:'5′UTR',three_prime_utr:'3′UTR',stop_codon:'종결 코돈',no_region_annotation:'영역 미주석',unresolved_annotation:'참조 대응 미확정'};
function regionLabel(value){return (value??'').split('+').map(x=>REGION_NAMES[x]??x).join(' / ')}
function duplexEntry(){return button('science-duplex-dialog','보조 가닥·말단까지 설계안 비교',`data-id="${esc(selected)}"`,'primary small')}
function duplexCheckBoxes(rows,name,label){return `<fieldset><legend>${label}</legend><div class="dock-candidates">${rows.map(r=>`<label><input type="checkbox" name="${name}" value="${esc(r.id)}">${esc(r.source_candidate_id??r.id)}${r.overhang_variant?` · ${esc(r.overhang_variant)}`:''}<code class="sequence-text">${esc(r.guide_5to3)}</code></label>`).join('')}</div></fieldset>`}
function duplexTable(result){
 return `<p>어느 가닥·어떤 말단을 비교하는지 먼저 확인하세요. 이 결과는 <strong>합성 전 계산안</strong>이며, 기존 가이드 평가를 보존합니다.</p>
 <div class="duplex-grid">${result.rows.map(r=>`<article class="panel duplex-card"><h3>${esc(r.source_candidate_id)} · ${r.overhang_variant==='UU'?'양쪽3′UU':'돌출부 없음'}</h3>
 <dl class="duplex-sequences"><dt>가이드</dt><dd>${rnaNotation(r.guide_5to3,{strand:'guide',modifications:r.modifications,core_chemistry:r.source_core_chemistry,phosphorothioate_linkages:r.guide_phosphorothioate_linkages})}</dd><dt>보조 가닥</dt><dd>${rnaNotation(r.passenger_5to3,{strand:'passenger',modifications:r.modifications,core_chemistry:r.source_core_chemistry,phosphorothioate_linkages:r.passenger_phosphorothioate_linkages})}</dd></dl>${rnaNotationLegend(r.modifications)}${rnaDeliveryLine(r)}
 <p class="small">짝지음 ${r.paired_length}nt · 원 core ${esc(({unknown:'수식 미확인',unmodified:'무수식',modified:'수식 있음'})[r.source_core_chemistry]??r.source_core_chemistry)}</p>
 <p>5bp 말단 에너지 차 <strong>${number(r.guide_minus_passenger_5bp_kcal_mol)} kcal/mol</strong></p>
 <p class="small muted">가이드−보조 가닥의 무수식 모형 대비입니다. 적재율·효능 순위가 아닙니다.</p>
 <details><summary>말단·에너지 계산 조건 보기</summary><p>5′말단: 가이드 ${esc(r.guide_5prime_terminal_state)} / 보조 ${esc(r.passenger_5prime_terminal_state)}</p><p>전체 고정 구조 ${number(r.fixed_duplex.kcal_mol)} kcal/mol · 37°C</p><ul>${r.end_window_contrasts.map(x=>`<li>${x.paired_window}bp 대비: ${number(x.guide_minus_passenger_kcal_mol)} kcal/mol</li>`).join('')}</ul></details>${sourceLinks([r.source_candidate_artifact_id])}</article>`).join('')}</div>
 <div class="detail-actions">${button('science-duplex-long-dialog','보조 가닥의 긴 상보성 확인',`data-id="${esc(selected)}"`,'small')}${button('science-duplex-seed-dialog','보조 가닥의 짧은 seed 확인',`data-id="${esc(selected)}"`,'primary small')}${button('science-review','이 설계안으로 다음 판단 검토',`data-id="${esc(selected)}"`,'small')}</div>`;
}
function duplexSeedTable(result){
 const names={guide:'가이드',passenger:'보조 가닥'};
 return `<p>가닥별 실제3′UTR 위치 검색입니다. 같은 seed를 공유하는 돌출부 계산안은 한 번 검색했습니다. <strong>적재·독성 점수는 아닙니다.</strong></p>
 <div class="table-scroll"><table><thead><tr><th>원 후보·가닥</th><th>seed2–8</th><th>다른 유전자</th><th>m8/8mer 유전자</th><th>간TPM≥1 유전자</th></tr></thead><tbody>${result.candidate_summary.map(r=>{
 const links=result.strand_links.filter(x=>x.calculation_id===r.candidate_id);
 const labels=[...new Set(links.map(x=>`${x.source_candidate_id} · ${names[x.strand_role]}`))];
 return `<tr><td>${labels.map(esc).join('<br>')}<br><span class="small muted">설계 맥락 ${links.length}개</span></td><td><code>${esc(links[0]?.seed_2to8_5to3)}</code></td><td>${r.other_genes.toLocaleString()}</td><td>${r.m8_or8mer_other_genes.toLocaleString()}</td><td>${r.other_genes_with_liver_tpm_at_least['1'].toLocaleString()}</td></tr>`}).join('')}</tbody></table></div>
 <p class="small muted">유전자 중앙TPM은 해당 부위를 가진 isoform의 발현이 아닙니다. 가이드와 보조 가닥의 수를 더해 위험도를 만들지 않습니다.</p>
 <details><summary>반환된 개별 위치 보기</summary><div class="table-scroll"><table><thead><tr><th>검색ID</th><th>유전자</th><th>전사체</th><th>부위</th><th>유형</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(r.candidate_id)}</td><td>${esc(r.gene_symbol||r.gene_id)}</td><td>${esc(r.transcript_id)}</td><td>${r.utr_start_1_based}–${r.utr_end_1_based}</td><td>${esc(r.site_type)}</td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>${result.offset+1}–${result.offset+result.rows.length} / ${result.total_rows}</span>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></details>
 <div class="detail-actions">${button('science-review','가이드 근거와 함께 판단 갱신',`data-id="${esc(selected)}"`,'primary small')}</div>`;
}
function duplexLongTable(result){
 const labels={guide:'가이드',passenger:'보조 가닥'};
 const name=id=>[...new Set(result.strand_links.filter(x=>x.calculation_id===id).map(x=>`${x.source_candidate_id} · ${labels[x.strand_role]} · ${x.strand_5to3.length}nt`))].join(' / ');
 return `<p>돌출부를 포함한 전체 가닥으로 <strong>인간 전사체의 긴 상보성</strong>을 계산했습니다. 짧은seed 검색과 다른 근거이며, 두 결과를 합산해 안전성 점수를 만들지 않습니다.</p>
 <div class="table-scroll"><table><thead><tr><th>원 후보·가닥</th><th>주석 전사체 hit</th><th>다른 유전자</th><th>다른 유전자 최저 에너지</th></tr></thead><tbody>${result.candidate_summary.map(r=>`<tr><td>${esc(name(r.candidate_id))}</td><td>${r.annotated_transcript_hits.toLocaleString()}</td><td>${r.other_genes.toLocaleString()}</td><td>${number(r.best_other_gene_energy_kcal_mol)} kcal/mol</td></tr>`).join('')}</tbody></table></div>
 <p class="small muted">출력 상한 ${number(result.protocol.energy_cutoff_kcal_mol)} kcal/mol. 부위 존재가 적재·억제·독성을 입증하지 않으며 화학수식 에너지는 미반영입니다.</p>
 <details><summary>개별 정렬 위치와 별도 역상보 hit 보기</summary><div class="table-scroll"><table><thead><tr><th>가닥·유전자</th><th>전사체·위치</th><th>에너지</th><th>해석</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(name(r.candidate_id))}<br>${esc(r.gene_symbol||r.gene_id)}</td><td>${esc(r.transcript_id)}<br>${r.target_start_1_based}–${r.target_end_1_based}</td><td>${number(r.energy_kcal_mol)}</td><td>${r.index_strand==='-'?'합성 역상보 색인 · 실제 전사체 아님':r.same_target_gene?'원 표적 유전자':'다른 유전자 · 발현/억제 미확인'}</td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>${result.offset+1}–${result.offset+result.rows.length} / ${result.total_rows}</span>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></details>
 <div class="detail-actions">${button('science-review','짧은seed·기존 근거와 함께 판단 갱신',`data-id="${esc(selected)}"`,'primary small')}</div>`;
}
function deliveryResponseEntry(){return `<section class="panel science-form"><h3>관측 시점에 따라 다음 확인이 달라질까요?</h3><p>공개 마우스 전달 모형에서 탈출·적재·소실의 국소 영향을 비교합니다. 사람TTR 후보의 예측과 구분해 읽습니다.</p>${button('science-response-dialog','시점별 모형 민감도 비교','','small')}</section>`}
function deliveryResponseTable(result){result.focus_endpoint??='protein_suppression_at_24h_percent';return `<p><strong>마우스 AT / GalNAc 원모형</strong> · ${result.summary.dose_mg_kg}mg/kg · ${result.protocol.input.perturbation_factor===1.1?'10%':'5%'} 국소 변화. 사람TTR·새 후보의 효과가 아닙니다.</p>
 <label>보고 싶은 관측<select id="response-endpoint">${[...new Set(result.rows.map(r=>r.endpoint))].map(x=>`<option value="${esc(x)}" ${x===result.focus_endpoint?'selected':''}>${esc(responseEndpoint(x))}</option>`).join('')}</select></label>
 <div class="table-scroll"><table><thead><tr><th>변화시킨 항목</th><th>기준 출력</th><th>파라미터 감소 때</th><th>증가 때</th><th>국소 응답 계수</th></tr></thead><tbody>${result.rows.filter(r=>r.endpoint===result.focus_endpoint).map(r=>`<tr><td>${esc(responseParameter(r.parameter))}</td><td>${number(r.base_effect)}</td><td>${number(r.effect_minus)}</td><td>${number(r.effect_plus)}</td><td>${r.local_response_coefficient===null?'정의되지 않음':number(r.local_response_coefficient)}</td></tr>`).join('')}</tbody></table></div>
 <p class="small muted">계수는 같은 모형·시점의 변화율 비교이며 확률이 아닙니다. 값이 크다고 그 항목이 실제 병목이거나 나머지 후보를 제외해야 한다는 뜻은 아닙니다.</p>${button('science-review','현재 관측과 다음 확인에 연결',`data-id="${esc(selected)}"`,'primary small')}`}
function responseParameter(x){return ({fesc:'endosome 탈출 비율',kdegD:'endosome 분해 속도',kint:'수용체 내재화',Rtot:'수용체 총량',konRISC:'RISC 결합 속도',koffRISC:'RISC 해리 속도',kDR:'RISC 복합체 소실',kdegc:'세포질 siRNA 분해',kdegmRNA:'mRNA turnover',kdegprotein:'단백질 turnover'})[x]??x}
function responseEndpoint(x){const protein=x.startsWith('protein');const match=x.match(/at_(\d+)h/);return `${protein?'단백질':'mRNA'} 감소 · ${match?match[1]+'시간 (%)':'0–1000시간 누적 (%·시간)'}`}
document.addEventListener('change',event=>{if(event.target.id==='response-endpoint'){detail.result.focus_endpoint=event.target.value;render()}});
async function duplexAction(action,node){
 if(action==='science-region-filter'){rnaSpaceSearch={artifact:selected,query:node.dataset.query};offset=0;await readDetail();return}
 if(['science-duplex-dialog','science-duplex-seed-dialog','science-duplex-long-dialog'].includes(action)){
  const r=(await api(`/api/workspaces/${state.id}/artifacts/${node.dataset.id}?limit=100`)).result;
  if(action==='science-duplex-dialog'){
   const ends=(id,label)=>`<label>${label}<select id="${id}"><option value="unspecified">미정</option><option value="hydroxyl">5′OH</option><option value="phosphate">5′phosphate</option><option value="other_unmodeled">기타 · 아래에 설명</option></select></label>`;
   showDialog('어떤 이중가닥으로 이어갈까요?',`<p>가이드 core에 완전 상보인 보조 가닥을 붙이는 계산안입니다. 명시하지 않은 수식·제형은 미정으로 남습니다.</p>${duplexCheckBoxes(r.rows,'duplex-candidate','원 가이드 · 최대6개')}<fieldset><legend>돌출부 비교안</legend><label><input type="checkbox" name="duplex-variant" value="blunt" checked>돌출부 없음</label><label><input type="checkbox" name="duplex-variant" value="UU" checked>양쪽3′UU</label></fieldset><div class="science-fields">${ends('duplex-guide-end','가이드5′말단')}${ends('duplex-passenger-end','보조 가닥5′말단')}</div><label>알려진 수식·위치<input id="duplex-chemistry" placeholder="미정이면 비워 두세요. 예: 가이드7번…"></label><label>알려진 제형·접합<input id="duplex-formulation" placeholder="미정이면 비워 두세요"></label><p class="small muted">적은 화학 조건은 보존하지만 이번 열역학은 무수식37°C 모형입니다.</p>${button('science-duplex-run','설계안·말단 대비 실제 계산',`data-id="${esc(node.dataset.id)}"`,'primary')}`);
  }else {
   const long=action==='science-duplex-long-dialog';
   showDialog(long?'전체 가닥의 긴 상보성을 확인할까요?':'어느 가닥의 짧은seed를 확인할까요?',`${duplexCheckBoxes(r.rows,'duplex-design','설계안')}<label>검색할 가닥<select id="duplex-strand"><option value="passenger">보조 가닥 · 기존 가이드 결과는 유지</option><option value="guide">가이드</option><option value="both">양 가닥</option></select></label><p>${long?'돌출부를 포함한 전체 서열로 인간 전사체를 검색합니다. 서로 다른 전체 가닥은 한 번에12개까지 선택합니다.':'같은seed의 돌출부 변형은 한 번 검색합니다. 기존 가이드 계산이 있으면 보조 가닥만 추가할 수 있습니다.'}</p>${long?'<label>출력 에너지 상한 · kcal/mol<input id="duplex-long-energy" type="number" value="-20" min="-60" max="-1"></label><p class="small muted">상한 밖의 상호작용은 미검토로 남습니다. 화학수식·적재·실제 억제 확률을 계산하지 않습니다.</p>':''}${button(long?'science-duplex-long-run':'science-duplex-seed-run',long?'전체 가닥 실제 정렬':'선택 가닥 실제 seed 검색',`data-id="${esc(node.dataset.id)}"`,'primary')}`);
  }
  return;
 }
 if(action==='science-response-dialog'){
  showDialog('원 모형 안에서 무엇이 영향을 줄까요?',`<p>마우스AT/GalNAc의 관측 시간과 파라미터를 비교합니다. 환자 용량 추천이 아닙니다.</p><label>원 모형 용량<select id="response-dose"><option value="1">1mg/kg</option><option value="5">5mg/kg</option></select></label><label>양방향 국소 변화<select id="response-factor"><option value="1.1">10%</option><option value="1.05">5%</option></select></label><fieldset><legend>변화시킬 모형 항목</legend>${['fesc','kdegD','kint','Rtot','konRISC','koffRISC','kDR','kdegc','kdegmRNA','kdegprotein'].map(x=>`<label><input type="checkbox" name="response-parameter" value="${x}" checked>${responseParameter(x)}</label>`).join('')}</fieldset>${button('science-response-run','RNA·단백질 시간별 응답 계산','','primary')}`);return;
 }
 busy=true;node.disabled=true;
 const checked=name=>[...document.querySelectorAll(`input[name="${name}"]:checked`)].map(x=>x.value);
 try{
  if(action==='science-duplex-run'&&!checked('duplex-candidate').length)throw Error('원 가이드를 하나 이상 선택해 주세요.');
  if(action==='science-duplex-run')await runTool('rna_duplex',{artifact_id:node.dataset.id,candidate_ids:checked('duplex-candidate'),overhang_variants:checked('duplex-variant'),guide_5prime_state:document.querySelector('#duplex-guide-end').value,passenger_5prime_state:document.querySelector('#duplex-passenger-end').value,chemistry_description:document.querySelector('#duplex-chemistry').value,formulation_description:document.querySelector('#duplex-formulation').value});
  if(['science-duplex-seed-run','science-duplex-long-run'].includes(action)&&!checked('duplex-design').length)throw Error('검색할 설계안을 하나 이상 선택해 주세요.');
  if(action==='science-duplex-run'&&!checked('duplex-candidate').length)throw Error('원 가이드를 하나 이상 선택해 주세요.');
  if(action==='science-duplex-seed-run')await runTool('rna_duplex_seed',{artifact_id:node.dataset.id,duplex_ids:checked('duplex-design'),strand:document.querySelector('#duplex-strand').value});
  if(action==='science-duplex-long-run')await runTool('rna_duplex_transcriptome',{artifact_id:node.dataset.id,duplex_ids:checked('duplex-design'),strand:document.querySelector('#duplex-strand').value,energy_cutoff_kcal_mol:Number(document.querySelector('#duplex-long-energy').value)});
  if(action==='science-response-run')await runTool('rna_delivery_response',{dose_mg_kg:Number(document.querySelector('#response-dose').value),parameters:checked('response-parameter'),perturbation_factor:Number(document.querySelector('#response-factor').value)});
  if(action==='science-region-run')await runTool('rna_region_annotation',{artifact_id:node.dataset.id});
  dialog.close();
 }finally{busy=false;node.disabled=false;render()}
}
