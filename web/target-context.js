Object.assign(SCIENCE_LABELS,{target_context:'표적의 유전·세포·조직 조건'});
const TARGET_CONTEXT_LABELS={genetic_constraint:'집단 유전변이의 제약',essentiality:'암 세포주의 유전자 의존성',safety_liabilities:'출처별 안전성 관측',baseline_expression:'세포·조직의 기초 발현'};

function targetContextEntry(){return `<section class="panel science-form"><h3>이 표적을 조절하는 조건 확인하기</h3><p>질환과 연관됐다는 사실에 더해, 어떤 조직·작용 방향을 검토해야 할지 자료를 확인합니다. 앞서 찾은 표적 자료의 버튼으로도 시작할 수 있습니다.</p>${scienceInput('target-context-id','확인한 인간 Ensembl 표적 ID','ENSG…')}<fieldset><legend>이번 질문에 필요한 자료</legend>${Object.entries(TARGET_CONTEXT_LABELS).map(([id,label])=>`<label><input type="checkbox" name="target-context-section" value="${id}" ${['genetic_constraint','safety_liabilities'].includes(id)?'checked':''}> ${esc(label)}</label>`).join('')}</fieldset>${button('science-target-context-fetch','선택한 표적 자료 확인',busy?'disabled':'','small')}<p class="limit">점수를 합쳐 자동 순위를 만들지 않습니다. 기능 손실의 질환 기전과 조직별 부분 억제는 따로 검토합니다.</p></section>`}

async function targetContextAction(action,node){
 const fromSource=Boolean(node.dataset.targetId), target=fromSource?node.dataset.targetId:document.querySelector('#target-context-id').value.trim();
 const sections=fromSource?(node.dataset.sections??'genetic_constraint,safety_liabilities').split(','):[...document.querySelectorAll('[name="target-context-section"]:checked')].map(x=>x.value);
 if(!sections.length)throw new Error('이번 질문에 필요한 자료를 하나 이상 선택해 주세요.');
 await runTool('target_context',{target_id:target,sections,expression_page:Number(node.dataset.expressionPage??0)});
}

function targetContextTable(result){
 const target=result.target??{},coverage=result.section_coverage??{};
 const labels={returned_rows:'자료 반환',returned_no_records:'이 출처의 반환 기록 없음',not_returned:'미반환 · 음성 결과 아님',source_error:'출처 오류',source_error_with_rows:'일부 자료와 오류 반환'};
 const flag=v=>v===true?'공통 필수 유전자로 분류':v===false?'공통 필수 유전자로 분류되지 않음':'분류 미반환';
 const missing=v=>v===null||v===undefined?'미반환':typeof v==='number'?number(v):String(v);
 const cell=r=>{
  const v=r.value??{};
  if(r.context_type==='genetic_constraint')return ['집단 변이 · '+missing(v.constraintType),`관측 ${missing(v.obs)} / 기대 ${missing(v.exp)}`,`O/E ${missing(v.oe)} · 구간 ${missing(v.oeLower)}–${missing(v.oeUpper)}`];
  if(r.context_type==='common_essential_flag')return ['암 세포주 공통 의존성','정상 조직의 안전성 판정이 아님',flag(r.value)];
  if(r.context_type==='cancer_cell_dependency')return ['암 세포주 · '+missing(v.cellLineName),[r.tissue_name,v.diseaseFromSource,v.mutation].filter(Boolean).join(' · '),`Gene effect ${missing(v.geneEffect)} · 발현 ${missing(v.expression)}`];
  if(r.context_type==='safety_liabilities')return ['안전성 관측 · '+missing(v.event),[v.datasource,...(v.biosamples??[]).map(b=>b.tissueLabel||b.cellLabel)].filter(Boolean).join(' · '),(v.effects??[]).map(e=>[e.direction,e.dosing].filter(Boolean).join(' · ')).join('; ')||'효과 조건 미반환'];
  return ['기초 발현 · '+missing(v.datasourceId),[v.tissueBiosample?.biosampleName||v.tissueBiosampleFromSource,v.celltypeBiosample?.biosampleName||v.celltypeBiosampleFromSource,v.datatypeId].filter(Boolean).join(' · '),`중앙값 ${missing(v.median)} ${missing(v.unit)} · Q1–Q3 ${missing(v.q1)}–${missing(v.q3)}`];
 };
 const more=coverage.baseline_expression;
 return `<h3>${esc(target.approvedSymbol??result.summary?.target_id)} · ${esc(target.approvedName??'표적 확인 필요')}</h3><p>출처별 맥락을 비교할 자료입니다. 아래 관측만으로 표적을 추천하거나 배제하지 않습니다.</p><ul>${Object.entries(coverage).map(([k,v])=>`<li><strong>${esc(TARGET_CONTEXT_LABELS[k])}</strong> · ${esc(labels[v.status]??v.status)}${k==='baseline_expression'?` · 원 페이지 ${number((v.page??0)+1)}, 반환 ${number(v.returned_rows)} / 전체 ${number(v.total)}`:''}</li>`).join('')}</ul><div class="table-scroll"><table><thead><tr><th>자료</th><th>대상·조건</th><th>출처의 값</th></tr></thead><tbody>${(result.rows??[]).map(r=>`<tr>${cell(r).map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${more?.has_more?button('science-target-context-next','발현 자료의 다음 원 페이지 확인',`data-target-id="${esc(target.id)}" data-sections="baseline_expression" data-expression-page="${more.page+1}"`,'small'):''}<p class="limit">안전성 관측 0건은 위험 0이 아닙니다. O/E·Gene effect·발현은 서로 다른 자료이므로 같은 점수로 합치지 않습니다. 표의 원값·출처 위치·전체 응답은 보존 자료에서 확인할 수 있습니다.</p><details><summary>반환 판본과 자료 해석 범위</summary><pre>${esc(JSON.stringify(result.source_version,null,2))}</pre>${(result.limits??[]).map(x=>`<p>${esc(x)}</p>`).join('')}</details>`;
}
