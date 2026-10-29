// Links are built only from identifiers a record already holds. Nothing is looked up here and
// no identifier is guessed, so a malformed value must produce plain text rather than a wrong URL.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const context = vm.createContext({
  esc: s => String(s).replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])),
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/external-links.js'), 'utf8'), context);
const {externalUrl, externalAnchor, identifierLinks, linkifyIdentifiers,
       entityLink, candidateName, candidateLabel} = context;
// Values built inside the vm realm have different prototypes, so normalise before deep compare.
const plain = value => JSON.parse(JSON.stringify(value ?? null));

test('A well formed identifier resolves to its public page', () => {
  assert.equal(externalUrl('nct', 'NCT05321069'), 'https://clinicaltrials.gov/study/NCT05321069');
  assert.equal(externalUrl('pmcid', 'PMC13424673'), 'https://pmc.ncbi.nlm.nih.gov/articles/PMC13424673/');
  assert.equal(externalUrl('pmid', '39591723'), 'https://pubmed.ncbi.nlm.nih.gov/39591723/');
  assert.equal(externalUrl('doi', '10.1007/s40262-023-01314-7'), 'https://doi.org/10.1007/s40262-023-01314-7');
  assert.equal(externalUrl('chembl', 'CHEMBL1868'), 'https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL1868');
  assert.equal(externalUrl('pubchem', '40632'), 'https://pubchem.ncbi.nlm.nih.gov/compound/40632');
});

test('A value that is not that kind of identifier stays plain text', () => {
  for (const value of ['NOTANID', 'NCT123', '', 'NCT0532106X', null, undefined, 42]) {
    assert.equal(externalUrl('nct', value), null, String(value));
  }
  assert.equal(externalUrl('doi', 'not/a/doi'), null);
  assert.equal(externalUrl('unknown_kind', 'NCT05321069'), null);
  assert.equal(externalAnchor('nct', 'NOTANID'), 'NOTANID');
});

test('Identifiers inside free text become links without letting markup through', () => {
  const html = linkifyIdentifiers('<script>x</script> NCT05321069 and PMID: 39591723');
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /href="https:\/\/clinicaltrials\.gov\/study\/NCT05321069"/);
  assert.match(html, /href="https:\/\/pubmed\.ncbi\.nlm\.nih\.gov\/39591723\/"/);
});

test('A DOI containing an ampersand links to that DOI, not to a truncated one', () => {
  // The text is escaped before linkifying, so the ampersand arrives as `&amp;`. Stopping there
  // would point at a different record while looking like a working link.
  const html = linkifyIdentifiers('doi:10.1000/abc&def');
  assert.match(html, /href="https:\/\/doi\.org\/10\.1000\/abc&amp;def"/);
  assert.doesNotMatch(html, /doi\.org\/10\.1000\/abc&amp;amp/, 'the entity is not escaped twice');
  assert.doesNotMatch(html, /href="https:\/\/doi\.org\/10\.1000\/abc"/);
});

test('A DOI still ends at ordinary sentence punctuation', () => {
  const html = linkifyIdentifiers('doi: 10.1000/plain; and more');
  assert.match(html, /href="https:\/\/doi\.org\/10\.1000\/plain"/);
});

test('Every identifier a row carries is offered once', () => {
  const links = identifierLinks({nct_id: 'NCT05321069', molecule_chembl_id: 'CHEMBL1868',
                                 pmid: '39591723', nothing: 'ignored'});
  assert.deepEqual(plain(links).map(l => l.value), ['NCT05321069', '39591723', 'CHEMBL1868']);
  assert.equal(identifierLinks(null).length, 0);
  assert.equal(identifierLinks({nct_id: 'NCT05321069', nctId: 'NCT05321069'}).length, 1,
               'the same resolved page is not offered twice');
});

test('A candidate shows a readable name with its identifier still visible', () => {
  const named = candidateLabel({candidate_id: 'PUBCHEM:40632',
                                structure: {IUPACName: '5-methyl-1-phenylpyridin-2-one'}});
  assert.match(named, /5-methyl-1-phenylpyridin-2-one/);
  assert.match(named, /href="https:\/\/pubchem\.ncbi\.nlm\.nih\.gov\/compound\/40632"/);
  assert.match(named, /PUBCHEM:40632/, 'the identifier stays checkable beside the name');
  assert.equal(candidateName({pref_name: 'METFORMIN'}), 'METFORMIN');
  assert.equal(candidateName({}), null, 'an unnamed candidate is not given an invented label');
});

test('A bare database identifier is linked rather than dressed up as a name', () => {
  const bare = candidateLabel({candidate_id: 'CHEMBL1868'});
  assert.match(bare, /href="https:\/\/www\.ebi\.ac\.uk\/chembl\/explore\/compound\/CHEMBL1868"/);
  assert.match(bare, />CHEMBL1868</);
  assert.equal(candidateLabel({candidate_id: 'BDBM:12'}), 'BDBM:12',
               'an identifier with no public page stays plain text');
  assert.equal(entityLink('BDBM:12'), null);
  assert.deepEqual(plain(entityLink('PUBCHEM:40632')), {kind: 'pubchem', value: '40632'});
});

test('A name from a record cannot inject markup', () => {
  const html = candidateLabel({candidate_id: 'x', name: '<img src=x onerror=alert(1)>'});
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
});
