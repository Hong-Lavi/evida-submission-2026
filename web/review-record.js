// The stored record of one option review, as a person reads it.
//
// This is what the researcher opens from "선택지 검토". It used to fall through to raw JSON, which
// is unreadable at the exact moment someone is trying to check a judgement. Nothing is summarised
// or reworded here: every field is the model's own recorded text, shown where a reader expects it.

const REVIEW_AXES = {disease_match: '질환 일치도', clinical_precedent: '임상 선례',
                     evidence_grade: '근거의 종류', actionability: '개입 가능성'};
const REVIEW_STEP = ['가장 낮음', '낮음', '중간', '높음', '가장 높음'];
const REVIEW_GRADE = {established: '확립 · 사람 개입 근거', demonstrated: '실증 · 동물·세포 개입 근거',
                      hypothesis: '가설 · 목표 질환 개입 근거 없음'};
const REVIEW_MATCH = {target_disease: '목표 질환', related_disease: '유사 질환',
                      animal_model: '동물 모델', in_vitro: '세포·조직', none: '질환 맥락 없음'};

function reviewAxisCells(aspects) {
  if (!aspects || typeof aspects !== 'object') return '';
  const cells = Object.keys(REVIEW_AXES).map(axis => {
    const value = aspects[axis];
    const known = value !== null && value !== undefined;
    const step = known ? REVIEW_STEP[Math.max(0, Math.min(4, Math.round(Number(value) * 4)))] : '미확인';
    return `<div class="axis-cell${known ? '' : ' unchecked'}">
      <span class="axis-name">${esc(REVIEW_AXES[axis])}</span>
      <span class="axis-value">${esc(step)}</span></div>`;
  }).join('');
  return `<div class="axis-row">${cells}</div>`;
}

// A clause carries the sentence it was anchored to, so the reader checks the paper rather than us.
function reviewClauses(basis) {
  const clauses = (basis && basis.clauses) || [];
  if (!clauses.length) return '';
  return `<ol class="mechanism-clauses">${clauses.map(c => {
    const where = [c.context && c.context.disease, c.context && c.context.species,
                   c.context && c.context.tissue].filter(Boolean).join(' · ');
    const anchor = c.anchor || {};
    return `<li>
      <p class="clause-text">${esc(c.text || '')}</p>
      ${anchor.quote ? `<blockquote class="clause-quote">${esc(anchor.quote)}</blockquote>` : ''}
      <p class="small muted">${esc(where || '조건 미기재')}${
        c.disease_match ? ` · ${esc(REVIEW_MATCH[c.disease_match] || c.disease_match)}` : ''}</p>
      ${anchor.artifact_id ? sourceLinks([anchor.artifact_id]) : ''}
    </li>`;
  }).join('')}</ol>`;
}

function reviewGaps(basis) {
  const gaps = (basis && basis.missing_in_target_disease) || [];
  if (!gaps.length) return '';
  return `<div class="mechanism-gaps"><span class="roadmap-label">목표 질환에서 비어 있는 것</span>
    <ul>${gaps.map(g => `<li>${esc(g.claim || '')}${
      g.reported_count === null || g.reported_count === undefined
        ? '' : ` <span class="small muted">(조회 ${esc(g.reported_count)}건)</span>`}
      ${g.query_artifact_id ? sourceLinks([g.query_artifact_id]) : ''}</li>`).join('')}</ul></div>`;
}

// What the server checked about this assessment's basis: whether each quote is really in the
// stored row, and whether each gap count matches the recorded search. Advisory, never a verdict
// on the science - a rejected anchor means the quote was not found, not that the claim is false.
function reviewBasisCheck(check) {
  if (!check || typeof check !== 'object') return '';
  const problems = check.issues || [];
  const clauses = check.clauses || [];
  const gaps = check.gaps || [];
  const failed = [...clauses, ...gaps].filter(c => c && c.status !== 'verified');
  if (!problems.length && !failed.length) {
    return `<p class="small muted">인용문과 조회 건수를 보존 자료와 대조했고 모두 일치했습니다.</p>`;
  }
  return `<details class="review-check bad"><summary>대조에서 남은 문제 ${esc(problems.length || failed.length)}건</summary>
    <ul>${failed.map(c => `<li>${esc(c.reason || c.status)}${
      c.kind ? ` <span class="small muted">· ${esc(c.kind)}</span>` : ''}</li>`).join('')}</ul>
    <p class="limit">인용문을 보존 행에서 찾지 못했다는 뜻이며, 주장이 틀렸다는 판정이 아닙니다.</p></details>`;
}

function reviewAssessment(row, options) {
  const named = options[row.option_id];
  const label = named ? named.label : row.option_id;
  const kind = named ? (optionKinds[named.kind] || named.kind) : '';
  const basis = row.basis;
  const grade = basis && basis.grade;
  const link = row.targets_mechanism;
  const linked = link && options[link.option_id];
  return `<article class="review-assessment">
    <header>
      <h4>${esc(label)}</h4>
      <p class="small muted">${esc(kind)}${kind ? ' · ' : ''}${
        esc(optionStatus[row.status] || row.status)}${
        grade ? ` · ${esc(REVIEW_GRADE[grade] || grade)}` : ''}${
        row.priority !== null && row.priority !== undefined && row.comparison_group
          ? ` · ${esc(row.comparison_group)} ${esc(row.priority)}순위` : ''}</p>
    </header>
    ${reviewAxisCells(row.aspects)}
    ${reviewClauses(basis)}
    ${reviewGaps(basis)}
    ${reviewBasisCheck(row.basis_check)}
    ${row.reason ? `<p class="mechanism-reason">${esc(row.reason)}</p>` : ''}
    ${link ? `<p class="small">겨냥한 기전 · <strong>${esc(linked ? linked.label : link.option_id)}</strong>
      — ${esc(link.reason || '')}</p>` : ''}
    ${(row.uncertainties || []).length ? `<div class="mechanism-gaps">
      <span class="roadmap-label">남은 불확실성</span>
      <ul>${row.uncertainties.map(u => `<li>${esc(u)}</li>`).join('')}</ul></div>` : ''}
    ${row.next_action ? `<p class="small"><span class="roadmap-label">다음 행동</span> ${esc(row.next_action)}</p>` : ''}
    ${(row.support_source_ids || []).length ? `<p class="small"><span class="roadmap-label">지지 자료</span>
      ${sourceLinks(row.support_source_ids)}</p>` : ''}
    ${(row.challenge_source_ids || []).length ? `<p class="small"><span class="roadmap-label">반대 자료</span>
      ${sourceLinks(row.challenge_source_ids)}</p>` : ''}
  </article>`;
}

function reviewRecordView(value, meta) {
  if (!value || typeof value !== 'object') return '';
  const fresh = value.new_options || [];
  const assessments = value.assessments || [];
  const options = {};
  for (const o of fresh) options[o.option_id] = o;
  for (const a of assessments) if (!options[a.option_id]) options[a.option_id] = null;
  const checks = (meta && meta.basis_check) || [];
  const byOption = {};
  for (const c of checks) if (c && c.option_id) byOption[c.option_id] = c;
  const rows = assessments.map(a => ({...a, basis_check: byOption[a.option_id]}));
  const unsearched = value.unsearched_scope || [];
  return `<section class="review-record">
    ${value.question ? `<div class="review-question"><span class="roadmap-label">이 검토가 답한 질문</span>
      <p class="prose">${esc(value.question)}</p></div>` : ''}
    ${fresh.length ? `<details class="review-new" open><summary>이번에 등록한 선택지 ${esc(fresh.length)}개</summary>
      <ul>${fresh.map(o => `<li><strong>${esc(o.label)}</strong>
        <span class="small muted">${esc(optionKinds[o.kind] || o.kind)}</span>
        <p class="small">${esc(o.description || '')}</p>
        ${(o.source_ids || []).length ? sourceLinks(o.source_ids) : ''}</li>`).join('')}</ul>
      <p class="limit">등록은 발견을 보존한 것이며 추천이 아닙니다.</p></details>` : ''}
    ${rows.length ? `<h4 class="structured-heading">검토한 선택지 ${esc(rows.length)}개</h4>
      ${rows.map(r => reviewAssessment(r, options)).join('')}`
      : '<p class="small muted">이 기록은 선택지를 등록만 했고 개별 평가는 남기지 않았습니다. 평가가 없다는 것이 제외라는 뜻은 아닙니다.</p>'}
    ${unsearched.length ? `<details class="review-unsearched"><summary>이번에 조회하지 않은 범위 ${esc(unsearched.length)}개</summary>
      <ul>${unsearched.map(u => `<li>${esc(typeof u === 'string' ? u : (u.scope || JSON.stringify(u)))}</li>`).join('')}</ul>
      <p class="limit">조회하지 않았다는 기록이며, 그곳에 아무것도 없다는 뜻이 아닙니다.</p></details>` : ''}
    <p class="limit">모델이 기록한 검토입니다. 과학적 검증이 아니며, 생략된 선택지가 제외된 것도 아닙니다.</p>
  </section>`;
}
