// Show source conditions before a result is carried into another decision.
Object.assign(SCIENCE_LABELS,{chemical_sirna_evidence:'표적별 수식 원자료',research_evidence:'실제 시험·원전 조건 검토',source_image:'공개 원 그림'});

function chemicalSourceEntry(){return `<section class="panel science-form"><h3>수식 효과의 실제 근거 찾기</h3><p>같은 표적의 공개 원자료를 먼저 찾고, 두 가닥·화학·전달·대조 조건을 확인합니다.</p>${scienceInput('science-chemical-gene','표적 유전자 이름','예: TTR 또는 PCSK9')}${button('science-chemical-source','표적의 수식 원자료 조회',busy?'disabled':'','small')}<p class="limit">이 자료에는 13개 표적이 수록되어 있습니다. 미수록은 효과 없음이 아니며 다른 표적의 결과를 그대로 옮기지 않습니다.</p></section>`}

function chemicalSourceView(result){
 const s=result.summary,rows=result.rows??[];
 return `<p><strong>${esc(s.requested_gene)}</strong> · 전체 원자료 ${number(s.source_rows)}행 중 ${number(s.matching_rows)}행</p>${!s.matching_rows?'<div class="notice-inline">이 판본에서 같은 표적의 행을 찾지 못했습니다. 다른 문헌이나 직접 자료를 확인할 필요가 있습니다. 효능이 없다는 결과가 아닙니다.</div>':''}
 <details><summary>수록된 표적과 원자료 범위</summary><p>${Object.entries(s.available_target_counts).map(([k,v])=>`${esc(k)} ${number(v)}행`).join(' · ')}</p><p class="limit">같은 기록 조건·다른 수식 묶음 ${number(s.same_recorded_conditions_different_chemistry_groups)}개. 전달·대조 조건이 추가로 다를 수 있어 수식의 인과 효과는 아닙니다.</p></details>
 ${rows.length?`<div class="table-scroll"><table><thead><tr>${['원 ID','표적 · 전사체','세포/동물','농도 · 시간','원 억제값 · SD','수식·전체 원행'].map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>{const v=r.raw;return `<tr><td>${esc(v.ID)}</td><td>${esc(v.Target_Gene)}<br>${esc(v.Accession_number)}</td><td>${esc(v.Cell_Type)}</td><td>${esc(v.Concentration||'미기재')}<br>${esc(v.Time_of_administration||'미기재')}</td><td>${esc(v.Inhibition||'미기재')} · ${esc(v.SD||'미기재')}</td><td><details><summary>원값 확인</summary><p class="small">원행 ${r.source_record_1_based_after_header} · ${esc(v.patent_ID)}</p><p>가이드 ${esc(v.Antisense_seqence)}<br>보조 ${esc(v.Sense_seqence)}</p>${json(v)}</details></td></tr>`}).join('')}</tbody></table></div>`:''}
 <details><summary>해석 조건</summary>${list(result.limits)}</details>`;
}

function authorCheckpointTable(row){
 if(!row.checkpoint_scores?.length)return '';
 const score=v=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(6):'미제공';
 return `<details class="author-checkpoints"><summary>체크포인트·구조 조건별 원점수</summary><p class="limit">모델이 반환한 값입니다. 억제율·효능 확률이 아니며, 평균이나 가장 좋은 조건으로 합치지 않았습니다.</p><div class="table-scroll"><table><thead><tr><th>저자 모델</th><th>구조11</th><th>구조23</th><th>구조47</th><th>조건 간 폭</th></tr></thead><tbody>${row.checkpoint_scores.map(s=>`<tr><td>${esc(s.checkpoint)}</td>${['11','23','47'].map(k=>`<td>${score(s.scores_by_structure_seed[k])}</td>`).join('')}<td>${score(s.span)}</td></tr>`).join('')}</tbody></table></div><details><summary>이 결과와 연결된 정확한 입력</summary><p>가이드5′→3′: <code>${esc(row.identity.guide_5to3)}</code></p><p>보조5′→3′: <code>${esc(row.identity.passenger_5to3)}</code></p><p>${esc(row.identity.reference.transcript_id)}.${esc(row.identity.reference.version)} · 위치${esc(row.identity.target_start_1_based)}–${esc(row.identity.target_end_1_based)}</p><p class="small muted">계산은 무수식·blunt·제형없음. 원 제품 후보의 완성 화학·전달 설계는 별도 조건입니다.</p></details></details>`;
}

function researchEvidenceView(result){
 const s=result.summary??{};
 return `<div class="evidence-review"><p class="small muted">${esc(result.evidence_origin_label??'원자료와 분리한 검토')}</p><h3>${esc(s.question??'확인한 질문')}</h3><p>${judgmentText(s.finding??'')}</p>
 <details><summary>어떤 조건에서 확인했나요?</summary>${Object.entries(result.conditions??{}).map(([key,val])=>`<p><strong>${esc(key)}</strong> · ${esc(typeof val==='string'?val:JSON.stringify(val))}</p>`).join('')}</details>
 ${(result.rows??[]).map(row=>`<article class="source-evidence-row"><h4>${esc(typeof sourceDisplayText==='function'?sourceDisplayText(row.title??row.row_id):row.title??row.row_id)}</h4><p>${judgmentText(row.observation??'')}</p><p class="small muted">${judgmentText(row.interpretation??'')}</p>${authorCheckpointTable(row)}${modificationCheckpointTable(row)}${row.next_check?`<p class="small"><strong>다음 확인</strong> · ${judgmentText(row.next_check)}</p>`:''}${sourceLinks(row.artifact_refs??[])}${row.source_url&&/^https:\/\//.test(row.source_url)?`<a href="${esc(row.source_url)}" target="_blank" rel="noopener noreferrer">공개 원전</a>`:''}</article>`).join('')}
 <details><summary>이 결과로 아직 말할 수 없는 것</summary>${list(result.limits??[])}</details></div>`;
}

function modificationCheckpointTable(row){
 const values=row.modification_checkpoint_scores;if(!values?.length)return '';
 const score=v=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(6):'미제공';
 return `<details class="modification-checkpoints"><summary>수식 모델의 조건별 원점수 보기</summary><p class="limit">${esc(row.score_comparison_label??'같은 모델·입력 조건의 기록입니다. 실제 억제율이나 효과 확률로 환산하지 않습니다.')}</p>
 <div class="table-scroll"><table><thead><tr><th>체크포인트</th><th>${esc(row.score_left_label??'저자 무수식 입력')}</th><th>${esc(row.score_right_label??'AS2 2′-OMe 입력')}</th></tr></thead><tbody>${values.map(v=>`<tr><td>${esc(v.checkpoint)}</td><td>${score(v.left_score)}</td><td>${score(v.right_score)}</td></tr>`).join('')}</tbody></table></div>
 <details class="modification-diagnostics"><summary>별도 입력 표현 진단</summary><p class="limit">수식 위치 표지만 서로 바꾼 계산입니다. 실제 분자나 측정된 화학 효과가 아닙니다.</p><div class="table-scroll"><table><thead><tr><th>체크포인트</th><th>왼쪽 화학·오른쪽 위치 표지</th><th>오른쪽 화학·왼쪽 위치 표지</th></tr></thead><tbody>${values.map(v=>`<tr><td>${esc(v.checkpoint)}</td><td>${score(v.left_chemistry_right_mask)}</td><td>${score(v.right_chemistry_left_mask)}</td></tr>`).join('')}</tbody></table></div></details></details>`;
}
