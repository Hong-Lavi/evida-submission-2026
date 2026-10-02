SCIENCE_LABELS.intervention_direction_audit='약물 작용 방식과 방향 근거';

async function interventionDirectionAction(action,node){
 if(action==='science-direction-dialog'){
  const source=await api(`/api/workspaces/${state.id}/artifacts/${node.dataset.id}?download=1`);
  const drugs=new Map();
  for(const row of source.rows??[])if(row.drug?.id)drugs.set(row.drug.id,row.drug.name??row.drug.id);
  showDialog('이 약물은 표적에 어떻게 작용하나요?',`<p>근거에 등장하는 약물을 골라 실제 작용기전 기록과 대조합니다. 안정화와 RNA 생산 억제를 같은 의미로 해석하지 않도록 돕습니다.</p>
   <fieldset><legend>이번에 확인할 약물 · 최대 20개</legend><div class="dock-candidates">${[...drugs].map(([id,name])=>`<label><input type="checkbox" name="direction-molecule" value="${esc(id)}">${esc(name)} <small>${esc(id)}</small></label>`).join('')||'<p>이 자료에는 연결할 약물 식별자가 없습니다. 다른 근거 페이지를 확인하세요.</p>'}</div></fieldset>
   <p class="small muted">현재 자료에 받은 약물만 표시합니다. 다른 페이지와 미선택 약물도 기존 근거에 남아 있습니다. 약물·염은 원 식별자를 유지합니다.</p>
   <div class="dialog-actions">${button('science-run-direction-audit','선택 약물의 작용기전 조회',`data-id="${esc(node.dataset.id)}" ${drugs.size?'':'disabled'}`,'primary')}</div>`);
  return;
 }
 busy=true;node.disabled=true;
 try{
  const molecule_ids=[...document.querySelectorAll('input[name="direction-molecule"]:checked')].map(x=>x.value);
  if(!molecule_ids.length||molecule_ids.length>20)throw Error('확인할 약물을 1–20개 선택해 주세요.');
  await runTool('intervention_direction_audit',{artifact_id:node.dataset.id,molecule_ids});
  dialog.close();
 }finally{busy=false;node.disabled=false;render()}
}

function interventionDirectionTable(result){
 const names={'STABILISER':'단백질 안정화','RNAI INHIBITOR':'RNAi를 통한 생산 억제'};
 const source=result.summary.source_evidence_coverage??{};
 const current=result.summary.source_query_coverage;
 const legacyComplete=result.source_evidence_status==='succeeded'&&Number.isInteger(source.total)&&source.returned===source.total&&source.next_cursor===null;
 const sourceComplete=current?current.complete_for_reported_query:legacyComplete;
 const sourceState=current?.status??(sourceComplete?'complete':source.next_cursor?'partial':'unknown');
 const coverageNames={complete:'해당 조회 범위 수신 완료',partial:'일부 범위만 확인',unknown:'완료 여부 미확인',inconsistent:'건수·범위 대응 재확인 필요'};
 const mechanism=result.summary.mechanism_query_coverage;
 const mechanismLabel=mechanism?coverageNames[mechanism.status]:(result.summary.mechanism_next_page?'다음 페이지 미조회':'다음 페이지 없음으로 기록 · 전체 건수는 원 응답 확인');
 const reflected=state.decision_rev===state.rev&&(state.decision?.evidence_refs??[]).includes(selected);
 const next=reflected?`${button('tab','이 근거가 반영된 판단 보기','data-id="research"','primary small')}${button('science-review','다시 검토 요청',`data-id="${esc(selected)}" ${busy?'disabled':''}`,'small')}`:button('science-review','이 근거로 다음 판단 갱신',`data-id="${esc(selected)}" ${busy?'disabled':''}`,'primary small');
 return `<p class="notice-inline">실제 작용 방식과 원 DB 방향 표기를 나란히 확인합니다.</p>
  <div class="notice-inline" data-direction-coverage><p><strong>표적·질환 근거</strong> · ${esc(String(current?.returned_rows??source.returned??'미제공'))} / ${esc(String(current?.reported_total??source.total??'전체 미확인'))}행 · ${esc(coverageNames[sourceState])}</p>
   <p><strong>선택 약물의 작용기전</strong> · ${esc(mechanismLabel)}${mechanism?` (${esc(String(mechanism.returned_rows))} / ${esc(String(mechanism.reported_total??'전체 미확인'))}건)`:''}</p>
   <p class="small">두 조회 범위는 별개입니다. 받은 자료의 수신 완료는 원문 해석·과학적 검증의 완료가 아닙니다.${sourceComplete?'':' 아직 받지 않은 근거를 약효 없음으로 해석하지 않습니다.'}</p></div>
  <p>선택한 약물 항목 ${result.summary.selected_molecules}개 · 원전이 명시한 모체 ${result.summary.distinct_explicit_parents}개. 염과 모체의 원 식별자를 유지했으며, 아래 행 수는 독립 지지 근거의 개수가 아닙니다.</p>
  <details><summary>방향 정보가 어느 근거에 있나요?</summary><p class="small">선택한 원 근거 자료 안의 출처별 집계입니다. 미제공은 중립·반대 근거가 아니며 미조회 범위는 이 분모에 없습니다.</p><ul>${Object.entries(result.summary.direction_field_coverage??{}).map(([name,c])=>`<li>${esc(name)} · 표적 방향 제공 ${c.directionOnTarget_reported??0} / ${c.total}행</li>`).join('')}</ul></details>
  <div class="table-scroll"><table><thead><tr><th>약물</th><th>보고된 작용 방식</th><th>DB 방향 표기</th><th>원 조건과 표적</th></tr></thead><tbody>${result.rows.map((r,i)=>`<tr>
   <td>${button('row',esc(r.drug.name??r.drug.id),`data-index="${i}"`,'link-button small')}<br><small>${esc(r.drug.id)}</small></td>
   <td>${r.action_types.map(a=>esc(names[a]??a??'작용 유형 미제공')).join('<br>')||'기록 미반환 · 효과 없음이라는 뜻 아님'}</td>
   <td>${esc(r.direction_on_target??'미제공')} / ${esc(r.direction_on_trait??'미제공')}<br><small>${esc(r.datasource_id??'출처 미제공')}</small></td>
   <td><details><summary>이 기록의 조건 보기</summary><p>${esc(r.source_evidence.studyOverview??r.source_evidence.cohortDescription??'질환형·조직·용량은 원전 확인')}</p>
    <p>원 자료의 질환명: ${esc(r.source_evidence.diseaseFromSource??'미제공')}<br>매핑된 질환: ${esc(r.source_evidence.disease?.name??'미제공')} · ${esc(r.source_evidence.disease?.id??'미제공')}</p>
    <p class="small">근거 날짜: ${esc(r.source_evidence.evidenceDate??'미제공')} · 자료 공개일: ${esc(r.source_evidence.releaseDate??'미제공')} · 논문 연도: ${esc(String(r.source_evidence.publicationYear??'미제공'))}</p>
    <p>${esc([r.source_evidence.clinicalStage,r.source_evidence.trialWhyStopped].filter(Boolean).join(' · '))}</p><p>${esc((r.source_evidence.trialStopReasonCategories??[]).join(' · '))}</p>
    ${r.mechanisms.map(m=>`<p>${esc(m.mechanism_of_action??m.action_type??'작용 설명 미제공')} · 표적 ${esc(m.target_chembl_id??'미제공')}</p>`).join('')}
    <p class="small">${r.interpretation_notes.map(esc).join('<br>')}</p>${button('row','원행·원 링크 확인',`data-index="${i}"`,'small')}</details></td>
   </tr>`).join('')}</tbody></table></div>
  <p class="limit">GoF를 단백질 양을 늘리라는 권고로 바꾸지 않습니다. protect는 이 임상의 성공이나 승인 적응증을 보장하지 않습니다. 표적·질환형·조직의 대응은 이어 확인해야 합니다.</p>
  <p class="small">원 표적 근거 ${sourceLinks([result.source_artifact_id])} · 이번에 고르지 않은 약물 ${(result.summary.unselected_molecule_ids??[]).length}개${result.summary.mechanism_next_page?' · 작용기전 다음 페이지 미조회':''}</p>
  <div class="pagination"><span>${result.total_rows?result.offset+1:0}–${result.offset+result.rows.length} / ${result.total_rows}행</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div>
  <div class="detail-actions">${next}</div>`;
}
