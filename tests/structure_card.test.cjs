// Structure cards draw the stored SMILES. An unreadable structure must say so rather than show
// an empty box, and nothing here may invent a name, a formula or an identifier.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const context = vm.createContext({
  esc: s => String(s).replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])),
});
for (const file of ['../web/external-links.js', '../web/structure-card.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), context);
}
const {structureCard, structureTable, hasDepictions, structureThumb} = context;

// The card reads `state` and `button` from the page, as the browser provides them.
const withWorkspace = (artifacts, run) => {
  context.state = {id: 'ws', artifacts};
  context.button = (action, label, attrs, cls) =>
    `<button data-action="${action}" ${attrs} class="${cls}">${label}</button>`;
  try { return run(); } finally { context.state = null; }
};
const docking = ids => ({id: 'art_dock', kind: 'molecular_docking',
  meta: {result_status: 'succeeded', arguments: {candidate_ids: ids}}});

const drawn = () => ({
  candidate_id: 'CHEMBL103', name: 'PROGESTERONE',
  smiles: 'CC(=O)[C@H]1CC[C@H]2[C@@H]3CCC4=CC(=O)CC[C@]4(C)[C@H]3CC[C@]12C',
  depiction: {status: 'drawn', svg: '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>',
              formula: 'C21H30O2', average_mass: 314.47, exact_mass: 314.2246,
              inchikey: 'RJKFOVLPORLFTN-LEKSSAKUSA-N',
              smiles: 'CC(=O)[C@H]1CC[C@H]2[C@@H]3CCC4=CC(=O)CC[C@]4(C)[C@H]3CC[C@]12C'},
});

test('A drawn candidate shows its structure, formula, mass and identifiers', () => {
  const html = structureCard(drawn());
  assert.match(html, /<svg/, 'the drawing is rendered');
  assert.match(html, /C21H30O2/);
  assert.match(html, /314\.47 g\/mol/);
  assert.match(html, /RJKFOVLPORLFTN-LEKSSAKUSA-N/);
  assert.match(html, /PROGESTERONE/);
  assert.match(html, /href="https:\/\/www\.ebi\.ac\.uk\/chembl\/explore\/compound\/CHEMBL103"/);
  assert.match(html, /측정된 구조나 입체 배좌가 아니며/, 'the drawing is not claimed as a measurement');
});

test('An unreadable structure says so and keeps the stored string', () => {
  const row = {...drawn(), depiction: {status: 'unparsed', smiles: 'not a smiles'}};
  const html = structureCard(row);
  assert.match(html, /구조 문자열을 읽지 못했습니다/);
  assert.doesNotMatch(html, /<svg/);
  assert.match(html, /not a smiles/, 'the string itself is still shown');
});

test('A row with no drawing at all still renders without inventing one', () => {
  const html = structureCard({candidate_id: 'BDBM:9'});
  assert.match(html, /2D 그림 데이터가 반환되지 않았습니다/, 'missing depiction is explicit, not a blank or invented drawing');
  assert.match(html, /BDBM:9/);
  assert.doesNotMatch(html, /<svg/);
});

test('A truncated depiction set states how many rows were drawn', () => {
  const html = structureTable({rows: [drawn()], depiction_limit: 60,
                               depiction_meaning: '저장된 SMILES의 2D 그림입니다.'});
  assert.match(html, /앞의 60개 행에만/);
  assert.match(html, /나머지 행의 자료는 그대로 있습니다/);
});

test('Depiction presence is detected only when a row actually carries one', () => {
  assert.equal(hasDepictions({rows: [drawn()]}), true);
  assert.equal(hasDepictions({rows: [{candidate_id: 'x'}]}), false);
  assert.equal(hasDepictions({}), false);
  assert.equal(hasDepictions(null), false);
  assert.equal(structureThumb({candidate_id: 'x'}), '');
});

test('A 3D view is offered only when a docking run in this research names the candidate', () => {
  const shown = withWorkspace([docking(['CHEMBL103'])], () => structureCard(drawn()));
  assert.match(shown, /실제 좌표로 3D 보기/);
  assert.match(shown, /data-id="art_dock"/);
  assert.match(shown, /data-candidate="CHEMBL103"/);
  assert.match(shown, /측정된 결합 구조가 아닙니다/);

  const other = withWorkspace([docking(['CHEMBL999'])], () => structureCard(drawn()));
  assert.doesNotMatch(other, /3D 보기/, 'a run for another candidate must not open here');

  const failed = withWorkspace([{...docking(['CHEMBL103']),
    meta: {result_status: 'failed', arguments: {candidate_ids: ['CHEMBL103']}}}],
    () => structureCard(drawn()));
  assert.doesNotMatch(failed, /3D 보기/, 'a failed run has no coordinates to show');

  const none = withWorkspace([], () => structureCard(drawn()));
  assert.doesNotMatch(none, /3D 보기/);
});

test('Record values cannot inject markup through the card', () => {
  const row = {...drawn(), name: '<img src=x onerror=alert(1)>', depiction:
    {...drawn().depiction, formula: '<b>C1</b>'}};
  const html = structureCard(row);
  assert.doesNotMatch(html, /<img/);
  assert.doesNotMatch(html, /<b>C1<\/b>/);
  assert.match(html, /&lt;img/);
});

test('The record’s own InChIKey wins over one computed from the stored SMILES', () => {
  // Both would otherwise be labelled `PubChem · InChIKey` and point at different compounds.
  const row = {...drawn(), inchikey: 'AAAAAAAAAAAAAA-BBBBBBBBBB-N',
               depiction: {...drawn().depiction, inchikey: 'ZZZZZZZZZZZZZZ-YYYYYYYYYY-N'}};
  const html = structureCard(row);
  const links = html.match(/pubchem[^"]*inchikey[^"]*/gi) || [];
  assert.equal(links.length, 1, 'one card must not offer two PubChem links for two compounds');
  assert.match(html, /AAAAAAAAAAAAAA-BBBBBBBBBB-N/);
  assert.match(html, /InChIKey 불일치/, 'the disagreement is shown as a disagreement');
  assert.match(html, /ZZZZZZZZZZZZZZ-YYYYYYYYYY-N/, 'the computed value is kept, not hidden');
});

test('A computed InChIKey is used only when the record has none, and says so', () => {
  const html = structureCard(drawn());
  assert.match(html, /저장된 구조 문자열에서 계산/);
  assert.match(html, /RJKFOVLPORLFTN-LEKSSAKUSA-N/);
  assert.doesNotMatch(html, /InChIKey 불일치/);
});
