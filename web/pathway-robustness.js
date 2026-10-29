const pathwayAxisLabels={prior_signed_edges:'상호작용망',prior_order:'상호작용 입력 순서',selected_tf_ids:'선택한 전사인자',selected_tf_order:'전사인자 입력 순서',selected_tf_scores:'입력 점수',selected_tf_signs:'입력 방향',regulon_name:'조절망 종류',regulon_definition:'조절망 판본',dataset:'발현 원자료',solver_options:'계산 설정',engine:'계산 프로그램'};
const pathwayStateLabels={returned:'반환됨',not_selected:'탐색했으나 반환되지 않음',outside_search_scope:'탐색 범위 밖',not_returned_scope_unknown:'반환되지 않음 · 범위 미확인',unassessed:'계산 미완료·미확인'};
function pathwayComparisonEntry(){
  const runs=state.artifacts.filter(a=>a.kind==='pathway_hypotheses');
  if(runs.length<2)return '';
  const previous=state.artifacts.filter(a=>a.kind==='pathway_robustness');
  return `<details class="panel science-form"><summary>조건을 바꾼 설명 경로 비교</summary><p>저장된 계산 2~8개에서 입력 조건과 유지되거나 달라지는 연결을 함께 확인합니다.</p>${runs.map(a=>`<label class="check-line"><input type="checkbox" data-pathway-compare value="${esc(a.id)}">${esc(a.title)}</label>`).join('')}${button('science-pathway-compare','선택한 경로 비교','','primary small')}${previous.length?`<p>저장된 비교</p>${sourceLinks(previous.map(a=>a.id))}`:''}</details>`;
}
async function pathwayComparisonAction(node){
  if(busy||node.disabled)return;
  node.disabled=true;
  try{
    const ids=[...document.querySelectorAll('[data-pathway-compare]:checked')].map(n=>n.value);
    if(ids.length<2||ids.length>8)throw Error('비교할 경로 결과를 2~8개 선택해 주세요.');
    await runTool('pathway_robustness',{artifact_ids:ids});
    notice('저장된 경로와 계산 조건을 비교합니다.');
  }catch(error){actionError=error.message;notice(error.message)}finally{node.disabled=false;render()}
}
function pathwayRobustnessTable(result){
  const runs=result.runs??[],summary=result.summary??{};
  const runName=id=>runs.find(r=>r.run_id===id)?.title??'계산 확인 필요';
  const inputNodes=new Set(runs.flatMap(r=>r.input_facts?.selected_tf_ids??[]));
  const names=keys=>keys.map(k=>pathwayAxisLabels[k]??k).join(', ')||'없음';
  const edgeText=e=>`${e.source} ${e.sign===1?'→':'⊣'} ${e.target}`;
  const values=(rows,formatter)=>rows.length?list(rows.map(formatter)):'<p class="small muted">해당 연결 없음</p>';
  const stateCell=(row,run)=>{
    const s=row.states.find(s=>s.run_id===run.run_id);
    if(!s)return '미확인';
    const input=row.record_type==='node'&&(run.input_facts?.selected_tf_ids??[]).includes(row.node);
    return `${esc(s.status==='returned'&&row.record_type==='node'?(s.state>0?'활성 방향':s.state<0?'억제 방향':'0 상태'):pathwayStateLabels[s.status]??s.status)}${input?'<br><small>입력으로 지정</small>':''}${s.run_status!=='succeeded'?`<br><small>${esc({partial:'부분 계산',failed:'실패',unassessed:'미확인'}[s.run_status]??s.run_status)}</small>`:''}`;
  };
  return `<section data-pathway-comparison><h3>조건을 바꾸면 설명 경로가 유지되나</h3><p>저장된 계산 ${number(runs.length)}개의 원 입력과 반환 경로를 비교했습니다.</p><p class="small">입력으로 지정한 전사인자: ${esc([...inputNodes].join(', ')||'미확인')}. 이 방향의 일치는 독립적인 검증으로 세지 않습니다.</p><details open><summary>계산별 입력과 탐색 범위</summary><div class="table-scroll"><table><thead><tr><th>계산</th><th>조절망·입력</th><th>탐색 범위·완료 상태</th></tr></thead><tbody>${runs.map(r=>`<tr><td>${esc(r.title)}${sourceLinks([r.artifact_id])}</td><td>${esc(r.input_facts?.regulon_name??'조절망 미확인')}<br>${esc((r.input_facts?.selected_tf_ids??[]).join(', ')||'입력 미확인')}</td><td>${r.search_scope?.selected_prior_edges!=null?number(r.search_scope.selected_prior_edges):r.input_coverage?.selected_prior_edge_count!=null?number(r.input_coverage.selected_prior_edge_count):'미확인'} 연결${r.input_coverage?.full_selected_prior_recorded?'':' · 원 탐색망 미확인'}<br>${esc({succeeded:'계산 완료',partial:'부분 결과',failed:'실패',unassessed:'미확인'}[r.status]??r.status)}</td></tr>`).join('')}</tbody></table></div></details><h4>어느 조건에서 달라지는가</h4>${(result.pairwise??[]).map(p=>`<details class="outcome-details"><summary>${esc(runName(p.left_run_id))} ↔ ${esc(runName(p.right_run_id))}</summary><p><strong>달라진 입력·설정:</strong> ${esc(names(p.changed_axes))}</p><p><strong>동일 여부를 확인하지 못한 항목:</strong> ${esc(names(p.unexamined_axes))}</p>${p.output_comparison_status==='unassessed'?'<p>계산이 완료되지 않아 경로 차이를 판정하지 않았습니다.</p>':`<h4>두 계산에 함께 나온 연결</h4>${values(p.conserved_signed_edges,edgeText)}<h4>앞 계산에만 나온 연결</h4>${values(p.left_only_edges,edgeText)}<h4>뒤 계산에만 나온 연결</h4>${values(p.right_only_edges,edgeText)}${p.different_signed_nodes.length?`<h4>방향이 달라진 요소</h4>${values(p.different_signed_nodes,x=>`${x.node}: ${x.left_state} → ${x.right_state}`)}`:''}`}<p class="small muted">반환되지 않은 연결의 탐색 범위는 아래 표에서 따로 확인할 수 있습니다. 여러 설정이 바뀐 비교는 한 가지 원인으로 해석하지 않습니다.</p></details>`).join('')}<details><summary>요소·연결별 전체 비교표</summary><div class="table-scroll"><table><thead><tr><th>요소 또는 연결</th>${runs.map(r=>`<th>${esc(r.title)}</th>`).join('')}</tr></thead><tbody>${(result.rows??[]).map(row=>`<tr><td>${esc(row.record_type==='node'?row.node:edgeText(row))}</td>${runs.map(r=>`<td>${stateCell(row,r)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${result.has_more?'<p>현재 페이지의 원행입니다. 다음 페이지에서 나머지 요소·연결을 확인할 수 있습니다.</p>':''}</details><p class="small muted">확인한 계산들의 비교입니다. 공통 연결과 같은 목적값은 유일한 기전이나 인과 확률을 뜻하지 않습니다.</p></section>`;
}
