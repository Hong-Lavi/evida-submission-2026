// The computed order over mechanisms and approaches.
//
// Two things this must never do. It must not manufacture a first place: the order is a partial
// order, and when nothing is ahead of everything else that is a result, shown as one, not an
// error. And it must not present the weighting as measured — the axis-order statements it rests
// on are printed so a reader can reject them.

const AXIS_LABEL = {disease_match: '적용성', clinical_precedent: '임상 선례',
                    evidence_grade: '타당성', actionability: '개입 가능성'};
// Decision 0040: only the first two decide the order. 임상 선례 is recorded evidence that does not
// order anything by itself, and 개입 가능성 is what our tools can reach today - it is shown as a
// badge because a mechanism must not rank higher for being convenient to us.
const AXIS_WHAT = {disease_match: '이 질환·이 결과에 해당하는가',
                   evidence_grade: '설계와 실제 읽은 내용',
                   clinical_precedent: '사람에서의 이력 · 순서를 정하지 않음',
                   actionability: '지금 도구로 할 수 있는 일 · 순서를 정하지 않음'};
const HOLD_LABEL = {unassessed_axis: '미평가', support_not_confirmed: '지지 근거 미확인',
                    challenge_not_reviewed: '반대 근거 미검토',
                    applicable_challenge_unresolved: '반대 근거 적용 범위 미정',
                    bridge_not_reviewed: '겨냥한 기전 미검토'};
const GRADE_LABEL = {established: '확립 · 사람 개입 근거', demonstrated: '실증 · 동물·세포 개입 근거',
                     hypothesis: '가설 · 목표 질환 개입 근거 없음'};
const AXIS_STEP = ['가장 낮음', '낮음', '중간', '높음', '가장 높음'];

function axisStep(value) {
  if (value === null || value === undefined) return {text: '미확인', level: null};
  const step = Math.max(0, Math.min(4, Math.round(Number(value) * 4)));
  return {text: AXIS_STEP[step], level: step};
}

function mechanismAxes(aspects, optionId) {
  const compared = (mechanismRanking && mechanismRanking.comparison_axes)
    || ['disease_match', 'evidence_grade'];
  const cell = (axis, ordering) => {
    const {text, level} = axisStep((aspects || {})[axis]);
    return `<button type="button" data-action="mechanism-axis" data-axis="${esc(axis)}"
      data-option="${esc(optionId || '')}"
      class="axis-cell${level === null ? ' unchecked' : ''}${ordering ? '' : ' aside'}"
      title="${esc(AXIS_WHAT[axis] || '')} · 눌러서 이 값이 무엇에서 나왔는지 보기">
      <span class="axis-name">${esc(AXIS_LABEL[axis])}</span>
      <span class="axis-value">${esc(text)}</span>
      <span class="axis-what">${esc(AXIS_WHAT[axis] || '')}</span></button>`;
  };
  const others = Object.keys(AXIS_LABEL).filter(a => !compared.includes(a));
  return `<div class="axis-row">${compared.map(a => cell(a, true)).join('')}</div>
    <div class="axis-row axis-row-aside">${others.map(a => cell(a, false)).join('')}</div>`;
}

const AXIS_RUBRIC = {
  disease_match: ['모든 절의 맥락이 목표 질환·사람', '사람이지만 다른 질환', '동물 개체',
                  '세포·조직만', '질환 맥락 없음 (경로 수준)'],
  clinical_precedent: ['목표 질환 적응증의 허가 라벨', '목표 질환 등록시험 (2상 이상)',
                       '다른 적응증의 승인약', '물질은 있으나 등록시험 0건', '검색했고 해당 물질 없음'],
  evidence_grade: ['대조 사람 시험의 결과를 읽음', '대조 사람 시험이지만 초록·계획서만',
                   '대조가 있는 동물 실험 원문', '관찰·발현 연관만', '인용 근거 없음 · 경로 추론뿐'],
  actionability: ['후보 구조가 있고 필요한 계산이 돎', '후보는 나오나 계산 하나가 막힘',
                  '열거·서열 계산만 가능', '표적만 확인되고 후보를 뽑을 도구가 없음',
                  '조회했으나 작용할 실체가 없음'],
};
const AXIS_RUBRIC_MEANING = {
  disease_match: '관측이 어디에서 나왔는가 (강도가 아닙니다). 절이 여럿이면 가장 낮은 절을 씁니다.',
  clinical_precedent: '사람에게 투여된 적이 있는가. 효과가 있었는지가 아닙니다.',
  evidence_grade: '설계와 실제로 읽은 깊이.',
  actionability: '지금 연결된 도구로 후보까지 갈 수 있는가. 좋은 생각인지가 아닙니다.',
};
const CLAUSE_MATCH = {target_disease: '목표 질환', related_disease: '가까운 질환',
                      animal_model: '동물 모델', in_vitro: '세포·시험관', none: '해당 없음'};

// A12: an axis value is a rubric level somebody recorded, so a reader can ask what it was read
// off. Only what is stored is shown - the step, the clause contexts that set it, the recorded
// grade and the gaps - and the panel ends by saying what the server did and did not check.
function mechanismAxisDetail(row, axis) {
  if (!row) return '<p>이 선택지의 기록을 찾을 수 없습니다.</p>';
  const value = (row.aspects || {})[axis];
  const {text, level} = axisStep(value);
  const rubric = AXIS_RUBRIC[axis] || [];
  const ordering = (mechanismRanking && mechanismRanking.comparison_axes)
    || ['disease_match', 'evidence_grade'];
  const basis = row.basis || null;
  const clauses = (basis && basis.clauses) || [];
  const gaps = (basis && basis.missing_in_target_disease) || [];
  const steps = rubric.length
    ? `<ol class="axis-rubric">${rubric.map((line, index) => {
        const step = rubric.length - 1 - index;
        return `<li class="${step === level ? 'chosen' : ''}">${esc(line)}${
          step === level ? '<span class="axis-chosen-mark">기록된 값</span>' : ''}</li>`;
      }).join('')}</ol>` : '';
  const perClause = axis === 'disease_match' && clauses.length
    ? `<h4>이 값을 정한 절</h4>
       <p class="small muted">절이 여럿이면 <strong>가장 낮은 절</strong>이 이 축의 값이 됩니다.
         한 절이라도 목표 질환 밖이면 전체가 그 단계로 내려갑니다.</p>
       <ul class="axis-clauses">${clauses.map(c => `<li>
         <span class="axis-clause-match">${esc(CLAUSE_MATCH[c.disease_match] || c.disease_match || '미기재')}</span>
         ${esc((c.text || '').slice(0, 90))}</li>`).join('')}</ul>` : '';
  const grade = axis === 'evidence_grade' && basis && basis.grade
    ? `<h4>기록된 등급</h4><p>${esc(basis.grade)} · ${esc(GRADE_LABEL[basis.grade] || '')}</p>` : '';
  const gapNote = gaps.length
    ? `<h4>목표 질환에서 비어 있는 것 ${esc(gaps.length)}개</h4>
       <ul class="axis-clauses">${gaps.map(g => `<li>${esc(g.claim || '')}${
         g.reported_count === undefined ? ''
           : ` <span class="small muted">조회 결과 ${esc(g.reported_count)}건</span>`}</li>`).join('')}</ul>` : '';
  const rule = AXIS_RUBRIC_MEANING[axis]
    ? `<p class="axis-rule">${esc(AXIS_RUBRIC_MEANING[axis])}</p>` : '';
  const role = ordering.includes(axis)
    ? '<p class="axis-role ordering">이 축은 <strong>순서를 정하는 데 쓰입니다.</strong></p>'
    : `<p class="axis-role aside">이 축은 <strong>순서를 정하지 않습니다.</strong> ${esc(AXIS_WHAT[axis] || '')}</p>`;
  return `<p class="axis-value-line"><strong>${esc(text)}</strong>${
      value === null || value === undefined ? '' : ` <span class="small muted">기록값 ${esc(value)}</span>`}</p>
    ${rule}${role}
    ${value === null || value === undefined
      ? '<p class="notice-inline">이 축은 아직 판정하지 않았습니다. 미확인은 0점이 아니며, 이 선택지는 순서 계산에서 비교 보류로 빠집니다.</p>'
      : steps}
    ${perClause}${grade}${gapNote}
    <p class="limit">이 값은 모델이 기록한 판정입니다. 서버가 기계적으로 대조하는 것은 절에 붙은 인용문이 저장된 원문의
      정확한 부분 문자열인지까지이며, 단계 선택 자체를 검증하지는 않습니다.</p>`;
}

// An option that cannot take part in a comparison yet says which condition is missing. It keeps
// its record and its place on the screen; what it loses is the claim to be ahead of anything.
function mechanismHold(row) {
  if (!row || row.comparable !== false) return '';
  const names = (row.hold_reasons || []).map(r => HOLD_LABEL[r] || r).join(' · ');
  return `<p class="mechanism-hold"><strong>비교 보류</strong> ${esc(names)}
    ${(row.hold_meanings || []).map(m => `<span class="small muted">${esc(m)}</span>`).join('')}</p>`;
}

// The figure from the paper a clause was anchored to. It is the paper's own figure shown next to
// the claim that cites it - not a drawing of the mechanism, and nothing here read the image. Only
// files already retrieved are offered, so the card never waits on a download.
function mechanismFigures(row, limit) {
  const figures = (row.figures || []).slice(0, limit);
  if (!figures.length || typeof state === 'undefined' || !state) return '';
  const src = f => `/api/workspaces/${encodeURIComponent(state.id)}/artifacts/`
    + `${encodeURIComponent(f.artifact_id)}?figure=${encodeURIComponent(f.file)}`;
  return `<div class="mechanism-figures">${figures.map(f => `<figure>
    <img src="${esc(deploymentURL(src(f)))}" alt="${esc((f.caption || f.file) + ' · 원문 그림')}" loading="lazy">
    ${f.caption ? `<figcaption>${esc(f.caption)}</figcaption>` : ''}${sourceFigureScope(f)}
    <p class="small muted">${f.link_kind==='assessment_source'
      ? f.source_role==='challenge'?'검토 시 반대 근거로 연결한 원문의 그림입니다.':'검토 시 지지 근거로 연결한 원문의 그림입니다.'
      : '이 근거 문장에 연결한 원문의 그림입니다.'} 캡션과 원문 위치를 함께 확인하세요.${f.source_url
        ? ` <a href="${esc(f.source_url)}" target="_blank" rel="noopener noreferrer" class="source-link">원문</a>` : ''}</p>
  </figure>`).join('')}</div>`;
}

// A clause is shown with the sentence it was anchored to, so the reader checks the paper, not us.
function mechanismClauses(basis) {
  const clauses = (basis && basis.clauses) || [];
  if (!clauses.length) return '';
  const where = c => [c.context && c.context.disease, c.context && c.context.species,
                      c.context && c.context.tissue].filter(Boolean).join(' · ');
  return `<ol class="mechanism-clauses">${clauses.map(c => `<li>
    <p class="clause-text">${esc(c.text || '')}</p>
    ${c.anchor && c.anchor.quote
      ? `<blockquote class="clause-quote">${esc(c.anchor.quote)}</blockquote>` : ''}
    ${quoteSupport(c)}
    <p class="small muted">${esc(where(c) || '조건 미기재')}${
      c.disease_match ? ` · ${esc(c.disease_match)}` : ''}</p>
  </li>`).join('')}</ol>`;
}

// Whether the quoted sentence carries the clause. Advisory: it says something about this one
// sentence, not about whether the clause is true, so the wording must not read as a verdict.
const SUPPORT_NOTE = {
  supported: ['인용문이 이 절을 뒷받침합니다', 'ok'],
  not_carried: ['이 인용문만으로는 이 절이 나오지 않습니다', 'warn'],
  contradicted: ['인용문이 이 절과 반대로 읽힙니다 · 확인이 필요합니다', 'bad'],
};

function quoteSupport(clause) {
  const value = clause && clause.quote_supports_clause;
  if (!value || !SUPPORT_NOTE[value.status]) return '';
  const [text, tone] = SUPPORT_NOTE[value.status];
  return `<p class="quote-support ${tone}">${esc(text)}${
    value.confidence ? ` <span class="small muted">${esc(value.confidence)}</span>` : ''}${
    value.input_truncated ? ' <span class="small muted">· 긴 인용문은 앞부분만 검사했습니다</span>' : ''}</p>`;
}

function mechanismGaps(basis) {
  const gaps = (basis && basis.missing_in_target_disease) || [];
  if (!gaps.length) return '';
  return `<div class="mechanism-gaps"><span class="roadmap-label">목표 질환에서 비어 있는 것</span>
    <ul>${gaps.map(g => `<li>${esc(g.claim || '')}${
      g.reported_count === null || g.reported_count === undefined
        ? '' : ` <span class="small muted">(조회 ${esc(g.reported_count)}건)</span>`}</li>`).join('')}</ul></div>`;
}

// Every mechanism keeps its clauses and its gaps, not only the one in front: a reader who wants
// to move a lower mechanism up needs to see what it rests on. Below first place they are folded
// so the page stays readable, but a clause whose quote reads against it is named on the summary
// line, because a warning behind a closed fold is a warning nobody sees.
function mechanismBasis(basis, lead, row) {
  const body = mechanismClauses(basis) + mechanismGaps(basis)
    + (lead ? '' : mechanismFigures(row, 1));
  if (!body) return '';
  if (lead) return body;
  const clauses = (basis && basis.clauses) || [];
  const against = clauses.filter(c => (c.quote_supports_clause || {}).status === 'contradicted').length;
  const gaps = ((basis && basis.missing_in_target_disease) || []).length;
  const figures = (row && row.figures || []).length;
  const note = [`근거 절 ${clauses.length}개`, gaps ? `목표 질환 공백 ${gaps}개` : '',
                figures ? `원문 그림 ${figures}개` : '',
                against ? `반대로 읽히는 인용문 ${against}개` : ''].filter(Boolean).join(' · ');
  return `<details class="mechanism-basis${against ? ' bad' : ''}">
    <summary>${esc(note)}</summary>${body}</details>`;
}

// Below first place the reason and the next action used to be dropped, so a researcher comparing
// options saw the axes but not what the model actually concluded. The researcher may pick a lower
// rank, and cannot do that from four bars alone.
function mechanismReason(row) {
  const parts = [];
  if (row.reason) parts.push(`<p class="mechanism-reason">${esc(researcherWording(row.reason))}</p>`);
  if (row.status) {
    parts.push(`<p class="small muted">${esc(optionStatus[row.status] || row.status)}${
      row.priority !== null && row.priority !== undefined && row.comparison_group
        ? ` · ${esc(row.comparison_group)} ${esc(row.priority)}순위` : ''}</p>`);
  }
  return parts.join('');
}

function mechanismSources(row) {
  const ids = (row.sources || []).map(s => s && s.artifact_id).filter(Boolean).slice(0, 6);
  if (!ids.length) return '';
  return `<p class="source-links">${ids.map(id =>
    button('source', esc(artifactName(id)), `data-id="${esc(id)}"`, 'link-button small')).join('')}</p>`;
}

function mechanismCard(row, lead) {
  const grade = row.basis && row.basis.grade;
  const stale = row.current_conditions === false;
  return `<article class="mechanism-card${lead ? ' lead' : ''}">
    <header>
      <h4>${esc(researcherWording(row.label || row.option_id))}</h4>
      <p class="small muted">${esc(row.kind === 'mechanism' ? '기전' : '치료 접근')}${
        grade ? ` · ${esc(GRADE_LABEL[grade] || grade)}` : ''}${
        row.contradicted ? ' · <strong>반대 근거 기록됨</strong>' : ''}</p>
      ${stale ? '<p class="small muted">이전 조건의 검토입니다. 현재 입력 반영은 확인되지 않았습니다.</p>' : ''}
    </header>
    ${lead ? mechanismFigures(row, 2) : ''}
    ${mechanismAxes(row.aspects, row.option_id)}
    ${mechanismHold(row)}
    ${mechanismBasis(row.basis, lead, row)}
    ${mechanismReason(row)}
    ${(row.unchecked_axes || []).length
      ? `<p class="small muted">미확인 축 · ${(row.unchecked_axes || [])
          .map(a => esc(AXIS_LABEL[a] || a)).join(', ')}</p>` : ''}
    ${mechanismSources(row)}
  </article>`;
}

function mostlyAheadNotes(ranking) {
  const notes = ranking.mostly_ahead_notes || [];
  if (!notes.length) return '';
  const byId = Object.fromEntries((ranking.rows || []).map(r => [r.option_id, r]));
  const name = id => (byId[id] && byId[id].label) || id;
  return `<details class="mechanism-mostly"><summary>순서를 정하지 않은 쌍 중 한쪽이 대체로 앞선 경우 ${esc(notes.length)}개</summary>
    <ul>${notes.map(n => `<li>${esc(name(n.pair[0]))} ↔ ${esc(name(n.pair[1]))} ·
      <strong>${esc(name(n.mostly_ahead))}</strong>가 대체로 앞섰습니다</li>`).join('')}</ul>
    <p class="limit">${esc(notes[0].meaning)}</p></details>`;
}

function statedOrder(ranking) {
  const order = ranking.stated_axis_order || [];
  if (!order.length) return '';
  return `<details class="stated-order"><summary>순서를 정할 때 쓴 가정 ${esc(order.length)}개</summary>
    <ul>${order.map(o => `<li>${esc(AXIS_LABEL[o.at_least_as_heavy] || o.at_least_as_heavy)}가
      ${esc(AXIS_LABEL[o.as] || o.as)}보다 가볍지 않다</li>`).join('')}</ul>
    ${ranking.stated_axis_order_approval
      ? `<p class="limit">연구자가 승인한 가정입니다(결정 0038, ${esc(ranking.stated_axis_order_approval.approved_on || '')}).
          측정된 가중치는 아니며, 결정을 철회하면 빠지고 정할 수 있는 순서가 달라집니다.</p>`
      : `<p class="limit">측정된 가중치가 아니라 검토할 주장입니다. 하나를 거부하면 정할 수 있는 순서가
          달라집니다.</p>`}</details>`;
}

// What would actually change the order. Filling an unchecked axis can only add order, never
// reverse what is already decided, so this is a real next action rather than a suggestion.
function unresolvedNext(ranking) {
  const compared = ranking.comparison_axes || ['disease_match', 'evidence_grade'];
  const counts = {};
  for (const row of ranking.rows || []) {
    for (const axis of row.unchecked_axes || []) {
      if (compared.includes(axis)) counts[axis] = (counts[axis] || 0) + 1;
    }
  }
  const worst = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  if (!worst) return '';
  return `<p class="rank-next">비교에 쓰는 축을 채우면 순서가 더 갈릴 수 있습니다. 이미 정해진 순서가
    뒤집히지는 않습니다. <strong>지금 가장 많이 비어 있는 축 · ${esc(AXIS_LABEL[worst[0]] || worst[0])}
    ${esc(worst[1])}개</strong></p>`;
}

// Two places read together, never multiplied: the two orders come from different comparisons and
// nothing measured relates them, so a single combined number would be invented.
function mechanismCandidatePairs(ranking) {
  const paired = ranking.mechanism_candidate_pairs;
  if (!paired || !paired.linked) return '';
  return `<details class="pair-table" open><summary>기전과 후보를 함께 본 순서 · ${esc(paired.linked)}개</summary>
    <div class="table-scroll"><table><thead><tr><th>기전</th><th>후보</th><th>이 후보를 그 기전에 연결한 이유</th></tr></thead>
    <tbody>${paired.pairs.map(p => `<tr>
      <td>${esc(p.mechanism_label)}<br><span class="small muted">${
        p.mechanism_tier ? `계산된 ${esc(p.mechanism_tier)}단계` : '순서 미정'}</span></td>
      <td>${esc(p.candidate_label)}<br><span class="small muted">${
        p.candidate_priority ? `${esc(p.candidate_comparison_group || '')} ${esc(p.candidate_priority)}순위`
          : '순위 기록 없음'}</span></td>
      <td class="small">${esc(researcherWording(p.link_reason || ''))}</td></tr>`).join('')}</tbody></table></div>
    <p class="limit">두 순서를 나란히 읽은 것입니다. 곱하지 않았고 결합 확률을 만들지 않았습니다 —
      서로 다른 비교에서 나온 숫자라 하나로 합칠 근거가 없습니다. 후보의 기록이 기전을 지목한
      경우에만 나옵니다.</p></details>`;
}

function mechanismRankDetail(ranking) {
  if (!ranking || ranking.status !== 'computed') {
    return `<p class="muted">${esc((ranking && ranking.meaning)
      || '아직 계산할 순서가 없습니다.')}</p>`;
  }
  const rows = ranking.rows || [];
  const byId = Object.fromEntries(rows.map(r => [r.option_id, r]));
  const leader = ranking.single_leader ? byId[ranking.single_leader] : null;
  const frontier = (ranking.frontier || []).map(id => byId[id]).filter(Boolean);
  const rest = rows.filter(r => r.tier > 1);
  const held = rows.filter(r => r.comparable === false);
  const withheld = {contradicting_evidence_recorded: '반대 근거가 기록되어 1순위로 올리지 않았습니다.',
                    no_axis_checked: '비교에 쓰는 축이 모두 미확인입니다.',
                   }[ranking.single_leader_withheld];
  const alone = ranking.single_leader_withheld === 'only_one_option_graded';

  const head = leader
    ? `<div class="rank-head"><span class="rank-badge">1순위</span>
        <span class="small muted">비교 조건을 갖춘 항목 중, 적용성과 타당성 모두에서 뒤지지 않고 하나 이상에서 앞섭니다</span></div>
       ${mechanismCard(leader, true)}`
    : `<div class="rank-head"><span class="rank-badge undecided">${esc(alone ? '비교 대상 없음' : '1위 미정')}</span>
        <span class="small muted">${esc(alone ? '축을 기록한 기전 1개' : `최상위 후보 ${frontier.length}개`)}</span></div>
       <p class="rank-explain">${alone
         ? '축을 기록한 기전이 하나뿐이라 아직 아무것도 비교하지 않았습니다. 이 기전을 1순위라고 말하려면 비교할 다른 기전이 필요합니다. 오류가 아니라 사례 초기의 정상적인 상태입니다.'
         : withheld
         ? esc(withheld) + ' 부분순서 자체는 그대로 둡니다.'
         : '적용성과 타당성 두 기준 모두에서 앞서는 항목이 없습니다. 아래는 서로 순서를 정하지 않았습니다. 오류가 아니라 지금 근거로 말할 수 있는 전부입니다.'}</p>
       <div class="mechanism-grid">${frontier.map(r => mechanismCard(r, frontier.length === 1)).join('')}</div>`;

  const disagreement = ranking.model_priority_comparison
    && (ranking.model_priority_comparison.disagreements || []).length;
  return `<section class="mechanism-rank">
    ${head}
    ${unresolvedNext(ranking)}
    ${mechanismCandidatePairs(ranking)}
    ${mostlyAheadNotes(ranking)}
    ${held.length ? `<details class="mechanism-held"><summary>아직 비교하지 않은 항목 ${esc(held.length)}개</summary>
      <p class="small muted">${esc(ranking.eligibility_rule || '')}</p>
      <div class="mechanism-grid">${held.map(r => mechanismCard(r, false)).join('')}</div></details>` : ''}
    ${rest.length ? `<details class="mechanism-rest"><summary>아래 순위 ${esc(rest.length)}개</summary>
      <div class="mechanism-grid">${rest.filter(r => r.comparable !== false).map(r => mechanismCard(r, false)).join('')}</div></details>` : ''}
    ${disagreement ? `<p class="small muted">계산된 순서와 모델이 적은 우선순위가 ${esc(disagreement)}곳에서
      다릅니다. 둘 다 그대로 표시하며 어느 쪽도 고치지 않습니다.</p>` : ''}
    ${statedOrder(ranking)}
    ${supportControl()}
    <p class="limit">${esc(ranking.comparison_axes_meaning || '')} ${esc(ranking.comparison_rule || '')}
      확률이나 효능 추정이 아니며 과학적 검증도 아닙니다. 같은 자리의 항목은 서로 순서를 정하지 않았습니다.</p>
  </section>`;
}

// The first view answers which paths are being considered. Exact axes, quotes,
// comparison rules and complete source records remain in the expandable review.
function mechanismRankView(ranking) {
  if (!ranking || ranking.status !== 'computed') return mechanismRankDetail(ranking);
  const rows = ranking.rows || [];
  const leader = rows.find(row => row.option_id === ranking.single_leader);
  const ordered = leader ? [leader, ...rows.filter(row => row !== leader)] : rows;
  const card = row => {
    const count = typeof mechanismCandidateCount === 'function' ? mechanismCandidateCount(row.option_id) : 0;
    const clauses = row.basis?.clauses || [];
    const counter = row.contradicted || clauses.some(c => c.quote_supports_clause?.status === 'contradicted');
    const grade = GRADE_LABEL[row.basis?.grade];
    const summary = row.reason || clauses[0]?.text || '현재 근거와 적용 조건을 검토하는 경로입니다.';
    return `<article class="mechanism-summary${row === leader?' is-leading':''}">
      <div class="mechanism-summary-label">${row === leader?'<span class="rank-badge">1순위</span>':''}<span>${esc(row.kind==='mechanism'?'기전':'치료 접근')}</span>${row.current_conditions===false?'<span class="roadmap-flag">이전 조건의 검토</span>':''}</div>
      <h4>${esc(researcherWording(row.label || row.option_id))}</h4>${grade?`<p class="small muted">${esc(grade)}</p>`:''}
      ${counter?'<p class="mechanism-counter">반대 근거 함께 검토</p>':''}
      <p class="mechanism-summary-reason">${esc(researcherWording(summary))}</p>
      ${mechanismFigures(row, 1)}
      <div class="overview-actions">${button('discovery-detail','이유·원자료',`data-id="${esc(row.option_id)}"`,'small')}${count?button('roadmap-focus-mechanism',`연결 후보 ${count}개`,`data-id="${esc(row.option_id)}"`,'small'):''}</div>
    </article>`;
  };
  return `<section class="mechanism-overview"><p class="mechanism-overview-intro">검토한 기전과 접근 ${rows.length}개${leader?' · 현재 비교에서 앞선 경로를 먼저 표시합니다.':' · 각 경로의 근거와 다음 확인을 비교합니다.'}</p>
    <div class="mechanism-summary-grid">${ordered.slice(0,3).map(card).join('')}</div>
    ${ordered.length>3?`<details class="mechanism-other-paths" data-detail-key="mechanism-other-paths"><summary>다른 경로 ${ordered.length-3}개 보기</summary><div class="mechanism-summary-grid">${ordered.slice(3).map(card).join('')}</div></details>`:''}
    <details class="mechanism-comparison-detail" data-detail-key="mechanism-comparison-detail"><summary>평가 기준·근거 문장·기전별 비교 전체 보기</summary>${mechanismRankDetail(ranking)}</details>
  </section>`;
}


// Loaded lazily when stage 2 is open: the computed order is a screen view, so it is not part of
// the workspace snapshot and never reaches a model request.
let mechanismRanking = null, mechanismRankingFor = null, mechanismRankingError = '', mechanismRankingVersion = 0;
let mechanismRankingPendingFor = null, mechanismRankingErrorFor = null;
let mechanismSupportRequested = false, mechanismSupportRunning = false, mechanismSupportRunningFor = null;
function mechanismRankingKey() {
  return state ? `${state.id}@${state.event_cursor}@${state.rev}` : null;
}

// Whether each quoted sentence carries the clause it was attached to. The first run loads a
// model, so it is asked for rather than run on every open — and it is advisory either way:
// nothing in the order changes when it returns.
function supportControl() {
  if (mechanismSupportRunning && mechanismSupportRunningFor === mechanismRankingKey()) {
    return `<p class="small muted">인용문이 절을 뒷받침하는지 대조하는 중입니다.
      처음 한 번은 모델을 불러오느라 몇 분 걸릴 수 있습니다.</p>`;
  }
  if (mechanismSupportRequested) {
    return `<p class="small muted">인용문–절 대조를 실행했습니다. 결과는 각 절 아래에 있습니다.
      참고용이며 순서를 바꾸지 않았습니다.</p>`;
  }
  return `<p class="mechanism-support-ask">${button('mechanism-support',
    '인용문이 절을 뒷받침하는지 검사', '', 'link-button small')}
    <span class="small muted">각 절에 붙은 인용문이 그 절을 실제로 담고 있는지 대조합니다.
      참고용이며 순서를 바꾸지 않습니다.</span></p>`;
}

async function loadMechanismSupport() {
  if (!state) return;
  const wid = state.id, key = mechanismRankingKey();
  if (mechanismSupportRunning && mechanismSupportRunningFor === key) return;
  const version = ++mechanismRankingVersion;
  mechanismSupportRunning = true;
  mechanismSupportRunningFor = key;
  render();
  try {
    const value = await api(`/api/workspaces/${encodeURIComponent(wid)}/mechanism-ranking?support=1`);
    if (mechanismRankingKey() === key && version === mechanismRankingVersion) {
      mechanismRanking = value;
      mechanismRankingFor = key;
      mechanismSupportRequested = true;
      mechanismRankingError = '';
      mechanismRankingErrorFor = null;
    }
  } catch (error) {
    if (mechanismRankingKey() === key && version === mechanismRankingVersion) {
      mechanismRankingError = error.message;
      mechanismRankingErrorFor = key;
    }
  } finally {
    if (mechanismSupportRunningFor === key) {
      mechanismSupportRunning = false;
      mechanismSupportRunningFor = null;
    }
    if (mechanismRankingKey() === key) render();
  }
}

async function loadMechanismRanking() {
  if (!state) return;
  const wid = state.id, key = mechanismRankingKey();
  if (mechanismRankingFor === key || mechanismRankingPendingFor === key) return;
  const version = ++mechanismRankingVersion;
  mechanismRankingPendingFor = key;
  try {
    const value = await api(`/api/workspaces/${encodeURIComponent(wid)}/mechanism-ranking`);
    if (mechanismRankingKey() !== key || version !== mechanismRankingVersion) return;
    mechanismRanking = value;
    mechanismRankingFor = key;
    mechanismSupportRequested = false;  // this reload carries no verdicts; do not claim it does
    mechanismRankingError = '';
    mechanismRankingErrorFor = null;
  } catch (error) {
    if (mechanismRankingKey() === key && version === mechanismRankingVersion) {
      mechanismRankingError = error.message;
      mechanismRankingErrorFor = key;
    }
  } finally {
    if (version === mechanismRankingVersion) mechanismRankingPendingFor = null;
    if (mechanismRankingKey() === key && version === mechanismRankingVersion) render();
  }
}

function mechanismRankSection() {
  const key = mechanismRankingKey();
  if (!key) return '';
  if (mechanismRankingError && mechanismRankingErrorFor === key) {
    return `<p class="small" role="alert">순서를 불러오지 못했습니다 · ${esc(mechanismRankingError)}</p>`;
  }
  if (!mechanismRanking || mechanismRankingFor !== key) {
    loadMechanismRanking();
    return '<p class="small muted">기록한 축으로 순서를 계산하는 중입니다.</p>';
  }
  return mechanismRankView(mechanismRanking);
}
