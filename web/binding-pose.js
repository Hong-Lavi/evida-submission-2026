// Preserve the original result while making a local pose-order discrepancy visible.
function bindingPoseEntry(result) {
  const complete = result.rows.some(r => r.status === 'succeeded');
  return `<section class="panel"><h3>점수가 높은 포즈를 그대로 믿어도 될까요?</h3>
    <p>반환된 다른 포즈와 알려진 같은 화합물의 결합 배치를 비교할 수 있습니다. 선택하면 좌표를 유지한 채 다른 점수로 순위를 다시 봅니다.</p>
    ${button('science-pose-dialog','포즈 선택 근거 비교',`data-id="${esc(selected)}" ${complete?'':'disabled'}`,'primary small')}
    <p class="limit">후보의 약효 순위가 아니라, 이 계산에서 어떤 포즈를 후속 해석에 쓸지 확인하는 작업입니다.</p></section>`;
}

async function bindingPoseAction(action, node) {
  if (action === 'science-pose-dialog') {
    const id = node.dataset.id;
    const view = await api(`/api/workspaces/${state.id}/artifacts/${id}?limit=100`);
    const result = view.result;
    const structure = view.meta.arguments?.structure_id;
    if (!structure) throw Error('원 도킹과 연결된 구조 자료가 필요합니다.');
    const recorded = Boolean(result.protocol.receptor_files_sha256?.['receptor.pdbqt']);
    showDialog('원 포즈와 대안 포즈 비교', `<p>원 점수와 포즈를 모두 보존합니다. 같은 화합물의 공결정 배치가 있을 때만 기준 거리를 계산합니다.</p>
      <div class="dock-candidates">${result.rows.map(r => `<label><input type="checkbox" name="pose-candidate" value="${esc(r.candidate_id)}" ${r.status==='succeeded'?'checked':'disabled'}>${esc(r.candidate_id)} · ${esc(r.status==='succeeded'?'계산 완료':'미완료')}</label>`).join('')}</div>
      <label><input id="pose-rescore" type="checkbox" ${recorded?'checked':'disabled'}>고정 포즈의 GNINA 점수도 비교</label>
      <p class="limit">${recorded?'계산한 포즈의 위치를 바꾸지 않습니다. 후보 수에 따라 수 분 걸릴 수 있습니다.':'이전 도킹 결과에는 정확한 수용체 파일이 저장되지 않았습니다. 지금은 기준 배치를 비교할 수 있고, 재점수화하려면 수용체를 보존하는 새 도킹이 필요합니다.'}</p>
      <div class="dialog-actions">${button('science-pose-run','선택 후보 비교하기',`data-id="${esc(id)}" data-structure="${esc(structure)}"`,'primary')}</div>`);
    return;
  }
  if (action !== 'science-pose-run') return;
  const candidate_ids = [...dialog.querySelectorAll('[name="pose-candidate"]:checked')].map(x => x.value);
  if (!candidate_ids.length || candidate_ids.length > 12) throw Error('완료한 후보 1–12개를 선택해 주세요.');
  busy = true; node.disabled = true; actionError = '';
  try {
    await runTool('binding_pose_review', {artifact_id: node.dataset.id, structure_id: node.dataset.structure,
      candidate_ids, run_rescoring: Boolean(document.getElementById('pose-rescore')?.checked)});
    dialog.close(); notice('원 결과를 보존하며 포즈 비교를 시작했습니다. 완료 후 결과로 판단을 갱신할 수 있습니다.');
  } catch (error) { actionError = error.message; notice(error.message); }
  finally { busy = false; render(); }
}

function bindingPoseTable(result) {
  const distance = x => x === null || x === undefined ? '같은 화합물 기준 없음' : `${number(x)} Å`;
  const comparisons = result.candidate_comparisons ?? [];
  const rescore = result.protocol.rescoring;
  const status = {COMPLETED:'완료', NOT_REQUESTED:'선택하지 않음', EXACT_RECORDED_RECEPTOR_MISSING:'원 수용체 보존 필요', FAILED_OUTPUT_PRESERVED:'실패 · 원 출력 보존'}[rescore.status] ?? rescore.status;
  return `<section class="panel"><h3>포즈 선택에서 달라진 점</h3>
    <p>기준 거리의 차이는 결합 배치 재현을, 순위 변화는 점수 함수의 차이를 보여 줍니다. 이것만으로 후보의 효능 순위를 바꾸지는 않습니다.</p>
    <div class="table-scroll"><table><thead><tr><th>후보</th><th>기존 1위의 기준 거리</th><th>반환 포즈 중 가장 가까운 거리</th><th>CNN이 고른 원 순위</th><th>그 포즈의 기준 거리</th></tr></thead>
    <tbody>${comparisons.map(c=>`<tr><td>${esc(c.candidate_id)}</td><td>${distance(c.original_top_native_rmsd_angstrom)}</td><td>${distance(c.closest_returned_native_rmsd_angstrom)}</td><td>${c.cnn_top_original_rank===null?'미계산':`${c.cnn_top_original_rank}위`}</td><td>${c.cnn_top_pose?distance(c.cnn_top_native_rmsd_angstrom):'미계산'}</td></tr>`).join('')}</tbody></table></div>
    <p>고정 포즈 재점수화: <strong>${esc(status)}</strong> · 순위가 달라진 후보 ${result.summary.changed_pose_order_candidates}개</p>
    ${rescore.next_action?`<p class="limit">${esc(rescore.next_action)}</p>`:''}
    <p class="limit">공결정 부위: ${esc(result.protocol.reference_site_id)}. 대체배치는 원 좌표로 각각 비교합니다. 기준을 이용해 포즈를 이동시키거나 새 검색을 하지는 않았습니다.</p>
    ${button('science-review','이 차이로 다음 판단 검토',`data-id="${esc(selected)}" ${busy?'disabled':''}`,'primary small')}</section>
    <details><summary>모든 반환 포즈와 원 점수 보기</summary><div class="table-scroll"><table><thead><tr><th>후보</th><th>원 Vina 순위</th><th>Vina 계산값</th><th>CNN 순위 / 점수</th><th>같은 화합물 기준 거리</th></tr></thead>
    <tbody>${result.rows.map((r,i)=>`<tr><td>${button('row',esc(r.candidate_id),`data-index="${i}"`,'link-button small')}</td><td>${r.original_vina_rank}</td><td>${number(r.original_vina_score_kcal_mol)} kcal/mol</td><td>${r.cnn_rank===null?'미계산':`${r.cnn_rank} / ${number(r.CNNscore)}`}</td><td>${distance(r.nearest_reference_rmsd_angstrom)}</td></tr>`).join('')}</tbody></table></div>
    <p class="limit">CNNscore는 측정 성공 확률이 아닙니다. 같은 입력의 여러 점수를 독립 증거로 합산하지 않습니다.</p>
    <div class="pagination"><span>${result.offset+1}–${result.offset+result.rows.length} / ${result.total_rows} 포즈</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div></details>`;
}
