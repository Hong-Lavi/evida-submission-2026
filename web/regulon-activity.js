// Source-bound expression evidence is a conditional input to the research loop.
function regulonActivityEntry(){
 const sources=state.artifacts.filter(a=>a.kind==='gene_contrast_statistics'||a.meta?.semantic_type==='gene_contrast_statistics');
 return `<details class="panel science-form"><summary>발현 자료가 있다면 · 조절 패턴 비교</summary><p>유전자별 대비 통계를 두 조절망으로 계산해, 함께 남는 설명과 자료에 따라 달라지는 설명을 확인합니다. 원 카운트에서 대비 통계를 만드는 단계는 별도로 필요합니다.</p>${sources.length?`<label>비교할 자료<select id="regulon-source">${sources.map(a=>`<option value="${esc(a.id)}">${esc(a.title)}</option>`).join('')}</select></label>${scienceInput('regulon-focus','관심 전사인자 · 선택 사항','예: IRF1, E2F4')}${button('science-regulon-run','조절 패턴 실제 계산','','primary')}`:'<p class="muted">현재 연구에는 형식과 조건이 확인된 유전자별 대비 통계표가 없습니다. 자료를 추가하고 원래 비교·정규화·유전자 대응을 확인하면 연결할 수 있습니다.</p>'}</details>`;
}

async function regulonActivityAction(action,node){
 if(action!=='science-regulon-run')return;
 node.disabled=true;actionError='';
 try{
  const id=document.querySelector('#regulon-source')?.value;
  const source=state.artifacts.find(a=>a.id===id);const spec=source?.meta?.regulon_input;
  if(!spec)throw Error('원자료의 비교·통계 종류·열 대응을 먼저 확인해 주세요. 임의로 정하지 않았습니다.');
  const focus=(document.querySelector('#regulon-focus')?.value??'').split(/[\s,;]+/).filter(Boolean);
  await runTool('regulon_activity',{source_artifact_ids:[id],...spec,focus_tfs:[...new Set(focus)]});
  notice('발현 자료의 실제 계산을 시작했습니다. 완료 후 근거와 다음 판단에 연결할 수 있습니다.');
 }catch(error){actionError=error.message;notice(error.message)}finally{node.disabled=false;render()}
}

function regulonActivityTable(result){
 const table=rows=>`<div class="table-scroll"><table><thead><tr><th>전사인자</th><th>조절망</th><th>패턴 점수</th><th>자원 내 보정값</th><th>측정된 표적 수</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.source)}</td><td>${esc(r.resource)}</td><td>${number(r.score)}</td><td>${Number(r.BH_resource_family).toExponential(2)}</td><td>${number(r.measured_targets)}</td></tr>`).join('')}</tbody></table></div>`;
 const focus=result.focus_rows??[];
 const gaps=result.unestimated??[];
 return `<section class="regulon-result"><h3>발현 자료가 지지하는 조절 패턴</h3><p>${esc(result.comparison??'')}</p><p>같은 발현 자료를 두 조절망으로 계산한 결과입니다. 점수의 방향과 적용 조건을 비교하며, 그 자체로 치료 표적이나 효능을 확정하지 않습니다.</p>${focus.length?`<h4>관심 전사인자 비교</h4>${table(focus)}`:''}<details><summary>계산에 적용한 조건</summary><ul>${(result.conditions??[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p>${esc(result.method??'')}</p><p>버전: ${esc(JSON.stringify(result.versions??{}))}</p></details><h4>전체 추정 결과 · 현재 읽은 범위</h4>${table(result.rows??[])}${gaps.length?`<details><summary>추정하지 못한 항목 ${gaps.length}개 · 근거 부재와 구분</summary><p>조절망에 없거나 측정된 표적이 부족한 항목입니다. 음성 결과로 분류하지 않습니다.</p><ul>${gaps.slice(0,30).map(x=>`<li>${esc(x.TF)} · ${esc(x.resource)} · ${x.status==='resource_not_present'?'자원에 없음':'측정 표적 수 부족'} (${number(x.measured_targets)})</li>`).join('')}</ul>${gaps.length>30?'<p>나머지 항목도 원 결과에 보존되어 있습니다.</p>':''}</details>`:''}<details><summary>판단에 적용할 범위</summary><ul>${(result.limits??[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details></section>`;
}
