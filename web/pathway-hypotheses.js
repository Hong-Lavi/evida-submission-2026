function pathwayHypothesesEntry(){
 const results=state.artifacts.filter(a=>a.kind==='regulon_activity'&&a.meta?.result_status==='succeeded');
 if(!results.length)return '';
 return `<details class="panel science-form"><summary>조절 패턴을 설명할 경로 찾아보기</summary><p>확인할 전사인자와 선택 이유를 정하면, 알려진 상호작용 안에서 그 패턴을 설명하는 경로 후보를 실제 계산합니다. 계산된 경로가 치료 표적의 입증은 아닙니다.</p><label>사용할 계산 결과<select id="pathway-source">${results.map(a=>`<option value="${esc(a.id)}">${esc(a.title)}</option>`).join('')}</select></label><label>비교할 조절망<select id="pathway-resource"><option value="dorothea">DoRothEA</option><option value="collectri">CollecTRI</option></select></label>${scienceInput('pathway-tfs','확인할 전사인자','예: IRF1, E2F4')}${scienceInput('pathway-reason','이 신호를 함께 보는 이유','예: 두 조절망에서 함께 유지된 패턴을 설명하고 싶다')}${scienceInput('pathway-conditions','해석에 필요한 조건','조직·대조군·관측 또는 추정의 구별')}<label>상류 탐색 범위<select id="pathway-depth"><option value="1">한 연결 앞까지</option><option value="2" selected>두 연결 앞까지</option><option value="3">세 연결 앞까지</option><option value="4">네 연결 앞까지</option></select></label><p class="muted">이번 계산의 범위이며, 바깥에 다른 경로가 없다는 뜻은 아닙니다. 다른 조절망을 비교할 때는 같은 신호·범위를 사용합니다.</p>${button('science-pathway-run','경로 후보 실제 계산','','primary')}</details>`;
}

async function pathwayHypothesesAction(action,node){
 if(action==='science-pathway-section'){
  const id=node.dataset.artifact??selected,section=node.dataset.section,start=Number(node.dataset.offset??0);
  const data=await api(`/api/workspaces/${state.id}/artifacts/${encodeURIComponent(id)}?calculation_section=${encodeURIComponent(section)}&offset=${start}&limit=30`);
  const r=data.result;
  const nav=`data-artifact="${esc(id)}" data-section="${esc(section)}"`;
  const keys=[...new Set(r.rows.flatMap(x=>Object.keys(x.value??{})))];
  const table=`<div class="table-scroll"><table><thead><tr><th>경로 · 원 행</th>${keys.map(k=>`<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${r.rows.map(x=>`<tr><td>${x.network_index?`경로 ${number(x.network_index)} · `:''}${esc(x.source_path.slice(-1)[0])}</td>${keys.map(k=>`<td>${!(k in x.value)?'항목 없음':x.value[k]===null?'미제공 (null)':esc(typeof x.value[k]==='object'?JSON.stringify(x.value[k]):String(x.value[k]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  showDialog(r.section_label,`<p>원 계산표의 선택한 범위입니다. 0과 비선택 행도 보존합니다. 선택 가중치는 인과 확률이나 실측 활성이 아닙니다.</p>${table}<div class="pagination"><span>${r.rows.length?number(start+1):0}–${number(start+r.rows.length)} / ${number(r.total_rows)}행</span><div>${button('science-pathway-section','이전',`${nav} data-offset="${Math.max(0,start-30)}" ${start===0?'disabled':''}`,'small')}${button('science-pathway-section','다음',`${nav} data-offset="${start+30}" ${!r.has_more?'disabled':''}`,'small')}</div></div><details><summary>원 위치와 해시</summary>${json({artifact_id:id,sha256:data.source_sha256,rows:r.rows})}</details>`);
  return;
 }
 if(action!=='science-pathway-run')return;
 node.disabled=true;
 try{
  const value=id=>document.getElementById(id)?.value.trim()??'';
  const reason=value('pathway-reason'),condition=value('pathway-conditions');
  if(!reason||!condition)throw Error('선택 이유와 해석 조건을 적어 주세요. 빈 조건을 자동으로 정하지 않습니다.');
  const args={artifact_id:value('pathway-source'),resource:value('pathway-resource'),
   tf_ids:[...new Set(value('pathway-tfs').split(/[\s,;]+/).filter(Boolean))],selection_reason:reason,
   ancestor_steps:Number(value('pathway-depth')),conditions:[condition]};
  await runTool('pathway_hypotheses',args);notice('관측을 설명할 경로 후보를 계산하고 있습니다. 기존 판단은 유지합니다.');
 }catch(error){actionError=error.message;notice(error.message)}finally{node.disabled=false;render()}
}

function pathwayHypothesesTable(result){
 const real=(result.rows??[]).filter(r=>!r.artificial_root_edge),artificial=(result.rows??[]).filter(r=>r.artificial_root_edge);
 const rows=items=>`<div class="table-scroll"><table><thead><tr><th>후보 경로</th><th>앞선 요소</th><th>관계</th><th>다음 요소</th></tr></thead><tbody>${items.map(r=>`<tr><td>${number(r.network_index)}</td><td>${esc(r.source)}</td><td>${r.sign===1?'활성 방향':'억제 방향'}</td><td>${esc(r.target)}</td></tr>`).join('')}</tbody></table></div>`;
 return `<section class="pathway-result"><h3>조절 패턴을 설명하는 경로 후보</h3><p>${esc(result.selection_reason??'')}</p><p>계산에 사용한 추정 신호: ${(result.selected_inferred_observations??[]).map(x=>`${esc(x.source)} (${number(x.score)})`).join(', ')}</p>${rows(real)}<p>고정 상호작용 ${number(result.search_scope?.full_prior_edges)}개 중 이번 범위의 ${number(result.search_scope?.selected_prior_edges)}개를 사용했습니다. 계산 범위 밖은 미탐색입니다.</p><p>${result.solver_review?.optimal_reported?'이 범위의 목적함수에서 최적해가 보고됐습니다. 유일한 생물학적 설명을 뜻하지는 않습니다.':'최적성 확인이 끝나지 않은 계산 결과입니다. 실행 조건을 먼저 검토합니다.'}</p><details><summary>계산 조건과 해석 범위</summary><ul>${[...(result.source_conditions??[]),...(result.conditions??[]),...(result.limits??[])].map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p>${esc(result.method??'')} · ${esc(JSON.stringify(result.versions??{}))}</p></details>${(result.calculation_sections??[]).length?`<details class="calculation-section-navigation"><summary>전체 계산표에서 필요한 범위 확인</summary><p>기본 화면은 반환된 경로를 보여줍니다. 내부 표는 필요할 때 열 수 있으며 원자료에서 삭제하지 않습니다.</p>${result.calculation_sections.map(x=>button('science-pathway-section',`${x.label} · ${number(x.total_rows)}행`,`data-section="${esc(x.section)}" data-offset="0"`,'small')).join('')}</details>`:''}${artificial.length?`<details><summary>최적화의 가상 시작점 · 실제 원인과 구별</summary><p>Perturbation은 최적화 표현입니다. 실제 약물이나 원인으로 확정하지 않습니다.</p>${rows(artificial)}</details>`:''}</section>`;
}
