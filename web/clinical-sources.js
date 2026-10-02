Object.assign(SCIENCE_LABELS,{binding_measurements:'결합·활성 원자료 · BindingDB',drug_label_search:'약물 라벨 목록',drug_label:'약물의 적용 조건·시험',clinical_trial_search:'등록 시험 목록',clinical_trial:'시험의 대상·결과'});
Object.assign(SCIENCE_LABELS,{public_lookup_bundle:'함께 확인한 공개 근거',public_source_failure:'공개 자료 접근 기록'});
const CLINICAL_SOURCE_KINDS=['binding_measurements','drug_label_search','drug_label','clinical_trial_search','clinical_trial'];

function publicLookupBundleView(result){
 const states={succeeded:'자료 도착',partial:'일부 자료 도착',same_response:'같은 조회 결과 참조',rate_limited:'조회 한도에 도달',access_failed:'접근 실패',network_failed:'연결 실패',timeout:'응답 시간 초과',response_or_input_error:'입력·반환 확인 필요'};
 const names={search_literature:'문헌 검색',search_drug_labels:'약물 라벨 찾기',read_drug_label:'라벨 원문',search_clinical_trials:'등록 시험 찾기',read_clinical_trial:'시험 원 기록'};
 return `<p>서로의 결과를 기다릴 필요가 없는 공개 조회를 함께 진행했습니다. 각 자료의 조건을 확인한 뒤 다음 검색·판단을 이어갑니다.</p>${(result.rows??[]).map(r=>`<article class="source-paragraph"><h3>${esc(names[r.function]??r.function)} · ${esc(states[r.status]??r.status)}</h3><p>${esc(r.purpose)}</p>${r.error?`<p class="notice-inline">${esc(r.error)} · 다른 조회 결과는 보존됩니다.</p>`:''}${r.source_artifact_id?button('source','이 조회의 원자료·전체 결과 보기',`data-id="${esc(r.source_artifact_id)}"`,'link-button small'):''}${r.status==='same_response'?'<p class="small muted">같은 응답을 다시 가리킵니다. 별개의 실험이나 검색 결과로 합산하지 않습니다.</p>':''}${r.view_delivery?'<p class="small muted">이 요약에는 본문이 없습니다. 원자료를 열어 필요한 범위를 확인하세요.</p>':''}</article>`).join('')}`;
}

function clinicalSourcesEntry(){return `<section class="panel science-form"><h3>임상·적용 조건까지 확인하기</h3><p>문헌 속 후보가 어떤 대상·조건에서 검토됐는지 원 기록을 확인합니다.</p>
<details><summary>약물의 적응증·경고·시험 원문</summary>${scienceInput('clinical-drug','공개 성분명 또는 제품명','예: tafamidis')}${button('science-clinical-labels','DailyMed에서 라벨 찾기',busy?'disabled':'','small')}<p class="limit">미국 라벨입니다. 제품·제형·판본을 고른 뒤 본문을 확인합니다.</p></details>
<details><summary>진행·완료·중단된 임상시험</summary>${scienceInput('clinical-condition','공개 질환 이름','예: transthyretin amyloidosis')}${scienceInput('clinical-intervention','개입 이름 · 선택 사항','미정이면 비워 두세요')}${button('science-clinical-trials','시험 찾기',busy?'disabled':'','small')}${scienceInput('clinical-nct','이미 아는 시험 번호','NCT…')}${button('science-clinical-trial-id','이 시험의 원 기록 읽기',busy?'disabled':'','small')}<p class="limit">계획한 평가항목과 실제 게시 결과를 구분합니다. 결과 미게시가 음성은 아닙니다.</p></details>
<details><summary>추가 결합·활성 자료</summary>${scienceInput('clinical-uniprot','확인한 UniProt 표적 ID','예: P02766')}${scienceInput('clinical-cutoff','조회할 활성 문턱 · nM','예: 10000')}${button('science-clinical-binding','BindingDB 원자료 조회',busy?'disabled':'','small')}<p class="limit">문턱 밖 후보는 미조회입니다. 다른 활성 지표와 실험 조건을 섞어 순위를 매기지 않습니다.</p></details></section>`}

async function clinicalSourceAction(action,node){
 const val=id=>(document.getElementById(id)?.value??'').trim();
 if(action==='science-clinical-select'){
  const ids=[...new Set([...document.querySelectorAll('input[name="binding-candidate"]:checked')].map(n=>n.value))];
  if(!ids.length){notice('계산에 연결할 원 구조를 선택해 주세요.');return}
  showDialog('선정한 원 구조를 계산에 연결',`<p>선택한 ${ids.length}개 후보의 공개 원 SMILES를 계산용 자료로 만듭니다. 이 선택은 효능·안전성 추천이 아닙니다.</p><p class="small">${ids.map(esc).join(' · ')}</p><label>이 후보들을 비교할 이유<textarea id="clinical-selection-reason" placeholder="어떤 가설이나 차이를 계산으로 확인하려는지 적어 주세요."></textarea></label><p class="limit">같은 ID에 서로 다른 구조가 있으면 원행 확인을 요청합니다. 미선택 후보와 측정 원값은 그대로 남습니다.</p><div class="dialog-actions">${button('science-clinical-materialize','원 구조 연결',`data-source="${esc(selected)}" data-ids="${esc(JSON.stringify(ids))}"`,'primary')}</div>`);return;
 }
 if(action==='science-clinical-materialize'){
  const reason=val('clinical-selection-reason');if(!reason){notice('비교할 이유를 남겨 주세요.');return}
  const args={artifact_id:node.dataset.source,candidate_ids:JSON.parse(node.dataset.ids),reason};
  dialog.close();await runTool('compound_selection',args);return;
 }
 if(action==='science-clinical-labels')await runTool('drug_label_search',{drug_name:val('clinical-drug'),page:1});
 if(action==='science-clinical-label-read')await runTool('drug_label',{setid:node.dataset.id});
 if(action==='science-clinical-trials')await runTool('clinical_trial_search',{condition:val('clinical-condition'),intervention:val('clinical-intervention'),page_token:''});
 if(action==='science-clinical-trial-id')await runTool('clinical_trial',{nct_id:val('clinical-nct')});
 if(action==='science-clinical-trial-read')await runTool('clinical_trial',{nct_id:node.dataset.id});
 if(action==='science-clinical-binding')await runTool('binding_measurements',{uniprot_id:val('clinical-uniprot'),cutoff_nm:Number(val('clinical-cutoff'))});
 if(action==='science-clinical-more-labels')await runTool('drug_label_search',{drug_name:detail.result.summary.query,page:detail.result.summary.page+1});
 if(action==='science-clinical-more-trials')await runTool('clinical_trial_search',{condition:detail.result.summary.condition,intervention:detail.result.summary.intervention,page_token:detail.result.summary.next_page_token});
}

function clinicalSourceTable(result,kind){
 const content=clinicalSourceContent(result,kind);
 if(['drug_label_search','clinical_trial_search'].includes(kind)||content===null)return content;
 const rows=result.rows??[],start=result.offset??0,total=result.total_rows??rows.length;
 return content+`<div class="pagination"><span>보존 원문 ${rows.length?number(start+1):0}–${number(start+rows.length)} / ${number(total)}행</span><div>${button('prev','이전 원문 범위',start===0?'disabled':'','small')}${button('next','다음 원문 범위',!result.has_more?'disabled':'','small')}</div></div><p class="small muted">저장된 원문의 다른 범위를 엽니다. 새 조회나 계산을 실행하지 않습니다.</p>`;
}

function compoundSelectionView(result){
 return `<h3>계산에 연결한 후보 ${esc(result.summary?.selected??result.candidate_ids?.length??0)}개</h3><p>${esc(result.selection_reason??'')}</p><p class="small">${(result.candidate_ids??[]).map(esc).join(' · ')}</p><p class="limit">공개 원 구조의 선택 사본입니다. 효능 추천이나 새 구조 생성이 아니며 미선택 후보도 남아 있습니다.</p>${result.molecule_csv_artifact_id?`<div class="detail-actions">${button('source','선정 구조와 출처 보기',`data-id="${esc(result.molecule_csv_artifact_id)}"`,'small')}${button('tool','이 원 구조의 물성 계산',`data-tool="rdkit" data-id="${esc(result.molecule_csv_artifact_id)}" ${busy?'disabled':''}`,'primary small')}</div>`:''}`;
}

function clinicalSourceContent(result,kind){
 const rows=result.rows??[],s=result.summary??{};
 const table=(headers,values)=>`<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${values(r).map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
 if(kind==='drug_label_search')return `<p>현재 조회 페이지 ${esc(s.page)} · 전체 ${esc(s.total??'미확인')}개</p>`+table(['제품·제형','판본 · 게시일','다음 확인'],r=>[externalAnchor('setid',r.setid,r.title),esc(`${r.spl_version} · ${r.published_date}`),button('science-clinical-label-read','적용 조건·시험 읽기',`data-id="${esc(r.setid)}"`,'small')])+(s.has_more?button('science-clinical-more-labels','다음 라벨 목록 조회','','small'):'');
 if(kind==='clinical_trial_search')return `<p>전체 ${esc(s.total??'미확인')}개 중 이번 조회 ${esc(s.returned)}개</p>`+table(['시험','상태 · 설계','게시 결과','다음 확인'],r=>[externalAnchor('nct',r.nct_id)+'<br>'+esc(r.title),esc(r.status?.overallStatus??'미제공')+'<br>'+esc(r.design?.studyType??''),r.has_results===true?'있음':r.has_results===false?'아직 게시되지 않음':'미확인',button('science-clinical-trial-read','대상·계획·결과 읽기',`data-id="${esc(r.nct_id)}"`,'small')])+(s.has_more?button('science-clinical-more-trials','다음 시험 목록 조회','','small'):'');
 if(kind==='binding_measurements')return `<p>표적 ${esc(s.uniprot_id)} · 조회 문턱 ${esc(s.query_cutoff_nm)}nM</p><p class="limit">이 응답에는 세부 assay 조건이 없습니다. 같은 데이터의 재수록일 수 있어 원전을 확인해야 합니다.</p>`+table(['계산할 구조','원 지표·값','참조','반환 중복'],r=>[`<label><input type="checkbox" name="binding-candidate" value="${esc(r.candidate_id)}" ${r.structure_status==='available'?'':'disabled'}> ${esc(r.candidate_id)}</label><details><summary>원 SMILES</summary><p class="mono">${esc(r.smiles??'구조 미제공')}</p></details>`,esc(`${r.raw.affinity_type??''} ${r.raw.affinity??'미제공'}`),esc([r.raw.pmid?'PMID '+r.raw.pmid:'',r.raw.doi?'DOI '+r.raw.doi:''].filter(Boolean).join(' · ')||'미제공'),r.same_returned_representation_as_row!==null?`원행 ${esc(r.same_returned_representation_as_row+1)}과 동일 표현`:'독립성 미확인'])+button('science-clinical-select','선택한 원 구조를 계산에 연결',busy?'disabled':'','small');
 const nav=`<details><summary>원문에서 필요한 부분으로 이동</summary><div class="source-section-list">${(result.section_navigation??[]).filter(n=>n.row_count).map(n=>button('article-section',esc(n.section_title??[n.section,n.module].filter(Boolean).join(' / ')??'절'),`data-offset="${n.row_offset}"`,'link-button small')).join('')}</div></details>`;
 if(kind==='drug_label')return `<p>${externalAnchor('setid',s.setid,'DailyMed 원문')} · <strong>SPL 판본 ${esc(s.spl_version)}</strong> · 문서 effectiveTime ${esc(s.effective_time)}</p>${nav}`+rows.map(r=>`<section class="source-paragraph"><h4>${esc(r.section_title??'제목 없음')}</h4>${r.cells?`<p class="small">${esc(r.caption??'')}</p><div class="table-scroll"><table><tbody><tr>${r.cells.map(c=>`<td>${esc(c.text)}${c.colspan||c.rowspan?`<small> · 원 셀 병합 열 ${esc(c.colspan??1)}, 행 ${esc(c.rowspan??1)}</small>`:''}</td>`).join('')}</tr></tbody></table></div>`:`<p class="prose">${esc(r.text??'')}</p>`}${r.text_is_fragment?'<p class="small muted">긴 본문의 일부입니다. 이어지는 행도 확인해 주세요.</p>':''}</section>`).join('');
 if(kind==='clinical_trial')return `<h3>${esc(s.title)}</h3><p>${externalAnchor('nct',s.nct_id)} · ${esc(s.overall_status)} · 결과 ${s.has_results===true?'게시됨':s.has_results===false?'미게시':'미확인'}</p>${trialResultsView(result)}${nav}`
  // The registry sections stay available in full, but folded: the reported results above are what
  // a reader needs, and an open dump of every module buries them.
  +`<details class="source-raw-sections"><summary>등록부 원 기록 ${esc(rows.length)}개 구역 보기</summary>`
  +rows.map(r=>`<section class="source-paragraph"><h4>${esc([r.section,r.module].filter(Boolean).join(' / '))}</h4><p class="small muted">${esc(r.json_pointer)}</p>${json(r.value)}${r.fragment_offset_codepoints!==undefined?'<p class="small muted">긴 원문 문자열의 연속 부분입니다.</p>':''}</section>`).join('')
  +`</details>`;
 return null;
}
