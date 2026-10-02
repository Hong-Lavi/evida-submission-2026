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
