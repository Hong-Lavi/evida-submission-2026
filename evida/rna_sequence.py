"""Versioned RNA sequence inputs and actual ViennaRNA feature calculations.

Unmodified sequence features and exact complementarity are separate from
efficacy, nuclease stability, immune activation and tissue delivery.
"""
import hashlib
import json
import math
import re
import urllib.parse

from .science import fetch


def retrieve_reference(arguments):
    accession = arguments['ensembl_id']
    if not isinstance(accession, str) or not re.fullmatch(r'ENS[A-Z]*[GT][0-9]{11}(?:\.[0-9]+)?', accession):
        raise ValueError('확인한 Ensembl 유전자 또는 전사체 ID를 입력해 주세요.')
    # A version must be verified, never stripped and silently replaced.
    plain, _, requested_version = accession.partition('.')
    raw, source = fetch('https://rest.ensembl.org/lookup/id/' + urllib.parse.quote(plain) + '?expand=1;content-type=application/json')
    metadata = json.loads(raw)
    if metadata.get('id') != plain:
        raise ValueError('수신한 Ensembl ID가 요청과 다릅니다.')
    if requested_version and str(metadata.get('version')) != requested_version:
        raise ValueError('요청한 서열 버전과 현재 Ensembl 버전이 다릅니다. 원 버전 자료가 필요합니다.')
    if metadata.get('object_type') == 'Gene':
        rows = [{'transcript_id': t['id'], 'version': t.get('version'), 'display_name': t.get('display_name'),
                 'biotype': t.get('biotype'), 'canonical_annotation': bool(t.get('is_canonical')),
                 'genomic_start': t.get('start'), 'genomic_end': t.get('end'), 'strand': t.get('strand')}
                for t in metadata.get('Transcript', [])]
        return {'status': 'succeeded', 'semantic_type': 'transcript_identifier_candidates', 'source': source,
                'metadata_response': metadata, 'rows': rows,
                'summary': {'gene_id': plain, 'organism': metadata.get('species'), 'assembly': metadata.get('assembly_name'),
                            'transcripts': len(rows), 'requires_transcript_selection': True},
                'limits': ['유전자에 대응하는 현재 주석 전사체 목록입니다. canonical은 해당 조직에서 우세한 isoform이라는 뜻이 아닙니다.',
                           '질문과 조직/실험에 맞는 전사체 및 버전을 선택해야 서열 계산을 실행합니다.']}
    if metadata.get('object_type') != 'Transcript':
        raise ValueError('유전자 또는 전사체 레코드가 필요합니다.')
    raw_sequence, sequence_source = fetch('https://rest.ensembl.org/sequence/id/' + urllib.parse.quote(plain) + '?type=cdna;content-type=application/json')
    body = json.loads(raw_sequence)
    sequence = str(body.get('seq', '')).upper().replace('T', 'U')
    if not sequence or not re.fullmatch('[ACGUN]+', sequence) or len(sequence) > 50000:
        raise ValueError('현재 계산 범위의 유효한 cDNA 서열을 확인할 수 없습니다.')
    if body.get('id', '').split('.')[0] != plain or str(body.get('version')) != str(metadata.get('version')):
        raise ValueError('주석과 서열의 전사체 ID가 다릅니다.')
    # REST release is recorded at retrieval time. Exact original DNA and RNA
    # normalization are both preserved so later release changes are detectable.
    return {'status': 'succeeded', 'semantic_type': 'versioned_transcript_sequence',
            'source': source, 'sequence_source': sequence_source, 'metadata_response': metadata,
            'sequence_response': body, 'sequence_5to3': sequence,
            'reference': {'transcript_id': plain, 'version': metadata.get('version'), 'gene_id': metadata.get('Parent'),
                          'organism': metadata.get('species'), 'assembly': metadata.get('assembly_name'),
                          'sequence_type': 'spliced_cdna', 'sequence_sha256': hashlib.sha256(sequence.encode()).hexdigest(),
                          'dna_to_rna_normalization': 'T converted to U; original sequence_response retained'},
            'rows': [{'start_1_based': i + 1, 'end_1_based': min(i + 1000, len(sequence)), 'sequence_5to3': sequence[i:i + 1000]}
                     for i in range(0, len(sequence), 1000)],
            'summary': {'length': len(sequence), 'unknown_bases': sequence.count('N'), 'requires_transcript_selection': False},
            'limits': ['현재 공개 주석의 spliced cDNA이며 조직별 isoform 발현을 측정한 결과가 아닙니다.',
                       '새 버전이 과거 실험 참조를 자동 대체하지 않습니다. 화학 수식과 투여/전달 조건은 별도 입력입니다.']}


def sequence(value, minimum=1, maximum=50000):
    if not isinstance(value, str):
        raise ValueError('5′→3′ 서열 문자열이 필요합니다.')
    normalized = value.upper().replace('T', 'U')
    if not minimum <= len(normalized) <= maximum or not re.fullmatch('[ACGU]+', normalized):
        raise ValueError('길이 범위 안의 A/C/G/U(T) 서열만 지원합니다. 미확인 염기·수식 기호를 자동 삭제하지 않습니다.')
    return normalized


def reverse_complement(value):
    return value.translate(str.maketrans('ACGU', 'UGCA'))[::-1]


def evaluate(reference, candidates, chemistry, temperature=37.0):
    import RNA
    if reference.get('semantic_type') != 'versioned_transcript_sequence':
        raise ValueError('실제 서열이 있는 전사체를 먼저 선택해 주세요.')
    target = reference['sequence_5to3']
    if hashlib.sha256(target.encode()).hexdigest() != reference['reference']['sequence_sha256']:
        raise ValueError('참조 서열의 해시가 다릅니다.')
    if 'N' in target:
        raise ValueError('참조에 미확인 염기가 있습니다. 임의로 채워 접근성을 계산하지 않습니다.')
    if chemistry not in ('unmodified', 'modified', 'unknown'):
        raise ValueError('수식 상태를 표시해 주세요.')
    if not candidates or len(candidates) > 100 or len({c['id'] for c in candidates}) != len(candidates):
        raise ValueError('중복 없는 후보 1–100개가 필요합니다.')
    # pfl_fold_up deliberately uses the documented default 37°C model. Other
    # conditions need a separately validated probs_window configuration.
    if temperature != 37.0:
        raise ValueError('현재 접근성 계산은 ViennaRNA 기본 37°C 조건만 지원합니다.')
    normalized = [{**c, 'guide_5to3': sequence(c['guide_5to3'], 19, 30)} for c in candidates]
    max_length = max(len(c['guide_5to3']) for c in normalized)
    window = min(150, len(target)); span = min(100, window)
    if window < max_length:
        raise ValueError('전사체 길이가 가이드보다 짧습니다.')
    up = RNA.pfl_fold_up(target, max_length, window, span)
    rows = []
    for candidate in normalized:
        guide = candidate['guide_5to3']; site = reverse_complement(guide)
        sites, cursor = [], 0
        while True:
            index = target.find(site, cursor)
            if index < 0:
                break
            # The 2.7.2 wrapper doc says start, but the actual matrix uses
            # one-based END. Verified against constrained partition functions
            # in test_rna_sequence.py, including the first transcript window.
            probability = float(up[index + len(guide)][len(guide)])
            opening = -0.00198720425864083 * 310.15 * math.log(probability) if probability > 0 else None
            duplex = RNA.duplexfold(guide, site)
            sites.append({'start_1_based': index + 1, 'end_1_based': index + len(guide),
                          'target_site_5to3': site, 'unpaired_probability': probability,
                          'opening_free_energy_kcal_mol': opening,
                          'duplex_minimum_energy_kcal_mol': float(duplex.energy),
                          'duplex_structure': duplex.structure})
            cursor = index + 1
        structure, mfe = RNA.fold(guide)
        seed = guide[1:8]
        seed_target = reverse_complement(seed)
        seed_positions = [i + 1 for i in range(len(target) - len(seed_target) + 1) if target[i:i + len(seed_target)] == seed_target]
        rows.append({**candidate, 'chemistry': chemistry,
                     'calculation_scope': 'unmodified_RNA_model' if chemistry == 'unmodified' else 'unmodified_sequence_surrogate_only',
                     'length': len(guide), 'gc_fraction': sum(b in 'GC' for b in guide) / len(guide),
                     'guide_mfe_kcal_mol': float(mfe), 'guide_mfe_structure': structure,
                     'perfect_complementary_sites': sites, 'perfect_match_count': len(sites),
                     'seed_guide_positions_2_to_8_5to3': seed, 'seed_target_word_5to3': seed_target,
                     'seed_matches_in_selected_transcript': seed_positions,
                     'efficacy_prediction': None, 'transcriptome_offtarget_assessment': 'not_performed',
                     'delivery_prediction': None, 'nuclease_stability_prediction': None})
    return {'status': 'succeeded', 'semantic_type': 'rna_sequence_thermodynamics_and_exact_mapping',
            'reference': reference['reference'], 'source': reference['sequence_source'], 'rows': rows,
            'protocol': {'method': 'ViennaRNA RNAfold, duplexfold and pfl_fold_up; exact string complementarity',
                         'version': RNA.__version__, 'temperature_celsius': 37, 'window_size': window,
                         'maximum_base_pair_span': span, 'unpaired_coordinate': '1-based end (implementation verified; documentation discrepancy)',
                         'chemistry': chemistry, 'unsupported_modifications': chemistry != 'unmodified',
                         'sequence_direction': 'all input guides 5-prime to 3-prime, target word reverse complement'},
            'summary': {'candidates': len(rows), 'with_exact_target_match': sum(bool(r['perfect_match_count']) for r in rows),
                        'target_sequence_length': len(target)},
            'limits': ['실제 계산한 무수식 RNA 열역학·정확 상보성입니다. 효능·분해 안정성·면역자극·전달의 점수가 아닙니다.',
                       '접근성은 기록한 국소 window/span의 평형 모형입니다. 단백질·세포 환경과 장거리 접힘을 모두 표현하지 않습니다.',
                       '선택한 전사체 내 seed 일치만 계산했습니다. 전사체 전체의 비표적 검토는 별도 참조와 도구가 필요합니다.',
                       '완전 일치가 없으면 가닥 방향·서열/isoform·종·버전·변이와 overhang을 확인합니다. 효과가 없다는 실험 결과가 아닙니다.',
                       '수식이 있거나 미확인이면 무수식 서열 대리 계산으로만 표시하며 실제 화학 수식의 거동으로 해석하지 않습니다.']}


def generate(reference, arguments):
    target = reference.get('sequence_5to3', '')
    start, count, length, stride = (arguments[k] for k in ('start_1_based', 'count', 'paired_length', 'stride'))
    if any(type(x) is not int for x in (start, count, length, stride)) or not (1 <= start and 1 <= count <= 100 and 19 <= length <= 23 and 1 <= stride <= 1000):
        raise ValueError('후보 구간·개수·길이·간격을 확인해 주세요.')
    positions = list(range(start - 1, start - 1 + count * stride, stride))
    if not target or positions[-1] + length > len(target):
        raise ValueError('요청한 후보 구간이 실제 전사체 서열 밖입니다.')
    candidates = [{'id': f"{reference['reference']['transcript_id']}:{i + 1}-{i + length}",
                   'guide_5to3': reverse_complement(sequence(target[i:i + length], length, length)),
                   'origin': 'computed_reverse_complement_of_selected_transcript_window',
                   'target_start_1_based': i + 1} for i in positions]
    result = evaluate(reference, candidates, arguments['chemistry'])
    result['generation'] = {'strategy': 'specified transcript windows; no efficacy ranking', 'paired_region_only': True,
                            'start_1_based': start, 'count': count, 'paired_length': length, 'stride': stride,
                            'unexamined_windows_enumerated': False,
                            'generated_start_positions_1_based': [i+1 for i in positions],
                            'remaining_windows_not_generated': max(0,len(target)-length+1)-count,
                            'total_possible_windows': max(0, len(target) - length + 1),
                            'not_designed': ['overhangs', 'passenger strand chemistry', 'modification pattern', 'delivery formulation']}
    return result
