// Public rationale and actual work are shown together without conflating their status.
const hypothesisLabels = {proposed:'잠정 가설',inconclusive:'다음 확인 필요',consistent_in_context:'현재 근거와 부합',challenged:'다시 검토할 근거 있음'};
// Recognize only the frozen transport catalog grammar, including abbreviated
// ranges actually returned by the models. The exact original is kept on the
// disclosure button; clinical values and ordinary paper/table IDs are untouched.
const transportPart = 'p[0-9]{4}(?:\\s+l[0-9]+(?:[–-](?:p[0-9]{4}\\s+l)?[0-9]+)?)?';
const transportFile = 's-[0-9a-f]{16}-p[0-9]{4}\\.txt(?:\\s+(?:원문\\s+)?(?:l[0-9]+(?:[·–-][0-9]+)*|[0-9]+행)(?:\\s*[,;]?\\s*(?:b\\[[0-9]+\\s*,\\s*[0-9]+\\)|바이트\\s+[0-9]+[–-][0-9]+))?)?';
const transportLocator = '\\bD[0-9]{4}(?:[–-]D[0-9]{4})?(?:/|\\s+)(?:'+transportFile+'|'+transportPart+'(?:\\s+및\\s+'+transportPart+')*)';
const transportLocatorWhole = new RegExp('^'+transportLocator+'$');
// Display vocabulary for chemical-design prose only. Stored responses, original
// article quotes, compound IDs and submitted researcher inputs remain unchanged.
function researcherWording(value) {
  let text=String(value??'');
  if (/BDBM|CHEMBL|proposed-\d+|화합물|포즈|IC50|설계\s*후보|생성\s*후보|부모\s*구조|부모[–—-]제안|제안\s*\d+/i.test(text)) {
    text=text.replace(/CSV\s*수리\s*(?:뒤|후)\s*생성된\s*/g,'생성된 ');
    text=text.replace(/부모\s*화합물/g,'출발 화합물');
    text=text.replace(/부모와/g,'출발 화합물과').replace(/부모를/g,'출발 화합물을')
      .replace(/부모는/g,'출발 화합물은').replace(/부모가/g,'출발 화합물이')
      .replace(/부모(?=[\s·–—\-의로에대비별보]|$)/g,'출발 화합물')
      .replace(/(?:CSV\s*수리(?:\s*(?:뒤|후))?\s*)?제안\s*(\d+)/g,'설계 후보 $1');
  }
  // BindingDB explicitly identifies a chemical lineage; leave family-parent
  // language and source quotations outside this display helper untouched.
  return text.replace(/\bBindingDB(?:\s+출처)?\s+부모(?=[\s·–—\-의로에대비별보를와가은는,.()]|$)/g,
    'BindingDB에 기록된 출발 화합물');
}
function candidateDisplayName(item) {
  const matched=item?.origin==='generated_structure_proposal'&&String(item.label??'').match(/^proposed-(\d+)$/);
  return matched?`설계 후보 ${matched[1]}`:String(item?.label??'');
}
function judgmentText(value) {
  // Translate an enum value only. Words inside source prose and identifiers such
  // as proposed-1 belong to the scientific record and must remain unchanged.
  const raw=String(value ?? '');
  const text=Object.hasOwn(hypothesisLabels,raw)?hypothesisLabels[raw]+' 상태':raw;
  // Resolve only exact local source IDs. Scientific numbers, source ranges and
  // unknown identifiers remain unchanged; the original response is preserved.
  return text.split(new RegExp('('+transportLocator+'|\\bart_[0-9a-f]{16}\\b)','g')).map(part=>{
    if(transportLocatorWhole.test(part))return renderTransportHandle(part);
    const source=state?.artifacts.find(a=>a.id===part);
    return source?button('source','원자료',`data-id="${esc(part)}" title="${esc(artifactName(part))}" aria-label="원자료 · ${esc(artifactName(part))}"`,'inline-source-link'):esc(part);
  }).join('').replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>');
}
const relationLabels = {supports:'지지 근거',challenges:'반대·제한 근거',context:'해석 맥락'};
let feedbackContext = null;

function decisionChangeList(rows){
 if(!rows?.length)return '<p class="small muted">기록된 항목 없음</p>';
 const render=items=>`<ul class="list">${items.map(v=>`<li>${judgmentText(v)}</li>`).join('')}</ul>`;
 const technical=v=>/record_(?:judgment_context|discovery_review)|\bpriority\b[\s\S]*\bnull\b/.test(v);
 const scientific=rows.filter(v=>!technical(v)),records=rows.filter(technical);
 return (scientific.length?render(scientific.slice(0,2)):'')+
  (scientific.length>2?`<details><summary>나머지 ${scientific.length-2}개 보기</summary>${render(scientific.slice(2))}</details>`:'')+
  (records.length?`<details class="decision-record-notes"><summary>기록 처리 내역 ${records.length}개</summary>${render(records)}</details>`:'');
}
// renderResearchWorkspace was the pre-roadmap workspace screen. Nothing has called it since
// the five-stage view replaced it; its helpers below are still used and stay.

// Stage 5 is the experiment EVIDA recommends, so an external observation is laid out as one:
// what is measured, against what, read how - and what each possible result would change. The
// fields are the model's own words; nothing here fills a missing line or invents a protocol.
const CHECK_KIND = {external_observation: '실험 권고', tool: '자료 조회',
                    unconnected_method: '연결이 필요한 방법', researcher_input: '연구자 입력 필요'};
const REQUEST_FIELDS = [['측정 대상', /^[-•*\s]*측정\s*대상\s*[:：]\s*(.+)$/],
                        ['조건·비교군', /^[-•*\s]*(?:조건[·\s]*비교군|비교군|조건)\s*[:：]\s*(.+)$/],
                        ['판독 지표', /^[-•*\s]*(?:판독\s*지표|판독|지표)\s*[:：]\s*(.+)$/]];

// The one line a researcher acts on. The three fields already say what is measured, against what,
// and read how; a question like "do the candidates lower the target transcript?" restates the
// hypothesis and says none of it. So the headline is built from the fields the model wrote, and
// is empty when it wrote none - never filled in with a guess.
function experimentHeadline(request) {
  const lines = String(request || '').split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const parts = [];
  for (const [, pattern] of REQUEST_FIELDS) {
    const line = lines.find(l => pattern.test(l));
    if (line) parts.push(line.match(pattern)[1].trim().replace(/\s+/g, ' '));
  }
  return parts.join(' · ');
}

// An experiment names the sources it stands on, or says that it names none. Without this the two
// look identical on screen, and a recommendation built on a retrieved paper reads the same as one
// whose cell line and readout came from nowhere.
function experimentGrounding(operation) {
  const sources = (operation && operation.grounded_in) || [];
  if (sources.length) return `<p class="experiment-grounded">근거 자료 ${sources.length}건: `
    + sources.map(id => state?.artifacts?.some(a => a.id === id)
      ? button('source', esc(artifactName(id)), `data-id="${esc(id)}"`, 'link-button small')
      : `<code>${esc(id)}</code> <span class="muted">이 연구에서 자료를 찾을 수 없습니다.</span>`
    ).join(' ') + '</p>';
  return '<p class="experiment-ungrounded">이 권고는 조회한 자료를 지목하지 않았습니다. '
    + '틀렸다는 뜻이 아니라, 시료·비교군·판독 지표가 어느 원자료에서 나왔는지 되짚을 수 '
    + '없다는 뜻입니다.</p>';
}

function experimentRequest(request, operation) {
  const lines = String(request || '').split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const found = [], rest = [];
  for (const line of lines) {
    const hit = REQUEST_FIELDS.map(([name, pattern]) => [name, line.match(pattern)])
      .find(([, match]) => match);
    if (hit) found.push([hit[0], hit[1][1]]);
    else rest.push(line);
  }
  const grounding = experimentGrounding(operation);
  if (!found.length) return `<p class="check-request">${esc(researcherWording(request))}</p>${grounding}`;
  return `<dl class="experiment-fields">${found.map(([name, value]) =>
      `<dt>${esc(name)}</dt><dd>${esc(researcherWording(value))}</dd>`).join('')}</dl>`
    + (rest.length?`<details class="experiment-additional"><summary>추가 조건과 적용 범위</summary>${rest.map(line => `<p class="check-request">${esc(researcherWording(line))}</p>`).join('')}</details>`:'') + grounding;
}

// What each result would change, side by side rather than folded away: an experiment whose
// outcomes both lead to the same judgement is not worth running, and that has to be visible.
function outcomeBranches(check) {
  const outcomes = check.possible_outcomes || [];
  if (outcomes.length < 2) return '';
  // A result whose implication is only prose has nowhere to land when the researcher records it:
  // nothing names the hypothesis it would reject, so the next round cannot pick it up. That is a
  // different thing from an experiment that is wired to what it changes, and it should look
  // different rather than merely reading a little thinner.
  return `<div class="outcome-branches">${outcomes.map((o, i) => {
    const links = renderOutcomeLinks(check, i);
    return `<div class="outcome-branch">
    <span class="branch-mark">결과 ${String.fromCharCode(65 + i)}</span>
    <strong>${esc(researcherWording(o.observation))}</strong>
    <p>${judgmentText(researcherWording(o.implication))}</p>${links || `<p class="outcome-unlinked">가설 연결 필요: 지지·반증 결과에 따라 수정할 가설을 연결하면 후속 판단을 이어갈 수 있습니다.</p>`}</div>`;
  }).join('')}</div>`;
}

function renderCheck(check, current, index) {
  const run = state.research_checks?.find(r=>r.decision_id===state.decision_id&&r.check_id===check.id);
  const job = run && state.jobs.find(j=>j.id===run.job_id);
  const review = run && state.jobs.find(j=>j.id===run.review_job_id);
  const readiness = state.check_readiness?.[check.id];
  const op = check.operation;
  let control;
  if (job) {
    control = `<p class="check-status">확인 작업: ${esc(jobLabels[job.status]??job.status)}${review?` · 결과 해석: ${esc(jobLabels[review.status]??review.status)}`:' · 해석 갱신은 별도 확인'}${job.output_id?sourceLinks([job.output_id]):''}</p>`;
  } else if (op.kind==='tool') {
    const running = state.jobs.some(j=>['running','queued'].includes(j.status));
    control = `${button('run-check',status.gateway.available?'실행하고 결과 검토':'확인 실행',`data-check="${esc(check.id)}" ${!current||busy||running||!readiness?.executable?'disabled':''}`,'primary small')}${!readiness?.executable?`<p class="limit">${esc(readiness?.reason??'실행 가능 여부 확인 중')}</p>`:''}`;
  } else if (op.kind==='unconnected_method') {
    control = `<p class="small muted">연결 검토가 필요한 방법: ${esc(op.method)}</p>${list(op.needed_inputs)}${button('check-feedback','관련 자료·생각 추가',`data-check="${esc(check.id)}"`,'small')}`;
  } else {
    control = `${op.kind==='external_observation'?experimentRequest(op.request, op):`<p class="check-request">${esc(op.request)}</p>`}${button('check-feedback',op.kind==='researcher_input'?'정보 보완하기':'관측 결과 남기기',`data-check="${esc(check.id)}"`,'primary small')}`;
    if(['researcher_input','external_observation'].includes(op.kind)) control += `${button('delegate-check',op.kind==='external_observation'?'기존 자료 먼저 검토':'이 확인을 맡기기',`data-check="${esc(check.id)}" ${!current||busy?'disabled':''}`,'small')}<p class="small muted">${op.kind==='external_observation'?'보존 자료와 이미 끝난 계산을 먼저 확인합니다. 새 실험 결과를 만든다는 뜻은 아닙니다.':'공개 자료나 연결된 도구로 확인할 일이라면 연구를 이어 맡길 수 있습니다.'}</p>`;
  }
  const targets = (check.scope_targets??[]).flatMap(t=>(state.decision?.research_loop?.hypotheses.find(h=>h.id===t.hypothesis_id)?.assessment_scope?.parts??[]).filter(p=>t.part_ids.includes(p.id)).map(p=>p.statement));
  const experiment = op.kind==='external_observation';
  const content = `<h3><span class="check-kind ${esc(op.kind)}">${esc(CHECK_KIND[op.kind]??op.kind)}</span> ${esc(researcherWording(check.question))}</h3><details class="check-reason"><summary>이 확인을 제안한 이유</summary><p class="check-purpose">${esc(researcherWording(check.purpose))}</p>${targets.length?`<div class="small"><strong>확인할 가설</strong>${list(targets.map(researcherWording))}</div>`:''}</details><div class="check-controls">${control}</div>${experiment&&index===0&&check.possible_outcomes.length?`<details class="outcome-details"><summary>결과별 다음 결정 ${check.possible_outcomes.length}가지</summary>${outcomeBranches(check)}</details>`:''}${check.possible_outcomes.length&&!(experiment&&index===0)?`<details class="outcome-details"><summary>결과에 따라 달라질 판단</summary>${check.possible_outcomes.map((o,i)=>`<div class="outcome"><strong>${esc(researcherWording(o.observation))}</strong><p>${judgmentText(researcherWording(o.implication))}</p>${renderOutcomeLinks(check,i)}</div>`).join('')}</details>`:''}`;
  const headline = op.kind==='external_observation' ? researcherWording(experimentHeadline(op.request)) : '';
  return index===0?`<article class="primary-check" data-research-check="${esc(check.id)}">${content}</article>`:`<details class="further-check" data-research-check="${esc(check.id)}"><summary>${esc(headline||check.question)}</summary>${content}</details>`;
}

function renderOutcomeLinks(check, index) {
  const loop = state.decision?.research_loop;
  const labels = {supports:'지지할 수 있음',challenges:'다시 검토할 근거',unresolved:'이 결과만으로 구별되지 않음'};
  return (check.outcome_links??[]).filter(l=>l.outcome_index===index).map(l=>
    l.effects.map(e=>{
      const h=loop?.hypotheses.find(h=>h.id===e.hypothesis_id);
      const parts=(h?.assessment_scope?.parts??[]).filter(p=>e.part_ids.includes(p.id)).map(p=>p.statement);
      const alternatives=(h?.conditional_alternatives??[]).filter(a=>e.alternative_ids.includes(a.id)).map(a=>a.statement);
      return `<div class="outcome-effect"><strong>${esc(labels[e.relation])}</strong>${list([...parts,...alternatives].map(researcherWording))}<p class="small">${judgmentText(researcherWording(e.rationale))}</p></div>`;
    }).join('')+l.followup_check_ids.map(id=>{
      const next=loop?.next_checks.find(c=>c.id===id);
      return next?button('show-check',esc(next.question),`data-check="${esc(id)}"`,'link-button small'):'';
    }).join('')
  ).join('');
}

function renderConditionalAlternatives(h) {
  if(!h.conditional_alternatives?.length)return '';
  const origins={prospective:'결과를 보기 전에 제시한 예상',previously_recorded:'이전에 기록한 예상',reconstructed_after_result:'결과를 보고 구성한 설명'};
  const relations={can_coexist:'동시에 가능',exclusive_under_conditions:'명시한 조건에서 양립하기 어려움',unknown:'설명 간 관계 미확인'};
  return `<section class="conditional-alternatives"><h3>이 결과를 설명할 수 있는 경우</h3><p class="small muted">가능한 설명과 실제 입증은 다릅니다. 같은 관측도 조건에 따라 서로 다른 예상을 구별할 수 있습니다.</p>${h.conditional_alternatives.map(a=>`<details class="outcome-details" data-explanation="${esc(a.id)}"><summary>${esc(a.statement)}</summary><span class="assessment ${esc(a.assessment)}">${esc(hypothesisLabels[a.assessment])}</span><p>${judgmentText(a.rationale)}</p><h4>이 설명이 성립할 조건</h4>${list(a.conditions)}<h4>어떤 결과를 예상하는가</h4><p>${judgmentText(a.observable)}</p><p>${judgmentText(a.prediction)}</p><p class="small muted">${esc(origins[a.prediction_origin])}</p>${renderHypothesisEvidence(a.evidence)}${a.relations.map(r=>`<p class="small"><strong>${esc(relations[r.relation])}</strong> · ${esc(h.conditional_alternatives.find(x=>x.id===r.alternative_id)?.statement??r.alternative_id)}<br>${judgmentText(r.conditions)}</p>`).join('')}${a.unknowns.length?`<h4>아직 구별하지 못한 점</h4>${list(a.unknowns)}`:''}</details>`).join('')}</section>`;
}

function renderHypothesisEvidence(evidence) {
  return evidence.map(e=>`<div class="evidence-relation"><div class="evidence-label">${esc(relationLabels[e.relation])} · ${e.source_type==='message'?'연구자 입력':'보존 자료'}</div><p>${esc(e.detail)}</p><p class="limit">적용 조건: ${esc(e.applicability)}</p>${e.source_type==='artifact'?sourceLinks([e.source_id]):button('message-source','원래 입력 확인',`data-id="${esc(e.source_id)}"`,'link-button small')}</div>`).join('');
}

function renderHypothesisParts(h, canFeedback) {
  if (!h.assessment_scope) return '';
  const scope = h.assessment_scope;
  return `<section class="assessment-parts"><h3>부분별 판단</h3><p class="small muted">각 부분의 근거와 전체 설명의 타당성을 함께 검토합니다.</p>${scope.parts.map(p=>`<article class="assessment-part" data-hypothesis-part="${esc(p.id)}"><h4>${esc(p.statement)}</h4><span class="assessment ${esc(p.assessment)}">${esc(hypothesisLabels[p.assessment]??p.assessment)}</span><p class="hypothesis-expectation"><span>이 부분에서 예상한 관측</span>${judgmentText(p.expected_observation)}</p><p class="prose small">${judgmentText(p.rationale)}</p>${renderHypothesisEvidence(p.evidence)}${canFeedback?button('hypothesis-feedback','이 부분에 관측·정정 연결',`data-hypothesis="${esc(h.id)}" data-part="${esc(p.id)}"`,'small'):''}</article>`).join('')}<h3>전체 판단과의 연결</h3><p class="prose small">${judgmentText(scope.synthesis)}</p></section>`;
}

function renderHypothesis(h, canFeedback) {
  const first = state.events.find(e=>e.kind==='work_framed'&&e.body.hypotheses?.some(x=>x.id===h.id));
  const original = first?.body.hypotheses.find(x=>x.id===h.id);
  const wordingChanged = original && (original.statement!==h.statement || original.expected_observation!==h.expected_observation);
  const comparison = [...state.events].reverse().find(e=>e.kind==='hypothesis_wording_compared'&&e.body.receipt_id===state.decision_id);
  const recordedChange = canFeedback ? comparison?.body.comparisons.find(x=>x.id===h.id&&x.status==='wording_changed') : null;
  const checks = canFeedback ? (state.decision?.research_loop?.next_checks??[]).filter(c=>c.hypothesis_ids.includes(h.id)) : [];
  return `<details class="hypothesis"><summary><span>${esc(h.statement)}</span><span class="assessment ${esc(h.assessment)}">${h.assessment_scope?'전체 판단: ':''}${esc(hypothesisLabels[h.assessment]??h.assessment)}</span></summary>
    <p class="hypothesis-expectation"><span>예상한 관측</span>${judgmentText(h.expected_observation)}</p><p class="prose small">${judgmentText(h.rationale)}</p>
    ${renderHypothesisParts(h, canFeedback)}${renderConditionalAlternatives(h)}${renderJudgmentContext(h)}
    ${checks.length?`<div class="hypothesis-next"><h3>다음 판단을 위해 확인할 것</h3>${checks.map(c=>`<div>${button('show-check',esc(c.question),`data-check="${esc(c.id)}"`,'link-button small')}<p class="small muted">${esc(c.purpose)}</p></div>`).join('')}</div>`:canFeedback&&['proposed','inconclusive'].includes(h.assessment)?'<p class="limit">이 가설에는 다음 확인이 아직 연결되지 않았습니다. 연구를 이어갈 때 필요한 근거와 확인 방법을 함께 검토해야 합니다.</p>':''}
    ${wordingChanged?`<details class="outcome-details"><summary>처음 남긴 가설·예상과 비교</summary><p class="prose small">${esc(original.statement)}</p><p class="prose small">${esc(original.expected_observation)}</p><p class="limit">${esc(first.created)}에 남긴 원문입니다. 현재 표현과 의미가 같은지 검토할 수 있습니다.</p></details>`:''}
    ${recordedChange?`<details class="outcome-details"><summary>이전 판단에서 바뀐 문구</summary>${recordedChange.changed_fields.map(c=>`<h3>${c.field==='statement'?'가설':'예상한 관측'}</h3><p class="prose small">이전: ${esc(c.before)}</p><p class="prose small">현재: ${esc(c.after)}</p>`).join('')}<p class="limit">문구 차이를 자동 기록했습니다. 의미가 같거나 과학적으로 개선됐다는 판정은 아닙니다.</p></details>`:''}
    ${renderHypothesisEvidence(h.evidence)}${evidenceHistoryButton(h,canFeedback)}
    ${h.alternatives.length?`<h3>아직 가능한 다른 설명</h3>${list(h.alternatives)}`:''}
    ${canFeedback?`<div class="detail-actions">${button('hypothesis-feedback','이 가설에 관측·정정 연결',`data-hypothesis="${esc(h.id)}"`,'small')}</div>`:''}
  </details>`;
}

function openResearchFeedback(checkId, hypothesisId, partId=null, reference=null) {
  const loop = (reference?.decision??state.decision)?.research_loop;
  const referenceId = reference?.decision_id??state.decision_id;
  const check = loop?.next_checks.find(c=>c.id===checkId);
  const hypothesis = loop?.hypotheses.find(h=>h.id===hypothesisId);
  const part = hypothesis?.assessment_scope?.parts.find(p=>p.id===partId);
  if (!loop || !referenceId || (!check && !hypothesis)) throw Error('연결할 판단을 다시 확인해 주세요.');
  if (partId && !part) throw Error('연결할 부분 판단을 다시 확인해 주세요.');
  feedbackContext = {decision_id:referenceId,check_id:check?.id??null,hypothesis_ids:check?.hypothesis_ids??[hypothesis.id],comparison:'unclear'};
  if (part) feedbackContext.scope_targets = [{hypothesis_id:hypothesis.id,part_ids:[part.id]}];
  else if (check?.scope_targets) feedbackContext.scope_targets = check.scope_targets;
  const targets = (feedbackContext.scope_targets??[]).flatMap(t=>(loop.hypotheses.find(h=>h.id===t.hypothesis_id)?.assessment_scope?.parts??[]).filter(p=>t.part_ids.includes(p.id)).map(p=>p.statement));
  const kind = check?.operation.kind==='researcher_input'?'message':'observation';
  showDialog('관측과 판단 연결',`<p class="feedback-question">${esc(check?.question??part?.statement??hypothesis.statement)}</p>${targets.length?`<div class="small"><strong>이 관측을 연결할 부분</strong>${list(targets)}</div>`:''}<p class="small muted">이전 예상은 보존합니다. 새 내용이 무엇을 지지하거나 다시 보게 하는지 검토합니다.</p>
    <label class="input-label" for="feedback-text">새로 확인한 내용과 조건</label><textarea id="feedback-text" placeholder="후보·자료가 무엇인지, 어떤 조건에서 무엇을 관측했는지 알려주세요."></textarea>
    <div class="upload-fields"><label>기록 종류<select id="feedback-kind">${[['observation','새 관측'],['message','정보 보완'],['correction','기존 해석 정정']].map(([v,t])=>`<option value="${v}" ${kind===v?'selected':''}>${t}</option>`).join('')}</select></label><label>원래 예상과 비교<select id="feedback-comparison"><option value="unclear">아직 판단하기 어려움</option><option value="consistent">예상과 부합하는 관측</option><option value="different">예상과 다른 관측</option></select></label></div>
    <label class="checkbox"><input type="checkbox" id="feedback-synthetic"> 실제 측정이 아닌 가상 관측·개발 시험</label>
    <p class="limit">원자료 파일은 ‘자료와 도구’에서 추가할 수 있습니다. 짧은 보고만으로 원인이나 효능을 확정하지 않습니다.</p>
    <div class="dialog-actions">${button('save-feedback','기록만 저장','data-review="false"')}${button('save-feedback','반영해 다시 검토',`data-review="true" ${!status.gateway.available?'disabled':''}`,'primary')}</div>`);
}

async function saveResearchFeedback(review) {
  const text = dialog.querySelector('#feedback-text').value.trim();
  if (!text) throw Error('새로 확인한 내용이나 정정할 내용을 적어 주세요.');
  const context = {...feedbackContext,comparison:dialog.querySelector('#feedback-comparison').value};
  await api(`/api/workspaces/${state.id}/commands`,{expected_rev:state.rev,command_id:crypto.randomUUID(),body:{kind:dialog.querySelector('#feedback-kind').value,text,synthetic:dialog.querySelector('#feedback-synthetic').checked,review_requested:review,research_context:context}});
  dialog.close();feedbackContext=null;await refresh();
  if (review) notice('관측과 후속 검토를 함께 접수했습니다.');
  else notice('이전 판단과 연결해 기록했습니다. 현재 가설을 확정한 것은 아닙니다.');
}

function omittedHypotheses() {
  // Follow only the published decision's recorded lineage. Unpublished drafts
  // and unrelated frames must not become reviewed historical hypotheses.
  const comparisons=new Map(state.events.filter(e=>e.kind==='hypothesis_wording_compared').map(e=>[e.body.receipt_id,e.body]));
  const present=new Set((state.decision?.research_loop?.hypotheses??[]).map(h=>h.id));
  const rows=[],seen=new Set(),visited=new Set();
  let cursor=state.decision_id;
  while(cursor&&!visited.has(cursor)) {
    visited.add(cursor);
    const comparison=comparisons.get(cursor),previousId=comparison?.reference?.decision_id;
    if(!previousId)break;
    for(const c of comparison.comparisons) {
      if(c.status==='not_in_current'&&!present.has(c.id)&&!seen.has(c.id)) {
        rows.push({id:c.id,decision_id:previousId});seen.add(c.id);
      }
    }
    cursor=previousId;
  }
  return rows;
}

function renderOmittedHypotheses() {
  const rows=omittedHypotheses();
  if(!rows.length)return '';
  return `<details class="research-details omitted-hypotheses"><summary>이번 판단에 포함되지 않은 이전 가설 ${rows.length}개</summary><p class="small muted">이전 주장·예상과 근거는 보존되어 있습니다. 이번 판단에 없다는 사실만으로 기각되거나 다시 평가된 것은 아닙니다.</p>${rows.map((h,i)=>button('historical-hypothesis',`이전 가설 ${i+1} · 원문 확인·연구에 다시 연결`,`data-hypothesis="${esc(h.id)}" data-decision="${esc(h.decision_id)}"`,'small')).join('')}</details>`;
}

async function openHistoricalHypothesis(decisionId,hypothesisId) {
  const workspaceId=state.id;
  if(!omittedHypotheses().some(h=>h.id===hypothesisId&&h.decision_id===decisionId))throw Error('보존된 이전 판단의 연결을 다시 확인해 주세요.');
  const previous=await api(`/api/workspaces/${encodeURIComponent(workspaceId)}/artifacts/${encodeURIComponent(decisionId)}?download=1`);
  if(state.id!==workspaceId)throw Error('연구가 바뀌었습니다. 현재 연구에서 다시 선택해 주세요.');
  const hypothesis=previous.research_loop?.hypotheses.find(h=>h.id===hypothesisId);
  if(!hypothesis)throw Error('이전 판단에서 해당 가설을 찾지 못했습니다.');
  openResearchFeedback(null,hypothesisId,null,{decision:previous,decision_id:decisionId});
  const original=document.createElement('section');original.className='notice-inline';
  const heading=document.createElement('strong');heading.textContent='이전 판단의 가설 · 현재 평가로 승계되지 않았습니다';
  const expectation=document.createElement('p');expectation.className='prose small';expectation.textContent='당시 예상: '+hypothesis.expected_observation;
  original.append(heading,expectation);dialog.querySelector('.feedback-question').after(original);
  dialog.querySelector('#feedback-kind').value='message';
  dialog.querySelector('#feedback-text').value=`이전 판단에 있던 다음 가설을 현재 목표에서 다시 검토해 주세요: ${hypothesis.statement}\n당시 예상: ${hypothesis.expected_observation}\n원래 조건·계산은 보존하고, 이번 목표에서도 필요한지와 기존 근거의 적용 범위를 설명해 주세요. 이는 검토 요청이며 새 관측이 아닙니다.`;
  dialog.querySelector('#feedback-synthetic').checked=state.events.filter(e=>['message','observation','correction'].includes(e.kind)).at(-1)?.body.origin==='synthetic';
  dialog.querySelector('[data-action="save-feedback"][data-review="true"]').textContent='이 가설 다시 검토';
}

function openCheckDelegation(checkId) {
  const check=state.decision?.research_loop?.next_checks.find(c=>c.id===checkId);
  if(!check || state.decision_rev!==state.rev) throw Error('현재 입력을 반영한 판단의 다음 확인을 선택해 주세요.');
  openResearchFeedback(checkId,null);
  dialog.querySelector('#feedback-text').value=`다음 확인을 이어 진행해 주세요: ${check.question}\n목적: ${check.purpose}\n제안된 확인 내용: ${check.operation.request}\n공개 자료와 연결된 도구로 가능한 확인을 먼저 수행하고, 연구자의 선택이나 새로운 측정이 꼭 필요한 부분만 구분해 알려주세요. 이는 후속 연구 요청이며 새로운 관측을 제공하는 것은 아닙니다.`;
  if(check.operation.kind==='external_observation') dialog.querySelector('#feedback-text').value=`다음 확인에 대응하는 기존 자료를 먼저 검토해 주세요: ${check.question}\n목적: ${check.purpose}\n필요한 관측·조건: ${check.operation.request}\n보존한 원자료와 완료 계산에서 대응하는 조건·결과가 있는지 확인하고, 같은 입력의 완료 계산은 재사용해 주세요. 이 자료에 없다는 사실과 실제 연구 환경에 없다는 판단을 구별해 주세요. 새 관측은 제공하지 않았습니다. 이 확인과 병행해 가능한 조회·계산이 있으면 그 역할과 아직 판단할 수 없는 부분을 구분해 이어가 주세요.`;
  dialog.querySelector('#feedback-kind').value='message';
  dialog.querySelector('#feedback-comparison').value='unclear';
  const latest=state.events.filter(e=>['message','observation','correction'].includes(e.kind)).at(-1);
  dialog.querySelector('#feedback-synthetic').checked=latest?.body.origin==='synthetic';
  dialog.querySelector('label[for="feedback-text"]').textContent='맡길 확인 내용 · 필요하면 수정하세요';
  const note=document.createElement('p');note.className='notice-inline';note.textContent='후속 연구 요청입니다. 새 관측으로 저장되지 않으며, 아래에서 요청을 확인한 뒤 실제 검토를 시작합니다.';
  dialog.querySelector('#feedback-text').before(note);
  dialog.querySelector('[data-action="save-feedback"][data-review="true"]').textContent='이 확인 이어서 검토';
}

function articleView(result) {
  if(result.view_kind==='article_references')return articleReferencesView(result);
  const span=value=>/^\d+$/.test(String(value))&&Number(value)>0&&Number(value)<=1000?Number(value):1;
  const inline=parts=>(parts??[]).map(p=>{if(p.type==='text')return esc(p.text??'');if(p.type==='break')return '<br>';const tags={sub:'sub',sup:'sup',bold:'strong',italic:'em',monospace:'code'},tag=Object.hasOwn(tags,p.type)?tags[p.type]:null;const body=inline(p.children);return tag?`<${tag}>${body}</${tag}>`:body;}).join('');
  const table=r=>r.table_rows?.length?`<details class="primary-table" data-xml-id="${esc(r.xml_id??'')}"><summary>원문 표${r.xml_id?' · '+esc(r.xml_id):''}의 행·열과 각주 보기</summary><p class="limit">원문 XML의 셀 순서와 병합을 보존했습니다. 단위·대조군·각주를 함께 확인하세요.</p><div class="table-scroll"><table><tbody>${r.table_rows.map(row=>`<tr>${row.map(c=>{const tag=c.kind==='th'?'th':'td';return `<${tag} rowspan="${span(c.rowspan)}" colspan="${span(c.colspan)}">${c.inline_parts?inline(c.inline_parts):esc(c.text)}</${tag}>`}).join('')}</tr>`).join('')}</tbody></table></div>${(r.table_footnotes??[]).map(t=>`<p class="small">${esc(t)}</p>`).join('')}</details>`:'';
  return `<h3>${esc(result.title??result.pmc_id??'공개 원문')}</h3>${button('article-references','참고문헌에서 원전 찾기','data-reference-ids="[]"','small')}<p class="limit">${esc((result.permissions??[]).join(' · '))}</p>
    ${result.section_navigation?.length?`<details class="article-navigation"><summary>원문 구역으로 이동 · 방법·결과·표·그림</summary><div class="detail-actions">${result.section_navigation.map(s=>button('article-section',esc(s.section==='Figures and tables'?'표·그림':s.section)+' · '+s.blocks,`data-offset="${s.offset}"`,'small')).join('')}</div><p class="limit">원문 순서의 위치 목록입니다. 추천이나 읽기 완료 표시가 아닙니다.</p></details>`:''}
    ${result.access_attempts?.length?`<details class="article-access"><summary>원문 접근 경로와 실제 결과</summary>${result.access_attempts.map(a=>`<p class="small">${esc(a.status==='succeeded'?'원문 수신':a.status==='partial'?'부분 수신':'접근 실패')} · ${esc(a.url)}${a.http_status?` · HTTP ${esc(a.http_status)}`:''}</p>`).join('')}</details>`:''}
    ${articleFiguresView(result, state.id, detail?.artifact_id)}
    ${result.rows.map(r=>`<article class="article-block"><div class="small muted">${esc(r.section)}</div>${r.embedded_tables?.length?`<details><summary>표를 포함한 원래 문단 텍스트</summary><p class="prose small">${esc(r.text)}</p></details><p class="limit">아래 표는 같은 문단에 포함된 원문입니다. 별도의 관측으로 중복 계산하지 않습니다.</p>`:`<p class="prose small">${esc(r.text)}</p>`}${articleCitationButtons(r)}${table(r)}${(r.embedded_tables??[]).map(t=>table(t)).join('')}${r.requires_original_review?'<p class="limit">표·그림・수식 또는 보충자료가 포함됩니다. 원문에서 의미를 확인하세요.</p>':''}<a class="small" href="${esc(safeUrl(r.source_url))}" target="_blank" rel="noopener noreferrer">원문 위치 확인 ↗</a></article>`).join('')}
    <div class="pagination"><span>문단 ${result.rows.length?result.offset+1:0}–${result.offset+result.rows.length} / ${result.total_rows}</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div>`;
}

function repositoryDocumentView(result) {
  const license = result.permissions?.id ?? '레코드에 이용 조건이 표시되지 않았습니다.';
  if (!result.filename) return `<h3>${esc(result.title)}</h3><p class="limit">${esc(license)}</p>
    ${result.rows.map(r=>`<article class="article-block"><strong>${esc(r.filename)}</strong><p class="small">${number(r.bytes)} bytes</p>
    <a href="https://zenodo.org/records/${encodeURIComponent(result.record_id)}" target="_blank" rel="noopener noreferrer">원본 저장소 확인 ↗</a></article>`).join('')}`;
  if (['pdf','xlsx'].includes(result.document_format)) {
    const original=`/api/workspaces/${encodeURIComponent(state.id)}/artifacts/${encodeURIComponent(selected)}?original=1`;
    const body=result.rows.map(r=>r.kind==='pdf_page'
      ? `<article class="article-block"><h3>원문 ${esc(r.page_number)}쪽</h3><p class="limit">문자층을 읽은 결과입니다. 그림·패널과 후보의 대응은 원본에서 확인하세요.</p><pre class="raw">${esc(r.text || '읽을 수 있는 문자층이 없습니다. 원본을 확인해 주세요.')}</pre><a href="${original}#page=${r.page_number}" target="_blank" rel="noopener noreferrer">보존한 원본의 이 페이지 열기 ↗</a></article>`
      : `<article class="article-block"><h3>${esc(r.sheet)} · ${esc(r.row_number)}행${r.hidden_row?' · 숨김 행':''}</h3><div class="table-scroll"><table><thead><tr><th>셀</th><th>원값</th><th>자료형</th><th>수식의 저장된 값</th></tr></thead><tbody>${r.cells.map(c=>`<tr><td>${esc(c.coordinate)}</td><td>${c.value===null?'빈 셀':esc(typeof c.value==='object'?JSON.stringify(c.value):c.value)}</td><td>${esc(c.data_type)}</td><td>${'cached_value' in c ? (c.cached_value===null?'미제공':esc(c.cached_value)):'—'}</td></tr>`).join('')}</tbody></table></div></article>`).join('');
    return `<h3>${esc(result.filename)}</h3><p class="limit">${esc(license)} · 원자료와 해석을 구분합니다.</p><a href="${original}" target="_blank" rel="noopener noreferrer">보존한 원본 파일 열기 ↗</a>${result.summary.sheets?`<details class="meta-details"><summary>시트·병합·숨김 정보</summary>${json(result.summary.sheets)}</details>`:''}${body}<div class="pagination"><span>${result.document_format==='pdf'?'페이지':'자료 행'} ${result.rows.length?result.offset+1:0}–${result.offset+result.rows.length} / ${result.total_rows}</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div>`;
  }
  return articleView({...result, title:result.filename, permissions:[license],
    rows:result.rows.map(r=>({...r, section:`본문 위치 ${r.original_block_index+1}`,
      text:r.table_cells ? r.table_cells.map(row=>row.join(' | ')).join('\n') : r.text || '이 위치에는 원본 그림 또는 수식이 있습니다.'}))});
}

function renderRnaSensitivity(result) {
  const headers = ['UTR 선택','baseMean 최소값','seed','일치군 / 배경군','KS 통계량','Holm p · 16개 비교'];
  return `<p class="limit">동일한 처리표·guide의 참조 선택과 발현량 기준 비교입니다. 길이·발현량의 영향이 제거됐다는 검증은 아닙니다.</p><div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(r.policy==='longest'?'가장 긴 UTR':r.policy==='shortest'?'가장 짧은 적격 UTR':r.policy)}</td><td>${number(r.baseMean_min)}</td><td>${esc(r.seed)}</td><td>${number(r.target_genes)} / ${number(r.background_genes)}</td><td>${number(r.statistic)}</td><td>${number(r.pvalue_holm_16_sensitivity_comparisons)}</td></tr>`).join('')}</tbody></table></div>`;
}

const contextLabels={organism:'종',target_construct_variant:'표적·구성체·변이',transcript_version:'전사체·버전',tissue_cell:'조직·세포',intervention_chemistry_formulation:'개입·화학수식·제형',dose_route:'용량·경로',time:'시점',assay_buffer:'측정법·완충액',comparator:'비교군'};
const stageLabels={mechanism:'질환 기전',target_intervention:'표적 개입',approach:'치료 접근',candidate:'후보·조건'};
function contextFacts(c){return `<dl class="context-facts">${Object.entries(contextLabels).map(([k,label])=>`<div><dt>${label}</dt><dd>${esc(c[k]||'미확인')}</dd></div>`).join('')}</dl>${c.unknowns.length?`<p class="limit">미확인: ${esc(c.unknowns.join(' · '))}</p>`:''}${sourceLinks(c.source_ids.filter(id=>state.artifacts.some(a=>a.id===id)))}`}
function contextObservationView(x,o){
 const c=x.contexts.find(c=>c.id===o.context_id);
 return `<details class="observation-context"><summary>${esc(c?.time||o.context_id)} · ${esc(c?.comparator||'비교 조건 미확인')}${o.part_id?' · 부분 '+esc(o.part_id):''}</summary>${c?contextFacts(c):'<p>원 조건 확인이 필요합니다.</p>'}<dl class="context-facts"><div><dt>측정 신뢰</dt><dd>${esc(o.measurement_quality)}</dd></div><div><dt>처리 적절성</dt><dd>${esc(o.processing_validity)}</dd></div><div><dt>조건 적용 가능성</dt><dd>${esc(o.applicability)}</dd></div><div><dt>설명의 충분성</dt><dd>${esc(o.explanatory_adequacy)}</dd></div><div><dt>다음 확인</dt><dd>${esc(o.next_check)}</dd></div></dl>${sourceLinks(state.artifacts.some(a=>a.id===o.source_id)?[o.source_id]:[])}</details>`;
}
function renderJudgmentContext(h){
 const v=state.judgment_context;if(!v)return '';
 const x=v.context,bs=x.bindings.filter(b=>b.hypothesis_id===h.id);if(!bs.length)return '';
 const linked=Boolean(v.published_decision_id)&&v.published_decision_id===state.decision_id;
 const bindings=bs.map(b=>{
  const c=x.contexts.find(c=>c.id===b.context_id),assumptions=x.assumptions.filter(a=>b.assumption_ids.includes(a.id));
  return `<article class="context-binding"><div class="section-mark">${esc(stageLabels[b.stage])}${b.part_id?' · 부분 '+esc(b.part_id):''} · ${esc(c?.time||b.context_id)}</div><p><strong>${esc(b.prediction.observable)}</strong> · ${esc(b.prediction.direction_or_range)} ${esc(b.prediction.unit)}</p><p class="small">시점 ${esc(b.prediction.time||'미확인')} · 비교 ${esc(b.prediction.comparator||'미확인')} · ${b.prediction.origin==='reconstructed_after_result'?'결과를 본 뒤 재구성한 예상':b.prediction.origin==='prospective'?'결과 확인 전 예상':'이전에 기록된 예상'}</p><details><summary>이 적용 조건 확인·정정</summary>${c?contextFacts(c):''}${linked&&c?button('context-edit','이 조건 정정',`data-context="${esc(c.id)}" data-hypothesis="${esc(h.id)}" data-part="${esc(b.part_id)}"`,'small'):''}</details>${assumptions.length?`<h4>설명을 위해 필요한 가정</h4>${assumptions.map(a=>`<p class="small"><strong>${esc(a.statement)}</strong> · ${esc({proposed:'잠정',checked_in_context:'해당 조건에서 확인',challenged:'재검토 근거 있음',unknown:'미확인'}[a.status])}</p>`).join('')}`:''}</article>`;
 }).join('');
 const observations=x.observation_reviews.filter(o=>o.hypothesis_id===h.id);
 return `<section class="judgment-context"><h3>이 가설의 조건과 다시 볼 가정</h3><p class="limit">${linked?'현재 표시한 판단에 연결된 설명':'별도 보존된 문맥 초안 · 현재 판단과 연결 확인 필요'} · 설명 기록이며 과학적 검증 상태와 구분합니다.</p>${bindings}${observations.length?`<h4>조건별 관측 연결 ${observations.length}개</h4><p class="small muted">반대 결과와 다른 조건의 관측도 함께 보존했습니다. 연결 개수는 독립 실험 횟수가 아닙니다.</p>${observations.map(o=>contextObservationView(x,o)).join('')}`:''}</section>`;
}
function renderContextChanges(){const v=state.judgment_context;if(!v?.pending_changes.length)return '';return `<section class="panel context-change-review"><h3>정정에 따라 다시 검토할 부분</h3>${v.pending_changes.map(c=>`<p>${esc(c.text)}</p><p class="small">직접 연결: ${esc(c.impact.direct_hypotheses.join(', '))} · 상위 검토: ${esc(c.impact.upstream_review.join(', ')||'명시된 경로 없음')}</p>${c.impact.review_paths.map(p=>`<p class="small">${esc(p.reason)}</p>`).join('')}`).join('')}<p class="limit">명시된 의존 경로를 따라 재검토 대상을 표시했습니다. 관측 삭제·가설 폐기·계산 재실행을 자동 결정하지 않습니다.</p></section>`}
let conditionEdit=null;
function openConditionEdit(node){const v=state.judgment_context,c=v.context.contexts.find(c=>c.id===node.dataset.context);conditionEdit={context_artifact_id:v.artifact_id,context_id:c.id,hypothesis_id:node.dataset.hypothesis,part_id:node.dataset.part??'',decision_id:v.published_decision_id};showDialog('조건을 정정하고 영향 확인',`<p class="small">원 조건과 계산은 보존됩니다. 정정은 새 입력으로 저장하고, 연결된 가정의 검토를 요청합니다.</p><label>정정할 조건<select id="condition-field">${Object.entries(contextLabels).map(([k,l])=>`<option value="${k}">${l}</option>`).join('')}</select></label><p id="condition-before" class="notice-inline">현재: ${esc(c.organism||'미확인')}</p><label>수정할 내용<input id="condition-after"></label><label>정정 근거·이유<textarea id="condition-reason"></textarea></label><label class="check-line"><input type="checkbox" id="condition-synthetic">시연 가정·가상 조건 (실제 관측 아님)</label><div class="dialog-actions">${button('context-save','정정 저장·영향 보기','data-review="false"')}${button('context-save','정정하고 판단 갱신',`data-review="true" ${!status.gateway.available?'disabled':''}`,'primary')}</div>`)}
document.addEventListener('change',e=>{if(e.target.id==='condition-field'&&conditionEdit){const c=state.judgment_context.context.contexts.find(c=>c.id===conditionEdit.context_id);document.querySelector('#condition-before').textContent='현재: '+(c[e.target.value]||'미확인')}});
async function saveConditionEdit(review){const c=state.judgment_context.context.contexts.find(c=>c.id===conditionEdit.context_id),field=dialog.querySelector('#condition-field').value,after=dialog.querySelector('#condition-after').value.trim(),reason=dialog.querySelector('#condition-reason').value.trim();if(!after||!reason)throw Error('새 조건과 정정 이유를 입력해 주세요.');const rc={decision_id:conditionEdit.decision_id,check_id:null,hypothesis_ids:[conditionEdit.hypothesis_id],comparison:'unclear'};if(conditionEdit.part_id)rc.scope_targets=[{hypothesis_id:conditionEdit.hypothesis_id,part_ids:[conditionEdit.part_id]}];await api(`/api/workspaces/${state.id}/commands`,{expected_rev:state.rev,command_id:crypto.randomUUID(),body:{kind:'correction',text:`${contextLabels[field]} 조건 정정: ${c[field]||'미확인'} → ${after}. 근거: ${reason}`,synthetic:dialog.querySelector('#condition-synthetic').checked,review_requested:review,research_context:rc,context_update:{context_artifact_id:conditionEdit.context_artifact_id,context_id:c.id,field,before:c[field],after,reason}}});dialog.close();conditionEdit=null;await refresh();if(review)notice('조건 정정과 후속 검토를 접수했습니다.');else notice('원 조건을 보존하고 정정을 저장했습니다. 연결된 가정의 검토 범위를 확인하세요.')}
