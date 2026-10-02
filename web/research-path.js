// Read the stored relations, recommendations and comparison as separate records.
// No narrative parsing, inferred biological edge, new rank, request or mutation in render.
const PATH_MATCH_LABEL = {target_disease:'목표 질환의 근거', related_disease:'관련 질환의 근거',
  animal_model:'동물 모형의 근거', in_vitro:'세포·시험관의 근거', none:'경로 수준의 근거'};
const PATH_STATUS_LABEL = {recommended:'이번 검토 경로', alternative:'대안',
  needs_evidence:'근거 확인', deferred:'현재 보류', unreviewed:'검토 전'};
let pathPanelRequest = 0;

function pathText(value) { return typeof value === 'string' ? value : ''; }
function pathWording(value) {
  return typeof researcherWording === 'function' ? researcherWording(pathText(value)) : pathText(value);
}
function pathWorkspaceKey() {
  return typeof state !== 'undefined' && state ? `${state.id}@${state.event_cursor}@${state.rev}` : null;
}
function pathRanking() {
  if (typeof mechanismRanking === 'undefined' || !mechanismRanking) return null;
  if (typeof mechanismRankingKey === 'function' &&
      (typeof mechanismRankingFor === 'undefined' || mechanismRankingFor !== mechanismRankingKey())) return null;
  return mechanismRanking;
}
function pathMechanisms() {
  const ranking = pathRanking();
  const options = new Map();
  for (const option of state?.discovery?.mechanisms_and_approaches || []) {
    if (['mechanism','approach'].includes(option.kind)) options.set(option.option_id, option);
  }
  for (const row of ranking?.rows || []) {
    if (!options.has(row.option_id)) options.set(row.option_id, {
      option_id:row.option_id, label:row.label, kind:row.kind,
      assessment:row, sources:row.sources || []});
  }
  return [...options.values()].map(option => ({...option,
    ranking:(ranking?.rows || []).find(row => row.option_id === option.option_id) || null}));
}
function pathCandidates() {
  return typeof candidateOptions === 'function' ? candidateOptions() : [];
}
function pathLinkedCandidates(id) {
  return pathCandidates().filter(option => option.assessment?.targets_mechanism?.option_id === id);
}
function pathCurrent(assessment) {
  if (!assessment) return false;
  return Number.isInteger(assessment.based_rev)
    ? assessment.based_rev === state.rev : assessment.current_conditions === true;
}
function pathRevision(assessment) {
  if (!assessment) return '검토 기록 없음';
  if (Number.isInteger(assessment.based_rev)) return `연구 기록 ${assessment.based_rev}${pathCurrent(assessment)?' · 현재':' · 이전 조건'}`;
  return assessment.current_conditions === true ? '현재 입력의 검토' : '검토 입력 확인 필요';
}
function pathEvidenceIds(assessment) {
  const a = assessment || {};
  return [...new Set([...(a.support_source_ids || []), ...(a.challenge_source_ids || []),
    ...(a.basis?.clauses || []).map(clause => clause.anchor?.artifact_id)].filter(id => typeof id === 'string' && id))];
}
function pathRelationLabel(option) {
  const a = option.assessment || {}, clauses = a.basis?.clauses || [];
  const labels = [...new Set(clauses.map(c => PATH_MATCH_LABEL[c.disease_match]).filter(Boolean))];
  if (labels.length) return labels.join(' · ');
  if ((a.support_source_ids || []).length || (a.challenge_source_ids || []).length) return '평가에 인용한 근거';
  return '연결 근거 확인 필요';
}
function pathCandidateName(option) {
  return typeof candidateDisplayName === 'function' ? candidateDisplayName(option) : option.label || option.option_id;
}
function pathCandidateMeaning(option) {
  if (option.origin === 'generated_structure_proposal') return '계산으로 제안한 구조 · 생성 단계 활성 미측정';
  if (option.kind === 'rna_candidate' || option.kind === 'rna') return 'RNA 후보 · 서열·조건별 근거 확인';
  if (option.origin === 'public_activity_record') return '공개 활성 기록에서 회수 · 시험 조건 확인';
  if (option.origin === 'source_anchored_candidate_assertion' || option.kind === 'source_candidate') return '원문에서 회수한 후보·참조';
  return '기록된 후보 연결 · 기능 근거 확인';
}
function pathButton(action, label, id, extra='') {
  return `<button type="button" class="path-link-button" data-action="${esc(action)}" data-id="${esc(id)}" ${extra}>${esc(label)}</button>`;
}

function pathScope() {
  const intents = Array.isArray(state.intent) ? state.intent.filter(x => x && typeof x.text === 'string') : [];
  const primary = intents.find(x => x.origin === 'researcher') || intents[0];
  const unknowns = intents.filter(x => x.origin === 'unknown');
  return `<header class="research-path-scope">
    <p class="path-eyebrow">연구·평가 범위 · 연구 기록 ${esc(state.rev)}</p>
    <h3>${esc(state.title || '현재 연구')}</h3>
    ${primary?`<p class="path-goal"><span>${esc(primary.label || '기록한 목표')}</span>${esc(pathWording(primary.text))}</p>`:
      '<p class="path-unresolved">질환과 목표의 구조화된 기록을 확인하는 단계입니다.</p>'}
    ${unknowns.map(x => `<p class="path-unresolved"><strong>${esc(x.label || '확인할 조건')}</strong> ${esc(x.text)}</p>`).join('')}
    ${intents.length>1?`<details class="path-scope-details"><summary>목표·범위 원문 ${intents.length}개</summary><dl>${intents.map(x =>
      `<div><dt>${esc(x.label || '기록')} · ${esc(x.origin==='researcher'?'연구자 입력':x.origin==='unknown'?'조건 확인 필요':'구조화된 해석')}</dt><dd>${esc(x.text)}</dd></div>`).join('')}</dl></details>`:''}
  </header>`;
}

function pathComparisonSummary(ranking) {
  if (!ranking) return {title:'근거 비교를 불러오는 중', detail:'기전별 관계와 기록된 추천은 아래에서 확인할 수 있습니다.'};
  if (ranking.status !== 'computed') return {title:'비교 기준 확인 단계',
    detail:ranking.emptiness?.meaning || ranking.meaning || '현재 저장된 평가 축을 확인합니다.'};
  const rows = ranking.rows || [], byId = new Map(rows.map(r => [r.option_id,r]));
  const leader = byId.get(ranking.single_leader);
  const frontier = (ranking.frontier || []).map(id => byId.get(id)).filter(Boolean);
  const eligible = rows.filter(row => row.comparable !== false).length;
  let title;
  if (leader) title = `이 비교에서 앞선 경로: ${leader.label || leader.option_id}`;
  else if (ranking.single_leader_withheld === 'only_one_option_graded') title = '비교할 다른 기전·접근 확인 필요';
  else if (!frontier.length) title = '기전 간 비교 조건 확인 중';
  else if (frontier.length > 1) title = `앞선 기전·접근 ${frontier.length}개 · 서로 순서 미정`;
  else title = '기전·접근의 공통 1순위 미확정';
  const axes = (ranking.comparison_axes || []).map(axis => ({disease_match:'적용성',evidence_grade:'타당성',
    clinical_precedent:'임상 선례',actionability:'개입 가능성'})[axis] || axis).join('·');
  const versions = [...new Set(rows.map(row => row.based_rev).filter(Number.isInteger))];
  const detail = `비교 집합: 기전·접근 ${rows.length}개, 비교 조건을 갖춘 항목 ${eligible}개${axes?' · 기준: '+axes:''}`
    + ` · ${versions.length?'평가 연구 기록 '+versions.join(', '):'평가 입력 미기록'}`;
  return {title,detail};
}

function pathMeanings(options) {
  const current = options.filter(x => pathCurrent(x.assessment) && x.assessment.status === 'recommended');
  const selected = state.discovery?.selected;
  const selection = selected && selected.state_rev === state.rev ? selected : null;
  const comparison = pathComparisonSummary(pathRanking());
  const generated = pathCandidates().filter(x => x.origin === 'generated_structure_proposal').length;
  return `<dl class="path-meanings" aria-label="검토 경로·근거 비교·후보 상태의 구분">
    <div><dt>이번에 검토할 경로</dt><dd>${current.length?current.map(x=>esc(pathWording(x.label))).join(' · '):'현재 입력의 추천 경로 기록 없음'}
      ${selection?`<span>연구자 선택: ${esc(selection.label)}</span>`:''}<small>연구 기록 ${esc(state.rev)}의 추천·선택 기록</small></dd></div>
    <div><dt>기전 근거의 비교</dt><dd>${esc(comparison.title)}<small>${esc(comparison.detail)}</small></dd></div>
    <div><dt>후보의 측정 상태</dt><dd>${generated?`설계 구조 ${generated}건 · 생성 단계 활성 미측정`:'후보별 원문·계산·기능 관측을 구분'}
      <small>기전의 근거와 각 후보의 기능 확인은 별도 기록입니다.</small></dd></div>
  </dl>`;
}

function pathFigurePreview(option) {
  const figure = option.ranking?.figures?.[0];
  if (!figure || !figure.artifact_id || !figure.file) return '';
  const url = `/api/workspaces/${encodeURIComponent(state.id)}/artifacts/${encodeURIComponent(figure.artifact_id)}?figure=${encodeURIComponent(figure.file)}`;
  return `<button type="button" class="path-figure-preview" data-action="path-evidence" data-id="${esc(option.option_id)}">
    <img src="${esc(deploymentURL(url))}" alt="${esc((figure.caption || figure.file)+' · 근거 논문의 그림')}" loading="lazy">
    <span>논문 그림·캡션 보기</span></button>`;
}
function pathRow(option) {
  const a = option.assessment, candidates = pathLinkedCandidates(option.option_id);
  const sourceCount = pathEvidenceIds(a).length;
  return `<article class="research-path-row" data-path-option="${esc(option.option_id)}">
    <div class="path-origin"><span class="path-field">연구 질문과의 관계</span>
      <strong>${esc(pathRelationLabel(option))}</strong><span class="path-source-count">연결된 원자료 ${sourceCount}개</span>
      ${pathButton('path-evidence','왜 이 경로를 검토하나요?',option.option_id)}${pathFigurePreview(option)}</div>
    <div class="path-mechanism"><span class="path-field">${uiPathKind(option)}</span>
      <h4>${esc(pathWording(option.label || option.option_id))}</h4>
      <span class="path-state${a?.status==='deferred'?' is-deferred':''}">${esc(PATH_STATUS_LABEL[a?.status || 'unreviewed'] || '검토 기록')}</span>
      <span class="path-version${a&&!pathCurrent(a)?' is-earlier':''}">${esc(pathRevision(a))}</span>
      ${a?.priority!=null?`<p class="path-recorded-order">기록한 검토 순서: ${esc(a.comparison_group || '비교 집합 미기록')} · ${esc(a.priority)}</p>`:''}
      ${pathButton('path-evidence','주장·근거·다음 확인',option.option_id)}</div>
    <div class="path-candidates"><span class="path-field">이 경로를 겨냥한 후보</span>
      ${candidates.length?`<ul>${candidates.map(candidate=>`<li><strong>${esc(pathCandidateName(candidate))}</strong>
        <span class="path-candidate-relation">${esc(pathCandidateMeaning(candidate))}</span>
        ${candidate.assessment?.current_conditions===false?'<span class="path-version is-earlier">이전 조건의 후보 검토</span>':''}
        ${pathButton('discovery-detail','후보·출발 화합물 보기',candidate.option_id)}</li>`).join('')}</ul>`:
        '<p class="path-unresolved">이 경로를 겨냥한다고 기록한 후보를 확인할 단계입니다.</p>'}
    </div></article>`;
}

const pathViewSelections=new Map();
function renderResearchPath() {
  if (typeof state === 'undefined' || !state) return '';
  const options = pathMechanisms();
  const current = options.filter(x => pathCurrent(x.assessment));
  const other = options.filter(x => !pathCurrent(x.assessment));
  const shown = current.length ? current : other;
  const selected=shown.find(x=>x.option_id===pathViewSelections.get(state.id))??shown[0];
  const remaining=shown.filter(x=>x!==selected);
  return `<section class="research-path" aria-label="질환·목표와 기전·후보의 관계">
    ${pathScope()}
    <div class="path-list-heading"><h3>${current.length?'현재 입력에서 검토한 연결':'보존한 검토 경로'}</h3>
      <p>질환·목표의 근거와 후보의 기능 확인을 각각 살펴보세요.</p></div>
    ${shown.length?`<p class="small muted path-view-order">기전과 설계·시험 접근을 구분해 살펴보세요. 기록된 비교 범위와 순서는 각 항목에 표시됩니다.</p><nav class="path-view-choices" aria-label="기전과 설계·시험 접근 선택">${shown.map(x=>pathButton('path-select',`${uiPathKind(x)} · ${pathWording(x.label||x.option_id)}`,x.option_id,`aria-pressed="${x===selected}" title="${esc(pathWording(x.label||x.option_id))}"`)).join('')}</nav><div class="path-selected-connection">${pathRow(selected)}<div class="path-all-options">${pathButton('discovery-choose',selected.kind==='approach'?'이 접근 검토하기':'이 기전 검토하기',selected.option_id)}${!status.gateway.available?`<span role="status">${esc(status.gateway.message??'모델 연결 확인 필요')} · 선택 이유를 검토할 수 있으며, 새 검토는 연결 후 시작할 수 있습니다.</span>`:''}</div></div>${remaining.length?`<details class="path-other-connections" data-detail-key="path-other-connections"><summary>함께 검토한 다른 연결 ${remaining.length}개</summary>${remaining.map(pathRow).join('')}</details>`:''}`:'<p class="path-unresolved">저장된 기전·접근 관계가 생기면 이곳에서 후보까지 이어서 확인할 수 있습니다.</p>'}
    <details class="path-scope-details" data-detail-key="path-meanings"><summary>추천·비교 범위와 기록의 의미</summary>${pathMeanings(options)}</details>
    ${current.length&&other.length?`<details class="path-earlier"><summary>이전 조건·검토 전 경로 ${other.length}개</summary>${other.map(pathRow).join('')}</details>`:''}
    <div class="path-all-options">${pathButton('discovery-toggle',optionsOpen?'전체 목록 접기':'전체 기전·후보 목록 보기','',`aria-expanded="${optionsOpen}"`)}
      <span>현재 표시와 별도로 발견한 선택지를 모두 보존합니다.</span></div>
    ${optionsOpen?renderOptionBrowser():''}
  </section>`;
}

function pathSourceLinks(ids, anchor=null) {
  const unique = [...new Set((ids || []).filter(id => typeof id === 'string' && id))];
  if (!unique.length) return '<p class="path-unresolved">이 역할의 출처 기록 없음</p>';
  return unique.map(id => {
    const artifact = (state.artifacts || []).find(item => item.id === id);
    if (!artifact) return '<span class="path-unresolved">연결 원자료 확인 필요</span>';
    const label = sourceDisplayLabel(artifact,null,sourceDisplayRow(artifact,anchor));
    const located = anchor?.artifact_id === id && Number.isInteger(anchor.row_index) && anchor.row_index >= 0;
    const locator = located ? `data-source-offset="${esc(anchor.row_index)}" data-source-quote="${esc(pathText(anchor.quote))}"` : '';
    return pathButton('source',label && label !== id ? label : '원자료 보기',id,locator);
  }).join(' ');
}
function pathBoundContexts(basis) {
  if (!basis?.hypothesis_id) return '';
  const record = state.judgment_context, context = record?.context;
  const bindings = (context?.bindings || []).filter(binding => binding.hypothesis_id === basis.hypothesis_id);
  if (!bindings.length) return '';
  return `<section class="path-evidence-section"><h3>이 주장에 연결된 평가 관측</h3>
    <p class="path-version">${Number.isInteger(record.context_revision)?'연구 기록 '+esc(record.context_revision):'조건 입력 확인 필요'}${record.is_current_input===false?' · 이전 조건':''}</p>
    ${bindings.map(binding => {const target=(context.contexts || []).find(c=>c.id===binding.context_id),p=binding.prediction || {};
      return `<div class="path-bound-context"><p><strong>${esc(p.observable || '판독값 확인 필요')}</strong>${p.unit?' · '+esc(p.unit):''}</p>
        ${p.direction_or_range?`<p>기록된 예상: ${esc(p.direction_or_range)}</p>`:''}
        <dl>${[['대상',target?.organism],['조직·세포',target?.tissue_cell],['표적·구성체',target?.target_construct_variant],
          ['비교군',p.comparator || target?.comparator],['시점',p.time || target?.time]].filter(([,v])=>v).map(([k,v])=>
          `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl></div>`;}).join('')}
  </section>`;
}
function pathEvidenceBody(option, rankingRow) {
  const a = option.assessment || {}, basis = a.basis, clauses = basis?.clauses || [];
  const candidates = pathLinkedCandidates(option.option_id);
  return `<div class="path-evidence-body"><p class="path-version">${esc(pathRevision(option.assessment))} · ${esc(PATH_STATUS_LABEL[a.status] || '검토 전')}</p>
    <section class="path-evidence-section"><h3>기록된 연결 판단</h3><p>${esc(pathWording(a.reason || option.description || '연결 판단 확인 필요'))}</p></section>
    ${clauses.length?`<section class="path-evidence-section"><h3>주장과 원문 인용</h3>${clauses.map((clause,index)=>
      `<article class="path-clause"><span class="path-field">근거 문장 ${index+1} · ${esc(PATH_MATCH_LABEL[clause.disease_match] || '적용 범위 확인')}</span>
       <p class="path-claim">${esc(clause.text || '')}</p>
       <p class="path-context">${[clause.context?.disease,clause.context?.species,clause.context?.tissue].filter(Boolean).map(esc).join(' · ')}</p>
       ${clause.anchor?.quote?`<span class="path-field">원문 인용</span><blockquote>${esc(clause.anchor.quote)}</blockquote>`:''}
       ${clause.anchor?.artifact_id?pathSourceLinks([clause.anchor.artifact_id],clause.anchor):''}
       ${sourceLocatorDetails(state.artifacts.find(a=>a.id===clause.anchor?.artifact_id),clause.anchor)}</article>`).join('')}</section>`:
       '<p class="path-unresolved">이 검토는 아래 원자료를 평가에 연결했습니다. 구조화된 기전 문장·인용 위치는 추가로 확인할 수 있습니다.</p>'}
    <section class="path-evidence-section"><h3>지지 근거로 연결한 자료</h3>${pathSourceLinks(a.support_source_ids)}
      <h3>반대 근거로 연결한 자료</h3>${pathSourceLinks(a.challenge_source_ids)}</section>
    ${rankingRow?.figures?.length&&typeof mechanismFigures==='function'?`<section class="path-evidence-section"><h3>이 근거 논문의 그림</h3>${mechanismFigures(rankingRow,rankingRow.figures.length)}</section>`:''}
    ${pathBoundContexts(basis)}
    ${candidates.length?`<section class="path-evidence-section"><h3>후보가 이 경로를 겨냥하는 이유</h3>${candidates.map(candidate=>
      `<article class="path-candidate-evidence"><h4>${esc(pathCandidateName(candidate))}</h4><p class="path-candidate-relation">${esc(pathCandidateMeaning(candidate))}</p>
      <p>${esc(pathWording(candidate.assessment.targets_mechanism.reason))}</p>${pathButton('discovery-detail','후보의 개별 근거',candidate.option_id)}</article>`).join('')}</section>`:''}
    <section class="path-evidence-section"><h3>다음 확인</h3>${a.next_action?`<p>${esc(pathWording(a.next_action))}</p>`:''}
      ${[...(a.uncertainties || []),...(basis?.missing_in_target_disease || []).map(g=>g.claim)].map(text=>`<p>${esc(text)}</p>`).join('')}
      ${!a.next_action?'<p class="path-unresolved">이 경로의 다음 확인 기록을 검토하는 단계입니다.</p>':''}</section></div>`;
}
async function pathAction(action, node) {
  if(action==='path-select'){
    if(pathMechanisms().some(x=>x.option_id===node.dataset.id)){pathViewSelections.set(state.id,node.dataset.id);render();[...document.querySelectorAll('[data-action="path-select"]')].find(n=>n.dataset.id===node.dataset.id)?.focus()}
    return true;
  }
  if (action !== 'path-evidence') return false;
  const id = node?.dataset?.id, key = pathWorkspaceKey(), request = ++pathPanelRequest;
  if (!id || !key) return true;
  const option = await getOption(id);
  if (pathWorkspaceKey() !== key || request !== pathPanelRequest) return true;
  const row = (pathRanking()?.rows || []).find(x=>x.option_id===id);
  await openResearchPanel({kind:'relation', id,
    title:`${pathWording(option.label || option.option_id)}의 관계 근거`,
    body:pathEvidenceBody(option,row), subject:{kind:'mechanism',id,label:option.label || option.option_id}});
  return true;
}
