
;
/* Source: deployment.js */
// One optional mount prefix. Scientific source strings and external URLs are untouched.
const EVIDA_BASE = location.pathname === '/preview' || location.pathname.startsWith('/preview/') ? '/preview' : '';
function deploymentURL(value){
  const path=String(value??'');
  if(!path.startsWith('/')||path.startsWith('//')||!EVIDA_BASE||path===EVIDA_BASE||path.startsWith(EVIDA_BASE+'/'))return path;
  return EVIDA_BASE+path;
}
function deploymentHTML(html){return String(html).replace(/\b(href|src)=(['"])(\/(?!\/)[^'"]*)\2/g,(_match,attr,quote,url)=>`${attr}=${quote}${deploymentURL(url)}${quote}`)}
const evidaStorage={
  getItem:key=>localStorage.getItem((EVIDA_BASE?'evida-preview:':'')+key),
  setItem:(key,value)=>localStorage.setItem((EVIDA_BASE?'evida-preview:':'')+key,value),
  removeItem:key=>localStorage.removeItem((EVIDA_BASE?'evida-preview:':'')+key)
};


;
/* Source: external-links.js */
// Links from identifiers the research already holds. No new lookup is made here and no
// identifier is invented: a link is produced only when the exact ID is present in the record.
// A link points at the public source page; it does not assert that the source was read.
const EXTERNAL_SOURCES = {
  nct: {label: 'ClinicalTrials.gov', test: /^NCT\d{8}$/i,
        url: v => 'https://clinicaltrials.gov/study/' + v.toUpperCase()},
  pmcid: {label: 'PMC', test: /^PMC\d+$/i,
          url: v => 'https://pmc.ncbi.nlm.nih.gov/articles/' + v.toUpperCase() + '/'},
  pmid: {label: 'PubMed', test: /^\d{1,9}$/,
         url: v => 'https://pubmed.ncbi.nlm.nih.gov/' + v + '/'},
  doi: {label: 'DOI', test: /^10\.\d{4,9}\/\S+$/,
        url: v => 'https://doi.org/' + v},
  chembl: {label: 'ChEMBL', test: /^CHEMBL\d+$/i,
           url: v => 'https://www.ebi.ac.uk/chembl/explore/compound/' + v.toUpperCase()},
  chembl_target: {label: 'ChEMBL 표적', test: /^CHEMBL\d+$/i,
                  url: v => 'https://www.ebi.ac.uk/chembl/explore/target/' + v.toUpperCase()},
  pubchem: {label: 'PubChem', test: /^\d{1,9}$/,
            url: v => 'https://pubchem.ncbi.nlm.nih.gov/compound/' + v},
  inchikey: {label: 'PubChem · InChIKey', test: /^[A-Z]{14}-[A-Z]{10}-[A-Z]$/,
             url: v => 'https://pubchem.ncbi.nlm.nih.gov/#query=' + encodeURIComponent(v)},
  uniprot: {label: 'UniProt', test: /^[OPQ][0-9][A-Z0-9]{3}[0-9]$|^[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$/,
            url: v => 'https://www.uniprot.org/uniprotkb/' + v.toUpperCase()},
  ensembl: {label: 'Ensembl', test: /^ENS[A-Z]*[GT]\d{6,}(\.\d+)?$/i,
            url: v => 'https://ensembl.org/id/' + v.toUpperCase()},
  setid: {label: 'DailyMed', test: /^[0-9a-f-]{20,}$/i,
          url: v => 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=' + v},
  url: {label: '원문', test: /^https?:\/\/[^\s"'<>]+$/i, url: v => v},
};

function externalUrl(kind, value) {
  const source = EXTERNAL_SOURCES[kind];
  if (!source || typeof value !== 'string') return null;
  const clean = value.trim();
  return clean && source.test.test(clean) ? source.url(clean) : null;
}

// `label` defaults to the identifier itself so the ID stays visible and checkable.
function externalAnchor(kind, value, label) {
  const href = externalUrl(kind, value);
  const text = esc(label ?? value ?? '');
  if (!href) return text;
  return `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer" class="source-link">${text}</a>`;
}

// Field names actually used by the stored source rows, in display order.
const IDENTIFIER_FIELDS = [
  ['nct_id', 'nct'], ['nctId', 'nct'], ['pmcid', 'pmcid'], ['pmc_id', 'pmcid'],
  ['pmid', 'pmid'], ['doi', 'doi'], ['setid', 'setid'],
  ['molecule_chembl_id', 'chembl'], ['target_chembl_id', 'chembl_target'], ['chembl_id', 'chembl'],
  ['cid', 'pubchem'], ['CID', 'pubchem'], ['pubchem_cid', 'pubchem'],
  ['inchikey', 'inchikey'], ['InChIKey', 'inchikey'], ['standard_inchi_key', 'inchikey'],
  ['uniprot', 'uniprot'], ['accession', 'uniprot'],
  ['ensembl_id', 'ensembl'], ['gene_id', 'ensembl'],
  ['source_url', 'url'],
];

// Collect every identifier present on a record, deduplicated by resolved URL.
function identifierLinks(row, extra) {
  if (!row || typeof row !== 'object') return [];
  const found = [], seen = new Set();
  const consider = (field, kind, value) => {
    const href = externalUrl(kind, value);
    if (!href || seen.has(href)) return;
    seen.add(href);
    found.push({field, kind, value: String(value).trim(), href,
                label: EXTERNAL_SOURCES[kind].label});
  };
  for (const [field, kind] of IDENTIFIER_FIELDS) {
    const value = row[field] ?? row.structure?.[field] ?? row.identity?.[field];
    if (typeof value === 'string' || typeof value === 'number') consider(field, kind, String(value));
  }
  for (const [kind, value] of Object.entries(extra ?? {})) consider(kind, kind, value);
  return found;
}

function identifierLinkRow(row, extra) {
  const links = identifierLinks(row, extra);
  if (!links.length) return '';
  return `<p class="source-links">${links.map(l =>
    `<a href="${esc(l.href)}" target="_blank" rel="noopener noreferrer" class="source-link">${esc(l.label)} ${esc(l.value)}</a>`
  ).join('')}</p>`;
}

// A candidate's own identifier carries its database: CHEMBL1868, PUBCHEM:40632, BDBM:12.
function entityLink(entityId) {
  const value = String(entityId ?? '').trim();
  const prefixed = /^([A-Za-z]+):(.+)$/.exec(value);
  if (prefixed && prefixed[1].toUpperCase() === 'PUBCHEM') return {kind: 'pubchem', value: prefixed[2]};
  if (/^CHEMBL\d+$/i.test(value)) return {kind: 'chembl', value};
  return null;
}

// A readable chemical name where the record holds one. ChEMBL supplies pref_name but no IUPAC
// name; PubChem supplies both. The identifier always stays visible beside the name so a reader
// can check it, and an unnamed candidate shows its ID rather than an invented label.
function candidateName(row) {
  const structure = (row && row.structure) || {};
  const identity = (row && row.identity) || {};
  for (const value of [row && row.iupac_name, structure.IUPACName, row && row.pref_name,
                       identity.lookup_name, row && row.name, structure.Title]) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
}

function candidateLabel(row) {
  if (!row || typeof row !== 'object') return '';
  const id = String(row.candidate_id ?? row.row_id ?? row.id ?? '');
  const entity = entityLink(row.entity_id ?? id);
  const identifier = entity ? externalAnchor(entity.kind, entity.value, id) : esc(id);
  const name = candidateName(row);
  if (!name || name === id) return identifier;
  return `${esc(name)}<br><span class="small muted">${identifier}</span>`;
}

// Free-text identifiers (NCT…, PMID …, PMC…, doi:…) become links in place. The text is
// escaped first and only identifier shapes are replaced, so no markup can be injected.
// The text is escaped before this runs, so an ampersand inside a DOI is already `&amp;`. Reading
// it as an ordinary character would end the DOI at the entity and link to a different record, so
// the entity is matched as a unit here and turned back into `&` for the URL.
const INLINE_PATTERN = /(NCT\d{8})|(PMC\d{6,9})|(?:PMID[:\s]\s*)(\d{5,9})|(?:doi[:\s]\s*)(10\.\d{4,9}\/(?:&amp;|[^\s,;&)\]}"'])+)/gi;

function linkifyIdentifiers(text) {
  const safe = esc(String(text ?? ''));
  return safe.replace(INLINE_PATTERN, (match, nct, pmc, pmid, doi) => {
    if (nct) return externalAnchor('nct', nct);
    if (pmc) return externalAnchor('pmcid', pmc);
    if (pmid) return match.replace(pmid, externalAnchor('pmid', pmid));
    if (doi) return match.replace(doi, externalAnchor('doi', doi.replace(/&amp;/g, '&')));
    return match;
  });
}


;
/* Source: input-provenance.js */
// The server supplies effective classification; the preserved body stays inspectable.
function inputProvenance(event){
  if(event?.effective_provenance)return event.effective_provenance;
  const body=event?.body??{},synthetic=body.origin==='synthetic'||body.synthetic===true;
  return {origin:synthetic?'synthetic':body.origin??'researcher_report',synthetic,corrected_by:null};
}
function inputProvenanceLabel(event){
  const provenance=inputProvenance(event);
  return `${provenance.synthetic?'가상 입력':'연구자 입력'}${provenance.corrected_by?' · 출처 정정됨':''}`;
}
function inputProvenanceNotice(event){
  const provenance=inputProvenance(event),correction=provenance.corrected_by;
  if(!correction)return '';
  return `<p class="limit">${provenance.synthetic?'출처 정정에 따라 가상 시연 입력으로 분류합니다. 실제 측정이나 임상 효과의 근거가 아닙니다.':'출처 정정에 따라 연구자 보고로 분류합니다. 이 분류가 관측의 독립 검증을 뜻하지는 않습니다.'} 원문과 당시 출처 표기는 보존했습니다.</p><p class="small muted">연구자 확인: ${esc(correction.researcher_reply)} · ${esc(correction.reason)} ${button('message-source','출처 정정 기록',`data-id="${esc(correction.message_id)}"`,'link-button small')}</p>`;
}
function inputSourceView(event){
  if(!event)return '입력 기록을 찾지 못했습니다.';
  return `<p class="prose">${esc(event.body.text)}</p><p class="limit">${esc(inputProvenanceLabel(event))} · ${esc(event.created)}</p>${inputProvenanceNotice(event)}${event.effective_provenance?.corrected_by?`<details class="meta-details"><summary>정정 전 원 입력 기록</summary>${json(event.body)}</details>`:''}`;
}


;
/* Source: structure-card.js */
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


;
/* Source: review-record.js */
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


;
/* Source: mechanism-rank.js */
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


;
/* Source: discovery.js */
// Source-backed discovery and researcher choices. Recommendations never truncate the pool.
let goalApproach='', optionsOpen=false, optionsQuery='', optionsKind='', optionsOffset=0, optionsStage='';
let optionsPage=null, optionsError='', optionsWorkspace=null, optionsCursor=null, optionsLoadVersion=0;
const optionKinds={mechanism:'질환 기전',target:'표적',approach:'치료 접근',source_candidate:'문헌에서 찾은 후보·치료 참조',molecule:'구조·활성 조회 물질',rna_candidate:'RNA 후보·참조 조건',researcher_proposal:'연구자 제안'};
const optionStatus={recommended:'추천',alternative:'대안',needs_evidence:'근거 확인 필요',deferred:'현재 보류',unreviewed:'아직 미검토'};
function renderGoalWelcome(){
 if(intakeMode!=='question')return renderWelcome();
 return `<div class="welcome goal-home"><div class="welcome-heading"><div><span class="eyebrow">EVIDA · 연구 의사결정</span><h1>어떤 문제를 해결하고 싶으세요?</h1><p class="description">질환과 목표에서 출발해, 근거를 찾고 다음 실험을 결정합니다.</p></div></div>
 <section class="goal-start" aria-label="질환에서 연구 시작"><label class="input-label" for="message">연구할 질환·현상과 바꾸고 싶은 결과</label><textarea id="message" placeholder="예: 유전성 ATTR 아밀로이드증의 단백질 축적을 줄이고 싶어요. 관련 기전을 비교하고, 검토할 후보를 찾아 주세요.">${esc(draft)}</textarea>
 <fieldset class="approach-choices"><legend>우선 검토할 접근 <span class="muted">· 아직 정하지 않아도 됩니다</span></legend>${[['','함께 비교'],['small_molecule','저분자부터'],['sirna','siRNA부터']].map(([id,label])=>`<label class="approach-choice ${goalApproach===id?'selected':''}"><input type="radio" name="goal-approach" value="${id}" ${goalApproach===id?'checked':''}>${label}</label>`).join('')}</fieldset>
 <p class="goal-promise">후보 이름이나 서열이 없어도 시작할 수 있습니다. 기전과 표적의 근거를 찾고, 추천 이유와 다른 선택지를 함께 남깁니다.</p>
 ${intakeError?`<p class="form-error" role="alert">${esc(intakeError)}</p>`:''}<div class="input-bottom"><span class="small muted">공개 자료 조회와 실제 모델 검토가 시작됩니다.</span>${modelChoice()}${button('create-message','목표에서 연구 시작',busy?'disabled':'','primary')}</div></section>
 <div class="goal-journey" aria-label="연구 흐름">${[['01','구조화된 질문과 목표','무엇을, 왜 바꿀지'],['02','기전과 접근','어떤 방향을 검토할지'],['03','후보 발굴','무엇을 실제로 비교할지'],['04','근거와 계산','어디까지 확인했는지'],['05','EVIDA 실험 권고','다음에 무엇을 해볼지']].map(([n,t,d])=>`<div><span>${n}</span><strong>${t}</strong><p>${d}</p></div>`).join('')}</div>
 <section class="existing-entry"><h2>이미 진행 중인 연구가 있나요?</h2><p>가진 자료부터 시작하거나, 위 목표에 알려진 내용을 함께 적어 주세요.</p><div class="entry-help-actions">${ENTRY_PATHS.filter(x=>x.id!=='question').map(x=>button('choose-path',esc(x.name),`data-mode="${x.id}"`,'small')).join('')}${button('usage-help','사용법 보기','','quiet small')}</div></section>
 <section class="goal-examples"><h2>입력 예시</h2><div class="example-choices">${[['small_molecule','저분자 경로','유전성 ATTR 아밀로이드증의 축적을 줄이는 기전과 저분자 접근을 비교하고 싶어요. 후보가 없으니 근거로 찾고 실제 계산까지 이어 주세요.'],['sirna','siRNA 경로','간에서 만들어지는 TTR를 줄이는 접근이 유전성 ATTR 아밀로이드증에 타당한지 확인하고, 근거가 맞으면 실제 전사체에서 siRNA 후보를 만들어 비교해 주세요.']].map(([id,label,text])=>`<article><h3>${label}</h3><p>${text}</p>${button('discovery-example','이 질문으로 시작하기',`data-example="${id}"`,'small')}</article>`).join('')}</div><p class="small muted">예시 버튼은 질문을 채웁니다. 시작 버튼을 누르면 새 연구를 실행합니다.</p></section></div>`;
}
function rnaOptionContext(item){
 if(item.kind!=='rna_candidate'||!item.candidate_artifact_id)return '';
 const calculation=state.artifacts.find(a=>a.id===item.candidate_artifact_id);
 const reference=calculation?.meta.arguments?.artifact_id;
 if(!reference)return '';
 return `<p class="small muted">같은 가이드라도 전사체별 계산 조건은 다릅니다. 계산 참조: ${esc(artifactName(reference))}</p>`;
}
function optionKind(item){return item.kind??item.option_id.split(':')[0]}
function optionActionLabel(item,selected){const kind=optionKind(item);const base=({mechanism:'이 기전',target:'이 표적',approach:'이 접근',source_candidate:'이 문헌 후보',molecule:'이 화합물',rna_candidate:'이 RNA 후보',rna:'이 RNA 후보'})[kind]??'이 선택지';return base+(selected?'로 계속':' 검토하기')}
function groupedRecommendations(items){
 const groups=[['mechanism','target'],['approach'],['source_candidate','molecule','rna_candidate','rna'],['researcher_proposal']];
 const titles=['바꾸려는 기전과 표적','치료 접근','실제로 비교할 후보','연구자의 새 제안'];
 const known=new Set(groups.flat());
 return groups.map((kinds,i)=>{const rows=items.filter(x=>kinds.includes(optionKind(x)));return rows.length?`<section class="recommendation-stage"><h3>${titles[i]}</h3><div class="recommendation-grid">${rows.map(x=>discoveryCard(x,true)).join('')}</div></section>`:''}).join('')+
  `<div class="recommendation-grid">${items.filter(x=>!known.has(optionKind(x))).map(x=>discoveryCard(x,true)).join('')}</div>`;
}
function discoveryPreview(value){
 // Only frozen model-transport locators leave the card preview. Exact rationale
 // and its source links remain unchanged in the detail dialog and saved record.
 return String(value??'').replace(/\(D\d{4},\s*s-[a-f0-9]+-p\d+\.txt,[^)]*\)/g,'').trim();
}
function discoveryRecordLabel(assessment){
 if(!assessment)return '평가 기록 없음';
 const rev=Number.isInteger(assessment.based_rev)?`연구 기록 ${assessment.based_rev}`:'연구 기록 시점 미확인';
 return `${assessment.current_conditions===true?'현재 조건의 평가':assessment.current_conditions===false?'이전 조건의 평가':'평가 조건 확인 필요'} · ${rev}`;
}
function discoveryFirstDescription(item){
 if(!item.description)return '';
 const origin=(item.sources??[]).map(x=>state.artifacts.find(a=>a.id===x.artifact_id)).find(a=>a?.kind==='discovery_review');
 const rev=origin?.meta?.based_rev;
 return `<details class="discovery-first-description"><summary>처음 발견했을 때의 설명${Number.isInteger(rev)?' · 연구 기록 '+rev:' · 기록 시점 확인 필요'}</summary><p>${esc(item.description)}</p>${origin?sourceLinks([origin.id]):''}</details>`;
}
function discoveryCard(item,compact=false){
 const a=item.assessment,selected=item.selected??state.discovery?.selected?.option_id===item.option_id;
 const preview=discoveryPreview(a?.reason);
 const reviewJob=a?state.jobs.find(j=>j.id===state.artifacts.find(x=>x.id===a.artifact_id)?.meta?.job_id):null;const draftReview=reviewJob&&reviewJob.status!=='succeeded';
 return `<article class="option-card ${selected?'chosen':''}" data-option="${esc(item.option_id)}"><div class="option-heading"><div><span class="small muted">${esc(optionKinds[item.kind??item.option_id.split(':')[0]]??(item.option_id.startsWith('rna:')?'RNA 후보':'검토한 선택지'))}${a?.priority?` · ${a.priority}순위` :''}</span><h3>${esc(candidateDisplayName(item))}</h3></div><span class="option-tag ${esc(a?.status??'unreviewed')}">${selected?'연구자 선택':esc((a?.current_conditions===false?'이전 ':'')+optionStatus[a?.status??'unreviewed'])}</span></div>
 ${draftReview?`<p class="small revision-note">${['running','queued'].includes(reviewJob.status)?'검토 중인 추천안 · 최종 판단 전':'미완료 검토에서 보존한 추천안'}</p>`:''}${a?`<p class="small muted">${esc(discoveryRecordLabel(a))} · ${esc(optionStatus[a.status]??a.status)}</p><p>${judgmentText(compact&&preview.length>210?preview.slice(0,210)+'…':preview)}</p>${!a.current_conditions?'<p class="small revision-note">이전 조건의 검토 · 새 입력 반영 확인 필요</p>':''}`:`<p class="muted">발견 목록에 보존했습니다. 추천 여부는 아직 검토하지 않았습니다.</p>`}
 ${sourceCandidateInfo(item)}${rnaOptionContext(item)}${compact?'':discoveryFirstDescription(item)}<div class="detail-actions">${button('discovery-detail','근거·다음 확인',`data-id="${esc(item.option_id)}"`,'small')}${button('discovery-choose',optionActionLabel(item,selected),`data-id="${esc(item.option_id)}"`,'small')}${selected?'':button('discovery-run','이 경로로 연구 시작',`data-id="${esc(item.option_id)}" ${!status.gateway.available||busy?'disabled':''}`,'small primary')}</div></article>`;
}
function renderDiscovery(){
 const d=state.discovery;if(!d)return '';
 const recommended=(d.recommendations??[]).filter(item=>item.assessment?.current_conditions===true);
 const earlierRecommendations=(d.recommendations??[]).filter(item=>item.assessment?.current_conditions!==true);
 const spaces=state.artifacts.filter(a=>a.kind==='rna_candidate_space'&&a.meta.result_status==='succeeded');
 const listName=spaces.length?'기전·접근·개별 후보 목록':'발견한 선택지 전체';
 return `<section class="discovery-section" aria-label="추천과 전체 선택지"><div class="section-heading"><div><span class="section-mark">선택지를 보존하며 연구하기</span><h2>${recommended.length?'현재 조건에서 추천한 선택지':'선택지와 검토 기록'}</h2></div><span class="small muted">${spaces.length?'기전·접근·개별 후보':'발견'} ${d.total} · 검토 ${d.reviewed}</span></div>
 ${d.selected?`<div class="selected-path"><strong>${d.selected.state_rev<state.rev?'이전 입력의 선택 기록':'연구자의 선택 기록'}</strong> ${esc(d.selected.label)}${d.selected.reason?`<details><summary>선택 이유와 당시 조건</summary><p>${esc(d.selected.reason)}</p>${d.selected.state_rev<state.rev?'<p class="small">이번 입력보다 앞선 선택 기록입니다. 현재 적용 범위는 위 판단에서 확인하세요.</p>':''}</details>`:''}</div>`:''}
 ${recommended.length?`<div class="current-recommendations">${groupedRecommendations(recommended)}</div>`:`<p class="muted">${d.total?'현재 조건에서 추천으로 표시한 선택지는 없습니다. 아래에서 이전 추천과 보류 이유, 아직 평가하지 않은 선택지를 확인하고 다시 검토할 수 있습니다.':'질환의 근거를 조회하면 기전·표적·후보가 여기에 쌓입니다.'}</p>`}
 ${earlierRecommendations.length?`<details class="earlier-recommendations"><summary>이전 조건의 추천 ${earlierRecommendations.length}개 보기</summary><p class="small muted">당시 이유와 원 근거를 보존했습니다. 현재 목표의 추천과 구분해서 보고, 필요한 경로는 다시 선택할 수 있습니다.</p>${groupedRecommendations(earlierRecommendations)}</details>`:''}
 ${d.reconsidered_options?.length?`<section class="reconsidered-options"><h3>새 근거로 다시 확인할 접근·후보</h3><p class="small muted">앞서 추천했던 선택지의 현재 조건과 이유입니다. 후보는 보존하고, 추천이 바뀐 이유를 확인합니다.</p>${groupedRecommendations(d.reconsidered_options)}</section>`:''}
 <div class="discovery-controls">${button('discovery-toggle',optionsOpen?'목록 접기':`${listName} 보기 (${d.total})`,`aria-expanded="${optionsOpen}"`,'small')}${button('discovery-propose','다른 경로 제안하기','','small')}</div>
 ${spaces.length?`<section class="rna-retained-spaces" aria-label="보존한 전체 RNA 서열 후보"><h3>아직 고르지 않은 RNA 후보도 살펴보세요</h3><p class="small muted">위 목록의 수는 전체 서열 후보 수가 아닙니다. 아래에서 모든 후보를 검색하고, 추천 밖 후보도 골라 실제 계산할 수 있습니다.</p>${spaces.map(a=>{const s=a.meta.summary??{};return `<div class="discovery-controls">${button('source',`${s.region_annotated?'CDS·UTR로 살펴보기':'원 후보 목록 보기'} · ${Number(s.unique_guide_sequences).toLocaleString()}개`,`data-id="${esc(a.id)}"`,'small')}<span class="small muted">${s.selected_references}개 참조 · ${s.paired_length}nt · 원위치 ${Number(s.known_base_origins).toLocaleString()}개 · 효능 순위 아님</span></div>`}).join('')}</section>`:''}
 ${optionsOpen?renderOptionBrowser():''}<p class="small muted pool-scope">발견한 범위의 목록입니다. 추천 밖 항목도 검토할 수 있고, 아직 찾지 않은 기전·후보가 있을 수 있습니다.</p></section>`;
}
function renderOptionBrowser(){
 const ready=optionsPage&&optionsWorkspace===state.id&&optionsCursor===`${state.event_cursor}@${state.rev}`;
 return `<div class="option-browser"><div class="option-filters"><label>선택지 검색<input type="search" id="option-query" value="${esc(optionsQuery)}" placeholder="이름, 이유, 출처로 찾기"></label><label>종류<select id="option-kind"><option value="">모든 종류</option>${Object.entries(optionKinds).map(([k,v])=>`<option value="${k}" ${optionsKind===k?'selected':''}>${v}</option>`).join('')}</select></label>${button('discovery-search','찾기','','small')}</div>
 ${optionsError?`<p role="alert">${esc(optionsError)}</p>`:''}${ready?`<div class="option-range"><span>${optionsPage.filtered_total}개 중 ${optionsPage.rows.length?optionsPage.offset+1:0}–${optionsPage.offset+optionsPage.rows.length} 표시</span><div>${button('discovery-prev','이전',optionsOffset===0?'disabled':'','small')}${button('discovery-next','다음',!optionsPage.has_more?'disabled':'','small')}</div></div><div class="option-list">${optionsPage.rows.map(x=>discoveryCard(x)).join('')||'<p>이 검색에 맞는 항목이 없습니다. 다른 검색이나 새 경로 제안을 이용하세요.</p>'}</div>`:'<p>원자료에 연결된 목록을 불러오고 있습니다.</p>'}
 <details class="pool-coverage"><summary>찾은 범위와 아직 남은 탐색</summary>${state.discovery.scope_review?`<p class="small muted">${state.discovery.scope_review.current_conditions?'현재 조건에서 남긴 탐색 메모':'이전 조건에서 남긴 탐색 메모 · 이후 읽은 자료는 최신 판단과 함께 확인하세요.'}${sourceLinks([state.discovery.scope_review.artifact_id])}</p>`:''}${list(state.discovery.unsearched_scope)}${(state.discovery.rna_search_coverage??[]).map(c=>`<p class="small">${esc(c.transcript_id)} · ${c.paired_length}nt 결합 영역 ${c.possible_windows}개 중 ${c.generated_windows}개 생성 · ${c.remaining_windows_not_generated}개 미생성${c.version?` · 버전 ${esc(c.version)}`:""}</p>`).join("")}${ready?optionsPage.coverage.map(c=>`<p class="small">${esc(labels[c.kind]??c.kind)} · ${esc(c.summary?.rule??'보존된 원 조회 범위')}${c.summary?.has_more?' · 다음 페이지 있음':''}${sourceLinks([c.artifact_id])}</p>`).join(''):''}</details></div>`;
}
async function loadOptions(){
 if(!state||!optionsOpen)return;const wid=state.id,cursor=`${state.event_cursor}@${state.rev}`,version=++optionsLoadVersion;
 const params=new URLSearchParams({query:optionsQuery,kind:optionsKind,offset:String(optionsOffset),limit:'12'});
 const current=()=>state?.id===wid&&`${state.event_cursor}@${state.rev}`===cursor&&version===optionsLoadVersion;
 try{const value=await api(`/api/workspaces/${wid}/discovery-options?${params}`);if(!current())return;optionsPage=value;optionsWorkspace=wid;optionsCursor=cursor;optionsError=''}catch(e){if(current())optionsError=e.message}if(current())render();
}
async function getOption(id){
 const key=`${state.id}@${state.event_cursor}@${state.rev}`;
 const page=await api(`/api/workspaces/${state.id}/discovery-options?`+new URLSearchParams({query:id,limit:'100'}));
 if(!state||`${state.id}@${state.event_cursor}@${state.rev}`!==key)throw Error('연구가 바뀌었습니다. 현재 연구에서 다시 선택해 주세요.');
 const item=page.rows.find(x=>x.option_id===id);if(!item)throw Error('현재 선택지 목록에서 항목을 확인할 수 없습니다. 목록을 새로 불러와 주세요.');return item;
}
function optionDetail(item){
 const a=item.assessment;
 const drawn=typeof candidateStructureRow==='function'?candidateStructureRow(item.option_id):null;
 const picture=drawn&&structureThumb(drawn)?`<div class="candidate-detail-structure">${structureFigure(drawn.depiction,item.label)}<p class="small muted">${esc(drawn.depiction.formula??'')} · 기록된 구조의 2D 그림</p></div>`:'';
 return `${picture}<p class="small muted">${esc(optionKinds[item.kind])} · ${esc(optionStatus[item.review_status])}</p>${sourceCandidateInfo(item,true)}${rnaOptionContext(item)}${a?`<h3>${esc(discoveryRecordLabel(a))}</h3><p>${judgmentText(researcherWording(a.reason))}</p>${a.priority?`<p class="small">${esc(a.comparison_group)} 안의 ${a.priority}순위</p>`:''}<h3>지지 근거</h3>${sourceLinks(a.support_source_ids)}<h3>반대 근거·적용 조건</h3>${sourceLinks(a.challenge_source_ids)}${list(a.uncertainties)}<h3>다음 확인</h3><p>${esc(researcherWording(a.next_action))}</p>`:'<p>아직 추천 검토를 마치지 않은 항목입니다. 아래 원자료를 보거나 이 경로의 검토를 요청할 수 있습니다.</p>'}${discoveryFirstDescription(item)}<details><summary>발견한 원자료 ${item.sources.length}개</summary>${sourceLinks(item.sources.map(x=>x.artifact_id))}${item.message_id?button('message-source','연구자 원 제안',`data-id="${esc(item.message_id)}"`,'link-button'):''}</details>${item.assessments.length>1?`<details><summary>이전 검토 이력 ${item.assessments.length-1}개</summary>${item.assessments.slice(0,-1).reverse().map(x=>`<p class="small muted">${esc(discoveryRecordLabel(x))} · ${esc(optionStatus[x.status])}</p><p>${esc(x.reason)}</p>${sourceLinks([x.artifact_id])}`).join('')}</details>`:''}<div class="dialog-actions">${button('discovery-choose','이 경로 검토하기',`data-id="${esc(item.option_id)}"`,'primary')}</div>`;
}
async function discoveryAction(action,node){
 if(action==='discovery-example'){
  goalApproach=node.dataset.example;draft=goalApproach==='sirna'?'간에서 만들어지는 TTR를 줄이는 접근이 유전성 ATTR 아밀로이드증에 타당한지 확인하고, 근거가 맞으면 실제 전사체에서 siRNA 후보를 만들어 비교해 주세요.':'유전성 ATTR 아밀로이드증의 축적을 줄이는 기전과 저분자 접근을 비교하고 싶어요. 후보가 없으니 근거로 찾고 실제 계산까지 이어 주세요.';
  evidaStorage.setItem(draftKey(),draft);render();document.querySelector('#message')?.focus();return;
 }
 if(action==='discovery-toggle'){optionsOpen=!optionsOpen;render();if(optionsOpen)await loadOptions();return}
 if(['discovery-search','discovery-prev','discovery-next'].includes(action)){optionsQuery=document.querySelector('#option-query')?.value??optionsQuery;optionsKind=document.querySelector('#option-kind')?.value??optionsKind;optionsOffset=action==='discovery-search'?0:Math.max(0,optionsOffset+(action==='discovery-next'?12:-12));optionsPage=null;render();await loadOptions();return}
 if(action==='discovery-detail'){const item=await getOption(node.dataset.id);if(dialog.open)dialog.close();showDialog(candidateDisplayName(item),optionDetail(item));return}
 if(action==='discovery-choose'||action==='discovery-propose'){
  const propose=action==='discovery-propose';const item=propose?null:await getOption(node.dataset.id);
  if(dialog.open)dialog.close();const active=state.jobs.some(j=>['queued','running'].includes(j.status));
  showDialog(propose?'연구자의 새로운 경로':'검토할 경로 선택',`<p>${propose?'추천 목록에 없는 기전·표적·접근도 제안해 주세요. 근거를 확인하고 다음 작업에 반영합니다.':`${esc(item.label)}를 우선 검토합니다. 기존 추천과 원자료는 그대로 보존합니다.`}</p>${propose?'<label>검토할 경로<input id="option-proposal" maxlength="240" placeholder="예: 다른 기전, 표적 또는 조합 접근"></label>':''}<label>${propose?'아이디어의 근거·조건':'선택 이유 또는 추가 조건'}<textarea id="option-reason" placeholder="선행 지식이나 확인하고 싶은 점을 알려주세요. 모르는 부분은 비워 두어도 됩니다."></textarea></label><p class="small muted">선택·제안 자체가 과학적 타당성을 확정하지는 않습니다.</p>${active?'<p class="notice-inline">진행 중인 검토가 있습니다. 선택을 저장하면(어느 버튼이든) 그 검토는 판단을 내지 않고 ‘이전 조건의 작업’으로 닫힙니다. 모은 자료·계산은 보존되고 다음 검토에서 재사용됩니다. ‘이 경로로 검토 시작’은 새 조건으로 다시 검토하고, ‘선택만 저장’은 새 검토를 시작하지 않습니다. 첫 판단을 먼저 보려면 검토가 끝난 뒤 선택하세요.</p>':''}<div class="dialog-actions">${button('discovery-save','선택만 저장',`data-id="${esc(item?.option_id??'')}" data-proposal="${propose}"`)}${button('discovery-save','이 경로로 검토 시작',`data-id="${esc(item?.option_id??'')}" data-proposal="${propose}" data-review="true" ${!status.gateway.available?'disabled':''}`,'primary')}</div>`);return;
 }
 if(action==='discovery-run'){
  busy=true;node.disabled=true;
  try{
   await api(`/api/workspaces/${state.id}/discovery-select`,{expected_rev:state.rev,
     command_id:crypto.randomUUID(),text:'',option_id:node.dataset.id,review_requested:true});
   if(dialog.open)dialog.close();await refresh();
   notice('이 경로로 검토를 시작했습니다. 기존 추천과 원자료는 그대로 보존됩니다.');
  }finally{busy=false;render()}
  return;
 }
 if(action==='discovery-save'){
  const propose=node.dataset.proposal==='true',text=document.querySelector('#option-reason').value,label=document.querySelector('#option-proposal')?.value;
  busy=true;node.disabled=true;
  try{await api(`/api/workspaces/${state.id}/${propose?'discovery-proposals':'discovery-select'}`,{expected_rev:state.rev,command_id:crypto.randomUUID(),text,label,option_id:node.dataset.id,review_requested:node.dataset.review==='true'});dialog.close();await refresh();notice(node.dataset.review==='true'?'연구자의 경로와 후속 검토를 함께 접수했습니다.':'연구자의 경로와 원래 추천을 함께 보존했습니다.')}finally{busy=false;render()}return;
 }
}
document.addEventListener('change',event=>{if(event.target.name==='goal-approach'){goalApproach=event.target.value;render()}if(event.target.id==='option-kind')optionsKind=event.target.value});
document.addEventListener('input',event=>{if(event.target.id==='option-query')optionsQuery=event.target.value});

function sourceCandidateInfo(item,detail=false){
 if(item.kind!=='source_candidate')return '';
 const modality=({small_molecule:'저분자',sirna:'siRNA 치료 참조',other:'다른 치료 방식',unknown:'치료 방식 확인 중'})[item.modality]??'치료 방식 확인 중';
 const linked=(item.identity_links??[]).filter(x=>x.structure_status==='available');
 const identity=linked.length?'데이터베이스 구조 회수 · 원 시료 대응은 별도 확인':((item.identity_links??[]).length?'구조 조회 결과 미확인 · 원문 후보 보존':item.identity?.lookup_name?'원문 식별명 확보 · 구조 조회 전':'구조 식별 확인 필요');
 const brief=`<p class="small muted">${esc(modality)} · ${item.role==='reference_treatment'?'비교를 위한 치료 참조':'원문 후보'} · ${esc(identity)}</p>`;
 if(!detail)return brief;
 return brief+`<h3>목록에 남긴 이유와 적용 조건</h3>${list(item.conditions)}<p>${esc(item.next_check)}</p>${item.identity?.lookup_name?`<p>원문에서 확인한 조회명: ${esc(item.identity.lookup_name)}</p>`:''}<details><summary>정확한 원문 이름·위치와 식별 이력</summary>${(item.candidate_records??[]).map(x=>`<p>${esc(x.record.mention.row_id??x.record.mention.locator)}</p><blockquote>${esc(x.record.mention.quote)}</blockquote>${sourceLinks([x.record.mention.artifact_id])}`).join('')}${(item.identity_links??[]).map(x=>`<p>${esc(x.candidate_id)} · ${x.structure_status==='available'?'구조 반환':'식별 미확인'}</p>${x.next_identity_check?`<p>${esc(x.next_identity_check)}</p>`:''}${sourceLinks([x.artifact_id])}`).join('')}</details>`;
}


;
/* Source: regulon-activity.js */
// Source-bound expression evidence is a conditional input to the research loop.
function regulonActivityEntry(){
 const sources=state.artifacts.filter(a=>a.kind==='gene_contrast_statistics'||a.meta?.semantic_type==='gene_contrast_statistics');
 return `<details class="panel science-form"><summary>발현 자료가 있다면 · 조절 패턴 비교</summary><p>유전자별 대비 통계를 두 조절망으로 계산해, 함께 남는 설명과 자료에 따라 달라지는 설명을 확인합니다. 원 카운트에서 대비 통계를 만드는 단계는 별도로 필요합니다.</p>${sources.length?`<label>비교할 자료<select id="regulon-source">${sources.map(a=>`<option value="${esc(a.id)}">${esc(a.title)}</option>`).join('')}</select></label>${scienceInput('regulon-focus','관심 전사인자 · 선택 사항','예: IRF1, E2F4')}${button('science-regulon-run','조절 패턴 실제 계산','','primary')}`:'<p class="muted">현재 연구에는 형식과 조건이 확인된 유전자별 대비 통계표가 없습니다. 자료를 추가하고 원래 비교·정규화·유전자 대응을 확인하면 연결할 수 있습니다.</p>'}</details>`;
}

async function regulonActivityAction(action,node){
 if(action!=='science-regulon-run')return;
 node.disabled=true;actionError='';
 try{
  const id=document.querySelector('#regulon-source')?.value;
  const source=state.artifacts.find(a=>a.id===id);const spec=source?.meta?.regulon_input;
  if(!spec)throw Error('원자료의 비교·통계 종류·열 대응을 먼저 확인해 주세요. 임의로 정하지 않았습니다.');
  const focus=(document.querySelector('#regulon-focus')?.value??'').split(/[\s,;]+/).filter(Boolean);
  await runTool('regulon_activity',{source_artifact_ids:[id],...spec,focus_tfs:[...new Set(focus)]});
  notice('발현 자료의 실제 계산을 시작했습니다. 완료 후 근거와 다음 판단에 연결할 수 있습니다.');
 }catch(error){actionError=error.message;notice(error.message)}finally{node.disabled=false;render()}
}

function regulonActivityTable(result){
 const table=rows=>`<div class="table-scroll"><table><thead><tr><th>전사인자</th><th>조절망</th><th>패턴 점수</th><th>자원 내 보정값</th><th>측정된 표적 수</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.source)}</td><td>${esc(r.resource)}</td><td>${number(r.score)}</td><td>${Number(r.BH_resource_family).toExponential(2)}</td><td>${number(r.measured_targets)}</td></tr>`).join('')}</tbody></table></div>`;
 const focus=result.focus_rows??[];
 const gaps=result.unestimated??[];
 return `<section class="regulon-result"><h3>발현 자료가 지지하는 조절 패턴</h3><p>${esc(result.comparison??'')}</p><p>같은 발현 자료를 두 조절망으로 계산한 결과입니다. 점수의 방향과 적용 조건을 비교하며, 그 자체로 치료 표적이나 효능을 확정하지 않습니다.</p>${focus.length?`<h4>관심 전사인자 비교</h4>${table(focus)}`:''}<details><summary>계산에 적용한 조건</summary><ul>${(result.conditions??[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p>${esc(result.method??'')}</p><p>버전: ${esc(JSON.stringify(result.versions??{}))}</p></details><h4>전체 추정 결과 · 현재 읽은 범위</h4>${table(result.rows??[])}${gaps.length?`<details><summary>추정하지 못한 항목 ${gaps.length}개 · 근거 부재와 구분</summary><p>조절망에 없거나 측정된 표적이 부족한 항목입니다. 음성 결과로 분류하지 않습니다.</p><ul>${gaps.slice(0,30).map(x=>`<li>${esc(x.TF)} · ${esc(x.resource)} · ${x.status==='resource_not_present'?'자원에 없음':'측정 표적 수 부족'} (${number(x.measured_targets)})</li>`).join('')}</ul>${gaps.length>30?'<p>나머지 항목도 원 결과에 보존되어 있습니다.</p>':''}</details>`:''}<details><summary>판단에 적용할 범위</summary><ul>${(result.limits??[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details></section>`;
}


;
/* Source: pathway-hypotheses.js */
function pathwayHypothesesEntry(){
 const results=state.artifacts.filter(a=>a.kind==='regulon_activity'&&a.meta?.result_status==='succeeded');
 if(!results.length)return '';
 return `<details class="panel science-form"><summary>조절 패턴을 설명할 경로 찾아보기</summary><p>확인할 전사인자와 선택 이유를 정하면, 알려진 상호작용 안에서 그 패턴을 설명하는 경로 후보를 실제 계산합니다. 계산된 경로가 치료 표적의 입증은 아닙니다.</p><label>사용할 계산 결과<select id="pathway-source">${results.map(a=>`<option value="${esc(a.id)}">${esc(a.title)}</option>`).join('')}</select></label><label>비교할 조절망<select id="pathway-resource"><option value="dorothea">DoRothEA</option><option value="collectri">CollecTRI</option></select></label>${scienceInput('pathway-tfs','확인할 전사인자','예: IRF1, E2F4')}${scienceInput('pathway-reason','이 신호를 함께 보는 이유','예: 두 조절망에서 함께 유지된 패턴을 설명하고 싶다')}${scienceInput('pathway-conditions','해석에 필요한 조건','조직·대조군·관측 또는 추정의 구별')}<label>상류 탐색 범위<select id="pathway-depth"><option value="1">한 연결 앞까지</option><option value="2" selected>두 연결 앞까지</option><option value="3">세 연결 앞까지</option><option value="4">네 연결 앞까지</option></select></label><p class="muted">이번 계산의 범위이며, 바깥에 다른 경로가 없다는 뜻은 아닙니다. 다른 조절망을 비교할 때는 같은 신호·범위를 사용합니다.</p>${button('science-pathway-run','경로 후보 실제 계산','','primary')}</details>`;
}

async function pathwayHypothesesAction(action,node){
 if(action==='science-pathway-section'){
  const id=node.dataset.artifact??selected,section=node.dataset.section,start=Number(node.dataset.offset??0);
  const data=await api(`/api/workspaces/${state.id}/artifacts/${encodeURIComponent(id)}?calculation_section=${encodeURIComponent(section)}&offset=${start}&limit=30`);
  const r=data.result;
  const nav=`data-artifact="${esc(id)}" data-section="${esc(section)}"`;
  const keys=[...new Set(r.rows.flatMap(x=>Object.keys(x.value??{})))];
  const table=`<div class="table-scroll"><table><thead><tr><th>경로 · 원 행</th>${keys.map(k=>`<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${r.rows.map(x=>`<tr><td>${x.network_index?`경로 ${number(x.network_index)} · `:''}${esc(x.source_path.slice(-1)[0])}</td>${keys.map(k=>`<td>${!(k in x.value)?'항목 없음':x.value[k]===null?'미제공 (null)':esc(typeof x.value[k]==='object'?JSON.stringify(x.value[k]):String(x.value[k]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  showDialog(r.section_label,`<p>원 계산표의 선택한 범위입니다. 0과 비선택 행도 보존합니다. 선택 가중치는 인과 확률이나 실측 활성이 아닙니다.</p>${table}<div class="pagination"><span>${r.rows.length?number(start+1):0}–${number(start+r.rows.length)} / ${number(r.total_rows)}행</span><div>${button('science-pathway-section','이전',`${nav} data-offset="${Math.max(0,start-30)}" ${start===0?'disabled':''}`,'small')}${button('science-pathway-section','다음',`${nav} data-offset="${start+30}" ${!r.has_more?'disabled':''}`,'small')}</div></div><details><summary>원 위치와 해시</summary>${json({artifact_id:id,sha256:data.source_sha256,rows:r.rows})}</details>`);
  return;
 }
 if(action!=='science-pathway-run')return;
 node.disabled=true;
 try{
  const value=id=>document.getElementById(id)?.value.trim()??'';
  const reason=value('pathway-reason'),condition=value('pathway-conditions');
  if(!reason||!condition)throw Error('선택 이유와 해석 조건을 적어 주세요. 빈 조건을 자동으로 정하지 않습니다.');
  const args={artifact_id:value('pathway-source'),resource:value('pathway-resource'),
   tf_ids:[...new Set(value('pathway-tfs').split(/[\s,;]+/).filter(Boolean))],selection_reason:reason,
   ancestor_steps:Number(value('pathway-depth')),conditions:[condition]};
  await runTool('pathway_hypotheses',args);notice('관측을 설명할 경로 후보를 계산하고 있습니다. 기존 판단은 유지합니다.');
 }catch(error){actionError=error.message;notice(error.message)}finally{node.disabled=false;render()}
}

function pathwayHypothesesTable(result){
 const real=(result.rows??[]).filter(r=>!r.artificial_root_edge),artificial=(result.rows??[]).filter(r=>r.artificial_root_edge);
 const rows=items=>`<div class="table-scroll"><table><thead><tr><th>후보 경로</th><th>앞선 요소</th><th>관계</th><th>다음 요소</th></tr></thead><tbody>${items.map(r=>`<tr><td>${number(r.network_index)}</td><td>${esc(r.source)}</td><td>${r.sign===1?'활성 방향':'억제 방향'}</td><td>${esc(r.target)}</td></tr>`).join('')}</tbody></table></div>`;
 return `<section class="pathway-result"><h3>조절 패턴을 설명하는 경로 후보</h3><p>${esc(result.selection_reason??'')}</p><p>계산에 사용한 추정 신호: ${(result.selected_inferred_observations??[]).map(x=>`${esc(x.source)} (${number(x.score)})`).join(', ')}</p>${rows(real)}<p>고정 상호작용 ${number(result.search_scope?.full_prior_edges)}개 중 이번 범위의 ${number(result.search_scope?.selected_prior_edges)}개를 사용했습니다. 계산 범위 밖은 미탐색입니다.</p><p>${result.solver_review?.optimal_reported?'이 범위의 목적함수에서 최적해가 보고됐습니다. 유일한 생물학적 설명을 뜻하지는 않습니다.':'최적성 확인이 끝나지 않은 계산 결과입니다. 실행 조건을 먼저 검토합니다.'}</p><details><summary>계산 조건과 해석 범위</summary><ul>${[...(result.source_conditions??[]),...(result.conditions??[]),...(result.limits??[])].map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p>${esc(result.method??'')} · ${esc(JSON.stringify(result.versions??{}))}</p></details>${(result.calculation_sections??[]).length?`<details class="calculation-section-navigation"><summary>전체 계산표에서 필요한 범위 확인</summary><p>기본 화면은 반환된 경로를 보여줍니다. 내부 표는 필요할 때 열 수 있으며 원자료에서 삭제하지 않습니다.</p>${result.calculation_sections.map(x=>button('science-pathway-section',`${x.label} · ${number(x.total_rows)}행`,`data-section="${esc(x.section)}" data-offset="0"`,'small')).join('')}</details>`:''}${artificial.length?`<details><summary>최적화의 가상 시작점 · 실제 원인과 구별</summary><p>Perturbation은 최적화 표현입니다. 실제 약물이나 원인으로 확정하지 않습니다.</p>${rows(artificial)}</details>`:''}</section>`;
}


;
/* Source: science-workbench.js */
// Optional scientific entry points. A displayed stage is not a completed claim.
const SCIENCE_LABELS={pathway_hypotheses:'관측을 설명하는 경로 후보',regulon_activity:'발현 자료의 조절 패턴',gene_contrast_statistics:'유전자별 대비 통계',disease_targets:'질환–표적 근거',target_disease_evidence:'개별 표적 근거',chembl_search:'표적·화합물 식별',bioactivities:'보고 활성·실험 조건',binding_pose_review:'포즈 순위·기준 구조 비교',target_structure:'표적 구조·결합 부위',molecular_docking:'결합 포즈 계산',rna_reference:'RNA 전사체·참조',rna_sequence_evaluation:'RNA 서열·접근성',rna_candidate_generation:'RNA 결합 영역 후보'};
Object.assign(SCIENCE_LABELS,{rna_seed_sites:'3′UTR seed·간 발현',rna_chemistry_evidence:'수식·안정성·조직 노출 근거',rna_reference_archive:'보존 참조 · 판본 명시',rna_transcriptome_search:'전체 전사체 상호작용',rna_author_full:'전체 ENsiRNA · 조건부 core 점수',rna_activity_score:'탐색용 활성 모델 점수',rna_delivery_simulation:'전달·시간경과 모형'});
let scienceScope='evidence';
const scienceDrafts=new Map();
function scienceDraft(){const key=state?.id??'new';if(!scienceDrafts.has(key))scienceDrafts.set(key,{});return scienceDrafts.get(key)}
function scienceValue(id,fallback=''){return esc(scienceDraft()[id]??fallback)}
document.addEventListener('input',e=>{if(e.target.matches('[data-science-input]'))scienceDraft()[e.target.id]=e.target.value});
document.addEventListener('change',e=>{if(e.target.matches('[data-science-input]'))scienceDraft()[e.target.id]=e.target.value;if(e.target.id==='dock-csv')loadDockCandidates(e.target.value).catch(e=>notice(e.message))});
function scienceInput(id,label,placeholder,value=''){return `<label>${esc(label)}<input id="${id}" data-science-input value="${scienceValue(id,value)}" placeholder="${esc(placeholder)}"></label>`}
function scienceOptions(kind){return state.artifacts.filter(a=>a.kind===kind).map(a=>`<option value="${a.id}">${esc(a.title)}</option>`).join('')}
function scienceRecent(){const groups={evidence:['pathway_hypotheses','regulon_activity','gene_contrast_statistics','lens_literature','gtopdb_pharmacology',...CLINICAL_SOURCE_KINDS,'target_context','entity_search','disease_targets','target_disease_evidence','intervention_direction_audit','chembl_search','bioactivities','literature'],binding:['kinetic_conditions','exposure_requirements','research_evidence','target_structure','molecular_docking','binding_pose_review','molecule_csv','admet'],rna:['rna_author_mod','chemical_sirna_evidence','research_evidence','rna_duplex','rna_duplex_seed','rna_duplex_transcriptome','rna_region_annotation','rna_delivery_response','rna_tissue_context','rna_variant_catalog','rna_allele_scenario','rna_candidate_space','rna_reference_panel','rna_seed_sites','rna_chemistry_evidence','rna_reference','rna_reference_archive','rna_transcriptome_search','rna_activity_score','rna_author_full','rna_delivery_simulation','rna_sequence_evaluation','rna_candidate_generation','rna_seed_analysis','rna_table']};const items=state.artifacts.filter(a=>groups[scienceScope].includes(a.kind)).slice(-6).reverse();return `<section class="science-results"><h2>이 연구에서 얻은 자료와 결과</h2>${items.length?items.map(a=>`<button data-action="source" data-id="${a.id}" class="science-result"><span><small>${esc(SCIENCE_LABELS[a.kind]??labels[a.kind])}</small><strong>${esc(artifactName(a.id))}</strong></span><span>${a.meta.result_status?esc(jobLabels[a.meta.result_status]??a.meta.result_status):'원자료'} →</span></button>`).join(''):'<p class="muted">위에서 조회하거나 자료를 넣으면 결과가 여기에 나타납니다.</p>'}<p class="limit">결과를 열면 조건·단위·원행과 다음 작업을 확인할 수 있습니다. 계산 완료가 가설의 입증을 뜻하지는 않습니다.</p></section>`}
function renderScienceWorkbench(){
 const groups=[['evidence','기전과 표적','질환에서 근거와 접근 찾기'],['binding','저분자 결합','구조·활성·포즈 함께 보기'],['rna','RNA 서열','참조와 후보를 실제 계산하기']];
 // Rendered inside the 자료 tab's "직접 조회" drawer, which already says what this is for, so the
 // former full-page intro and its tab jump are gone. The job list lives in 변경 기록.
 return `<p class="small muted">질환부터 시작해도, 이미 가진 후보나 관측에서 시작해도 됩니다. 결과와 맞지 않는 가정은 연구 탭에서 다시 검토합니다.</p><nav class="science-paths" aria-label="과학 작업 종류">${groups.map(([id,title,desc])=>button('science-scope',`<strong>${title}</strong><span>${desc}</span>`,`data-scope="${id}" aria-pressed="${scienceScope===id}"`,`science-path ${scienceScope===id?'active':''}`)).join('')}</nav><div class="science-columns"><div>${scienceScope==='evidence'?(scienceEvidenceForm()+regulonActivityEntry()+pathwayHypothesesEntry()+lensEntry()+gtopdbEntry()+clinicalSourcesEntry()+targetContextEntry()):scienceScope==='binding'?scienceBindingForm():scienceRnaForm()}</div><div>${scienceRecent()}</div></div>`;
}
function scienceEvidenceForm(){return `<section class="panel science-form"><h3>질환·표적 이름에서 시작</h3><p>정확한 대상과 질환 범위를 먼저 확인합니다. 결과의 이름을 누르면 표적 근거 또는 RNA 참조로 이어집니다.</p>${scienceInput('science-name','공개 질환명 또는 유전자명','예: transthyretin amyloidosis, TTR')}<div class="detail-actions">${button('science-find-disease','질환 찾기',busy?'disabled':'','primary small')}${button('science-find-target','표적 찾기',busy?'disabled':'','small')}</div></section><section class="panel science-form"><h3>보고된 화합물·표적 활성 확인</h3><p>실험의 종류·종·단위·측정 조건을 함께 확인합니다.</p>${scienceInput('science-chembl-name','공개 화합물 또는 표적 이름','예: tafamidis, transthyretin')}<div class="detail-actions">${button('science-find-molecule','화합물 찾기',busy?'disabled':'','small')}${button('science-find-chembl-target','활성 DB의 표적 찾기',busy?'disabled':'','small')}</div></section>`}
function scienceBindingForm(){return `<section class="panel science-form"><h3>1. 표적 구조와 결합 부위 확인</h3><p>PDB의 생물학적 조립체를 받아 실제 사슬과 공결정 성분을 확인합니다. 구조를 열고 평가할 부위를 선택하세요.</p><div class="science-fields">${scienceInput('science-pdb','PDB ID','예: 6E6Z')}${scienceInput('science-assembly','조립체 번호','1','1')}</div>${button('science-structure','구조·부위 가져오기',busy?'disabled':'','primary small')}<p class="limit">표적 이름만으로 도메인·변이·상태가 같은 구조라고 판단하지 않습니다.</p></section><section class="panel science-form"><h3>2. 후보와 구조를 연결해 포즈 계산</h3><p>후보 ID와 SMILES가 있는 CSV를 올리고, 받은 구조의 부위에서 계산할 후보를 고릅니다.</p>${button('upload','후보 CSV 올리기','','small')}<p class="limit">현재는 알려진 공결정 부위의 rigid docking을 지원합니다. 점수와 포즈 검사는 실제 활성·선택성 측정을 대체하지 않습니다.</p></section><section class="panel"><h3>3. 측정 근거와 불일치 확인</h3><p>포즈 결과를 활성 기록·용해도·실험 조건과 대조하세요. 맞지 않으면 후보뿐 아니라 구조 상태·시료·측정 가정도 다시 검토할 수 있습니다.</p>${button('science-scope','활성·표적 근거 찾기','data-scope="evidence"','small')}</section>`}
function scienceRnaForm(){const refs=state.artifacts.filter(a=>['rna_reference','rna_reference_archive'].includes(a.kind)&&a.meta.summary?.requires_transcript_selection===false);return `<section class="panel science-form"><h3>1. 종·isoform·버전 확인</h3><p>유전자이면 전사체 목록, 전사체이면 실제 cDNA 서열을 받습니다. 이름만 안다면 기전과 표적에서 검색하세요.</p>${scienceInput('science-ensembl','Ensembl 유전자 또는 전사체','예: ENSG00000118271')}<label>참조 자료<select id="science-reference-source" data-science-input><option value="archive">인간 Ensembl115 · GRCh38 보존 참조</option><option value="archive116" ${scienceDraft()['science-reference-source']==='archive116'?'selected':''}>인간 Ensembl116 · GRCh38 보존 참조</option><option value="live" ${scienceDraft()['science-reference-source']==='live'?'selected':''}>Ensembl 현재 REST · 종/버전 확인</option></select></label>${button('science-reference','참조 확인하기',busy?'disabled':'','primary small')}</section><section class="panel science-form"><h3>2. 실제 서열에서 후보 찾기</h3><p>전체 구간에서 후보를 찾고, 확인할 후보를 골라 계산할 수 있습니다.</p>${button('science-space-dialog','전체 구간에서 후보 찾기',busy?'disabled':'','primary small')}<details><summary>이미 가진 가이드·특정 구간만 계산</summary><label>계산할 전사체<select id="science-rna-ref" data-science-input><option value="">참조를 먼저 선택하세요</option>${refs.map(a=>`<option value="${a.id}" ${scienceDraft()['science-rna-ref']===a.id?'selected':''}>${esc(a.title)}</option>`).join('')}</select></label><label>RNA 수식 상태<select id="science-chemistry" data-science-input><option value="unknown">미확인 · 무수식 서열 근사</option><option value="unmodified" ${scienceDraft()['science-chemistry']==='unmodified'?'selected':''}>무수식 RNA</option><option value="modified" ${scienceDraft()['science-chemistry']==='modified'?'selected':''}>수식 있음 · 무수식 서열 근사</option></select></label><details open><summary>내 가이드 서열 계산</summary><label>5′→3′ 가이드 · 한 줄에 하나<textarea id="science-guides" data-science-input placeholder="ACGU…">${scienceValue('science-guides')}</textarea></label>${button('science-evaluate-guides','표적 대응·접근성 계산',busy?'disabled':'','small')}</details><details><summary>선택 구간에서 결합 영역 후보 만들기</summary><div class="science-fields">${scienceInput('science-rna-start','시작 위치 · 1부터','100','100')}${scienceInput('science-rna-count','후보 수','5','5')}${scienceInput('science-rna-length','짝지을 길이 · nt','21','21')}${scienceInput('science-rna-stride','후보 간격 · nt','10','10')}</div>${button('science-generate-rna','후보 생성·실제 계산',busy?'disabled':'','small')}<p class="limit">지정 구간의 역상보 후보입니다. 효능 순위나 overhang·수식·전달을 갖춘 완성 siRNA 설계가 아닙니다.</p></details><p class="limit">접힘·국소 접근성·정확 서열 대응을 계산합니다. 아래에서 전체 전사체 상호작용과 별도 학습 모델을 확인할 수 있습니다. 분해 안정성과 조직 전달은 실제 화학·제형 조건에 맞는 근거가 필요합니다.</p></details></section><section class="panel science-form"><h3>3. 후보별 활성·비표적 검토</h3><p>전사체 대응 결과에서 조직별 발현을 연결하고, 공개 변이 조건에 따라 후보를 다시 비교할 수 있습니다.</p>${button('science-context-variant-dialog','참조의 공개 변이 찾기','','small')}<p>완료한 후보 결과를 열면 전체 전사체·seed 검색과 탐색용 활성 모델을 실행할 수 있습니다. 활성 모델은19nt만 지원하며 긴 서열을 자동 자르지 않습니다.</p><p class="limit">두 계산은 서로 다른 질문에 답합니다. 높은 서열 점수를 전달 성공이나 안전성으로 해석하지 않습니다.</p></section>${chemicalSourceEntry()}${scienceDeliveryForm()}${deliveryResponseEntry()}`}
async function openDocking(structureId,siteId){showDialog('선택한 부위에서 후보 포즈 계산',`<p class="small">부위 ${esc(siteId)} · 원 구조와 후보의 전하/성분은 보존합니다. 점수는 새 친화도 측정이 아닙니다.</p><label>후보 CSV<select id="dock-csv"><option value="">후보 자료 선택</option>${scienceOptions('molecule_csv')}</select></label><div id="dock-candidates" class="dock-candidates"></div><div class="science-fields"><label>탐색량<select id="dock-effort"><option value="8">8 · 첫 탐색</option><option value="16" selected>16</option><option value="32">32 · 더 넓은 탐색</option></select></label><label>초기 구조·탐색 공통 시드<input id="dock-seed" value="20260925" type="number"></label></div><div class="dialog-actions">${button('science-run-docking','선택 후보 실제 계산',`data-structure="${esc(structureId)}" data-site="${esc(siteId)}"`,'primary')}</div>`)}
async function loadDockCandidates(id){const box=document.querySelector('#dock-candidates');if(!id){box.textContent='';return}const value=await api(`/api/workspaces/${state.id}/artifacts/${id}?limit=100`);const r=value.result;box.innerHTML=`<p class="small">계산할 후보를 최대12개 고르세요. ${r.has_more?'앞100행을 표시합니다. 더 큰 목록은 조건으로 선별한 뒤 요청하세요.':''}</p>${r.rows.map(x=>`<label><input type="checkbox" name="dock-candidate" value="${esc(x.candidate_id??'')}" ${!x.candidate_id||!x.width_matches?'disabled':''}> ${esc(x.candidate_id??'ID 없음')} <small>${esc(x.smiles??'구조 없음')}</small></label>`).join('')}`}
async function scienceAction(action,node){
 if(action.startsWith('science-pathway-')){await pathwayHypothesesAction(action,node);return}
 if(action.startsWith('science-regulon-')){await regulonActivityAction(action,node);return}
 if(action.startsWith('science-lens-')){await lensAction(action,node);return}
 if(action.startsWith('science-gtopdb-')){await gtopdbAction(action,node);return}
 if(action.startsWith('science-target-context-')){await targetContextAction(action,node);return}
 if(action.startsWith('science-clinical-')){await clinicalSourceAction(action,node);return}
 if(action.startsWith('science-author-mod-')){await authorModAction(action,node);return}
 if(action.startsWith('science-duplex-')||action.startsWith('science-response-')||action.startsWith('science-region-')){await duplexAction(action,node);return}
 if(action.startsWith('science-pose-')){await bindingPoseAction(action,node);return}
 if(action.startsWith('science-context-')){await rnaContextAction(action,node);return}
 if(action.startsWith('science-space-')){await candidateSpaceAction(action,node);return}
 if(action==='science-direction-dialog'||action==='science-run-direction-audit'){await interventionDirectionAction(action,node);return}
 if(action==='science-reference-panel'||action==='science-run-reference-panel'){await referencePanelAction(action,node);return}
 if(action==='science-view-structure'){await openMoleculeView(node.dataset.id,node.dataset.candidate);return}

 if(action==='science-scope'){scienceScope=node.dataset.scope;tab='data';render();return}
 if(action==='science-select-rna-gene'){scienceDraft()['science-ensembl']=node.dataset.id;scienceScope='rna';tab='data';render();return}
 if(action==='science-candidate-followup'){await openRnaFollowup(node.dataset.id,node.dataset.tool);return}
 if(action==='science-dock-dialog'){await openDocking(node.dataset.structure,node.dataset.site);return}
 if(action==='science-use-reference'){scienceDraft()['science-rna-ref']=node.dataset.id;scienceScope='rna';tab='data';render();return}
 busy=true;node.disabled=true;actionError='';
 const val=id=>document.getElementById(id)?.value.trim()??'';
 try{
  let tool,args;
  if(action==='science-find-disease'||action==='science-find-target'){tool='entity_search';args={query:val('science-name'),entity:action==='science-find-disease'?'disease':'target',page:0}}
  if(action==='science-find-molecule'||action==='science-find-chembl-target'){tool='chembl_search';args={query:val('science-chembl-name'),entity:action==='science-find-molecule'?'molecule':'target',page:0}}
  if(action==='science-disease-targets'){tool='disease_targets';args={disease_id:node.dataset.id,page:0,include_descendants:false}}
  if(action==='science-pair-evidence'){tool='target_disease_evidence';args={target_id:node.dataset.target,disease_id:node.dataset.disease,cursor:''}}
  if(action==='science-activities'){tool='bioactivities';args={target_chembl_id:node.dataset.target??'',molecule_chembl_id:node.dataset.molecule??'',page:0}}
  if(action==='science-structure'){tool='target_structure';args={pdb_id:val('science-pdb'),assembly_id:Number(val('science-assembly'))}}
  if(action==='science-reference'||action==='science-fetch-reference'){const source=node.dataset.source??val('science-reference-source');tool=source==='archive116'?'rna_reference_release':source==='archive'?'rna_reference_archive':'rna_reference';args={ensembl_id:node.dataset.id??val('science-ensembl'),...(source==='archive116'?{release:116}:{})}}
  if(action==='science-run-docking'){tool='molecular_docking';args={artifact_id:val('dock-csv'),structure_id:node.dataset.structure,site_id:node.dataset.site,candidate_ids:[...dialog.querySelectorAll('[name="dock-candidate"]:checked')].map(x=>x.value),exhaustiveness:Number(val('dock-effort')),seed:Number(val('dock-seed'))};if(!args.artifact_id||!args.candidate_ids.length||args.candidate_ids.length>12)throw Error('후보 CSV에서 1–12개를 선택해 주세요.')}
  if(action==='science-evaluate-guides'){tool='rna_sequence_evaluation';args={artifact_id:val('science-rna-ref'),chemistry:val('science-chemistry'),guides:val('science-guides').split(/\r?\n/).filter(x=>x.trim()).map((x,i)=>({id:`guide-${i+1}`,guide_5to3:x.trim()}))};if(!args.artifact_id||!args.guides.length)throw Error('전사체와 가이드 서열을 먼저 선택해 주세요.')}
  if(action==='science-generate-rna'){tool='rna_candidate_generation';args={artifact_id:val('science-rna-ref'),chemistry:val('science-chemistry'),start_1_based:Number(val('science-rna-start')),count:Number(val('science-rna-count')),paired_length:Number(val('science-rna-length')),stride:Number(val('science-rna-stride'))};if(!args.artifact_id)throw Error('계산할 실제 전사체 서열을 먼저 선택해 주세요.')}
  if(action==='science-run-rna-followup'){tool=node.dataset.tool;args={artifact_id:node.dataset.id,candidate_ids:[...dialog.querySelectorAll('[name="rna-candidate"]:checked')].map(x=>x.value)};if(!args.candidate_ids.length||args.candidate_ids.length>12)throw Error('1–12개 후보를 선택해 주세요.');if(tool==='rna_activity_score')args.reference_id=node.dataset.reference;else if(tool==='rna_author_full'){if(args.candidate_ids.length>3)throw Error('구조 계산은 한 번에1–3개를 선택해 주세요.');args.reference_id=val('rna-author-reference');args.representation='unmodified_19nt_blunt_core_proxy';}else if(tool==='rna_transcriptome_search')args.energy_cutoff_kcal_mol=Number(val('rna-energy-cutoff'))}
  if(action==='science-chemical-source'){tool='chemical_sirna_evidence';args={gene:val('science-chemical-gene')}}
  if(action==='science-chemistry-evidence'){tool='rna_chemistry_evidence';args={study:'Nair2017_GalNAc'}}
  if(action==='science-delivery-paper'){tool='article';args={pmc_id:node.dataset.pmc}}
  if(action==='science-delivery'){tool='rna_delivery_simulation';args={dose_mg_kg:Number(val('delivery-dose')),escape_multiplier:Number(val('delivery-escape')),protein_turnover_multiplier:Number(val('delivery-turnover'))}}
  if(action==='science-review'){await api(`/api/workspaces/${state.id}/commands`,{expected_rev:state.rev,command_id:crypto.randomUUID(),body:{kind:'message',text:`새로 얻은 ${artifactName(node.dataset.id)} (${node.dataset.id}) 결과를 현재 목표와 가설에 연결해 검토해 주세요. 어떤 가정이 유지되거나 다시 확인되어야 하는지, 계산·문헌·관측의 조건 차이를 설명하고 다음 확인을 제안해 주세요.`,synthetic:false}});await refresh();tool='planner';args={};tab='research'}
  if(action==='science-next-page'){tool=node.dataset.tool;args=JSON.parse(node.dataset.args)}
  if(!tool)throw Error('작업을 확인해 주세요.');
  await runTool(tool,args);dialog.close();notice('실제 작업을 시작했습니다. 완료되면 근거·결과와 실행 기록에서 확인할 수 있습니다.');
 }catch(error){actionError=error.message;notice(error.message)}finally{busy=false;render()}
}
function scienceTable(result,kind){
 if(kind==='pathway_hypotheses')return pathwayHypothesesTable(result);
 if(kind==='regulon_activity')return regulonActivityTable(result);
 if(kind==='exposure_requirements')return exposureRequirementsTable(result);
 if(kind==='kinetic_conditions')return kineticConditionsTable(result);
 if(kind==='lens_literature')return lensTable(result);
 if(kind==='gtopdb_pharmacology')return gtopdbTable(result);
 if(kind==='target_context')return targetContextTable(result);
 if(CLINICAL_SOURCE_KINDS.includes(kind))return clinicalSourceTable(result,kind);
 if(kind==='analogue_proposal')return proposalTable(result);
 if(kind==='rna_author_mod')return authorModTable(result);
 if(kind==='rna_duplex')return duplexTable(result);
 if(kind==='rna_duplex_seed')return duplexSeedTable(result);
 if(kind==='rna_duplex_transcriptome')return duplexLongTable(result);
 if(kind==='rna_delivery_response')return deliveryResponseTable(result);
 if(kind==='binding_pose_review')return bindingPoseTable(result);
 if(kind==='intervention_direction_audit')return interventionDirectionTable(result);
 if(kind==='rna_reference_panel')return rnaReferencePanelTable(result);
 if(kind==='rna_candidate_space')return rnaCandidateSpaceTable(result);
 if(kind==='rna_tissue_context')return rnaTissueTable(result);
 if(kind==='rna_variant_catalog')return rnaVariantTable(result);
 if(kind==='rna_allele_scenario')return rnaAlleleTable(result);
 let columns,values;
 if(kind==='entity_search'){columns=['대상 이름','식별자','다음 작업'];values=r=>[esc(r.name),esc(r.id),r.entity==='disease'?button('science-disease-targets','이 질환의 표적 근거',`data-id="${esc(r.id)}"`,'small'):button('science-select-rna-gene','RNA 참조 선택',`data-id="${esc(r.id)}"`,'small')]}
 if(kind==='disease_targets'){columns=['표적','DB 연관 점수','출처별 구성','다음 확인'];values=r=>[esc(r.target.approvedSymbol),number(r.score),esc(r.datatypeScores.map(s=>s.id).join(', ')),button('science-pair-evidence','개별 근거 읽기',`data-target="${esc(r.target.id)}" data-disease="${esc(result.disease.id)}"`,'small')]}
 if(kind==='target_disease_evidence'){columns=['근거 출처','약물','DB 방향 표기','실험·모형·코호트','원전'];values=r=>[esc(r.datasourceId),esc(r.drug?.name??r.drug?.id??'약물 근거 아님'),esc([r.directionOnTarget,r.directionOnTrait].filter(Boolean).join(' / ')||'미제공'),esc(r.studyOverview??r.cohortDescription??r.biologicalModelId??r.clinicalStage??'조건 원전 확인'),(r.literature??[]).map(id=>`<a href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(id)}/" target="_blank" rel="noopener noreferrer">${esc(id)}</a>`).join(' ')]}
 if(kind==='chembl_search'){columns=['이름','식별자','종·유형','실제 활성'];values=r=>[esc(r.pref_name??'이름 미제공'),esc(r.target_chembl_id??r.molecule_chembl_id),esc([r.organism,r.target_type,r.molecule_type].filter(Boolean).join(' · ')),button('science-activities','측정 기록 읽기',r.target_chembl_id?`data-target="${esc(r.target_chembl_id)}"`:`data-molecule="${esc(r.molecule_chembl_id)}"`,'small')]}
 if(kind==='bioactivities'){columns=['화합물 / 표적','측정값·단위','실험','적용 조건'];values=r=>[esc((r.molecule_pref_name??r.molecule_chembl_id)+' / '+r.target_pref_name),esc([r.standard_type,r.standard_relation,r.standard_value,r.standard_units].filter(x=>x!==null&&x!==undefined).join(' ')),esc(r.assay_description??''),esc([r.target_organism,r.assay_type,r.bao_label,r.data_validity_comment,r.assay_context?.confidence_description].filter(Boolean).join(' · '))]}
 if(kind==='target_structure'){columns=['사슬 / 성분','좌표 정보','조건','다음 작업'];values=r=>r.kind==='protein_chain'?[esc(r.chain+' · 단백질'),`${r.modeled_residues}개 잔기`,esc(r.internal_numbering_gaps.length?'내부 번호 공백 있음':'내부 번호 연속'),'']: [esc(r.ligand_id),`${r.heavy_atoms}개 중원자`,esc('점유율 '+r.occupancies.join(', ')),r.heavy_atoms>=6?button('science-dock-dialog','이 부위에서 계산',`data-structure="${esc(selected)}" data-site="${esc(r.ligand_id)}"`,'small'):'부위 조건 확인']}
 if(kind==='molecular_docking'){columns=['후보','실행 상태','Vina 점수 · kcal/mol','포즈 점검'];values=r=>[esc(r.candidate_id),esc(r.status==='succeeded'?'계산 완료':r.error),number(r.vina_score_kcal_mol),r.posebusters?button('row','기하·충돌 검사 보기',`data-index="${result.rows.indexOf(r)}"`,'small')+button('science-view-structure','구조로 보기',`data-id="${esc(selected)}" data-candidate="${esc(r.candidate_id)}"`,'small'):'미완료']}
 if(['rna_reference','rna_reference_archive'].includes(kind)){columns=result.summary.requires_transcript_selection?['전사체','주석','버전','다음 작업']:['서열 위치','5′→3′ 서열'];values=r=>result.summary.requires_transcript_selection?[esc(r.display_name??r.transcript_id),esc(r.biotype)+(r.canonical_annotation?' · canonical':''),esc(r.version),button('science-fetch-reference','이 전사체 받기',`data-id="${esc(r.transcript_id+'.'+r.version)}" data-source="${kind==='rna_reference_archive'?(result.source?.release===116?'archive116':'archive'):'live'}"`,'small')]:[`${r.start_1_based}–${r.end_1_based}`,`<code class="sequence-text">${esc(r.sequence_5to3)}</code>`]}
 if(['rna_sequence_evaluation','rna_candidate_generation'].includes(kind)){columns=['후보 · 5′→3′','표적 대응','guide MFE · kcal/mol','표적 접근성','계산 의미'];values=r=>[esc(r.id)+`<code class="sequence-text">${esc(r.guide_5to3)}</code>`,esc(r.perfect_match_count+'개'),number(r.guide_mfe_kcal_mol),r.perfect_complementary_sites.map(s=>`${s.start_1_based}–${s.end_1_based}: ${number(s.unpaired_probability)}`).join('<br>')||'대응 부위 없음',esc(r.calculation_scope==='unmodified_RNA_model'?'무수식 RNA 모형':'무수식 서열 근사 · 실제 수식 미반영')]}
 if(kind==='rna_author_full'){columns=['후보','저자 체크포인트','조건부 원점수','계산 표현'];values=r=>[esc(r.candidate_id),esc(r.checkpoint),number(r.raw_model_score),esc('비수식19nt blunt core · 효능/확률 아님')]}
 if(kind==='rna_activity_score'){columns=['후보','RNA-FM+ridge','단순3mer+ridge','적용 조건'];values=r=>[esc(r.id),number(r.rna_fm_ridge_score),number(r.sequence3mer_ridge_score),esc('19nt · '+(r.chemistry==='unmodified'?'무수식':'수식 미반영')+' · 성공확률 아님')]}
 if(kind==='rna_transcriptome_search'){columns=['후보 / 대응 유전자','전사체','정렬 위치·에너지','구분'];values=r=>[esc(r.candidate_id)+'<br>'+esc(r.gene_symbol??r.gene_id),esc(r.transcript_id),esc(r.target_start_1_based+'–'+r.target_end_1_based+' · '+r.energy_kcal_mol+' kcal/mol'),r.index_strand==='-'?'합성 역상보 색인 · 실제 전사체로 세지 않음':r.same_selected_transcript?'선택한 표적 전사체':r.same_target_gene?'표적의 다른 isoform':'다른 유전자 · 발현/억제 미확인']}
 if(kind==='rna_seed_sites'){columns=['후보 · 유전자','전사체 · site','3′UTR 위치','간 발현 · 유전자 medianTPM'];values=r=>[esc(r.candidate_id)+'<br>'+esc(r.gene_symbol??r.gene_id),esc(r.transcript_id)+'<br>'+esc(r.site_type),esc(r.utr_start_1_based+'–'+r.utr_end_1_based),r.liver_median_tpm===null?'미대응/모호 · 원행 확인':number(r.liver_median_tpm)+' · isoform 발현 미확인']}
 if(kind==='rna_delivery_simulation'){columns=['시간 · h','혈장 · ng/mL','간 · ng/g','RISC · ng/g','mRNA 잔존 %','단백질 잔존 %'];values=r=>[number(r.time_h),number(r.plasma_sirna_ng_ml),number(r.liver_sirna_ng_g),number(r.RISC_bound_sirna_ng_g),number(r.mrna_percent_remaining),number(r.protein_percent_remaining)]}
 if(kind==='rna_chemistry_evidence'){columns=['화학/경로·조직','원 측정량','원값','조건/주의'];values=r=>[esc(r.molecule+' · '+r.route+' · '+r.tissue),esc(r.metric_original),esc(r.reported_value_original),esc(r.quality_flag??'mouse · 10mg/kg · Atto-probe')]}
 if(!columns)return null;
 const table=`<div class="table-scroll"><table><thead><tr>${columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${result.rows.map((r,i)=>`<tr>${values(r).map((v,j)=>`<td>${j===0?button('row',v,`data-index="${i}"`,'link-button small'):v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
 let next='';
 if(result.summary?.has_more){let tool,args;if(kind==='disease_targets'){tool=kind;args={disease_id:result.disease.id,page:result.summary.page+1,include_descendants:result.summary.include_descendants}}if(kind==='chembl_search'){tool=kind;args={query:result.summary.query,entity:result.summary.entity,page:result.summary.page+1}}if(kind==='bioactivities'){tool=kind;args={target_chembl_id:result.filters.target_chembl_id??'',molecule_chembl_id:result.filters.molecule_chembl_id??'',page:result.summary.page+1}}if(tool)next=button('science-next-page','공개 DB 다음 페이지',`data-tool="${tool}" data-args="${esc(JSON.stringify(args))}"`,'small')}
 if(kind==='target_disease_evidence'&&result.summary.next_cursor)next=button('science-next-page','근거 다음 페이지',`data-tool="target_disease_evidence" data-args="${esc(JSON.stringify({disease_id:result.summary.disease_id,target_id:result.summary.target_id,cursor:result.summary.next_cursor}))}"`,'small');
 return `${kind==='rna_author_full'?button('science-author-mod-open','이 core의 수식·위치 비교',`data-id="${esc(selected)}"`,'primary small'):''}${['rna_sequence_evaluation','rna_candidate_generation'].includes(kind)?duplexEntry():''}${kind==='molecular_docking'?bindingPoseEntry(result):''}${result.selection?rnaSelectedCandidateSummary(result):''}${kind==='target_disease_evidence'?button('science-direction-dialog','약물 작용 방식 함께 확인',`data-id="${esc(selected)}"`,'primary small'):''}${['rna_sequence_evaluation','rna_candidate_generation'].includes(kind)?button('science-reference-panel','다른 전사체와 비교',`data-id="${esc(selected)}"`,'small'):''}${kind==='target_structure'?button('science-view-structure','구조 회전·확대해서 보기',`data-id="${esc(selected)}"`,'small'):''}${['rna_reference','rna_reference_archive'].includes(kind)&&!result.summary.requires_transcript_selection?`<p class="small">${esc(result.reference.organism)} · ${esc(result.reference.transcript_id)}.${esc(result.reference.version)} · ${esc(result.reference.assembly)}${result.reference.release?` · Ensembl${esc(result.reference.release)}`:''}</p>${button('science-use-reference','이 서열로 후보 계산',`data-id="${esc(selected)}"`,'primary small')}${button('science-context-variant-dialog','이 참조의 변이 조건 보기',`data-reference="${esc(selected)}"`,'small')}`:''}${kind==='rna_author_full'?'<p class="notice-inline">새 RNAplex/Rosetta 구조와 RNA-FM·저자5GNN을 실제 실행했습니다. 원 후보의 수식·돌출부·제형을 반영한 효능이 아닙니다. 각 체크포인트 점수를 그대로 보여줍니다.</p>':''}${kind==='rna_activity_score'?'<p class="notice-inline">탐색용 모델 비교 · 성공 확률 아님. 단일 EGFP 시험에서 소폭 개선됐으나 검증셋에서는 단순 모델보다 나빴습니다.</p>'.replace('実험','실험'):''}${kind==='rna_transcriptome_search'?rnaOfftargetSummary(result):''}${kind==='rna_seed_sites'?rnaSeedSiteSummary(result):''}${kind==='rna_delivery_simulation'?deliveryChart(result):''}${table}${['rna_sequence_evaluation','rna_candidate_generation'].includes(kind)?rnaThermodynamicDetails(result):''}${['rna_sequence_evaluation','rna_candidate_generation'].includes(kind)?`<div class="detail-actions">${button('science-candidate-followup','전체 전사체 비표적 후보 찾기',`data-id="${esc(selected)}" data-tool="rna_transcriptome_search"`,'small')}${button('science-candidate-followup','3′UTR seed·간 발현 확인',`data-id="${esc(selected)}" data-tool="rna_seed_sites"`,'small')}${button('science-candidate-followup','19nt 활성 모델 비교',`data-id="${esc(selected)}" data-tool="rna_activity_score"`,'small')}${button('science-candidate-followup','전체 ENsiRNA로 core 계산',`data-id="${esc(selected)}" data-tool="rna_author_full"`,'small')}</div>`:''}<div class="pagination"><span>보존 결과 ${result.offset+1}–${result.offset+result.rows.length} / ${result.total_rows}행</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}${next}</div></div><div class="detail-actions">${button('science-review','이 결과로 판단 갱신',`data-id="${esc(selected)}" ${busy?'disabled':''}`,'primary small')}</div>`;
}

function scienceDeliveryForm(){return `<section class="panel science-form"><h3>4. 화학수식·안정성·전달 근거</h3><p>실제 연구의 화학 차이와 혈장·간·신장 노출을 조건별로 확인합니다. 같은 서열 열역학으로 분해 안정성을 대신하지 않습니다.</p><p class="limit"><strong>제형 설계는 이 도구로 계산하지 않습니다.</strong> 여기 있는 전달 모형은 공개된 생쥐 antithrombin·GalNAc 약동학 모형 하나뿐입니다. LNP 조성·입자 크기·조직 표적화는 계산 대상이 아니며, 다른 조직·종·제형의 값으로 옮겨 읽지 않습니다.</p><div class="detail-actions">${button('science-chemistry-evidence','Nair2017 원 측정값 비교','','small')}${button('science-delivery-paper','Brown2020 · 전달 원문','data-pmc="PMC7708070"','small')}</div><h3>5. 전달·반응 지연의 가정 바꿔보기</h3><p>공개 마우스 AT/GalNAc 모형에서 노출→RISC→RNA→단백질의 시간차를 계산합니다. 이 모형의 값을 새 TTR 후보나 사람에게 그대로 적용하지 않습니다.</p><div class="science-fields">${scienceInput('delivery-dose','원 모형의 SC 투여량 · mg/kg','0–5','2.5')}${scienceInput('delivery-escape','endosomal escape 배율','0–10','1')}${scienceInput('delivery-turnover','단백질 turnover 배율','0.1–10','1')}</div>${button('science-delivery','이 조건의 시간경과 계산',busy?'disabled':'','small')}<p class="limit">1은 원 모형 값입니다. 배율 변경은 가상 조건 시험이며 연구자의 측정 결과가 아닙니다. 실제 후보의 안정성·조직 전달은 해당 화학/제형/용량의 자료로 검토합니다.</p></section>`}
async function openRnaFollowup(id,tool){if(tool==='rna_author_full')return openAuthorRna(id);const view=await api(`/api/workspaces/${state.id}/artifacts/${id}?limit=100`);const a=state.artifacts.find(x=>x.id===id);const ref=a.meta.arguments?.reference_id??a.meta.arguments?.artifact_id;showDialog(tool==='rna_activity_score'?'탐색용 활성 모델 비교':tool==='rna_seed_sites'?'3′UTR seed·간 발현 확인':'전체 전사체의 상호작용 후보',`<p>${tool==='rna_activity_score'?'19nt 가이드의 RNA-FM+ridge와 단순3mer 모델을 실제 비교합니다. 성공 확률·TTR 효능 검증이 아닙니다.':tool==='rna_seed_sites'?'명시적으로 확인한 Ensembl115 3′UTR에 6mer·m8·A1·8mer를 검색하고 GTExv8 간 유전자 발현을 연결합니다. 해당 isoform의 발현이나 억제 확률은 아닙니다.':'인간 Ensembl115의328868 spliced cDNA를 검색합니다. 조직 발현·실제 억제 위험은 별도 확인입니다.'}</p><div class="dock-candidates">${view.result.rows.map(r=>`<label><input type="checkbox" name="rna-candidate" value="${esc(r.id)}" ${tool==='rna_activity_score'&&r.length!==19?'disabled':''}>${esc(r.id)} · ${r.length}nt</label>`).join('')}</div>${tool==='rna_transcriptome_search'?'<label>에너지 상한 · kcal/mol<input id="rna-energy-cutoff" type="number" value="-20" min="-40" max="-10"></label><p class="limit">상한 이하의 정렬만 출력합니다. 출력하지 않은 약한 상호작용을 생물학적 부재로 해석하지 않습니다.</p>':''}<div class="dialog-actions">${button('science-run-rna-followup','선택 후보 실제 계산',`data-id="${esc(id)}" data-tool="${tool}" data-reference="${esc(ref??'')}"`,'primary')}</div>`)}
function rnaOfftargetSummary(r){return `<div class="table-scroll"><table><thead><tr><th>후보</th><th>주석 전사체 hit</th><th>다른 유전자 수</th><th>별도 역상보 hit</th></tr></thead><tbody>${r.candidate_summary.map(x=>`<tr><td>${esc(x.candidate_id)}</td><td>${x.annotated_transcript_hits}</td><td>${x.other_genes}</td><td>${x.reverse_index_hits}</td></tr>`).join('')}</tbody></table></div><p class="limit">모든 hit는 보존했습니다. 같은 유전자의 isoform 중복과 합성 역상보를 안전성 점수에 합산하지 않습니다.</p>`}
function deliveryChart(r){const rows=r.plot_rows??r.rows;const w=580,h=210,p=34;const xx=x=>p+x/1000*(w-2*p),yy=y=>h-p-y/100*(h-2*p);const path=k=>rows.map((v,i)=>(i?'L':'M')+xx(v.time_h).toFixed(2)+','+yy(v[k]).toFixed(2)).join(' ');return `<p class="notice-inline">공개 마우스 AT/GalNAc 모형 · 새 후보 예측 아님</p><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="모형의 mRNA와 단백질 잔존량 시간경과"><path d="M${p},${p}V${h-p}H${w-p}" fill="none" stroke="#aaa"/><path d="${path('mrna_percent_remaining')}" fill="none" stroke="#246d8a" stroke-width="3"/><path d="${path('protein_percent_remaining')}" fill="none" stroke="#b66b34" stroke-width="3"/><text x="0" y="${p}">100%</text><text x="8" y="${h-p}">0%</text><text x="${p}" y="${h-7}">0h</text><text x="${w-p-35}" y="${h-7}">1000h</text></svg><p class="small"><span style="color:#246d8a">● mRNA</span> · <span style="color:#b66b34">● 단백질</span> · 최소 잔존: ${number(r.summary.mrna_nadir_percent_remaining)}% / ${number(r.summary.protein_nadir_percent_remaining)}%</p>`}

function rnaSeedSiteSummary(r){return `<div class="table-scroll"><table><thead><tr><th>후보</th><th>m8/8mer 다른 유전자</th><th>A1만으로 추가된 유전자</th><th>네 종류 전체 · 간 TPM≥1</th><th>발현 미대응/모호</th></tr></thead><tbody>${r.candidate_summary.map(x=>`<tr><td>${esc(x.candidate_id)}</td><td>${x.m8_or8mer_other_genes}</td><td>${x.additional_A1_other_genes}</td><td>${x.other_genes_with_liver_tpm_at_least["1"]}</td><td>${x.other_genes_expression_unmapped_or_ambiguous}</td></tr>`).join("")}</tbody></table></div><p class="limit">TPM≥1은 보기 기준이며 안전성 문턱이 아닙니다. 다른 기준0.1/10·원 위치·겹친 site 종류는 원결과에 보존했습니다. 유전자 발현은 해당 isoform의 발현을 입증하지 않습니다.</p>`}

async function openAuthorRna(id){
 const start=selected===id?offset:0;
 const view=await api(`/api/workspaces/${state.id}/artifacts/${id}?offset=${start}&limit=30`);
 const a=state.artifacts.find(x=>x.id===id);
 const prior=a.meta.arguments?.reference_id??a.meta.arguments?.artifact_id;
 const refs=state.artifacts.filter(x=>['rna_reference','rna_reference_archive'].includes(x.kind));
 showDialog('전체 ENsiRNA · 새 구조와 core 비교',`<p>선택한19nt 가이드에 비수식 blunt 보조가닥을 구성하고, 구조부터 저자5개 모델까지 실제 계산합니다. 원 후보의 수식·돌출부·제형을 반영한 효능은 아닙니다.</p>
 <p class="limit">한 번에1–3개를 비교합니다. 구조 계산에 수분 이상 걸릴 수 있으며, 입력·구조·각 모델의 원점수와 실패 기록을 보존합니다.</p>
 <label>계산에 쓸 원 전사체<select id="rna-author-reference">${refs.map(r=>`<option value="${esc(r.id)}" ${r.id===prior?'selected':''}>${esc(artifactName(r.id))}</option>`).join('')}</select></label>
 <div class="dock-candidates">${view.result.rows.map(r=>`<label><input type="checkbox" name="rna-candidate" value="${esc(r.id)}" ${r.length!==19?'disabled':''}>${esc(r.id)} · ${r.length}nt</label>`).join('')}</div>
 <p class="limit">현재 조회 구간의 후보입니다. 다른 페이지의 후보도 그 페이지에서 선택할 수 있습니다. 미선택 후보는 유지됩니다.</p>
 <div class="dialog-actions">${button('science-run-rna-followup','선택한 core 실제 계산',`data-id="${esc(id)}" data-tool="rna_author_full" ${refs.length?'':'disabled'}`,'primary')}</div>`);
}

// The main table stays compact; these are returned values, not a new score.
function rnaThermodynamicDetails(result){
 const sites=result.rows.flatMap(row=>(row.perfect_complementary_sites??[]).map(site=>({id:row.id,...site})));
 if(!sites.length)return '';
 const protocol=result.protocol??{};
 return `<details class="rna-thermodynamic-details"><summary>표적 열림·결합 계산값 비교</summary><p class="small">현재 보이는 후보의 대응 부위별 원 계산값입니다. 가이드 자체의 접힘과 표적 부위의 열림·가이드–표적 결합을 구분합니다. 세포 내 효능이나 실제 수식의 효과를 측정한 값은 아닙니다.</p><p class="limit">ViennaRNA ${esc(protocol.version??'버전 미제공')} · ${esc(protocol.temperature_celsius??'미제공')} °C · 접근성 window ${esc(protocol.window_size??'미제공')}, span ${esc(protocol.maximum_base_pair_span??'미제공')}</p><div class="table-scroll"><table><thead><tr><th>후보 · 표적 위치</th><th>표적 열림 비용 · kcal/mol</th><th>가이드–표적 결합 에너지 · kcal/mol</th></tr></thead><tbody>${sites.map(s=>`<tr><td>${esc(s.id)}<br>${esc(s.start_1_based)}–${esc(s.end_1_based)}</td><td>${number(s.opening_free_energy_kcal_mol)}</td><td>${number(s.duplex_minimum_energy_kcal_mol)}</td></tr>`).join('')}</tbody></table></div></details>`;
}


;
/* Source: source-evidence.js */
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


;
/* Source: trial-results.js */
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


;
/* Source: clinical-sources.js */
Object.assign(SCIENCE_LABELS,{binding_measurements:'결합·활성 원자료 · BindingDB',drug_label_search:'약물 라벨 목록',drug_label:'약물의 적용 조건·시험',clinical_trial_search:'등록 시험 목록',clinical_trial:'시험의 대상·결과'});
Object.assign(SCIENCE_LABELS,{public_lookup_bundle:'함께 확인한 공개 근거',public_source_failure:'공개 자료 접근 기록'});
const CLINICAL_SOURCE_KINDS=['binding_measurements','drug_label_search','drug_label','clinical_trial_search','clinical_trial'];

function publicLookupBundleView(result){
 const states={succeeded:'자료 도착',partial:'일부 자료 도착',same_response:'같은 조회 결과 참조',rate_limited:'조회 한도에 도달',access_failed:'접근 실패',network_failed:'연결 실패',timeout:'응답 시간 초과',response_or_input_error:'입력·반환 확인 필요'};
 const names={search_literature:'문헌 검색',search_drug_labels:'약물 라벨 찾기',read_drug_label:'라벨 원문',search_clinical_trials:'등록 시험 찾기',read_clinical_trial:'시험 원 기록'};
 return `<p>서로의 결과를 기다릴 필요가 없는 공개 조회를 함께 진행했습니다. 각 자료의 조건을 확인한 뒤 다음 검색·판단을 이어갑니다.</p>${(result.rows??[]).map(r=>`<article class="source-paragraph"><h3>${esc(names[r.function]??r.function)} · ${esc(states[r.status]??r.status)}</h3><p>${esc(r.purpose)}</p>${r.error?`<p class="notice-inline">${esc(r.error)} · 다른 조회 결과는 보존됩니다.</p>`:''}${r.source_artifact_id?button('source','이 조회의 원자료·전체 결과 보기',`data-id="${esc(r.source_artifact_id)}"`,'link-button small'):''}${r.status==='same_response'?'<p class="small muted">같은 응답을 다시 가리킵니다. 별개의 실험이나 검색 결과로 합산하지 않습니다.</p>':''}${r.view_delivery?'<p class="small muted">이 요약에는 본문이 없습니다. 원자료를 열어 필요한 범위를 확인하세요.</p>':''}</article>`).join('')}`;
}

function clinicalSourcesEntry(){return `<section class="panel science-form"><h3>임상·적용 조건까지 확인하기</h3><p>문헌 속 후보가 어떤 대상·조건에서 검토됐는지 원 기록을 확인합니다.</p>
<details><summary>약물의 적응증·경고·시험 원문</summary>${scienceInput('clinical-drug','공개 성분명 또는 제품명','예: tafamidis')}${button('science-clinical-labels','DailyMed에서 라벨 찾기',busy?'disabled':'','small')}<p class="limit">미국 라벨입니다. 제품·제형·판본을 고른 뒤 본문을 확인합니다.</p></details>
<details><summary>진행·완료·중단된 임상시험</summary>${scienceInput('clinical-condition','공개 질환 이름','예: transthyretin amyloidosis')}${scienceInput('clinical-intervention','개입 이름 · 선택 사항','미정이면 비워 두세요')}${button('science-clinical-trials','시험 찾기',busy?'disabled':'','small')}${scienceInput('clinical-nct','이미 아는 시험 번호','NCT…')}${button('science-clinical-trial-id','이 시험의 원 기록 읽기',busy?'disabled':'','small')}<p class="limit">계획한 평가항목과 실제 게시 결과를 구분합니다. 결과 미게시가 음성은 아닙니다.</p></details>
<details><summary>추가 결합·활성 자료</summary>${scienceInput('clinical-uniprot','확인한 UniProt 표적 ID','예: P02766')}${scienceInput('clinical-cutoff','조회할 활성 문턱 · nM','예: 10000')}${button('science-clinical-binding','BindingDB 원자료 조회',busy?'disabled':'','small')}<p class="limit">문턱 밖 후보는 미조회입니다. 다른 활성 지표와 실험 조건을 섞어 순위를 매기지 않습니다.</p></details></section>`}

async function clinicalSourceAction(action,node){
 const val=id=>(document.getElementById(id)?.value??'').trim();
 if(action==='science-clinical-select'){
  const ids=[...new Set([...document.querySelectorAll('input[name="binding-candidate"]:checked')].map(n=>n.value))];
  if(!ids.length){notice('계산에 연결할 원 구조를 선택해 주세요.');return}
  showDialog('선정한 원 구조를 계산에 연결',`<p>선택한 ${ids.length}개 후보의 공개 원 SMILES를 계산용 자료로 만듭니다. 이 선택은 효능·안전성 추천이 아닙니다.</p><p class="small">${ids.map(esc).join(' · ')}</p><label>이 후보들을 비교할 이유<textarea id="clinical-selection-reason" placeholder="어떤 가설이나 차이를 계산으로 확인하려는지 적어 주세요."></textarea></label><p class="limit">같은 ID에 서로 다른 구조가 있으면 원행 확인을 요청합니다. 미선택 후보와 측정 원값은 그대로 남습니다.</p><div class="dialog-actions">${button('science-clinical-materialize','원 구조 연결',`data-source="${esc(selected)}" data-ids="${esc(JSON.stringify(ids))}"`,'primary')}</div>`);return;
 }
 if(action==='science-clinical-materialize'){
  const reason=val('clinical-selection-reason');if(!reason){notice('비교할 이유를 남겨 주세요.');return}
  const args={artifact_id:node.dataset.source,candidate_ids:JSON.parse(node.dataset.ids),reason};
  dialog.close();await runTool('compound_selection',args);return;
 }
 if(action==='science-clinical-labels')await runTool('drug_label_search',{drug_name:val('clinical-drug'),page:1});
 if(action==='science-clinical-label-read')await runTool('drug_label',{setid:node.dataset.id});
 if(action==='science-clinical-trials')await runTool('clinical_trial_search',{condition:val('clinical-condition'),intervention:val('clinical-intervention'),page_token:''});
 if(action==='science-clinical-trial-id')await runTool('clinical_trial',{nct_id:val('clinical-nct')});
 if(action==='science-clinical-trial-read')await runTool('clinical_trial',{nct_id:node.dataset.id});
 if(action==='science-clinical-binding')await runTool('binding_measurements',{uniprot_id:val('clinical-uniprot'),cutoff_nm:Number(val('clinical-cutoff'))});
 if(action==='science-clinical-more-labels')await runTool('drug_label_search',{drug_name:detail.result.summary.query,page:detail.result.summary.page+1});
 if(action==='science-clinical-more-trials')await runTool('clinical_trial_search',{condition:detail.result.summary.condition,intervention:detail.result.summary.intervention,page_token:detail.result.summary.next_page_token});
}

function clinicalSourceTable(result,kind){
 const content=clinicalSourceContent(result,kind);
 if(['drug_label_search','clinical_trial_search'].includes(kind)||content===null)return content;
 const rows=result.rows??[],start=result.offset??0,total=result.total_rows??rows.length;
 return content+`<div class="pagination"><span>보존 원문 ${rows.length?number(start+1):0}–${number(start+rows.length)} / ${number(total)}행</span><div>${button('prev','이전 원문 범위',start===0?'disabled':'','small')}${button('next','다음 원문 범위',!result.has_more?'disabled':'','small')}</div></div><p class="small muted">저장된 원문의 다른 범위를 엽니다. 새 조회나 계산을 실행하지 않습니다.</p>`;
}

function compoundSelectionView(result){
 return `<h3>계산에 연결한 후보 ${esc(result.summary?.selected??result.candidate_ids?.length??0)}개</h3><p>${esc(result.selection_reason??'')}</p><p class="small">${(result.candidate_ids??[]).map(esc).join(' · ')}</p><p class="limit">공개 원 구조의 선택 사본입니다. 효능 추천이나 새 구조 생성이 아니며 미선택 후보도 남아 있습니다.</p>${result.molecule_csv_artifact_id?`<div class="detail-actions">${button('source','선정 구조와 출처 보기',`data-id="${esc(result.molecule_csv_artifact_id)}"`,'small')}${button('tool','이 원 구조의 물성 계산',`data-tool="rdkit" data-id="${esc(result.molecule_csv_artifact_id)}" ${busy?'disabled':''}`,'primary small')}</div>`:''}`;
}

function clinicalSourceContent(result,kind){
 const rows=result.rows??[],s=result.summary??{};
 const table=(headers,values)=>`<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${values(r).map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
 if(kind==='drug_label_search')return `<p>현재 조회 페이지 ${esc(s.page)} · 전체 ${esc(s.total??'미확인')}개</p>`+table(['제품·제형','판본 · 게시일','다음 확인'],r=>[externalAnchor('setid',r.setid,r.title),esc(`${r.spl_version} · ${r.published_date}`),button('science-clinical-label-read','적용 조건·시험 읽기',`data-id="${esc(r.setid)}"`,'small')])+(s.has_more?button('science-clinical-more-labels','다음 라벨 목록 조회','','small'):'');
 if(kind==='clinical_trial_search')return `<p>전체 ${esc(s.total??'미확인')}개 중 이번 조회 ${esc(s.returned)}개</p>`+table(['시험','상태 · 설계','게시 결과','다음 확인'],r=>[externalAnchor('nct',r.nct_id)+'<br>'+esc(r.title),esc(r.status?.overallStatus??'미제공')+'<br>'+esc(r.design?.studyType??''),r.has_results===true?'있음':r.has_results===false?'아직 게시되지 않음':'미확인',button('science-clinical-trial-read','대상·계획·결과 읽기',`data-id="${esc(r.nct_id)}"`,'small')])+(s.has_more?button('science-clinical-more-trials','다음 시험 목록 조회','','small'):'');
 if(kind==='binding_measurements')return `<p>표적 ${esc(s.uniprot_id)} · 조회 문턱 ${esc(s.query_cutoff_nm)}nM</p><p class="limit">이 응답에는 세부 assay 조건이 없습니다. 같은 데이터의 재수록일 수 있어 원전을 확인해야 합니다.</p>`+table(['계산할 구조','원 지표·값','참조','반환 중복'],r=>[`<label><input type="checkbox" name="binding-candidate" value="${esc(r.candidate_id)}" ${r.structure_status==='available'?'':'disabled'}> ${esc(r.candidate_id)}</label><details><summary>원 SMILES</summary><p class="mono">${esc(r.smiles??'구조 미제공')}</p></details>`,esc(`${r.raw.affinity_type??''} ${r.raw.affinity??'미제공'}`),esc([r.raw.pmid?'PMID '+r.raw.pmid:'',r.raw.doi?'DOI '+r.raw.doi:''].filter(Boolean).join(' · ')||'미제공'),r.same_returned_representation_as_row!==null?`원행 ${esc(r.same_returned_representation_as_row+1)}과 동일 표현`:'독립성 미확인'])+button('science-clinical-select','선택한 원 구조를 계산에 연결',busy?'disabled':'','small');
 const nav=`<details><summary>원문에서 필요한 부분으로 이동</summary><div class="source-section-list">${(result.section_navigation??[]).filter(n=>n.row_count).map(n=>button('article-section',esc(n.section_title??[n.section,n.module].filter(Boolean).join(' / ')??'절'),`data-offset="${n.row_offset}"`,'link-button small')).join('')}</div></details>`;
 if(kind==='drug_label')return `<p>${externalAnchor('setid',s.setid,'DailyMed 원문')} · <strong>SPL 판본 ${esc(s.spl_version)}</strong> · 문서 effectiveTime ${esc(s.effective_time)}</p>${nav}`+rows.map(r=>`<section class="source-paragraph"><h4>${esc(r.section_title??'제목 없음')}</h4>${r.cells?`<p class="small">${esc(r.caption??'')}</p><div class="table-scroll"><table><tbody><tr>${r.cells.map(c=>`<td>${esc(c.text)}${c.colspan||c.rowspan?`<small> · 원 셀 병합 열 ${esc(c.colspan??1)}, 행 ${esc(c.rowspan??1)}</small>`:''}</td>`).join('')}</tr></tbody></table></div>`:`<p class="prose">${esc(r.text??'')}</p>`}${r.text_is_fragment?'<p class="small muted">긴 본문의 일부입니다. 이어지는 행도 확인해 주세요.</p>':''}</section>`).join('');
 if(kind==='clinical_trial')return `<h3>${esc(s.title)}</h3><p>${externalAnchor('nct',s.nct_id)} · ${esc(s.overall_status)} · 결과 ${s.has_results===true?'게시됨':s.has_results===false?'미게시':'미확인'}</p>${trialResultsView(result)}${nav}`
  // The registry sections stay available in full, but folded: the reported results above are what
  // a reader needs, and an open dump of every module buries them.
  +`<details class="source-raw-sections"><summary>등록부 원 기록 ${esc(rows.length)}개 구역 보기</summary>`
  +rows.map(r=>`<section class="source-paragraph"><h4>${esc([r.section,r.module].filter(Boolean).join(' / '))}</h4><p class="small muted">${esc(r.json_pointer)}</p>${json(r.value)}${r.fragment_offset_codepoints!==undefined?'<p class="small muted">긴 원문 문자열의 연속 부분입니다.</p>':''}</section>`).join('')
  +`</details>`;
 return null;
}


;
/* Source: target-context.js */
Object.assign(SCIENCE_LABELS,{target_context:'표적의 유전·세포·조직 조건'});
const TARGET_CONTEXT_LABELS={genetic_constraint:'집단 유전변이의 제약',essentiality:'암 세포주의 유전자 의존성',safety_liabilities:'출처별 안전성 관측',baseline_expression:'세포·조직의 기초 발현'};

function targetContextEntry(){return `<section class="panel science-form"><h3>이 표적을 조절하는 조건 확인하기</h3><p>질환과 연관됐다는 사실에 더해, 어떤 조직·작용 방향을 검토해야 할지 자료를 확인합니다. 앞서 찾은 표적 자료의 버튼으로도 시작할 수 있습니다.</p>${scienceInput('target-context-id','확인한 인간 Ensembl 표적 ID','ENSG…')}<fieldset><legend>이번 질문에 필요한 자료</legend>${Object.entries(TARGET_CONTEXT_LABELS).map(([id,label])=>`<label><input type="checkbox" name="target-context-section" value="${id}" ${['genetic_constraint','safety_liabilities'].includes(id)?'checked':''}> ${esc(label)}</label>`).join('')}</fieldset>${button('science-target-context-fetch','선택한 표적 자료 확인',busy?'disabled':'','small')}<p class="limit">점수를 합쳐 자동 순위를 만들지 않습니다. 기능 손실의 질환 기전과 조직별 부분 억제는 따로 검토합니다.</p></section>`}

async function targetContextAction(action,node){
 const fromSource=Boolean(node.dataset.targetId), target=fromSource?node.dataset.targetId:document.querySelector('#target-context-id').value.trim();
 const sections=fromSource?(node.dataset.sections??'genetic_constraint,safety_liabilities').split(','):[...document.querySelectorAll('[name="target-context-section"]:checked')].map(x=>x.value);
 if(!sections.length)throw new Error('이번 질문에 필요한 자료를 하나 이상 선택해 주세요.');
 await runTool('target_context',{target_id:target,sections,expression_page:Number(node.dataset.expressionPage??0)});
}

function targetContextTable(result){
 const target=result.target??{},coverage=result.section_coverage??{};
 const labels={returned_rows:'자료 반환',returned_no_records:'이 출처의 반환 기록 없음',not_returned:'미반환 · 음성 결과 아님',source_error:'출처 오류',source_error_with_rows:'일부 자료와 오류 반환'};
 const flag=v=>v===true?'공통 필수 유전자로 분류':v===false?'공통 필수 유전자로 분류되지 않음':'분류 미반환';
 const missing=v=>v===null||v===undefined?'미반환':typeof v==='number'?number(v):String(v);
 const cell=r=>{
  const v=r.value??{};
  if(r.context_type==='genetic_constraint')return ['집단 변이 · '+missing(v.constraintType),`관측 ${missing(v.obs)} / 기대 ${missing(v.exp)}`,`O/E ${missing(v.oe)} · 구간 ${missing(v.oeLower)}–${missing(v.oeUpper)}`];
  if(r.context_type==='common_essential_flag')return ['암 세포주 공통 의존성','정상 조직의 안전성 판정이 아님',flag(r.value)];
  if(r.context_type==='cancer_cell_dependency')return ['암 세포주 · '+missing(v.cellLineName),[r.tissue_name,v.diseaseFromSource,v.mutation].filter(Boolean).join(' · '),`Gene effect ${missing(v.geneEffect)} · 발현 ${missing(v.expression)}`];
  if(r.context_type==='safety_liabilities')return ['안전성 관측 · '+missing(v.event),[v.datasource,...(v.biosamples??[]).map(b=>b.tissueLabel||b.cellLabel)].filter(Boolean).join(' · '),(v.effects??[]).map(e=>[e.direction,e.dosing].filter(Boolean).join(' · ')).join('; ')||'효과 조건 미반환'];
  return ['기초 발현 · '+missing(v.datasourceId),[v.tissueBiosample?.biosampleName||v.tissueBiosampleFromSource,v.celltypeBiosample?.biosampleName||v.celltypeBiosampleFromSource,v.datatypeId].filter(Boolean).join(' · '),`중앙값 ${missing(v.median)} ${missing(v.unit)} · Q1–Q3 ${missing(v.q1)}–${missing(v.q3)}`];
 };
 const more=coverage.baseline_expression;
 return `<h3>${esc(target.approvedSymbol??result.summary?.target_id)} · ${esc(target.approvedName??'표적 확인 필요')}</h3><p>출처별 맥락을 비교할 자료입니다. 아래 관측만으로 표적을 추천하거나 배제하지 않습니다.</p><ul>${Object.entries(coverage).map(([k,v])=>`<li><strong>${esc(TARGET_CONTEXT_LABELS[k])}</strong> · ${esc(labels[v.status]??v.status)}${k==='baseline_expression'?` · 원 페이지 ${number((v.page??0)+1)}, 반환 ${number(v.returned_rows)} / 전체 ${number(v.total)}`:''}</li>`).join('')}</ul><div class="table-scroll"><table><thead><tr><th>자료</th><th>대상·조건</th><th>출처의 값</th></tr></thead><tbody>${(result.rows??[]).map(r=>`<tr>${cell(r).map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${more?.has_more?button('science-target-context-next','발현 자료의 다음 원 페이지 확인',`data-target-id="${esc(target.id)}" data-sections="baseline_expression" data-expression-page="${more.page+1}"`,'small'):''}<p class="limit">안전성 관측 0건은 위험 0이 아닙니다. O/E·Gene effect·발현은 서로 다른 자료이므로 같은 점수로 합치지 않습니다. 표의 원값·출처 위치·전체 응답은 보존 자료에서 확인할 수 있습니다.</p><details><summary>반환 판본과 자료 해석 범위</summary><pre>${esc(JSON.stringify(result.source_version,null,2))}</pre>${(result.limits??[]).map(x=>`<p>${esc(x)}</p>`).join('')}</details>`;
}


;
/* Source: gtopdb.js */
Object.assign(SCIENCE_LABELS,{gtopdb_pharmacology:'표적의 작용 물질과 약리 근거'});

function gtopdbEntry(){
 return '<section class="panel science-form"><h3>이 표적에 작용하는 물질 찾아보기</h3><p>GtoPdb에서 작용 물질과 측정 근거를 확인합니다. 찾은 물질은 전체 선택지에도 남습니다.</p>'+
 scienceInput('gtopdb-gene','확인할 표적의 유전자 기호','예: AVPR2')+
 '<label>표적의 종<select id="gtopdb-species"><option value="Human">사람 표적</option><option value="Mouse">마우스 표적</option><option value="Rat">랫드 표적</option></select></label>'+
 button('science-gtopdb-fetch','작용 물질과 근거 찾기',busy?'disabled':'','small')+
 '<p class="limit">물질을 찾았다는 사실만으로 이 질환의 치료 후보로 추천하지 않습니다.</p></section>';
}

async function gtopdbAction(action,node){
 const gene=node.dataset.gene||document.querySelector('#gtopdb-gene').value.trim();
 const species=node.dataset.gene?'Human':document.querySelector('#gtopdb-species').value;
 await runTool('gtopdb_pharmacology',{gene_symbol:gene,species});
}

function gtopdbTable(result){
 const labels={Agonist:'작용제',Antagonist:'길항제',None:'작용 미확인',Inhibitor:'억제제'};
 const action=r=>r.curated_action?.status==='reported'?(labels[r.curated_action.action]||r.curated_action.action):'작용 미확인';
 const measure=r=>[r.measurement?.parameter,r.measurement?.value_as_reported].filter(x=>x!==null&&x!==undefined&&x!=='').join(' ')||'측정값 미반환';
 const meaning=r=>r.measurement?.kind==='binding_affinity'?'결합 지표 · 기능 효과 아님':r.measurement?.kind==='unclassified'?'측정 해석 미확인':'시험 조건 확인 필요';
 const plain=v=>String(v||'').replace(/<\/?(?:sub|sup|i|b)>/gi,'');
 const pmids=r=>(r.pmids||[]).filter(x=>/^\d+$/.test(String(x))).map(x=>'<a href="https://pubmed.ncbi.nlm.nih.gov/'+esc(x)+'/" target="_blank" rel="noopener noreferrer">PMID '+esc(x)+'</a>').join(', ')||'PMID 미반환';
 return '<h3>'+esc(result.target?.queried_gene_symbol||result.query?.gene_symbol||'표적')+' · '+esc(plain(result.target?.name||'표적 확인 필요'))+'</h3>'+
 '<p>작용 방향은 GtoPdb의 큐레이션 기록이며, 결합 수치와 별도로 봅니다. 사람 표적 실험이 사람 임상시험을 뜻하지는 않습니다.</p>'+
 (result.status!=='succeeded'?'<p class="limit">'+esc(result.error||'조회 미완료 · 약리 근거 0건이 아닙니다.')+'</p>':'')+
 '<div class="table-scroll"><table class="pharmacology-table"><thead><tr><th>물질</th><th>기록된 작용</th><th>측정</th><th>실험 조건</th><th>원문 확인</th></tr></thead><tbody>'+
 (result.rows||[]).map(r=>'<tr><td>'+esc(plain(r.ligand_name))+'</td><td>'+esc(action(r))+'</td><td>'+esc(measure(r))+'<br><small>'+esc(meaning(r))+'</small></td><td>'+esc(r.missing_condition_fields?.length?'일부 조건 미확인':r.raw_record?.assayDescription||'상세 원자료 확인')+'</td><td>'+'<details><summary>원문 '+number((r.pmids||[]).length)+'편</summary>'+pmids(r)+'</details></td></tr>').join('')+
 '</tbody></table></div>'+storedSourcePages(result)+'<p>IUPHAR/BPS Guide to PHARMACOLOGY · 데이터베이스 ODbL · 콘텐츠 CC BY-SA 4.0</p>'+
 '<details><summary>전체 근거와 미확인 범위</summary><p>참고문헌 링크는 원문 읽기 완료 표시가 아닙니다. 전체 결과를 내려받으면 원 측정값·조건·참고문헌을 확인할 수 있습니다.</p>'+
 (result.limits||[]).map(x=>'<p>'+esc(x)+'</p>').join('')+'</details>';
}


;
/* Source: lens-sources.js */
Object.assign(SCIENCE_LABELS,{lens_literature:'문헌 검색과 인용 연결'});
function lensEntry(){return '<section class="panel science-form"><h3>다른 접근과 연결 문헌 찾기</h3><p>질환·기전 검색과 원전의 참고문헌·후속 인용을 함께 살펴볼 수 있습니다.</p>'+scienceInput('lens-query','검색어 또는 논문 DOI','질환, 확인할 질문, 논문 DOI 또는 Lens ID')+button('science-lens-search','Lens 문헌 검색',busy?'disabled':'','small')+'<p class="limit">검색된 문헌은 읽기 후보입니다. 제목이나 인용만으로 치료 후보로 추천하지 않습니다.</p></section>'}
async function lensAction(action,node){
 const mode=action==='science-lens-search'?'search':node.dataset.mode;
 const query=mode==='search'?(node.dataset.query||document.querySelector('#lens-query').value.trim()):'';
 await runTool('lens_literature',{mode,query,lens_id:mode==='search'?'':node.dataset.lensId,offset:Number(node.dataset.offset||0),limit:20});
}
function lensTable(result){
 const names={search:'독립 문헌 검색',references:'이 논문의 참고문헌',citing:'이 논문을 인용한 후속 문헌'};
 const summary=result.summary||{},query=result.query||{};
 return '<h3>'+esc(names[query.mode]||'문헌 조회')+'</h3><p>이번 원페이지 '+number(summary.returned)+'편 / 검색 범위 전체 '+number(summary.source_total)+'편. 원문·주장의 타당성은 추가로 확인합니다.</p>'+
 '<div class="lens-records">'+(result.rows||[]).map(r=>'<article class="lens-record"><h4>'+esc(r.title||'제목 미반환')+'</h4><p>'+esc(r.year_published||'발행연도 미반환')+' · Lens '+esc(r.lens_id)+'</p>'+
 (r.abstract?'<details><summary>반환된 초록</summary><p>'+esc(r.abstract)+'</p></details>':'<p class="limit">초록 미반환 · 원문 확인 필요</p>')+
 '<div class="detail-actions">'+button('science-lens-citation','참고문헌 찾기','data-mode="references" data-lens-id="'+esc(r.lens_id)+'"','small')+button('science-lens-citation','후속 인용 찾기','data-mode="citing" data-lens-id="'+esc(r.lens_id)+'"','small')+'</div></article>').join('')+'</div>'+
 storedSourcePages(result)+
 (summary.source_has_more?button('science-lens-next','다음 원페이지 조회','data-mode="'+esc(query.mode)+'" data-query="'+esc(query.query)+'" data-lens-id="'+esc(query.lens_id)+'" data-offset="'+result.frontier.next_source_offset+'"','small'):'')+
 '<p class="limit">한 번의 인용 조회는 탐색 깊이의 상한이 아닙니다. 필요한 원전을 다시 출발점으로 삼을 수 있으며, 인용망 밖 검색도 열려 있습니다.</p>';
}

function storedSourcePages(result){
 if(!Number.isInteger(result.total_rows))return '';
 const start=result.offset||0,count=(result.rows||[]).length;
 return '<div class="pagination"><span>보존한 자료 '+number(count?start+1:0)+'–'+number(start+count)+' / '+number(result.total_rows)+'행</span><div>'+button('prev','이전',start===0?'disabled':'','small')+button('next','다음',!result.has_more?'disabled':'','small')+'</div></div>';
}


;
/* Source: exposure-requirements.js */
Object.assign(SCIENCE_LABELS,{exposure_requirements:'노출과 시험 농도의 연결 조건'});
Object.assign(SCIENCE_LABELS,{kinetic_conditions:'효소 속도의 조건별 비교'});
function kineticConditionsTable(result){
 const fmt=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ko-KR',{maximumSignificantDigits:5}):'미확인';
 const name=id=>result.parameters?.find(p=>p.id===id)?.label??id;
 return `<h3>기질 조건에 따라 달라지는 계산 결과</h3><p class="limit">원문에 보고된 평균 모수를 속도식에 넣은 조건부 계산입니다. 새 측정·곡선 적합·유의성 검정이나 생체 내 효과가 아닙니다.</p><p>식: v = Vmax × S / (Km + S)</p>${list(result.comparison_assumptions??[])}<div class="table-scroll"><table><thead><tr><th>비교 조건</th><th>기질 농도</th><th>기준 속도</th><th>비교 속도</th><th>기준 대비 비</th><th>같은 속도가 되는 양 배수</th></tr></thead><tbody>${(result.rows??[]).map(r=>`<tr><td>${esc(name(r.comparator_id))}</td><td>${fmt(r.substrate_uM)} μM</td><td>${fmt(r.reference_rate)} ${esc(r.rate_unit)}</td><td>${fmt(r.comparator_rate)} ${esc(r.rate_unit)}</td><td>${fmt(r.conditional_rate_ratio)}</td><td>${fmt(r.amount_multiplier_for_equal_rate)}배</td></tr>`).join('')}</tbody></table></div><p class="small muted">양 배수는 속도가 시료량에 비례한다는 가정입니다. 실제 단백질 증가량을 측정한 값이 아닙니다.</p>${(result.crossings??[]).map(c=>`<p>${esc(name(c.comparator_id))}: ${c.equal_functions?'같은 모수의 속도 곡선':c.positive_substrate_crossing?`기준과 같아지는 양의 기질 농도 ${fmt(c.algebraic_crossing_uM)} μM`:'양의 기질 농도에서 기준과 교차하지 않음'}</p>`).join('')}<p class="limit">교차점이 없다고 같은 곡선이거나 구별할 수 없다는 뜻은 아닙니다. 실제 측정 정밀도와 시료 조건을 함께 확인해야 합니다.</p><details><summary>원문 모수·조건과 출처 확인</summary>${(result.parameters??[]).map(p=>`<p><strong>${esc(p.label)}</strong>: Km ${fmt(p.km_uM)} μM · Vmax ${fmt(p.vmax)} ${esc(p.vmax_unit)}<br>${esc(p.conditions)}</p>`).join('')}${(result.source_bindings??[]).map(s=>`<blockquote>${esc(s.quote)}<br>${button('source','원자료 확인',`data-id="${esc(s.artifact_id)}"`,'small')}</blockquote>`).join('')}<p class="limit">원문 위치·인용·숫자 일치는 확인하지만, 그 숫자의 의미와 생물학적 비교 가능성은 별도 검토가 필요합니다.</p></details>`;
}
function exposureRequirementsTable(result){
 const fmt=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ko-KR',{maximumSignificantDigits:5}):'미확인';
 const range=(single,bounds)=>Array.isArray(bounds)&&bounds.length===2?`${fmt(bounds[0])}–${fmt(bounds[1])}`:fmt(single);
 const metric={Cmax:'최고 농도',Ctrough:'최저 농도',Caverage:'보고 평균',AUC_divided_by_interval_mean:'AUC/시간으로 계산한 평균',other_concentration:'보고 농도'};
 return `<h3>시험 농도와 실제 노출의 조건부 비교</h3><p>${esc(result.context??'')}</p><p>시험 비교값: <strong>${fmt(result.assay_benchmark?.value)} ${esc(result.assay_benchmark?.unit??'')}</strong> · ${esc(result.assay_benchmark?.metric??'')}</p><p>${esc(result.assay_benchmark?.context??'')}</p><p class="limit">혈장 농도와 세포시험 농도는 바로 같은 값으로 볼 수 없습니다. 아래 비율은 두 실험계의 자유 작용부위 농도가 같다는 가정에서의 값입니다. 효능에 필요한 조건을 입증하거나 실제 전달 비율·효능을 측정한 결과가 아닙니다.</p><div class="table-scroll"><table class="exposure-table"><thead><tr><th>자료·조건</th><th>원문 값·파생 범위</th><th>비교용 농도</th><th>화학형 가정</th><th>동일 농도 가정의 비율</th></tr></thead><tbody>${(result.rows??[]).map(r=>`<tr><td>${esc(r.label)}<details><summary>자료 조건</summary><p>${esc(r.exposure_context)}</p></details></td><td>${range(r.reported_value,r.derived_value_range)} ${esc(r.reported_unit)}${r.derivation?`<small>원문 백분율로 계산 · 직접 측정값 아님</small><details><summary>계산식·원 조건</summary><p>${fmt(r.derivation.base_reported_value)} × (${fmt(r.derivation.percent_min)}–${fmt(r.derivation.percent_max)}) ÷ 100</p><p>${esc(r.derivation.base_context)}</p><p>이 범위는 신뢰구간·개인별 예측이 아닙니다.</p></details>`:''}${r.interval_hours!==null?`<small>적분 구간 ${fmt(r.interval_hours)}시간</small>`:''}</td><td>${range(r.comparison_concentration_uM,r.comparison_concentration_uM_range)} μM<small>${esc(metric[r.comparison_statistic]??r.comparison_statistic)}</small></td><td>${esc(r.mass_basis_label)}<small>${r.mass_basis_status==='sensitivity_only'?'원 PK의 기준 미확인 · 감도 시나리오':r.mass_basis_status==='no_mass_conversion'?'질량 변환 없음':'출처 조건 확인 필요'}</small></td><td>${range(r.required_effective_translation_factor,r.required_effective_translation_factor_range)}배<small>실제 연결 비율은 미측정</small></td></tr>`).join('')}</tbody></table></div>${(result.unresolved_inputs??[]).map(g=>`<p class="limit">${esc(g.exposure_id)}: ${esc(g.required)}</p>`).join('')}<details><summary>원문 연결과 계산의 의미</summary><p>단백 결합, 조직·세포 내 분포, 노출 시간과 시험 조건을 확인해야 후보 유지·변경을 판단할 수 있습니다. AUC 평균은 지속적인 최저 농도를 대신하지 않습니다.</p><pre>${esc(JSON.stringify(result.equations,null,2))}</pre>${(result.verified_source_locations??[]).map(s=>`<blockquote>${esc(s.quote)}<br>${button('source','원자료 확인',`data-id="${esc(s.artifact_id)}"`,'small')}<small>${esc(JSON.stringify(s.path))}</small></blockquote>`).join('')}</details>`;
}


;
/* Source: article-references.js */
const articleReferenceModes=new Map();
function articleReferenceQuery(id){
 const value=articleReferenceModes.get(id);if(!value)return '';
 return '&references=1'+value.map(x=>'&reference_id='+encodeURIComponent(x)).join('');
}
async function openArticleReferences(node){
 const ids=JSON.parse(node.dataset.referenceIds??'[]'),next=Number(node.dataset.offset??0);
 if(!Array.isArray(ids)||!Number.isInteger(next)||next<0)throw Error('참고문헌 위치를 확인해 주세요.');
 articleReferenceModes.set(selected,ids);offset=next;await readDetail();
 document.querySelector('.data-detail')?.scrollIntoView({block:'start'});
}
function articleCitationButtons(row){
 const ids=[...new Set((row.citation_markers??[]).flatMap(m=>m.reference_ids))];
 return ids.length?button('article-references','이 문단이 인용한 원전 찾기',`data-reference-ids="${esc(JSON.stringify(ids))}"`,'link-button small'):'';
}
function articleReferencesView(result){
 const ids=JSON.stringify(result.selected_reference_ids??[]);
 const links=r=>(r.article_ids??[]).filter((x,i,all)=>all.findIndex(y=>y.type===x.type&&y.value===x.value)===i).map(x=>{
  const url=x.type==='pmid'?'https://pubmed.ncbi.nlm.nih.gov/'+encodeURIComponent(x.value)+'/':x.type==='doi'?'https://doi.org/'+encodeURIComponent(x.value):null;
  return url?`<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(x.type.toUpperCase())} ${esc(x.value)} ↗</a>`:`<span>${esc(x.type)} ${esc(x.value)}</span>`;
 }).join(' · ');
 return `<h3>인용한 원전 · ${esc(result.title??result.pmc_id)}</h3><p>이 목록은 현재 논문이 인용한 문헌입니다. 원전을 열어 대상·조건과 실제 결과를 확인할 수 있습니다.</p>${button('article-section','본문으로 돌아가기','data-offset="0"','small')}${result.selected_reference_ids?.length?button('article-references','전체 참고문헌 보기','data-reference-ids="[]"','small'):''}${result.unresolved_reference_ids?.length?`<p class="notice-inline">목록에서 확인되지 않은 원 ID: ${esc(result.unresolved_reference_ids.join(', '))}</p>`:''}${result.rows.map(r=>`<article class="article-block"><div class="small muted">${esc(r.original_label??r.reference_id??'원 번호 없음')}</div><p>${esc(r.display_citation??r.text)}</p><p>${links(r)}</p><div class="detail-actions">${r.citation_contexts.map(c=>button('article-section',esc(c.section||'본문')+' · 인용 문맥 확인',`data-offset="${c.offset}"`,'small')).join('')}</div></article>`).join('')}<div class="pagination"><span>현재 선택의 ${result.rows.length?result.offset+1:0}–${result.offset+result.rows.length} / ${result.total_rows}개 · 원 목록 ${result.source_total_references}개</span><div>${button('article-references','앞 참고문헌',`data-reference-ids="${esc(ids)}" data-offset="${Math.max(0,result.offset-30)}" ${result.offset===0?'disabled':''}`,'small')}${button('article-references','뒤 참고문헌',`data-reference-ids="${esc(ids)}" data-offset="${result.offset+30}" ${!result.has_more?'disabled':''}`,'small')}</div></div><p class="limit">인용 목록과 연결을 확인한 것이며, 인용된 문헌의 읽기·주장 검증을 완료한 것은 아닙니다.</p>`;
}


;
/* Source: article-figures.js */
// Figures of an article the research already read. The caption and the anchor in the source are
// the evidence and come from the stored record; the image is a convenience that is shown only when
// it has actually been retrieved. A figure that was not retrieved says so and still links out.

function articleFigureCaption(text) {
  // Publishers prepend "Figure 3" and append a boilerplate accessibility line; both are noise here.
  const clean = String(text || '').replace(/For image description[^]*$/i, '').trim();
  const match = /^((?:Figure|Fig\.?|Table)\s*\d+[.:]?)\s*([^]*)$/i.exec(clean);
  return match ? {label: match[1].trim(), body: match[2].trim()} : {label: '', body: clean};
}

function articleFigureImage(figure, workspaceId, artifactId) {
  const full = (figure.available || []).find(a => a.cached && !/\.gif$/i.test(a.file))
    || (figure.available || []).find(a => a.cached);
  if (!full) {
    return `<p class="small muted">그림 파일은 아직 회수되지 않았습니다. 아래 원문 위치에서 확인할 수 있습니다.</p>`;
  }
  const source = `/api/workspaces/${encodeURIComponent(workspaceId)}/artifacts/${
    encodeURIComponent(artifactId)}?figure=${encodeURIComponent(full.file)}`;
  const {label, body} = articleFigureCaption(figure.caption);
  return `<img class="article-figure-image" loading="lazy" src="${esc(deploymentURL(source))}"
    alt="${esc([label, body].filter(Boolean).join(' ').slice(0, 300))}">`;
}

function articleFiguresView(result, workspaceId, artifactId) {
  const figures = (result && result.figures) || [];
  if (!figures.length) return '';
  const cached = figures.filter(f => (f.available || []).some(a => a.cached)).length;
  const retrieval = result.figure_retrieval || {};
  const retrievalStatus = {failed:'그림 파일 회수를 완료하지 못했습니다.',
    cache_error:'그림 파일 저장 상태를 확인해야 합니다.', started:'이전 그림 회수 작업이 완료되기 전에 중단됐습니다.',
    partial:'일부 그림 파일을 회수했습니다.', not_returned:'이번 공개 응답에는 요청한 그림 파일이 없었습니다.'}[retrieval.status];
  return `<details class="article-figures" open>
    <summary>원문 그림 ${esc(figures.length)}개${cached < figures.length
      ? ` · 회수된 이미지 ${esc(cached)}개` : ''}</summary>
    ${retrievalStatus ? `<p class="small muted">${esc(retrievalStatus)} 저장된 캡션과 원문 위치는 계속 확인할 수 있습니다.</p>` : ''}
    <div class="article-figure-grid">${figures.map(figure => {
      const {label, body} = articleFigureCaption(figure.caption);
      return `<figure class="article-figure">
        ${articleFigureImage(figure, workspaceId, artifactId)}
        <figcaption>
          ${label ? `<strong>${esc(label)}</strong> ` : ''}${esc(body)}
          <span class="small muted">${esc(figure.section || '')}</span>
          ${figure.source_url ? `<a href="${esc(figure.source_url)}" target="_blank"
            rel="noopener noreferrer" class="source-link">원문 위치</a>` : ''}
        </figcaption>
      </figure>`;
    }).join('')}</div>
    <p class="limit">저자가 논문에 실은 그림입니다. 캡션과 원문 위치가 근거이고, 그림 자체는 읽기를
      돕기 위한 것입니다. 이 화면이 그림을 해석하거나 새로 계산하지 않습니다.</p>
  </details>`;
}


;
/* Source: binding-pose.js */
// Preserve the original result while making a local pose-order discrepancy visible.
function bindingPoseEntry(result) {
  const complete = result.rows.some(r => r.status === 'succeeded');
  return `<section class="panel"><h3>점수가 높은 포즈를 그대로 믿어도 될까요?</h3>
    <p>반환된 다른 포즈와 알려진 같은 화합물의 결합 배치를 비교할 수 있습니다. 선택하면 좌표를 유지한 채 다른 점수로 순위를 다시 봅니다.</p>
    ${button('science-pose-dialog','포즈 선택 근거 비교',`data-id="${esc(selected)}" ${complete?'':'disabled'}`,'primary small')}
    <p class="limit">후보의 약효 순위가 아니라, 이 계산에서 어떤 포즈를 후속 해석에 쓸지 확인하는 작업입니다.</p></section>`;
}

async function bindingPoseAction(action, node) {
  if (action === 'science-pose-dialog') {
    const id = node.dataset.id;
    const view = await api(`/api/workspaces/${state.id}/artifacts/${id}?limit=100`);
    const result = view.result;
    const structure = view.meta.arguments?.structure_id;
    if (!structure) throw Error('원 도킹과 연결된 구조 자료가 필요합니다.');
    const recorded = Boolean(result.protocol.receptor_files_sha256?.['receptor.pdbqt']);
    showDialog('원 포즈와 대안 포즈 비교', `<p>원 점수와 포즈를 모두 보존합니다. 같은 화합물의 공결정 배치가 있을 때만 기준 거리를 계산합니다.</p>
      <div class="dock-candidates">${result.rows.map(r => `<label><input type="checkbox" name="pose-candidate" value="${esc(r.candidate_id)}" ${r.status==='succeeded'?'checked':'disabled'}>${esc(r.candidate_id)} · ${esc(r.status==='succeeded'?'계산 완료':'미완료')}</label>`).join('')}</div>
      <label><input id="pose-rescore" type="checkbox" ${recorded?'checked':'disabled'}>고정 포즈의 GNINA 점수도 비교</label>
      <p class="limit">${recorded?'계산한 포즈의 위치를 바꾸지 않습니다. 후보 수에 따라 수 분 걸릴 수 있습니다.':'이전 도킹 결과에는 정확한 수용체 파일이 저장되지 않았습니다. 지금은 기준 배치를 비교할 수 있고, 재점수화하려면 수용체를 보존하는 새 도킹이 필요합니다.'}</p>
      <div class="dialog-actions">${button('science-pose-run','선택 후보 비교하기',`data-id="${esc(id)}" data-structure="${esc(structure)}"`,'primary')}</div>`);
    return;
  }
  if (action !== 'science-pose-run') return;
  const candidate_ids = [...dialog.querySelectorAll('[name="pose-candidate"]:checked')].map(x => x.value);
  if (!candidate_ids.length || candidate_ids.length > 12) throw Error('완료한 후보 1–12개를 선택해 주세요.');
  busy = true; node.disabled = true; actionError = '';
  try {
    await runTool('binding_pose_review', {artifact_id: node.dataset.id, structure_id: node.dataset.structure,
      candidate_ids, run_rescoring: Boolean(document.getElementById('pose-rescore')?.checked)});
    dialog.close(); notice('원 결과를 보존하며 포즈 비교를 시작했습니다. 완료 후 결과로 판단을 갱신할 수 있습니다.');
  } catch (error) { actionError = error.message; notice(error.message); }
  finally { busy = false; render(); }
}

function bindingPoseTable(result) {
  const distance = x => x === null || x === undefined ? '같은 화합물 기준 없음' : `${number(x)} Å`;
  const comparisons = result.candidate_comparisons ?? [];
  const rescore = result.protocol.rescoring;
  const status = {COMPLETED:'완료', NOT_REQUESTED:'선택하지 않음', EXACT_RECORDED_RECEPTOR_MISSING:'원 수용체 보존 필요', FAILED_OUTPUT_PRESERVED:'실패 · 원 출력 보존'}[rescore.status] ?? rescore.status;
  return `<section class="panel"><h3>포즈 선택에서 달라진 점</h3>
    <p>기준 거리의 차이는 결합 배치 재현을, 순위 변화는 점수 함수의 차이를 보여 줍니다. 이것만으로 후보의 효능 순위를 바꾸지는 않습니다.</p>
    <div class="table-scroll"><table><thead><tr><th>후보</th><th>기존 1위의 기준 거리</th><th>반환 포즈 중 가장 가까운 거리</th><th>CNN이 고른 원 순위</th><th>그 포즈의 기준 거리</th></tr></thead>
    <tbody>${comparisons.map(c=>`<tr><td>${esc(c.candidate_id)}</td><td>${distance(c.original_top_native_rmsd_angstrom)}</td><td>${distance(c.closest_returned_native_rmsd_angstrom)}</td><td>${c.cnn_top_original_rank===null?'미계산':`${c.cnn_top_original_rank}위`}</td><td>${c.cnn_top_pose?distance(c.cnn_top_native_rmsd_angstrom):'미계산'}</td></tr>`).join('')}</tbody></table></div>
    <p>고정 포즈 재점수화: <strong>${esc(status)}</strong> · 순위가 달라진 후보 ${result.summary.changed_pose_order_candidates}개</p>
    ${rescore.next_action?`<p class="limit">${esc(rescore.next_action)}</p>`:''}
    <p class="limit">공결정 부위: ${esc(result.protocol.reference_site_id)}. 대체배치는 원 좌표로 각각 비교합니다. 기준을 이용해 포즈를 이동시키거나 새 검색을 하지는 않았습니다.</p>
    ${button('science-review','이 차이로 다음 판단 검토',`data-id="${esc(selected)}" ${busy?'disabled':''}`,'primary small')}</section>
    <details><summary>모든 반환 포즈와 원 점수 보기</summary><div class="table-scroll"><table><thead><tr><th>후보</th><th>원 Vina 순위</th><th>Vina 계산값</th><th>CNN 순위 / 점수</th><th>같은 화합물 기준 거리</th></tr></thead>
    <tbody>${result.rows.map((r,i)=>`<tr><td>${button('row',esc(r.candidate_id),`data-index="${i}"`,'link-button small')}</td><td>${r.original_vina_rank}</td><td>${number(r.original_vina_score_kcal_mol)} kcal/mol</td><td>${r.cnn_rank===null?'미계산':`${r.cnn_rank} / ${number(r.CNNscore)}`}</td><td>${distance(r.nearest_reference_rmsd_angstrom)}</td></tr>`).join('')}</tbody></table></div>
    <p class="limit">CNNscore는 측정 성공 확률이 아닙니다. 같은 입력의 여러 점수를 독립 증거로 합산하지 않습니다.</p>
    <div class="pagination"><span>${result.offset+1}–${result.offset+result.rows.length} / ${result.total_rows} 포즈</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div></details>`;
}


;
/* Source: proposal-table.js */
// Structures this run proposed, and what is known about each one.
//
// Everything on this screen is untested: the structures were assembled from what the research
// retrieved, the number beside them is a model's estimate of a public assay value, and none of
// them has been made. So the card leads with that, and each column says where its value came
// from - which compound was transformed, by what change, how far the result has drifted from the
// compounds the model learned on, and whether the docking comparison kept it.
//
// The verdict the screen must never hide is the refusal: when the activity model could not
// predict compounds whose scaffolds it had not seen, there are no scores at all, and saying so
// is the result.
if (typeof SCIENCE_LABELS !== 'undefined') SCIENCE_LABELS.analogue_proposal = '공개 화합물에서 설계한 후보';

function proposalModelVerdict(result) {
  const model = result.activity_model;
  if (!model) return '';
  const review = model.input_review;
  const preparation = review ? `<p class="small">학습 측정 종류: ${esc(review.selected_endpoint || '확인 중')} ·
    정확한 보고값의 구조 ${esc(review.point_fit_structures)}개 ·
    원자료에 보존한 경계값 ${esc(review.retained_bound_records)}건</p>` : '';
  if (!model.usable) {
    return `<p class="notice-inline proposal-refusal"><strong>활성 평가에 필요한 자료를 확인해 주세요.</strong>
      ${esc(model.meaning || '')}</p>${preparation}`;
  }
  const summary = model.summary || {};
  const sources = Object.entries(summary.sources || {}).map(([name, count]) => `${name} ${count}`).join(' · ');
  return `<div class="proposal-model">
    <p><strong>${review ? '골격을 나눈 공개 활성 자료 예측 시험' : '이전 데이터 처리 방식의 예측 기록 · 재검토 대상'}</strong> · 순위 상관
      ${esc(summary.held_out_spearman)} (기준 ${esc(summary.minimum_spearman_to_use)})</p>
    <p class="small muted">학습 ${esc(summary.trained_on)}개 · 시험 ${esc(summary.held_out)}개 ·
      골격 ${esc(summary.scaffolds)}종 · 자료원 ${esc(sources || '기록 없음')}
      ${summary.pooled_assay_types && summary.pooled_assay_types.length
        ? ` · 보고된 측정 종류 ${esc(summary.pooled_assay_types.join(', '))}` : ''}</p>
    ${preparation}<p class="limit">공개 시험 기록을 예측한 값입니다. 후보의 실제 활성은 후속 실험에서 확인합니다.</p></div>`;
}

function proposalSearchTrajectory(result) {
  const search = result.guided_search;
  if (!search) return '';
  if (!search.ran) {
    return `<p class="small muted">점수 유도 탐색은 돌지 않았습니다. ${esc(search.meaning || '')}</p>`;
  }
  const rows = (search.history || []).map(entry => `<tr>
    <td>${esc(entry.round)}</td><td>${esc(entry.proposed)}</td><td>${esc(entry.kept)}</td>
    <td>${entry.best_predicted_p_activity === null || entry.best_predicted_p_activity === undefined
          ? '—' : esc(entry.best_predicted_p_activity)}</td>
    <td>${entry.kept_inside_applicability === undefined ? '—'
          : `${esc(entry.kept_inside_applicability)} / ${esc(entry.kept)}`}</td>
    <td>${entry.median_nearest_training_similarity === null
          || entry.median_nearest_training_similarity === undefined
          ? '—' : esc(entry.median_nearest_training_similarity)}</td></tr>`).join('');
  const summary = search.summary || {};
  return `<details class="proposal-search" data-detail-key="guided-search"><summary>점수를 길잡이로 한 탐색 ${esc(summary.rounds ?? 0)}라운드</summary>
    <div class="table-scroll"><table><thead><tr><th>라운드</th><th>제안</th><th>남김</th>
      <th>최고 예측값</th><th>적용 범위 안</th><th>학습 집합과 유사도(중앙값)</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <p class="small">학습 화합물의 실제 최고값 ${esc(summary.best_measured_p_activity_in_training ?? '—')} ·
      탐색이 남긴 최고 예측값 ${esc(summary.best_predicted_p_activity ?? '—')} ·
      적용 범위 밖 ${esc(summary.kept_outside_applicability ?? 0)}개</p>
    <p class="limit">${esc(search.reading || '')}</p></details>`;
}

function proposalRows(result) {
  const rows = (result.guided_search && result.guided_search.ran && result.guided_search.rows.length)
    ? result.guided_search.rows : (result.rows || []);
  if (!rows.length) return '<p>제안된 구조가 없습니다.</p>';
  const comparison = ((result.proposal_comparison || {}).rows || [])
    .reduce((all, row) => Object.assign(all, {[row.candidate_id]: row}), {});
  const scored = rows.some(row => row.predicted_p_activity !== undefined);
  const compared = Object.keys(comparison).length > 0;
  const oldPredictions = result.activity_model && !result.activity_model.input_review;
  const cell = row => {
    const docked = comparison[row.candidate_id];
    return `<tr>
      <td>${typeof structureThumb === 'function' && row.smiles
            ? structureThumb({smiles: row.smiles, depiction: row.depiction}) : ''}
        <code class="proposal-smiles">${esc(row.smiles)}</code></td>
      <td>${esc(row.transformed_from || row.core_from || '—')}
        ${row.transformation ? `<small class="mono">${esc(row.transformation)}</small>` : ''}
        ${row.context_radius ? `<small class="muted">문맥 반경 ${esc(row.context_radius)}</small>` : ''}</td>
      <td>${esc(row.MolWt ?? '—')}<small class="muted">SA ${esc(row.SA_score ?? '—')} · QED ${esc(row.QED ?? '—')}</small></td>
      ${scored ? `<td>${row.predicted_p_activity === undefined ? '—' : esc(row.predicted_p_activity)}
        ${row.inside_applicability === false
          ? '<small class="proposal-outside">적용 범위 밖 · 외삽</small>'
          : row.nearest_training_similarity !== undefined
            ? `<small class="muted">학습 유사도 ${esc(row.nearest_training_similarity)}</small>` : ''}</td>` : ''}
      ${compared ? `<td>${docked ? (docked.keep === true ? '<strong>계산 비교 기준 통과</strong>'
                      : docked.keep === false ? '계산 비교 기준 미충족' : '비교 보류')
                   : '<span class="muted">계산 기록 없음</span>'}
        ${docked && docked.reason ? `<small class="muted">${esc(docked.reason)}</small>` : ''}</td>` : ''}</tr>`;
  };
  return `<div class="table-scroll"><table class="proposal-table"><thead><tr>
      <th>설계 구조</th><th>무엇을 바꿨나</th><th>계산 물성</th>${scored ? `<th>${oldPredictions ? '이전 활성 예측 · 재검토 대상' : '예측 활성'}</th>` : ''}
      ${compared ? '<th>출발 화합물과의 계산상 포즈 비교</th>' : ''}</tr></thead><tbody>${rows.map(cell).join('')}</tbody></table></div>`;
}

function proposalTable(result) {
  const summary = result.summary || {};
  const generator = result.generator || {};
  const database = generator.fragment_database;
  return `<section class="proposal-result">
    <p class="notice-inline"><strong>회수한 화합물에서 계산으로 제안한 구조입니다.</strong>
      출발 화합물 구조와 변형 내용을 따라가며, 합성·활성 확인은 후속 실험으로 연결합니다.</p>
    <p class="small">생성 방식: ${esc(generator.method || result.method || '기록 없음')}
      ${database ? ` · 조각 사전은 이 실행이 회수한 화합물 ${esc(database.compounds)}개로 그때 만들었습니다(문맥 반경 ${esc((database.radii || []).join(', '))})` : ''}
      ${result.generator_error ? ` · 첫 생성기가 실패해 대체 방식으로 돌았습니다: ${esc(result.generator_error)}` : ''}</p>
    <p class="small muted">회수 구조 ${esc(summary.retrieved_inputs ?? '—')}개 → 열거 ${esc(summary.enumerated ?? '—')}개 →
      필터 통과 ${esc(summary.returned ?? '—')}개
      ${summary.dropped ? ` · 걸러짐: ${esc(Object.entries(summary.dropped).map(([k, v]) => `${({property_window: '물성창', synthetic_accessibility: '합성 난이도', structural_alert: '구조 경보', unstable_motif: '불안정 구조'})[k] || k} ${v}`).join(' · '))}` : ''}</p>
    ${proposalModelVerdict(result)}
    ${proposalRows(result)}
    ${proposalSearchTrajectory(result)}
    ${(result.limits || []).length ? `<details class="proposal-limits"><summary>해석 범위와 다음 확인 ${esc(result.limits.length)}개</summary>
      <ul>${result.limits.map(line => `<li>${esc(line)}</li>`).join('')}</ul></details>` : ''}
  </section>`;
}


;
/* Source: rna-notation.js */
// An oligonucleotide written the way a researcher writes one.
//
// A bare string of A/C/G/U is not a candidate anyone can order, discuss or compare: what makes it
// a real design is the direction, the sugar chemistry at each position and the backbone. The
// product stores those separately (`modifications` with a position and a chemistry, the core's
// chemistry state, the formulation), so the screen showed a bare string and hid the rest in a
// fold, and two designs that differ only in chemistry looked identical.
//
// So the sequence is printed in the common prefix notation - m/f/e/d before the base, `s` for a
// phosphorothioate linkage, 5′ and 3′ on the ends - with a legend of exactly the codes used.
//
// What this does NOT do: it never guesses. A position with no recorded modification is printed
// plain, and a candidate whose core chemistry is `unknown` says so instead of reading as
// unmodified. Notation is not efficacy: nothing here claims a design is stable, deliverable or
// active.
const RNA_CHEMISTRY_CODES = {
  '2-O-Methyl': {code: 'm', name: "2′-O-메틸"},
  '2-Fluoro': {code: 'f', name: "2′-플루오로"},
  '2-O-(2-Methoxyethyl)': {code: 'e', name: "2′-O-(2-메톡시에틸)"},
  '2-Deoxy': {code: 'd', name: "2′-데옥시"},
};
const RNA_CORE_CHEMISTRY = {unknown: '원 수식 미확인', unmodified: '무수식으로 기록됨',
                            modified: '수식 있음으로 기록됨'};

function rnaResidues(sequence, modifications, strand) {
  const cleaned = String(sequence ?? '').toUpperCase().replace(/\s+/g, '');
  const bases = /^[ACGUTN]*$/.test(cleaned) ? cleaned : '';
  const applied = new Map();
  for (const mod of modifications ?? []) {
    if (strand && mod.strand && mod.strand !== strand) continue;
    const at = Number(mod.position_1_based);
    if (Number.isInteger(at) && at >= 1 && at <= bases.length) applied.set(at, mod.chemistry);
  }
  return [...bases].map((base, index) => {
    const chemistry = applied.get(index + 1);
    return {base, chemistry: chemistry ?? null, code: RNA_CHEMISTRY_CODES[chemistry]?.code ?? ''};
  });
}

// `linkages`: positions (1-based, before the residue of that index+1) that carry a
// phosphorothioate. Absent means none recorded, which is not the same as none present.
function rnaNotationText(sequence, options = {}) {
  const residues = rnaResidues(sequence, options.modifications, options.strand);
  if (!residues.length) return '';
  const linkages = new Set((options.phosphorothioate_linkages ?? []).map(Number));
  const body = residues.map((r, i) => (i && linkages.has(i) ? 's' : '') + r.code + r.base).join('');
  return `5′-${body}-3′`;
}

function rnaNotation(sequence, options = {}) {
  const text = rnaNotationText(sequence, options);
  if (!text) return String(sequence ?? '').trim()
    ? '<span class="small muted">저장된 서열을 A·C·G·U(T·N)로 읽을 수 없습니다. 원 기록을 확인하세요.</span>'
    : '<span class="small muted">서열 기록이 없습니다.</span>';
  const residues = rnaResidues(sequence, options.modifications, options.strand);
  const modified = residues.filter(r => r.chemistry).length;
  const note = modified
    ? `${modified}/${residues.length}개 위치에 기록된 수식을 표기했습니다.`
    : options.core_chemistry === 'unmodified'
      ? '수식 없음으로 기록된 서열입니다.'
      : '이 서열에 대한 수식 기록이 없습니다. 무수식이라는 뜻은 아닙니다.';
  return `<code class="rna-notation" data-length="${residues.length}">${esc(text)}</code>`
    + `<span class="small muted rna-notation-note">${residues.length}nt · ${esc(note)}</span>`;
}

function rnaNotationLegend(modifications) {
  const used = [...new Set((modifications ?? []).map(m => m.chemistry))]
    .map(c => RNA_CHEMISTRY_CODES[c]).filter(Boolean);
  if (!used.length) return '';
  return `<p class="small muted rna-legend">표기: ${used.map(u => `<code>${esc(u.code)}</code> ${esc(u.name)}`).join(' · ')}`
    + ` · <code>s</code> 포스포로티오에이트 결합 · 5′→3′ 방향</p>`;
}

// The conditions a sequence was calculated under, on the row rather than inside a fold: the same
// sequence means something different in a different formulation, and an unrecorded condition is
// printed as unrecorded.
function rnaDeliveryLine(row) {
  const parts = [];
  if (row?.source_core_chemistry) parts.push(RNA_CORE_CHEMISTRY[row.source_core_chemistry] ?? row.source_core_chemistry);
  if (row?.chemistry_description) parts.push(row.chemistry_description);
  parts.push(row?.formulation_description ? row.formulation_description : '제형 기록 없음');
  return `<p class="small rna-delivery">조건: ${parts.map(p => esc(p)).join(' · ')}</p>`;
}


;
/* Source: rna-reference-panel.js */
SCIENCE_LABELS.rna_reference_panel='후보별 전사체·버전 대응';

document.addEventListener('change',event=>{
 if(event.target.id==='panel-focus-candidate')focusReferencePanel(event.target.value).catch(error=>notice(error.message));
});

async function focusReferencePanel(candidate){
 const id=selected,wid=state.id;
 offset=0;
 if(!candidate){await readDetail();return}
 const result=await api(`/api/workspaces/${wid}/artifacts/${id}?download=1`);
 if(selected!==id||state.id!==wid)return;
 const rows=result.rows.filter(row=>row.candidate_id===candidate);
 detail={artifact_id:id,result:{...result,rows,panel_focus_candidate:candidate,
   total_rows:rows.length,panel_total_rows:result.rows.length,offset:0,has_more:false}};
 render();
}

async function referencePanelAction(action,node){
 if(action==='science-reference-panel'){
  const view=await api(`/api/workspaces/${state.id}/artifacts/${node.dataset.id}?limit=100`);
  const refs=state.artifacts.filter(a=>['rna_reference','rna_reference_archive'].includes(a.kind)&&a.meta.summary?.requires_transcript_selection===false);
  showDialog('다른 전사체에도 같은 부위가 있을까요?',`<p>비교할 후보와 실제 서열을 선택합니다. 같은 유전자의 전사체 버전별 일치 부위를 계산하며, 조직 발현이나 억제 효과는 별도로 확인합니다.</p>
   <fieldset><legend>후보</legend><div class="dock-candidates">${view.result.rows.map(r=>`<label><input type="checkbox" name="panel-candidate" value="${esc(r.id)}">${esc(r.id)}<code class="sequence-text">${esc(r.guide_5to3)}</code></label>`).join('')}</div></fieldset>
   <fieldset><legend>대조할 전사체 서열</legend><div class="dock-candidates">${refs.map(r=>`<label><input type="checkbox" name="panel-reference" value="${esc(r.id)}">${esc(r.meta.arguments?.ensembl_id??r.title)} · ${esc(r.meta.summary.length)}nt</label>`).join('')||'<p>먼저 RNA 작업에서 필요한 전사체 서열을 받아 주세요.</p>'}</div></fieldset>
   <p class="small muted">선택 밖 isoform·변이는 이번 계산에서 확인하지 않습니다. 같은 전사체의 중복 사본은 하나만 선택하세요.</p>
   <div class="dialog-actions">${button('science-run-reference-panel','선택한 서열에 실제 대조',`data-id="${esc(node.dataset.id)}"`,'primary')}</div>`);
  return;
 }
 busy=true;node.disabled=true;
 try{
  const candidate_ids=[...document.querySelectorAll('input[name="panel-candidate"]:checked')].map(x=>x.value);
  const reference_ids=[...document.querySelectorAll('input[name="panel-reference"]:checked')].map(x=>x.value);
  if(!candidate_ids.length||!reference_ids.length)throw Error('후보와 전사체를 각각 하나 이상 선택해 주세요.');
  await runTool('rna_reference_panel',{artifact_id:node.dataset.id,candidate_ids,reference_ids});
  dialog.close();
 }finally{busy=false;node.disabled=false;render()}
}

function rnaReferencePanelTable(result){
 const statusNames={exact_site_present:'정확 일치 부위 있음',no_exact_site:'정확 일치 없음',unresolved_unknown_bases:'N 염기로 미확정'};
 return `${button('science-context-tissue-dialog','조직 발현 조건 함께 보기',`data-id="${esc(selected)}"`,'primary small')}${button('science-space-dialog','기존 후보 밖의 전체 구간 찾기','','small')}<p class="notice-inline">선택한 ${result.summary.selected_references}개 전사체의 서열 비교 · 조직 발현·효능은 별도 확인</p>
 <label>어떤 후보의 전사체 대응을 볼까요?<select id="panel-focus-candidate"><option value="">전체 ${result.summary.selected_candidates}개 후보 · ${result.summary.comparison_rows}개 비교</option>${result.candidate_summary.map(c=>`<option value="${esc(c.candidate_id)}" ${result.panel_focus_candidate===c.candidate_id?'selected':''}>${esc(c.candidate_id)} · 일치 ${c.references_with_exact_site} / ${result.summary.selected_references}${c.references_unresolved?` · 미확정 ${c.references_unresolved}`:''}</option>`).join('')}</select></label>
 <p class="small muted">일치 개수는 효능 순위가 아닙니다. 전사체 주석과 실제 조직 발현을 함께 확인하세요. 전체 결과는 그대로 보존됩니다.</p>
 <div class="table-scroll"><table><thead><tr><th>후보</th><th>전사체·버전</th><th>일치 상태</th><th>실제 위치 · 1부터</th><th>원 참조</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(r.candidate_id)}</td><td>${esc(r.transcript_id)}.${esc(r.version)}<br><span class="small muted">${esc(r.annotation_biotype??"주석 미확인")}</span></td><td>${esc(statusNames[r.match_status])}${r.unknown_windows?` · 미확정 창 ${r.unknown_windows}개`:''}</td><td>${r.exact_sites.map(s=>`${s.start_1_based}–${s.end_1_based}`).join(', ')||'—'}</td><td>${sourceLinks([r.reference_artifact_id])}</td></tr>`).join('')}</tbody></table></div>
 <p class="limit">일치하지 않는 서열과 미확정 항목도 보존했습니다. 일치 없음은 효과 없음이라는 실험 결과가 아닙니다. 선택 밖 전사체·변이는 아직 미확인입니다.</p>
 <div class="pagination"><span>${result.panel_focus_candidate?'선택 후보 · ':''}${result.offset+1}–${result.offset+result.rows.length} / ${result.total_rows}행</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div>
 <div class="detail-actions">${button('science-review','이 차이로 다음 판단 갱신',`data-id="${esc(selected)}" ${busy?'disabled':''}`,'primary small')}</div>`;
}


;
/* Source: rna-duplex.js */
Object.assign(SCIENCE_LABELS,{rna_duplex:'가이드·보조 가닥 설계안',rna_region_annotation:'RNA 후보의 CDS·UTR 구간',rna_duplex_seed:'가닥별 seed 위치',rna_duplex_transcriptome:'가닥별 긴 상보성 검색',rna_delivery_response:'전달 모형의 시점별 민감도'});
const REGION_NAMES={CDS:'CDS',five_prime_utr:'5′UTR',three_prime_utr:'3′UTR',stop_codon:'종결 코돈',no_region_annotation:'영역 미주석',unresolved_annotation:'참조 대응 미확정'};
function regionLabel(value){return (value??'').split('+').map(x=>REGION_NAMES[x]??x).join(' / ')}
function duplexEntry(){return button('science-duplex-dialog','보조 가닥·말단까지 설계안 비교',`data-id="${esc(selected)}"`,'primary small')}
function duplexCheckBoxes(rows,name,label){return `<fieldset><legend>${label}</legend><div class="dock-candidates">${rows.map(r=>`<label><input type="checkbox" name="${name}" value="${esc(r.id)}">${esc(r.source_candidate_id??r.id)}${r.overhang_variant?` · ${esc(r.overhang_variant)}`:''}<code class="sequence-text">${esc(r.guide_5to3)}</code></label>`).join('')}</div></fieldset>`}
function duplexTable(result){
 return `<p>어느 가닥·어떤 말단을 비교하는지 먼저 확인하세요. 이 결과는 <strong>합성 전 계산안</strong>이며, 기존 가이드 평가를 보존합니다.</p>
 <div class="duplex-grid">${result.rows.map(r=>`<article class="panel duplex-card"><h3>${esc(r.source_candidate_id)} · ${r.overhang_variant==='UU'?'양쪽3′UU':'돌출부 없음'}</h3>
 <dl class="duplex-sequences"><dt>가이드</dt><dd>${rnaNotation(r.guide_5to3,{strand:'guide',modifications:r.modifications,core_chemistry:r.source_core_chemistry,phosphorothioate_linkages:r.guide_phosphorothioate_linkages})}</dd><dt>보조 가닥</dt><dd>${rnaNotation(r.passenger_5to3,{strand:'passenger',modifications:r.modifications,core_chemistry:r.source_core_chemistry,phosphorothioate_linkages:r.passenger_phosphorothioate_linkages})}</dd></dl>${rnaNotationLegend(r.modifications)}${rnaDeliveryLine(r)}
 <p class="small">짝지음 ${r.paired_length}nt · 원 core ${esc(({unknown:'수식 미확인',unmodified:'무수식',modified:'수식 있음'})[r.source_core_chemistry]??r.source_core_chemistry)}</p>
 <p>5bp 말단 에너지 차 <strong>${number(r.guide_minus_passenger_5bp_kcal_mol)} kcal/mol</strong></p>
 <p class="small muted">가이드−보조 가닥의 무수식 모형 대비입니다. 적재율·효능 순위가 아닙니다.</p>
 <details><summary>말단·에너지 계산 조건 보기</summary><p>5′말단: 가이드 ${esc(r.guide_5prime_terminal_state)} / 보조 ${esc(r.passenger_5prime_terminal_state)}</p><p>전체 고정 구조 ${number(r.fixed_duplex.kcal_mol)} kcal/mol · 37°C</p><ul>${r.end_window_contrasts.map(x=>`<li>${x.paired_window}bp 대비: ${number(x.guide_minus_passenger_kcal_mol)} kcal/mol</li>`).join('')}</ul></details>${sourceLinks([r.source_candidate_artifact_id])}</article>`).join('')}</div>
 <div class="detail-actions">${button('science-duplex-long-dialog','보조 가닥의 긴 상보성 확인',`data-id="${esc(selected)}"`,'small')}${button('science-duplex-seed-dialog','보조 가닥의 짧은 seed 확인',`data-id="${esc(selected)}"`,'primary small')}${button('science-review','이 설계안으로 다음 판단 검토',`data-id="${esc(selected)}"`,'small')}</div>`;
}
function duplexSeedTable(result){
 const names={guide:'가이드',passenger:'보조 가닥'};
 return `<p>가닥별 실제3′UTR 위치 검색입니다. 같은 seed를 공유하는 돌출부 계산안은 한 번 검색했습니다. <strong>적재·독성 점수는 아닙니다.</strong></p>
 <div class="table-scroll"><table><thead><tr><th>원 후보·가닥</th><th>seed2–8</th><th>다른 유전자</th><th>m8/8mer 유전자</th><th>간TPM≥1 유전자</th></tr></thead><tbody>${result.candidate_summary.map(r=>{
 const links=result.strand_links.filter(x=>x.calculation_id===r.candidate_id);
 const labels=[...new Set(links.map(x=>`${x.source_candidate_id} · ${names[x.strand_role]}`))];
 return `<tr><td>${labels.map(esc).join('<br>')}<br><span class="small muted">설계 맥락 ${links.length}개</span></td><td><code>${esc(links[0]?.seed_2to8_5to3)}</code></td><td>${r.other_genes.toLocaleString()}</td><td>${r.m8_or8mer_other_genes.toLocaleString()}</td><td>${r.other_genes_with_liver_tpm_at_least['1'].toLocaleString()}</td></tr>`}).join('')}</tbody></table></div>
 <p class="small muted">유전자 중앙TPM은 해당 부위를 가진 isoform의 발현이 아닙니다. 가이드와 보조 가닥의 수를 더해 위험도를 만들지 않습니다.</p>
 <details><summary>반환된 개별 위치 보기</summary><div class="table-scroll"><table><thead><tr><th>검색ID</th><th>유전자</th><th>전사체</th><th>부위</th><th>유형</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(r.candidate_id)}</td><td>${esc(r.gene_symbol||r.gene_id)}</td><td>${esc(r.transcript_id)}</td><td>${r.utr_start_1_based}–${r.utr_end_1_based}</td><td>${esc(r.site_type)}</td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>${result.offset+1}–${result.offset+result.rows.length} / ${result.total_rows}</span>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></details>
 <div class="detail-actions">${button('science-review','가이드 근거와 함께 판단 갱신',`data-id="${esc(selected)}"`,'primary small')}</div>`;
}
function duplexLongTable(result){
 const labels={guide:'가이드',passenger:'보조 가닥'};
 const name=id=>[...new Set(result.strand_links.filter(x=>x.calculation_id===id).map(x=>`${x.source_candidate_id} · ${labels[x.strand_role]} · ${x.strand_5to3.length}nt`))].join(' / ');
 return `<p>돌출부를 포함한 전체 가닥으로 <strong>인간 전사체의 긴 상보성</strong>을 계산했습니다. 짧은seed 검색과 다른 근거이며, 두 결과를 합산해 안전성 점수를 만들지 않습니다.</p>
 <div class="table-scroll"><table><thead><tr><th>원 후보·가닥</th><th>주석 전사체 hit</th><th>다른 유전자</th><th>다른 유전자 최저 에너지</th></tr></thead><tbody>${result.candidate_summary.map(r=>`<tr><td>${esc(name(r.candidate_id))}</td><td>${r.annotated_transcript_hits.toLocaleString()}</td><td>${r.other_genes.toLocaleString()}</td><td>${number(r.best_other_gene_energy_kcal_mol)} kcal/mol</td></tr>`).join('')}</tbody></table></div>
 <p class="small muted">출력 상한 ${number(result.protocol.energy_cutoff_kcal_mol)} kcal/mol. 부위 존재가 적재·억제·독성을 입증하지 않으며 화학수식 에너지는 미반영입니다.</p>
 <details><summary>개별 정렬 위치와 별도 역상보 hit 보기</summary><div class="table-scroll"><table><thead><tr><th>가닥·유전자</th><th>전사체·위치</th><th>에너지</th><th>해석</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(name(r.candidate_id))}<br>${esc(r.gene_symbol||r.gene_id)}</td><td>${esc(r.transcript_id)}<br>${r.target_start_1_based}–${r.target_end_1_based}</td><td>${number(r.energy_kcal_mol)}</td><td>${r.index_strand==='-'?'합성 역상보 색인 · 실제 전사체 아님':r.same_target_gene?'원 표적 유전자':'다른 유전자 · 발현/억제 미확인'}</td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>${result.offset+1}–${result.offset+result.rows.length} / ${result.total_rows}</span>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></details>
 <div class="detail-actions">${button('science-review','짧은seed·기존 근거와 함께 판단 갱신',`data-id="${esc(selected)}"`,'primary small')}</div>`;
}
function deliveryResponseEntry(){return `<section class="panel science-form"><h3>관측 시점에 따라 다음 확인이 달라질까요?</h3><p>공개 마우스 전달 모형에서 탈출·적재·소실의 국소 영향을 비교합니다. 사람TTR 후보의 예측과 구분해 읽습니다.</p>${button('science-response-dialog','시점별 모형 민감도 비교','','small')}</section>`}
function deliveryResponseTable(result){result.focus_endpoint??='protein_suppression_at_24h_percent';return `<p><strong>마우스 AT / GalNAc 원모형</strong> · ${result.summary.dose_mg_kg}mg/kg · ${result.protocol.input.perturbation_factor===1.1?'10%':'5%'} 국소 변화. 사람TTR·새 후보의 효과가 아닙니다.</p>
 <label>보고 싶은 관측<select id="response-endpoint">${[...new Set(result.rows.map(r=>r.endpoint))].map(x=>`<option value="${esc(x)}" ${x===result.focus_endpoint?'selected':''}>${esc(responseEndpoint(x))}</option>`).join('')}</select></label>
 <div class="table-scroll"><table><thead><tr><th>변화시킨 항목</th><th>기준 출력</th><th>파라미터 감소 때</th><th>증가 때</th><th>국소 응답 계수</th></tr></thead><tbody>${result.rows.filter(r=>r.endpoint===result.focus_endpoint).map(r=>`<tr><td>${esc(responseParameter(r.parameter))}</td><td>${number(r.base_effect)}</td><td>${number(r.effect_minus)}</td><td>${number(r.effect_plus)}</td><td>${r.local_response_coefficient===null?'정의되지 않음':number(r.local_response_coefficient)}</td></tr>`).join('')}</tbody></table></div>
 <p class="small muted">계수는 같은 모형·시점의 변화율 비교이며 확률이 아닙니다. 값이 크다고 그 항목이 실제 병목이거나 나머지 후보를 제외해야 한다는 뜻은 아닙니다.</p>${button('science-review','현재 관측과 다음 확인에 연결',`data-id="${esc(selected)}"`,'primary small')}`}
function responseParameter(x){return ({fesc:'endosome 탈출 비율',kdegD:'endosome 분해 속도',kint:'수용체 내재화',Rtot:'수용체 총량',konRISC:'RISC 결합 속도',koffRISC:'RISC 해리 속도',kDR:'RISC 복합체 소실',kdegc:'세포질 siRNA 분해',kdegmRNA:'mRNA turnover',kdegprotein:'단백질 turnover'})[x]??x}
function responseEndpoint(x){const protein=x.startsWith('protein');const match=x.match(/at_(\d+)h/);return `${protein?'단백질':'mRNA'} 감소 · ${match?match[1]+'시간 (%)':'0–1000시간 누적 (%·시간)'}`}
document.addEventListener('change',event=>{if(event.target.id==='response-endpoint'){detail.result.focus_endpoint=event.target.value;render()}});
async function duplexAction(action,node){
 if(action==='science-region-filter'){rnaSpaceSearch={artifact:selected,query:node.dataset.query};offset=0;await readDetail();return}
 if(['science-duplex-dialog','science-duplex-seed-dialog','science-duplex-long-dialog'].includes(action)){
  const r=(await api(`/api/workspaces/${state.id}/artifacts/${node.dataset.id}?limit=100`)).result;
  if(action==='science-duplex-dialog'){
   const ends=(id,label)=>`<label>${label}<select id="${id}"><option value="unspecified">미정</option><option value="hydroxyl">5′OH</option><option value="phosphate">5′phosphate</option><option value="other_unmodeled">기타 · 아래에 설명</option></select></label>`;
   showDialog('어떤 이중가닥으로 이어갈까요?',`<p>가이드 core에 완전 상보인 보조 가닥을 붙이는 계산안입니다. 명시하지 않은 수식·제형은 미정으로 남습니다.</p>${duplexCheckBoxes(r.rows,'duplex-candidate','원 가이드 · 최대6개')}<fieldset><legend>돌출부 비교안</legend><label><input type="checkbox" name="duplex-variant" value="blunt" checked>돌출부 없음</label><label><input type="checkbox" name="duplex-variant" value="UU" checked>양쪽3′UU</label></fieldset><div class="science-fields">${ends('duplex-guide-end','가이드5′말단')}${ends('duplex-passenger-end','보조 가닥5′말단')}</div><label>알려진 수식·위치<input id="duplex-chemistry" placeholder="미정이면 비워 두세요. 예: 가이드7번…"></label><label>알려진 제형·접합<input id="duplex-formulation" placeholder="미정이면 비워 두세요"></label><p class="small muted">적은 화학 조건은 보존하지만 이번 열역학은 무수식37°C 모형입니다.</p>${button('science-duplex-run','설계안·말단 대비 실제 계산',`data-id="${esc(node.dataset.id)}"`,'primary')}`);
  }else {
   const long=action==='science-duplex-long-dialog';
   showDialog(long?'전체 가닥의 긴 상보성을 확인할까요?':'어느 가닥의 짧은seed를 확인할까요?',`${duplexCheckBoxes(r.rows,'duplex-design','설계안')}<label>검색할 가닥<select id="duplex-strand"><option value="passenger">보조 가닥 · 기존 가이드 결과는 유지</option><option value="guide">가이드</option><option value="both">양 가닥</option></select></label><p>${long?'돌출부를 포함한 전체 서열로 인간 전사체를 검색합니다. 서로 다른 전체 가닥은 한 번에12개까지 선택합니다.':'같은seed의 돌출부 변형은 한 번 검색합니다. 기존 가이드 계산이 있으면 보조 가닥만 추가할 수 있습니다.'}</p>${long?'<label>출력 에너지 상한 · kcal/mol<input id="duplex-long-energy" type="number" value="-20" min="-60" max="-1"></label><p class="small muted">상한 밖의 상호작용은 미검토로 남습니다. 화학수식·적재·실제 억제 확률을 계산하지 않습니다.</p>':''}${button(long?'science-duplex-long-run':'science-duplex-seed-run',long?'전체 가닥 실제 정렬':'선택 가닥 실제 seed 검색',`data-id="${esc(node.dataset.id)}"`,'primary')}`);
  }
  return;
 }
 if(action==='science-response-dialog'){
  showDialog('원 모형 안에서 무엇이 영향을 줄까요?',`<p>마우스AT/GalNAc의 관측 시간과 파라미터를 비교합니다. 환자 용량 추천이 아닙니다.</p><label>원 모형 용량<select id="response-dose"><option value="1">1mg/kg</option><option value="5">5mg/kg</option></select></label><label>양방향 국소 변화<select id="response-factor"><option value="1.1">10%</option><option value="1.05">5%</option></select></label><fieldset><legend>변화시킬 모형 항목</legend>${['fesc','kdegD','kint','Rtot','konRISC','koffRISC','kDR','kdegc','kdegmRNA','kdegprotein'].map(x=>`<label><input type="checkbox" name="response-parameter" value="${x}" checked>${responseParameter(x)}</label>`).join('')}</fieldset>${button('science-response-run','RNA·단백질 시간별 응답 계산','','primary')}`);return;
 }
 busy=true;node.disabled=true;
 const checked=name=>[...document.querySelectorAll(`input[name="${name}"]:checked`)].map(x=>x.value);
 try{
  if(action==='science-duplex-run'&&!checked('duplex-candidate').length)throw Error('원 가이드를 하나 이상 선택해 주세요.');
  if(action==='science-duplex-run')await runTool('rna_duplex',{artifact_id:node.dataset.id,candidate_ids:checked('duplex-candidate'),overhang_variants:checked('duplex-variant'),guide_5prime_state:document.querySelector('#duplex-guide-end').value,passenger_5prime_state:document.querySelector('#duplex-passenger-end').value,chemistry_description:document.querySelector('#duplex-chemistry').value,formulation_description:document.querySelector('#duplex-formulation').value});
  if(['science-duplex-seed-run','science-duplex-long-run'].includes(action)&&!checked('duplex-design').length)throw Error('검색할 설계안을 하나 이상 선택해 주세요.');
  if(action==='science-duplex-run'&&!checked('duplex-candidate').length)throw Error('원 가이드를 하나 이상 선택해 주세요.');
  if(action==='science-duplex-seed-run')await runTool('rna_duplex_seed',{artifact_id:node.dataset.id,duplex_ids:checked('duplex-design'),strand:document.querySelector('#duplex-strand').value});
  if(action==='science-duplex-long-run')await runTool('rna_duplex_transcriptome',{artifact_id:node.dataset.id,duplex_ids:checked('duplex-design'),strand:document.querySelector('#duplex-strand').value,energy_cutoff_kcal_mol:Number(document.querySelector('#duplex-long-energy').value)});
  if(action==='science-response-run')await runTool('rna_delivery_response',{dose_mg_kg:Number(document.querySelector('#response-dose').value),parameters:checked('response-parameter'),perturbation_factor:Number(document.querySelector('#response-factor').value)});
  if(action==='science-region-run')await runTool('rna_region_annotation',{artifact_id:node.dataset.id});
  dialog.close();
 }finally{busy=false;node.disabled=false;render()}
}


;
/* Source: rna-author-mod.js */
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


;
/* Source: rna-candidate-space.js */
SCIENCE_LABELS.rna_candidate_space='RNA 전체 후보 구간';
SCIENCE_LABELS.rna_candidate_selection='선택한 RNA 후보 실제 계산';
let rnaSpaceSearch={artifact:null,query:''};

function candidateSpaceQuery(id){
 return rnaSpaceSearch.artifact===id?`&candidate_query=${encodeURIComponent(rnaSpaceSearch.query)}`:'';
}

async function candidateSpaceAction(action,node){
 if(action==='science-space-dialog'){
  const refs=state.artifacts.filter(a=>['rna_reference','rna_reference_archive'].includes(a.kind)&&a.meta.summary?.requires_transcript_selection===false);
  const previous=state.artifacts.filter(a=>['rna_candidate_generation','rna_sequence_evaluation'].includes(a.kind)&&a.meta.result_status==='succeeded');
  showDialog('어느 전사체에서 후보를 찾을까요?',`<p>선택한 참조의 모든 상보 영역을 보존합니다. 후보를 먼저 알 필요는 없습니다. 여러 참조를 고르면 같은 가이드의 모든 출처를 함께 볼 수 있습니다.</p>
   <fieldset><legend>실제 전사체 서열 · 같은 유전자/종/assembly</legend><div class="dock-candidates">${refs.map(a=>`<label><input type="checkbox" name="space-reference" value="${esc(a.id)}" ${node.dataset.reference===a.id?'checked':''}>${esc(a.meta.arguments?.ensembl_id??a.title)} · ${esc(a.meta.summary.length)}nt</label>`).join('')||'<p>먼저 전사체 서열을 받아 주세요.</p>'}</div></fieldset>
   <label>상보 영역 길이 · nt<input id="space-length" type="number" min="19" max="30" value="19"></label>
   <details><summary>이전 평가의 후보 ID도 연결하기 · 선택 사항</summary><div class="dock-candidates">${previous.map(a=>`<label><input type="checkbox" name="space-prior" value="${esc(a.id)}">${esc(artifactName(a.id))}</label>`).join('')||'<p>이전 평가가 없습니다.</p>'}</div><p class="small muted">연결하지 않은 이전 자료도 삭제되지 않습니다.</p></details>
   <p class="small muted">미확인 염기가 있는 창은 미확정으로 남깁니다. 목록 순서는 효능 순위가 아니며, 열역학·비표적·전달은 후보 선택 후 별도로 계산합니다.</p>
   <div class="dialog-actions">${button('science-space-run','전체 구간에서 후보 찾기','','primary')}</div>`);
  return;
 }
 if(action==='science-space-search'){
  rnaSpaceSearch={artifact:selected,query:document.getElementById('space-query').value.trim()};
  offset=0;await readDetail();return;
 }
 if(action==='science-space-pick'){
  const row=detail.result.rows.find(r=>r.id===node.dataset.candidate);
  if(!row)throw Error('후보를 다시 열어 주세요.');
  const origins=[...new Map(row.origins.map(o=>[o.reference_artifact_id,o])).values()];
  showDialog('선택한 후보를 실제로 계산합니다',`<p>${rnaNotation(row.guide_5to3,{strand:'guide',modifications:row.modifications,core_chemistry:row.source_core_chemistry})}</p><p>${row.origins.length}개 원위치가 있는 ${row.length}nt 상보 영역입니다. 후보 선택만으로 효능이 확인되지는 않습니다.</p>
   <label>접근성을 계산할 참조<select id="space-eval-reference">${origins.map(o=>`<option value="${esc(o.reference_artifact_id)}">${esc(o.transcript_id)}.${esc(o.version)} · ${o.start_1_based}–${o.end_1_based}</option>`).join('')}</select></label>
   <label>RNA 수식 상태<select id="space-eval-chemistry"><option value="unknown">미확인 · 무수식 서열 대리 계산</option><option value="unmodified">무수식 RNA</option><option value="modified">수식 있음 · 무수식 서열 대리 계산</option></select></label>
   <label>왜 이 후보를 확인하나요?<textarea id="space-eval-reason" placeholder="예: 기존 후보가 다루지 않은 구간의 접근성과 다른 전사체 대응을 비교하고 싶습니다."></textarea></label>
   <details><summary>모든 원위치·기존 계산 연결</summary>${candidateOriginDetails(row)}</details>
   <div class="dialog-actions">${button('science-space-evaluate','선택 후보 실제 계산',`data-id="${esc(selected)}" data-candidate="${esc(row.id)}"`,'primary')}</div>`);
  return;
 }
 busy=true;node.disabled=true;
 try{
  if(action==='science-space-run'){
   const reference_ids=[...document.querySelectorAll('[name="space-reference"]:checked')].map(x=>x.value);
   if(!reference_ids.length)throw Error('실제 전사체 서열을 하나 이상 선택해 주세요.');
   const prior_candidate_artifact_ids=[...document.querySelectorAll('[name="space-prior"]:checked')].map(x=>x.value);
   if(prior_candidate_artifact_ids.length>20)throw Error('한 번에 연결할 이전 평가를20개 이내로 골라 주세요. 원 결과는 모두 보존됩니다.');
   await runTool('rna_candidate_space',{reference_ids,paired_length:Number(document.getElementById('space-length').value),prior_candidate_artifact_ids});
  }else if(action==='science-space-evaluate'){
   const reason=document.getElementById('space-eval-reason').value.trim();
   if(!reason)throw Error('선택 이유를 남겨 주세요.');
   await runTool('rna_candidate_selection',{artifact_id:node.dataset.id,candidate_ids:[node.dataset.candidate],reference_id:document.getElementById('space-eval-reference').value,chemistry:document.getElementById('space-eval-chemistry').value,reason});
  }
  dialog.close();notice('작업을 시작했습니다. 원 후보와 기존 결과는 보존됩니다.');
 }finally{busy=false;node.disabled=false;render()}
}

function candidateOriginDetails(row){
 return `<ul>${row.origins.map(o=>`<li>${esc(o.transcript_id)}.${esc(o.version)} · ${o.start_1_based}–${o.end_1_based}${o.annotated_region?` · ${esc(regionLabel(o.annotated_region))}`:''} ${sourceLinks([o.reference_artifact_id])}</li>`).join('')}</ul>
 ${row.prior_evaluations.length?`<p>기존 평가: ${row.prior_evaluations.map(p=>`${esc(p.candidate_id)} ${sourceLinks([p.artifact_id])}`).join(' · ')}</p>`:'<p>이번 열거에 연결한 이전 평가 없음 · 효능 미평가</p>'}`;
}

function rnaSelectedCandidateSummary(result){
 const s=result.selection;
 return `<section class="panel"><h3>이 후보를 고른 이유</h3><p>${esc(s.reason)}</p>
  <p class="small muted">전체 ${s.source_pool_summary.unique_guide_sequences.toLocaleString()}개 서열 중 ${s.selected_candidate_ids.length}개를 이번 조건에서 실제 계산했습니다. 나머지 후보와 이전 결과는 보존됩니다.</p>
  <p>참조 ${esc(result.reference.transcript_id)}.${esc(result.reference.version)} · ${sourceLinks([s.reference_artifact_id])}</p></section>`;
}

function rnaCandidateSpaceTable(result){
 const s=result.summary;
 return `<p class="notice-inline">${s.selected_references}개 전사체의 ${s.known_base_origins.toLocaleString()}개 원위치 → ${s.unique_guide_sequences.toLocaleString()}개 가이드 서열</p>
  <p>모든 알려진 염기의 구간을 보존했습니다. 목록은 효능 순위가 아닙니다. 후보를 골라 실제 계산하고, 그 결과로 다음 판단을 갱신할 수 있습니다.</p>
  ${result.region_annotation?`<p>같은 버전의 기능 영역을 원위치별로 연결했습니다.</p><div class="detail-actions">${[['three_prime_utr','3′UTR 포함'],['five_prime_utr','5′UTR 포함'],['CDS','CDS 포함'],['','전체']].map(([query,label])=>button('science-region-filter',label,`data-query="${query}"`,'small')).join('')}</div>`:button('science-region-run','CDS·UTR 영역 확인',`data-id="${esc(selected)}"`,'small')}
  <label>후보 ID·서열·전사체·위치·영역으로 찾기<input id="space-query" value="${esc(result.candidate_query??'')}" placeholder="예: ENST00000237014:100-118 또는 가이드 서열"></label>
  ${button('science-space-search','전체 보존 후보에서 찾기','','small')}
  <p class="small muted">현재 ${result.total_rows.toLocaleString()}개 표시 대상 / 전체 ${s.unique_guide_sequences.toLocaleString()}개 · 미확인 염기 창 ${s.unknown_base_windows}개 · 선택 밖 참조는 미검색</p>
  <div class="table-scroll"><table><thead><tr><th>가이드 · 5′→3′</th><th>출처·이전 평가</th><th>현재 상태</th><th>다음 작업</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${rnaNotation(r.guide_5to3,{strand:'guide',modifications:r.modifications,core_chemistry:r.source_core_chemistry})}<small>${esc(r.id)}</small></td><td><details><summary>${r.origins.length}개 원위치 · 이전 평가 ${r.prior_evaluations.length}개</summary>${candidateOriginDetails(r)}</details></td><td>서열 열거 완료<br><span class="small muted">효능·조직 발현 미평가</span></td><td>${button('science-space-pick','이 후보 계산',`data-candidate="${esc(r.id)}"`,'small')}</td></tr>`).join('')}</tbody></table></div>
  ${!result.rows.length?'<p>일치하는 후보가 없습니다. 검색 조건 밖 후보도 모두 보존되어 있습니다.</p>':''}
  <div class="pagination"><span>${result.rows.length?result.offset+1:0}–${result.offset+result.rows.length} / ${result.total_rows}개</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div>
  <p class="limit">상보 영역의 목록이며 완성 siRNA 설계가 아닙니다. 선택한 후보의 접근성·전사체 대응·비표적을 따로 확인하세요.</p>`;
}


;
/* Source: rna-tissue-options.js */
// Official GTEx dataset/tissueSiteDetail snapshot; exact source responses retained in the research audit.
const rnaTissueOptions={"gtex_v8":[{"id":"Adipose_Subcutaneous","label":"Adipose - Subcutaneous"},{"id":"Adipose_Visceral_Omentum","label":"Adipose - Visceral (Omentum)"},{"id":"Adrenal_Gland","label":"Adrenal Gland"},{"id":"Artery_Aorta","label":"Artery - Aorta"},{"id":"Artery_Coronary","label":"Artery - Coronary"},{"id":"Artery_Tibial","label":"Artery - Tibial"},{"id":"Bladder","label":"Bladder"},{"id":"Brain_Amygdala","label":"Brain - Amygdala"},{"id":"Brain_Anterior_cingulate_cortex_BA24","label":"Brain - Anterior cingulate cortex (BA24)"},{"id":"Brain_Caudate_basal_ganglia","label":"Brain - Caudate (basal ganglia)"},{"id":"Brain_Cerebellar_Hemisphere","label":"Brain - Cerebellar Hemisphere"},{"id":"Brain_Cerebellum","label":"Brain - Cerebellum"},{"id":"Brain_Cortex","label":"Brain - Cortex"},{"id":"Brain_Frontal_Cortex_BA9","label":"Brain - Frontal Cortex (BA9)"},{"id":"Brain_Hippocampus","label":"Brain - Hippocampus"},{"id":"Brain_Hypothalamus","label":"Brain - Hypothalamus"},{"id":"Brain_Nucleus_accumbens_basal_ganglia","label":"Brain - Nucleus accumbens (basal ganglia)"},{"id":"Brain_Putamen_basal_ganglia","label":"Brain - Putamen (basal ganglia)"},{"id":"Brain_Spinal_cord_cervical_c-1","label":"Brain - Spinal cord (cervical c-1)"},{"id":"Brain_Substantia_nigra","label":"Brain - Substantia nigra"},{"id":"Breast_Mammary_Tissue","label":"Breast - Mammary Tissue"},{"id":"Cells_EBV-transformed_lymphocytes","label":"Cells - EBV-transformed lymphocytes"},{"id":"Cells_Cultured_fibroblasts","label":"Cells - Cultured fibroblasts"},{"id":"Cervix_Ectocervix","label":"Cervix - Ectocervix"},{"id":"Cervix_Endocervix","label":"Cervix - Endocervix"},{"id":"Colon_Sigmoid","label":"Colon - Sigmoid"},{"id":"Colon_Transverse","label":"Colon - Transverse"},{"id":"Esophagus_Gastroesophageal_Junction","label":"Esophagus - Gastroesophageal Junction"},{"id":"Esophagus_Mucosa","label":"Esophagus - Mucosa"},{"id":"Esophagus_Muscularis","label":"Esophagus - Muscularis"},{"id":"Fallopian_Tube","label":"Fallopian Tube"},{"id":"Heart_Atrial_Appendage","label":"Heart - Atrial Appendage"},{"id":"Heart_Left_Ventricle","label":"Heart - Left Ventricle"},{"id":"Kidney_Cortex","label":"Kidney - Cortex"},{"id":"Kidney_Medulla","label":"Kidney - Medulla"},{"id":"Liver","label":"Liver"},{"id":"Lung","label":"Lung"},{"id":"Minor_Salivary_Gland","label":"Minor Salivary Gland"},{"id":"Muscle_Skeletal","label":"Muscle - Skeletal"},{"id":"Nerve_Tibial","label":"Nerve - Tibial"},{"id":"Ovary","label":"Ovary"},{"id":"Pancreas","label":"Pancreas"},{"id":"Pituitary","label":"Pituitary"},{"id":"Prostate","label":"Prostate"},{"id":"Skin_Not_Sun_Exposed_Suprapubic","label":"Skin - Not Sun Exposed (Suprapubic)"},{"id":"Skin_Sun_Exposed_Lower_leg","label":"Skin - Sun Exposed (Lower leg)"},{"id":"Small_Intestine_Terminal_Ileum","label":"Small Intestine - Terminal Ileum"},{"id":"Spleen","label":"Spleen"},{"id":"Stomach","label":"Stomach"},{"id":"Testis","label":"Testis"},{"id":"Thyroid","label":"Thyroid"},{"id":"Uterus","label":"Uterus"},{"id":"Vagina","label":"Vagina"},{"id":"Whole_Blood","label":"Whole Blood"}],"gtex_v10":[{"id":"Adipose_Subcutaneous","label":"Adipose - Subcutaneous"},{"id":"Adipose_Visceral_Omentum","label":"Adipose - Visceral (Omentum)"},{"id":"Adrenal_Gland","label":"Adrenal Gland"},{"id":"Artery_Aorta","label":"Artery - Aorta"},{"id":"Artery_Coronary","label":"Artery - Coronary"},{"id":"Artery_Tibial","label":"Artery - Tibial"},{"id":"Bladder","label":"Bladder"},{"id":"Brain_Amygdala","label":"Brain - Amygdala"},{"id":"Brain_Anterior_cingulate_cortex_BA24","label":"Brain - Anterior qcingulate cortex (BA24)"},{"id":"Brain_Caudate_basal_ganglia","label":"Brain - Caudate (basal ganglia)"},{"id":"Brain_Cerebellar_Hemisphere","label":"Brain - Cerebellar Hemisphere"},{"id":"Brain_Cerebellum","label":"Brain - Cerebellum"},{"id":"Brain_Cortex","label":"Brain - Cortex"},{"id":"Brain_Frontal_Cortex_BA9","label":"Brain - Frontal Cortex (BA9)"},{"id":"Brain_Hippocampus","label":"Brain - Hippocampus"},{"id":"Brain_Hypothalamus","label":"Brain - Hypothalamus"},{"id":"Brain_Nucleus_accumbens_basal_ganglia","label":"Brain - Nucleus accumbens (basal ganglia)"},{"id":"Brain_Putamen_basal_ganglia","label":"Brain - Putamen (basal ganglia)"},{"id":"Brain_Spinal_cord_cervical_c-1","label":"Brain - Spinal cord (cervical c-1)"},{"id":"Brain_Substantia_nigra","label":"Brain - Substantia nigra"},{"id":"Breast_Mammary_Tissue","label":"Breast - Mammary Tissue"},{"id":"Cells_Cultured_fibroblasts","label":"Cells - Cultured fibroblasts"},{"id":"Cells_EBV-transformed_lymphocytes","label":"Cells - EBV-transformed lymphocytes"},{"id":"Cervix_Ectocervix","label":"Cervix - Ectocervix"},{"id":"Cervix_Endocervix","label":"Cervix - Endocervix"},{"id":"Colon_Sigmoid","label":"Colon - Sigmoid"},{"id":"Colon_Transverse","label":"Colon - Transverse"},{"id":"Esophagus_Gastroesophageal_Junction","label":"Esophagus - Gastroesophageal Junction"},{"id":"Esophagus_Mucosa","label":"Esophagus - Mucosa"},{"id":"Esophagus_Muscularis","label":"Esophagus - Muscularis"},{"id":"Fallopian_Tube","label":"Fallopian Tube"},{"id":"Heart_Atrial_Appendage","label":"Heart - Atrial Appendage"},{"id":"Heart_Left_Ventricle","label":"Heart - Left Ventricle"},{"id":"Kidney_Cortex","label":"Kidney - Cortex"},{"id":"Kidney_Medulla","label":"Kidney - Medulla"},{"id":"Liver","label":"Liver"},{"id":"Lung","label":"Lung"},{"id":"Minor_Salivary_Gland","label":"Minor Salivary Gland"},{"id":"Muscle_Skeletal","label":"Muscle - Skeletal"},{"id":"Nerve_Tibial","label":"Nerve - Tibial"},{"id":"Ovary","label":"Ovary"},{"id":"Pancreas","label":"Pancreas"},{"id":"Pituitary","label":"Pituitary"},{"id":"Prostate","label":"Prostate"},{"id":"Skin_Not_Sun_Exposed_Suprapubic","label":"Skin - Not Sun Exposed (Suprapubic)"},{"id":"Skin_Sun_Exposed_Lower_leg","label":"Skin - Sun Exposed (Lower leg)"},{"id":"Small_Intestine_Terminal_Ileum","label":"Small Intestine - Terminal Ileum"},{"id":"Spleen","label":"Spleen"},{"id":"Stomach","label":"Stomach"},{"id":"Testis","label":"Testis"},{"id":"Thyroid","label":"Thyroid"},{"id":"Uterus","label":"Uterus"},{"id":"Vagina","label":"Vagina"},{"id":"Whole_Blood","label":"Whole Blood"}]};


;
/* Source: rna-context.js */
Object.assign(SCIENCE_LABELS,{rna_tissue_context:'조직별 전사체 발현 조건',rna_variant_catalog:'참조 서열의 공개 변이',rna_allele_scenario:'변이 조건에서 후보 다시 비교'});
let rnaVariantSearch={artifact:null,query:''};
let rnaScenarioChoice=null;
const tissueStatusLabels={version_matched_reported:'같은 버전 · 정량 보고',version_matched_zero:'같은 버전 · 중앙값 0',version_mismatch:'버전 다름 · 값 미적용',not_in_returned_quantification:'정량 자료에 없음'};
const alleleEffectLabels={exact_site_lost:'정확 부위 소실',exact_site_gained:'정확 부위 새로 발견',exact_positions_changed:'정확 부위 위치 변경',exact_sites_unchanged:'정확 부위 동일',unresolved_unknown_bases:'미확인 염기로 부재 판단 보류'};

function rnaContextQuery(id){return rnaVariantSearch.artifact===id?`&candidate_query=${encodeURIComponent(rnaVariantSearch.query)}`:''}
function tissueOptionHtml(dataset){return (rnaTissueOptions[dataset]??[]).map(r=>`<option value="${esc(r.id)}" ${r.id==='Liver'?'selected':''}>${esc(r.id==='Liver'?'간 · Liver':r.label)}</option>`).join('')}
function contextPagination(r){return `<div class="pagination"><span>${r.rows.length?r.offset+1:0}–${r.offset+r.rows.length} / ${r.total_rows}행</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!r.has_more?'disabled':'','small')}</div></div>`}
function contextReviewButton(){return `<div class="detail-actions">${button('science-review','이 조건으로 다음 판단 갱신',`data-id="${esc(selected)}" ${busy?'disabled':''}`,'primary small')}</div>`}
function siteText(sites){return sites.map(s=>`${s.start_1_based}–${s.end_1_based}`).join(', ')||'정확 부위 없음'}

document.addEventListener('change',event=>{
 if(event.target.id==='context-dataset')document.getElementById('context-tissue').innerHTML=tissueOptionHtml(event.target.value);
 if(event.target.id==='scenario-evaluation')loadScenarioCandidates(event.target.value).catch(e=>notice(e.message));
});

async function loadScenarioCandidates(id){
 const node=document.getElementById('scenario-candidates');node.innerHTML='후보를 불러오는 중…';
 if(!id){node.innerHTML='비교할 기존 계산을 먼저 선택하세요.';return}
 const view=await api(`/api/workspaces/${state.id}/artifacts/${id}?limit=100`);
 if(document.getElementById('scenario-evaluation')?.value!==id)return;
 node.innerHTML=view.result.rows.map(r=>`<label><input type="checkbox" name="scenario-candidate" value="${esc(r.id)}">${esc(r.id)}<code class="sequence-text">${esc(r.guide_5to3)}</code></label>`).join('')+
  (view.result.has_more?'<p>현재 첫100개를 표시합니다. 나머지는 원 계산에 보존되며 도구에서 ID를 지정해 비교할 수 있습니다.</p>':'');
}

async function rnaContextAction(action,node){
 if(action==='science-context-tissue-dialog'){
  showDialog('이 후보의 전사체가 어느 조직에서 보고됐나요?',`<p>서열 대응 결과에 조직별 전사체 정량을 나란히 붙입니다. 데이터셋의 주석 버전부터 확인하며, 중앙값0·다른 버전·자료 없음을 구별합니다.</p>
   <label>정량 데이터셋<select id="context-dataset"><option value="gtex_v10">GTEx v10</option><option value="gtex_v8">GTEx v8 · 이전 주석 비교</option></select></label>
   <label>조직<select id="context-tissue">${tissueOptionHtml('gtex_v10')}</select></label>
   <p class="small muted">공여자의 bulk 조직 전사체 중앙 TPM입니다. 질환 세포·개별 환자의 억제 범위나 단백질 기여율이 아닙니다.</p>
   <div class="dialog-actions">${button('science-context-tissue-run','조직 근거 연결',`data-id="${esc(node.dataset.id)}"`,'primary')}</div>`);return;
 }
 if(action==='science-context-variant-dialog'){
  const refs=state.artifacts.filter(a=>['rna_reference','rna_reference_archive'].includes(a.kind)&&a.meta.summary?.requires_transcript_selection===false);
  showDialog('어느 참조의 변이 조건을 확인할까요?',`<p>보존 전사체의 exon 좌표와 공개 변이를 연결합니다. 변이 이름을 미리 알 필요는 없습니다. REF가 맞는 변이를 골라 별도의 서열 시나리오로 비교할 수 있습니다.</p>
   <label>실제 전사체 참조<select id="context-variant-reference">${refs.map(r=>`<option value="${esc(r.id)}" ${r.id===node.dataset.reference?'selected':''}>${esc(r.meta.arguments?.ensembl_id??r.title)} · ${esc(r.meta.summary.length)}nt</option>`).join('')}</select></label>
   <p class="small muted">인간 GRCh38·Ensembl115의 같은 버전 GTF가 필요합니다. 한 번에250kb 이하 전사체 영역을 조회하며, 환자 유전자형을 추정하지 않습니다.</p>
   <div class="dialog-actions">${button('science-context-variant-run','공개 변이 확인','','primary')}</div>`);return;
 }
 if(action==='science-context-variant-search'){
  rnaVariantSearch={artifact:selected,query:document.getElementById('variant-query').value.trim()};offset=0;await readDetail();return;
 }
 if(action==='science-context-scenario-dialog'){
  const row=detail.result.rows.find(r=>r.variant_key===node.dataset.variant);
  if(!row||row.mapping.status!=='ref_verified')throw Error('REF를 확인한 변이 행을 다시 선택해 주세요.');
  rnaScenarioChoice={catalog_id:selected,variant_key:row.variant_key};
  const evaluations=state.artifacts.filter(a=>['rna_sequence_evaluation','rna_candidate_generation'].includes(a.kind)&&a.meta.result_status==='succeeded');
  showDialog('이 변이 조건에서 후보를 다시 비교합니다',`<p><strong>${esc(row.variant_id)}</strong> · ${esc(row.source_record.seq_region_name)}:${row.source_record.start}–${row.source_record.end} · REF ${esc(row.source_record.alleles[0])}</p>
   <label>비교할 ALT · 공개 기록의 가닥 기준<select id="scenario-alt">${row.mapping.available_alternates.map(a=>`<option value="${esc(a)}">${esc(a==='-'?'삭제 (-)':a)}</option>`).join('')}</select></label>
   <label>후보를 가져올 기존 계산<select id="scenario-evaluation"><option value="">계산 결과 선택</option>${evaluations.map(a=>`<option value="${esc(a.id)}">${esc(artifactName(a.id))}</option>`).join('')}</select></label>
   <fieldset><legend>다시 대조할 후보 · 원 결과와 다른 후보도 유지</legend><div id="scenario-candidates" class="dock-candidates">기존 계산을 선택하면 후보가 나타납니다.</div></fieldset>
   <label>이 조건을 확인하려는 이유<textarea id="scenario-reason" placeholder="예: 삭제 때문에 원 후보의 부위가 없어지는지, 온전한 하류 부위는 위치만 바뀌는지 비교합니다."></textarea></label>
   <p class="small muted">연구자/환자의 관측이 아닌 공개 단일 allele 서열 시나리오입니다. 원 참조를 덮어쓰지 않으며, 정확 부위가 없다는 결과는 억제 실패 판정이 아닙니다.</p>
   <div class="dialog-actions">${button('science-context-scenario-run','원 참조와 변이 조건 실제 비교','','primary')}</div>`);return;
 }
 busy=true;node.disabled=true;
 try{
  if(action==='science-context-tissue-run')await runTool('rna_tissue_context',{artifact_id:node.dataset.id,dataset:document.getElementById('context-dataset').value,tissue:document.getElementById('context-tissue').value});
  else if(action==='science-context-variant-run')await runTool('rna_variant_catalog',{artifact_id:document.getElementById('context-variant-reference').value});
  else if(action==='science-context-scenario-run'){
   const ids=[...document.querySelectorAll('[name="scenario-candidate"]:checked')].map(x=>x.value),reason=document.getElementById('scenario-reason').value.trim();
   if(!ids.length||!reason)throw Error('비교할 후보와 이유를 선택해 주세요.');
   await runTool('rna_allele_scenario',{...rnaScenarioChoice,artifact_id:document.getElementById('scenario-evaluation').value,variant_key:rnaScenarioChoice.variant_key,alternate:document.getElementById('scenario-alt').value,candidate_ids:ids,reason});
  }
  dialog.close();notice('실제 근거 조회·계산을 시작했습니다. 원 참조·결과는 보존합니다.');
 }finally{busy=false;node.disabled=false;render()}
}

function rnaTissueTable(r){
 const s=r.summary;
 return `<p class="notice-inline">${esc(s.dataset)} · ${esc(s.tissue)} · ${s.selected_references}개 선택 전사체</p>
  <p>후보의 서열 일치와 조직 정량은 다른 확인입니다. 같은 버전의 정량만 붙이며, 다른 버전의 원값도 펼쳐 볼 수 있습니다.</p>
  <p class="small">${Object.entries(s.transcript_status_counts).map(([k,v])=>`${esc(tissueStatusLabels[k])} ${v}개`).join(' · ')}</p>
  <div class="table-scroll"><table><thead><tr><th>후보</th><th>전사체 · 주석</th><th>정확 부위</th><th>조직 중앙 TPM</th><th>대응 상태·원값</th></tr></thead><tbody>${r.rows.map(x=>`<tr><td>${esc(x.candidate_id)}</td><td>${esc(x.transcript_id)}.${esc(x.version)}<br>${esc(x.annotation_biotype??'미확인')}</td><td>${siteText(x.exact_sites)}</td><td>${x.tissue_context.median_tpm===null?'—':number(x.tissue_context.median_tpm)}</td><td>${esc(tissueStatusLabels[x.tissue_context.status])}<details><summary>왜 이 상태인가요?</summary><p>${esc(x.tissue_context.interpretation)}</p>${x.tissue_context.source_rows.map(a=>`<p>${esc(a.transcriptId)} · ${number(a.median)} ${esc(a.unit)}</p>`).join('')}${sourceLinks([x.reference_artifact_id])}</details></td></tr>`).join('')}</tbody></table></div>
  <p class="limit">환자·표본별 표적 보유 비율을 계산하지 않았습니다. 단백질 분비 기여·RISC·전달·기능은 별도 조건입니다.</p>${contextPagination(r)}${contextReviewButton()}`;
}

function rnaVariantTable(r){
 return `<p class="notice-inline">${esc(r.summary.transcript_accession)} · ${esc(r.summary.region)} · ${r.summary.variants_returned}개 공개 변이</p>
  <p>REF 대응 확인 ${r.summary.ref_verified}개 · 미적용 ${r.summary.not_applied}개. 모든 반환행을 보존하며 목록 순서는 추천 순위가 아닙니다.</p>
  <label>변이 ID·위치·적용 상태 검색<input id="variant-query" value="${esc(r.candidate_query??'')}" placeholder="예: rs 번호 또는 ref_verified"></label>${button('science-context-variant-search','보존 변이에서 찾기','','small')}
  <details><summary>참조 exon 좌표와 적용 조건</summary><p>${esc(r.reference.assembly)} · ${esc(r.reference.organism)} · 가닥 ${esc(r.geometry.strand)}</p><ul>${r.geometry.exons.map(e=>`<li>exon ${e.exon_number} · ${esc(e.chromosome)}:${e.start}–${e.end}</li>`).join('')}</ul>${sourceLinks([r.reference_artifact_id])}<p class="small muted">같은 버전·유전자·길이·서열 해시에 연결한 GTF 대응입니다. 환자 서열이나 스플라이싱 결과가 아닙니다.</p></details>
  <div class="table-scroll"><table><thead><tr><th>공개 변이</th><th>유전체 위치 · REF/ALT</th><th>서열 적용</th><th>다음 작업</th></tr></thead><tbody>${r.rows.map(x=>`<tr><td>${esc(x.variant_id)}</td><td>${esc(x.source_record.seq_region_name)}:${x.source_record.start}–${x.source_record.end}<br>${esc(x.source_record.alleles?.join(' / '))}</td><td>${esc(x.mapping.reason)}</td><td>${x.mapping.status==='ref_verified'?button('science-context-scenario-dialog','이 조건으로 비교',`data-variant="${esc(x.variant_key)}"`,'small'):'미적용 · 원행 보존'}</td></tr>`).join('')}</tbody></table></div>
  <p class="limit">공개 목록에 있다고 환자에게 그 변이가 있거나 질환 원인이라는 뜻은 아닙니다. exon 밖·경계 영향과 phase는 별도 검토합니다.</p>${contextPagination(r)}`;
}

function rnaAlleleTable(r){
 return `<p class="notice-inline">${esc(r.summary.variant_id)} · ALT ${esc(r.summary.alternate)} · 별도 단일 allele 시나리오</p><p>${esc(r.selection_reason)}</p>
  <p>원 ${esc(r.reference.transcript_id)}.${esc(r.reference.version)}과 비교 · cDNA 길이 변화 ${r.summary.length_change_nt}nt</p>
  <div class="table-scroll"><table><thead><tr><th>후보</th><th>원 참조의 정확 부위</th><th>시나리오의 정확 부위</th><th>차이</th></tr></thead><tbody>${r.rows.map(x=>`<tr><td>${esc(x.candidate_id)}</td><td>${siteText(x.original.exact_sites)}<details><summary>원 유전체 대응</summary>${x.original_genomic_sites.map(s=>`<p>${s.cdna_site.start_1_based}–${s.cdna_site.end_1_based}: ${s.genomic_blocks.map(b=>`${esc(b.chromosome)}:${b.start_1_based}–${b.end_1_based} (${esc(b.strand)}, exon${b.exon_number})`).join(' + ')}</p>`).join('')}</details></td><td>${siteText(x.scenario.exact_sites)}<br><span class="small muted">알려진 창 최소 불일치 ${x.scenario.minimum_gapless_mismatches??'미확정'}</span></td><td>${esc(alleleEffectLabels[x.effect])}</td></tr>`).join('')}</tbody></table></div>
  <p class="limit">원 참조와 다른 시나리오 좌표입니다. 위치 변경과 정확 부위 소실을 구분하며, 실제 억제·환자 유전자형·스플라이싱 효과는 계산하지 않았습니다.</p>${contextPagination(r)}${contextReviewButton()}`;
}


;
/* Source: intervention-direction.js */
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


;
/* Source: structure-viewer.js */
let moleculeLibrary;
let currentMoleculeViewer;
async function ensureMoleculeLibrary(){
  if(window.$3Dmol)return;
  if(!moleculeLibrary)moleculeLibrary=new Promise((resolve,reject)=>{
    const script=document.createElement('script');script.src=deploymentURL('/vendor/3Dmol-2.5.5.min.js');
    script.onload=()=>window.$3Dmol?resolve():reject(Error('구조 표시 모듈을 확인할 수 없습니다.'));
    script.onerror=()=>{moleculeLibrary=null;reject(Error('로컬 구조 표시 모듈을 불러오지 못했습니다.'))};
    document.head.appendChild(script);
  });
  await moleculeLibrary;
}
async function storedMoleculeArtifact(id){
  const response=await fetch(deploymentURL(`/api/workspaces/${state.id}/artifacts/${encodeURIComponent(id)}?download=1`));
  if(!response.ok)throw Error('저장된 구조 원자료를 불러오지 못했습니다.');
  return response.json();
}
async function openMoleculeView(id,candidate){
  showDialog('실제 좌표로 구조 확인',`<p id="molecule-state" role="status">저장된 좌표를 불러오고 있습니다.</p><div id="molecule-view" aria-label="회전·확대 가능한 분자 구조"></div><div class="detail-actions">${button('molecule-all','전체 구조','','small')}${button('molecule-site','결합 부위','','small')}</div><p class="small">드래그: 회전 · 휠/두 손가락: 확대. <span class="native-legend">주황: 공결정 성분</span> · <span class="computed-legend">파랑: 계산 포즈</span></p><p class="limit">관측 구조와 계산을 원 좌표계에서 겹칩니다. 화면의 가까운 배치만으로 결합·선택성·효능을 판정하지 않습니다. 원점유율·결측·구성체 조건은 구조 자료에 남아 있습니다.</p><p class="small">3Dmol.js 2.5.5 · 로컬 표시 · <a href="/vendor/3Dmol-LICENSE.txt" target="_blank" rel="noopener">라이선스</a></p>`);
  dialog.classList.add('structure-dialog');
  try{
    const item=state.artifacts.find(a=>a.id===id);let structure,pose,site;
    if(item.kind==='molecular_docking'){
      const raw=await storedMoleculeArtifact(id);
      const row=raw.rows.find(r=>r.candidate_id===candidate&&r.status==='succeeded');
      if(!row)throw Error('완료한 후보 포즈가 없습니다.');
      const filename=row.pose_file.replace('-poses.pdbqt','-top.sdf');
      pose=raw.raw_output_files[filename];
      if(!pose)throw Error('원 실행의 포즈 좌표 파일이 없습니다.');
      structure=await storedMoleculeArtifact(item.meta.arguments.structure_id);
      site=raw.protocol.preparation.site;
    }else{
      structure=await storedMoleculeArtifact(id);
      site=structure.rows.find(r=>r.kind==='bound_component'&&r.heavy_atoms>=6);
    }
    if(!structure.original_cif)throw Error('원 구조 좌표를 확인해 주세요.');
    await ensureMoleculeLibrary();
    if(!dialog.open||!document.querySelector('#molecule-view'))return;
    const viewer=$3Dmol.createViewer(document.querySelector('#molecule-view'),{backgroundColor:'#f8fafc',antialias:true});
    const receptor=viewer.addModel(structure.original_cif,'cif',{doAssembly:false});
    const components=structure.rows.filter(r=>r.kind==='bound_component'&&r.heavy_atoms>=6);
    const names=new Set(components.map(r=>r.component));
    // Symmetry-related, fractionally occupied components may overlap. A
    // distance-only display parser must not bond distinct component copies.
    const atoms=receptor.selectedAtoms({}),byIndex=new Map(atoms.map(a=>[a.index,a]));let removed=0;
    for(const a of atoms){
      const keep=a.bonds.map((index,i)=>({index,order:a.bondOrder[i]})).filter(b=>{
        const other=byIndex.get(b.index);
        const separate=other&&names.has(a.resn)&&names.has(other.resn)&&(a.chain!==other.chain||a.resi!==other.resi||a.resn!==other.resn);
        if(separate)removed++;return !separate;
      });a.bonds=keep.map(b=>b.index);a.bondOrder=keep.map(b=>b.order);
    }
    viewer.setStyle({model:0,hetflag:false},{cartoon:{color:'#a7b8c4',opacity:pose?.3:.7}});
    const nativeSelection=site?{model:0,resn:site.component,chain:site.chain,resi:parseInt(site.residue,10)}:{};
    if(site)viewer.setStyle(nativeSelection,{stick:{color:'#d78b20',radius:.19}});
    if(pose){
      viewer.addModel(pose,'sdf');viewer.setStyle({model:1},{stick:{color:'#2365cc',radius:.17}});
      viewer.addStyle({model:0,hetflag:false,within:{distance:5,sel:{model:1}}},{stick:{colorscheme:'grayCarbon',radius:.1}});
    }
    const focus=pose?{model:1}:nativeSelection;
    currentMoleculeViewer={viewer,focus,removed_intercomponent_display_bonds:removed/2};viewer.zoomTo(focus);viewer.zoom(.5);viewer.render();
    document.querySelector('#molecule-state').textContent=`${structure.pdb_id} · 생물학적 조립체 ${structure.assembly_id}${candidate?' · '+candidate+' 최상위 계산 포즈':''} · 좌표 표시 완료${site?' · 공결정 '+site.ligand_id+'만 표시 (점유율 '+site.occupancies.join(', ')+')':''}. 다른 성분 배치와 원좌표는 원자료에 보존됩니다.`;
  }catch(e){const status=document.querySelector('#molecule-state');if(status)status.textContent=e.message;else notice(e.message);}
}
document.addEventListener('click',e=>{
  const action=e.target.closest('[data-action]')?.dataset.action;
  if(!currentMoleculeViewer||!['molecule-all','molecule-site'].includes(action))return;
  const {viewer,focus}=currentMoleculeViewer;viewer.zoomTo(action==='molecule-all'?{}:focus);if(action==='molecule-site')viewer.zoom(.65);viewer.render();
});
document.addEventListener('close',e=>{
  if(e.target.id==='editor'){dialog.classList.remove('structure-dialog');currentMoleculeViewer?.viewer.clear();currentMoleculeViewer=null;}
},true);


;
/* Source: onboarding.js */
// Product guidance and entry points. Guidance is local; scientific results require real jobs.
let intakeMode = 'question', intakeFile = null, intakeContext = '', intakeError = '', actionError = '', submitPhase = '';
let intakeDelimiter = ',', intakeSmiles = 'smiles', intakeId = 'cid';
// null keeps the server's current model. The server rechecks any explicit approved choice.
let chosenModel = null;
function offeredModels(){return [...new Set((status?.gateway?.approved_models??[]).filter(name=>typeof name==='string'&&name))]}
function modelDisplayName(name){return name==='claude-opus-5'?'Claude Opus 5':String(name??'모델 확인 필요')}
function modelEffortLabel(){return status?.gateway?.requested_effort??'설정 확인 필요'}
function modelAccessButton(){
  const g=status?.gateway??{},name=modelDisplayName(g.requested_model),short=name.replace(/^Claude /,'');
  return button('model-help',`${esc(short)} · ${esc(modelEffortLabel())}${g.available?'':' · 확인'}`,`aria-label="모델 이용 안내 · ${esc(name)} · ${esc(modelEffortLabel())}${g.available?' · 연결됨':' · 연결 상태 확인 필요'}" title="모델 이용 안내"`,'quiet small');
}
async function openModelAccessHelp(){
  await refreshGatewayStatus({force:true});
  const g=status.gateway??{},current=modelDisplayName(g.requested_model);
  showDialog('모델 이용 안내',`<dl><dt>현재 연결</dt><dd>${esc(current)} · ${esc(modelEffortLabel())}</dd><dt>연결 상태</dt><dd role="status">${g.available?'사용 가능':esc(g.message??'현재 모델 연결을 확인해야 합니다.')}</dd></dl><p>현재 Claude는 개발자 구독으로 제공 중입니다. 심사·지속 사용은 대회 API 크레딧 확보 후 연결을 권장합니다.</p><p><strong>대회 API · 할당량 소진</strong><br>크레딧 확보와 실제 연결 확인 후 사용할 수 있습니다.</p><details><summary>현재 연결에서 허용된 모델</summary>${list(offeredModels().map(modelDisplayName))||'<p>허용된 모델 확인 필요</p>'}</details>`);
}
function modelChoice(){
  const offered=offeredModels();
  const running=status.gateway?.requested_model,selected=chosenModel??running;
  return `<label class="model-choice">모델
    <select id="intake-model">${offered.map(name=>`<option value="${esc(name)}" ${
      selected===name?'selected':''}>${esc(modelDisplayName(name))}${name===running?' · '+esc(modelEffortLabel()):''}</option>`).join('')}${!offered.includes(selected)?'<option value="" selected disabled>연결 모델 확인 필요</option>':''}<option value="competition-api-unavailable" disabled>대회 API · 할당량 소진</option></select>
  </label>${button('model-help','모델 이용 안내','','quiet small')}`;
}
const ENTRY_PATHS = [
  {id:'molecule',name:'저분자 후보 평가',tag:'이미 후보가 있나요?',input:'후보 ID와 SMILES가 있는 CSV',output:'물성·ADMET, 구조가 있으면 도킹·실험 근거 비교',limit:'물성·ADMET와 알려진 구조 부위의 실제 도킹·포즈 검사를 연결합니다. 측정 활성·선택성 및 세포 효과는 해당 실험 근거로 따로 확인합니다.',example:'cache',workspace:'ws_3668b668abba4d89',placeholder:'어떤 후보를 다음에 검토할지 알고 싶어요. 표적과 선별 조건을 적어 주세요.'},
  {id:'rna',name:'siRNA 실험 결과 해석',tag:'처리 후 결과가 있나요?',input:'유전자별 차등발현 결과표 TSV 또는 TXT.GZ',output:'표적 유전자 변화, 대조군·조건 차이와 다음 확인',limit:'기존 처리표·seed/분포 분석입니다. RNA 서열 작업은 별도 시작 항목을 이용하세요. 효능·조직 전달을 처리표만으로 확정하지 않습니다.',example:'rna',workspace:'ws_97e175bb05cc4ece',placeholder:'표적 유전자, 종·조직, 처리군과 대조군, 지금 해석하려는 질문을 적어 주세요.'},
  {id:'question',name:'연구 질문부터 정리',tag:'어디서 시작할지 고민인가요?',input:'연구 목표, 표적·질환, 알려진 조건이나 궁금한 점',output:'접근·대안의 근거, 필요한 조사·분석과 다음 행동',limit:'자료가 없으면 실제 분석값이나 치료 경로의 우열을 만들어 내지 않습니다.',placeholder:'예: ATTR-CM 연구에서 저분자와 siRNA 접근을 검토하고 싶어요. 현재 확보한 자료는 … 이고, 먼저 결정할 것은 … 입니다.'}
];
ENTRY_PATHS.push({id:'sequence',name:'RNA 서열·후보 검토',tag:'유전자나 가이드가 있나요?',input:'종·표적 유전자 또는 전사체, 가이드 5′→3′ 서열과 수식 여부',output:'버전이 있는 참조, 결합 영역 후보·접근성· 비표적 비교',limit:'후보 뒤에는 전체 전사체 정렬·3′UTR seed/간 발현·탐색용 활성 모델 점수를 연결할 수 있습니다. 화학수식과 전달 효과는 원 조건의 근거·모형과 새 후보를 구별해 검토합니다.',placeholder:'예: 인간 TTR의 공개 전사체를 확인하고 지정 구간에서 RNA 후보를 만들어 접근성을 비교해 주세요. 조직·수식 조건은 … 입니다.'});
const RNA_COLUMNS = ['ensembl_gene_id','baseMean','log2FoldChange','lfcSE','stat','pvalue','padj','symbol'];
// The two cards above open workspaces named in this file, so on any server that does not mount
// those exact ids the panel offered nothing at all - which is what the public demo does, where the
// first two entries in the catalog are a guided example marked "실제 연구 결과 아님" and a
// screen-check fixture, both rebuilt at every start and therefore always holding the newest
// timestamps. This lists the research this server actually holds that reached a published
// judgment, so the first thing a visitor can click is a finished study. Workspaces without a
// judgment are left out: they are mid-run or stopped, and opening one first says nothing about
// what the product does. They remain in the left-hand list.
// The guided walkthrough carries a published judgment too, and it is rebuilt at every start so it
// holds the newest timestamp and would lead this list. It names itself as not a real result, and
// that is the marker used to sort it last rather than a guess about its contents.
const NOT_REAL_RESEARCH = '실제 연구 결과 아님';
function finishedResearch(limit = 6) {
  const done = (projects || []).filter(p => p.has_decision);
  if (!done.length) return '';
  const example = p => (p.title || '').includes(NOT_REAL_RESEARCH) ? 1 : 0;
  done.sort((a, b) => example(a) - example(b));
  const shown = done.slice(0, limit);
  return `<div class="finished-research"><h3>이 서버에 있는 완료된 연구 ${done.length}건</h3>
    <ul>${shown.map(p => `<li><a href="/?workspace=${esc(p.id)}">${esc(p.title)}</a></li>`).join('')}</ul>
    ${done.length > shown.length ? `<p class="small muted">나머지 ${done.length - shown.length}건은 왼쪽 목록에 있습니다.</p>` : ''}
    <p class="small muted">판단이 게시된 연구만 적었습니다. 진행 중이거나 판단 전에 멈춘 연구도 목록에서 열 수 있습니다.</p></div>`;
}
function entryPath(){return ENTRY_PATHS.find(p=>p.id===intakeMode)||ENTRY_PATHS[2]}
function isUsageQuestion(value){
  const text=String(value??'').trim().toLowerCase();
  if(text.length>160)return false;
  const compact=text.replace(/\s+/g,'');
  return /^(이거|여기|이앱|이사이트|이플랫폼|evida|에비다)(는|가|를|을|에서|에)?(어떻게(쓰|써|사용|시작)|뭐하는|무엇을하는|사용법|쓰는법)/.test(compact)
    || /^(어떻게(쓰|써|사용)|사용법|쓰는법|시작하는법)/.test(compact)
    || /^(how (do i|to) use|what (is|does) evida)/.test(text);
}
function usageGuide(question=''){
  // What the four tabs and the five stages are for. Before this the guide never named either,
  // so a reader could not tell why a screen existed or which one answered their question.
  const stages=[
    ['구조화된 질문과 목표','연구자가 적은 원 요청이 맨 위에 그대로 남고, 그 아래에 모델이 구조화한 목표·조건·모르는 것이 놓입니다. 두 가지를 나란히 두어 해석이 맞는지 볼 수 있습니다.'],
    ['기전과 접근','어떤 기전을 겨냥할지 비교합니다. 기록한 축으로 계산한 순서를 보여주고, 하나가 앞선다고 말할 수 없으면 그렇게 적습니다. 추천 1순위를 따를 의무는 없습니다 — 다른 순위를 고르면 그 경로로 연구가 이어집니다.'],
    ['후보 발굴','그 기전을 겨냥할 분자·서열을 실제로 찾아 구조·물성과 함께 보여줍니다. 추천 밖 후보도 목록에 남습니다.'],
    ['근거와 계산','앞 단계의 판단이 어떤 원자료와 계산에서 나왔는지 모읍니다. 임상시험은 1차 종점 값과 이상반응을, 계산은 무엇을 확인했고 수치가 얼마인지를 보여줍니다.'],
    ['EVIDA 실험 권고','연구자가 실제로 할 다음 행동입니다. 측정 대상·조건·비교군·판독 지표와, 결과가 A면 무엇이 바뀌고 B면 무엇이 바뀌는지를 함께 적습니다.'],
  ];
  const tabs=[
    ['연구','위 다섯 단계를 순서대로 봅니다. 평소에는 이 탭만 보면 됩니다.'],
    ['자료','회수한 원자료와 계산 결과를 하나씩 열어 봅니다. 단계에서 본 근거의 원본이 여기 있고, 맨 아래 <strong>직접 조회</strong>를 열면 표적·화합물·RNA를 이름으로 조회하거나 계산을 따로 돌릴 수 있습니다.'],
  ];
  return `<section class="usage-answer" aria-label="EVIDA 사용 안내"><div class="section-mark">사용 안내 · 현재 연결된 기능 기준</div>${question?`<p class="small muted">질문: ${esc(question)}</p>`:''}
    <h2>질환과 바꾸고 싶은 결과부터 적어 주세요.</h2>
    <p>표적도 후보도 정하지 않은 채 시작해도 됩니다. EVIDA가 공개 근거에서 기전을 찾고, 그 기전을 겨냥할 후보를 실제로 회수하거나 생성해, 다음에 해볼 실험까지 이어 줍니다. 이미 후보나 실험 자료가 있다면 그 지점부터 시작할 수도 있습니다.</p>
    <h3>연구 판단의 다섯 단계</h3>
    <ol class="usage-stages">${stages.map(([name,what])=>`<li><strong>${esc(name)}</strong> — ${esc(what)}</li>`).join('')}</ol>
    <p class="small muted">단계는 한 번 지나가면 끝나는 절차가 아닙니다. 새 관측이나 생각을 넣으면 앞 단계로 돌아가 판단이 다시 계산됩니다.</p>
    <h3>두 개의 탭</h3>
    <ul class="usage-tabs">${tabs.map(([name,what])=>`<li><strong>${esc(name)}</strong> — ${what}</li>`).join('')}</ul>
    <p class="small muted">무엇이 언제 바뀌었는지는 오른쪽 위 <strong>변경 기록</strong>에 시간순으로 남습니다.</p>
    <h3>연구자가 개입하는 곳</h3>
    <p>각 단계 아래의 <strong>이 지점에서 개입하기</strong>에 질문·새 관측·조건 정정을 넣습니다. 실험 결과를 넣으면 그 결과로 가설과 순위가 다시 검토됩니다. 추천을 따르지 않고 다른 경로를 골라도 원래 추천과 이유는 그대로 남습니다.</p>
    <p class="limit">화면의 순서와 점수는 기록한 근거를 정리한 것이지 성공 확률이 아닙니다. 확인하지 않은 것은 '미확인'으로 남고 0으로 바뀌지 않습니다. 조회에 실패한 것과 실제로 없는 것은 구분해 표시합니다.</p>
    <p><a href="/team.html">질환만으로 시작한 실제 저분자·siRNA 연구 열기 ↗</a></p>
    <div class="entry-help-actions">${ENTRY_PATHS.map(p=>button('choose-path',esc(p.name),`data-mode="${p.id}"`,'small')).join('')}</div>
    <details><summary>자료 입력용 CACHE·처리표 예제는 무엇인가요?</summary><p><strong>CACHE</strong>는 공개 화합물 발굴 평가 프로젝트의 자료 이름입니다. 여기서는 LRRK2 표적의 기존 후보73개로 물성·예측·실험 관측을 구분하는 흐름을 봅니다. EVIDA 기능명이나 ATTR-CM 치료 후보 세트가 아닙니다. <a href="https://zenodo.org/records/13820554" target="_blank" rel="noopener noreferrer">원자료</a></p><p><strong>처리표 입력용 RNA 예제</strong>는 랫드 간 Ttr 관련 처리표3개를 해석합니다. 첫 화면의 인간 ATTR 질환 출발 예시와 다른 자료입니다. 새 siRNA를 설계하는 기능과는 구분하며, 이 두 예제를 같은 질환의 직접 경로 비교로 사용하지 않습니다.</p></details></section>`;
}
function openUsageHelp(question=''){showDialog('EVIDA 사용 안내',usageGuide(question))}
function renderWelcome(){
  const p=entryPath();
  return `<div class="welcome intake-home"><div class="welcome-heading"><div><span class="eyebrow">연구 시작</span><h1>지금 어떤 일을 확인하고 싶으세요?</h1><p class="description">가진 자료에서 시작해, 다음 연구 판단까지 이어갑니다.</p></div>${button('usage-help','사용법 보기','','quiet small')}</div>
  <div class="entry-paths" role="group" aria-label="시작할 연구 작업">${ENTRY_PATHS.map(item=>`<button type="button" data-action="choose-path" data-mode="${item.id}" class="entry-path ${item.id===intakeMode?'selected':''}" aria-pressed="${item.id===intakeMode}"><span class="eyebrow">${esc(item.tag)}</span><strong>${esc(item.name)}</strong><span>${esc(item.output)}</span></button>`).join('')}</div>
  <section class="intake-panel" aria-label="연구 입력"><div class="intake-contract"><div><span class="section-mark">넣을 것</span><p>${esc(p.input)}</p></div><span aria-hidden="true">→</span><div><span class="section-mark">받을 것</span><p>${esc(p.output)}</p></div></div>
  ${['molecule','rna'].includes(p.id)?`<div class="intake-upload"><label class="input-label" for="intake-file">1. 분석할 파일</label><input type="file" id="intake-file" accept="${p.id==='molecule'?'.csv,.tsv,.txt':'.tsv,.txt,.gz'}"><p id="intake-file-name" class="small muted">${intakeFile?esc(intakeFile.name)+' 선택됨':'파일을 선택하세요. 아직 서버로 전송되지 않습니다.'}</p>${p.id==='molecule'?`<details><summary>CSV 열 이름·구분자 설정</summary><div class="upload-fields"><label>구분자<select id="intake-delimiter"><option value="," ${intakeDelimiter===','?'selected':''}>쉼표</option><option value=";" ${intakeDelimiter===';'?'selected':''}>세미콜론</option><option value="tab" ${intakeDelimiter==='tab'?'selected':''}>탭</option></select></label><label>후보 ID 열<input id="intake-id" type="text" value="${esc(intakeId)}"></label><label>SMILES 열<input id="intake-smiles" type="text" value="${esc(intakeSmiles)}"></label></div><a href="/templates/molecules.csv" download>빈 CSV 양식 받기</a></details>`:`<details><summary>지원하는 RNA 결과표 형식</summary><p class="small">UTF-8, 탭으로 구분된 DESeq2 결과표입니다. FASTQ나 raw count matrix는 이 입력에 해당하지 않습니다.</p><p class="mono">${RNA_COLUMNS.join(' · ')}</p><p class="small">열 이름을 확인하고, 결측은 NA로 유지하세요. 임의의 값이나 p값을 채우지 마세요.</p><a href="/templates/rna-results.tsv" download>빈 TSV 양식 받기</a></details>`}</div><label class="input-label" for="intake-context">2. 자료의 조건</label><textarea id="intake-context" class="short-input" placeholder="${p.id==='molecule'?'표적, 후보 출처, 측정값이 있다면 단위·측정 조건. 모르는 항목은 미확인으로 적어 주세요.':'표적 유전자, 종·조직, 처리군과 대조군, 용량·시점, 공유 대조군 여부. 모르는 항목은 미확인으로 적어 주세요.'}">${esc(intakeContext)}</textarea>`:''}
  <label class="input-label" for="message">${!['molecule','rna'].includes(p.id)?'지금 궁금한 질문': '3. 이번에 확인할 질문'}</label><textarea id="message" placeholder="${esc(p.placeholder)}">${esc(draft)}</textarea>
  ${intakeError?`<p class="form-error" role="alert">${esc(intakeError)}</p>`:''}
  <div class="input-bottom"><span class="small muted">${!['molecule','rna'].includes(p.id)?'접근·표적이 미정이어도 연구 목표와 질문으로 시작할 수 있습니다.':'원자료를 보존하고 실제 계산 결과를 연결합니다.'}</span>${modelChoice()}${button('create-message',!['molecule','rna'].includes(p.id)?'질문 검토 시작':'자료 분석 시작',busy?'disabled':'','primary')}</div><p class="small muted submit-note">분석·검토 시작은 실제 모델과 도구를 실행하며 수분이 걸릴 수 있습니다. 사용법 안내에는 모델을 호출하지 않습니다.</p>
  <details class="support-scope"><summary>현재 이 작업에서 가능한 범위</summary><p class="small">${esc(p.limit)}</p></details></section>
  <section class="try-examples"><div><h2>자료 없이 먼저 살펴보세요</h2><p class="small muted">완료한 결과를 보거나, 같은 공개 원자료로 새 분석을 시작할 수 있습니다.</p></div><div class="example-choices">${ENTRY_PATHS.filter(x=>x.example).map(x=>`<article><h3>${esc(x.name)}</h3><p class="small">${x.id==='molecule'?'LRRK2 공개 후보73개 · CACHE 자료':'랫드 간 Ttr 처리표3개 · 공개 RNA 자료'}</p><div class="detail-actions">${projects.some(p=>p.id===x.workspace)?`<a href="/?workspace=${x.workspace}&guide=${x.id==='molecule'?'molecule':'rna'}">완료 결과 열기</a>`:''}${button('intake-example','예제 자료로 새 분석',`data-id="${x.example}" ${!status.gateway.available||busy?'disabled':''}`,'small')}</div></article>`).join('')}</div>${finishedResearch()}</section></div>`;
}
function renderWorkflowStatus(){
  const current=Boolean(state.decision&&state.rev===state.decision_rev);
  const active=state.jobs.some(j=>['queued','running'].includes(j.status));
  const latest=[...state.jobs].reverse().find(j=>j.kind==='planner'&&j.based_rev===state.rev);
  const inputs=state.artifacts.filter(a=>!['model_receipt','decision_proposal','research_notes','tool_reading','protocol_snapshot'].includes(a.kind));
  const request=state.events.filter(e=>['message','observation','correction'].includes(e.kind)).at(-1)?.body.text??'';
  const guideOnly=!state.jobs.length&&isUsageQuestion(request);
  if(guideOnly)return usageGuide(request);
  const hasPrevious=Boolean(state.decision);
  const queued=latest?.status==='queued';
  const oldOnly=active&&!state.jobs.some(j=>j.based_rev===state.rev&&['queued','running'].includes(j.status));
  const title=current?'검토 결과가 준비됐습니다.':queued?'검토 실행을 기다리고 있습니다.':oldOnly?'이전 조건의 작업이 실행 중입니다.':active?'입력한 질문을 검토하고 있습니다.':latest?'이번 검토가 끝까지 완료되지 않았습니다.':hasPrevious?'새 근거가 추가됐습니다. 이전 판단과 비교해 보세요.':inputs.length?'자료가 준비됐습니다. 분석을 시작해 주세요.':'질문이 저장됐습니다. 검토를 시작해 주세요.';
  const body=current?'아래에서 판단과 근거를 확인하고, 추가 질문이나 새 관측으로 이어가세요.':queued?'요청은 저장됐습니다. 실행 순서를 기다리고 있으며 같은 질문을 다시 보내지 않아도 됩니다. 기존 자료와 판단은 지금도 확인할 수 있습니다.':oldOnly?'새 입력은 저장됐지만 현재 조건의 검토는 아직 시작되지 않았습니다. 실행 중인 작업의 결과는 원래 조건으로 보존합니다.':active?'진행 중에도 자료를 살펴볼 수 있습니다. 페이지를 새로고침해도 작업은 이어집니다.':latest?(latest.error||'완료한 자료와 이전 판단은 보존돼 있습니다. 실행 기록에서 현재 상태를 확인하세요.'):hasPrevious?'이전 판단과 모든 원자료는 보존돼 있습니다. 추가된 근거로 판단을 갱신하거나, 가정·관측을 더 입력할 수 있습니다.':'입력 저장만으로는 모델이 실행되지 않습니다. 아래 버튼을 누르면 실제 검토와 필요한 도구 실행을 시작합니다.';
  const content = `<ol class="workflow-steps"><li class="done">1 요청·자료</li><li class="${active&&!queued&&!oldOnly?'now':current?'done':''}">2 분석·근거 검토</li><li class="${current?'done':''}">3 판단·다음 행동</li><li>4 관측·정정 반영</li></ol><strong>${esc(title)}</strong><p>${esc(body)}</p>${workflowActivity(latest)}${renderSavedProgress()}${!current&&!active&&!latest?button('plan',hasPrevious?'새 근거로 판단 갱신':inputs.length?'이 자료 분석하기':'저장한 질문 검토하기',!status.gateway.available||busy?'disabled':'','primary small'):''}${!active&&latest&&!current?button('show-jobs','실행 상태 확인','','small'):''}`;
  if(current&&!active)return `<details class="workflow-status workflow-complete"><summary>검토 완료 · 조사 과정 보기</summary>${content}</details>`;
  return `<section class="workflow-status ${active?'working':''}" aria-live="polite">${content}</section>`;
}
function renderSavedProgress(){
  const progress=state.research_progress;
  if(!progress)return '';
  if(progress.status==='unavailable')return `<p class="small muted">${esc(progress.message)}</p>`;
  const notes=progress.notes, findings=notes.findings??[];
  const finding=item=>`<li><p>${judgmentText(item.text)}</p>${sourceLinks(item.source_ids.filter(id=>state.artifacts.some(a=>a.id===id)))}</li>`;
  return `<section class="saved-progress" aria-label="조사 중 기록"><div class="section-mark">조사 중 기록 · ${esc(time(progress.created))}</div>
    ${notes.next_goal?`<p><strong>확인하려는 질문</strong> · ${judgmentText(notes.next_goal)}</p>`:''}
    <p class="small muted">${progress.following_operation_returned?'이 질문의 도구 응답이 도착했습니다. 다음 해석을 준비하고 있습니다.':'다음 조회·계산을 위해 남긴 질문입니다. 아직 결과 확인과 구별해 주세요.'}</p>
    ${findings.length?`<div><strong>지금까지 남긴 잠정 발견</strong><ul class="list">${findings.slice(-2).map(finding).join('')}</ul>${findings.length>2?`<details><summary>이 메모의 나머지 발견 ${findings.length-2}개</summary><ul class="list">${findings.slice(0,-2).map(finding).join('')}</ul></details>`:''}</div>`:''}
    ${notes.open_questions?.length?`<details><summary>아직 풀리지 않은 질문 ${notes.open_questions.length}개</summary>${list(notes.open_questions)}</details>`:''}
    <p class="limit">완료 전 연구 메모입니다. 새 근거에 따라 달라질 수 있으며 최종 판단은 아래에 따로 표시합니다.</p></section>`;
}
function workflowActivity(planner){
  if(!planner||!['queued','running'].includes(planner.status))return '';
  const tools=state.jobs.filter(j=>!['planner','explanation'].includes(j.kind)&&j.based_rev===planner.based_rev&&j.created>=planner.created);
  const running=tools.filter(j=>j.status==='running').at(-1);
  const completed=tools.filter(j=>['succeeded','reused'].includes(j.status)&&j.output_id).sort((a,b)=>a.updated.localeCompare(b.updated)).at(-1);
  return `<div class="workflow-activity"><p>요청 시각 ${esc(time(planner.created))}${running?` · 현재 작업: ${esc(labels[running.kind]??'연결 도구')}`:''}</p>${completed?`<p>최근 완료: ${esc(labels[completed.kind]??'연결 도구')} · ${esc(time(completed.updated))}. 결과의 과학적 해석은 최종 판단에서 확인하세요.</p>${sourceLinks([completed.output_id])}`:''}</div>`;
}
function headerFields(text,delimiter){
  const fields=[];let field='',quoted=false;
  text=text.replace(/^\uFEFF/,'');
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(c==='"'){if(quoted&&text[i+1]==='"'){field+='"';i++}else quoted=!quoted}
    else if(!quoted&&c===delimiter){fields.push(field);field=''}
    else if(!quoted&&(c==='\n'||c==='\r')){fields.push(field);return fields}
    else field+=c;
  }
  if(quoted)throw Error('헤더의 따옴표가 닫히지 않았습니다. 파일 구분자와 첫 행을 확인해 주세요.');
  fields.push(field);return fields;
}
async function validateInputFile(file,kind,meta){
  if(!file)throw Error('먼저 분석할 파일을 선택해 주세요. 자료가 없으면 “연구 질문부터 정리”를 선택할 수 있습니다.');
  if(!file.size||file.size>10*1024*1024)throw Error('내용이 있는 10 MiB 이내 파일을 선택해 주세요.');
  if(kind==='rna_table'&&file.name.toLowerCase().endsWith('.gz'))return;
  let text;
  try{text=new TextDecoder('utf-8',{fatal:true}).decode(await file.slice(0,65536).arrayBuffer(),{stream:true})}catch{throw Error('파일을 UTF-8로 저장해 주세요. 원본은 변경하지 않았습니다.')}
  const fields=headerFields(text,kind==='rna_table'?'\t':meta.delimiter);
  const needed=kind==='rna_table'?RNA_COLUMNS:[meta.id_column,meta.smiles_column];
  const missing=needed.filter(n=>!n||fields.filter(f=>f===n).length!==1);
  if(missing.length)throw Error('필수 열이 없거나 중복됐습니다: '+missing.join(', ')+'. 파일 형식과 열 이름을 확인해 주세요.');
}
async function uploadInput(file,kind,meta){
  const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
  for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
  await api(`/api/workspaces/${state.id}/artifacts`,{title:file.name,kind,content_base64:btoa(binary),meta:{original_filename:file.name,encoding:'utf-8-sig',...meta}});
  await refresh();
}
function rememberWorkspace(){
  const u=new URL(location.href);u.searchParams.delete('guide');u.searchParams.set('workspace',state.id);history.replaceState(null,'',u);
  evidaStorage.setItem('evida-project',state.id);tab='research';selected=null;detail=null;
}
async function startIntake(){
  if(isUsageQuestion(draft)){openUsageHelp(draft);return}
  const p=entryPath();
  if(!draft.trim())throw Error('이번에 알고 싶은 질문을 적어 주세요. 사용법이 궁금하면 “사용법 보기”를 누르세요.');
  if(!await refreshGatewayStatus({force:true,renderChanges:false}))throw Error('현재 모델 연결을 사용할 수 없습니다. 입력 초안은 그대로 남아 있습니다.');
  const kind=p.id==='rna'?'rna_table':'molecule_csv';
  const meta={delimiter:p.id==='rna'?'\t':intakeDelimiter==='tab'?'\t':intakeDelimiter,smiles_column:intakeSmiles,id_column:intakeId,context:intakeContext.trim()||'자료 조건 미확인 — 연구자 확인 필요'};
  if(['molecule','rna'].includes(p.id))await validateInputFile(intakeFile,kind,meta);
  submitPhase='질문과 원자료를 저장하고 있습니다.';render();
  state=await api('/api/workspaces',{title:draft.trim().slice(0,50)});rememberWorkspace();inputKind='message';syntheticDraft=false;
  if(p.id==='question'&&goalApproach)draft+='\n연구자가 우선 지정한 접근: '+(goalApproach==='small_molecule'?'저분자':'siRNA')+'. 다른 접근의 유용한 근거는 대안으로 보존해 주세요.';
  await saveMessage();
  if(['molecule','rna'].includes(p.id))await uploadInput(intakeFile,kind,meta);
  projects=await api('/api/workspaces');intakeFile=null;intakeContext='';
  submitPhase='실제 검토를 시작하고 있습니다.';render();
  await runTool('planner',plannerOptions());
}
function plannerOptions(){
  // Omitted entirely when the reader kept the server's model, so a run that made no choice
  // carries no claim to have made one.
  return chosenModel&&chosenModel!==status.gateway?.requested_model?{model:chosenModel}:{};
}
async function startExample(id){
  if(!await refreshGatewayStatus({force:true,renderChanges:false}))throw Error('현재 모델 연결을 사용할 수 없습니다. 완료 결과는 바로 열 수 있습니다.');
  submitPhase='공개 원자료를 새 연구에 연결하고 있습니다.';render();
  state=await api('/api/team-examples',{id});rememberWorkspace();draft='';inputKind='message';syntheticDraft=false;
  projects=await api('/api/workspaces');submitPhase='예제의 실제 분석을 시작하고 있습니다.';render();
  await runTool('planner',plannerOptions());
}
function chooseEntry(mode){
  if(!ENTRY_PATHS.some(p=>p.id===mode))return;
  if(dialog.open)dialog.close();
  if(state){state=null;selected=null;detail=null;draft=evidaStorage.getItem('evida-draft-new')??'';history.replaceState(null,'',deploymentURL('/'));evidaStorage.removeItem('evida-project')}
  intakeMode=mode;intakeError='';actionError='';inputKind='message';syntheticDraft=false;render();
  document.querySelector('.intake-panel')?.scrollIntoView({behavior:'smooth',block:'start'});
}
document.addEventListener('input',event=>{
  const id=event.target.id,v=event.target.value;
  if(id==='intake-context')intakeContext=v;
  if(id==='intake-id')intakeId=v;
  if(id==='intake-smiles')intakeSmiles=v;
});
document.addEventListener('change',event=>{
  if(event.target.id==='intake-file'){intakeFile=event.target.files[0]??null;document.getElementById('intake-file-name').textContent=intakeFile?intakeFile.name+' 선택됨':'파일을 선택하세요.'}
  if(event.target.id==='intake-delimiter')intakeDelimiter=event.target.value;
  if(event.target.id==='intake-model'){
    if(offeredModels().includes(event.target.value))chosenModel=event.target.value;
    else{event.target.value=chosenModel??status.gateway?.requested_model??'';notice('현재 연결에서 허용된 모델만 선택할 수 있습니다.')}
  }
  if(event.target.id==='upload-kind')updateUploadKind();
});
function updateUploadKind(){
  const rna=dialog.querySelector('#upload-kind')?.value==='rna_table';
  for(const el of dialog.querySelectorAll('[data-molecule-field]'))el.hidden=rna;
  const d=dialog.querySelector('#upload-delimiter');if(d)d.value=rna?'tab':',';
  const help=dialog.querySelector('#upload-format-help');if(help)help.innerHTML=deploymentHTML(rna?`<p>UTF-8·탭 구분의 기존 차등발현 결과표입니다. 필수 열:</p><p class="mono">${RNA_COLUMNS.join(' · ')}</p><a href="/templates/rna-results.tsv" download>빈 TSV 양식 받기</a>`:'<p>후보 ID와 SMILES가 있는 CSV입니다. 열 이름과 구분자를 맞춰 주세요.</p><a href="/templates/molecules.csv" download>빈 CSV 양식 받기</a>');
}


;
/* Source: team-examples.js */
// Actual saved research runs; opening a record makes no model call.
const TEAM_EXAMPLES = [
  {
    "id": "goal-ipf82",
    "workspace": "ws_b8990996dd034dfb",
    "number": "01",
    "featured": true,
    "category": "이번에 먼저 살펴볼 세 장면",
    "label": "IPF · 계산과 임상 근거의 조건",
    "title": "한 계산 결과를 치료 방향으로 바로 바꿔도 될까?",
    "description": "질환 목표에서 치료와 기전을 찾은 뒤, 실제 공개 조직 자료를 분석했습니다. 세포 표지·분석 조건을 바꾸면 해석이 달라지는 부분과 임상 근거를 나눠 확인합니다.",
    "steps": [
      "로드맵에서 연구 목표 → 기전 → 후보 흐름 따라가기",
      "근거 단계에서 실제 계산의 조건과 원 임상 표 열기",
      "바뀐 판단과 남은 확인이 어떤 근거에 연결됐는지 보기"
    ],
    "synthetic": true,
    "prompt": "현재 IPF 판단에서 임상 시험의 근거와 같은 공개 조직 자료의 조건 분석을 구분해 쉽게 설명해 주세요. 유지한 부분과 조건에 따라 달라진 부분을 짚고, 같은 계산을 반복하지 말고 지금 판단을 바꿀 수 있는 다음 확인을 이어 주세요."
  },
  {
    "id": "goal-aip82",
    "workspace": "ws_c4da95940a61461d",
    "number": "02",
    "featured": true,
    "category": "이번에 먼저 살펴볼 세 장면",
    "label": "AIP · 논문 속 후보에서 실제 계산으로",
    "title": "추천하지 않은 후보도 다시 살펴볼 수 있을까?",
    "description": "질환에서 출발해 논문에 등장한 후보와 치료 참조를 보존했습니다. 구조를 찾은 후보, 구조가 미해결인 후보, siRNA 치료 참조를 구분하고 실제 계산과 실패 기록까지 따라가 보세요.",
    "steps": [
      "접근·후보 단계에서 전체 발견 목록 열기",
      "원문 후보의 이름·조건과 구조 조회 결과 비교",
      "계산 결과를 열고 추천 밖 후보의 검토를 요청해 보기"
    ],
    "synthetic": true,
    "prompt": "AIP 전체 발견 목록에서 원문 후보와 구조 조회 결과, siRNA 치료 참조를 구분해 주세요. 구조가 미해결인 후보도 보존하고, 현재 근거와 계산으로 판단할 수 있는 부분과 다음 확인을 설명해 주세요."
  },
  {
    "id": "goal-ph1-78",
    "workspace": "ws_a2b7e1eb0b114b40",
    "number": "03",
    "category": "이번에 먼저 살펴볼 세 장면",
    "label": "PH1 · 관측에 따라 달라지는 다음 확인",
    "title": "전달량은 충분한데, 왜 반응이 약할까?",
    "description": "가상의 두 차례 관측을 입력했습니다. 세포질 전달량과 Ago2 결합을 나눠 판단하면서 이전 임상·서열 근거를 유지한 과정과, 다시 확인할 조건을 살펴보세요.",
    "steps": [
      "로드맵에서 현재 판단과 다음 확인 보기",
      "근거 단계에서 전달량·Ago2 결합의 서로 다른 판단 열기",
      "이번 판단의 변화에서 유지한 부분과 바꾼 부분 비교"
    ],
    "synthetic": true,
    "prompt": "두 차례 관측은 실제 실험이 아닌 가상 개발 입력이라는 점을 유지해 주세요. 세포질 양과 Ago2 결합의 판단이 왜 다르게 바뀌었는지 설명하고, 이미 알려준 요약값을 반복 요청하지 않으면서 원인을 구별할 다음 확인을 제안해 주세요.",
    "featured": true
  },
  {
    "id": "goal-adpkd78",
    "workspace": "ws_ec94bce5dda34292",
    "number": "04",
    "category": "이전에 개발한 연구 흐름",
    "label": "ADPKD · 다른 기전 찾기와 조건 변경",
    "title": "첫 추천 밖에도 연구할 만한 길이 있을까?",
    "description": "기존 개발에 쓰지 않았던 질환을 목표만으로 시작했습니다. 첫 판단을 보존한 뒤 다른 기전·후보를 더 찾고, 조사 도중 관리 부담이라는 연구 기준을 추가하는 개발 검토를 이어갑니다. 현재 결과와 실행 상태를 확인하세요.",
    "steps": [
      "원 질문과 현재 판단의 적용 조건 확인",
      "다른 기전·후보의 추천 이유와 미검토 범위 보기",
      "추가한 연구 기준이 무엇을 바꾸고 어떤 근거를 유지했는지 확인"
    ],
    "synthetic": true,
    "prompt": "이 가상 제품 검토의 현재 ADPKD 목표와 관리 부담 조건을 유지해 주세요. 추천한 기전·후보의 근거와 아직 비교하지 않은 부분을 설명하고, 이미 확보한 공개 원자료로 다음 유용한 확인을 이어 주세요. 새로운 실험 결과를 가정하지 마세요.",
    "featured": false
  },
  {
    "id": "goal-molecule71",
    "workspace": "ws_fba2854a7ca34c4e",
    "number": "05",
    "label": "질환에서 저분자 후보로",
    "title": "치료할 조직이 바뀌면, 같은 후보를 쓸 수 있을까?",
    "description": "후보 이름 없이 ATTR에서 출발해 공개 후보와 구조를 찾았습니다. 실제 포즈·기능 근거를 검토한 뒤, 연구 목표를 심장 중심에서 중추신경계로 바꾸는 가상 정정이 어떤 판단을 다시 열었는지 확인합니다.",
    "steps": [
      "질환 → 기전 → 후보로 이어진 원 기록 확인",
      "현재 판단에서 유지한 기전과 다시 확인할 조직·노출 구별",
      "제안된 원문 확인을 맡기거나 내 목표로 다시 질문"
    ],
    "synthetic": true,
    "prompt": "현재 중추신경계 목표가 개발 확인용 가정이라는 점을 유지해 주세요. 지금 다음 확인 중 공개 자료와 연결된 도구로 할 수 있는 가장 유용한 일을 이어서 수행해 주세요. 원 ATTR-CM 판단과 완료 계산을 보존하고, 새 근거가 어떤 수준의 판단을 바꾸는지 설명해 주세요.",
    "featured": false,
    "category": "이전에 개발한 연구 흐름"
  },
  {
    "id": "goal-sirna71",
    "workspace": "ws_169ab4ba281148d0",
    "number": "06",
    "label": "질환에서 siRNA 결합 영역으로",
    "title": "계산은 좋은데 반응이 약하다면, 어디를 다시 볼까?",
    "description": "서열 없이 표적·전사체를 찾고 전체 후보를 보존했습니다. 추천 밖 후보110의 실제 계산, 약한 반응과 양성대조의 가상 입력을 따라 어떤 설명이 좁혀지고 무엇이 남는지 확인합니다.",
    "steps": [
      "추천 후보와 원 계산의 조건·한계 확인",
      "전체 후보에서 다른 서열과 양 가닥 근거도 살펴보기",
      "새 관측·내 해석을 입력하고 다음 행동의 변화를 확인"
    ],
    "synthetic": true,
    "prompt": "이 사례의 약한 반응과 양성대조는 가상 관측임을 유지해 주세요. 현재 판단에서 남은 후보별 원인을 구별할 때 기존 자료로 먼저 확인할 수 있는 것과 실제 새 관측이 필요한 것을 설명하고, 가능한 다음 확인을 이어 주세요. 이미 계산한 값을 반복하지 마세요.",
    "featured": false,
    "category": "이전에 개발한 연구 흐름"
  },
  {
    "id": "goal-gout75",
    "workspace": "ws_711490e959944d0e",
    "number": "07",
    "label": "새 저분자 목표 · 후보 선택과 재계획",
    "title": "후보를 직접 고르고, 연구 목표를 바꾸면?",
    "description": "통풍의 요산 축적이라는 목표에서 표적과 화합물을 찾고, 추천 밖 후보를 선택해 실제 물성·ADMET·원문을 비교했습니다. 이후 가상의 급성 결정 염증 목표로 바꾼 기록에서 무엇을 유지하고 다시 검토하는지 살펴봅니다.",
    "steps": [
      "발견한 선택지 전체에서 후보와 추천 이유 확인",
      "후보 비교의 계산·원전과 이전 판단 열기",
      "목표 변경 후 현재 검토 상태와 바뀐 기전·다음 행동 확인"
    ],
    "synthetic": true,
    "prompt": "기존 요산 감소 연구와 지금의 결정 염증 목표를 구별해 주세요. 현재 목표에서 보존 자료로 가능한 다음 확인을 이어가고, 기존 두 화합물의 계산만으로 새 목표의 효과를 확정하지 마세요.",
    "featured": false,
    "category": "이전에 개발한 연구 흐름"
  },
  {
    "id": "goal-ldl75",
    "workspace": "ws_ee711a1182834829",
    "number": "08",
    "label": "새 siRNA 목표 · 표적에서 실제 후보로",
    "title": "표적과 서열이 없어도 어디까지 이어질까?",
    "description": "높은 LDL을 낮추고 싶다는 가상 연구 질문에서 시작했습니다. 공개 근거로 표적 방향을 비교한 첫 판단과, 실제 전사체·후보·계산으로 이어가는 후속 작업을 같은 기록에서 볼 수 있습니다.",
    "steps": [
      "플랫폼이 제안한 잠정 표적과 아직 남은 대안 확인",
      "현재 실행 상태와 실제 반환된 전사체·후보·계산 구분",
      "새 조건이나 다른 선택을 입력해 후속 판단 요청"
    ],
    "synthetic": true,
    "prompt": "현재 잠정 표적의 이유와 실제 생성·계산된 후보를 구별해 설명해 주세요. 지금 결과에서 후보 수준만 바꿀 조건과 표적·기전까지 다시 볼 조건을 나누고, 기존 자료로 수행 가능한 다음 확인을 이어 주세요.",
    "featured": false,
    "category": "이전에 개발한 연구 흐름"
  }
];


;
/* Source: team-workspace.js */
function teamGuide(){
  const id=new URLSearchParams(location.search).get('guide');
  const item=TEAM_EXAMPLES.find(e=>e.id===id&&e.workspace===state?.id);
  if(!item)return '';
  const refused=item.feedback&&Boolean(providerNotice());
  return `<details class="team-guide" open><summary>예시 따라가기 · ${esc(item.label)}</summary><ol>${item.steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ol>${sourceLinks(item.sources)}${refused?'<p class="small">최신 추가 검토는 서비스에서 거절됐습니다. 변경 기록에서 완료된 이전 정정과 이번 미완료 입력을 구별해 확인하세요.</p>':`${item.feedback?button('team-feedback','가상 후속 관측 입력해 보기','','small'):button('team-prompt','후속 질문 입력해 보기','','small')}<p class="small muted">입력 예시는 초안으로 열립니다. 저장·실행을 누르기 전에는 연구가 바뀌지 않습니다.</p>`}</details>`;
}
function renderInputChanges(){
  const change=state.input_changes;
  if(!change || !(change.sources.length||change.messages.length||change.intent_edits.length))return '';
  const published=change.phase==='published_review';
  return `<details class="input-changes"><summary>${published?'이번 판단까지 추가된':'이전 판단 이후 추가된'} 자료 ${change.sources.length}개 · 입력 ${change.messages.length+change.intent_edits.length}개</summary><p class="small muted">추가된 자료의 위치입니다. 모든 자료를 읽었거나 각 주장이 검증됐다는 뜻은 아닙니다. 이전 근거는 자료 목록에서 계속 확인할 수 있습니다.</p>${sourceLinks(change.sources.map(a=>a.id))}${change.messages.map(m=>button('message-source',`${m.kind==='correction'?'정정':m.kind==='observation'?'새 관측':'연구 요청'}${m.origin==='synthetic'?' · 개발용 가상 입력':''}`,`data-id="${esc(m.id)}"`,'link-button small')).join('')}${change.intent_edits.length?`<p class="small">연구 의도 수정 ${change.intent_edits.length}건 · 변경 기록에서 확인</p>`:''}</details>`;
}
function jobStatus(job){
  const diagnostic=[...state.events].reverse().find(e=>e.kind==='provider_response_diagnostic'&&e.body.job_id===job.id);
  return diagnostic?`${jobLabels[diagnostic.body.status]??diagnostic.body.status} · ${diagnostic.body.provider_error_code}`:(jobLabels[job.status]??job.status);
}
function providerNotice(){
  const job=[...state.jobs].reverse().find(j=>j.kind==='planner'&&j.based_rev===state.rev);
  if(!job||state.decision_rev===state.rev)return '';
  const diagnostic=[...state.events].reverse().find(e=>e.kind==='provider_response_diagnostic'&&e.body.job_id===job.id);
  if(!diagnostic&&job.status!=='refused')return '';
  return `<div class="provider-notice" role="status"><strong>새 판단을 완료하지 못했습니다.</strong><p>${esc(diagnostic?.body.message??job.error)}</p><p>새로 입력한 관측과 이전 판단은 남아 있습니다. 자료 조회와 계산 결과는 계속 확인할 수 있습니다.</p></div>`;
}
async function teamAction(action){
  const item=TEAM_EXAMPLES.find(e=>e.id===new URLSearchParams(location.search).get('guide')&&e.workspace===state?.id);
  if(!item)return;
  if(action==='team-prompt'){
    if(draft.trim()){notice('작성 중인 입력이 있습니다. 먼저 저장하거나 비운 뒤 예시를 넣어 주세요.');return;}
    draft=item.prompt;inputKind='message';syntheticDraft=item.synthetic===true;tab='research';evidaStorage.setItem(draftKey(),draft);render();document.querySelector('#message').focus();
  }else if(action==='team-feedback'){
    if(providerNotice()){notice('이 예시의 최신 추가 검토는 서비스에서 거절됐습니다. 원 입력과 이전 판단은 변경 기록에서 확인할 수 있습니다.');return;}
    const h=state.decision?.research_loop?.hypotheses.find(h=>h.id===item.hypothesis);
    if(!h){notice('현재 가설을 확인한 뒤 연결할 부분을 선택해 주세요.');return;}
    const part=h.assessment_scope?.parts.find(p=>p.id===item.part);
    openResearchFeedback(null,h.id,part?.id??null);
    dialog.querySelector('#feedback-text').value=item.feedback;
    dialog.querySelector('#feedback-synthetic').checked=true;
    dialog.querySelector('#feedback-comparison').value='different';
  }
}


;
/* Source: research.js */
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


;
/* Source: evidence-history.js */
// On-demand published relationships. Opening history starts no model or science job.
let evidenceHistorySelection = null;
const edgeHistoryLabels = {same_recorded_link:'이번 목록에도 같은 연결이 있음',recorded_link_changed:'이번 목록에서 관계·설명이 달라짐',not_in_current_list:'이번 근거 목록에는 없음'};

function evidenceHistoryButton(h, published) {
  if(!published || state.events.filter(e=>e.kind==='decision_published').length<2)return '';
  return `<div class="detail-actions">${button('evidence-history','이전 근거와 적용 조건 보기',`data-hypothesis="${esc(h.id)}" data-offset="0"`,'small')}</div>`;
}

function historyEvidenceRow(row) {
  const e=row.edge;
  return `<article class="evidence-relation"><div class="evidence-label">당시 ${esc(relationLabels[e.relation]??e.relation)} · ${esc(edgeHistoryLabels[row.comparison])}</div>${row.part_id?`<p>당시 부분 주장: ${esc(row.part_statement)}</p>`:''}${row.explanation_id?`<p>당시 설명: ${esc(row.explanation_statement)}</p>${list(row.explanation_conditions??[])}`:''}<p>${esc(e.detail)}</p><p class="limit">당시 적용 조건: ${esc(e.applicability)}</p>${e.source_type==='artifact'?sourceLinks([e.source_id]):button('message-source','당시 연구자 입력',`data-id="${esc(e.source_id)}"`,'small')}${row.comparison==='recorded_link_changed'?`<details><summary>이번 기록과 비교</summary>${row.current_links.map(c=>`<p>현재 기록: ${esc(relationLabels[c.edge.relation])}</p><p>${esc(c.edge.detail)}</p><p class="limit">현재 적용 조건: ${esc(c.edge.applicability)}</p>`).join('')}</details>`:''}</article>`;
}

async function openEvidenceHistory(hypothesisId,offset=0) {
  const wid=state.id,decisionId=state.decision_id;
  const value=await api(`/api/workspaces/${encodeURIComponent(wid)}/hypothesis-history?hypothesis_id=${encodeURIComponent(hypothesisId)}&offset=${offset}&limit=4`);
  if(state.id!==wid||state.decision_id!==decisionId)throw Error('판단이 바뀌었습니다. 최신 화면에서 다시 열어 주세요.');
  evidenceHistorySelection={wid,decisionId,value};
  showDialog('이전 근거와 적용 조건',`<p class="notice-inline">${esc(value.meaning)}</p>${value.current_content_status!=='available'?'<p class="limit">현재 판단의 원본을 확인하지 못했습니다. 비교 상태를 확정하지 마세요.</p>':''}${value.rows.map(r=>`<details class="history-evidence-decision" ${!r.is_current?'open':''}><summary>${r.is_current?'현재 판단':'이전 판단'} · 연구 기록 ${r.state_revision} · ${esc(time(r.created))}</summary>${r.content_status!=='available'?'<p class="limit">원 판단을 읽을 수 없거나 무결성 검사가 실패했습니다. 이는 과학적 반대 근거가 아닙니다.</p>':r.hypothesis?`<h3>${esc(r.hypothesis.statement)}</h3><p class="small">당시 예상: ${esc(r.hypothesis.expected_observation)}</p><p>당시 판단: ${esc(hypothesisLabels[r.hypothesis.assessment])}</p>${r.claim_comparison==='literal_claim_changed'?'<p class="notice-inline">현재 가설과 문구가 다릅니다. 아래 관계는 당시 주장에 대한 기록입니다.</p>':'<p class="small muted">같은 문구여도 대상·시험·조건이 달라질 수 있습니다. 현재 지지로 자동 승계하지 않습니다.</p>'}${r.evidence_comparison.length?r.evidence_comparison.map(historyEvidenceRow).join(''):'<p class="small muted">이 판단에는 근거 연결이 기록되어 있지 않습니다. 앞선 판단과 원자료는 계속 확인할 수 있습니다.</p>'}${r.context_artifact_id?`<p>당시 별도로 기록한 조건</p>${sourceLinks([r.context_artifact_id])}`:''}${sourceLinks([r.decision_id])}${button('history-evidence-feedback','이 근거를 현재 질문에서 다시 검토',`data-decision="${esc(r.decision_id)}"`,'small')}`:'<p class="small muted">이 판단에는 해당 ID의 가설이 없습니다. 기각으로 해석하지 않습니다.</p>'}</details>`).join('')}${value.lineage_gap?'<p class="limit">기록된 이전 판단 연결이 여기서 끊깁니다. 임의의 다른 판단으로 이어 붙이지 않았습니다.</p>':''}<div class="detail-actions">${offset?button('evidence-history','더 최근 판단',`data-hypothesis="${esc(hypothesisId)}" data-offset="${Math.max(0,offset-4)}"`,'small'):''}${value.has_more?button('evidence-history','더 이전 판단',`data-hypothesis="${esc(hypothesisId)}" data-offset="${offset+4}"`,'small'):''}</div><p class="small muted">이 화면을 열어도 새 조사나 평가 변경은 실행되지 않습니다.</p>`);
}

async function reviewHistoricalEvidence(decisionId) {
  const selected=evidenceHistorySelection;
  if(!selected||selected.wid!==state.id||selected.decisionId!==state.decision_id)throw Error('최신 판단에서 근거 이력을 다시 열어 주세요.');
  const row=selected.value.rows.find(r=>r.decision_id===decisionId&&r.content_status==='available'&&r.hypothesis);
  if(!row)throw Error('열람한 이전 판단을 선택해 주세요.');
  const previous=await api(`/api/workspaces/${encodeURIComponent(state.id)}/artifacts/${encodeURIComponent(decisionId)}?download=1`);
  if(selected.wid!==state.id||selected.decisionId!==state.decision_id)throw Error('판단이 바뀌었습니다. 다시 확인해 주세요.');
  openResearchFeedback(null,row.hypothesis.id,null,{decision:previous,decision_id:decisionId});
  dialog.querySelector('#feedback-kind').value='message';
  dialog.querySelector('#feedback-text').value=`이전 판단의 근거를 현재 질문에서 다시 검토해 주세요.\n당시 주장: ${row.hypothesis.statement}\n당시 판단: ${decisionId}\n원 적용 조건과 반대 근거를 보존하고, 현재 주장에 계속 쓸 수 있는 관계와 다시 확인할 부분을 구분해 주세요. 이는 새 관측이나 과거 판단의 자동 채택이 아닙니다.`;
  dialog.querySelector('[data-action="save-feedback"][data-review="true"]').textContent='이 근거 다시 검토';
}

function renderTransportHandle(part) {
  return button('transport-handle','전달 표기',`data-original="${esc(part)}" aria-label="원 응답의 자료 전달 표기 보기"`,'inline-source-link');
}


;
/* Source: interaction.js */
// An explanation has its own saved snapshot and never edits research conditions.
const explanationDrafts = new Map();
let explanationSending = false;
document.addEventListener('input', event => {
  if(event.target.id === 'explanation-question' && state) explanationDrafts.set(state.id,event.target.value);
});

function publishedFollowthrough(current,request){
  if(!request||current.decision_rev!==current.rev||request.requested_rev>current.decision_rev)return null;
  const requestedJob=current.jobs.find(j=>j.id===request.job_id);
  if(request.status==='pending'||['queued','running'].includes(requestedJob?.status))return null;
  const artifact=current.artifacts.find(a=>a.id===current.decision_id&&a.kind==='decision_proposal');
  const job=artifact?.meta?.job_id?current.jobs.find(j=>j.id===artifact.meta.job_id):null;
  if(!job||job.kind!=='planner'||job.status!=='succeeded'||job.based_rev!==current.rev||artifact.meta.based_rev!==current.rev)return null;
  if(job.id!==request.job_id&&![job.request?.resume_from_job,job.request?.reviewed_source_job].includes(request.job_id))return null;
  // A later request at the same revision must not inherit an older completion.
  const published=Date.parse(artifact.created),requested=Date.parse(request.created);
  if(!Number.isFinite(published)||!Number.isFinite(requested)||published<requested)return null;
  return {job_id:job.id,recovered_from_other_job:job.id!==request.job_id};
}

// Citations belong to the explanation's saved snapshot, never today's event list.
function explanationArtifactLinks(answer){
 const refs=(answer.evidence_refs??[]).filter(ref=>typeof ref==='string'&&ref.startsWith('art_'));
 return sourceLinks(refs);
}
function explanationParagraphs(value){
 const text=String(value??''),segmenter=typeof Intl.Segmenter==='function'?new Intl.Segmenter('ko',{granularity:'sentence'}):null;
 // Preserve each character, including existing newlines and numeric punctuation.
 const lines=text.match(/[^\r\n]*(?:\r\n|\r|\n|$)/g)?.filter(Boolean)??[];
 return lines.flatMap(line=>segmenter?[...segmenter.segment(line)].map(x=>x.segment):[line]);
}
function explanationInlineText(value){
 // Consume the whole generated-candidate token before artifact linking. A suffix,
 // different source, or absent current candidate must never resolve by prefix.
 return String(value).split(/(\bmolecule:generated:[A-Za-z0-9_:./-]+)/g).map(part=>{
  if(!part.startsWith('molecule:generated:'))return judgmentText(part);
  const matches=candidateOptions().filter(item=>item.option_id===part);
  const item=matches.length===1?matches[0]:null,name=item?candidateDisplayName(item):'';
  return name?button('discovery-detail',esc(name),`data-id="${esc(part)}" aria-label="${esc(name)} · 후보 상세"`,'inline-source-link'):
   '<span class="small muted">후보 확인 필요 · 저장된 설명 원문 참조</span>';
 }).join('');
}
function explanationAnswerText(answer){
 const original=String(answer.answer??''),display=researcherWording(original);
 return `${explanationParagraphs(display).map(part=>`<p class="prose">${explanationInlineText(part)}</p>`).join('')}<details data-detail-key="explanation-original:${esc(answer.artifact_id??answer.context_artifact_id??'')}"><summary>저장된 설명 원문</summary><p class="prose">${esc(original)}</p></details>`;
}
function explanationEventDate(event){
 const parsed=new Date(event.created);return Number.isNaN(parsed.getTime())?String(event.created??''):parsed.toLocaleString('ko-KR');
}
function explanationEventLabel(event){return eventLabels[event.kind]??event.kind}
function explanationEventRecords(answer){
 const records=(answer.event_citations??[]).filter(e=>Number.isInteger(e.seq));
 if(!records.length)return '';
 return `<details class="explanation-event-records" data-detail-key="explanation-events:${esc(answer.artifact_id)}"><summary>설명에 사용한 연구 기록 ${records.length}건</summary><ul class="list">${records.map(event=>`<li>${button('interaction-event-record',`${esc(explanationEventLabel(event))} · ${esc(explanationEventDate(event))}`,`data-id="${esc(answer.artifact_id)}" data-event-seq="${event.seq}"`,'link-button small')}<small>저장 기록 #${event.seq}${['message','correction','observation'].includes(event.kind)?' · '+esc(inputProvenanceLabel(event)):''}</small></li>`).join('')}</ul></details>`;
}
function explanationEventBody(event){
 const body=event.body??{},text=value=>typeof value==='string'&&value?`<p class="prose">${esc(value)}</p>`:'';
 let content=text(body.text);
 if(event.kind==='work_framed'){
  const brief=Array.isArray(body.task_brief)?body.task_brief.map(task=>typeof task==='string'?text(task):`<article>${text(task?.question)}${text(task?.purpose)}${Array.isArray(task?.depends_on)&&task.depends_on.length?`<p class="small muted">함께 확인할 자료</p>${list(task.depends_on)}`:''}</article>`).join(''):text(body.task_brief);
  content=`${text(body.current_question)}${brief}`;
 }
 if(event.kind==='decision_published'){
  const receipt=typeof body.receipt_id==='string'?body.receipt_id:'';
  content+=receipt&&state.artifacts.some(a=>a.id===receipt)?sourceLinks([receipt]):receipt?`<p class="small muted">저장된 실행 기록: ${esc(receipt)}</p>`:'';
 }
 const input=['message','correction','observation'].includes(event.kind);
 return `<p class="small muted">${esc(explanationEventLabel(event))} · ${esc(explanationEventDate(event))} · 저장 기록 #${event.seq}</p>${input?`<p class="limit">${esc(inputProvenanceLabel(event))}</p>${inputProvenanceNotice(event)}`:''}${content}`;
}

function renderLiveInteraction(){
  const jobs=state.jobs.filter(j=>j.kind==='explanation'), pending=jobs.find(j=>['queued','running'].includes(j.status));
  const answers=state.explanations??[], latest=answers.at(-1), lastJob=jobs.at(-1);
  const live=state.jobs.some(j=>j.kind!=='explanation'&&['queued','running'].includes(j.status));
  const failure=lastJob&&!['queued','running','succeeded'].includes(lastJob.status)?lastJob.error:null;
  const text=explanationDrafts.get(state.id)??'';
  const request=state.followthrough_requests?.at(-1);
  const nextJob=request?.job_id?state.jobs.find(j=>j.id===request.job_id):null;
  const published=publishedFollowthrough(state,request);
  let follow='';
  if(request){
    let title,body;
    if(published){title='현재 조건의 판단이 도착했습니다';body=published.recovered_from_other_job?'중단 이후 이어서 검토한 결과입니다. 이전 중단 기록은 변경 기록에 보존되어 있습니다.':'아래 판단에서 바뀐 내용과 계속 유지한 내용을 확인할 수 있습니다.'}
    else if(request.status==='pending'){title='변경을 접수했습니다';body='현재 작업의 다음 경계에서 새 조건으로 이어서 검토합니다. 앞선 원자료와 결과도 함께 확인합니다.'}
    else if(request.status==='needs_confirmation'){title='이어서 검토할 조건을 확인해 주세요';body=request.error}
    else if(nextJob&&['queued','running'].includes(nextJob.status)){title='변경한 조건으로 검토 중입니다';body='새 질문과 이전 근거를 함께 보고, 영향을 받은 판단과 다음 행동을 다시 확인합니다.'}
    else if(nextJob?.status==='succeeded'){title='변경한 조건의 판단이 도착했습니다';body='아래 판단에서 바뀐 내용과 계속 유지한 내용을 확인할 수 있습니다.'}
    else if(nextJob){title='후속 검토의 기록을 확인해 주세요';body=nextJob.error??jobLabels[nextJob.status]??nextJob.status}
    if(title)follow=`<aside class="followthrough-status" role="status"><strong>${esc(title)}</strong><p>${esc(body??'')}</p>${request.status==='needs_confirmation'&&!published?button('interaction-review-current','현재 조건으로 이어서 검토',!status.gateway.available?'disabled':'','small'):''}</aside>`;
  }
  return `${follow}<section class="live-interaction"><div class="interaction-heading"><div><h2>${live?'조사 중에도 물어보세요':'판단을 이해하고 싶다면'}</h2><p>설명만 묻는 질문입니다. 조건을 바꾸려면 아래의 ‘이 지점에서 개입하기’를 사용하세요.</p></div></div>
  <label class="sr-only" for="explanation-question">저장된 판단과 진행 상황에 대한 설명 질문</label>
  <div class="explanation-composer"><textarea id="explanation-question" rows="2" placeholder="왜 이 방향을 보고 있나요? 지금 무엇이 아직 불확실한가요?">${esc(text)}</textarea>${button('interaction-explain','설명 물어보기',pending||explanationSending||!status.gateway.available?'disabled':'','small')}</div>
  ${pending?`<p class="interaction-pending" role="status">${pending.status==='queued'?'설명 질문을 접수했습니다.':'저장된 근거로 설명을 준비하고 있습니다.'} 조사 진행 상황은 아래에서 계속 확인할 수 있습니다.</p>`:''}
  ${failure?`<p class="notice-inline">설명을 마치지 못했습니다. ${esc(failure)}</p>`:''}
  ${latest?`<details class="latest-explanation"><summary>질문에 대한 설명 보기 · ${esc(latest.question.slice(0,70))}${latest.question.length>70?'…':''}</summary><article class="interaction-answer"><p class="interaction-question">${esc(latest.question)}</p>${explanationAnswerText(latest)}${explanationArtifactLinks(latest)}${explanationEventRecords(latest)}
    ${latest.not_established.length?`<details><summary>아직 확인하지 않은 점</summary>${list(latest.not_established)}</details>`:''}
    ${(latest.citation_provenance??[]).some(x=>x.delivery==='cited_in_saved_snapshot_not_reread')?'<p class="small muted">저장된 판단·메모가 연결한 출처를 포함합니다. 이번 설명에서 모든 원자료를 다시 확인한 것은 아닙니다.</p>':''}
    <p class="small muted">설명 기준: ${esc(new Date(latest.snapshot_captured_at??latest.created).toLocaleTimeString('ko-KR'))}${latest.based_rev!==state.rev?' · 이후 연구 조건이 바뀌었습니다.':''}</p>
    ${latest.suggested_condition_change?button('interaction-use-change','제안된 정정 문구를 입력창으로 가져오기',`data-id="${esc(latest.artifact_id)}"`,'small'):''}</article></details>`:''}
  ${answers.length>1?`<details><summary>이전 설명 ${answers.length-1}개</summary>${answers.slice(0,-1).reverse().map(a=>`<article class="interaction-answer"><strong>${esc(a.question)}</strong>${explanationAnswerText(a)}${explanationArtifactLinks(a)}${explanationEventRecords(a)}<p class="small muted">저장 당시 조건의 설명</p></article>`).join('')}</details>`:''}</section>`;
}

async function interactionAction(action,node){
  if(action==='interaction-event-record'){
    const answer=(state.explanations??[]).find(a=>a.artifact_id===node.dataset.id);
    const event=(answer?.event_citations??[]).find(e=>e.seq===Number(node.dataset.eventSeq));
    if(!event){notice('이 설명에 사용한 저장 기록을 확인할 수 없습니다.');return;}
    await openResearchPanel({kind:'explanation-event',id:`${answer.artifact_id}:event:${event.seq}`,title:'설명에 사용한 연구 기록',body:explanationEventBody(event)});return;
  }
  if(action==='interaction-use-change'){
    const answer=(state.explanations??[]).find(x=>x.artifact_id===node.dataset.id);
    if(!answer?.suggested_condition_change)return;
    draft=answer.suggested_condition_change;inputKind='correction';syntheticDraft=false;
    evidaStorage.setItem(draftKey(),draft);render();document.querySelector('#message')?.focus();return;
  }
  if(action==='interaction-review-current'){
    await api(`/api/workspaces/${state.id}/review-requests`,{expected_rev:state.rev,command_id:crypto.randomUUID()});
    await refresh();notice('현재 조건의 후속 검토를 접수했습니다.');return;
  }
  if(action!=='interaction-explain'||explanationSending)return;
  const wid=state.id,rev=state.rev,question=(explanationDrafts.get(wid)??'').trim();
  if(!question){notice('설명이 필요한 질문을 적어 주세요.');return}
  explanationSending=true;
  try{
    if(!await refreshGatewayStatus({force:true,renderChanges:false}))throw Error('현재 모델 연결을 사용할 수 없습니다. 설명 질문 초안은 그대로 남아 있습니다.');
    if(state?.id!==wid||state.rev!==rev||(explanationDrafts.get(wid)??'').trim()!==question)throw Error('연구 조건이나 질문이 바뀌었습니다. 현재 내용을 확인한 뒤 다시 보내 주세요.');
    await api(`/api/workspaces/${wid}/explanations`,{expected_rev:rev,command_id:crypto.randomUUID(),question});
    explanationDrafts.delete(wid);await refresh();notice('설명 질문을 접수했습니다.');
  }finally{explanationSending=false;render()}
}

async function submitResearchFollowthrough(){
  if(draft.trim()){
    const body={kind:inputKind,text:draft.trim(),synthetic:syntheticDraft,review_requested:true};
    await api(`/api/workspaces/${state.id}/commands`,{expected_rev:state.rev,command_id:crypto.randomUUID(),body});
    draft='';syntheticDraft=false;evidaStorage.removeItem(draftKey());
  }else{
    await api(`/api/workspaces/${state.id}/review-requests`,{expected_rev:state.rev,command_id:crypto.randomUUID()});
  }
  await refresh();notice('이 조건으로 검토하도록 접수했습니다.');
}


;
/* Source: rna-method-review.js */
// Actual analysis evidence; this view never publishes a research decision.
function renderRnaMethodReview(result) {
  const table = (headers, rows) => `<div class="table-scroll"><table><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(value => `<td>${typeof value === 'number' ? number(value) : esc(value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const groups = result.comparisons ?? {};
  const repaired = result.report_version >= 2;
  const lengthHeaders = ['조건','원 평균 차이','최근접 매칭', ...(repaired ? ['동점 배분 매칭'] : []), '층별 표준화','GAM'];
  return `<div class="rna-method-review">
    <p class="section-mark">실제 분석</p>
    <p class="limit">실제 계산의 검토 메모입니다. 이전 연구 판단은 보존되며 새 근거를 반영한 판단 검토가 필요합니다.</p>
    <h3>${esc(result.interpretation?.headline)}</h3>
    ${list(result.interpretation?.supported)}
    <h3>길이 차이를 보정해도 감소하는가</h3>
    <p class="small muted">같은 목표 유전자 집합에서 seed군−배경군의 평균 log₂ FC를 비교했습니다. 음수는 seed군의 상대적 감소를 뜻합니다.</p>
    ${table(lengthHeaders, (groups.length ?? []).map(r => [r.label, r.original, r.matching, ...(repaired ? [r.fractional_ties] : []), r.stratified, r.gam]))}
    <p class="limit">${repaired ? '동점 배분 매칭은 세 입력 순서에서 같은 결과였습니다. 수치 허용오차를 포함한 실제 저자 구현을 검산했으며, 이 수리가 모든 교란을 제거했다는 뜻은 아닙니다.' : '효과 크기는 대조 유전자 선택에 민감합니다.'} 이 표에는 동물 단위 p값이나 신뢰구간을 붙이지 않았습니다.</p>
    ${result.distribution_review ? list(result.distribution_review) : ''}
    <h3>동물 표본 변동을 고려해도 근거가 강한가</h3>
    ${table(['조건','CAMERA 방향','상관 추정 모드 양측 p','동물 점수 Holm p 범위'], (groups.dependence ?? []).map(r => [r.label, r.direction, r.camera_p, r.animal_holm_range]))}
    <p class="limit">CAMERA와 동물 점수는 서로 다른 질문의 검정입니다. CAMERA에는 길이 균형 가중치를 적용하지 않았고, 동물 배치의 교환가능성도 미확정입니다. 효과가 없다고 확정한 결과가 아닙니다.</p>
    <h3>특정 seed 서열이 두드러지는가</h3>
    ${table(['조건','cWords 감소 방향 순위','Sylamer 배경 보정 후 순위'], (groups.motif ?? []).map(r => [r.label, r.cwords_rank, r.sylamer_rank]))}
    <p class="limit">서열 후보의 탐색 순위입니다. 두 방법의 점수와 검정 조건이 달라 순위를 합산하지 않습니다. 동물 수준의 확증이나 직접 결합의 증거도 아닙니다.</p>
    ${result.reference_review ? `<h3>참조를 바꾸면 무엇이 달라지는가</h3>${list(result.reference_review)}` : ''}
    ${groups.a1 ? `<h3>새로 발견한 A1의 감소도 남는가</h3>
      <p class="small muted">A1-only와 세 선택 site가 없는 유전자를 비교한 후속 탐색입니다. 같은 참조 안에서 목표 집합을 고정했습니다.</p>
      ${table(['참조','A1 목표 유전자','범위 제외','길이 보정','길이·AU 보정'], groups.a1.map(r => [r.label,r.target_Q,r.excluded_target,r.length,r.length_AU]))}
      <p class="limit">발견에 사용한 자료로 다시 분석했습니다. AU 조정 뒤에도 감소 방향은 남지만, 직접 결합이나 독립 확증을 뜻하지 않습니다.</p>` : ''}
    ${groups.shrinkage ? `<h3>효과 크기는 추정 방식에 얼마나 민감한가</h3>
      ${table(['조건','축소 추정 MAP','비축소 추정 MLE'], groups.shrinkage.map(r => [r.label,r.MAP,r.MLE]))}
      <p class="limit">같은 유전자와 동점 배분 가중치를 사용한 평균 log₂ FC 차이입니다. MLE를 정답으로 취급하지 않습니다.</p>` : ''}
    <h3>새 관측이 바꾼 다음 확인</h3>
    ${list(result.next_actions)}
    <details class="meta-details"><summary>각 계산의 질문·조건·남은 한계</summary>${table(['계산','확인한 내용','남은 조건'], (result.rows ?? []).map(r => [r.method, r.observation, r.limit]))}</details>
  </div>`;
}


;
/* Source: roadmap-model.js */
// Read-only presentation of the recorded workflow. No inferred causal edges,
// approval, stage completion, or scientific score is produced here.
const ROADMAP_STAGES = [
  {id:'goal',title:'구조화된 질문과 목표',hint:'무엇을 바꾸려는가'},
  {id:'mechanisms',title:'기전과 접근',hint:'어떤 방향을 검토하는가',kinds:['mechanism','target','approach','researcher_proposal']},
  {id:'candidates',title:'후보 발굴',hint:'무엇을 실제로 비교하는가',kinds:['source_candidate','molecule','rna_candidate','rna']},
  {id:'evidence',title:'근거와 계산',hint:'어디까지 확인했는가'},
  {id:'next',title:'EVIDA 실험 권고',hint:'다음에 무엇을 해볼까'},
];
// JSON objects have no key order; arrays retain their recorded order. Missing is
// distinct from explicit null. This compares records, not scientific meaning.
function roadmapSame(a,b){
  if(a===b)return true;
  if(a===null||b===null||typeof a!=='object'||typeof b!=='object')return false;
  if(Array.isArray(a)!==Array.isArray(b))return false;
  const ak=Object.keys(a),bk=Object.keys(b);
  return ak.length===bk.length&&ak.every(k=>Object.hasOwn(b,k)&&roadmapSame(a[k],b[k]));
}
function roadmapOptionKind(x){return x.kind??String(x.option_id??'').split(':')[0]}
function roadmapSummary(value,limit=70){
  const text=String(value??'').replace(/\s+/g,' ').trim();
  return text.length>limit?text.slice(0,limit)+'…':text;
}
function roadmapRecordDiff(before,after,fields){
  const valid=rows=>Array.isArray(rows)&&rows.every(x=>x&&typeof x.id==='string'&&x.id)&&new Set(rows.map(x=>x.id)).size===rows.length;
  if(!valid(before??[])||!valid(after??[]))return [{id:'ambiguous-record-ids',status:'unavailable',fields:[],before,after,reason:'항목 ID가 없거나 중복되어 정확히 대응할 수 없습니다.'}];
  const old=new Map((before??[]).map(x=>[x.id,x])),now=new Map((after??[]).map(x=>[x.id,x]));
  return [...new Set([...old.keys(),...now.keys()])].map(id=>{
    const a=old.get(id),b=now.get(id);
    const changed=fields.filter(key=>!roadmapSame(a?.[key],b?.[key]));
    return {id,before:a??null,after:b??null,fields:changed,
      status:!a?'added':!b?'omitted':changed.length?'changed':'unchanged'};
  });
}
function roadmapClaimRecords(decision){
  const rows=[];
  for(const h of decision?.research_loop?.hypotheses??[]){
    rows.push({...h,id:h.id,claim_id:h.id,hypothesis_id:h.id,level:'hypothesis'});
    for(const [level,items] of [['part',h.assessment_scope?.parts],['alternative',h.conditional_alternatives]]){
      for(const item of items??[])rows.push({...item,id:typeof h.id==='string'&&typeof item.id==='string'?`${h.id}/${level}/${item.id}`:null,claim_id:item.id,hypothesis_id:h.id,level});
    }
  }
  return rows;
}
function roadmapAssessmentPublication(snapshot,assessment){
  if(!assessment)return 'unreviewed';
  const artifact=(snapshot.artifacts??[]).find(a=>a.id===assessment.artifact_id);
  const job=(snapshot.jobs??[]).find(j=>j.id===artifact?.meta?.job_id);
  if(!job)return 'unknown';
  if(['succeeded','reused'].includes(job.status))return 'returned';
  return ['queued','running'].includes(job.status)?'draft':'unfinished';
}
function buildResearchRoadmap(snapshot,goalRows=[],history={status:'unread'}){
  const s=snapshot??{},d=s.discovery??{},dec=s.decision,loop=dec?.research_loop;
  const current=!!dec&&s.decision_rev===s.rev;
  const publication=(s.events??[]).filter(e=>e.kind==='decision_published').at(-1);
  const priorLink=(s.events??[]).find(e=>e.kind==='hypothesis_wording_compared'&&e.body.receipt_id===s.decision_id)?.body.reference;
  const previous=history.status==='ready'&&history.workspaceId===s.id&&history.currentId===s.decision_id&&history.previousId===priorLink?.decision_id?history.decision:null;
  const proposals=[...(d.reviewed_options??[]),...(d.recommendations??[]),...(d.reconsidered_options??[]),
    ...(d.selected_option?[d.selected_option]:[])];
  const seen=new Set();const options=proposals.filter(x=>!seen.has(x.option_id)&&seen.add(x.option_id));
  const selected=d.selected??null;
  const events=s.events??[],changes=s.input_changes??{},after=changes.after_event??0;
  const addedInputs=events.filter(e=>e.seq>after&&['message','observation','correction','intent_edit'].includes(e.kind));
  const intentChanged=addedInputs.some(e=>e.kind==='intent_edit');
  const hasNewInput=changes.phase==='pending_review'&&!!(changes.messages?.length||changes.intent_edits?.length||changes.sources?.length);
  const hypotheses=loop?.hypotheses??[],checks=loop?.next_checks??[];
  const running=(s.jobs??[]).some(j=>j.kind==='planner'&&j.based_rev===s.rev&&['queued','running'].includes(j.status));
  const diffs=previous?{
    goals:roadmapRecordDiff(previous.intent_records,dec.intent_records,['label','text','origin','source_refs']),
    hypotheses:roadmapRecordDiff(previous.research_loop?.hypotheses,hypotheses,['statement','expected_observation','assessment','rationale','evidence','assessment_scope','conditional_alternatives']),
    checks:roadmapRecordDiff(previous.research_loop?.next_checks,checks,['question','purpose','hypothesis_ids','operation','possible_outcomes','outcome_links','scope_targets']),
    claims:roadmapRecordDiff(roadmapClaimRecords(previous).filter(x=>x.level!=='hypothesis'),roadmapClaimRecords(dec).filter(x=>x.level!=='hypothesis'),['statement','expected_observation','assessment','rationale','evidence','conditions','prediction','prediction_origin','observable','part_ids','relations','unknowns']),
  }:null;
  const labelChanged=items=>items?.some(x=>['added','omitted','changed'].includes(x.status));
  const relevant=(kinds)=>options.filter(x=>kinds.includes(roadmapOptionKind(x)));
  const nodes=ROADMAP_STAGES.map(stage=>{
    const n={...stage,summary:'아직 기록 전',status:'기록 대기',mark:'empty',change:null};
    if(stage.kinds){
      n.options=relevant(stage.kinds);n.count=stage.kinds.reduce((sum,k)=>sum+(d.counts?.[k]??0),0);
      n.recommended=n.options.filter(x=>x.assessment?.current_conditions===true&&x.assessment?.status==='recommended'&&roadmapAssessmentPublication(s,x.assessment)==='returned');
      n.reviewed=n.options.filter(x=>x.assessment&&roadmapAssessmentPublication(s,x.assessment)==='returned');
      n.drafts=n.options.filter(x=>['draft','unfinished'].includes(roadmapAssessmentPublication(s,x.assessment)));
      const key=selected&&roadmapOptionKind(selected);
      n.selected=selected&&stage.kinds.includes(key)?selected:null;
      const selectedKnown=selected&&n.options.find(x=>x.option_id===selected.option_id);
      if(!n.selected&&selectedKnown)n.selected=selected;
      const found=stage.id==='mechanisms'?'기전·접근':'후보';
      n.summary=n.selected?n.selected.label
        :n.recommended.length?`${n.recommended[0].label}${n.recommended.length>1?` 외 추천 ${n.recommended.length-1}개`:''}`
        :n.reviewed.length?`${n.reviewed[0].label} · ${n.reviewed[0].assessment.status==='needs_evidence'?'근거 확인 필요':n.reviewed[0].assessment.status==='deferred'?'현재 보류':'검토 기록 있음'}`
        :n.count?`${found} ${n.count}개를 찾았고 아직 순위를 매기지 않았습니다`:`${found}을 아직 찾지 못했습니다`;
      n.status=n.selected?'연구자 선택':n.recommended.length?`추천 ${n.recommended.length}개`:n.reviewed.length?`검토 기록 ${n.reviewed.length}개`:n.count?`찾은 것 ${n.count}개`:'아직 없음';
      n.mark=n.selected?'selected':n.recommended.length?'proposed':n.count?'recorded':'empty';
      if(!n.selected&&!n.recommended.length&&n.drafts.length){n.status=`검토 중 ${n.drafts.length}개`;n.mark='draft'}
      if(n.selected?.state_rev<s.rev||(!n.recommended.length&&!n.drafts.length&&n.options.some(x=>x.assessment?.current_conditions===false))){n.status='이전 조건의 판단';n.mark='earlier'}
      if(addedInputs.some(e=>stage.kinds.includes(roadmapOptionKind(e.body.discovery_selection??{}))))n.change='선택 추가';
      if(stage.id==='mechanisms'&&previous&&!roadmapSame(previous.alternatives,dec.alternatives))n.change='비교안 변경';
    }
    if(stage.id==='goal'){
      const goal=goalRows.find(r=>r.origin==='researcher')??goalRows[0];
      const first=events.find(e=>e.kind==='message');
      n.summary=goal?.text??first?.body.text??'질환과 바꾸려는 결과를 알려주세요';
      n.status=goal?(goal.origin==='researcher'?'연구자가 적은 목표':goal.origin==='unknown'?'조건 미확인':'모델이 정리한 목표'):first?'원 요청만 있음':'입력 대기';
      n.mark=goal||first?'recorded':'empty';
      if(intentChanged)n.change='의도 수정';else if(labelChanged(diffs?.goals))n.change='조건 기록 변경';
    }
    if(stage.id==='evidence'){
      n.summary=dec?`가설 ${hypotheses.length}개와 그 근거·적용 조건`:s.artifacts?.length?`자료 ${s.artifacts.length}개를 모았고 해석 전입니다`:'근거를 찾고 계산 결과를 대조합니다';
      n.status=dec?(current?`가설 ${hypotheses.length}개`:'이전 판단'):s.artifacts?.length?`자료 ${s.artifacts.length}개 · 판단 전`:'확인 전';
      n.mark=dec?(current?'recorded':'earlier'):s.artifacts?.length?'recorded':'empty';
      if(labelChanged(diffs?.hypotheses))n.change='판단 기록 변경';
      else if(changes.sources?.length)n.change='자료 추가';
    }
    if(stage.id==='next'){
      n.summary=checks[0]?.question??dec?.next_actions?.[0]??'근거를 비교한 뒤 다음 확인을 제안합니다';
      n.status=checks.length?(current?`제안 ${checks.length}개`:'이전 조건의 제안'):dec?.next_actions?.length?(current?'후속 제안':'이전 조건의 제안'):'아직 제안 전';
      n.mark=dec?(current?'proposed':'earlier'):'empty';
      const run=checks.length&&(s.research_checks??[]).find(x=>x.decision_id===s.decision_id&&x.check_id===checks[0].id);
      const job=run&&(s.jobs??[]).find(j=>j.id===run.job_id);
      if(job){n.jobStatus=job.status;n.status=['running','queued'].includes(job.status)?'확인 실행 중':['succeeded','reused'].includes(job.status)?'결과 해석 확인':'실행 상태 확인'}
      if(labelChanged(diffs?.checks)||previous&&!roadmapSame(previous.next_actions,dec.next_actions))n.change='다음 확인 변경';
    }
    if(running&&!current&&stage.id!=='goal'&&n.mark==='empty'){n.status='조사 중 · 판단 전';n.mark='working'}
    return n;
  });
  // A result the researcher entered is the point of the loop, so the judgement that followed it
  // should not be two clicks away. This only reports order of record: it does not claim the
  // observation caused the change.
  const lastObservation=(s.events??[]).filter(e=>e.kind==='observation').at(-1);
  const answeredObservation=lastObservation&&Number.isInteger(publication?.seq)
    &&publication.seq>lastObservation.seq?lastObservation:null;
  return {nodes,current,running,hasNewInput,selected,previous,priorLink,diffs,publication,answeredObservation,
    currentDecisionId:s.decision_id??null,historyStatus:previous?'ready':history.status==='ready'?'unavailable':history.status,
    changedNodes:nodes.filter(n=>n.change).map(n=>n.id)};
}

// Match by the exact result artifact, never by a reused NC number or array order.
function currentResearchActivity(snapshot){
  const jobs=snapshot?.jobs??[], active=j=>['queued','running'].includes(j.status);
  const recent=rows=>[...rows].sort((a,b)=>String(b.updated??b.created??'').localeCompare(String(a.updated??a.created??'')));
  const direct=recent(jobs.filter(j=>j.kind==='research_check'&&active(j)&&j.request?.check?.question))[0];
  if(direct)return {question:direct.request.check.question,checkJobId:direct.id,
    status:direct.status==='queued'?'선택한 확인 대기 중':'선택한 확인 실행 중'};
  const publication=(snapshot.events??[]).find(e=>e.kind==='decision_published'&&e.body?.receipt_id===snapshot.decision_id);
  const supersededPause=planner=>{
    const stopped=(snapshot.events??[]).filter(e=>e.kind==='job_finished'&&e.body?.job_id===planner.id&&e.body?.status==='paused').at(-1);
    // Publication need not increase the input revision. Match the actual receipt
    // and recorded event order; a later paused review must still be visible.
    return Number.isInteger(publication?.seq)&&Number.isInteger(stopped?.seq)&&stopped.seq<publication.seq;
  };
  for(const planner of recent(jobs.filter(j=>j.kind==='planner'&&(active(j)||j.status==='paused'&&j.based_rev===snapshot.rev&&!supersededPause(j))))){
    const sources=new Set((planner.request?.source_views??[]).map(v=>v.artifact_id));
    const check=recent(jobs.filter(j=>j.kind==='research_check'&&sources.has(j.output_id)&&j.request?.check?.question))[0];
    if(check)return {question:check.request.check.question,checkJobId:check.id,plannerJobId:planner.id,
      status:planner.status==='paused'?'해석 보류 · 원기록 보존':check.status==='failed'?'확인 실패 기록 검토 중':'새 결과 검토 중'};
  }
  return null;
}

// Which recorded tools were run, returned to the model, and cited by the published
// judgment. "Returned" is delivery, not reading; "cited" is a recorded link in the
// decision, not scientific validation. Results without a job (later re-runs or
// imports) and failed jobs without a result both stay visible.
const ROADMAP_NON_TOOL_JOBS=['planner','research_check','coordinator_review','execution_review','explanation'];
function roadmapCitedSources(decision){
  const ids=new Set((decision?.evidence_refs??[]).map(x=>String(x).split('#')[0]));
  for(const c of roadmapClaimRecords(decision))for(const e of c.evidence??[])if(e?.source_id)ids.add(String(e.source_id).split('#')[0]);
  return ids;
}
function roadmapArgumentText(args,limit=90){
  if(!args||typeof args!=='object')return '';
  const pairs=Object.entries(args).filter(([,v])=>v!==null&&v!==undefined&&v!=='').map(([k,v])=>`${k}: ${typeof v==='object'?JSON.stringify(v):v}`);
  return roadmapSummary(pairs.join(', '),limit);
}
function roadmapToolUsage(snapshot){
  const s=snapshot??{},artifacts=s.artifacts??[],jobs=s.jobs??[];
  const current=!!s.decision&&s.decision_rev===s.rev;
  const cited=roadmapCitedSources(s.decision);
  const returned=new Set();
  for(const a of artifacts)if(a.kind==='tool_reading'){
    const m=a.meta??{};
    for(const id of [m.source_artifact_id,m.arguments?.artifact_id,...(m.source_artifact_ids??[])])if(id)returned.add(id);
  }
  for(const j of jobs)for(const v of j.request?.source_views??[])if(v?.artifact_id)returned.add(v.artifact_id);
  const byOutput=new Map(jobs.filter(j=>j.output_id).map(j=>[j.output_id,j]));
  const groups=new Map();
  const group=kind=>{if(!groups.has(kind))groups.set(kind,{kind,runs:0,statuses:{},items:[],returned:0,cited:0});return groups.get(kind)};
  for(const a of artifacts){
    if(!a.meta?.result_status||['model_receipt','tool_reading'].includes(a.kind))continue;
    const g=group(a.kind),job=byOutput.get(a.id),status=a.meta.result_status;
    const item={id:a.id,status,input:roadmapArgumentText(a.meta.arguments??job?.request),created:a.created??null,
      jobId:job?.id??null,returned:returned.has(a.id),cited:cited.has(a.id)};
    g.runs++;g.statuses[status]=(g.statuses[status]??0)+1;g.items.push(item);
    if(item.returned)g.returned++;if(item.cited)g.cited++;
  }
  const results=new Set(artifacts.map(a=>a.id));
  for(const j of jobs){
    if(ROADMAP_NON_TOOL_JOBS.includes(j.kind)||(j.output_id&&results.has(j.output_id)))continue;
    const g=group(j.kind);g.runs++;g.statuses[j.status]=(g.statuses[j.status]??0)+1;
    g.items.push({id:null,status:j.status,input:roadmapArgumentText(j.request),created:j.created??null,jobId:j.id,returned:false,cited:false});
  }
  const models={};
  for(const a of artifacts)if(a.kind==='model_receipt'){const m=a.meta?.requested_model??'unknown';models[m]=(models[m]??0)+1}
  const tools=[...groups.values()].sort((a,b)=>b.cited-a.cited||b.returned-a.returned||b.runs-a.runs||a.kind.localeCompare(b.kind));
  return {tools,current,runs:tools.reduce((n,t)=>n+t.runs,0),
    returned:tools.reduce((n,t)=>n+t.returned,0),cited:tools.reduce((n,t)=>n+t.cited,0),
    citedOutsideTools:[...cited].filter(id=>!artifacts.some(a=>a.id===id&&a.meta?.result_status)).length,
    modelCalls:Object.entries(models).map(([model,count])=>({model,count})).sort((a,b)=>b.count-a.count)};
}

// What the running planner has actually recorded so far: its returned tool calls,
// completed model calls and the notes it saved before the latest operation. The
// notes are provisional working text, not findings or a judgment.
function roadmapLiveProgress(snapshot,nowMs=Date.now()){
  const s=snapshot??{},jobs=s.jobs??[];
  const planner=[...jobs].reverse().find(j=>j.kind==='planner'&&j.based_rev===s.rev&&['queued','running'].includes(j.status));
  if(!planner)return null;
  const mine=a=>a.meta?.job_id===planner.id;
  const functions={};
  for(const r of (s.artifacts??[]).filter(a=>a.kind==='tool_reading'&&mine(a))){const f=r.meta?.function??'unknown';functions[f]=(functions[f]??0)+1}
  const started=Date.parse(planner.created);
  const notes=s.research_progress?.job_id===planner.id?s.research_progress.notes:null;
  return {jobId:planner.id,status:planner.status,started:planner.created,
    elapsedMinutes:Number.isFinite(started)?Math.max(0,Math.floor((nowMs-started)/60000)):null,
    completedCalls:(s.artifacts??[]).filter(a=>a.kind==='model_receipt'&&mine(a)).length,
    functions,nextGoal:notes?.next_goal??null,findings:(notes?.findings??[]).length};
}


;
/* Source: roadmap.js */
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


;
/* Source: research-path.js */
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


;
/* Source: source-display.js */
// Presentation only: never rewrite a quote, original record, locator or identity.
function sourceDisplayText(value){
 let text=String(value??'');
 const entities={amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' ',ndash:'–',mdash:'—',micro:'µ'};
 for(let i=0;i<2;i++)text=text.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp|ndash|mdash|micro);/gi,(whole,name)=>{if(name[0]!=='#')return entities[name.toLowerCase()]??whole;const n=name[1].toLowerCase()==='x'?parseInt(name.slice(2),16):parseInt(name.slice(1),10);return n>0&&n<=0x10ffff&&!(n>=0xd800&&n<=0xdfff)?String.fromCodePoint(n):whole});
 return text.replace(/<\/?(?:sub|sup)\b[^>]*>/gi,'');
}
function sourceBibliography(result,row){
 const actual=row??(Array.isArray(result?.rows)&&result.rows.length===1?result.rows[0]:null);
 const value=actual??(result?.semantic_type==='open_article'||result?.pmc_id?result:null);
 if(!value)return null;
 const title=value.title??value.articleTitle;
 if(typeof title!=='string'||!title.trim())return null;
 const authors=value.authorString??value.authors??value.author;
 return {title:sourceDisplayText(title),authors:typeof authors==='string'?sourceDisplayText(authors):null,year:value.pubYear??value.year??value.publicationYear??null,studyType:value.publicationType??value.study_type??value.publication_types??value.pubTypeList?.pubType??null,pmid:value.pmid??(value.source==='MED'?value.id:null),doi:value.doi??null};
}
function sourceDisplayLabel(artifact,result,row){
 const b=sourceBibliography(result,row);
 if(b)return [b.authors?.includes(',')?b.authors.split(',')[0]+' 외':b.authors,b.year,b.title.length>130?b.title.slice(0,130)+'…':b.title].filter(Boolean).join(' · ');
 if(artifact?.kind==='literature')return '검색 결과 묶음';
 if(artifact?.kind==='public_lookup_bundle')return '공개 자료 조회 묶음';
 if(artifact?.kind==='article')return '보존한 원문 · '+sourceDisplayText(artifact.title??'문헌');
 return sourceDisplayText(artifact?.title??'자료 묶음');
}
function sourceBibliographyView(result,row){
 const b=sourceBibliography(result,row);if(!b)return '<p class="small muted">검색 결과 묶음 · 특정 문헌은 연결된 원행에서 확인하세요.</p>';
 return `<section class="source-bibliography"><strong>${esc(b.title)}</strong><p class="small">${[b.authors,b.year,Array.isArray(b.studyType)?b.studyType.join(' · '):b.studyType].filter(Boolean).map(esc).join(' · ')}</p>${b.pmid||b.doi?`<p class="small">${b.pmid?'PMID '+esc(b.pmid):''}${b.doi?' · DOI '+esc(b.doi):''}</p>`:''}</section>`;
}
function sourceLocatorDetails(artifact,anchor){return `<details class="source-technical-locator"><summary>출처 위치·조회 기록</summary><p>${esc(artifact?.title??'')} · <code>${esc(artifact?.id??'')}</code></p>${Number.isInteger(anchor?.offset)?`<p>저장 원행 인덱스 ${anchor.offset} · 0부터 셈</p>`:''}${Number.isInteger(anchor?.row_index)?`<p>저장 원행 인덱스 ${anchor.row_index} · 0부터 셈</p>`:''}</details>`;}
// Call only for display titles in an already-created source view. TextContent prevents external HTML execution.
function normalizeSourceTitleNodes(container){for(const node of container.querySelectorAll('.source-bibliography strong, .source-paragraph h3, td a[href*="europepmc.org"]'))node.textContent=sourceDisplayText(node.textContent);}
function sourceFigureScope(figure){
 // Caption remains exact; no guessed drug/model/readout from a title or thumbnail.
 const caption=String(figure?.caption??'');
 if(!/BI\s*1015550/i.test(caption)||!/PBMC|peripheral blood mononuclear/i.test(caption)||!/TNF|tumor necrosis/i.test(caption)||!/IL-2|interleukin-2/i.test(caption))return '<p class="small muted">원논문의 시험 물질·모델·판독은 원 캡션에서 확인하세요.</p>';
 return '<p class="small muted">원논문 범위: BI 1015550 · 사람 PBMC의 cytokine 판독(TNF-α·IL-2). 이 그림의 측정 대상은 BI 1015550이며, 생성 후보의 기능은 후보별 시험에서 확인합니다.</p>';
}

const sourceDisplayCache=new Map();
function sourceDisplayRow(artifact,anchor,wid=state?.id){
 if(!artifact||anchor?.artifact_id!==artifact.id||!Number.isInteger(anchor.row_index))return null;
 return sourceDisplayCache.get(`${wid}:${artifact.id}:${artifact.sha256}:${anchor.row_index}`)?.row??null;
}
async function warmSourceDisplayAnchors(snapshot,request=api){
 const anchors=(snapshot?.discovery?.mechanisms_and_approaches??[]).concat(snapshot?.discovery?.recommendations??[]).flatMap(item=>item.assessment?.basis?.clauses??[]).map(c=>c.anchor).filter(a=>a?.artifact_id&&Number.isInteger(a.row_index)&&a.row_index>=0);
 const requests=[];
 for(const anchor of anchors){
  const artifact=snapshot.artifacts.find(a=>a.id===anchor.artifact_id);if(!artifact)continue;
  const key=`${snapshot.id}:${artifact.id}:${artifact.sha256}:${anchor.row_index}`;if(sourceDisplayCache.has(key))continue;
  sourceDisplayCache.set(key,{pending:true});
  requests.push((async()=>{try{const value=await request(`/api/workspaces/${encodeURIComponent(snapshot.id)}/artifacts/${encodeURIComponent(artifact.id)}?offset=${anchor.row_index}&limit=1`);const row=value.result?.rows?.[0];sourceDisplayCache.set(key,{row:value.result?.offset===anchor.row_index?row:null});}catch(_){sourceDisplayCache.set(key,{row:null});}})());
  if(requests.length>=16)break;
 }
 await Promise.all(requests);
}


;
/* Source: research-display.js */
// Browser-only projections of saved records. Never a scientific rank or a stored relation.
const uiGenerationViews=new Map(), uiExperimentReturns=new Map();
function uiCurrentPaths(){
  return pathMechanisms().filter(x=>pathCurrent(x.assessment)&&x.assessment.status!=='deferred');
}
function uiPathKind(option){return option.kind==='approach'?'설계·시험 접근':'생물학적 기전'}
function uiDecisionScope(){
  const paths=uiCurrentPaths(),mechanisms=paths.filter(x=>x.kind==='mechanism').length;
  const approaches=paths.filter(x=>x.kind==='approach').length,checks=state.decision?.research_loop?.next_checks?.length??0;
  return [mechanisms?`기전 ${mechanisms}개`:null,approaches?`접근 ${approaches}개`:null,`다음 확인 ${checks}건`].filter(Boolean).join(' · ');
}
function uiPathSummary(){return uiCurrentPaths().map(x=>`<li><span class="ui-eyebrow">${esc(uiPathKind(x))}</span><strong>${esc(researcherWording(x.label))}</strong><span>${esc(optionStatus[x.assessment.status])}</span></li>`).join('')}
function uiGenerationKey(id){return `${candidateStructuresKey()}:${id}`}
function uiGenerationData(id){return uiGenerationViews.get(uiGenerationKey(id))}
async function uiLoadGeneration(id){
  const wid=state.id,key=uiGenerationKey(id);if(uiGenerationViews.has(key))return;
  const artifact=state.artifacts.find(x=>x.id===id&&x.kind==='analogue_proposal');if(!artifact)return;
  uiGenerationViews.set(key,{loading:true});
  try{const value=await api(`/api/workspaces/${encodeURIComponent(wid)}/artifacts/${encodeURIComponent(id)}?offset=0&limit=100`);
    if(uiGenerationKey(id)!==key)return;
    uiGenerationViews.set(key,{value,artifact});
  }catch(error){if(uiGenerationKey(id)===key)uiGenerationViews.set(key,{error:'생성 원자료를 읽지 못했습니다.'})}
  if(uiGenerationKey(id)===key)render();
}
function uiGenerationCount(item){
  const data=uiGenerationData(item?.candidate_artifact_id)?.value?.result;
  return Number.isInteger(data?.total_rows)?data.total_rows:data?.has_more===false?data.rows?.length:null;
}
function uiCandidateRole(item){
  if(item?.origin!=='generated_structure_proposal')return '';
  const a=item.assessment,reason=a?.reason??'',count=uiGenerationCount(item);
  const role=reason.includes('시험 대응 예시')?'시험 대응 예시':a?'개별 검토한 생성 후보':'생성 집합의 후보 · 개별 검토 전';
  return `<p class="ui-candidate-role"><strong>${esc(role)}</strong>${count!=null?` · 생성 집합 ${count}개 중 1개`:''}${reason.includes('시험 대응 예시')&&a.priority==null?' · 효능 순위 미부여':''}</p>`;
}
function uiGenerationLink(item){
  if(item?.origin!=='generated_structure_proposal'||!item.candidate_artifact_id)return '';
  const count=uiGenerationCount(item);
  queueMicrotask(()=>uiLoadGeneration(item.candidate_artifact_id));
  return button('ui-generated-group',count!=null?`같은 생성 집합 ${count}개 · 출발 화합물 보기`:'같은 생성 집합 · 출발 화합물 보기',`data-id="${esc(item.candidate_artifact_id)}"`,'link-button small');
}
function uiGeneratedGroup(panel){
  const data=uiGenerationData(panel.id);if(!data||data.loading)return '<p role="status">보존된 생성 목록을 읽고 있습니다.</p>';
  if(data.error)return uiEmpty(data.error);
  const result=data.value?.result??{},rows=result.rows??[];
  return `<p>같은 실행에서 생성한 ${esc(result.total_rows??rows.length)}개 구조를 원자료 순서로 표시합니다. 후보별 개별 검토 여부를 함께 확인하세요.</p><div class="ui-generated-list">${rows.map((row,i)=>{
    const id=`molecule:generated:${panel.id}:${row.candidate_id}`;
    const item=candidateOptions().find(x=>x.option_id===id),a=item?.assessment;
    return `<article class="ui-generated-row" data-generated-candidate="${esc(id)}">${structureThumb(row)}<div><h3>${esc(row.candidate_id)}</h3><p>출발 화합물 <strong>${esc(row.transformed_from??row.core_from??'확인 필요')}</strong></p><p class="small">${a?`${esc(optionStatus[a.status])} · ${uiRevision(a)}`:'개별 검토 전'} · 생성 단계 활성 미측정</p>${button('discovery-detail','이 후보 상세',`data-id="${esc(id)}"`,'small')}${button('source','생성 원행',`data-id="${esc(panel.id)}" data-source-offset="${(result.offset??0)+i}"`,'link-button small')}</div></article>`;
  }).join('')}</div>${result.has_more?uiEmpty('첫 페이지입니다. 생성 원자료에서 나머지 행을 확인하세요.'):''}${sourceLinks([panel.id])}`;
}
function uiTokenMention(text,value){
  if(!value)return false;
  const escaped=String(value).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  return new RegExp(`(^|[^A-Za-z0-9_-])${escaped}(?=$|[^A-Za-z0-9_-])`,'i').test(text);
}
function uiCandidateExperimentLinks(item,row,checks){
  const exact=[],mentioned=[],shared=[];
  const a=item.assessment??{},h=a.basis?.hypothesis_id;
  const sourceIds=new Set([item.candidate_artifact_id,...(a.support_source_ids??[]),...(item.sources??[]).map(x=>x.artifact_id)].filter(Boolean));
  const parent=item.generation?.transformed_from??row?.transformed_from??row?.core_from;
  const entity=item.entity_id??row?.candidate_id,match=String(entity??'').match(/^proposed-(\d+)$/);
  const aliases=[entity,item.option_id,...(match?[`제안 ${match[1]}`,`설계 후보 ${match[1]}`]:[])].filter(Boolean);
  for(const check of checks){
    const refs=[...(check.candidate_refs??[]),...(check.operation?.candidate_refs??[])];
    const explicit=refs.some(ref=>ref===item.option_id||ref?.option_id===item.option_id||(ref?.candidate_id===entity&&ref?.artifact_id===item.candidate_artifact_id));
    if(explicit||(h&&check.hypothesis_ids?.includes(h))){exact.push({check,label:explicit?'후보 ID로 연결됨':'후보 평가와 같은 가설에 연결됨'});continue}
    const text=[check.question,check.purpose,check.operation?.request].filter(Boolean).join('\n');
    const common=(check.operation?.grounded_in??[]).filter(id=>sourceIds.has(id));
    if(!common.length)continue;
    const named=aliases.some(alias=>uiTokenMention(text,alias));
    if(named&&(!parent||uiTokenMention(text,parent))){mentioned.push({check,label:'본문에 후보·비교 대상 명시 · 연결 확인 필요',common});continue}
    // A shared source is not a candidate edge. Do not associate another numbered proposal.
    if(!/(?:proposed-|제안\s*|설계 후보\s*)\d+/i.test(text))shared.push({check,label:'같은 자료를 인용한 권고 · 후보별 연결 확인 필요',common});
  }
  return {exact,mentioned,shared};
}
function uiRelatedExperiments(item,row){
  const links=uiCandidateExperimentLinks(item,row,state.decision?.research_loop?.next_checks??[]);
  const group=(title,rows)=>rows.length?`<section class="ui-related-group"><h3>${title}</h3>${rows.map(({check,label})=>`<p class="small muted">${esc(label)}</p>${button('ui-related-experiment',esc(uiExperimentAlias(check)),`data-id="${esc(check.id)}"`,'ui-linked-check')}<details><summary>권고 본문에서 확인</summary><p>${uiText(check.question)}</p></details>`).join('')}</section>`:'';
  return group('기록된 연결',links.exact)+group('본문으로 연결을 확인할 실험',links.mentioned)+group('자료를 함께 사용하는 권고',links.shared)+
    (!links.exact.length&&!links.mentioned.length&&!links.shared.length?uiEmpty('이 후보를 특정한 실험 연결 확인 필요'):'')+`<p class="small muted">본문 명시와 공통 자료는 저장된 후보–실험 ID 연결과 구분합니다.</p>${button('ui-stage','현재 연구의 실험 전체','data-stage="next"','small')}`;
}
async function uiLoadParentStructures(panel){
  const key=candidateStructuresKey(),wid=state.id;
  const links=panel.item.generation?.parent_links??[];
  const parent=panel.item.generation?.transformed_from??candidateStructureRow(panel.id)?.transformed_from;
  const actual=links.filter(x=>x.candidate_id===parent);
  panel.parentStructures=[];
  for(const link of actual){
    if(link.status!=='resolved'||link.option_ids?.length!==1){panel.parentStructures.push({link,missing:'출발 화합물의 유일한 구조 연결 확인 필요'});continue}
    try{const value=await api(`/api/workspaces/${encodeURIComponent(wid)}/candidate-structures?option_id=${encodeURIComponent(link.option_ids[0])}`);
      if(candidateStructuresKey()!==key)return;
      const row=value.rows?.find(x=>x.option_id===link.option_ids[0]);
      panel.parentStructures.push({link,row,missing:row?.depiction?.status==='drawn'?null:'연결된 출발 화합물에 그릴 수 있는 구조가 없습니다.'});
    }catch{panel.parentStructures.push({link,missing:'출발 화합물의 구조 자료를 읽지 못했습니다.'})}
  }
  panel.parentStructuresLoaded=true;if(candidateStructuresKey()===key&&currentReader()===panel)render();
}
function uiCandidatePair(panel,row){
  const item=panel.item;if(item.origin!=='generated_structure_proposal')return '';
  const actual=item.generation?.transformed_from??row?.transformed_from;
  const sources=item.generation?.source_artifact_ids??[];
  return `<section class="ui-structure-comparison"><h3>출발 화합물과 생성 후보</h3><p class="small muted">저장된 변환 관계와 구조 문자열을 나란히 표시합니다.</p><div class="ui-structure-pair"><article><h4>출발 화합물 · ${esc(actual??'관계 확인 필요')}</h4>${!panel.parentStructuresLoaded?'<p role="status">연결된 구조를 읽고 있습니다.</p>':panel.parentStructures?.length?panel.parentStructures.map(p=>`${p.row?structureFigure(p.row.depiction,p.link.candidate_id):''}${p.missing?uiEmpty(p.missing):''}${p.row?`<details><summary>출발 구조·원 기록</summary>${structureFacts(p.row)}${json(Object.fromEntries(Object.entries(p.row).filter(([k])=>k!=='depiction')))}</details>`:''}`).join(''):uiEmpty('출발 화합물의 구조화된 연결 확인 필요')}<p class="small">측정값과 시험 조건은 출발 자료에서 확인합니다.</p>${sourceLinks(sources)}</article><article><h4>생성 후보 · ${esc(item.entity_id)}</h4>${row?structureFigure(row.depiction,item.entity_id):uiEmpty('후보 구조 확인 필요')}<p class="small">생성 단계 활성 미측정</p>${sourceLinks([item.candidate_artifact_id])}</article></div></section>`;
}
function uiCandidateProperties(row){
  const copy={...row,depiction:{...row.depiction}};
  const massKnown=Number.isFinite(row.MolWt)&&Number.isFinite(row.depiction?.average_mass);
  const sameRounding=massKnown&&Math.abs(row.MolWt-row.depiction.average_mass)<=0.050001;
  if(Number.isFinite(row.MolWt)&&(sameRounding||!Number.isFinite(row.depiction?.average_mass)))copy.depiction.average_mass=String(row.MolWt);
  const massConflict=massKnown&&!sameRounding?`<p class="ui-missing">계산 기록 사이의 분자량 차이 확인 필요 · 생성 기록 ${esc(row.MolWt)} g/mol · 구조 묘사 계산 ${esc(row.depiction.average_mass)} g/mol</p>`:'';
  const defs=[['LogP','LogP','지용성 추정값입니다. 값이 높을수록 지용성이 큽니다.'],['TPSA','극성 표면적','구조에서 계산한 극성 표면적(Å²)입니다.'],['QED','QED','일반적인 경구 약물 물성의 균형을 나타내는 0–1 지표입니다.'],['SA_score','합성 접근성','구조 복잡도 기반 추정입니다. 낮을수록 합성이 수월할 것으로 추정합니다.']];
  return `${massConflict}${structureFacts(copy)}<dl class="ui-facts">${defs.filter(([key])=>row[key]!==undefined).map(([key,label,meaning])=>`<div><dt>${label}</dt><dd>${esc(row[key])}<small>${meaning}</small></dd></div>`).join('')}</dl><p class="small muted">물성·구조 기반 지표이며 활성, 체내 효능, 실제 합성 성공은 각 실험으로 확인합니다.</p><details><summary>계산별 원값·구조·생성 기록</summary><p>반올림 차이는 생성 기록의 정밀도로 표시하며, 그보다 큰 차이는 별도로 표시합니다. 각 계산의 원값을 보존합니다.</p>${json(Object.fromEntries(Object.entries(row).filter(([k])=>k!=='depiction')))}${json(Object.fromEntries(Object.entries(row.depiction??{}).filter(([k])=>k!=='svg')))}</details>`;
}
function uiExperimentAlias(check){
  const text=[check.question,check.operation?.request].join(' '),read=experimentFields(check).found;
  const targets=[...new Set(text.match(/\b(?:PDE\d+[A-Z]\d*|LPAR\d+|STMN\d+|FAAH|LOX|FTIR|sFlt-?1|TTR)\b/g)??[])];
  if(targets.length)return targets.slice(0,3).join(' · ')+(text.includes('IC50')?' 효소 기능 비교':text.includes('칼슘')?' 기능 반응 비교':' 판별 실험');
  const n=(state.decision?.research_loop?.next_checks??[]).findIndex(c=>c.id===check.id)+1;
  return `${CHECK_KIND[check.operation?.kind]??'확인'} ${n>0?n:''} · ${roadmapSummary(researcherWording(read['측정 대상']?.[0]??check.question),42)}`;
}
function uiExecutionConditions(check){
  if(check.operation?.kind!=='external_observation')return '';
  const needed=check.operation.needed_inputs??[],request=check.operation.request??'';
  const explicit=request.split(/\n/).filter(x=>/확인|실제|기록|정하지|지정하지|미정|반복/.test(x));
  return `<details class="ui-execution-conditions"><summary>실행 전에 확인할 조건</summary><p class="small">시료·시험계, 농도·시점, 반복 단위와 수, 분석·판정 기준을 실제 수행 조건으로 확인해 주세요. 아래는 저장된 권고의 확인 사항입니다.</p>${needed.length?list(needed):''}${explicit.map(x=>`<p>${uiText(x)}</p>`).join('')||uiEmpty('구체적인 수행 조건의 확인 기록이 필요합니다.')}<p class="small muted">이 확인 목록은 수행 완료나 실측 결과를 뜻하지 않습니다.</p></details>`;
}

const uiSourcesWarmed=new Set();
function uiWarmSources(){const key=candidateStructuresKey();if(uiSourcesWarmed.has(key))return;uiSourcesWarmed.add(key);const snapshot=state;void warmSourceDisplayAnchors(snapshot).then(()=>{if(candidateStructuresKey()===key)render()})}


;
/* Source: workspace-ui.js */
// Reading state belongs to the browser. Scientific records and their ordering stay unchanged.
const researchReaders = new Map(), experimentSelections = new Map(), candidateViews = new Map();
const researchSubjects = new Map(), outcomeSelections = new Map();
let workspaceWide=false, conversationOpen=false;
let readerRequest = 0, researchSearch = '', researchListMode = 'recent', researchRailCollapsed = true;
const readerHistoryFrames=new Map();
let renderedResearchPanel=null;
const workspaceTabs = [['','한눈에 보기'],['mechanisms','기전'],['candidates','후보'],['next','실험'],['evidence','근거']];
function uiIcon(name){
  const paths={menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',mechanism:'<rect x="9" y="2" width="6" height="5" rx="1"/><rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/><path d="M12 7v5M5 17v-5h14v5"/>',molecule:'<path d="m12 2 8.5 5v10L12 22l-8.5-5V7Z"/><path d="m6.5 8.5 5.5-3.2M17.5 9v6M12 18.5l-5.5-3.2"/>',experiment:'<path d="M8 2h8M10 2v7l-6.5 10A2 2 0 0 0 5.2 22h13.6a2 2 0 0 0 1.7-3L14 9V2M7 15h10"/>'};
  return `<svg class="ui-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]??paths.molecule}</svg>`;
}
function uiQuickLinks(){return `<nav class="ui-quick-links" aria-label="연구 바로가기">${[['mechanisms','mechanism','기전과 후보의 연결'],['candidates','molecule','후보 구조와 검토'],['next','experiment','실험 설계와 판독']].map(([stage,icon,label])=>button('ui-stage',`${uiIcon(icon)}<span>${label}</span>`,`data-stage="${stage}"`,'ui-quick-link')).join('')}</nav>`}
function readerState(){return state?researchReaders.get(state.id):null}
function currentReader(){return readerState()?.stack.at(-1)??null}
function uiText(value){return judgmentText(researcherWording(value))}
function uiEmpty(text){return `<p class="ui-missing">${esc(text)}</p>`}
function syntheticInputNotice(){const rows=state.events.filter(e=>['message','observation','correction'].includes(e.kind)&&inputProvenance(e).synthetic);return rows.length?`<details><summary>가상 목표·입력 ${rows.length}건 포함</summary>${rows.map(e=>button('message-source','입력 원문',`data-id="${esc(e.body.message_id)}"`,'link-button small')).join('')}<p>가상 시연 입력으로 구분해 보존했습니다.</p></details>`:''}
function uiRevision(a){return !a?'검토 전':a.current_conditions===true?'현재 조건':a.current_conditions===false?'이전 조건':'적용 조건 확인 필요'}
function uiExcerpt(value){
  // A labelled verbatim first paragraph/sentence, never an inferred scientific summary.
  const text=String(value??'').trim();
  const boundary=text.search(/(?:[.!?。](?=\s|$)|\n)/);
  return boundary>=0?text.slice(0,boundary+1):text;
}
function uiStage(){return tab==='research'?(roadmapChosen()??''):tab}
// Navigation preferences only. These IDs never enter a scientific ranking or a job.
const INITIAL_PINNED_RESEARCH=['ws_3c8fe9df9cd14339','ws_4475545a286541b2','ws_1ff05aa2d7c24e0e'];
// Exact manually seeded screen fixtures, verified against their original creation scripts.
// This is navigation metadata only: no title matching, job-state filtering or record deletion.
const ARCHIVED_RESEARCH_EXAMPLES=Object.freeze({
  ws_741a80721d08469f:'순위 화면 점검용 고정 자료',
  ws_05cd9d62e1664faa:'다섯 단계 화면 예시'
});
function isArchivedResearchExample(id){return Object.hasOwn(ARCHIVED_RESEARCH_EXAMPLES,id)}
function archivedResearchNotice(){
  if(!isArchivedResearchExample(state?.id))return '';
  return `<aside class="panel" data-archived-research="${esc(state.id)}" aria-label="보관된 개발 예시"><strong>보관된 개발 예시 · ${esc(ARCHIVED_RESEARCH_EXAMPLES[state.id])}</strong><p class="small">화면 점검용으로 직접 작성한 후보·판단입니다. 원 기록을 보존했습니다.</p>${button('project','실제 IPF 연구 열기','data-id="ws_3c8fe9df9cd14339"','link-button small')}</aside>`;
}
const RESEARCH_PIN_KEY='evida-pinned-research';
function pinnedResearchIds(){
  try{const saved=evidaStorage.getItem(RESEARCH_PIN_KEY);if(saved===null)return [...INITIAL_PINNED_RESEARCH];
    const ids=JSON.parse(saved);return Array.isArray(ids)?[...new Set(ids.filter(x=>typeof x==='string'))]:[];
  }catch{return []}
}
function researchRailGroups(){
  const q=researchSearch.toLocaleLowerCase(),pins=pinnedResearchIds(),rows=projects.filter(p=>!q||p.title.toLocaleLowerCase().includes(q));
  const pinned=pins.map(id=>rows.find(p=>p.id===id)).filter(Boolean),unpinned=rows.filter(p=>!pins.includes(p.id));
  const archived=unpinned.filter(p=>isArchivedResearchExample(p.id)),others=unpinned.filter(p=>!isArchivedResearchExample(p.id));
  return {pinned,archived,visibleTotal:pinned.length+others.length,others:researchListMode==='recent'&&!q?others.slice(0,8):others,hasMore:researchListMode==='recent'&&!q&&others.length>8};
}
function toggleResearchPin(id){
  if(!projects.some(p=>p.id===id))return false;
  const ids=pinnedResearchIds(),next=ids.includes(id)?ids.filter(x=>x!==id):[...ids,id];
  try{evidaStorage.setItem(RESEARCH_PIN_KEY,JSON.stringify(next));return true}
  catch{notice('이 브라우저에 고정 목록을 저장할 수 없습니다.');return false}
}
function researchRailRow(p,pinned){
  const pinIcon='<svg class="ui-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m9 3 6 0-1 6 4 4v2H6v-2l4-4-1-6ZM12 15v7"/></svg>';
  return `<div class="ui-project-row ${pinned?'is-pinned':''}" data-research-id="${esc(p.id)}">${button('project',`<span class="project-name">${esc(p.title)}</span><small class="project-status">${isArchivedResearchExample(p.id)?'개발 예시 · ':''}${Number.isInteger(p.rev)?'연구 기록 '+p.rev+' · ':''}${esc(({reviewed:'판단 기록 있음',needs_review:'판단 갱신 필요',awaiting_input:'입력 대기'})[p.review_status]??'상태 확인 필요')}</small>`,`data-id="${esc(p.id)}" aria-current="${p.id===state?.id?'page':'false'}"`,`project ${p.id===state?.id?'active':''}`)}${button('ui-pin-research',pinIcon,`data-id="${esc(p.id)}" aria-label="${esc(p.title)} · ${pinned?'고정 해제':'연구 고정'}" title="${pinned?'고정 해제':'연구 고정'}" aria-pressed="${pinned}"`,'ui-project-pin quiet small')}</div>`;
}
function uiDecisionRecord(id){
  const event=[...(state?.events??[])].reverse().find(e=>e.kind==='decision_published'&&e.body.receipt_id===id);
  if(!event)return null;
  const current=id===state.decision_id;
  return {id,rev:event.body.state_rev,current,title:`${current?'현재 게시 판단':'이전 판단'} · 연구 기록 ${event.body.state_rev}`};
}
function renderResearchRail(){
  const {pinned,others,archived,hasMore,visibleTotal}=researchRailGroups();
  return `<div class="rail-heading"><div class="brand">EVIDA</div>${button('ui-rail',uiIcon('menu'),`aria-label="연구 목록 ${researchRailCollapsed?'펼치기':'접기'}" aria-expanded="${!researchRailCollapsed}"`,'quiet small')}</div>
    ${button('new','＋ 새 연구','','new-button')}
    <div class="rail-browser"><label class="sr-only" for="research-search">저장된 연구 검색</label><input id="research-search" type="search" value="${esc(researchSearch)}" placeholder="연구 검색">
    <div class="rail-list-modes">${[['recent','최근 연구'],['all','전체 연구']].map(([id,label])=>button('ui-research-mode',label,`data-mode="${id}" aria-pressed="${researchListMode===id}"`,'quiet small')).join('')}</div>
    <div class="project-list"><nav aria-label="저장된 연구">${pinned.length?`<p class="rail-group-label">고정한 연구 <small>이 브라우저</small></p>${pinned.map(p=>researchRailRow(p,true)).join('')}`:''}${others.length?`<p class="rail-group-label">${researchListMode==='recent'&&!researchSearch?'최근 연구':'다른 연구'}</p>${others.map(p=>researchRailRow(p,false)).join('')}`:''}${!pinned.length&&!others.length?uiEmpty('일치하는 연구가 없습니다.'):''}</nav>
    ${hasMore?button('ui-research-mode',`연구 ${visibleTotal}개 보기`,'data-mode="all"','quiet small'):''}
    ${archived.length?`<details class="ui-secondary" data-detail-key="research-archive"><summary>개발 예시 보관함 · ${archived.length}개</summary><p class="small muted">화면 점검용 기록입니다. 원문과 후보를 그대로 보존합니다.</p><nav aria-label="보관된 개발 예시">${archived.map(p=>researchRailRow(p,false)).join('')}</nav></details>`:''}</div></div>`;
}
function renderDecisionWorkspace(){
  const stage=uiStage(),model=roadmapModel(),reading=currentReader();
  if(tab==='research'){queueMicrotask(()=>loadCandidateStructures());queueMicrotask(()=>loadMechanismRanking());queueMicrotask(()=>uiWarmSources())}
  const active=state.jobs.some(j=>['running','queued'].includes(j.status));
  const body=tab==='data'?dataView():tab==='history'?historyPanel():stage==='mechanisms'?renderResearchPath():stage==='candidates'?uiCandidates():stage==='next'?uiExperiments():stage==='evidence'?`${renderEvidenceWorkbench()}<details class="ui-secondary"><summary>계산·조회·근거의 전체 기록</summary>${roadmapEvidencePanel()}</details>`:stage==='goal'?roadmapGoalPanel():stage==='changes'?roadmapChangesPanel(model):uiOverview(model);
  return `${archivedResearchNotice()}<header class="ui-workspace-heading"><div><span class="ui-eyebrow">연구 워크스페이스</span><h1>${esc(state.title)}</h1><p>${esc(roadmapRevisionText(model))}</p></div><div class="ui-workspace-tools">${button('ui-question','질문하기',`aria-expanded="${conversationOpen}"`,'small ui-question-button')}${button('ui-wide',workspaceWide?'대화와 함께 보기':'넓게 보기',`aria-pressed="${workspaceWide}"`,'small quiet')}${button('ui-stage','목표·조건','data-stage="goal"','small quiet')}</div></header>
    ${quotaNotice()}${active?roadmapActivity():''}
    <div class="ui-research-layout"><aside class="ui-conversation" aria-label="연구 대화"><header class="ui-conversation-heading"><h2>연구 대화</h2>${button('ui-question-close','닫기','aria-label="연구 대화 닫기"','small quiet ui-conversation-close')}</header>${uiConversation()}${uiQuickLinks()}<div class="ui-conversation-compose">${uiComposer(active)}</div><details class="ui-secondary" data-detail-key="workspace-log"><summary>입력 변경·실행 기록</summary>${roadmapRunLine(active)}${renderInputChanges()}${syntheticInputNotice()}</details></aside>
    <div class="ui-work-product"><header class="ui-product-heading"><span>작업물</span><nav class="ui-stage-nav" aria-label="연구 작업 화면">${[...workspaceTabs,['data','원자료']].map(([id,label])=>button('ui-stage',label,`data-stage="${id}" aria-current="${stage===id?'page':'false'}"`,`ui-stage ${stage===id?'active':''}`)).join('')}</nav></header><div class="workspace-split ${reading?'with-reader':''}"><div class="workspace-content" id="workspace-content"><section id="roadmap-inspector" tabindex="-1">${body}</section></div>${reading?renderResearchPanel():''}</div></div></div>`;
}
function uiConversation(){
  const messages=state.events.filter(e=>['message','observation','correction'].includes(e.kind));
  const original=messages[0],latest=messages.at(-1),shown=original===latest?[original]:[original,latest];
  const source=e=>`${inputProvenanceNotice(e)}${button('message-source','입력 원문·출처',`data-id="${esc(e.body.message_id)}"`,'link-button small')}`;
  return `<div class="ui-conversation-thread">${original?`<article class="ui-conversation-message"><div class="ui-conversation-meta"><strong>연구자</strong><span>처음 요청</span></div><p class="prose">${esc(uiExcerpt(original.body.text))}</p>${String(original.body.text??'')!==uiExcerpt(original.body.text)?`<details><summary>입력 전문</summary><p class="prose">${esc(original.body.text)}</p></details>`:''}${source(original)}</article>`:uiEmpty('저장된 연구자 입력 확인 필요')}${latest&&latest!==original?`<details class="ui-latest-input"><summary>최근 입력·정정</summary><p class="prose">${esc(latest.body.text)}</p>${source(latest)}</details>`:''}<article class="ui-conversation-response"><div class="ui-conversation-meta"><strong>EVIDA</strong><span>${esc(uiDecisionScope())}</span></div>${state.decision?`<ul class="ui-conversation-paths">${uiPathSummary()}</ul><details><summary>판단 원문 앞부분</summary><p>${uiText(uiExcerpt(state.decision.recommendation))}</p></details>`:'<p>아직 판단이 기록되지 않았습니다.</p>'}${state.decision?button('ui-judgment','판단 전체·근거','','link-button small'):''}</article>${messages.length>shown.filter(Boolean).length?button('ui-stage',`중간 입력 ${messages.length-shown.filter(Boolean).length}건 · 변경 기록`,'data-stage="history"','link-button small'):''}</div>`;
}
function uiOverview(model){
  const d=state.decision,node=model.nodes.find(n=>n.id==='candidates'),mechanisms=model.nodes.find(n=>n.id==='mechanisms');
  const candidate=node?.recommended?.[0]??node?.options?.[0];
  const selected=candidate&&node?.recommended?.some(x=>x.option_id===candidate.option_id);
  const checks=d?.research_loop?.next_checks??[];
  const paths=uiCurrentPaths();
  const row=candidate&&candidateStructureRow(candidate.option_id),picture=row&&structureThumb(row),assessment=candidate?.assessment,parent=row?.transformed_from??row?.core_from;
  return `<section class="ui-overview" aria-label="연구 핵심 요약">
    <article class="ui-judgment"><span class="ui-eyebrow">${model.current?'현재 판단':'마지막으로 기록한 판단'}</span><h2>${d?esc(uiDecisionScope()):'연구 질문을 검토하고 있습니다.'}</h2>${d?`<p class="ui-overview-decision-text">${uiText(d.recommendation)}</p>`:''}
      <div class="ui-judgment-links">${d?'<span class="small muted">저장된 현재 검토와 다음 확인</span>':''}${d?button('ui-judgment','판단 전체·근거 보기','','link-button small'):uiEmpty('자료 조회 후 판단이 기록되면 이곳에서 확인할 수 있습니다.')}</div></article>
    <div class="ui-overview-grid"><div class="ui-overview-visual" ${candidate?`data-candidate-option="${esc(candidate.option_id)}"`:''}><div class="ui-candidate-picture">${picture||uiEmpty(candidate&&['rna','rna_candidate'].includes(optionKind(candidate))?'RNA 서열·전사체 조건':'2D 구조 확인 필요')}</div>${candidate?button('discovery-detail',`${esc(candidateDisplayName(candidate))} · 구조 상세`, `data-id="${esc(candidate.option_id)}"`,'link-button small'):''}</div>
    <article class="ui-overview-mechanisms"><h3>검토 기전·접근</h3>${paths.length?`<ul class="ui-path-list">${paths.map(p=>`<li><span class="ui-eyebrow">${esc(uiPathKind(p))}</span><strong>${esc(researcherWording(p.label))}</strong><span>${esc(optionStatus[p.assessment?.status??'unreviewed'])} · ${uiRevision(p.assessment)}</span>${p.assessment?.priority!=null?`<small>${esc(researcherWording(p.assessment.comparison_group??'기록한 비교 범위'))} · ${p.assessment.priority}</small>`:''}</li>`).join('')}</ul>`:uiEmpty('검토할 기전과 질환의 연결 근거 확인 필요')}${button('ui-stage',paths.length>1?`기전·접근 ${paths.length}개와 질환 연결 보기`:'질환과의 연결 보기','data-stage="mechanisms"','link-button small')}</article>
    <article class="ui-overview-candidate"><h3>${selected?'현재 추천에 포함된 후보':'확대해서 보는 후보'}</h3>${candidate?`<h4>${esc(candidateDisplayName(candidate))}</h4>${uiCandidateRole(candidate)}${uiGenerationLink(candidate)}${parent?`<p class="small muted">출발 화합물 ${esc(parent)}</p>`:''}<p class="small">${esc(optionStatus[assessment?.status??'unreviewed'])} · ${uiRevision(assessment)}</p>${candidate.origin==='generated_structure_proposal'?'<p class="small muted">설계 구조 · 생성 단계 활성 미측정</p>':''}`:uiEmpty('비교할 후보와 구조 확인 필요')}${button('ui-stage','후보 전체 비교','data-stage="candidates"','link-button small')}</article>
    <article class="ui-overview-next"><h3>다음 실험·확인</h3>${checks.length?`<ul class="ui-overview-checks">${checks.map(c=>`<li>${button('ui-overview-experiment',esc(uiExperimentAlias(c)),`data-id="${esc(c.id)}"`,'link-button')}<span class="small muted">${esc(uiExperimentStatus(c))}</span></li>`).join('')}</ul>`:uiEmpty('다음 실험 권고 확인 필요')}${button('ui-stage','대상·대조군·판독 검토','data-stage="next"','link-button small')}</article></div>
    ${d?`<div class="ui-overview-foot">${button('ui-stage','이전 판단과 비교','data-stage="changes"','quiet small')}<span class="small muted">추천·계산·실제 관측은 각 근거에서 확인합니다.</span></div>`:''}</section>`;
}
function uiCandidateTile(item,compact=false){
  const row=candidateStructureRow(item.option_id),picture=row&&structureThumb(row),a=item.assessment,parent=row?.transformed_from??row?.core_from;
  return `<article class="ui-candidate ${compact?'compact':''} ${readerState()?.stack[0]?.id===item.option_id?'is-selected':''}" data-candidate-option="${esc(item.option_id)}"><div class="ui-candidate-picture">${picture||uiEmpty(['rna','rna_candidate'].includes(optionKind(item))?'RNA 서열·전사체 조건':'2D 구조 확인 필요')}</div><div><h4>${esc(candidateDisplayName(item))}</h4>${uiCandidateRole(item)}${uiGenerationLink(item)}${parent?`<p class="small muted">출발 화합물 ${esc(parent)}</p>`:''}<p class="small">${esc(optionStatus[a?.status??'unreviewed'])} · ${uiRevision(a)}</p>${item.origin==='generated_structure_proposal'?'<p class="small muted">설계 구조 · 생성 단계 활성 미측정</p>':''}${a?.priority?`<p class="small muted">${esc(researcherWording(a.comparison_group))} 내 검토 순서 ${esc(a.priority)}</p>`:''}${button('discovery-detail','후보 상세',`data-id="${esc(item.option_id)}"`,'small')}</div></article>`;
}
function uiCandidates(){
  const all=candidateOptions(),mode=candidateViews.get(state.id)??'current',focus=mechanismFocus.get(state.id);
  const groups={current:all.filter(x=>x.assessment?.current_conditions===true&&x.assessment?.status!=='deferred'),earlier:all.filter(x=>x.assessment?.current_conditions!==true||x.assessment?.status==='deferred')};
  const rows=(groups[mode]??[]).filter(x=>!focus||candidateMechanismId(x)===focus);
  return `<section class="ui-candidates"><div class="ui-section-heading"><div><h2>후보·구조</h2><p>같은 이름도 출처와 기록 ID를 기준으로 구분합니다.</p></div>${button('discovery-propose','다른 후보·경로 제안','','small')}</div>
    <nav class="ui-subnav" aria-label="후보 범위">${[['current',`현재 검토 ${groups.current.length}건`],['earlier',`보류·이전·미확인 ${groups.earlier.length}건`],['all','발견 기록 전체']].map(([id,label])=>button('ui-candidate-view',label,`data-view="${id}" aria-pressed="${mode===id}"`,'small')).join('')}</nav>
    ${focus?`<p>연결 기전: ${esc(candidateMechanismLabel(focus))} ${button('roadmap-focus-clear','필터 해제','','small')}</p>`:''}
    ${mode==='all'?`<p class="small muted">전체 ${number(state.discovery?.total??0)}개 선택지 기록입니다. 기전·표적·접근도 포함하며, 화합물의 고유 개수와 구분합니다.</p>${renderOptionBrowser()}`:`<div class="ui-candidate-grid">${rows.map(x=>uiCandidateTile(x)).join('')||uiEmpty('이 범위의 후보 기록이 없습니다. 발견 기록 전체에서 미검토 후보를 확인할 수 있습니다.')}</div>`}
    ${state.artifacts.filter(a=>a.kind==='rna_candidate_space').map(a=>`<div class="ui-secondary"><strong>보존한 RNA 서열 ${number(a.meta.summary?.unique_guide_sequences)}개</strong>${sourceLinks([a.id])}</div>`).join('')}</section>`;
}
function experimentFields(check){
  const lines=String(check.operation?.request??'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean),found={},rest=[];
  for(const line of lines){const match=REQUEST_FIELDS.map(([key,re])=>[key,line.match(re)]).find(([,m])=>m);if(match){(found[match[0]]??=[]).push(match[1][1])}else rest.push(line)}
  return {found,rest};
}
function selectedExperiment(){
  const checks=state.decision?.research_loop?.next_checks??[];
  return checks.find(x=>x.id===experimentSelections.get(state.id))??checks[0]??null;
}
function uiExperimentStatus(check){
  const run=state.research_checks?.find(x=>x.decision_id===state.decision_id&&x.check_id===check.id),job=run&&state.jobs.find(x=>x.id===run.job_id);
  return job?jobLabels[job.status]??job.status:'제안됨 · 수행 결과 확인 전';
}
function uiExperiments(){
  const checks=state.decision?.research_loop?.next_checks??[],selected=selectedExperiment();
  return `<section class="ui-experiments"><div class="ui-section-heading"><div><h2>다음 실험·확인</h2><p>무엇을 비교하고, 어떤 결과에 따라 판단을 바꿀지 검토합니다.</p></div></div>
    ${!roadmapModel().current&&state.decision?uiEmpty('이전 조건의 권고입니다. 새 입력에 맞춘 검토가 필요합니다.'):''}
    ${uiExperimentReturns.has(state.id)?button('ui-candidate-return','← 후보 상세로 돌아가기','','quiet small'):''}<div class="ui-experiment-layout"><nav class="ui-experiment-list" aria-label="실험·확인 목록">${checks.map(c=>button('ui-experiment',`<span class="ui-eyebrow">${esc(CHECK_KIND[c.operation.kind])}</span><strong>${esc(uiExperimentAlias(c))}</strong><small>${esc(uiExperimentStatus(c))}</small>`,`data-id="${esc(c.id)}" aria-pressed="${selected?.id===c.id}"`,'ui-experiment-choice')).join('')||uiEmpty('실험·확인 제안이 아직 없습니다.')}</nav>${selected?uiExperimentDetail(selected):''}</div></section>`;
}
function uiExperimentDetail(check){
  const {found,rest}=experimentFields(check),op=check.operation,loop=state.decision.research_loop;
  const field=(key)=>found[key]?.map(x=>`<p>${uiText(x)}</p>`).join('')||uiEmpty('확인 필요 · 권고에 구분해 기록된 값이 없습니다.');
  const hypotheses=(check.hypothesis_ids??[]).map(id=>loop.hypotheses.find(h=>h.id===id)).filter(Boolean);
  const scopes=(check.scope_targets??[]).flatMap(t=>(loop.hypotheses.find(h=>h.id===t.hypothesis_id)?.assessment_scope?.parts??[]).filter(p=>t.part_ids.includes(p.id)).map(p=>p.statement));
  return `<article class="ui-experiment-detail" data-research-check="${esc(check.id)}"><header><span class="ui-eyebrow">판별 질문 · ${esc(CHECK_KIND[op.kind])} · 연구 기록 ${state.decision_rev}</span><h3>${esc(uiExperimentAlias(check))}</h3><p class="small muted">${esc(uiExperimentStatus(check))}</p></header>
    <details class="ui-check-question" data-detail-key="check-question:${esc(check.id)}"><summary>전체 질문·권고 목적·연결 가설</summary><h4>원 질문</h4><p>${uiText(check.question)}</p>${check.purpose?`<p>${uiText(check.purpose)}</p>`:''}${scopes.length?list(scopes.map(researcherWording)):hypotheses.length?list(hypotheses.map(h=>researcherWording(h.statement))):uiEmpty('연결된 가설 확인 필요')}</details>
    <div class="ui-experiment-fields"><section><h4>시험 대상·시료</h4>${field('측정 대상')}</section><section><h4>비교 대상·대조</h4>${field('조건·비교군')}</section></div>
    <section class="ui-experiment-readout"><h4>읽을 값·단위와 시점</h4>${field('판독 지표')}</section>
    <section class="ui-experiment-outcomes"><h4>결과별 다음 행동</h4>${uiOutcomeBranches(check)}</section>${uiExecutionConditions(check)}
    <details class="ui-check-conditions" data-detail-key="check-conditions:${esc(check.id)}"><summary>전체 조건·설계 원문</summary>${rest.length?rest.map(x=>`<p>${uiText(x)}</p>`).join(''):''}<p class="prose">${uiText(op.request??op.method??'연결된 도구로 자료를 확인하는 단계입니다.')}</p>${op.needed_inputs?list(op.needed_inputs):''}</details>
    <details class="ui-secondary" data-detail-key="check-sources:${esc(check.id)}"><summary>실험 제안에 연결된 원자료 ${op.grounded_in?.length??0}건</summary><p class="small">실험 기록 ID: <code>${esc(check.id)}</code></p>${op.grounded_in?.length?sourceLinks(op.grounded_in):uiEmpty('구체적인 근거 자료 연결 확인 필요')}</details>
    ${uiExperimentControls(check)}
    </article>`;
}
function uiOutcomeBranches(check){
  const outcomes=check.possible_outcomes??[],key=`${state.id}:${state.decision_id}:${check.id}`;
  const chosen=Math.min(outcomeSelections.get(key)??0,Math.max(0,outcomes.length-1));
  const label=(i)=>{const relations=[...new Set((check.outcome_links??[]).filter(x=>x.outcome_index===i).flatMap(x=>x.effects??[]).map(x=>x.relation))];return relations.map(x=>({supports:'가설에 부합',challenges:'재검토',unresolved:'판정 불가 · 추가 구별'})[x]).filter(Boolean).join(' · ')||`예상 결과 ${i+1}`};
  if(!outcomes.length)return uiEmpty('결과별 판단 분기 확인 필요');
  return `<nav class="ui-result-tabs" aria-label="예상 결과별 해석">${outcomes.map((o,i)=>button('ui-outcome',esc(label(i)),`data-key="${esc(key)}" data-index="${i}" aria-pressed="${chosen===i}" aria-controls="outcome-${i}"`,'small')).join('')}</nav><div class="ui-result-branches">${outcomes.map((o,i)=>`<article id="outcome-${i}" ${chosen!==i?'hidden':''}><span class="ui-eyebrow">${esc(label(i))} · 예상 결과, 실제 관측 전</span><h5>관측할 결과</h5><p>${uiText(o.observation)}</p><h5>판단·후속 확인</h5><p>${uiText(o.implication)}</p><details><summary>연결된 가설·판단 이유</summary>${renderOutcomeLinks(check,i)}</details></article>`).join('')}</div>`;
}
function uiExperimentControls(check){
  const current=roadmapModel().current,op=check.operation,running=state.jobs.some(j=>['running','queued'].includes(j.status)),ready=state.check_readiness?.[check.id];
  const run=state.research_checks?.find(x=>x.decision_id===state.decision_id&&x.check_id===check.id),job=run&&state.jobs.find(x=>x.id===run.job_id);
  return `<footer class="ui-experiment-actions"><div><strong>기존 자료 검토</strong>
    ${job?.output_id?sourceLinks([job.output_id]):op.kind==='tool'?button('run-check','자료 조회·결과 검토',`data-check="${esc(check.id)}" ${!current||busy||running||!ready?.executable?'disabled':''}`,'small'):['external_observation','researcher_input'].includes(op.kind)?button('delegate-check','기존 자료로 먼저 확인',`data-check="${esc(check.id)}" ${!current||busy?'disabled':''}`,'small'):uiEmpty('연결할 방법·자료 확인 필요')}</div><div class="ui-observation-action"><strong>${op.kind==='external_observation'?'새 관측 기록':'정보·정정 기록'}</strong>${button('check-feedback',op.kind==='external_observation'?'실험 결과 연결':'확인한 내용 연결',`data-check="${esc(check.id)}"`,'primary small')}</div></footer>`;
}

function readerSnapshot(){
  const current=currentReader();if(!current||current!==renderedResearchPanel)return;
  current.scroll=document.querySelector('#research-reader-body')?.scrollTop??0;
  current.openDetails=[...document.querySelectorAll('#research-reader-body details')].map((n,i)=>n.open?i:-1).filter(i=>i>=0);
}
function readerOpener(){
  const node=document.activeElement;
  if(!node?.dataset?.action)return null;
  const target={action:node.dataset.action,id:node.dataset.id??'',stage:node.dataset.stage??'',detailKey:node.closest('[data-detail-key]')?.dataset.detailKey??''};
  return {...target,index:readerOpenerMatches(target).indexOf(node)};
}
function readerOpenerMatches(target){
  if(!target)return [];
  return [...document.querySelectorAll('[data-action]')].filter(n=>n.dataset.action===target.action&&(n.dataset.id??'')===(target.id??'')&&(n.dataset.stage??'')===(target.stage??'')&&(target.detailKey===undefined||(n.closest('[data-detail-key]')?.dataset.detailKey??'')===target.detailKey));
}
function restoreReaderOpener(target){
  const matches=readerOpenerMatches(target),exact=matches[target?.index??0];
  // The same paper can appear in collapsed search records and several claims.
  // Restore the exact expanded claim's link, never a hidden duplicate.
  const opener=exact?.getClientRects().length?exact:matches.find(n=>n.getClientRects().length);
  (opener??document.querySelector('#roadmap-inspector'))?.focus({preventScroll:true});
}
function rememberWorkspaceView(push=false){
  history[push?'pushState':'replaceState']({evida_view:{workspace:state.id,tab,stage:roadmapChosen(),scroll:window.scrollY,opener:readerOpener()}},'',location.href);
}
async function openResearchPanel(panel){
  if(!state)return;
  if(['candidate','relation'].includes(panel.kind)&&panel.subject)researchSubjects.set(state.id,panel.subject);
  readerSnapshot();
  let reader=readerState();
  if(!reader){rememberWorkspaceView();reader={stack:[],opener:readerOpener(),pageScroll:window.scrollY};researchReaders.set(state.id,reader)}
  if(dialog.open)dialog.close();
  const item={...panel,workspace:state.id,rev:state.rev,scroll:0,openDetails:[]};
  // Switching between candidates keeps one inspector; following a citation preserves its parent.
  const replacing=panel.kind==='candidate'&&reader.stack[0]?.kind==='candidate';
  if(replacing)reader.stack=[item];else reader.stack.push(item);
  const token=crypto.randomUUID();readerHistoryFrames.set(token,{reader,stack:[...reader.stack],stage:roadmapChosen(),tab});
  history[replacing?'replaceState':'pushState']({evida_reader:{workspace:state.id,token}},'',location.href);
  render();
  requestAnimationFrame(()=>document.querySelector('#research-reader-title')?.focus({preventScroll:true}));
}
function closeResearchPanel(back=false,fromHistory=false){
  const reader=readerState();if(!reader)return;
  ++readerRequest;
  if(back&&reader.stack.length>1){reader.stack.pop();if(!fromHistory)history.back();render();requestAnimationFrame(()=>document.querySelector('#research-reader-title')?.focus({preventScroll:true}));return}
  if(!fromHistory&&history.state?.evida_reader?.workspace===state.id)history.go(-reader.stack.length);
  researchReaders.delete(state.id);render();
  requestAnimationFrame(()=>{window.scrollTo(0,reader.pageScroll);restoreReaderOpener(reader.opener)});
}
function renderResearchPanel(){
  const panel=currentReader(),reader=readerState();if(!panel)return '';
  const body=panel.kind==='generated-group'?uiGeneratedGroup(panel):panel.kind==='candidate'?uiCandidateDetail(panel):panel.kind==='source'?uiSourceDetail(panel):panel.body??'';
  return `<aside class="research-reader" id="research-reader" aria-labelledby="research-reader-title"><header class="reader-heading"><div>${reader.stack.length>1?button('ui-reader-back','← 돌아가기','','quiet small'):panel.historyContext?button('ui-history-return','← 같은 판단 이력으로','','quiet small'):''}<h2 id="research-reader-title" tabindex="-1">${esc(panel.title)}</h2></div>${button('ui-reader-close','닫기','aria-label="근거 상세 닫기"','small')}</header>
    <div class="reader-context"><span>${esc(panel.subject?.label??state.title)}</span><small>열어본 시점 · 연구 기록 ${panel.rev}${panel.rev!==state.rev?` · 현재 연구 기록 ${state.rev}, 새 판단 확인 필요`:''}</small>${panel.subject&&panel.kind!=='candidate'&&panel.kind!=='local-draft'?button('ui-subject','이 대상에 질문',`data-kind="${esc(panel.subject.kind)}" data-id="${esc(panel.subject.id)}" data-label="${esc(panel.subject.label)}"`,'link-button small'):''}</div>
    <div id="research-reader-body" class="reader-body">${body}</div></aside>`;
}
async function uiOpenCandidate(id){
  const token=++readerRequest,item=await getOption(id);if(token!==readerRequest)return;
  await loadCandidateStructures();if(token!==readerRequest)return;
  // The initial thumbnail page is bounded. Resolve an opened candidate by its exact
  // catalog ID and stored source relation, never a name guess or a changed ranking.
  let structureError=null;
  if(!candidateStructureRow(id)&&['molecule','rna_candidate'].includes(optionKind(item))){
    try{
    const key=candidateStructuresKey();
    const value=await api(`/api/workspaces/${encodeURIComponent(state.id)}/candidate-structures?option_id=${encodeURIComponent(id)}`);
    if(token!==readerRequest||candidateStructuresKey()!==key)return;
    if(candidateStructuresFor!==key){candidateStructures={rows:[]};candidateStructuresFor=key}
    candidateStructures??={rows:[]};candidateStructures.rows??=[];
    for(const row of value.rows??[])if(row.option_id===id&&!candidateStructures.rows.some(x=>x.option_id===id))candidateStructures.rows.push(row);
    }catch(error){if(token!==readerRequest)return;structureError='후보 구조를 읽지 못했습니다. 보존된 후보 정보와 원자료를 확인할 수 있습니다.'}
  }
  const mechanism=['mechanism','target','approach','researcher_proposal'].includes(optionKind(item));
  if(mechanism){await openResearchPanel({kind:'relation',id,title:item.label,subject:{kind:'mechanism',id,label:item.label},body:optionDetail(item)});return}
  await openResearchPanel({kind:'candidate',id,title:candidateDisplayName(item),item,structureError,section:'summary',subject:{kind:'candidate',id,label:candidateDisplayName(item)}});
  const panel=currentReader();if(panel?.id===id)void uiLoadParentStructures(panel);
  if(item.candidate_artifact_id)void uiLoadGeneration(item.candidate_artifact_id);
}
function uiCandidateDetail(panel){
  const item=panel.item,a=item.assessment,row=candidateStructureRow(item.option_id),section=panel.section??'summary';
  const name=candidateDisplayName(item),parent=row?.transformed_from??row?.core_from;
  const siblings=candidateOptions(),index=siblings.findIndex(x=>x.option_id===item.option_id);
  const tabs=[['summary','요약'],['evidence','근거'],['properties','구조·물성'],['experiments','관련 실험']];
  let content='';
  if(section==='summary')content=`<p>${esc(item.description??'')}</p>${a?`<h3>검토 이유</h3><p>${uiText(a.reason)}</p><h3>다음 확인</h3><p>${uiText(a.next_action)}</p>${a.priority?`<p class="small">비교 집합: ${esc(researcherWording(a.comparison_group))} · 검토 순서 ${a.priority}</p>`:''}`:uiEmpty('후보의 개별 검토 기록 확인 필요')}${parent?`<p>출발 화합물: <strong>${esc(parent)}</strong></p><p class="small muted">구조를 생성한 이력입니다. 기능 비교는 관련 실험에서 확인합니다.</p>`:''}${sourceCandidateInfo(item,true)}${rnaOptionContext(item)}`;
  if(section==='evidence')content=`<h3>평가의 지지 근거</h3>${sourceLinks(a?.support_source_ids)||uiEmpty('연결된 지지 근거 확인 필요')}<h3>반대 근거·적용 조건</h3>${sourceLinks(a?.challenge_source_ids)}${list(a?.uncertainties)}<h3>발견한 원자료</h3>${sourceLinks((item.sources??[]).map(x=>x.artifact_id))}${(row?.name_mentions??[]).filter(m=>state.artifacts.some(a=>a.id===m.artifact_id)&&/^rows\/\d+$/.test(m.locator??'')).length?`<h3>이름이 등장한 원문 구절</h3><p class="small muted">원문 이름 등장과 데이터베이스 구조 연결입니다. 효능·시료 동일성 확인은 아닙니다.</p>${(row.name_mentions??[]).filter(m=>state.artifacts.some(a=>a.id===m.artifact_id)&&/^rows\/\d+$/.test(m.locator??'')).map(m=>button('source',esc(artifactName(m.artifact_id))+' · 원문 '+esc(m.locator),`data-id="${esc(m.artifact_id)}" data-source-offset="${Number(m.locator.split('/')[1])}"`,'link-button small')).join('')}`:''}${sourceCandidateInfo(item,true)}${item.assessments?.length>1?`<details><summary>이전 검토 ${item.assessments.length-1}개</summary>${item.assessments.slice(0,-1).reverse().map(x=>`<p>${esc(optionStatus[x.status])} · ${uiRevision(x)}</p><p>${uiText(x.reason)}</p>${sourceLinks([x.artifact_id])}`).join('')}</details>`:''}`;
  if(section==='properties')content=row?`${uiCandidatePair(panel,row)}${uiCandidateProperties(row)}${item.candidate_artifact_id?sourceLinks([item.candidate_artifact_id]):''}`:uiEmpty('이 후보에 연결된 구조·물성 기록 확인 필요');
  if(section==='experiments')content=uiRelatedExperiments(item,row);
  return `${panel.structureError?`<p role="status">${esc(panel.structureError)}</p>`:''}<div class="reader-candidate-identity">${row&&structureThumb(row)?structureFigure(row.depiction,name):uiEmpty(['rna','rna_candidate'].includes(optionKind(item))?'RNA 서열과 참조 조건을 아래 근거에서 확인하세요.':'2D 구조 확인 필요')}<div><strong>${esc(name)}</strong>${uiCandidateRole(item)}${uiGenerationLink(item)}<p>${esc(optionStatus[a?.status??'unreviewed'])} · ${uiRevision(a)}</p>${item.origin==='generated_structure_proposal'?'<p>설계 구조 · 생성 단계 활성 미측정</p>':''}<details><summary>정확한 후보 식별자</summary><code>${esc(item.option_id)}</code>${item.label!==name?`<p>원 기록명: ${esc(item.label)}</p>`:''}</details></div></div>
    <nav class="ui-subnav" aria-label="후보 상세 항목">${tabs.map(([id,label])=>button('ui-candidate-tab',label,`data-section="${id}" aria-pressed="${section===id}"`,'small')).join('')}</nav>${content}
    <footer class="reader-candidate-footer">${index>0?button('discovery-detail','← 이전 후보',`data-id="${esc(siblings[index-1].option_id)}"`,'small'):''}${index>=0&&index<siblings.length-1?button('discovery-detail','다음 후보 →',`data-id="${esc(siblings[index+1].option_id)}"`,'small'):''}${button('ui-subject','이 후보에 질문·정정',`data-kind="candidate" data-id="${esc(item.option_id)}" data-label="${esc(name)}"`,'small')}</footer>`;
}
async function uiOpenSource(id,anchor={}){
  const wid=state.id,token=++readerRequest,artifact=state.artifacts.find(a=>a.id===id.split('#')[0]);
  if(!artifact)throw Error('현재 연구에서 이 자료를 찾을 수 없습니다.');
  const parent=currentReader(),subject=parent?.subject??researchSubjects.get(wid)??{kind:'research',id:wid,label:state.title};
  const start=Number.isInteger(anchor.offset)&&anchor.offset>=0?anchor.offset:0;
  const historyContext=dialog.open&&typeof evidenceHistorySelection!=='undefined'&&evidenceHistorySelection?.wid===wid&&dialog.querySelector('.history-evidence-decision')?{hypothesisId:evidenceHistorySelection.value.hypothesis_id,offset:evidenceHistorySelection.value.offset}:parent?.historyContext;
  await openResearchPanel({kind:'source',id:artifact.id,title:artifactName(artifact.id),subject,parentTitle:parent?.title??(workspaceTabs.find(([stage])=>stage===uiStage())?.[1]??'연구'),offset:start,loading:true,anchor,historyContext,quoteRef:id.includes('#')?id.split('#').slice(1).join('#'):null});
  try{const value=await api(`/api/workspaces/${wid}/artifacts/${artifact.id}?offset=${start}&limit=30`);if(state?.id!==wid||token!==readerRequest||currentReader()?.id!==artifact.id)return;Object.assign(currentReader(),{value,loading:false,title:sourceDisplayLabel(artifact,value.result,Number.isInteger(anchor.offset)?value.result?.rows?.[0]:undefined)});render()}catch(error){if(state?.id===wid&&token===readerRequest){Object.assign(currentReader(),{loading:false,error:error.message});render()}}
}
function uiRecordedDecisionView(result,artifact){
  const record=uiDecisionRecord(artifact.id),checks=result.research_loop?.next_checks??[],hypotheses=result.research_loop?.hypotheses??[];
  return `<section class="ui-recorded-decision" data-decision-id="${esc(artifact.id)}"><h3>${esc(record?.title??'게시 전 판단 제안')}</h3><p>${esc(result.recommendation??'')}</p><details><summary>당시 판단 이유·가설 ${hypotheses.length}개</summary><p>${esc(result.reason??'')}</p>${hypotheses.map(h=>`<article><h4>${esc(h.statement)}</h4><p>${esc(hypothesisLabels[h.assessment]??h.assessment)}</p><p>${esc(h.expected_observation)}</p>${sourceLinks((h.evidence??[]).filter(e=>e.source_type==='artifact').map(e=>e.source_id))}</article>`).join('')}</details><h3>당시의 다음 실험·확인</h3>${checks.map(check=>`<details class="ui-recorded-check" data-recorded-check="${esc(check.id)}"><summary>${esc(check.purpose||check.question)}</summary><p class="small">${esc(CHECK_KIND[check.operation.kind]??check.operation.kind)} · ${esc(check.id)}</p><h4>판별 질문</h4><p>${esc(check.question)}</p><h4>당시 기록한 대상·대조·판독</h4><p class="prose">${esc(check.operation.request??check.operation.method??'기록한 도구의 실행 조건은 원문에서 확인하세요.')}</p>${check.operation.needed_inputs?list(check.operation.needed_inputs):''}${sourceLinks(check.operation.grounded_in)}${(check.possible_outcomes??[]).map((outcome,i)=>`<article class="ui-recorded-outcome"><h4>당시 예상 결과 ${i+1}</h4><p>${esc(outcome.observation)}</p><p>${esc(outcome.implication)}</p></article>`).join('')}</details>`).join('')}<details class="ui-recorded-raw"><summary>원 판단 JSON·출처 그대로 보기</summary>${json(result)}<p class="small">저장 당시 자료명: ${esc(artifact.title)}</p><p class="mono">SHA256 ${esc(artifact.sha256)}</p></details>${button('download','원본·전체 결과 내려받기',`data-id="${esc(artifact.id)}"`,'small')}</section>`;
}
function uiSourceDetail(panel){
  if(panel.loading)return '<p role="status">보존한 원자료를 읽고 있습니다.</p>';
  if(panel.error)return `<p role="alert">${esc(panel.error)}</p>`;
  const artifact=state.artifacts.find(a=>a.id===panel.id),result=panel.value?.result;if(!artifact)return uiEmpty('자료 기록 확인 필요');
  // Existing readers preserve endpoint units and uncertainties. Their execution controls are
  // removed here: reading evidence cannot submit a job or change a selected research option.
  const old={selected,detail,offset};let html;
  try{selected=panel.id;detail=panel.value;offset=panel.offset;html=artifact.kind==='decision_proposal'&&result?.research_loop?uiRecordedDecisionView(result,artifact):artifactDetail()}finally{selected=old.selected;detail=old.detail;offset=old.offset}
  const template=document.createElement('template');template.innerHTML=html;normalizeSourceTitleNodes(template.content);
  const readable=new Set(['source','download','row','prev','next','article-section','article-references','transport-handle']);
  for(const node of template.content.querySelectorAll('[data-action]')){
    if(!readable.has(node.dataset.action)){node.remove();continue}
    if(node.dataset.action==='prev'||node.dataset.action==='next'){const direction=node.dataset.action==='prev'?-30:30;node.dataset.action='ui-source-page';node.dataset.offset=String(Math.max(0,panel.offset+direction))}
    if(node.dataset.action==='row')node.dataset.action='ui-source-row';
    if(node.dataset.action==='article-section'){node.dataset.action='ui-source-page'}
    if(node.dataset.action==='article-references')node.remove();
  }
  const total=result?.total_rows??result?.retained_total_rows??result?.rows?.length;
  const guidance=result?.next_steps??result?.next_actions??result?.recommendation;
  const decisionRecord=artifact.kind==='decision_proposal'?uiDecisionRecord(artifact.id):null;
  return `<div class="reader-source-role"><strong>${decisionRecord?esc(decisionRecord.title):'원자료 · '+esc(panel.parentTitle)+'에서 열었습니다'}</strong><p class="small">자료 저장: ${new Date(artifact.created).toLocaleString('ko-KR')}${decisionRecord?' · 당시 게시 기록':' · 현재 판단의 연구 기록 '+esc(state.decision_rev??'미기록')}</p>${panel.quoteRef?`<p>연결 위치: <code>${esc(panel.quoteRef)}</code></p>`:''}${sourceLocatorDetails(artifact,panel.anchor)}${panel.anchor?.quote?`<span class="ui-eyebrow">이 판단에 연결된 원문 인용</span><blockquote>${esc(panel.anchor.quote)}</blockquote>`:''}</div>${decisionRecord?'':`<section class="reader-current-recommendation"><strong>${roadmapModel().current?'현재 판단':'마지막 판단 · 새 입력 검토 필요'}</strong><p>${uiText(uiExcerpt(state.decision?.recommendation??'판단 확인 필요'))}</p>${button('ui-stage','현재 실험·확인 권고','data-stage="next"','link-button small')}</section>`}${['literature','article'].includes(artifact.kind)?sourceBibliographyView(result,Number.isInteger(panel.anchor?.offset)?result?.rows?.[0]:undefined):''}<section class="reader-original-result"><h3>자료 생성 당시의 결과·안내</h3><p class="small muted">아래 결과와 안내는 이 자료가 생성된 시점의 기록입니다.</p>${template.innerHTML}</section>
    ${guidance?`<details><summary>이 도구 결과에 기록된 후속 안내</summary>${typeof guidance==='string'?`<p>${esc(guidance)}</p>`:json(guidance)}<p class="small">이 자료 생성 시점의 안내입니다. 현재 권고는 ‘다음 실험’에서 확인합니다.</p></details>`:''}
    ${typeof total==='number'&&total>30?`<nav class="reader-pagination" aria-label="원자료 페이지">${button('ui-source-page','이전',`data-offset="${Math.max(0,panel.offset-30)}" ${panel.offset===0?'disabled':''}`,'small')}<span>${panel.offset+1}–${Math.min(panel.offset+30,total)} / ${total}행</span>${button('ui-source-page','다음',`data-offset="${panel.offset+30}" ${panel.offset+30>=total?'disabled':''}`,'small')}</nav>`:''}
    ${button('ui-full-source','자료 작업 화면에서 열기',`data-id="${esc(panel.id)}"`,'small')}`;
}
function uiCurrentSubject(){
  const explicit=researchSubjects.get(state.id);if(explicit)return explicit;
  const panel=currentReader();if(panel?.subject)return panel.subject;
  if(uiStage()==='mechanisms'){const id=mechanismFocus.get(state.id),item=pathMechanisms().find(x=>x.option_id===id);if(item)return {kind:'mechanism',id,label:item.label}}
  if(uiStage()==='next'){const c=selectedExperiment();if(c)return {kind:'check',id:c.id,label:c.question,decision_id:state.decision_id}}
  return researchSubjects.get(state.id)??{kind:'research',id:state.id,label:state.title};
}
function uiComposer(active){
  const subject=uiCurrentSubject();
  let original=renderRoadmapComposer(active).replace('이 지점에서 개입하기','질문·조건·관측 추가').replace('관측이나 아이디어로 방향을 바꿀 수 있어요.','새로 추가할 내용의 대상과 종류를 확인하세요.').replace('data-action="roadmap-send"','data-action="ui-send-preview"').replace(/(data-action="ui-send-preview"[^>]*?)disabled/g,'$1').replace('>보내기</button>','>초안 확인</button>');
  if(!status.gateway.available)original=`<section class="research-composer roadmap-composer"><label class="input-label" for="message">현재 대상에 질문하기</label><textarea id="message" placeholder="질문, 확인할 조건 또는 새로 관측한 내용을 적으세요.">${esc(draft)}</textarea><div class="roadmap-input-tools"><select id="input-kind" aria-label="추가 내용 종류">${[['message','질문·아이디어'],['observation','새 관측'],['correction','조건·해석 정정']].map(([v,label])=>`<option value="${v}" ${inputKind===v?'selected':''}>${label}</option>`).join('')}</select><div class="actions">${button('ui-send-preview','초안 확인','','primary small')}</div></div><p class="small muted">로컬 초안 · 연구에 저장하거나 실행하기 전입니다.</p></section>`;
  if(!status.gateway.available&&((state.explanations??[]).length||(state.jobs??[]).some(j=>j.kind==='explanation')))original+=`<details class="roadmap-help" data-detail-key="explain-question"><summary>저장된 연구 설명 보기</summary>${renderLiveInteraction()}</details>`;
  return `<div class="ui-composer-context"><span>입력 대상</span><strong>${esc(subject.kind==='check'&&state.decision?.research_loop?.next_checks?.find(c=>c.id===subject.id)?uiExperimentAlias(state.decision.research_loop.next_checks.find(c=>c.id===subject.id)):roadmapSummary(researcherWording(subject.label),64))}</strong><details><summary>연결 ID 확인</summary><code>${esc(subject.id)}</code></details>${subject.kind==='check'&&status.gateway.available?button('check-feedback','이 실험의 관측·정정 연결',`data-check="${esc(subject.id)}"`,'small'):subject.kind!=='research'?button('ui-subject-clear','연구 전체로 변경','','small'):''}</div>${original}`;
}
function uiPreparedInput(){
  const subject=uiCurrentSubject(),body=draft.trim();
  return subject.kind==='research'?body:`[연결 대상: ${researcherWording(subject.label)}]\n[기록 ID: ${subject.id}]\n${body}`;
}
function workspaceAfterRender(){
  document.body.classList.toggle('ui-rail-collapsed',researchRailCollapsed);
  document.body.classList.toggle('ui-reading',!!currentReader());
  document.body.classList.toggle('ui-workspace-wide',workspaceWide);
  document.body.classList.toggle('ui-conversation-open',conversationOpen);
  const panel=currentReader(),body=document.querySelector('#research-reader-body');
  renderedResearchPanel=panel;
  if(panel&&body){body.scrollTop=panel.scroll??0;for(const [i,node] of [...body.querySelectorAll('details')].entries())if(panel.openDetails?.includes(i))node.open=true}
  const mobile=matchMedia('(max-width: 1100px)').matches&&!!panel;
  for(const node of document.querySelectorAll('#workspace-content,.rail,.ui-stage-nav,.ui-workspace-heading,.ui-conversation'))node.inert=mobile;
  const conversationModal=matchMedia('(max-width:850px)').matches&&conversationOpen&&!panel;
  for(const node of document.querySelectorAll('.topbar,.ui-work-product'))node.inert=conversationModal;
  if(conversationModal)for(const node of document.querySelectorAll('.rail,.ui-workspace-heading'))node.inert=true;
  const conversation=document.querySelector('.ui-conversation');if(conversation){conversation.setAttribute('role',conversationModal?'dialog':'complementary');if(conversationModal)conversation.setAttribute('aria-modal','true')}
  const reader=document.querySelector('#research-reader');if(reader){reader.setAttribute('role',mobile?'dialog':'region');if(mobile)reader.setAttribute('aria-modal','true')}
  fitResearchReader();
}
function fitResearchReader(){const node=document.querySelector('#research-reader');if(!node)return;if(matchMedia('(max-width:1100px)').matches){node.style.height='';return}const top=Math.max(16,node.getBoundingClientRect().top);node.style.height=`${Math.max(200,innerHeight-top-16)}px`}
window.addEventListener('scroll',fitResearchReader,{passive:true});
async function workspaceAction(action,node){
  if(action.startsWith('path-')){await pathAction(action,node);return true}
  if(action==='discovery-detail'){await uiOpenCandidate(node.dataset.id);return true}
  if(action==='source'&&state){await uiOpenSource(node.dataset.id,{offset:node.dataset.sourceOffset===undefined?undefined:Number(node.dataset.sourceOffset),quote:node.dataset.sourceQuote});return true}
  if(action==='show-check'){researchSubjects.delete(state.id);experimentSelections.set(state.id,node.dataset.check);closeResearchPanel();tab='research';roadmapSelections.set(state.id,'next');render();return true}
  if(!action.startsWith('ui-'))return false;
  if(action==='ui-pin-research'){if(toggleResearchPin(node.dataset.id)){const id=node.dataset.id;render();[...document.querySelectorAll('[data-action="ui-pin-research"]')].find(n=>n.dataset.id===id)?.focus()}return true}
  if(action==='ui-history-return'){const previous=currentReader()?.historyContext;if(previous){closeResearchPanel();await openEvidenceHistory(previous.hypothesisId,previous.offset)}return true}
  if(action==='ui-stage'){
    const stage=node.dataset.stage;uiExperimentReturns.delete(state.id);researchSubjects.delete(state.id);researchReaders.delete(state.id);++readerRequest;
    tab=['data','history'].includes(stage)?stage:'research';roadmapSelections.set(state.id,tab==='research'?(stage||null):null);render();window.scrollTo(0,0);rememberWorkspaceView();document.querySelector('#roadmap-inspector')?.focus({preventScroll:true});return true;
  }
  if(action==='ui-wide'){workspaceWide=!workspaceWide;conversationOpen=false;render();return true}
  if(action==='ui-question'){conversationOpen=true;workspaceWide=false;render();document.querySelector('#message')?.focus();return true}
  if(action==='ui-question-close'){conversationOpen=false;render();document.querySelector('[data-action="ui-question"]')?.focus();return true}
  if(action==='ui-outcome'){outcomeSelections.set(node.dataset.key,Number(node.dataset.index));render();document.querySelector(`[data-action="ui-outcome"][data-index="${node.dataset.index}"]`)?.focus({preventScroll:true});return true}
  if(action==='ui-rail'){researchRailCollapsed=!researchRailCollapsed;render();return true}
  if(action==='ui-research-mode'){researchListMode=node.dataset.mode;render();return true}
  if(action==='ui-reader-close'||action==='ui-reader-back'){closeResearchPanel(action==='ui-reader-back');return true}
  if(action==='ui-judgment'){await openResearchPanel({kind:'judgment',title:'판단 전체와 근거',subject:{kind:'research',id:state.id,label:state.title},body:`<h3>판단 원문</h3><p>${uiText(state.decision.recommendation)}</p><h3>판단 이유</h3><p>${uiText(state.decision.reason)}</p>${sourceLinks(state.decision.evidence_refs)}${questions(state.decision.questions)}`});return true}
  if(action==='ui-candidate-view'){candidateViews.set(state.id,node.dataset.view);if(node.dataset.view==='all'){optionsOpen=true;optionsStage='candidates';optionsOffset=0;optionsKind='';optionsPage=null;render();await loadOptions()}else render();return true}
  if(action==='ui-candidate-tab'){readerSnapshot();Object.assign(currentReader(),{section:node.dataset.section,scroll:0,openDetails:[]});render();return true}
  if(action==='ui-generated-group'){await uiLoadGeneration(node.dataset.id);await openResearchPanel({kind:'generated-group',id:node.dataset.id,title:'같은 생성 집합',subject:uiCurrentSubject()});return true}
  if(action==='ui-candidate-return'){const saved=uiExperimentReturns.get(state.id);if(saved?.rev===state.rev){researchReaders.set(state.id,saved.reader);tab=saved.tab;roadmapSelections.set(state.id,saved.stage);render()}uiExperimentReturns.delete(state.id);return true}
  if(['ui-experiment','ui-related-experiment','ui-overview-experiment'].includes(action)){researchSubjects.delete(state.id);experimentSelections.set(state.id,node.dataset.id);if(action!=='ui-experiment'){if(action==='ui-related-experiment'){readerSnapshot();uiExperimentReturns.set(state.id,{reader:readerState(),rev:state.rev,tab,stage:roadmapChosen()})}researchReaders.delete(state.id);tab='research';roadmapSelections.set(state.id,'next')}render();return true}
  if(action==='ui-subject'){conversationOpen=true;workspaceWide=false;researchSubjects.set(state.id,{kind:node.dataset.kind,id:node.dataset.id,label:node.dataset.label});closeResearchPanel();render();document.querySelector('#message')?.focus();return true}
  if(action==='ui-subject-clear'){researchSubjects.set(state.id,{kind:'research',id:state.id,label:state.title});render();return true}
  if(action==='ui-source-page'){
    const p=currentReader(),next=Number(node.dataset.offset),wid=state.id,token=++readerRequest;
    if(!p||p.kind!=='source'||!Number.isInteger(next)||next<0)return true;
    const value=await api(`/api/workspaces/${wid}/artifacts/${p.id}?offset=${next}&limit=30`);
    if(state?.id===wid&&token===readerRequest&&currentReader()===p){Object.assign(p,{value,offset:next,scroll:0,openDetails:[]});render()}return true;
  }
  if(action==='ui-source-row'){const p=currentReader(),r=p?.value?.result,row=r?.rows?.[Number(node.dataset.index)];if(row!==undefined)await openResearchPanel({kind:'row',id:p.id,title:'원행의 전체 값',subject:p.subject,body:json(r.header?{header:r.header,row}:row)});return true}
  if(action==='ui-full-source'){researchReaders.delete(state.id);await chooseArtifact(node.dataset.id);return true}
  if(action==='ui-send-preview'){
    if(!draft.trim()){notice('추가할 내용을 입력해 주세요.');return true}
    const subject=uiCurrentSubject();
    if(!status.gateway.available){await openResearchPanel({kind:'local-draft',id:subject.id,title:'질문 초안',subject,body:`<h3>로컬 초안 · 저장·실행 전</h3><p>종류: ${esc(({message:'질문·아이디어',observation:'새 관측',correction:'조건·해석 정정'})[inputKind])}</p><p class="prose">${esc(uiPreparedInput())}</p><p class="small muted">이 미리보기에서는 연구 기록을 바꾸거나 모델을 실행하지 않습니다. 닫으면 입력으로 돌아갑니다.</p>`});return true}
    if(subject.kind==='check'&&['observation','correction'].includes(inputKind)){openResearchFeedback(subject.id,null);document.querySelector('#feedback-text').value=draft;document.querySelector('#feedback-kind').value=inputKind;return true}
    const prepared=uiPreparedInput();await openResearchPanel({kind:'input-preview',id:subject.id,title:'보내기 전에 확인',subject,prepared,originalDraft:draft,inputKind,sendMode,body:`<h3>저장할 내용</h3><p class="prose">${esc(prepared)}</p><p>종류: ${esc(({message:'질문·아이디어',observation:'새 관측',correction:'조건·해석 정정'})[inputKind])}</p><p>${sendMode==='record'?'기록만 저장합니다.':'자료와 연결된 도구를 사용해 검토합니다.'}</p>${button('ui-send-confirm','확인하고 보내기','','primary small')}`});return true;
  }
  if(action==='ui-send-confirm'){
    const panel=currentReader();if(!panel||panel.kind!=='input-preview'||panel.rev!==state.rev||panel.originalDraft!==draft||panel.inputKind!==inputKind||panel.sendMode!==sendMode)throw Error('입력 또는 연구 조건이 바뀌었습니다. 보낼 내용을 다시 확인해 주세요.');
    draft=panel.prepared;evidaStorage.setItem(draftKey(),draft);researchReaders.delete(state.id);await roadmapAction('roadmap-send',node);return true;
  }
  return true;
}
document.addEventListener('input',event=>{if(event.target.id==='research-search'){researchSearch=event.target.value;render()}});
document.addEventListener('keydown',event=>{
  if(!currentReader()&&conversationOpen&&matchMedia('(max-width:850px)').matches&&!dialog.open){
    if(event.key==='Escape'){event.preventDefault();conversationOpen=false;render();document.querySelector('[data-action="ui-question"]')?.focus();return}
    if(event.key==='Tab'){const nodes=[...document.querySelectorAll('.ui-conversation button:not([disabled]),.ui-conversation a[href],.ui-conversation textarea,.ui-conversation select,.ui-conversation summary')].filter(n=>n.getClientRects().length),first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}}
    return;
  }
  if(!currentReader()||dialog.open)return;
  if(event.key==='Escape'){event.preventDefault();closeResearchPanel(currentReader()?.kind==='source'&&readerState().stack.length>1);return}
  if(event.key==='Tab'&&matchMedia('(max-width: 1100px)').matches){const nodes=[...document.querySelectorAll('#research-reader button:not([disabled]),#research-reader a[href],#research-reader input,#research-reader select,#research-reader textarea,#research-reader summary')].filter(n=>n.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&(document.activeElement===first||document.activeElement.id==='research-reader-title')){event.preventDefault();last?.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}}
});
window.addEventListener('resize',()=>{if(typeof state!=='undefined'&&state)workspaceAfterRender()});
window.addEventListener('popstate',event=>{
  if(typeof state==='undefined'||!state)return;
  readerSnapshot();
  const key=event.state?.evida_reader,frame=key?.workspace===state.id&&readerHistoryFrames.get(key.token);
  const view=event.state?.evida_view;
  ++readerRequest;
  if(frame){frame.reader.stack=[...frame.stack];researchReaders.set(state.id,frame.reader);tab=frame.tab;roadmapSelections.set(state.id,frame.stage);render();requestAnimationFrame(()=>document.querySelector('#research-reader-title')?.focus({preventScroll:true}))}
  else if(view?.workspace===state.id){
    const reader=readerState();researchReaders.delete(state.id);tab=view.tab;roadmapSelections.set(state.id,view.stage);render();
    requestAnimationFrame(()=>{window.scrollTo(0,reader?.pageScroll??view.scroll??0);restoreReaderOpener(reader?.opener??view.opener)});
  }else if(readerState())closeResearchPanel(false,true);
});


;
/* Source: evidence-workbench.js */
/* Typed evidence projection. Recorded interpretations and optional local
   semantic reading order stay separate; neither changes the scientific state. */
const EVIDENCE_WORKBENCH_RELATION={supports:'지지',challenges:'반대·제약',context:'적용 맥락',uncertain:'판정 보류'};
const EVIDENCE_WORKBENCH_ASSESSMENT={consistent_in_context:'해당 조건에서 부합',challenged:'반대 근거 있음',inconclusive:'판정 미정',unassessed:'미평가'};
const semanticLiteratureViews=new Map();
function semanticView(wid){if(!semanticLiteratureViews.has(wid))semanticLiteratureViews.set(wid,{});return semanticLiteratureViews.get(wid)}
function semanticStop(wid,message){const view=semanticLiteratureViews.get(wid);if(!view)return;view.controller?.abort();clearTimeout(view.timer);view.version=(view.version??0)+1;view.loading=false;view.checking=false;view.preparing=false;view.timer=null;if(message)view.message=message;}
async function semanticRequest(wid,path,body){const view=semanticView(wid);view.controller?.abort();const controller=new AbortController();view.controller=controller;const response=await fetch(deploymentURL(`/api/workspaces/${encodeURIComponent(wid)}/semantic-literature${path}`),{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Evida-Request':'1'}:{},body:body?JSON.stringify(body):undefined,signal:controller.signal});const data=await response.json();if(!response.ok)throw Error(data.error||'문헌 준비 상태를 확인하지 못했습니다.');return data;}
function semanticPanelOpen(){return !!document.querySelector('[data-detail-key="semantic-literature"]')?.open}
function semanticAfterRender(){for(const wid of semanticLiteratureViews.keys())if(wid!==state?.id)semanticStop(wid,'다른 연구로 이동했습니다. 시작한 문헌 준비는 원래 연구에서 계속됩니다.');const wid=state?.id;if(!wid||!semanticPanelOpen())return;const view=semanticView(wid);if(view.paused)return;if(!view.status&&!view.checking&&!view.error)void semanticStatus(wid);else if(view.status?.running&&!view.timer&&!view.checking)semanticPoll(wid);}
function semanticPoll(wid){const view=semanticView(wid);clearTimeout(view.timer);view.timer=setTimeout(()=>{view.timer=null;if(state?.id===wid&&semanticPanelOpen())void semanticStatus(wid)},1500)}
async function semanticStatus(wid){const view=semanticView(wid);if(view.checking||view.loading||view.preparing)return;view.checking=true;const version=view.version??0;
 try{const status=await semanticRequest(wid,'/status');if(state?.id!==wid||version!==(view.version??0))return;view.status=status;if(!status.available)view.result=null;view.error=null;if(!status.running)view.message=null;}
 catch(error){if(error.name!=='AbortError'&&state?.id===wid&&version===(view.version??0))view.error=error.message;}
 finally{if(version===(view.version??0)){view.checking=false;if(state?.id===wid)render();}}
}
function semanticSourceButtons(row){const refs=row.all_source_locators?.length?row.all_source_locators:[row.source];return refs.filter(Boolean).map((source,i)=>{const offset=source.row_offset??source.row_index;return Number.isInteger(offset)&&offset>=0?button('source',refs.length>1?`원행 보기 ${i+1}`:'원행 보기',`data-id="${esc(source.artifact_id)}" data-source-offset="${offset}"`,'link-button small'):'<span class="small muted">원행 위치 확인 필요</span>'}).join(' ')}
function renderSemanticLiterature(snapshot){
 if(!snapshot?.semantic_literature)return '';const view=semanticView(snapshot.id),scope=view.status??snapshot.semantic_literature,result=scope.available===false?null:view.result;
 const indexed=Number(scope.indexed_documents??0),pending=Number(scope.pending_documents??0),retained=Number(scope.retained_documents??indexed),running=!!scope.running,ready=scope.available??(indexed>0&&!scope.stale_source_records);
 const states={unindexed:'문헌 내용 찾기 준비 전',ready:'문헌 내용 찾기 준비 완료',pending:'추가 문헌 준비 필요',building:'문헌 내용 찾기 준비 중',failed:'문헌 준비를 완료하지 못했습니다',empty:'검색할 제목·초록이 아직 없습니다'};
 const rows=(result?.rows??[]).map(row=>`<li><strong>${row.rank}. ${esc(row.title)}</strong><small>${esc(row.document_id)}</small>${semanticSourceButtons(row)}<details><summary>보존된 초록</summary><p>${esc(row.abstract||'이 반환 행에는 초록이 없습니다.')}</p></details></li>`).join('');
 return `<details class="ew-search" data-detail-key="semantic-literature"><summary>영문으로 문헌 내용 찾기 · 선택</summary>
 <p role="status">${view.checking&&!view.status?'보존 문헌의 검색 범위를 확인 중입니다.':states[scope.state]??(indexed?'문헌 내용 찾기 준비 완료':'보존 문헌의 준비 상태를 확인합니다.')}</p>
 <p>준비된 제목·초록 ${indexed}개 / 보존 문헌 ${retained}개${pending?` · 추가 준비 ${pending}개`:''}. 검색어와 가까운 순서로 읽습니다. 근거 강도나 치료 추천 순위와는 별개입니다.</p>
 ${scope.retained_search_records!==undefined?`<p class="small muted">보존 검색 기록 ${scope.retained_search_records}개 중 준비된 기록 ${scope.indexed_search_records??0}개.</p>`:''}
 ${scope.stale_source_records?'<p class="small muted">일부 출처가 현재 원자료와 달라 다시 준비해야 합니다. 해당 자료는 기존 원자료 보기에서 확인할 수 있습니다.</p>':''}
 ${running?'<p class="small muted">문헌을 준비하고 있습니다. 다른 연구로 이동해도 시작한 준비는 이 연구에서 계속됩니다.</p>':''}
 <div class="detail-actions">${scope.can_build&&!running?button('semantic-literature-prepare',view.preparing?'문헌 준비 요청 중…':indexed?'추가 보존 문헌으로 내용 찾기 준비':'보존 문헌으로 내용 찾기 준비',view.preparing?'disabled':'','small'):''}${button('semantic-literature-status','준비 상태 확인',view.checking||view.preparing?'disabled':'','quiet small')}</div>
 ${ready?`<label for="semantic-literature-query">영문 검색어</label><input type="search" id="semantic-literature-query" maxlength="1024" value="${esc(view.query??'')}" placeholder="예: microglia inflammasome cytokine" autocomplete="off"><div class="detail-actions">${button('semantic-literature-search',view.loading?'문헌 검색 중…':'내용으로 찾기',view.loading?'disabled':'','small')}${result?button('semantic-literature-clear','검색 결과 접기','','quiet small'):''}</div>`:''}
 ${view.loading||running||view.preparing?button('semantic-literature-cancel',view.loading?'현재 검색 취소':'준비 상태 기다림 닫기','','quiet small'):''}
 ${view.message?`<p role="status">${esc(view.message)}</p>`:''}${view.error?`<p role="alert">${esc(view.error)} 원자료와 기존 판단은 계속 확인할 수 있습니다.</p>`:''}
 ${result?`<p role="status">${esc(result.query)} · ${result.rows.length?result.offset+1:0}–${result.offset+result.rows.length} / 검색한 제목·초록 ${result.total_indexed}개</p><ul class="list">${rows}</ul><div class="detail-actions">${result.offset?button('semantic-literature-page','이전 문헌',`data-offset="${Math.max(0,result.offset-result.limit)}" ${view.loading?'disabled':''}`,'small'):''}${result.has_more?button('semantic-literature-page','다음 문헌',`data-offset="${result.offset+result.limit}" ${view.loading?'disabled':''}`,'small'):''}</div>`:''}</details>`;
}
async function semanticLiteratureAction(action,node){
 if(!action.startsWith('semantic-literature-'))return false;if(!state?.semantic_literature)return true;const wid=state.id,view=semanticView(wid);
 if(action==='semantic-literature-cancel'){const panel=node.closest?.('[data-detail-key="semantic-literature"]');if(panel)panel.open=false;semanticStop(wid,'화면의 기다림을 닫았습니다. 이미 시작한 문헌 준비는 이 연구에서 계속됩니다.');view.paused=true;render();return true;}
 if(action==='semantic-literature-clear'){semanticStop(wid);view.result=null;render();return true;}
 if(action==='semantic-literature-status'){view.paused=false;await semanticStatus(wid);return true;}
 if(view.loading||view.preparing)return true;semanticStop(wid);view.paused=false;view.error=null;view.message=null;const version=view.version;
 if(action==='semantic-literature-prepare'){view.preparing=true;render();try{const status=await semanticRequest(wid,'/index',{});if(state?.id===wid&&view.version===version)view.status=status;}catch(error){if(error.name!=='AbortError'&&state?.id===wid&&view.version===version)view.error=error.message;}finally{if(view.version===version){view.preparing=false;if(state?.id===wid)render();}}return true;}
 const query=action==='semantic-literature-page'?view.result?.query:document.querySelector('#semantic-literature-query')?.value??'';const offset=action==='semantic-literature-page'?Number(node.dataset.offset):0;
 view.query=query;view.loading=true;render();try{const result=await semanticRequest(wid,'?'+new URLSearchParams({query,offset,limit:10}));if(state?.id===wid&&view.version===version)view.result=result;}catch(error){if(error.name!=='AbortError'&&state?.id===wid&&view.version===version)view.error=error.message;}finally{if(view.version===version){view.loading=false;if(state?.id===wid)render();}}return true;
}

function evidenceWorkbenchText(value,fallback='확인 필요'){
  return typeof value==='string'&&value.trim()?value.trim():fallback;
}
function evidenceWorkbenchClaims(decision){
  if(typeof roadmapClaimRecords==='function')return roadmapClaimRecords(decision);
  const rows=[];
  for(const hypothesis of decision?.research_loop?.hypotheses??[]){
    rows.push({...hypothesis,claim_id:hypothesis.id,level:'hypothesis'});
    for(const part of hypothesis.assessment_scope?.parts??[])rows.push({...part,claim_id:part.id,level:'part',hypothesis_id:hypothesis.id});
    for(const alternative of hypothesis.conditional_alternatives??[])rows.push({...alternative,claim_id:alternative.id,level:'alternative',hypothesis_id:hypothesis.id});
  }
  return rows;
}
function evidenceWorkbenchScope(snapshot){
  const artifacts=Array.isArray(snapshot?.artifacts)?snapshot.artifacts:[];
  const searches=artifacts.filter(a=>a&&['literature','clinical_trial_search','drug_label_search','entity_search'].includes(a.kind)
    && Number.isInteger(a.meta?.summary?.returned) && a.meta.summary.returned>=0);
  const fullText=artifacts.filter(a=>a?.kind==='article'
    && a.meta?.semantic_type==='published_full_text'
    && a.meta?.summary?.content_scope==='body_available'
    && ['succeeded','reused'].includes(a.meta?.result_status));
  const claims=evidenceWorkbenchClaims(snapshot?.decision);
  const evidence=claims.flatMap(c=>Array.isArray(c.evidence)?c.evidence:[]);
  const artifactIds=new Set(artifacts.map(a=>a.id));
  const linked=[...new Set(evidence.filter(e=>e?.source_type==='artifact'&&artifactIds.has(e.source_id)).map(e=>e.source_id))];
  return {searches,fullText,claims,evidence,linked};
}
function evidenceWorkbenchSource(row,snapshot){
  const id=typeof row?.source_id==='string'?row.source_id:'';
  if(!id)return '<span class="ew-gap">출처 ID 확인 필요</span>';
  if(row.source_type==='artifact'){
    if(!(snapshot.artifacts??[]).some(a=>a.id===id))return `<span class="ew-gap">현재 연구에 연결된 원자료 확인 필요 · <code>${esc(id)}</code></span>`;
    return sourceLinks([id]);
  }
  if(row.source_type==='message'){
    const exists=(snapshot.events??[]).some(e=>e?.body?.message_id===id);
    return exists?button('message-source','연구자 입력 원문',`data-id="${esc(id)}"`,'link-button small'):
      `<span class="ew-gap">입력 원문 연결 확인 필요 · <code>${esc(id)}</code></span>`;
  }
  return `<span class="ew-gap">출처 유형 확인 필요 · <code>${esc(id)}</code></span>`;
}
function evidenceWorkbenchQuote(row){
  const anchor=row?.anchor;
  const valid=anchor&&anchor.artifact_id===row.source_id&&typeof anchor.quote==='string'&&anchor.quote.trim();
  const location=valid&&Number.isInteger(anchor.offset)&&anchor.offset>=0?` · 원행 ${anchor.offset}`:'';
  return valid?`<blockquote>${esc(anchor.quote)}</blockquote><p class="ew-locator">원문 인용${location}</p>`:
    '<p class="ew-gap">확인 필요 · 원문 인용과 행 위치는 출처 상세에서 대조하세요.</p>';
}
function evidenceWorkbenchRow(row,snapshot){
  const relation=EVIDENCE_WORKBENCH_RELATION[row?.relation]??'관계 확인 필요';
  return `<article class="ew-row" data-source-id="${esc(row?.source_id??'')}">
    <header><strong>${esc(relation)}</strong><div class="ew-source">근거 출처: ${evidenceWorkbenchSource(row,snapshot)}</div></header>
    <dl><div><dt>대상·적용 조건</dt><dd>${esc(evidenceWorkbenchText(row?.applicability))}</dd></div>
      <div><dt>판단 기록의 해석</dt><dd>${esc(evidenceWorkbenchText(row?.detail))}</dd></div></dl>
    ${evidenceWorkbenchQuote(row)}</article>`;
}
function evidenceWorkbenchSearchItem(artifact){
  const summary=artifact.meta.summary;
  const query=artifact.meta?.arguments?.query??artifact.meta?.arguments?.condition??artifact.meta?.arguments?.entity??'';
  const more=summary.has_more===true||!!summary.next_cursor||!!summary.next_page_token;
  return `<li><strong>${esc(artifactName(artifact.id))}</strong><span>이 요청의 반환 ${summary.returned}행${more?' · 다음 페이지 있음':''}</span>
    ${query?`<small>검색 조건: ${esc(String(query))}</small>`:''}${sourceLinks([artifact.id])}</li>`;
}
function renderEvidenceWorkbench(snapshot=state){
  const scope=evidenceWorkbenchScope(snapshot),current=!!snapshot?.decision&&snapshot.decision_rev===snapshot.rev;
  const body=scope.claims.map(claim=>{
    const rows=Array.isArray(claim.evidence)?claim.evidence:[];
    const label={hypothesis:'가설',part:'부분 주장',alternative:'조건부 설명'}[claim.level]??'주장';
    return `<details class="ew-claim" data-detail-key="ew:${esc(claim.hypothesis_id??claim.id)}:${esc(claim.level)}:${esc(claim.claim_id)}" data-claim-id="${esc(claim.claim_id??'')}"><summary><span class="ew-kind">${label}</span>
      <strong>${esc(researcherWording(evidenceWorkbenchText(claim.statement,'주장 문장 확인 필요')))}</strong><span class="ew-state">${esc(EVIDENCE_WORKBENCH_ASSESSMENT[claim.assessment]??'판단 상태 확인 필요')}</span></summary>
      <div class="ew-claim-body"><p class="ew-id">기록 ID <code>${esc(claim.claim_id??'확인 필요')}</code>${claim.hypothesis_id&&claim.level!=='hypothesis'?` · 연결 가설 <code>${esc(claim.hypothesis_id)}</code>`:''}</p>
      <dl class="ew-claim-context"><div><dt>확인할 관측</dt><dd>${esc(researcherWording(evidenceWorkbenchText(claim.expected_observation)))}</dd></div>
      <div><dt>판단과 남은 조건</dt><dd>${esc(researcherWording(evidenceWorkbenchText(claim.rationale)))}</dd></div></dl>
      ${Array.isArray(claim.alternatives)&&claim.alternatives.length?`<section class="ew-uncertainty"><h4>경쟁 설명·남은 불확실성</h4><ul>${claim.alternatives.map(x=>`<li>${esc(evidenceWorkbenchText(x))}</li>`).join('')}</ul></section>`:''}
      <h4>이 주장에 직접 연결한 판독 ${rows.length}행</h4>${rows.length?rows.map(r=>evidenceWorkbenchRow(r,snapshot)).join(''):
        '<p class="ew-gap">확인 필요 · 이 주장에 직접 연결한 판독 기록</p>'}</div></details>`;
  }).join('');
  const searches=scope.searches.map(evidenceWorkbenchSearchItem).join('');
  return `<section class="evidence-workbench" aria-label="질문별 근거 검토와 판독 범위">
    <header class="ew-heading"><h3>주장과 원자료를 함께 검토</h3><p>${current?'현재 입력의 게시 판단':'이전 입력의 판단 또는 새 판단 전 기록'} · 검색 반환, 원문 회수, 판단 연결은 서로 다른 단계입니다.</p></header>
    <div class="ew-scope" aria-label="기록된 자료 범위"><div><span>검색 반환</span><strong>${scope.searches.length?scope.searches.length+'개 검색 기록':'기록 확인 필요'}</strong><small>반환 행 수는 각 검색 원자료에서 확인</small></div>
      <div><span>원문 본문 회수</span><strong>${scope.fullText.length?scope.fullText.length+'개 자료':'본문 반환 기록 확인 필요'}</strong><small>본문 파일을 회수한 기록</small></div>
      <div><span>판단에 연결한 근거</span><strong>${scope.evidence.length?scope.evidence.length+'개 판단 행':'판단 연결 확인 필요'}</strong><small>출처 ID 기준 원자료 ${scope.linked.length}개</small></div></div>
    <details class="ew-search" data-detail-key="ew-search"><summary>검색별 반환과 남은 페이지 ${scope.searches.length}건</summary>
      <p>각 검색의 반환 행과 남은 페이지를 검토합니다. 원문 회수와 판단 연결 현황은 위에 구분했습니다.</p>
      ${scope.searches.length?`<ul>${searches}</ul>`:'<p class="ew-gap">검색 반환 수를 기록한 원자료를 확인해야 합니다.</p>'}</details>
    ${renderSemanticLiterature(snapshot)}
    <div class="ew-claims"><h4>질문·주장별 근거</h4><p>기록된 적용 조건과 판단 해석을 그대로 놓았습니다. 원문 인용·원행은 출처 상세에서 대조하세요.</p>
      ${body||'<p class="ew-gap">확인 필요 · 구조화된 가설과 부분 주장</p>'}</div>
    <p class="ew-foot">효능 판단에 필요한 조건과 실제 관측은 연결된 원자료에서 확인합니다.</p>
  </section>`;
}


;
/* Source: app.js */
const app = document.querySelector('#app');
const dialog = document.querySelector('#editor');
let status, projects = [], state = null, tab = 'research', selected = null, detail = null;
let offset = 0, query = '', busy = false, noticeTimer, draft = '', inputKind = 'message', syntheticDraft = false;
let intentEditBase = null;
let projectLoadVersion = 0;
const labels = {tool_reading:'확인한 원문·결과',public_method_background:'공개 방법 배경',source_visual_review:'원문 시각 검토',rna_seed_analysis:'RNA seed 분포 분석',rna_seed_reference:'RNA 참조 전사체',rna_guide:'출처가 확인된 RNA 서열',repository_document:'공개 자료 설명',protocol_snapshot:'판단 생성 방식',article:'공개 원문',entity_search:'표적·질환 후보',rna_gene_review:'RNA 유전자 관측 대조',evidence_view:'확인한 자료 범위',research_check:'후속 연구 확인',molecule_csv:'후보 원자료',rna_table:'RNA 원자료',rdkit:'계산 물성',admet:'모델 예측',rna_observations:'관측 검토',open_targets:'공개 표적 속성',literature:'문헌 검색',model_receipt:'모델 실행 기록',decision_proposal:'판단 제안'};
labels.rna_method_review = 'RNA 실제 방법 비교';
Object.assign(labels,{explanation:'저장된 판단 설명',explanation_context:'설명 기준',explanation_answer:'질문에 대한 설명',explanation_model_output:'설명 응답 기록',explanation_reading:'설명에 사용한 원문'});
Object.assign(labels,SCIENCE_LABELS);
labels.rna_seed_sensitivity = 'RNA 참조·발현 민감도';
const jobLabels = {queued:'대기',running:'실행 중',succeeded:'완료',reused:'기존 계산 재사용',failed:'실패',partial:'일부 반환',interrupted:'중단 기록',stale:'이전 조건의 작업',paused:'추가 실행 가능',refused:'서비스 응답 거절',input_missing:'입력 필요',outcome_unknown:'완료 여부 미확인',quota_or_rate_limit:'서비스 한도',identity_unverified:'모델 확인 필요'};
const eventLabels = {reading_focus_set:'현재 질문의 자료 선택',research_check_requested:'다음 확인 실행',research_check_review_pending:'확인 결과의 해석 대기',created:'연구 시작',message:'연구 요청',correction:'조건 정정',observation:'새 관측',intent_edit:'연구자의 의도 수정',artifact_added:'자료 저장',job_queued:'작업 요청',job_started:'작업 실행',job_finished:'실행 결과',work_framed:'의도와 작업 분해',decision_published:'판단 갱신',decision_stale:'이전 조건의 판단 보존',job_interrupted:'중단된 작업 보존',source_import_failed:'공개 자료 수신 오류'};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => value === null || value === undefined ? '—' : typeof value === 'number' ? (value!==0&&(Math.abs(value)<0.0001||Math.abs(value)>=1e8) ? value.toExponential(4) : Number.isInteger(value) ? value.toLocaleString('ko-KR') : value.toLocaleString('ko-KR',{maximumSignificantDigits:5})) : esc(value);
const button = (action, text, extra = '', klass = '') => `<button type="button" class="${klass}" data-action="${action}" ${extra}>${text}</button>`;
const list = values => values?.length ? `<ul class="list">${values.map(v=>`<li>${esc(v)}</li>`).join('')}</ul>` : '';
const json = value => `<pre class="raw">${esc(JSON.stringify(value,null,2))}</pre>`;
const time = value => new Date(value).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'});
Object.assign(labels,{chemical_sirna_evidence:'수식 siRNA 원자료',research_evidence:'시험·원전 조건 검토'});
const artifactName = id => {const a=state?.artifacts.find(a=>a.id===id.split('#')[0]);if(!a)return id;if(a.kind==='decision_proposal'&&typeof uiDecisionRecord==='function')return uiDecisionRecord(a.id)?.title??'게시 전 판단 제안';if(a.kind==='article'&&typeof a.source_title==='string'&&a.source_title.trim())return a.source_title;if(a.kind==='clinical_trial'&&a.meta.summary?.title)return a.meta.summary.title;if(a.kind==='gtopdb_pharmacology'&&a.meta.summary?.gene_symbol)return a.meta.summary.gene_symbol+' · '+a.title;if(a.kind==='target_context'&&a.meta.summary?.symbol)return `${a.meta.summary.symbol} · ${a.title}`;if(['rna_reference','rna_reference_archive'].includes(a.kind)&&a.meta.arguments?.ensembl_id)return `${a.title} · ${a.meta.arguments.ensembl_id}`;if(a.kind==='tool_reading'){const source=state.artifacts.find(x=>x.id===a.meta.source_artifact_id);return source?`${artifactName(source.id)} · 확인한 부분`:'확인한 원문·결과';}return a.title;};
const inputContext = a => a.meta.contrast ?? state?.artifacts.find(i=>i.id===a.meta.consumed_artifacts?.[0])?.meta.contrast;
function notice(message){clearTimeout(noticeTimer);const n=document.querySelector('#notice');n.textContent=message;n.classList.add('visible');noticeTimer=setTimeout(()=>n.classList.remove('visible'),7000)}
async function api(path,body){const response=await fetch(deploymentURL(path),{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Evida-Request':'1'}:{},body:body?JSON.stringify(body):undefined});const data=await response.json();if(!response.ok)throw Error(data.error||'요청을 완료하지 못했습니다.');return data}
let gatewayStatusPending=null;
function gatewayDisplayState(value){const g=value?.gateway??{};return JSON.stringify([g.available,g.message,g.requested_model,g.requested_effort,g.approved_models,value?.read_only_preview])}
async function refreshGatewayStatus({force=false,renderChanges=true}={}){
 if(gatewayStatusPending){if(!force)return gatewayStatusPending;await gatewayStatusPending}
 const pending=(async()=>{
  const before=gatewayDisplayState(status);
  try{
   const response=await fetch(deploymentURL('/api/status'),{cache:'no-store',signal:AbortSignal.timeout(5000)}),fresh=await response.json();
   if(!response.ok||typeof fresh.gateway?.available!=='boolean')throw Error('모델 연결 상태 확인 실패');
   status=fresh;
  }catch{
   status={...status,gateway:{...status?.gateway,available:false,message:'모델 연결 상태를 확인하지 못했습니다. 입력 초안은 유지됩니다.'}};
  }
  if(renderChanges&&before!==gatewayDisplayState(status)&&!busy)render();
  return status.gateway.available===true;
 })();
 gatewayStatusPending=pending;
 try{return await pending}finally{if(gatewayStatusPending===pending)gatewayStatusPending=null}
}
function checkGatewayWhenVisible(){if(status&&!document.hidden&&!busy)refreshGatewayStatus().catch(()=>{})}
window.addEventListener('focus',checkGatewayWhenVisible);
document.addEventListener('visibilitychange',checkGatewayWhenVisible);
Object.assign(labels,{literature_compounds:'문헌 후보의 공식 구조',structure_search:'표적의 실험 구조 목록',compound_candidates:'공개 화합물 후보',compound_selection:'계산할 후보 선정',discovery_review:'선택지 검토'});
function sourceLinks(refs){return refs?.length?`<div class="source-links">${refs.map(ref=>button('source',esc(sourceDisplayLabel(state.artifacts.find(a=>a.id===ref.split('#')[0]))),`data-id="${esc(ref)}"`,'link-button')).join('')}</div>`:''}
function draftKey(){return `evida-draft-${state?.id??'new'}`}
function latestFrame(){return state?.events.filter(e=>e.kind==='work_framed'&&e.body.based_rev===state.rev).at(-1)?.body}
function latestIntentEdit(){return state?.events.filter(e=>e.kind==='intent_edit').at(-1)?.body}
function editableIntents(){if(state?.intent.length||latestIntentEdit())return state.intent;return latestFrame()?.intent_records??state?.decision?.intent_records??[]}
function intents(){
 if(state?.decision_rev===state?.rev)return state?.intent??[];
 const records=latestFrame()?.intent_records??editableIntents(),edit=latestIntentEdit();
 const merged=new Map(records.map(r=>[r.id,r]));
 if(edit){
  const protectedIds=new Set(edit.protected_ids??edit.records.map(r=>r.id));
  for(const r of state.intent)if(protectedIds.has(r.id))merged.set(r.id,r);
  for(const id of edit.deleted_ids??[])merged.delete(id);
 }
 return [...merged.values()];
}
// Preserve the reader's expanded panels during progress refreshes. This is
// presentation state only; it cannot change research, source data or decisions.
const detailPanelStates = new Map();
let lastRenderedView = null;
function detailPanelKeys(){
  const counts=new Map();
  return [...app.querySelectorAll('details')].map(node=>{
    const titles=[];
    for(let p=node;p&&p!==app;p=p.parentElement){
      if(p.tagName==='DETAILS')titles.unshift(p.dataset.detailKey?'key:'+p.dataset.detailKey:p.querySelector(':scope > summary')?.textContent.trim()??'');
      if(p.dataset?.researchCheck)titles.unshift('check:'+p.dataset.researchCheck);
    }
    const base=JSON.stringify(titles),n=counts.get(base)??0;counts.set(base,n+1);
    return [base+':'+n,node];
  });
}
function previewReadOnly(){return EVIDA_BASE==='/preview'||status?.read_only_preview===true}
function renderPreviewNotice(){if(!previewReadOnly())return '';const url=location.origin+'/?'+new URLSearchParams(state?{workspace:state.id}:{});return `<aside class="ui-preview-notice" aria-label="미리보기 안내"><span>읽기 전용 미리보기 · 저장·실행 없음</span><a href="${esc(url)}" target="_blank" rel="noopener">운영 연구 열기 ↗</a></aside>`}
function render(){
  readerSnapshot();
  queueMicrotask(()=>loadRoadmapHistory());
  if(lastRenderedView)detailPanelStates.set(lastRenderedView,new Map(detailPanelKeys().map(([key,node])=>[key,node.open])));
  const focused=document.activeElement?.id, start=document.activeElement?.selectionStart;
  const active=state?.jobs.some(j=>['running','queued'].includes(j.status));
  app.innerHTML=deploymentHTML(`<div class="shell"><aside class="rail">${renderResearchRail()}</aside>
    <div class="main-shell"><header class="topbar"><div class="breadcrumb"><span>워크스페이스</span><span>/</span><strong>${esc(state?.title??'새 연구')}</strong></div><div class="top-actions">${previewReadOnly()||status.gateway.available?'':`<span class="gateway-warning" role="status">${esc(status.gateway.message??'모델 연결 확인 필요')}</span>`}${modelAccessButton()}${button('usage-help','도움말','','quiet small')}${state?button('tab','변경 기록',`data-id="history"`,'quiet small'):''}<span class="saved">${active?'작업 실행 중':state?'저장됨 · 연구 기록 '+state.rev:'연구 준비'}</span>${state?button('export','기록 내보내기','','small'):''}</div></header>
    <main class="page" id="main">${renderPreviewNotice()}${submitPhase?`<p class="submitting" role="status">${esc(submitPhase)}</p>`:''}${actionError?`<p class="action-error" role="alert">${esc(actionError)}</p>`:''}${state?teamGuide():''}${state?workspace():welcome()}</main></div></div>`);
  lastRenderedView=JSON.stringify([state?.id??'new',tab,tab==='data'?selected:null]);
  const panelStates=detailPanelStates.get(lastRenderedView);
  if(panelStates)for(const [key,node] of detailPanelKeys())if(panelStates.has(key))node.open=panelStates.get(key);
  if(!state&&intakeFile){const input=document.getElementById('intake-file');if(input){const transfer=new DataTransfer();transfer.items.add(intakeFile);input.files=transfer.files;}}
  if(focused){const target=document.getElementById(focused);if(target){target.focus({preventScroll:true});if(typeof start==='number'&&target.setSelectionRange)try{target.setSelectionRange(start,start)}catch{}}}
  workspaceAfterRender();
  semanticAfterRender();
}
function welcome(){return renderGoalWelcome()}
// Two tabs, not four. The research stages are what a researcher reads; everything retrieved or
// computed is one "자료" tab, with the tool-by-tool workbench a drawer inside it rather than a
// separate destination. The change log is a button in the top bar and appears as a tab only while
// it is open, so there is a way back without a permanent fourth tab.
function workspace(){return renderDecisionWorkspace()}
function research(){return renderRoadmapResearch()}
function questions(items){return items?.length?`<div class="questions">${items.map(q=>`<div class="question"><strong class="small">${esc(q.question)}</strong><small>${esc(q.affects)}</small></div>`).join('')}</div>`:''}
function quotaNotice(){return state.quota_resume?`<section class="notice-inline"><p>서비스 한도로 중단됐습니다. 완료한 조회는 저장돼 있습니다.</p>${button('resume-planner','중단한 판단 이어가기',`data-id="${esc(state.quota_resume.source_job)}" ${busy?'disabled':''}`,'small')}</section>`:''}
function jobsPanel(){return state.jobs.length?`<section class="panel"><h2>실행 기록</h2><div class="jobs">${state.jobs.slice(-6).reverse().map(j=>`<div><div class="job"><span class="job-name">${esc(j.kind==='planner'?'근거 검토와 판단':labels[j.kind]??j.kind)}</span><span class="status-word ${j.status}">${esc(jobStatus(j))}</span></div>${j.error?`<p class="job-error">${esc(j.error)}</p>`:''}</div>`).join('')}</div></section>`:''}
function dataView(){const artifacts=state.artifacts.filter(a=>!['model_receipt','decision_proposal','research_notes','tool_reading','protocol_snapshot','explanation_context','explanation_answer','explanation_model_output','explanation_reading'].includes(a.kind)&&(!query||[a.title,a.meta.arguments?.ensembl_id??''].join(' ').toLowerCase().includes(query.toLowerCase())));return `<div class="data-toolbar"><input id="artifact-search" type="text" placeholder="자료 이름으로 찾기" value="${esc(query)}" aria-label="자료 검색">${button('upload','＋ 자료 추가')}</div><div class="data-layout ${selected?'has-selection':''}"><div><div class="artifact-list">${artifacts.map(a=>button('source',`<span class="artifact-title">${esc(artifactName(a.id))}${inputContext(a)?`<span class="muted"> · ${esc(inputContext(a).candidate_label)} / ${esc(inputContext(a).cohort)}</span>`:''}</span><span class="artifact-meta"><span>${esc(labels[a.kind]??a.kind)}</span><span>${a.meta.result_status?esc(jobLabels[a.meta.result_status]??a.meta.result_status):'원자료'}</span></span>`,`data-id="${a.id}"`,`artifact ${selected===a.id?'active':''}`)).join('')||'<div class="panel empty">아직 연결된 자료가 없습니다.</div>'}</div><div class="rule"></div><details class="tool-drawer" data-detail-key="direct-lookup"><summary>직접 조회 · 도구 실행<small>필요할 때만 엽니다. 평소에는 연구 탭의 단계가 필요한 조회를 스스로 합니다.</small></summary><section class="panel"><h3>공개 문헌 찾기</h3><div class="tool-form"><label>과학 질문<input type="text" id="literature-query" placeholder="표적, 기전, 관측…"></label>${button('literature','검색',busy?'disabled':'')}</div><p class="limit">Europe PMC 문헌·초록을 조회합니다.</p></section><section class="panel"><h3>표적 속성 조회</h3><div class="tool-form"><label>인간 Ensembl ID<input type="text" id="target-id" placeholder="ENSG…"></label>${button('target','조회',busy?'disabled':'')}</div><p class="limit">Open Targets의 표적 수준 속성입니다.</p></section>${renderScienceWorkbench()}</details></div><div class="data-detail">${selected?artifactDetail():'<section class="panel empty"><strong>검토할 자료를 선택하세요.</strong>원자료를 보존한 상태에서 계산하거나 출처와 관측을 확인합니다.</section>'}</div></div>`}
function artifactDetail(){const a=state.artifacts.find(a=>a.id===selected);if(!a)return '';if(!detail||detail.artifact_id!==selected)return '<section class="panel">자료를 읽고 있습니다.</section>';const result=detail.result;const handledLimits=['target_context','gtopdb_pharmacology'].includes(a.kind)||result?.view_kind==='article_references';const total=result?.retained_total_rows??result?.panel_total_rows??result?.total_rows??result?.rows?.length;const capability=status.capabilities.find(c=>c.input_kind===a.kind&&['rdkit','admet','rna_observations','rna_weighted_distribution'].includes(c.id));return `<section class="panel"><div class="section-mark">${esc(labels[a.kind]??a.kind)}</div><h2>${esc(artifactName(a.id))}</h2><div class="source-summary"><span>${a.meta.source_mode==='public_download'?'공개 원자료 수신':a.meta.source_mode==='researcher_upload'?'연구자 업로드':a.meta.result_status?'실제 도구 실행':'보존 자료'}</span><span>${new Date(a.created).toLocaleString('ko-KR')}</span>${total!==undefined?`<span>${number(total)}행 보존</span>`:''}${result?.content_coverage?`<span>${result.content_coverage.scope==='body_available'?'본문 XML 포함':result.content_coverage.scope==='abstract_only'?'초록만 수신 · 본문 미반환':'본문 미반환'}</span>`:''}</div><div class="detail-actions">${capability?button('tool',capability.id==='rdkit'?'물성 계산':capability.id==='admet'?'ADMET 예측':capability.id==='rna_weighted_distribution'?'평균·분포 계산':'관측 검토',`data-tool="${capability.id}" data-id="${a.id}" ${busy?'disabled':''}`,'primary small'):''}${button('download','원본·전체 결과 내려받기',`data-id="${a.id}"`,'small')}</div>
 ${result?.error?`<div class="notice-inline">${esc(result.error)}</div>`:''}${result?.contrast?`<p class="small muted">${esc(result.contrast.candidate_label)} · ${esc(result.contrast.cohort)} · ${esc(result.context)}</p>`:''}${!handledLimits&&a.kind!=='rna_candidate_space'&&result?.limits?.[0]?`<p class="limit">${esc(result.limits[0])}</p>`:''}${a.kind==='rna_seed_analysis'?seedSummary(result):''}${a.kind==='source_image'?`<img class="source-original-image" alt="${esc(a.title)}" src="/api/workspaces/${state.id}/artifacts/${a.id}?image=1"><p class="limit">공개 원 이미지입니다. 자동 판독이나 새 실험 결과가 아닙니다.</p>`:a.kind==='public_lookup_bundle'?publicLookupBundleView(result):a.kind==='compound_selection'?compoundSelectionView(result):a.kind==='research_evidence'?researchEvidenceView(result):a.kind==='chemical_sirna_evidence'?chemicalSourceView(result):a.kind==='discovery_review'?reviewRecordView(result,a.meta):a.kind==='tool_reading'?readingSnapshotView(result):a.kind==='source_visual_review'&&result?.rows?sourceVisualReviewView(result):a.kind==='article'&&result?.rows?articleView(result):a.kind==='repository_document'&&result?.rows?repositoryDocumentView(result):result?.rows?renderTable(result,a.kind):result?.response?.data?.target?targetTable(result.response.data.target):detail.preview?`<p class="limit">원자료 앞부분입니다. 계산 결과가 아닙니다.</p><pre class="raw">${esc(detail.preview)}</pre>`:result?json(result):''}
 ${handledLimits?'':['rna_candidate_space','rna_duplex','rna_duplex_seed','rna_duplex_transcriptome','rna_delivery_response'].includes(a.kind)?`<details class="meta-details"><summary>계산 범위와 아직 확인하지 않은 조건</summary>${(result?.limits??[]).map(l=>`<p class="limit">${esc(l)}</p>`).join('')}</details>`:(result?.limits??a.meta.limits??[]).map(l=>`<p class="limit">${esc(l)}</p>`).join('')}
 ${a.meta.consumed_artifacts?.length?sourceLinks(a.meta.consumed_artifacts):''}
 <details class="meta-details"><summary>출처·조건·도구 버전</summary>${a.meta.source?.url?`<p class="limit"><a href="${esc(safeUrl(a.meta.source.url))}" target="_blank" rel="noopener noreferrer">공개 원자료 열기 ↗</a></p>`:''}${json(a.meta)}${result?.endpoint_metadata?json({endpoint_metadata:result.endpoint_metadata,versions:result.versions}):''}${result?.columns?json({columns:result.columns,versions:result.versions}):''}<p class="mono">SHA256 ${esc(a.sha256)}</p></details></section>`}
function seedSummary(result){const summary=result.summary;if(!summary)return '';return `<div class="source-summary"><span>참조 대응 ${number(summary.mapped_genes)}개</span><span>미대응 ${number(summary.unmapped_genes)}개</span><span>분포 비교 ${number(summary.distribution_eligible_genes)}개</span></div><p class="small muted">${esc(result.reference?.assembly)} · Ensembl ${esc(result.reference?.annotation_release)} · 기존 처리표에서 계산한 seed 일치군의 발현 변화</p><div class="table-scroll"><table><thead><tr><th>seed</th><th>일치군 / 배경군</th><th>log₂ FC 중앙값 · 일치군 / 배경군</th><th>KS 통계량</th><th>Holm 조정 p-value</th></tr></thead><tbody>${(summary.tests??[]).map(t=>`<tr><td>${esc(t.seed)}</td><td>${number(t.target_genes)} / ${number(t.background_genes)}</td><td>${number(t.target_median)} / ${number(t.background_median)}</td><td>${number(t.statistic)}</td><td>${number(t.pvalue_holm_two_seed_family)}</td></tr>`).join('')}</tbody></table></div><p class="limit">집단 분포의 비교이며 개별 유전자의 off-target이나 인과 기전을 입증하지 않습니다. 원행의 미대응·결측과 참조 선택 조건을 함께 확인하세요.</p>`}
function safeUrl(value){try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)?url.href:'#'}catch{return '#'}}
function targetTable(t){return `<h3>${esc(t.approvedSymbol)} · ${esc(t.approvedName)}</h3>${button('science-target-context-source','이 표적의 유전·안전성 조건 확인',`data-target-id="${esc(t.id)}"`,'small')}<div class="table-scroll"><table><thead><tr><th>평가 항목</th><th>접근 분류</th><th>DB 반환값</th></tr></thead><tbody>${t.tractability.map(r=>`<tr><td>${esc(r.label)}</td><td>${esc(r.modality)}</td><td>${r.value===true?'true':r.value===false?'false':'미확인'}</td></tr>`).join('')}</tbody></table></div>`}
function admetPredictionCell(row,endpoint,result){
 const flag=(result.prediction_domain_check?.flags??[]).find(f=>f.row_id===row.row_id&&f.endpoint===endpoint);
 return `${number(row.predictions?.[endpoint])}${flag?'<br><span class="limit">정의 범위 밖 · 수치 해석 보류</span>':''}`;
}
function admetEndpointTable(result){
 const rows=result.rows??[], endpoints=[...new Set(rows.flatMap(r=>Object.keys(r.predictions??{})))];
 if(!endpoints.length)return '<p class="limit">이번 범위에 반환된 예측값이 없습니다. 계산 상태와 원행의 사유를 확인하세요.</p>';
 const metadata=new Map((Array.isArray(result.endpoint_metadata)?result.endpoint_metadata:[]).map(m=>[m.id,m]));
 return `<details class="meta-details admet-endpoints"><summary>전체 예측 항목 ${number(endpoints.length)}개 비교${result.prediction_domain_check?.flags.length?` · 범위 확인 ${number(result.prediction_domain_check.flags.length)}건`:""}</summary><p class="limit">현재 페이지의 후보를 비교합니다. 좁은 화면에서는 표를 좌우로 밀어 값을 확인하세요. 정의 범위 밖의 값은 원 출력으로 보존하며, 그 값만으로 후보를 배제하지 않습니다. 분류 점수는 환자의 발생 확률이나 확인된 안전성 수치가 아닙니다. 항목마다 의미와 단위가 다르며, 빈 값은 0이 아닌 미반환입니다.</p><div class="table-scroll"><table><thead><tr><th>예측 항목 · 원 정의</th><th>유형 · 단위</th>${rows.map(r=>`<th>${esc(r.candidate_id||r.row_id)}<br><small>${esc(jobLabels[r.status]??r.status)}</small></th>`).join('')}</tr></thead><tbody>${endpoints.map(id=>{const m=metadata.get(id)??{},kind=m.task_type==='classification'?'분류 점수':m.task_type==='regression'?'회귀 예측':'유형 미기록',unit=m.task_type==='classification'?'무단위':m.units&&m.units!=='-'?m.units:'단위 미기록';return `<tr data-endpoint="${esc(id)}"><td><strong>${esc(id)}</strong>${m.name?`<br>${esc(m.name)}`:''}${m.url&&safeUrl(m.url)!=='#'?`<br><a href="${esc(safeUrl(m.url))}" target="_blank" rel="noopener noreferrer">원 항목 정의 ↗</a>`:''}</td><td>${esc(kind)}<br>${esc(unit)}</td>${rows.map(r=>`<td>${admetPredictionCell(r,id,result)}</td>`).join('')}</tr>`}).join('')}</tbody></table></div></details>`;
}
function renderTable(result,kind){const science= scienceTable(result,kind);if(science!==null)return science;const structures=hasDepictions(result)?structureTable(result):'';if(structures)return structures+genericTable(result,kind);return genericTable(result,kind);}
function genericTable(result,kind){if(kind==='rna_weighted_distribution'){return `<div class="table-scroll"><table><thead><tr>${['조건','비교군 수','평균 차이 · log₂ FC','CDF 차이 최댓값','CDF 차이 최솟값','전체 곡선 교차'].map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(r.case)}</td><td>${number(r.target_Q)}</td><td>${number(r.mean_difference)}</td><td>${number(r.maximum_positive_difference)}</td><td>${number(r.minimum_difference)}</td><td>${r.crosses?'있음':'관측되지 않음'}</td></tr>`).join('')}</tbody></table></div><p class="limit">전체 관측값에서 계산했습니다. 평균 감소와 분포 전체의 한쪽 이동은 다릅니다. 유의성·인과성 검정은 아닙니다.</p>`;}if(kind==='rna_method_review')return renderRnaMethodReview(result);if(kind==='rna_seed_sensitivity')return renderRnaSensitivity(result);const rows=result.rows;let headers,fields;if(kind==='rdkit'){headers=['후보','계산 상태','MolWt · g/mol','LogP','TPSA · Å²','QED'];fields=r=>[candidateLabel(r),esc(jobLabels[r.status]??r.status),...['MolWt','LogP','TPSA','QED'].map(k=>number(r.properties?.[k]))]}else if(kind==='admet'){const endpoints=Object.keys(rows.find(r=>r.predictions)?.predictions??{}).slice(0,3);headers=['후보','계산 상태',...endpoints];fields=r=>[candidateLabel(r),esc(jobLabels[r.status]??r.status),...endpoints.map(k=>number(r.predictions?.[k]))]}else if(kind==='rna_observations'){headers=['유전자','이름','log₂ FC','p-value','조정 p-value'];fields=r=>[esc(r.gene_id),esc(r.symbol),number(r.values.log2FoldChange),number(r.values.pvalue),number(r.values.padj)]}else if(kind==='rna_seed_analysis'){headers=['유전자','참조 대응','log₂ FC','7mer-m8','8mer','분포 비교 포함'];fields=r=>[esc(r.symbol||r.gene_id),r.reference_mapping==='mapped'?'대응':'미대응',number(r.values?.log2FoldChange),number(r.seed_counts?.mer7m8),number(r.seed_counts?.mer8),r.distribution_eligible?'포함':'제외 · 사유는 원행 확인']}else if(kind==='molecule_csv'){headers=['후보',...result.header];fields=r=>[esc(r.candidate_id??r.row_id),...r.raw_values.map(esc)]}else if(kind==='rna_gene_review'){headers=['유전자','자료','대응','log₂ FC','조정 p-value'];fields=r=>[esc(r.requested_gene),esc(artifactName(r.input_artifact_id)),r.status==='not_found_in_table'?'행 없음':r.matching_rows>1?`대응 ${r.matching_rows}행`:'원행',number(r.observation?.values.log2FoldChange),number(r.observation?.values.padj)]}else if(kind==='entity_search'){headers=['ID','이름','종류'];fields=r=>[esc(r.id),esc(r.name),esc(r.entity)]}else if(kind==='literature'){headers=['발행','문헌','저자'];fields=r=>[esc(r.pubYear),`<a href="https://europepmc.org/article/${encodeURIComponent(r.source)}/${encodeURIComponent(r.id)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>`,esc(r.authorString)]}else{headers=['항목','내용'];fields=r=>[esc(r.row_id??r.id??''),esc(JSON.stringify(r))]}
 return `<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((r,i)=>`<tr>${fields(r).map((v,j)=>`<td>${j===0?button('row',v,`data-index="${i}"`,'link-button small'):v}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="pagination"><span>${number(result.offset+1)}–${number(result.offset+rows.length)} / ${number(result.total_rows)}행 · 행 이름을 누르면 전체 값 확인</span><div>${button('prev','이전',offset===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div>${kind==='admet'?admetEndpointTable(result):''}`}
function historyPanel(){return `<div class="work-grid"><section class="panel"><h2>연구가 바뀐 과정</h2>${[...state.events].reverse().map(e=>`<article class="history-row"><div class="history-time">${time(e.created)}<br><span class="mono">#${e.seq}</span></div><div><h3>${esc(eventLabels[e.kind]??e.kind)}${inputProvenance(e).synthetic||e.effective_provenance?.corrected_by?' · '+esc(inputProvenanceLabel(e)):''}</h3><p>${esc(e.body.text??e.body.title??e.body.current_question??e.body.error??(e.body.status?jobLabels[e.body.status]??e.body.status:''))}</p>${inputProvenanceNotice(e)}${e.body.output_id?sourceLinks([e.body.output_id]):''}<details class="meta-details"><summary>세부 기록</summary>${json(e.body)}</details></div></article>`).join('')}</section><aside>${jobsPanel()}<section class="panel"><h2>기록 보존</h2><p class="small muted">정정 전 원문과 이전 결과도 남습니다. 새 조건을 반영하지 않은 판단은 현재 판단과 구별합니다.</p>${button('export','연구 기록 내보내기','','small')}</section></aside></div>`}
async function loadProject(id){
 if(state)semanticStop(state.id,'다른 연구로 이동했습니다. 시작한 문헌 준비는 원래 연구에서 계속됩니다.');
 const version=++projectLoadVersion,u=new URL(location.href);
 if(u.searchParams.get('workspace')!==id)u.searchParams.delete('guide');
 u.searchParams.set('workspace',id);history.replaceState(null,'',u);
 let fresh;
 try{fresh=await api(`/api/workspaces/${id}`)}catch(error){if(version!==projectLoadVersion)return;throw error}
 if(version!==projectLoadVersion)return;
 tab='research';state=fresh;evidaStorage.setItem('evida-project',id);draft=evidaStorage.getItem(draftKey())??'';
 selected=null;detail=null;offset=0;query='';optionsOffset=0;optionsPage=null;optionsWorkspace=null;
 render();if(optionsOpen)await loadOptions();if(version===projectLoadVersion)window.scrollTo(0,0);
}
async function refresh(){if(!state)return;const wid=state.id;const fresh=await api(`/api/workspaces/${wid}`);if(state?.id!==wid)return;const changed=fresh.event_cursor!==state.event_cursor;state=fresh;if(changed){projects=await api('/api/workspaces');render();if(optionsOpen)await loadOptions()}}
async function chooseArtifact(id){selected=id;offset=0;detail=null;tab='data';render();await readDetail()}
async function openArticleSection(node){articleReferenceModes.delete(selected);const next=Number(node.dataset.offset);if(!Number.isInteger(next)||next<0)return;offset=next;await readDetail();document.querySelector('.data-detail')?.scrollIntoView({block:'start'});}
async function readDetail(){const id=selected,data=await api(`/api/workspaces/${state.id}/artifacts/${id}?offset=${offset}&limit=${state.artifacts.find(a=>a.id===id)?.kind==='rna_delivery_response'?100:30}${candidateSpaceQuery(id)}${rnaContextQuery(id)}${articleReferenceQuery(id)}`);if(id===selected){detail=data;render()}}
async function saveMessage(){if(!draft.trim())return;const body={kind:inputKind,text:draft.trim(),synthetic:syntheticDraft};await api(`/api/workspaces/${state.id}/commands`,{expected_rev:state.rev,command_id:crypto.randomUUID(),body});draft='';syntheticDraft=false;evidaStorage.removeItem(draftKey());await refresh()}
async function runTool(tool,args){const response=await api(`/api/workspaces/${state.id}/jobs`,{expected_rev:state.rev,tool,arguments:args});await refresh();notice('작업을 시작했습니다. 결과와 원자료를 함께 보존합니다.');return response}
function showDialog(title,content){dialog.innerHTML=deploymentHTML(`<div class="dialog-title"><h2 id="editor-title">${esc(title)}</h2>${button('close-dialog','닫기','','quiet small')}</div>${content}`);dialog.showModal()}
function editIntents(){const records=structuredClone(editableIntents());intentEditBase={workspace:state.id,rev:state.rev,records};showDialog('연구 의도 수정',`<p class="small muted">저장된 의도를 편집합니다. 바꾼 항목만 연구자의 수정으로 기록하고, 나머지 내용과 출처는 유지합니다.</p><div id="intent-rows">${records.map(intentRow).join('')||intentRow({label:'',text:''})}</div><div class="dialog-actions">${button('add-intent','＋ 항목 추가')}${button('save-intent','수정 내용 저장','','primary')}</div>`)}
function intentRow(r={}){return `<div class="edit-row" data-record-id="${esc(r.id??'')}"><input type="text" class="intent-label" aria-label="의도 항목 이름" placeholder="예: 판단 기준" value="${esc(r.label??'')}"><textarea class="intent-text" aria-label="의도 항목 내용" placeholder="내용 또는 미확인 사항">${esc(r.text??'')}</textarea>${button('remove-intent','×','aria-label="이 항목 삭제"','quiet')}</div>`}
function uploadDialog(){showDialog('기존 자료 추가',`<p class="small muted">원본 파일을 보존합니다. 모르는 조건은 맥락에 미확인으로 적어 주세요.</p><label class="input-label" for="upload-file">자료 파일</label><input type="file" id="upload-file" accept=".csv,.tsv,.txt,.gz"><div class="upload-fields"><label>자료 종류<select id="upload-kind"><option value="molecule_csv">기존 분자 후보 CSV</option><option value="rna_table">기존 RNA 차등발현표</option></select></label><label data-molecule-field>CSV 구분자<select id="upload-delimiter"><option value=",">쉼표</option><option value=";">세미콜론</option><option value="tab">탭</option></select></label><label data-molecule-field>SMILES 열 이름<input type="text" id="upload-smiles" value="smiles"></label><label data-molecule-field>후보 식별자 열 이름<input type="text" id="upload-id" value="cid"></label></div><div id="upload-format-help" class="small muted"><p>후보 ID와 SMILES가 있는 CSV입니다. 열 이름과 구분자를 맞춰 주세요.</p><a href="/templates/molecules.csv" download>빈 CSV 양식 받기</a></div><label class="input-label" for="upload-context">자료의 대상·조건·출처</label><textarea id="upload-context" placeholder="어떤 후보 또는 시료의 자료인지, 단위·시점·대조군 등 알려진 내용을 적어 주세요."></textarea><div class="dialog-actions"><span class="small muted">파일당 10 MiB</span>${button('save-upload','자료 저장','','primary')}</div>`)}
async function act(action,node){
 if(await semanticLiteratureAction(action,node))return;
 if(await workspaceAction(action,node))return;
 if(busy && !['close-dialog','usage-help','model-help'].includes(action))return;
 if(action.startsWith('interaction-')){try{await interactionAction(action,node)}catch(e){notice(e.message)}return}
 if(action.startsWith('roadmap-')){await roadmapAction(action,node);return}
 if(action.startsWith('discovery-')){await discoveryAction(action,node);return}
 if(action==='mechanism-support'){await loadMechanismSupport();return}
 if(action==='mechanism-axis'){
  const row=((mechanismRanking||{}).rows||[]).find(r=>r.option_id===node.dataset.option);
  showDialog(`${row?row.label:'선택지'} · ${AXIS_LABEL[node.dataset.axis]??node.dataset.axis}`,
             mechanismAxisDetail(row,node.dataset.axis));return;
 }
 if(action==='context-edit'){openConditionEdit(node);return}
 if(action==='context-save'){await saveConditionEdit(node.dataset.review==='true');return}
 if(action.startsWith('science-')){await scienceAction(action,node);return}
 if(action==='usage-help'){openUsageHelp();return}
 if(action==='model-help'){await openModelAccessHelp();return}
 if(action==='choose-path'){chooseEntry(node.dataset.mode);return}
 if(action==='show-jobs'){tab='history';render();return}
 if(action==='plan'&&isUsageQuestion(draft)){openUsageHelp(draft);return}
 if(action==='team-prompt'||action==='team-feedback'){await teamAction(action);return}
 if(action==='close-dialog'){dialog.close();return}
 if(action==='remove-intent'){node.closest('.edit-row').remove();return}
 if(action==='add-intent'){document.querySelector('#intent-rows').insertAdjacentHTML('beforeend',intentRow());return}
 if(action==='row'){const row=detail.result.rows[Number(node.dataset.index)];showDialog('행의 전체 값과 출처',json(detail.result.header?{header:detail.result.header,row}:row));return}
 if(action==='edit-intent'){editIntents();return}
 if(action==='upload'){uploadDialog();return}
 if(action==='hypothesis-feedback'){openResearchFeedback(null,node.dataset.hypothesis,node.dataset.part??null);return}
 if(action==='check-feedback'){openResearchFeedback(node.dataset.check,null);return}
 if(action==='delegate-check'){openCheckDelegation(node.dataset.check);return}
 if(action==='evidence-history'){await openEvidenceHistory(node.dataset.hypothesis,Number(node.dataset.offset));return}
 if(action==='history-evidence-feedback'){await reviewHistoricalEvidence(node.dataset.decision);return}
 if(action==='transport-handle'){showDialog('원 응답의 자료 전달 표기',`<p class="prose">${esc(node.dataset.original)}</p><p class="limit">모델에 자료를 전달할 때 사용한 내부 위치입니다. 논문 인용이나 이해·주장 지지의 증거는 아닙니다. 연결된 원자료에서 실제 내용과 적용 조건을 확인하세요. 원 응답은 변경하지 않았습니다.</p>`);return}
 if(action==='historical-hypothesis'){await openHistoricalHypothesis(node.dataset.decision,node.dataset.hypothesis);return}
 if(action==='show-check'){tab='research';roadmapSelections.set(state.id,'next');render();const item=[...document.querySelectorAll('[data-research-check]')].find(el=>el.dataset.researchCheck===node.dataset.check);if(item){if(item.tagName==='DETAILS')item.open=true;item.scrollIntoView({behavior:'smooth',block:'center'})}return}
 if(action==='message-source'){const e=state.events.find(e=>e.body.message_id===node.dataset.id);showDialog('원래 입력',inputSourceView(e));return}
 if(action==='export'){window.location.href=deploymentURL(`/api/workspaces/${state.id}/export`);return}
 if(action==='download'){window.location.href=deploymentURL(`/api/workspaces/${state.id}/artifacts/${node.dataset.id}?download=1`);return}
 if(action==='new'){++projectLoadVersion;intakeError='';actionError='';intakeFile=null;intakeContext='';intakeMode='question';optionsOpen=false;inputKind='message';syntheticDraft=false;history.replaceState(null,'',deploymentURL('/'));state=null;selected=null;detail=null;draft=evidaStorage.getItem(draftKey())??'';tab='research';evidaStorage.removeItem('evida-project');render();return}
 if(action==='tab'){tab=node.dataset.id;render();window.scrollTo(0,0);return}
 if(action==='source'){if(dialog.open)dialog.close();await chooseArtifact(node.dataset.id);return}
 if(action==='article-section'){await openArticleSection(node);return}
 if(action==='article-references'){await openArticleReferences(node);return}
 if(action==='prev'||action==='next'){offset=Math.max(0,offset+(action==='next'?30:-30));await readDetail();return}
 if(action==='project'){await loadProject(node.dataset.id);return}
 busy=true;node.disabled=true;actionError='';intakeError='';
 try{
  if(action==='example'){notice('공개 원자료를 내려받아 조사 때의 내용과 대조하고 있습니다.');state=await api('/api/examples',{id:node.dataset.id});projects=await api('/api/workspaces');draft='';evidaStorage.setItem('evida-project',state.id);const failed=state.events.some(e=>e.kind==='source_import_failed');notice(failed?'일부 자료를 받지 못했습니다. 변경 기록에서 원인을 확인할 수 있습니다.':'공개 원자료를 저장했습니다. 자료와 도구에서 실제 계산을 시작할 수 있습니다.')}
  if(action==='create-message')await startIntake();
  if(action==='intake-example')await startExample(node.dataset.id);
  if(action==='run-check'){await api(`/api/workspaces/${state.id}/research-checks`,{expected_rev:state.rev,decision_id:state.decision_id,check_id:node.dataset.check});await refresh();notice('선택한 확인을 실행하고, 모델이 연결돼 있으면 결과를 이어 검토합니다.')}
  if(action==='save-feedback'){await saveResearchFeedback(node.dataset.review==='true')}
  if(action==='save-message'){await saveMessage();notice('내용을 저장했습니다. 이전 원문과 결과는 유지됩니다.')}
  if(action==='resume-planner'){await api(`/api/workspaces/${state.id}/resume-planner`,{expected_rev:state.rev,source_job:node.dataset.id});await refresh();notice('완료한 조회를 유지하며 중단한 판단을 이어갑니다.')}
  if(action==='plan'){await submitResearchFollowthrough()}
  if(action==='synthesize'){await saveMessage();await runTool('planner',{synthesis_only:true})}
  if(action==='tool'){await runTool(node.dataset.tool,{artifact_id:node.dataset.id})}
  if(action==='literature'){await runTool('literature',{query:document.querySelector('#literature-query').value,cursor:'*'})}
  if(action==='target'){await runTool('open_targets',{target_id:document.querySelector('#target-id').value.trim()})}
  if(action==='save-intent'){
   if(!intentEditBase||intentEditBase.workspace!==state.id)throw Error('현재 연구의 의도 편집을 다시 열어 주세요.');
   const records=[...dialog.querySelectorAll('.edit-row')].map(row=>({id:row.dataset.recordId||`intent_${crypto.randomUUID()}`,label:row.querySelector('.intent-label').value,text:row.querySelector('.intent-text').value}));
   const unchanged=records.length===intentEditBase.records.length&&records.every((r,i)=>['id','label','text'].every(k=>r[k]===intentEditBase.records[i][k]));
   if(unchanged){dialog.close();intentEditBase=null;notice('변경한 항목이 없습니다.');return;}
   await api(`/api/workspaces/${state.id}/commands`,{expected_rev:intentEditBase.rev,command_id:crypto.randomUUID(),body:{kind:'intent_edit',base_records:intentEditBase.records,records}});
   dialog.close();intentEditBase=null;await refresh();notice('수정한 항목을 저장했습니다. 다른 의도와 출처는 유지됩니다.');
  }
  if(action==='save-upload'){
    const file=dialog.querySelector('#upload-file').files[0], kind=dialog.querySelector('#upload-kind').value;
    const d=dialog.querySelector('#upload-delimiter').value;
    const meta={delimiter:kind==='rna_table'?'\t':d==='tab'?'\t':d,smiles_column:dialog.querySelector('#upload-smiles').value,id_column:dialog.querySelector('#upload-id').value,context:dialog.querySelector('#upload-context').value};
    await validateInputFile(file,kind,meta);await uploadInput(file,kind,meta);dialog.close();notice('원자료를 저장했습니다. 분석을 시작하면 실제 결과를 확인할 수 있습니다.');
  }
 }finally{busy=false;submitPhase='';render()}
}
document.addEventListener('click',event=>{const node=event.target.closest('[data-action]');if(!node||node.disabled)return;act(node.dataset.action,node).catch(e=>{busy=false;submitPhase='';if(state)actionError=e.message;else intakeError=e.message;notice(e.message);render()})});
document.addEventListener('input',event=>{if(event.target.id==='message'){draft=event.target.value;evidaStorage.setItem(draftKey(),draft)}if(event.target.id==='artifact-search'){query=event.target.value;render()}});
document.addEventListener('change',event=>{if(event.target.id==='input-kind')inputKind=event.target.value;if(event.target.id==='synthetic')syntheticDraft=event.target.checked});
document.addEventListener('input',event=>{if(event.target.id==='semantic-literature-query'&&state){const view=semanticView(state.id),wasLoading=view.loading;if(wasLoading)semanticStop(state.id,'검색어가 바뀌어 이전 검색 기다림을 닫았습니다.');view.query=event.target.value;if(wasLoading){view.result=null;render()}}});
document.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.id==='semantic-literature-query'){event.preventDefault();act('semantic-literature-search',event.target)}});
async function init(){[status,projects]=await Promise.all([api('/api/status'),api('/api/workspaces')]);const id=new URLSearchParams(location.search).get('workspace')??evidaStorage.getItem('evida-project');if(id&&projects.some(p=>p.id===id))await loadProject(id);else{draft=evidaStorage.getItem(draftKey())??'';render()}setInterval(()=>{if(state&&!busy)refresh().catch(()=>{})},2500);setInterval(checkGatewayWhenVisible,10000)}
init().catch(e=>{app.innerHTML=`<p class="boot">${esc(e.message)}</p>`});

function sourceVisualReviewView(result){return `<p class="limit">보존된 원문 페이지를 읽고 남긴 판독 기록입니다. 새 실험 결과나 독립 검증은 아닙니다.</p>${result.source_artifact_id?sourceLinks([result.source_artifact_id]):''}${result.rows.map(r=>`<article class="source-paragraph"><h3>${esc(r.page)}쪽 · ${esc(r.region_ko??r.region)}</h3><p class="prose">${esc(r.finding_ko??r.finding)}</p><p class="limit">${esc(r.limit_ko??r.limit)}</p></article>`).join('')}`;}

function readingSnapshotView(view){
  if(view?.semantic_type==='independent_saved_evidence_reads')return `<p class="limit">당시 함께 대조하려고 요청한 보존 원문입니다. 각 읽기의 목적·범위·실제 전달 상태를 구별합니다.</p>${view.rows.map(r=>`<details class="source-paragraph"><summary>${esc(r.purpose)} · ${r.status==='succeeded'?'원문 범위 전달':r.status==='same_immutable_view'?'동일 원문 범위 참조':r.status==='needs_narrower_read'?'범위를 좁혀 읽기 필요':'읽기 실패'}</summary>${sourceLinks([r.source_artifact_id])}${r.view?readingSnapshotView(r.view):`<p>${esc(r.message??`읽기 ${r.same_view_as_read+1}번과 같은 뷰입니다.`)}</p>`}<details><summary>요청 범위와 해시</summary>${json({arguments:r.arguments,source_sha256:r.source_sha256,view_sha256:r.view_sha256,status:r.status})}</details></details>`).join('')}`;
  const result=view?.result;
  const source=view?.artifact_id?sourceLinks([view.artifact_id]):'';
  if(!result)return source+json(view);
  if(result.selected_columns&&Array.isArray(result.rows)){
    const headers=result.selected_columns.map((p,i)=>{const cell=result.rows.find(r=>r.cells?.[i]?.source_cell)?.cells[i].source_cell;return cell?.coordinate?cell.coordinate.replace(/[0-9]+$/,'')+'열':p.join(' · ')});
    const rows=result.rows.map(r=>`<tr><td>${esc(r.identity?.sheet??'')} ${esc(r.identity?.row_number??r.identity?.row_id??r.identity?.candidate_id??'')}</td>${r.cells.map(c=>`<td>${!c.present?'열 없음':c.value===null?'비어 있음 (null)':esc(typeof c.value==='object'?JSON.stringify(c.value):String(c.value))}</td>`).join('')}</tr>`).join('');
    return `<p class="limit">당시 판단에 전달된 원행·열입니다. 원본 전체는 아래 출처에서 다시 열 수 있습니다. 빈 값·0·no·??는 그대로 구별합니다.</p>${source}<div class="table-scroll"><table><thead><tr><th>원 위치</th>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div><p class="limit">이번 전달 ${result.rows.length}행 · 전체 일치 ${esc(result.total_rows)}행${result.has_more?' · 뒤의 일치 행이 더 있습니다':''}</p><details class="meta-details"><summary>원 셀·조건·선택 범위 확인</summary>${json(result)}</details>`;
  }
  return source+json(result);
}

labels.rna_weighted_input = 'RNA 고정 가중치·관측';
labels.rna_weighted_distribution = 'RNA 평균·전체 분포 비교';

labels.source_candidates = "원문에서 찾은 후보·치료 참조";

document.addEventListener('toggle',event=>{if(!event.target.isConnected||event.target.dataset?.detailKey!=='semantic-literature'||!state)return;const view=semanticView(state.id);if(event.target.open){view.paused=false;semanticAfterRender();}else semanticStop(state.id);},true);

