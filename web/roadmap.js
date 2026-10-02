// Compact common decisions; full scientific details stay behind explicit actions.
// The five stages are a reading hierarchy over stored records. No stage completion,
// approval, ranking or inferred causal edge is produced here.
const roadmapSelections=new Map(),roadmapHistory=new Map();
// Which control opened the inspector, so closing returns focus where it started.
let roadmapOpener=null;
// Status is carried by a symbol and a word together, never by colour alone.
const roadmapMarks={selected:'■',proposed:'○',recorded:'▷',earlier:'▣',empty:'—',draft:'◌',working:'⋯'};
const roadmapOperations={tool:'연결된 도구로 실행할 수 있는 확인',external_observation:'보존 자료 확인 또는 새 관측이 필요한 확인',researcher_input:'연구자의 정보 보완이 필요한 확인',unconnected_method:'방법 연결을 먼저 확인해야 하는 단계'};
function roadmapHistoryKey(){return `${state.id}:${state.decision_id??'none'}`}
function roadmapModel(){return buildResearchRoadmap(state,intents(),roadmapHistory.get(roadmapHistoryKey()))}
function roadmapChosen(){return roadmapSelections.get(state.id)??null}
function roadmapStageIds(){return [...ROADMAP_STAGES.map(x=>x.id),'changes']}
async function loadRoadmapHistory(){
  if(!state?.decision_id)return;
  const wid=state.id,id=state.decision_id,key=roadmapHistoryKey();if(roadmapHistory.has(key))return;
  const prior=state.events.find(e=>e.kind==='hypothesis_wording_compared'&&e.body.receipt_id===id)?.body.reference?.decision_id;
  if(!prior){roadmapHistory.set(key,{status:'first'});return}
  roadmapHistory.set(key,{status:'loading'});
  try{
    const decision=await api(`/api/workspaces/${wid}/artifacts/${prior}?download=1`);
    if(!decision||typeof decision!=='object'||!Array.isArray(decision.intent_records))throw Error('이전 판단 형식 확인 필요');
    roadmapHistory.set(key,{status:'ready',workspaceId:wid,currentId:id,previousId:prior,decision});
  }catch(e){roadmapHistory.set(key,{status:'unavailable',message:e.message})}
  if(state?.id===wid&&state.decision_id===id)render();
}
function roadmapInputLinks(refs){
  return (refs??[]).map(id=>state.artifacts.some(a=>a.id===id)?sourceLinks([id]):
    state.events.some(e=>e.body.message_id===id)?button('message-source','원 요청',`data-id="${esc(id)}"`,'link-button small'):'').join('');
}
// current_conditions alone does not make an assessment a published result. If the job
// that produced it has not succeeded or been reused, its proposal stays a draft.
function roadmapDraftNote(assessment){
  if(!assessment?.artifact_id)return '';
  const artifact=state.artifacts.find(a=>a.id===assessment.artifact_id);
  const job=artifact?.meta?.job_id?state.jobs.find(j=>j.id===artifact.meta.job_id):null;
  if(!job)return '검토 결과의 생성 상태를 확인할 수 없습니다';
  if(['succeeded','reused'].includes(job.status))return '';
  return ['queued','running'].includes(job.status)?'검토 중인 추천 초안 · 발표된 판단 아님':'미완료 검토에서 보존한 추천 초안 · 발표된 판단 아님';
}
function roadmapRevisionText(model){
  if(!state.decision)return '질문에서 시작하는 연구';
  if(model.current)return `연구 기록 ${state.rev} · 현재 조건의 판단`;
  return `이전 판단 · 연구 기록 ${state.decision_rev} / 현재 연구 기록 ${state.rev} · 새 입력 반영은 확인되지 않았습니다`;
}
function roadmapOperationLabel(operation){return roadmapOperations[operation?.kind]??'확인 방법의 기록을 확인해야 합니다'}
const roadmapModelNames={'claude-opus-5':'Claude Opus 5','claude-opus-5-5':'Claude Opus 5.5','claude-fable-5-1':'Claude Fable 5.1','gpt-6-sol':'GPT-6 Sol',unknown:'모델 기록 없음'};
// Registered tool names carry the actual service (e.g. "공개 문헌 · Europe PMC").
function roadmapToolSpec(kind){return (status?.capabilities??[]).find(c=>c.id===kind)}
function roadmapToolName(kind){return roadmapToolSpec(kind)?.name??labels[kind]??kind}
function roadmapToolInput(text){return String(text??'').replace(/art_[0-9a-f]{16}/g,id=>artifactName(id))}
// Main-page line: which tools this judgment actually used, most-cited first.
function roadmapToolLine(){
  const u=roadmapToolUsage(state);if(!u.runs)return '';
  const names=u.tools.slice(0,4).map(t=>roadmapToolName(t.kind));
  return `<div class="roadmap-direction-block roadmap-tool-line"><span class="section-mark">이 판단에 쓰인 도구</span><p>${esc(names.join(' · '))}${u.tools.length>4?` 외 ${u.tools.length-4}종`:''}</p><p class="small muted">실행 ${number(u.runs)}회 · 모델에 반환 ${number(u.returned)}건 · ${u.current?'현재':'마지막 발표'} 판단의 근거로 인용 ${number(u.cited)}건</p>${button('roadmap-open','도구별 실행·인용 보기','id="roadmap-open-tools" data-stage="evidence" data-detail="roadmap-tool-usage"','small')}</div>`;
}
function roadmapToolPanel(){
  const u=roadmapToolUsage(state);if(!u.tools.length&&!u.modelCalls.length)return '';
  const statuses=st=>Object.entries(st).map(([k,n])=>`${jobLabels[k]??k} ${n}`).join(' · ');
  const inputs=t=>[...new Set(t.items.map(i=>roadmapToolInput(i.input)).filter(Boolean))];
  const row=t=>{const shown=inputs(t),spec=roadmapToolSpec(t.kind);return `<tr><th scope="row"${spec?.license?` title="${esc('출처·이용 조건: '+spec.license)}"`:''}>${esc(roadmapToolName(t.kind))}</th><td>${number(t.runs)}회<span class="roadmap-tool-status">${esc(statuses(t.statuses))}</span></td><td>${esc(shown.slice(0,2).join(' / ')||'—')}${shown.length>2?`<span class="roadmap-tool-status">외 입력 ${shown.length-2}개</span>`:''}</td><td>${number(t.returned)} / ${number(t.runs)}</td><td>${t.cited?`<strong>${number(t.cited)}</strong>`:'0'}</td></tr>`};
  const item=(t,i)=>`<li><span>${esc(roadmapToolName(t.kind))} · ${esc(jobLabels[i.status]??i.status)}${i.cited?' · 판단 인용':i.returned?' · 모델에 반환':''}</span><span class="small muted">${esc(roadmapToolInput(i.input)||'입력 기록 없음')}</span>${i.id?button('source','결과 원자료',`data-id="${esc(i.id)}"`,'link-button small'):'<span class="small muted">결과 없이 끝난 실행</span>'}</li>`;
  return `<details class="roadmap-tools" id="roadmap-tool-usage" data-detail-key="tool-usage"><summary>사용한 도구 ${u.tools.length}종 · 실행 ${number(u.runs)}회 · 판단 근거로 인용 ${number(u.cited)}건</summary>
    <p class="small muted">도구 결과가 모델에 반환됐는지와 ${u.current?'현재':'마지막으로 발표된'} 판단의 근거로 연결됐는지를 구분합니다. 반환은 모델이 읽었거나 이해했다는 뜻이 아니고, 인용은 판단 기록의 연결이지 과학적 검증이 아닙니다. 실패·일부 반환도 그대로 보여줍니다.</p>
    <div class="table-scroll" tabindex="0" role="region" aria-label="사용한 도구 요약"><table class="roadmap-tool-table"><thead><tr><th scope="col">도구</th><th scope="col">실행</th><th scope="col">대표 입력</th><th scope="col">모델에 반환</th><th scope="col">판단 인용</th></tr></thead><tbody>${u.tools.map(row).join('')}</tbody></table></div>
    ${u.citedOutsideTools?`<p class="small muted">도구 결과가 아닌 자료(원 입력·검토 기록 등)에 연결된 인용 ${number(u.citedOutsideTools)}건은 위 표에 포함하지 않았습니다.</p>`:''}
    ${u.modelCalls.length?`<p class="small">판단 생성 모델 호출(요청 기준, 이전 기록 포함): ${u.modelCalls.map(m=>`${esc(roadmapModelNames[m.model]??m.model)} ${number(m.count)}회`).join(' · ')}. 실제 응답 모델은 각 호출 기록에서 확인합니다.</p>`:''}
    <details data-detail-key="tool-usage-items"><summary>실행별 기록 ${number(u.runs)}건 보기</summary><ul class="roadmap-tool-items">${u.tools.flatMap(t=>t.items.slice().reverse().map(i=>item(t,i))).join('')}</ul></details>
  </details>`;
}
function roadmapRow(node,index,selected){
  const open=selected===node.id,mark=roadmapMarks[node.mark]??'—';
  return `<li class="roadmap-node ${esc(node.mark)}${open?' is-open':''}"><button type="button" id="roadmap-${node.id}" data-action="roadmap-stage" data-stage="${node.id}" aria-expanded="${open}" aria-controls="roadmap-inspector"><span class="roadmap-step">${String(index+1).padStart(2,'0')}</span><span class="roadmap-node-title">${esc(node.title)}</span><span class="roadmap-preview">${esc(roadmapSummary(node.summary,96))}</span><span class="roadmap-state"><span class="roadmap-mark"><span aria-hidden="true">${mark}</span> ${esc(node.status)}</span>${node.change?`<span class="roadmap-change-mark">↻ ${esc(node.change)}</span>`:''}</span><span class="roadmap-open-sign" aria-hidden="true">${open?'−':'＋'}</span></button></li>`;
}
// Default inspector content: the direction that is recorded right now, and what is
// proposed next. Neither is presented as an executed or finished step.
function roadmapDirection(model){
  const d=state.decision;
  if(!d)return `<div class="roadmap-direction"><p class="roadmap-direction-text small muted">아직 발표된 판단이 없습니다. 위 단계를 누르면 지금까지 기록된 것이 나옵니다.</p></div>`;
  const check=d.research_loop?.next_checks?.[0];
  const candidates=candidateOptions();
  if(candidates.length)loadCandidateStructures();
  const candidate=x=>{const drawn=candidateStructureRow(x.option_id),picture=drawn&&structureThumb(drawn);
    return `<div class="overview-candidate">${picture?`<div class="overview-structure">${picture}</div>`:''}<div><strong>${esc(candidateDisplayName(x))}</strong><span class="roadmap-label">${esc(optionStatus[x.assessment?.status??'unreviewed']??'검토 기록')}${x.assessment?.current_conditions===false?' · 이전 조건':''}</span>${x.origin==='generated_structure_proposal'?'<span class="roadmap-label">설계 구조 · 활성 측정 전</span>':''}${button('discovery-detail','후보 상세',`data-id="${esc(x.option_id)}"`,'link-button small')}</div></div>`;};
  return `<div class="roadmap-direction overview-focus">
    <div class="roadmap-direction-block"><h3 class="overview-label">${model.current?'현재 판단':'이전 판단 · 새 입력 검토 중'}</h3><p class="roadmap-direction-text">${judgmentText(researcherWording(d.recommendation))}</p><div class="overview-actions">${button('roadmap-open','기전 살펴보기','data-stage="mechanisms"','small')}${button('roadmap-open','판단 근거','id="roadmap-open-reason" data-stage="next" data-detail="roadmap-rationale"','link-button small')}</div></div>
    <div class="roadmap-direction-block"><h3 class="overview-label">검토한 후보</h3>${candidates.slice(0,2).map(candidate).join('')||'<p class="roadmap-next-text muted">기전과 자료를 검토하며 비교할 후보를 찾습니다.</p>'}${button('roadmap-open',candidates.length>2?`검토 후보 ${candidates.length}개 보기`:'후보와 전체 목록','data-stage="candidates"','small')}</div>
    <div class="roadmap-direction-block"><h3 class="overview-label">다음 확인</h3>${check?`<span class="option-tag">${esc(CHECK_KIND[check.operation?.kind]??'연구 제안')}</span>`:''}<p class="roadmap-next-text">${esc(researcherWording(check?.question??d.next_actions?.[0]??'근거를 검토해 다음 확인을 정합니다.'))}</p>${button('roadmap-open','대상·대조군·판독 보기','id="roadmap-open-check" data-stage="next"','small')}</div>
  </div><details class="overview-tools" data-detail-key="overview-tools"><summary>사용한 자료·도구와 실행 기록</summary>${roadmapToolLine()}</details>`;
}
function roadmapFoot(model){
  const changed=model.changedNodes.length;
  return `<div class="roadmap-foot"><details class="roadmap-reading-note"><summary>${changed?`이전 판단에서 달라진 단계 ${changed}개`:'이 화면의 기록 읽기'}</summary><p class="small muted">단계를 열면 판단 이유와 다른 선택지, 원자료를 확인할 수 있습니다. 기록의 변화는 과학적 재검증이나 인과의 증거와 구분합니다.</p></details>${state.decision?button('roadmap-open','변경 전후 보기','id="roadmap-open-changes" data-stage="changes"','small'):''}</div>`;
}
const roadmapFunctionNames={search_literature:'문헌 검색',find_entities:'표적·질환 식별',read_open_article:'공개 원문 읽기',inspect_article_references:'참고문헌 확인',collect_public_evidence:'공개 근거 함께 조회',inspect_artifact:'저장 자료 다시 보기',read_evidence_bundle:'근거 묶음 읽기',read_clinical_trial:'임상시험 상세',read_drug_label:'약물 라벨 원문',resolve_literature_compounds:'문헌 화합물 구조',materialize_compound_candidates:'후보 구조 연결',compute_properties:'분자 물성 계산',predict_admet:'ADMET 예측',record_source_candidates:'출처 후보 기록',record_discovery_review:'선택지 검토 기록',inspect_discovery_options:'선택지 살펴보기'};
function roadmapLiveCard(){
  const p=roadmapLiveProgress(state);if(!p)return '';
  const used=Object.entries(p.functions).map(([f,n])=>`${roadmapFunctionNames[f]??f} ${n}회`).join(' · ');
  const call=p.completedCalls+(p.status==='running'?1:0);
  return `<div class="roadmap-activity roadmap-live" role="status" aria-live="polite"><span class="section-mark">${p.status==='queued'?'조사 대기 중':'조사 진행 중'} · 시작 ${esc(time(p.started))}${p.elapsedMinutes===null?'':` · ${p.elapsedMinutes}분 경과`}${call?` · 모델 호출 ${call}회째`:''}</span>
    ${p.nextGoal?`<p><strong>지금 확인하려는 것</strong> · ${esc(roadmapSummary(p.nextGoal,240))} <span class="small muted">(모델의 잠정 메모)</span></p>`:'<p>질문을 정리하고 필요한 자료를 찾고 있습니다.</p>'}
    ${used?`<p class="small">지금까지 실행한 도구: ${esc(used)}</p>`:''}
    <p class="small muted">첫 판단이 게시되면 기전과 접근부터 실험 권고까지 채워집니다. 보통 20–60분 걸리며 화면은 자동으로 갱신됩니다.${p.findings?` 잠정 발견 ${p.findings}개는 판단 전 메모입니다.`:''}</p>
    ${button('roadmap-progress-open','조사 과정 자세히 보기','','small')}</div>`;
}
function roadmapActivity(){
  const activity=currentResearchActivity(state);if(!activity)return roadmapLiveCard();
  return `<div class="roadmap-activity" role="note" aria-label="현재 진행 중인 확인"><span class="section-mark">${esc(activity.status)}</span><p>${esc(activity.question)}</p></div>`;
}
function renderRoadmap(){
  const model=roadmapModel(),selected=roadmapChosen();
  const stage=selected?model.nodes.find(x=>x.id===selected):null;
  const label=selected?(stage?stage.title:'이전 판단과 현재 기록 비교'):'현재의 연구 방향';
  return `<section class="research-roadmap" aria-label="연구 로드맵"><div class="roadmap-heading"><h2>연구 흐름</h2><span class="roadmap-revision">${esc(roadmapRevisionText(model))}</span></div>
    ${roadmapActivity()}
    <div class="roadmap-layout">
      <ol class="roadmap-track">${model.nodes.map((n,i)=>roadmapRow(n,i,selected)).join('')}</ol>
      <div id="roadmap-inspector" class="roadmap-inspector" tabindex="-1" role="region" aria-label="${esc(label)}">${selected?renderRoadmapInspector(selected,model):roadmapDirection(model)}</div>
    </div>
    ${roadmapFoot(model)}
  </section>`;
}
function renderRoadmapInspector(selected,model){
  const stage=model.nodes.find(x=>x.id===selected);
  return `<div class="roadmap-inspector-heading"><div><span class="section-mark">${stage?esc(stage.hint):'이전 판단과 현재 기록 비교'}</span><h3>${stage?esc(stage.title):'어디가 달라졌나요?'}</h3></div>${button('roadmap-close','닫기','aria-label="단계 상세 닫기"','quiet small')}</div><div class="roadmap-panel">${
    selected==='goal'?roadmapGoalPanel():selected==='mechanisms'||selected==='candidates'?roadmapOptionsPanel(stage):
    selected==='evidence'?roadmapEvidencePanel():selected==='next'?roadmapNextPanel(model):roadmapChangesPanel(model)}</div>`;
}
function roadmapGoalPanel(){
  // The researcher's own words come first and stay visible; the structured records below are the
  // model's reading of them, so a reader can check one against the other without opening anything.
  const original=state.events.find(e=>e.kind==='message'),rows=intents();
  return `${original?`<section class="original-request"><span class="roadmap-label">연구자가 입력한 원 요청</span><p class="prose">${esc(original.body.text)}</p>${roadmapInputLinks([original.body.message_id])}</section>`:''}
    <h4 class="structured-heading">모델이 구조화한 기록</h4>
    <div class="roadmap-intents">${rows.map(r=>`<article><span class="roadmap-label">${esc(r.label)} · ${r.origin==='researcher'?'연구자 지정 기록':r.origin==='unknown'?'조건 미확인':'해석 초안'}</span><p>${esc(r.text)}</p>${roadmapInputLinks(r.source_refs)}</article>`).join('')||'<p>아직 질문을 항목별로 정리하지 않았습니다. 원 요청은 그대로 보존합니다.</p>'}</div>
    ${rows.length?'':'<p class="muted">아직 구조화된 기록이 없습니다. 위 원 요청이 연구자가 적은 그대로입니다.</p>'}
    <p class="small muted">위는 연구자가 적은 그대로이고, 아래는 그것을 모델이 구조화한 기록입니다. 목표를 적었다는 것이 치료 경로의 승인은 아닙니다.</p>
    <details class="roadmap-records" data-detail-key="task-decomposition"><summary>이 질문의 작업 분해·실행 기록</summary>${latestFrame()?`<p class="prose">${esc(latestFrame().current_question)}</p>${Number.isInteger(latestFrame().carried_from_rev)?`<p class="small muted">연구 기록 ${esc(latestFrame().carried_from_rev)}에서 만든 분해를 그대로 이어서 쓰고 있습니다. 질문이 실제로 바뀌면 다시 나눕니다.</p>`:''}${latestFrame().task_brief.map((t,i)=>`<div class="task-row"><span>${i+1}</span><div>${esc(t.question)}<small>${esc(t.purpose)}</small>${t.depends_on.length?`<small>먼저 필요한 결과: ${esc(t.depends_on.join(', '))}</small>`:''}</div></div>`).join('')}${questions(latestFrame().questions)}`:'<p class="small muted">아직 작업 분해 기록이 없습니다.</p>'}${jobsPanel()}</details>
    <div class="detail-actions">${button('edit-intent','목표·조건 수정','','small')}${button('roadmap-write','새 조건 입력','data-kind="correction"','small')}</div>`;
}
// Candidate structures are fetched only when stage 3 is open, from a screen-only route: a
// drawing is for a person to read, and putting it anywhere a model request is answered would
// spend context on something the model cannot use.
let candidateStructures=null,candidateStructuresFor=null,candidateStructuresVersion=0,candidateStructuresPendingFor=null;
function candidateStructuresKey(){return state?`${state.id}@${state.event_cursor}@${state.rev}`:null}
async function loadCandidateStructures(){
  if(!state)return;
  const wid=state.id,key=candidateStructuresKey();
  if(candidateStructuresFor===key||candidateStructuresPendingFor===key)return;
  const version=++candidateStructuresVersion;
  candidateStructuresPendingFor=key;
  try{
    const value=await api(`/api/workspaces/${encodeURIComponent(wid)}/candidate-structures`);
    if(candidateStructuresKey()!==key||version!==candidateStructuresVersion)return;
    candidateStructures=value;
    candidateStructuresFor=key;
  }catch(error){
    if(candidateStructuresKey()===key&&version===candidateStructuresVersion){candidateStructures=null;candidateStructuresFor=key}
  }finally{
    if(version===candidateStructuresVersion)candidateStructuresPendingFor=null;
    if(candidateStructuresKey()===key&&version===candidateStructuresVersion)render();
  }
}
function candidateStructureRow(optionId){
  if(candidateStructuresFor!==candidateStructuresKey())return null;
  return ((candidateStructures||{}).rows||[]).find(r=>r&&r.option_id===optionId)||null;
}
// A candidate is shown under the mechanism its own record says it targets (P4): the pair is the
// model's recorded link, not an inference from names. Stage 2 can narrow stage 3 to one mechanism
// (P5), and the narrowing is stated on screen with a way back to every candidate.
const mechanismFocus=new Map();
let sendMode='review';
function candidateOptions(){return roadmapModel().nodes.find(n=>n.id==='candidates')?.options??[]}
function mechanismOptions(){return roadmapModel().nodes.find(n=>n.id==='mechanisms')?.options??[]}
function candidateMechanismId(option){return option?.assessment?.targets_mechanism?.option_id??''}
function mechanismCandidateCount(id){return candidateOptions().filter(x=>candidateMechanismId(x)===id).length}
function candidateMechanismLabel(id){
  const known=mechanismOptions().find(x=>x.option_id===id);
  if(known)return known.label;
  const link=candidateOptions().map(x=>x.assessment?.targets_mechanism).find(t=>t?.option_id===id);
  return link?.label??id;
}
function candidateMechanismGroups(rows){
  const focus=mechanismFocus.get(state.id);
  const shown=focus?rows.filter(x=>candidateMechanismId(x)===focus):rows;
  const groups=new Map();
  for(const row of shown){
    const id=candidateMechanismId(row);
    if(!groups.has(id))groups.set(id,[]);
    groups.get(id).push(row);
  }
  return [...groups].map(([id,items])=>[id||'unlinked',
    id?`겨냥한 기전 · ${candidateMechanismLabel(id)}`:'겨냥한 기전이 기록되지 않은 후보',items]);
}
function mechanismKindGroups(rows){
  const groups=new Map();
  for(const row of rows){
    const kind=roadmapOptionKind(row);
    if(!groups.has(kind))groups.set(kind,[]);
    groups.get(kind).push(row);
  }
  // One kind needs no heading: the stage title already says what it is.
  if(groups.size<2)return [...groups].map(([kind,items])=>[kind,'',items]);
  return [...groups].map(([kind,items])=>[kind,optionKinds[kind]??'선택지',items]);
}
function candidateOverviewTable(rows){
  return `<div class="table-scroll candidate-overview-scroll"><table class="candidate-overview"><thead><tr><th scope="col">구조</th><th scope="col">후보</th><th scope="col">검토 상태</th><th scope="col">다음 확인</th></tr></thead><tbody>${rows.map(x=>{
    const a=x.assessment,drawn=candidateStructureRow(x.option_id),picture=drawn&&structureThumb(drawn);
    const generated=x.origin==='generated_structure_proposal';
    const type=optionKinds[roadmapOptionKind(x)]??'후보';
    return `<tr data-candidate-option="${esc(x.option_id)}"><td class="candidate-picture">${picture||`<span class="muted">${['rna','rna_candidate'].includes(roadmapOptionKind(x))?'서열·조건':'구조 미리보기 없음'}</span>`}</td><td><strong>${esc(candidateDisplayName(x))}</strong><span class="roadmap-label">${esc(type)}</span>${drawn?.depiction?.formula?`<span class="small muted">${esc(drawn.depiction.formula)}</span>`:''}${x.candidate_artifact_id?`<span class="roadmap-label">${esc(artifactName(x.candidate_artifact_id))}</span>`:''}${button('discovery-detail','상세·원자료',`data-id="${esc(x.option_id)}"`,'link-button small')}</td><td><span class="option-tag ${esc(a?.status??'unreviewed')}">${esc(optionStatus[a?.status??'unreviewed'])}</span>${generated?'<span class="roadmap-label">설계 구조 · 활성 측정 전</span>':''}${a?.current_conditions===false?'<span class="roadmap-flag">이전 조건의 검토</span>':''}${roadmapDraftNote(a)?`<span class="roadmap-flag">${esc(roadmapDraftNote(a))}</span>`:''}</td><td>${esc(researcherWording(roadmapSummary(a?.next_action??'검토 전',180)))}</td></tr>`;
  }).join('')}</tbody></table></div>`;
}
function roadmapOptionsPanel(node){
  const ranked=node?.id==='mechanisms'?mechanismRankSection():'';
  const rows=node?.options??[],spaces=node?.id==='candidates'?state.artifacts.filter(a=>a.kind==='rna_candidate_space'):[];
  const candidates=node?.id==='candidates';
  if(candidates)loadCandidateStructures();
  const earlier=rows.filter(x=>x.assessment?.current_conditions===false).length;
  const unknown=rows.filter(x=>x.assessment&&typeof x.assessment.current_conditions!=='boolean').length;
  const row=x=>{
    const a=x.assessment,draft=roadmapDraftNote(a);
    const drawn=candidates?candidateStructureRow(x.option_id):null;
    const picture=drawn&&structureThumb(drawn)
      ?`<div class="roadmap-structure">${structureThumb(drawn)}${
          drawn.depiction&&drawn.depiction.formula?`<span class="small muted">${esc(drawn.depiction.formula)}</span>`:''}</div>`:'';
    return `<article class="roadmap-option-row${picture?' has-structure':''}">${picture}<div class="roadmap-option-main"><strong>${esc(candidateDisplayName(x))}</strong><span class="roadmap-label">${esc(optionKinds[roadmapOptionKind(x)]??'선택지')} · ${esc(optionStatus[a?.status??'unreviewed']??'선택지')}</span>${a?.current_conditions===false?'<span class="roadmap-flag">이전 조건의 검토 · 새 입력 반영은 확인되지 않았습니다</span>':''}${draft?`<span class="roadmap-flag">${esc(draft)}</span>`:''}${Number.isInteger(a?.based_rev)&&a.based_rev!==state.rev?`<span class="roadmap-label">검토 당시 연구 기록 ${esc(a.based_rev)} · 현재 연구 기록 ${esc(state.rev)}</span>`:''}</div><div class="roadmap-option-actions">${button('discovery-detail','이유·원자료',`data-id="${esc(x.option_id)}"`,'small')}${node?.id==='mechanisms'&&mechanismCandidateCount(x.option_id)?button('roadmap-focus-mechanism',`이 기전의 후보 ${mechanismCandidateCount(x.option_id)}개 보기`,`data-id="${esc(x.option_id)}"`,'small'):''}</div></article>`;
  };
  const groups=candidates?candidateMechanismGroups(rows):mechanismKindGroups(rows);
  const focus=candidates?mechanismFocus.get(state.id):'';
  const groupBlock=([key,label,items])=>`<section class="roadmap-option-group"${key?` data-group="${esc(key)}"`:''}>${label?`<h4 class="roadmap-group-heading">${esc(label)} <span class="small muted">${items.length}개</span></h4>`:''}${candidates?candidateOverviewTable(items):`${items.slice(0,3).map(row).join('')}${items.length>3?`<details data-detail-key="rest:${esc(key)}"><summary>이 묶음의 나머지 ${items.length-3}개</summary>${items.slice(3).map(row).join('')}</details>`:''}`}</section>`;
  return `${ranked}${node?.selected?`<div class="roadmap-choice"><strong>연구자가 검토할 경로로 선택</strong><p>${esc(node.selected.label)}</p>${node.selected.reason?`<p class="small">${esc(node.selected.reason)}</p>`:''}<span class="small muted">선택 당시 연구 기록 ${esc(node.selected.state_rev)} · 선택 자체가 효능 검증은 아닙니다.</span></div>`:''}
    ${candidates&&focus?`<p class="roadmap-focus-note">기전 <strong>${esc(candidateMechanismLabel(focus))}</strong>를 겨냥한 후보만 보고 있습니다. ${button('roadmap-focus-clear','전체 후보 보기','','small')}</p>`:''}
    ${!candidates&&ranked?`<details class="mechanism-review-records" data-detail-key="mechanism-review-records"><summary>개별 검토 기록 ${rows.length}개</summary>${groups.map(groupBlock).join('')}</details>`:groups.map(groupBlock).join('')}
    ${earlier?`<p class="small muted">위 기록 중 ${earlier}개는 이전 조건의 검토입니다. 현재 조건의 추천과 구분해 확인하세요.</p>`:''}
    ${unknown?`<p class="small muted">${unknown}개 기록은 현재 조건 적용 여부가 미확인입니다. 이전 조건으로 단정하지 않습니다.</p>`:''}
    ${!rows.length?`<p>${node?.count?`이 단계에 ${node.count}개 선택지를 보존하고 있습니다. 개별 추천 기록은 아직 없으므로 아래 전체 목록에서 미검토·보류·대안을 확인하세요.`:'이 단계의 정리된 선택지는 아직 없습니다. 판단 원문·계산에 등장하는 후보까지 모두 평가했다는 뜻은 아닙니다.'}</p>`:''}
    ${spaces.map(a=>`<div class="roadmap-option-row"><div class="roadmap-option-main"><strong>보존한 전체 RNA 서열</strong><span class="roadmap-label">${number(a.meta.summary?.unique_guide_sequences)}개 · 효능 순위 아님</span></div>${button('source','서열 목록·조건',`data-id="${esc(a.id)}"`,'small')}</div>`).join('')}
    ${node?.id==='mechanisms'&&state.decision?.alternatives?.length?`<details><summary>판단에 함께 남긴 대안 ${state.decision.alternatives.length}개</summary>${state.decision.alternatives.map(a=>`<article class="alternative"><h4>${esc(a.title)}</h4><p>${judgmentText(a.reason)}</p><p>현재 실행 범위: ${esc(a.execution_support)}</p>${list(a.uncertainties)}</article>`).join('')}</details>`:''}
    <div class="detail-actions">${button('roadmap-pool',optionsOpen&&optionsStage===node?.id?'전체 목록 접기':`미검토·대안까지 모두 보기 (${node?.count??0})`,`id="roadmap-pool-${esc(node?.id??'')}" data-stage="${esc(node?.id??'')}" aria-expanded="${optionsOpen&&optionsStage===node?.id}"`,'small')}${button('discovery-propose','다른 경로 제안하기','','small')}</div>
    ${optionsOpen&&optionsStage===node?.id?`<div class="roadmap-pool-inline" id="roadmap-pool-inline">${renderOptionBrowser()}</div>`:''}
    <details class="roadmap-reading-note"><summary>목록과 구조 그림의 범위</summary><p class="small muted">검토했거나 선택한 후보를 먼저 표시합니다. 미검토 후보도 전체 목록에 보존합니다. 구조 그림은 기록된 구조 문자열을 그린 것으로, 실제 시료 확인이나 활성 측정이 아닙니다. 서로 다른 비교 조건의 순위를 하나로 합치지 않습니다.</p></details>`;
}
function roadmapEvidencePanel(){
  const dec=state.decision,frame=latestFrame(),current=dec&&state.decision_rev===state.rev;
  const hs=current?dec.research_loop?.hypotheses??[]:frame?.hypotheses??dec?.research_loop?.hypotheses??[];
  const results=state.artifacts.filter(a=>a.meta.result_status&&a.kind!=='model_receipt');
  const unfinished=results.filter(a=>!['succeeded','reused'].includes(a.meta.result_status));
  return `<p class="small muted">${current?'현재 판단의 가설과 실제 결과를 나란히 확인합니다.':'새 입력이 반영되기 전 기록 또는 검토 중인 초안입니다.'} 계산이 성공했다는 사실은 그 자체로 가설을 지지하지 않습니다.</p>
    ${unfinished.length?`<p class="notice-inline">완료되지 않은 조회·계산 ${unfinished.length}건이 있습니다. 결과가 없다는 것과 실행에 실패했다는 것을 구별하세요.</p>`:''}
    ${roadmapToolPanel()}
    ${roadmapEvidenceLedger()}
    <details class="roadmap-hypothesis-text" data-detail-key="complete-hypothesis-text"><summary>가설의 전체 설명·예상과 피드백</summary><div class="hypotheses-section">${hs.map(h=>renderHypothesis(h,!!dec?.research_loop&&(!frame||current))).join('')}${renderOmittedHypotheses()}</div></details>
    <details class="roadmap-results" data-detail-key="actual-results"><summary>실제 계산·조회 결과 ${results.length}개 열기</summary><p class="small muted">최신 자료가 있다는 것과 그 원문을 읽었다는 것은 다릅니다. 읽기 완료 표시는 만들지 않습니다.</p><div class="roadmap-result-list">${results.slice().reverse().map(a=>`<div>${button('source',esc(artifactName(a.id)),`data-id="${esc(a.id)}"`,'link-button')}<span>${esc(labels[a.kind]??a.kind)} · ${esc(jobLabels[a.meta.result_status]??a.meta.result_status)}</span></div>`).join('')||'<p>아직 계산·조회 결과가 없습니다.</p>'}</div></details>
    ${dec?.unknowns?.length?`<details><summary>판단에 남은 불확실성 ${dec.unknowns.length}개</summary>${list(dec.unknowns)}</details>`:''}
    <div class="detail-actions">${button('tab','원자료·전체 결과 열기','data-id="data"','small')}</div>`;
}
function roadmapEvidenceLedger(){
  const model=roadmapModel(),claims=roadmapClaimRecords(state.decision);
  const total=claims.reduce((n,c)=>n+(c.evidence??[]).length,0);
  const changes=new Map([...(model.diffs?.hypotheses??[]),...(model.diffs?.claims??[])].map(x=>[x.id,x]));
  const statuses={added:'새 기록',omitted:'이번 판단에 없음',changed:'기록 변경',unchanged:'기록 동일',unavailable:'비교 불가'};
  const visible=claims.map(c=>({...c,rows:c.evidence??[]}));
  return `<section class="roadmap-ledger" aria-label="주장별 근거와 적용 조건">
    <div class="roadmap-ledger-heading"><h4>어떤 근거로 판단했나요?</h4><span class="small muted">${model.current?'현재 발표 판단':'이전 발표 판단 · 새 입력 반영 전'}</span></div>
    <p class="small muted">연결 기록 ${total}개 · 같은 출처가 여러 주장에 연결될 수 있어 독립 근거 수나 신뢰도 점수가 아닙니다.</p>
    ${visible.map(c=>{const change=changes.get(c.id),level={hypothesis:'전체 가설',part:'가설의 일부',alternative:'조건부 설명'}[c.level];return `<details class="roadmap-claim" data-claim="${esc(c.id)}" data-detail-key="claim:${esc(c.id)}"><summary><span>${esc(roadmapSummary(c.statement,110))}</span><span class="roadmap-claim-status">${esc(hypothesisLabels[c.assessment]??'판단 미확인')}</span></summary><p class="small muted">${esc(level)} · ${esc(c.claim_id)} · ${change?esc(statuses[change.status]):model.previous?'이전·현재 대응 확인 필요':'이전 판단 비교 전'}</p><p>${judgmentText(c.statement)}</p>${c.rows.length?`<div class="table-scroll roadmap-evidence-table" tabindex="0" role="region" aria-label="${esc(c.claim_id)}의 근거 표"><table><caption>${esc(c.claim_id)} · 출처에 연결된 원 판단 기록</caption><thead><tr><th scope="col">관계</th><th scope="col">적용 조건</th><th scope="col">확인한 내용</th><th scope="col">출처</th></tr></thead><tbody>${c.rows.map(e=>`<tr data-source="${esc(e.source_id)}"><td>${esc(relationLabels[e.relation]??e.relation)}</td><td>${judgmentText(e.applicability)}</td><td>${judgmentText(e.detail)}</td><td>${e.source_type==='artifact'?sourceLinks([e.source_id]):button('message-source','원 입력',`data-id="${esc(e.source_id)}"`,'link-button small')}</td></tr>`).join('')}</tbody></table></div>`:'<p class="small muted">이 항목에 직접 연결한 근거 기록이 없습니다. 전체 가설의 근거와 구분합니다.</p>'}</details>`}).join('')||'<p>주장별로 연결한 근거 기록이 아직 없습니다. 근거가 없다는 뜻은 아닙니다.</p>'}
  </section>`;
}
// A6, second half: when the candidate this research is recommending has already been in people,
// the next step is not a bench experiment designed from nothing - it is what the reported results
// and adverse events leave open. Only the human records the candidate's own review actually cited
// are shown, so nothing is matched by name or guessed.
function existingHumanRecords(model){
  const stage=model.nodes.find(n=>n.id==='candidates');
  const candidate=stage?.selected??stage?.recommended?.[0];
  const assessment=candidate&&(candidate.assessment??null);
  if(!assessment)return null;
  const cited=[...(assessment.support_source_ids??[]),...(assessment.challenge_source_ids??[])];
  const records=state.artifacts.filter(a=>cited.includes(a.id)
    &&['clinical_trial','drug_label'].includes(a.kind)&&a.meta.result_status!=='failed');
  return records.length?{label:candidate.label,records}:null;
}
function roadmapExistingDrug(model){
  const found=existingHumanRecords(model);
  if(!found)return '';
  const line=a=>{
    const s=a.meta.summary??{};
    const parts=[a.kind==='clinical_trial'?(s.nct_id??'등록 기록'):(s.title??'허가 라벨'),
                 a.kind==='clinical_trial'?(s.overall_status??'상태 미확인'):'',
                 a.kind==='clinical_trial'?(s.has_results?'결과 보고 있음':'결과 보고 없음'):''];
    return `<li>${parts.filter(Boolean).map(x=>esc(x)).join(' · ')}
      ${button('source','원 기록 열기',`data-id="${esc(a.id)}"`,'link-button small')}</li>`;
  };
  return `<section class="existing-drug"><h4>이 후보는 이미 사람에서 쓰인 기록이 있습니다 · ${esc(found.label)}</h4>
    <p class="small muted">아래는 이 후보의 검토가 실제로 인용한 임상 기록입니다. 이름이 같아 보이는 다른 기록을 끌어오지 않았습니다.</p>
    <ul class="existing-drug-list">${found.records.map(line).join('')}</ul>
    <p class="small">다음 행동은 새 실험을 처음부터 설계하는 것보다, 보고된 1차 종점·이상반응이 남긴 질문을 이어가는 쪽일 수 있습니다. 아래 권고가 그 점을 반영했는지 확인하세요.</p>
    <p class="limit">사람에서 쓰인 기록이 있다는 것은 이 질환·이 목적에 효과가 있다는 뜻이 아닙니다. 적응증·대상·용량·기간이 다르면 결과를 옮기지 않습니다.</p>
  </section>`;
}
function roadmapNextPanel(model){
  const d=state.decision,current=model.current,checks=d?.research_loop?.next_checks??[];
  const node=model.nodes.find(n=>n.id==='next');
  return `${d?`<details class="roadmap-rationale" id="roadmap-rationale"><summary>현재 판단의 전체 문장과 이유</summary><p class="prose decision-title">${judgmentText(researcherWording(d.recommendation))}</p><p class="prose">${judgmentText(researcherWording(d.reason))}</p>${sourceLinks(d.evidence_refs)}${questions(d.questions)}</details>`:''}
    ${!current&&d?'<p class="notice-inline">이전 조건의 제안입니다. 새 입력에 맞는 검토 후 실제 실행할 수 있습니다.</p>':''}
    ${node?.jobStatus?`<p class="small muted">첫 확인의 실행 기록: ${esc(jobLabels[node.jobStatus]??node.jobStatus)} · 실행 상태이며 결과의 해석과는 별도입니다.</p>`:''}
    ${checks[0]?`<p class="roadmap-operation">${esc(roadmapOperationLabel(checks[0].operation))}</p>`:''}
    ${roadmapExistingDrug(model)}
    <section class="next-research">${checks.map((c,i)=>renderCheck(c,current,i)).join('')||list(d?.next_actions)||'<p>아직 다음 확인이 제안되지 않았습니다.</p>'}</section>`;
}
function roadmapChangesPanel(model){
  const previous=model.previous,d=state.decision,history=roadmapHistory.get(roadmapHistoryKey());
  const names={statement:'가설 문장',expected_observation:'예상 관측',assessment:'평가',rationale:'이유',evidence:'연결 근거',assessment_scope:'부분별 판단',conditional_alternatives:'조건부 설명',question:'확인 질문',purpose:'목적',hypothesis_ids:'연결 가설',operation:'실행 방법',possible_outcomes:'결과별 해석',outcome_links:'결과 연결',scope_targets:'대상 부분',label:'항목 이름',text:'조건 내용',origin:'입력 출처',source_refs:'원 입력'};
  const record=(x)=>`<article class="roadmap-diff ${x.status}"><span class="roadmap-diff-tag">${({added:'＋ 새 기록',omitted:'− 이번 판단에 없음',changed:'↻ 기록 변경',unchanged:'＝ 기록 동일',unavailable:'? 비교 불가'})[x.status]}</span><strong>${esc(x.id)}</strong>${x.reason?`<p class="notice-inline">${esc(x.reason)}</p>`:''}<p>${esc(roadmapSummary(x.after?.statement??x.after?.question??x.after?.text??x.before?.statement??x.before?.question??x.before?.text,120))}</p>${x.status==='changed'?`<span class="small muted">${x.fields.map(f=>names[f]??f).join(' · ')}</span>`:''}${x.status==='omitted'?'<span class="small muted">이번 판단에 없다는 기록일 뿐 기각·반증이 아닙니다.</span>':''}${x.status!=='unchanged'?`<details><summary>정확한 이전·현재 값 비교</summary>${x.fields.map(f=>`<div class="roadmap-diff-values"><h4>${esc(names[f]??f)}</h4><div><span>이전</span>${typeof x.before?.[f]==='string'?`<p class="prose">${esc(x.before[f])}</p>`:json(x.before?.[f]??null)}</div><div><span>현재</span>${typeof x.after?.[f]==='string'?`<p class="prose">${esc(x.after[f])}</p>`:json(x.after?.[f]??null)}</div></div>`).join('')}</details>`:''}</article>`;
  return `${!model.current?'<p class="notice-inline">새 입력의 반영은 아직 확인되지 않았습니다. 아래 변경은 마지막으로 발표된 두 판단 사이의 기록입니다.</p>':''}
    ${renderInputChanges()}
    ${d?`<details><summary>이번 판단이 설명한 변경·유지 이유</summary><div class="change-grid"><div><h4>바꾼 내용</h4>${decisionChangeList(d.changed)}</div><div><h4>유지한 내용</h4>${decisionChangeList(d.preserved)}</div></div>${d.research_loop?.revision_rationale?`<p class="prose small">${judgmentText(d.research_loop.revision_rationale)}</p>`:''}</details>`:''}
    ${previous?`<p class="small muted">원본의 값과 연결을 비교했습니다. 같은 문구가 과학적 재검증을 뜻하지 않으며, 바뀐 기록 모두가 새 입력 때문이라고 추정하지 않습니다.</p>${[['goals','목표·조건'],['hypotheses','전체 가설·근거'],['claims','가설의 부분·조건부 설명'],['checks','다음 확인']].map(([key,title])=>`<details data-detail-key="diff:${key}"><summary>${title}의 이전·현재 비교</summary>${model.diffs[key].map(record).join('')||'<p>비교할 항목이 없습니다.</p>'}</details>`).join('')}<div class="detail-actions">${button('source','이전 판단 원문',`data-id="${esc(model.priorLink.decision_id)}"`,'small')}${button('source','현재 판단 원문',`data-id="${esc(state.decision_id)}"`,'small')}</div>`:
      model.historyStatus==='unavailable'?`<p class="notice-inline"><span aria-hidden="true">? </span>이전 판단 원문을 불러오지 못해 비교할 수 없습니다. 동일 여부도 변경 여부도 단정하지 않습니다.${history?.message?` (${esc(history.message)})`:''}</p>`:
      `<p class="small muted">${model.historyStatus==='first'?'이전에 발표된 판단과의 비교 기록이 아직 없습니다.':'이전 판단 원문을 확인하고 있습니다.'}</p>`}
    <div class="detail-actions">${button('tab','모든 입력·변경 기록','data-id="history"','small')}${button('roadmap-write','새 관측·정정 반영','data-kind="correction"','small')}</div>`;
}
// After a researcher enters a result, what the judgement kept and what it changed is the answer
// they asked for, so it is shown in place rather than behind the change viewer. This states the
// recorded order and the model's own rationale; it does not assert that the result caused it.
function roadmapObservationAnswer(model){
  const event=model.answeredObservation;
  if(!event||!state.decision)return '';
  const d=state.decision;
  const changed=Array.isArray(d.changed)?d.changed:[];
  const preserved=Array.isArray(d.preserved)?d.preserved:[];
  const rationale=d.research_loop?.revision_rationale;
  if(!changed.length&&!preserved.length&&!rationale)return '';
  return `<section class="observation-answer" aria-label="입력한 결과 이후 달라진 것">
    <span class="roadmap-label">입력한 결과 이후 · 이 판단이 설명한 것</span>
    <p class="prose small">${esc(roadmapSummary(event.body.text,220))}</p>
    ${rationale?`<p class="prose">${judgmentText(rationale)}</p>`:''}
    <div class="change-grid">
      <div><h4>바꾼 내용 ${changed.length?`· ${esc(changed.length)}`:''}</h4>${
        changed.length?decisionChangeList(changed):'<p class="small muted">바꾼 내용을 기록하지 않았습니다.</p>'}</div>
      <div><h4>유지한 내용 ${preserved.length?`· ${esc(preserved.length)}`:''}</h4>${
        preserved.length?decisionChangeList(preserved):'<p class="small muted">유지한 내용을 기록하지 않았습니다.</p>'}</div>
    </div>
    <p class="limit">입력한 결과 뒤에 나온 판단이라는 기록입니다. 그 결과가 원인이라는 뜻은 아니며,
      바뀌지 않은 가설도 그대로 남아 있습니다. ${button('roadmap-open','정확한 이전·현재 값 비교','data-stage="changes"','link-button small')}</p>
  </section>`;
}
function renderRoadmapResearch(){
  const active=state.jobs.some(j=>['queued','running'].includes(j.status));
  const synthetics=state.events.filter(e=>['message','observation','correction'].includes(e.kind)&&inputProvenance(e).synthetic);
  const model=roadmapModel();
  return `<div class="research-sheet roadmap-workspace">${providerNotice()}${renderContextChanges()}
    ${renderRoadmap()}
    ${roadmapObservationAnswer(model)}
    ${synthetics.length?`<details class="roadmap-assumption" data-detail-key="synthetic-inputs"><summary>가상 목표·입력 ${synthetics.length}건 포함</summary><p class="small muted">실제 측정과 구분합니다. 이후 추가한 공개 원문·계산의 출처는 각 자료에서 확인하세요.</p>${synthetics.map(e=>button('message-source',esc(roadmapSummary(e.body.text,65)),`data-id="${esc(e.body.message_id)}"`,'link-button small')).join('')}</details>`:''}
    ${roadmapRunLine(active)}
    ${renderRoadmapComposer(active)}
  </div>`;
}
// One line for what the system is doing, with the full run record behind it. Before this the
// page carried a fold per state whose summary read like an internal stage name.
function roadmapRunLine(active){
  const jobs=state.jobs??[],last=jobs[jobs.length-1];
  const running=jobs.filter(j=>['queued','running'].includes(j.status)).length;
  const line=active
    ? `실행 중 ${running}건 · ${labels[last?.kind]??'작업'} 진행`
    : last?`마지막 실행 · ${esc(labels[last.kind]??last.kind)} ${esc(jobLabels[last.status]??last.status)}${last.finished?' · '+time(last.finished):''}`:'아직 실행한 작업이 없습니다';
  return `<details class="roadmap-progress" id="roadmap-progress" data-detail-key="workflow-progress"><summary><span class="roadmap-run-line">${line}</span><small>실행 과정 열기</small></summary>${renderWorkflowStatus()}${active?'':renderInputChanges()}</details>`;
}
function renderRoadmapComposer(active){
  // One send button. What the send should do is a choice next to it, not a second and third
  // button of its own; the development-only synthetic switch is gone, and a workspace that
  // already carries synthetic input says so instead. The "explain what you are doing" question
  // is part of intervening here, so it sits in the same panel.
  const modes=[['review',active?'접수하고 이어서 검토':'검토까지 진행'],['record','검토 없이 기록만'],
               ...(state.artifacts.length?[['synthesize','새 조회 없이 현재 자료로 판단']]:[])];
  return `<section class="research-composer roadmap-composer"><div class="roadmap-composer-heading"><h2>이 지점에서 개입하기</h2><span>관측이나 아이디어로 방향을 바꿀 수 있어요.</span></div>
    <label class="input-label" for="message">맡길 질문·새로 확인한 내용</label><textarea id="message" placeholder="예: 이 경로도 함께 비교해 주세요. 또는 새 실험에서 확인한 결과를 알려주세요.">${esc(draft)}</textarea>
    <div class="roadmap-input-tools"><select id="input-kind" aria-label="추가 내용 종류">${[['message','새 질문·아이디어'],['observation','새 관측'],['correction','목표·조건 정정']].map(([v,t])=>`<option value="${v}" ${inputKind===v?'selected':''}>${t}</option>`).join('')}</select>
      <select id="send-mode" aria-label="보낼 방식">${modes.map(([v,t])=>`<option value="${v}" ${sendMode===v?'selected':''}>${t}</option>`).join('')}</select>
      <div class="actions">${button('roadmap-send','보내기',!status.gateway.available&&sendMode!=='record'||busy?'disabled':'','primary small')}</div></div>
    ${syntheticDraft?'<p class="small muted">이 입력은 가상 입력으로 기록됩니다. 실제 측정과 구분해 보존합니다.</p>':''}
    <p class="small muted">${sendMode==='record'?'기록만 저장합니다. 판단은 다시 계산하지 않습니다.':sendMode==='synthesize'?'새 조회 없이 지금까지의 자료로만 판단합니다.':active?'진행 중인 검토는 판단 없이 닫히고(모은 자료·계산은 보존) 새 내용으로 다시 검토합니다.':'필요한 자료·도구를 사용해 다음 판단을 만듭니다.'}</p>
    <details class="roadmap-help" data-detail-key="explain-question"><summary>지금 하는 연구를 설명해 주세요</summary>${renderLiveInteraction()}</details>
  </section>`;
}
// Move focus into the inspector and bring it into view only when it is off screen.
function roadmapRevealInspector(){
  const panel=document.getElementById('roadmap-inspector');
  if(!panel)return;
  panel.focus({preventScroll:true});
  panel.scrollIntoView({block:'nearest'});
}
// A stage filter is applied only when one kind covers the whole stage, so browsing
// the pool never hides options the researcher was told are there.
function roadmapPoolKind(stage,model){
  const kinds=model.nodes.find(n=>n.id===stage)?.kinds??[],counts=state.discovery?.counts??{};
  const present=kinds.filter(k=>(counts[k]??0)>0&&Object.hasOwn(optionKinds,k));
  return present.length===1&&present.reduce((sum,k)=>sum+counts[k],0)===kinds.reduce((sum,k)=>sum+(counts[k]??0),0)?present[0]:'';
}
async function roadmapAction(action,node){
  if(action==='roadmap-stage'){
    const stage=node.dataset.stage;if(!roadmapStageIds().includes(stage))return;
    const opening=roadmapChosen()!==stage;
    roadmapOpener=opening?node.id||null:null;
    roadmapSelections.set(state.id,opening?stage:null);render();
    if(opening)roadmapRevealInspector();else document.getElementById('roadmap-'+stage)?.focus({preventScroll:true});return;
  }
  // Buttons that promise to open a detail always open it, including when it is open.
  if(action==='roadmap-progress-open'){const d=document.getElementById('roadmap-progress');if(d){d.open=true;d.scrollIntoView({block:'nearest'})}return}
  if(action==='roadmap-open'){
    const stage=node.dataset.stage;if(!roadmapStageIds().includes(stage))return;
    roadmapOpener=node.id||null;
    roadmapSelections.set(state.id,stage);render();
    if(node.dataset.detail){const target=document.getElementById(node.dataset.detail);if(target)target.open=true}
    roadmapRevealInspector();return;
  }
  if(action==='roadmap-close'){
    const stage=roadmapChosen(),opener=roadmapOpener;
    roadmapSelections.delete(state.id);roadmapOpener=null;render();
    const back=(opener&&document.getElementById(opener))??document.getElementById('roadmap-'+stage);
    back?.focus({preventScroll:true});return;
  }
  if(action==='roadmap-send'){
    const mode=document.getElementById('send-mode')?.value??sendMode;
    await act(mode==='record'?'save-message':mode==='synthesize'?'synthesize':'plan',node);return;
  }
  if(action==='roadmap-focus-mechanism'){
    mechanismFocus.set(state.id,node.dataset.id);roadmapSelections.set(state.id,'candidates');render();
    document.getElementById('roadmap-candidates')?.scrollIntoView({block:'nearest'});return;
  }
  if(action==='roadmap-focus-clear'){mechanismFocus.delete(state.id);render();return}
  if(action==='roadmap-write'){inputKind=node.dataset.kind??'message';render();document.getElementById('message')?.focus();return}
  if(action==='roadmap-pool'){
    const stage=node.dataset.stage;
    if(optionsOpen&&optionsStage===stage){optionsOpen=false;render();return}
    optionsOpen=true;optionsStage=stage;optionsQuery='';optionsKind=roadmapPoolKind(stage,roadmapModel());optionsOffset=0;optionsPage=null;
    await loadOptions();document.getElementById('roadmap-pool-inline')?.scrollIntoView({block:'nearest'});return;
  }
}

// The send mode is a field, so a real progress refresh must not reset what was chosen.
document.addEventListener('change',event=>{
  if(event.target.id==='send-mode'){sendMode=event.target.value;render()}
});
