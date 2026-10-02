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
