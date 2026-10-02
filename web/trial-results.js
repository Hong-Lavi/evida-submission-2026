// A registered trial's reported results, read straight from the stored record.
// Every number here is copied from the registry response; nothing is recomputed, combined across
// trials or turned into a verdict. A trial with no posted results says so rather than showing
// blanks, because "not posted" and "no effect" are different things.

function trialPercent(affected, atRisk) {
  const a = Number(affected), n = Number(atRisk);
  if (!Number.isFinite(a) || !Number.isFinite(n) || n <= 0) return '';
  return ` (${(100 * a / n).toFixed(1)}%)`;
}

function trialInterval(measurement) {
  const {value, lowerLimit, upperLimit, spread} = measurement || {};
  if (value === undefined || value === null || value === '') return '미보고';
  const range = (lowerLimit !== undefined && upperLimit !== undefined && lowerLimit !== null)
    ? ` [${esc(lowerLimit)} ~ ${esc(upperLimit)}]`
    : (spread !== undefined && spread !== null ? ` ± ${esc(spread)}` : '');
  return `<strong>${esc(value)}</strong>${range}`;
}

// Group-versus-group tests as the registry recorded them, including the method, because a p-value
// without its model is not interpretable.
function trialAnalyses(outcome, groupName) {
  const analyses = outcome.analyses || [];
  if (!analyses.length) return '';
  const rows = analyses.map(a => {
    const pairs = (a.groupIds || []).map(id => esc(groupName[id] || id)).join(' 대 ');
    const p = a.pValue !== undefined && a.pValue !== null && a.pValue !== ''
      ? `p ${esc(a.pValue)}` : 'p 미보고';
    const method = a.statisticalMethod ? ` · ${esc(a.statisticalMethod)}` : '';
    const kind = a.nonInferiorityType && a.nonInferiorityType !== 'SUPERIORITY'
      ? ` · ${esc(a.nonInferiorityType)}` : '';
    return `<li>${pairs} — ${p}${method}${kind}</li>`;
  }).join('');
  return `<ul class="trial-analyses">${rows}</ul>`;
}

function trialOutcome(outcome) {
  const groupName = {};
  for (const g of outcome.groups || []) groupName[g.id] = g.title;
  const measurements = [];
  for (const cls of outcome.classes || []) {
    for (const category of cls.categories || []) {
      for (const m of category.measurements || []) {
        measurements.push({...m, label: [cls.title, category.title].filter(Boolean).join(' · ')});
      }
    }
  }
  const body = measurements.length
    ? `<div class="table-scroll"><table><thead><tr><th>비교군</th><th>값${
        outcome.unitOfMeasure ? ` · ${esc(outcome.unitOfMeasure)}` : ''}</th>${
        measurements.some(m => m.label) ? '<th>구분</th>' : ''}</tr></thead><tbody>${
        measurements.map(m => `<tr><td>${esc(groupName[m.groupId] || m.groupId)}</td><td>${
          trialInterval(m)}</td>${measurements.some(x => x.label) ? `<td>${esc(m.label || '')}</td>` : ''}</tr>`
        ).join('')}</tbody></table></div>`
    : `<p class="muted">이 평가항목에는 반환된 측정값이 없습니다${
        outcome.reportingStatus ? ` · ${esc(outcome.reportingStatus)}` : ''}.</p>`;
  return `<section class="trial-outcome"><h4>${esc(outcome.title || '제목 없음')}</h4>
    <p class="small muted">${[outcome.type, outcome.paramType, outcome.dispersionType]
      .filter(Boolean).map(esc).join(' · ')}</p>
    ${outcome.timeFrame ? `<p class="small muted">측정 시점 · ${esc(outcome.timeFrame)}</p>` : ''}
    ${body}${trialAnalyses(outcome, groupName)}
    ${outcome.populationDescription ? `<p class="small muted">분석집단 · ${esc(outcome.populationDescription)}</p>` : ''}
  </section>`;
}

// The most frequently affected terms, so a reader sees what actually happened to patients rather
// than only a count. Ordering is by affected share; it is not a safety ranking.
function trialEventTable(events, groupName, limit) {
  const scored = events.map(event => {
    const stats = event.stats || [];
    const best = stats.reduce((top, s) => {
      const share = Number(s.numAtRisk) > 0 ? Number(s.numAffected) / Number(s.numAtRisk) : 0;
      return share > top ? share : top;
    }, 0);
    return {event, share: best};
  }).sort((a, b) => b.share - a.share).slice(0, limit);
  if (!scored.length) return '';
  const ids = Object.keys(groupName);
  return `<div class="table-scroll"><table><thead><tr><th>이상반응</th><th>기관계</th>${
    ids.map(id => `<th>${esc(groupName[id])}</th>`).join('')}</tr></thead><tbody>${
    scored.map(({event}) => {
      const byGroup = {};
      for (const s of event.stats || []) byGroup[s.groupId] = s;
      return `<tr><td>${esc(event.term || '')}</td><td>${esc(event.organSystem || '')}</td>${
        ids.map(id => {
          const s = byGroup[id];
          return `<td>${s ? esc(s.numAffected) + '/' + esc(s.numAtRisk) + trialPercent(s.numAffected, s.numAtRisk) : '—'}</td>`;
        }).join('')}</tr>`;
    }).join('')}</tbody></table></div>`;
}

function trialAdverseEvents(module) {
  if (!module || !(module.eventGroups || []).length) return '';
  const groupName = {};
  for (const g of module.eventGroups) groupName[g.id] = g.title || g.id;
  const summary = `<div class="table-scroll"><table><thead><tr><th>비교군</th><th>중대한 이상반응</th>
    <th>기타 이상반응</th><th>사망</th></tr></thead><tbody>${
    module.eventGroups.map(g => `<tr><td>${esc(g.title || g.id)}</td>
      <td>${esc(g.seriousNumAffected)}/${esc(g.seriousNumAtRisk)}${trialPercent(g.seriousNumAffected, g.seriousNumAtRisk)}</td>
      <td>${esc(g.otherNumAffected)}/${esc(g.otherNumAtRisk)}${trialPercent(g.otherNumAffected, g.otherNumAtRisk)}</td>
      <td>${g.deathsNumAffected !== undefined ? esc(g.deathsNumAffected) + '/' + esc(g.deathsNumAtRisk) : '미보고'}</td></tr>`
    ).join('')}</tbody></table></div>`;
  const serious = module.seriousEvents || [], other = module.otherEvents || [];
  return `<section class="trial-adverse"><h4>이상반응</h4>
    ${module.frequencyThreshold ? `<p class="small muted">기타 이상반응 보고 기준 · ${esc(module.frequencyThreshold)}% 이상</p>` : ''}
    ${summary}
    ${serious.length ? `<details><summary>중대한 이상반응 ${esc(module.seriousEventsTotal ?? serious.length)}건 중 빈도 상위 ${serious.length}건</summary>
      ${trialEventTable(serious, groupName, 12)}
      <p class="limit">보고된 빈도 순입니다. 군간 차이의 유의성 검정이 아니며 인과 판정도 아닙니다.</p></details>` : ''}
    ${other.length ? `<details><summary>기타 이상반응 ${esc(module.otherEventsTotal ?? other.length)}건 중 빈도 상위 ${other.length}건</summary>
      ${trialEventTable(other, groupName, 12)}</details>` : ''}
    <p class="limit">용어 사전 ${esc(((serious[0] || other[0] || {}).sourceVocabulary) || '원 기록 확인')} · 등록부에 게시된 값 그대로입니다.</p>
  </section>`;
}

// Entry point: the structured results view for a stored clinical_trial artifact.
function trialResultsView(value) {
  const summary = (value && value.summary) || {};
  // The paged artifact view drops the raw response and supplies `reported_results` instead; the
  // full record is still read directly when the whole artifact is in hand.
  const derived = value && value.reported_results;
  const section = value && value.response && value.response.resultsSection;
  const results = derived
    ? {outcomeMeasuresModule: {outcomeMeasures: derived.outcomeMeasures || []},
       adverseEventsModule: derived.adverseEvents}
    : section;
  const link = summary.nct_id ? externalAnchor('nct', summary.nct_id) : '';
  if (!results) {
    return `<section class="trial-results"><p class="small">${link}
      ${summary.has_results === false
        ? '· 이 시험은 등록부에 결과를 게시하지 않았습니다. 결과 미게시는 효과 없음과 다릅니다.'
        : '· 결과 게시 여부가 확인되지 않았습니다.'}</p></section>`;
  }
  const outcomes = (results.outcomeMeasuresModule || {}).outcomeMeasures || [];
  const primary = outcomes.filter(o => o.type === 'PRIMARY');
  const rest = outcomes.filter(o => o.type !== 'PRIMARY');
  return `<section class="trial-results">
    <p class="small">${link} · 게시된 결과 항목 ${esc(outcomes.length)}개</p>
    ${primary.map(trialOutcome).join('')}
    ${rest.length ? `<details><summary>그 밖의 평가항목 ${rest.length}개</summary>${
      rest.map(trialOutcome).join('')}</details>` : ''}
    ${trialAdverseEvents(results.adverseEventsModule)}
  </section>`;
}
