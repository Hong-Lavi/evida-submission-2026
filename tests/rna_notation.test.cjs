// A written oligonucleotide must say what it is, and must not say what was never recorded.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const context = vm.createContext({
  esc: s => String(s).replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])),
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/rna-notation.js'), 'utf8'), context);
const {rnaNotation, rnaNotationText, rnaNotationLegend, rnaDeliveryLine} = context;

const design = [{strand: 'guide', position_1_based: 1, chemistry: '2-O-Methyl'},
                {strand: 'guide', position_1_based: 2, chemistry: '2-Fluoro'},
                {strand: 'passenger', position_1_based: 1, chemistry: '2-Deoxy'}];

test('The recorded chemistry is written on the position it was recorded for', () => {
  const text = rnaNotationText('AUGCA', {strand: 'guide', modifications: design});
  assert.equal(text, '5′-mAfUGCA-3′');
});

test('A modification recorded for the other strand is not applied to this one', () => {
  assert.equal(rnaNotationText('AUGCA', {strand: 'passenger', modifications: design}),
               '5′-dAUGCA-3′');
});

test('Direction is always written, so a reversed sequence cannot be read as the same design', () => {
  assert.match(rnaNotationText('AUGC', {}), /^5′-/);
  assert.match(rnaNotationText('AUGC', {}), /-3′$/);
});

test('A phosphorothioate linkage is written between the residues it joins', () => {
  assert.equal(rnaNotationText('AUGC', {phosphorothioate_linkages: [1, 2]}), '5′-AsUsGC-3′');
});

test('No modification record is stated as no record, never as unmodified', () => {
  const html = rnaNotation('AUGC', {});
  assert.match(html, /수식 기록이 없습니다/);
  assert.match(html, /무수식이라는 뜻은 아닙니다/);
  assert.doesNotMatch(html, /수식 없음으로 기록된/);
});

test('A sequence recorded as unmodified says exactly that', () => {
  assert.match(rnaNotation('AUGC', {core_chemistry: 'unmodified'}), /수식 없음으로 기록된 서열/);
});

test('The legend lists only the codes actually used', () => {
  const legend = rnaNotationLegend(design);
  assert.match(legend, /2′-O-메틸/);
  assert.match(legend, /2′-플루오로/);
  assert.match(legend, /2′-데옥시/);
  assert.doesNotMatch(legend, /메톡시에틸/, 'a code nothing uses is noise in a legend');
  assert.equal(rnaNotationLegend([]), '');
});

test('An empty or unrecorded sequence does not draw an empty box', () => {
  assert.match(rnaNotation('', {}), /서열 기록이 없습니다/);
  assert.equal(rnaNotationText(undefined, {}), '');
});

test('The length shown is the length of the sequence', () => {
  const html = rnaNotation('AUGCAUGCAUGCAUGCAUG', {strand: 'guide', modifications: design});
  assert.match(html, /19nt/);
  assert.match(html, /2\/19개 위치에 기록된 수식/);
});

test('Delivery conditions are shown, and an unrecorded formulation says so', () => {
  assert.match(rnaDeliveryLine({source_core_chemistry: 'unknown'}), /원 수식 미확인/);
  assert.match(rnaDeliveryLine({}), /제형 기록 없음/);
  assert.match(rnaDeliveryLine({formulation_description: 'GalNAc 접합'}), /GalNAc 접합/);
});

test('A string that is not a sequence is refused, not silently rewritten', () => {
  // Keeping only the letters it knows would turn this into AUCTGC - a different oligonucleotide.
  assert.equal(rnaNotationText('AU<script>GC', {}), '');
  assert.match(rnaNotation('AU<script>GC', {}), /읽을 수 없습니다/);
  assert.doesNotMatch(rnaNotation('AU<script>GC', {}), /<script>/);
  assert.equal(rnaNotationText(' AUGC\n', {}), '5′-AUGC-3′', 'whitespace is layout, not content');
});
