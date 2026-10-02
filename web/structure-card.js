// Candidate structures. The drawing comes from the stored SMILES and the identifiers come from
// the record; neither is looked up here. A row whose structure string could not be read keeps the
// string and says so, because an empty box and an unreadable structure are different facts.

function structureFigure(depiction, label) {
  if (!depiction || depiction.status !== 'drawn' || !depiction.svg) {
    const why = depiction && depiction.status === 'unparsed'
      ? '구조 문자열을 읽지 못했습니다' : '구조 그림 없음';
    return `<div class="structure-figure empty"><span class="small muted">${esc(why)}</span></div>`;
  }
  // The drawing is inert markup produced by RDKit from the stored string.
  return `<figure class="structure-figure" role="img" aria-label="${esc((label || '') + ' 구조 그림')}">
    ${depiction.svg}</figure>`;
}

function structureFacts(row) {
  const d = row.depiction || {};
  const facts = [];
  if (d.formula) facts.push(['분자식', esc(d.formula)]);
  if (d.average_mass) facts.push(['분자량', `${esc(d.average_mass)} g/mol`]);
  if (d.exact_mass) facts.push(['정확 질량', esc(d.exact_mass)]);
  // The record's own key wins. The other one is computed here from the stored SMILES, and the
  // two disagree whenever the record and the string differ on stereochemistry or on salt versus
  // parent. Letting the computed key lead would put two identically labelled PubChem links for
  // two different compounds on one card, so a disagreement is shown as a disagreement instead.
  const recorded = row.inchikey || (row.structure || {}).standard_inchi_key;
  const computed = d.inchikey;
  if (recorded || computed) {
    facts.push([recorded ? 'InChIKey' : 'InChIKey · 저장된 구조 문자열에서 계산',
                externalAnchor('inchikey', recorded || computed)]);
  }
  if (recorded && computed && computed !== recorded) {
    facts.push(['InChIKey 불일치', `<span class="warn">저장된 구조 문자열에서 계산하면
      <code class="mono">${esc(computed)}</code>입니다. 기록된 값과 달라 같은 화합물인지 확인이 필요합니다.</span>`]);
  }
  const smiles = (row.depiction || {}).smiles || row.smiles;
  if (smiles) facts.push(['SMILES', `<code class="mono">${esc(smiles)}</code>`]);
  if (!facts.length) return '';
  return `<dl class="structure-facts">${facts.map(([k, v]) =>
    `<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')}</dl>`;
}

// A candidate is only offered a 3D view when a docking run in this research actually names it,
// so the button never opens someone else's pose.
function dockedRunFor(candidateId) {
  if (!candidateId || typeof state === 'undefined' || !state) return null;
  return (state.artifacts || []).find(a => a.kind === 'molecular_docking'
    && a.meta?.result_status === 'succeeded'
    && (a.meta?.arguments?.candidate_ids || []).includes(candidateId)) || null;
}

function structureThreeDimensional(row) {
  const id = row.candidate_id ?? row.entity_id ?? row.row_id;
  const run = dockedRunFor(id);
  if (!run) return '';
  return `<p class="structure-3d">${button('science-view-structure', '실제 좌표로 3D 보기',
    `data-id="${esc(run.id)}" data-candidate="${esc(id)}"`, 'link-button small')}
    <span class="small muted">이 연구에서 실행한 도킹 결과의 좌표입니다. 측정된 결합 구조가 아닙니다.</span></p>`;
}

// One candidate, large enough to judge: drawing, readable name, identifiers and what was computed.
function structureCard(row, extra) {
  if (!row || typeof row !== 'object') return '';
  const name = candidateName(row);
  // Only fills in a key the record does not have; it never competes with a recorded one.
  const recordedKey = row.inchikey || (row.structure || {}).standard_inchi_key;
  const links = identifierLinkRow(row, !recordedKey && (row.depiction || {}).inchikey
    ? {inchikey: row.depiction.inchikey} : undefined);
  return `<article class="structure-card">
    ${structureFigure(row.depiction, name || row.candidate_id)}
    <div class="structure-body">
      <h4>${candidateLabel(row)}</h4>
      ${structureFacts(row)}
      ${structureThreeDimensional(row)}
      ${links}
      ${extra || ''}
      <p class="limit">저장된 구조 문자열을 그린 것입니다. 측정된 구조나 입체 배좌가 아니며,
        실제 시료의 동일성 확인도 아닙니다.</p>
    </div>
  </article>`;
}

// A compact cell for tables, so a list of candidates is readable without opening each one.
function structureThumb(row) {
  const d = (row && row.depiction) || {};
  if (d.status !== 'drawn' || !d.svg) return '';
  return `<div class="structure-thumb">${d.svg}</div>`;
}

function hasDepictions(result) {
  return !!(result && Array.isArray(result.rows) && result.rows.some(r => r && r.depiction));
}

// Table used for any stored view whose rows carry a structure.
function structureTable(result) {
  const rows = result.rows.filter(r => r && (r.depiction || r.smiles));
  if (!rows.length) return '';
  return `<div class="structure-grid">${rows.map(r => structureCard(r)).join('')}</div>
    ${result.depiction_limit ? `<p class="limit">구조 그림은 앞의 ${esc(result.depiction_limit)}개 행에만 붙였습니다. 나머지 행의 자료는 그대로 있습니다.</p>` : ''}
    <p class="limit">${esc(result.depiction_meaning || '')}</p>`;
}
