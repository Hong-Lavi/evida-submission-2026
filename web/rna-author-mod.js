Object.assign(SCIENCE_LABELS,{rna_author_mod:'ENsiRNA-mod · 수식 위치 비교'});
const authorChemistryNames={'2-O-Methyl':'2′-OMe','2-Fluoro':'2′-F','2-O-(2-Methoxyethyl)':'2′-MOE','2-Deoxy':'2′-deoxy'};
const authorChemistryOptions=()=>Object.entries(authorChemistryNames).map(([value,label])=>`<option value="${esc(value)}">${esc(label)}</option>`).join('');
function authorModRow(){return `<div class="author-mod-row science-fields"><label>가닥<select data-mod-strand><option value="guide">가이드 · antisense</option><option value="passenger">보조 · sense</option></select></label><label>5′부터 위치 · 쉼표로 구분<input data-mod-positions placeholder="예: 2, 5, 7" inputmode="numeric"></label><label>당 수식<select data-mod-chemistry>${authorChemistryOptions()}</select></label>${button('science-author-mod-remove','이 수식 삭제','','quiet small')}</div>`}
function authorDesign(name){return `<fieldset class="author-design"><legend>비교할 수식안</legend><label>이름<input data-design-name value="${esc(name)}"></label><div class="author-mod-rows"></div><p class="small muted">수식을 추가하지 않으면 이 비교안은 명시적 비수식 조건입니다.</p>${button('science-author-mod-add-row','＋ 수식·위치 추가','','small')} ${button('science-author-mod-remove-design','이 비교안 삭제','','quiet small')}</fieldset>`}
async function openAuthorMod(id){
 const view=await api(`/api/workspaces/${state.id}/artifacts/${id}?limit=100`);
 const candidates=[...new Set(view.result.rows.map(row=>row.candidate_id))];
 showDialog('같은 core에서 수식·위치 비교',`<p>양 가닥은 모두5′→3′입니다. 비교할 당 수식과 위치를 직접 지정하면 저자 모델5개를 실제 실행합니다.</p>
 <label>원 후보<select id="author-mod-candidate">${candidates.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></label>
 <div id="author-designs">${authorDesign('비수식 비교안')}${authorDesign('수식 비교안')}</div>
 ${button('science-author-mod-add-design','＋ 비교안 추가 · 최대4개','','small')}
 <p class="limit">원 후보의 미확인 수식을 채워 넣는 기능이 아닙니다. 동일한19nt 염기 구조를 재사용하며, 수식 원자의3D 구조·말단·돌출부·제형·조직 노출은 계산하지 않습니다. 점수는 효능이나 성공 확률이 아닙니다.</p>
 <div class="dialog-actions">${button('science-author-mod-run','입력한 수식안 실제 비교',`data-id="${esc(id)}"`,'primary')}</div>`);
}
async function authorModAction(action,node){
 if(action==='science-author-mod-open')return openAuthorMod(node.dataset.id);
 if(action==='science-author-mod-add-row'){node.closest('.author-design').querySelector('.author-mod-rows').insertAdjacentHTML('beforeend',authorModRow());return}
 if(action==='science-author-mod-remove'){node.closest('.author-mod-row').remove();return}
 if(action==='science-author-mod-remove-design'){if(dialog.querySelectorAll('.author-design').length>1)node.closest('.author-design').remove();return}
 if(action==='science-author-mod-add-design'){
  const count=dialog.querySelectorAll('.author-design').length;
  if(count>=4){notice('한 번에4개까지 비교합니다. 다른 수식안도 별도 실행할 수 있습니다.');return}
  dialog.querySelector('#author-designs').insertAdjacentHTML('beforeend',authorDesign('수식 비교안 '+(count+1)));return;
 }
 if(action==='science-author-mod-run'){
  busy=true;node.disabled=true;
  try{
   const designs=[...dialog.querySelectorAll('.author-design')].map(form=>({id:form.querySelector('[data-design-name]').value.trim(),
    modifications:[...form.querySelectorAll('.author-mod-row')].flatMap(row=>{
     const raw=row.querySelector('[data-mod-positions]').value.trim();
     if(!/^\d+(\s*,\s*\d+)*$/.test(raw))throw Error('수식 위치를1–19의 정수로 입력해 주세요. 여러 위치는 쉼표로 구분합니다.');
     return raw.split(',').map(p=>({strand:row.querySelector('[data-mod-strand]').value,position_1_based:Number(p),chemistry:row.querySelector('[data-mod-chemistry]').value}));
    })}));
   if(designs.some(d=>!d.id)||new Set(designs.map(d=>d.id)).size!==designs.length)throw Error('각 비교안에 서로 다른 이름을 입력해 주세요.');
   for(const d of designs){const sites=d.modifications.map(m=>m.strand+':'+m.position_1_based);if(new Set(sites).size!==sites.length||d.modifications.some(m=>m.position_1_based<1||m.position_1_based>19))throw Error('같은 가닥·위치의 수식 중복과1–19 범위를 확인해 주세요.');}
   await runTool('rna_author_mod',{artifact_id:node.dataset.id,candidate_id:dialog.querySelector('#author-mod-candidate').value,designs});
   dialog.close();notice('수식 위치를 저장하고 실제 모델 비교를 시작했습니다. 원 후보와 구조 계산도 보존합니다.');
  }catch(error){notice(error.message)}finally{busy=false;node.disabled=false}
 }
}
function authorModTable(result){
 return `<p class="notice-inline">입력한 수식·위치의 조건부 모델 비교입니다. 점수 차이가 화학 수식만의 생물학적 효과라는 뜻은 아닙니다.</p>
 <div class="table-scroll"><table><thead><tr><th>후보 / 비교안</th><th>명시한 수식·위치</th><th>저자 체크포인트</th><th>조건부 원점수</th></tr></thead><tbody>${result.rows.map(row=>`<tr><td>${esc(row.candidate_id)}<br>${esc(row.design_id)}</td><td>${row.modifications.length?row.modifications.map(m=>`${m.strand==='guide'?'가이드':'보조'} ${m.position_1_based}번 ${esc(authorChemistryNames[m.chemistry]??m.chemistry)}`).join('<br>'):'명시적 비수식 비교안'}</td><td>${esc(row.checkpoint)}</td><td>${number(row.raw_model_score)}</td></tr>`).join('')}</tbody></table></div>
 <p class="limit">5개 값은 독립 실험이나 성공 확률이 아닙니다. 원 ENsiRNA 점수와 합산하지 않으며, 입력의 학습 분포 적합성·제형·조직 효능은 미검증입니다.</p>${sourceLinks([result.source_artifact_id])}
 <div class="detail-actions">${button('science-review','이 결과로 판단 갱신',`data-id="${esc(selected)}" ${busy?'disabled':''}`,'primary small')}</div>`;
}
