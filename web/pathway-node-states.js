function pathwayStateText(value){
 if(value===1)return '상승 (+1)';
 if(value===-1)return '하강 (−1)';
 if(value===0)return '변화 미사용 (0)';
 return '계산 상태 확인 필요';
}

function pathwaySignedEdgeText(edge){
 const relation=edge.sign===1?'→':edge.sign===-1?'⊣':'?';
 return `${edge.source} ${relation} ${edge.target}`;
}

function pathwayAlternativeEdges(before,after){
 if(!Array.isArray(before?.edges)||!Array.isArray(after?.edges))return '<p class="small muted">두 계산의 유효한 연결 결과가 필요합니다.</p>';
 const key=edge=>JSON.stringify([edge.source,edge.sign,edge.target]);
 const baseline=new Map((before?.edges??[]).map(edge=>[key(edge),edge]));
 const alternative=new Map((after?.edges??[]).map(edge=>[key(edge),edge]));
 const all=new Map([...baseline,...alternative]);
 if(!all.size)return '<p class="small muted">반환된 설명 연결이 없습니다.</p>';
 return `<div class="table-scroll"><table><thead><tr><th>설명 연결</th><th>원 경로</th><th>질의 경로</th></tr></thead><tbody>${[...all].map(([id,edge])=>`<tr><td>${esc(pathwaySignedEdgeText(edge))}</td><td>${baseline.has(id)?'포함':'미사용'}</td><td>${alternative.has(id)?'포함':'미사용'}</td></tr>`).join('')}</tbody></table></div>`;
}

function pathwayAlternativeStates(before,after){
 if(!Array.isArray(before?.nodes)||!Array.isArray(after?.nodes))return '<p class="small muted">두 계산의 유효한 상태 결과가 필요합니다.</p>';
 const baseline=new Map((before?.nodes??[]).map(row=>[row.node,row.state]));
 const alternative=new Map((after?.nodes??[]).map(row=>[row.node,row.state]));
 const nodes=[...new Set([...baseline.keys(),...alternative.keys()])].sort();
 // Only absent rows in a valid sparse graph denote zero; an unknown stored state stays unknown.
 const stateFor=(graph,node)=>graph.has(node)?graph.get(node):0;
 const changes=nodes.filter(node=>{
  const a=stateFor(baseline,node),b=stateFor(alternative,node);
  return ![-1,0,1].includes(a)||![-1,0,1].includes(b)||a!==b;
 });
 if(!changes.length)return '<p class="small muted">반환된 생물학 요소의 변화 상태가 같습니다.</p>';
 return `<div class="table-scroll"><table><thead><tr><th>계산 요소</th><th>원 경로</th><th>질의 경로</th></tr></thead><tbody>${changes.map(node=>`<tr><td>${esc(node)}</td><td>${pathwayStateText(stateFor(baseline,node))}</td><td>${pathwayStateText(stateFor(alternative,node))}</td></tr>`).join('')}</tbody></table></div><p class="small muted">0은 이 설명에서 변화 상태를 사용하지 않았다는 뜻입니다. 다음 관측을 고를 때 각 요소의 실제 측정법과 조건을 함께 정합니다.</p>`;
}

function pathwayQueryEntry(result){
 const summary=result.solver_package_summary;
 if(summary?.supported!==true)return '<details class="outcome-details"><summary>같은 입력에서 다른 경로를 확인하려면</summary><p>새 경로를 계산할 때 원 계산 묶음을 함께 보존하면, 선택한 요소의 변화 없이도 설명되는 경로를 이어서 질의할 수 있습니다.</p></details>';
 const id=typeof selected==='string'?selected:'';
 if(!id)return '';
 return `<section class="outcome-details"><h4>이 요소의 변화 없이도 설명될까</h4><p>현재 경로의 요소를 고르면 같은 입력·상호작용망에서 대안 경로를 실제 계산합니다.</p>${button('science-pathway-node-dialog','확인할 요소 고르기',`data-artifact="${esc(id)}"`,'small')}</section>`;
}

let pathwayNodeDialogRequest=0;
async function pathwayNodeStatesAction(action,node){
 if(busy||node.disabled)return;
 const workspaceId=state.id;
 if(action==='science-pathway-node-dialog'){
  const requestId=++pathwayNodeDialogRequest;
  const visibleArtifact=typeof selected==='string'?selected:null;
  node.disabled=true;
  try{
   const id=node.dataset.artifact;
   const data=await api(`/api/workspaces/${workspaceId}/artifacts/${encodeURIComponent(id)}`);
   if(state.id!==workspaceId||requestId!==pathwayNodeDialogRequest||(typeof selected==='string'?selected:null)!==visibleArtifact)return;
   const summary=data.result?.solver_package_summary;
   if(summary?.supported!==true)throw Error(summary?.reason??'이 경로의 원 계산 묶음을 확인해 주세요.');
   const options=summary.selectable_nodes??[];
   showDialog('같은 입력에서 다른 설명 확인',`<p>확인할 요소를 1~2개 고르세요. 각 요소의 상승·하강 변화 상태를 사용하지 않는 별도 경로를 계산합니다.</p><p class="small muted">입력 신호와 상호작용망은 유지됩니다. 이 질의의 0은 계산의 변화 상태 미사용을 뜻합니다.</p><div>${options.map(row=>`<div><label class="check-line"><input type="checkbox" data-pathway-node value="${esc(row.node_id)}">${esc(row.node_id)} · ${pathwayStateText(row.state)}</label></div>`).join('')}</div><label>이 요소를 확인하는 이유<textarea id="pathway-node-reason" maxlength="2000" placeholder="예: 이 요소에만 후속 검증을 집중해도 되는지 확인하고 싶다"></textarea></label><p class="small">선택한 요소마다 별도 계산하며, 각 계산의 제한 시간은 2분입니다.</p><div class="dialog-actions">${button('science-pathway-node-run','대안 경로 실제 계산',`data-artifact="${esc(id)}" data-workspace="${esc(workspaceId)}"`,'primary')}</div>`);
  }catch(error){if(state.id===workspaceId&&requestId===pathwayNodeDialogRequest){actionError=error.message;notice(error.message)}}finally{node.disabled=false}
  return;
 }
 if(action!=='science-pathway-node-run')return;
 ++pathwayNodeDialogRequest;
 busy=true;node.disabled=true;
 try{
  if(node.dataset.workspace!==state.id)throw Error('열어 둔 연구가 바뀌었습니다. 현재 연구에서 확인할 경로를 다시 선택해 주세요.');
  const nodeIds=[...dialog.querySelectorAll('[data-pathway-node]:checked')].map(input=>input.value);
  const reason=document.getElementById('pathway-node-reason')?.value.trim()??'';
  if(nodeIds.length<1||nodeIds.length>2)throw Error('확인할 요소를 1~2개 선택해 주세요.');
  if(!reason)throw Error('이 요소를 확인하는 이유를 적어 주세요.');
  await runTool('pathway_node_states',{artifact_id:node.dataset.artifact,node_ids:nodeIds,reason});
  dialog.close();notice('선택한 요소별 대안 경로를 계산하고 있습니다. 결과에서 원 경로와 비교할 수 있습니다.');
 }catch(error){actionError=error.message;notice(error.message)}finally{busy=false;node.disabled=false;render()}
}

function pathwayMetric(value){return typeof value==='number'&&Number.isFinite(value)?number(value):'미제공'}

function pathwayObservationComparison(before,after){
 const baseline=new Map((before??[]).map(row=>[row.node,row]));
 const alternative=new Map((after??[]).map(row=>[row.node,row]));
 const nodes=[...new Set([...baseline.keys(),...alternative.keys()])];
 const sign=value=>value===1?'+1':value===-1?'−1':value===0?'0':'확인 필요';
 return `<div class="table-scroll"><table data-pathway-tf-comparison><thead><tr><th>입력 TF</th><th>원 경로</th><th>질의 경로</th></tr></thead><tbody>${nodes.map(node=>{
  const a=baseline.get(node),b=alternative.get(node);
  return `<tr><td>${esc(node)}<br><span class="muted">${sign(a?.target_sign??b?.target_sign)}</span></td><td>${sign(a?.fitted_sign)}</td><td>${sign(b?.fitted_sign)}</td></tr>`;
 }).join('')}</tbody></table></div><p class="small muted">+1은 상승, −1은 하강, 0은 변화 미사용입니다.</p>`;
}

function pathwayQueryConclusion(row){
 if(row.validation?.valid!==true)return '유효한 대안 해 확인 필요';
 if(typeof row.comparison?.same_objective!=='boolean'||typeof row.comparison?.same_observation_fit!=='boolean')return '목적값·입력 부호 적합도 비교 확인 필요';
 if(row.comparison?.same_objective===true&&row.comparison?.same_observation_fit===true)return '같은 목적값·같은 입력 부호 적합도의 대안 경로';
 if(row.comparison?.same_objective===true)return '목적값은 같고, 입력 부호 적합도는 달라진 경로';
 if(row.comparison?.same_observation_fit===true)return '입력 부호 적합도는 같고, 목적값이 달라진 경로';
 return '입력 부호 적합도와 목적값을 함께 검토할 대안 경로';
}

function pathwayArtificialComparison(before,after,changed){
 if(!changed)return '';
 const a=before?.artificial_root?.state,b=after?.artificial_root?.state;
 const stateChanged=[-1,0,1].includes(a)&&[-1,0,1].includes(b)&&a!==b;
 const sentence=stateChanged?`가상 시작점도 ${pathwayStateText(a)}에서 ${pathwayStateText(b)}로 달라졌습니다.`:'가상 시작점의 연결도 달라졌습니다.';
 const edges=graph=>(graph?.artificial_edges??[]).map(pathwaySignedEdgeText).join(', ')||'반환된 연결 없음';
 return `<p class="notice-inline">${sentence} 원 문제에서 자유롭게 선택하는 계산 상태입니다.</p><details><summary>가상 시작점의 원 연결과 질의 연결</summary><p>원 경로: ${esc(edges(before))}</p><p>질의 경로: ${esc(edges(after))}</p></details>`;
}

function pathwayNodeStatesTable(result){
 const baseline=result.baseline??{},rows=result.rows??[];
 const solverLabels={optimal_reported:'계산기가 최적해로 보고',optimal_within_relative_gap:'설정한 상대 오차 범위에서 계산 종료',solver_time_limit:'계산 시간 제한',outer_wall_timeout:'전체 실행 시간 제한',infeasible_reported:'계산기가 추가 조건에서 해 없음으로 보고',process_failure:'실행 확인 필요',process_or_validation_failure:'실행·해 검증 확인 필요',unclassified_solver_termination:'계산 종료 상태 확인 필요',not_started_after_stop:'앞선 계산 종료 후 미실행'};
 const objectiveRow=(label,key,row)=>`<tr><td>${label}</td><td>${pathwayMetric(baseline.objective?.[key])}</td><td>${pathwayMetric(row.objective?.[key])}</td></tr>`;
 const ownId=typeof selected==='string'?selected:'';
 return `<section data-pathway-node-states><h3>선택 요소의 변화 없이 설명되는 경로</h3><p>${esc(result.reason??'')}</p><p>같은 입력과 상호작용망에서 ${number(result.summary?.planned_queries??rows.length)}개 요소를 따로 확인하는 비교입니다.</p>${sourceLinks([result.source_binding?.artifact_id].filter(Boolean))}${rows.map(row=>{
  const valid=row.validation?.valid===true;
  return `<article class="panel" data-pathway-node-result="${esc(row.node_id)}"><h4>${esc(row.node_id)}의 변화 상태를 사용하지 않을 때</h4><p><strong>${pathwayQueryConclusion(row)}</strong></p><p class="small">${esc(solverLabels[row.solver?.termination]??'계산 종료 상태 확인 필요')}${row.solver?.elapsed_seconds!=null?` · ${pathwayMetric(row.solver.elapsed_seconds)}초`:''}</p>${valid?`<div class="table-scroll"><table><thead><tr><th>비교 항목</th><th>원 경로</th><th>질의 경로</th></tr></thead><tbody>${objectiveRow('총 목적값','total',row)}${objectiveRow('입력 부호의 가중 오차','weighted_sign_error',row)}${objectiveRow('변화 상태의 복잡도 항','state_penalty',row)}</tbody></table></div><p class="small muted">입력 부호를 설명하는 정도와 경로 복잡도를 함께 계산한 값입니다.</p><h4>어떤 입력을 같은 방향으로 설명하나</h4>${pathwayObservationComparison(baseline.measurements,row.measurements)}${pathwayArtificialComparison(baseline.graph,row.graph,row.artificial_source_changed)}<h4>대안에서 달라진 설명</h4>${pathwayAlternativeStates(baseline.graph,row.graph)}<details><summary>원 경로와 대안의 연결 비교</summary>${pathwayAlternativeEdges(baseline.graph,row.graph)}</details>`:`<p>${esc(row.reason??row.error??row.message??'보존된 실행 조건과 로그를 확인해 다음 질의를 정합니다.')}</p>`}<details><summary>계산 조건과 원 기록</summary><p>원 문제에 선택 요소의 양·음 변화 상태를 0으로 두는 조건을 더했습니다.</p><p class="small">가상 시작점: ${result.scope?.artificial_source_free===true?'원 문제에서 자유롭게 선택':result.scope?.artificial_source_free===false?'원 문제의 고정 조건 유지':'원 문제 확인 필요'}</p>${json({constraints:row.constraints,validation:row.validation,comparison:row.comparison,solver:row.solver,source_binding:result.source_binding})}</details></article>`;
 }).join('')}${ownId?`<div class="detail-actions">${button('science-review','대안 경로를 현재 가설과 검토',`data-id="${esc(ownId)}"`,'small')}</div>`:''}<p class="small muted">바뀐 계산 요소를 바탕으로 실제 구별할 관측의 측정법·조건을 검토합니다.</p></section>`;
}
