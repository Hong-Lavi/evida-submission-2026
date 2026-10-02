"""Explicit proposed duplex identities and separate strand-specific calculations.

The unmodified fixed-structure calculation is a conditional feature, never an
Ago loading, toxicity, stability, delivery or therapeutic efficacy prediction.
"""
import hashlib
import json
import math
import re

from .rna_resources import candidate_rows


def rc(value):
    if not isinstance(value, str) or not re.fullmatch('[ACGU]+', value):
        raise ValueError('명시적 RNA A/C/G/U 서열이 필요합니다. DNA·수식 표기를 자동 변환하지 않습니다.')
    return value.translate(str.maketrans('ACGU', 'UGCA'))[::-1]


def fixed_energy(first, second, length):
    import RNA
    rc(first); rc(second)
    if type(length) is not int or not 1 <= length <= min(len(first), len(second)):
        raise ValueError('짝지음 길이를 확인해 주세요.')
    if rc(first[:length]) != second[:length]:
        raise ValueError('이 계산은 명시한 완전 상보 core만 지원합니다. mismatch를 지우지 않습니다.')
    md = RNA.md(); md.temperature = 37.0; md.dangles = 2
    structure = '(' * length + '.' * (len(first)-length) + ')' * length + '.' * (len(second)-length)
    value = float(RNA.fold_compound(first+'&'+second, md).eval_structure(structure))
    if not math.isfinite(value) or abs(value) >= 10000:
        raise ValueError('유효한 고정 구조 에너지를 계산하지 못했습니다.')
    return {'kcal_mol': value, 'structure_without_strand_separator': structure,
            'strand_break_after_1_based': len(first)}


def end_contrasts(guide, passenger):
    rows = []
    for window in (4, 5, 6):
        g = fixed_energy(guide[:window], passenger[-window:], window)['kcal_mol']
        p = fixed_energy(passenger[:window], guide[-window:], window)['kcal_mol']
        rows.append({'paired_window': window, 'guide_5prime_kcal_mol': g,
                     'passenger_5prime_kcal_mol': p, 'guide_minus_passenger_kcal_mol': g-p})
    return rows


def propose(result, arguments):
    import RNA
    candidates = candidate_rows(result, arguments['candidate_ids'])
    if len(candidates)>6:raise ValueError('한 번에1–6개 core를 비교해 주세요. 다른 후보도 보존됩니다.')
    variants = arguments['overhang_variants']
    if not variants or len(set(variants)) != len(variants) or not set(variants) <= {'blunt', 'UU'}:
        raise ValueError('서로 다른 blunt 또는 양쪽3′UU 계산안을 선택해 주세요.')
    rows = []
    for old in candidates:
        core = old['guide_5to3']; passenger = rc(core)
        if not 19 <= len(core) <= 30:
            raise ValueError('core 길이는19–30nt여야 합니다.')
        if not old.get('perfect_complementary_sites'):
            raise ValueError('원 참조에 정확히 대응한 core를 선택해 주세요. 부위 불일치를 성공으로 처리하지 않습니다.')
        for variant in variants:
            overhang = '' if variant == 'blunt' else 'UU'
            identity = {'guide_core_5to3': core, 'passenger_core_5to3': passenger,
                'guide_overhang_3prime': overhang, 'passenger_overhang_3prime': overhang,
                'guide_5prime_terminal_state': arguments['guide_5prime_state'],
                'passenger_5prime_terminal_state': arguments['passenger_5prime_state'],
                'chemistry_description': arguments['chemistry_description'].strip() or 'unspecified',
                'formulation_description': arguments['formulation_description'].strip() or 'unspecified'}
            encoded = json.dumps({'identity':identity,'reference':result['reference'],'source_candidate_id':old['id']}, sort_keys=True, separators=(',', ':')).encode()
            contrasts = end_contrasts(core, passenger)
            rows.append({'id': 'duplex_'+hashlib.sha256(encoded).hexdigest()[:24], **identity,
                'source_candidate_id': old['id'], 'source_candidate_artifact_id': arguments['artifact_id'],
                'source_core_chemistry': old.get('chemistry', 'unknown'),
                'source_sites': old['perfect_complementary_sites'], 'reference': result['reference'],
                'guide_5to3': core+overhang, 'passenger_5to3': passenger+overhang,
                'paired_length': len(core), 'overhang_variant': variant,
                'design_status': 'computational_proposal_not_synthesized',
                'fixed_duplex': fixed_energy(core+overhang, passenger+overhang, len(core)),
                'end_window_contrasts': contrasts,
                'guide_minus_passenger_5bp_kcal_mol': contrasts[1]['guide_minus_passenger_kcal_mol'],
                'guide_seed_2to8_5to3': core[1:8], 'passenger_seed_2to8_5to3': passenger[1:8],
                'efficacy_score': None, 'risc_loading_prediction': None,
                'nuclease_stability_prediction': None, 'delivery_prediction': None})
    return {'status': 'succeeded', 'semantic_type': 'explicit_proposed_rna_duplexes',
        'reference': result['reference'], 'rows': rows,
        'summary': {'source_candidates': len(candidates), 'duplex_proposals': len(rows),
                    'synthesized_or_validated': False, 'efficacy_ranking_performed': False},
        'protocol': {'method': 'ViennaRNA fixed-structure evaluation', 'version': RNA.__version__,
            'parameters': 'default Turner2004', 'temperature_celsius': 37, 'dangles': 2,
            'scope': 'unmodified RNA surrogate; specified chemistry and termini are recorded, not parameterized',
            'end_windows': [4, 5, 6], 'end_window_scope': 'isolated paired cores, excluding overhangs and terminal chemistry',
            'delta_convention': 'guide5prime minus passenger5prime; positive means less stable guide end in this surrogate',
            'author_method_reproduction': False},
        'limits': ['명시적 이중가닥 계산안입니다. 합성·Ago 적재·효능·분해 안정성·전달 성공을 확인한 결과가 아닙니다.',
            '양 가닥은 모두5′→3′입니다. 입력 수식·말단·제형은 그대로 보존하고 무수식 열역학에 반영했다고 주장하지 않습니다.',
            '4/5/6bp 말단 창은 조건 민감도 보기입니다. 부호나 에너지 하나로 가이드/보조 가닥의 세포 내 활성을 확정하지 않습니다.',
            '원 전사체·core의 비표적 결과는 남아 있습니다. 보조 가닥 검토는 별도로 실행하며 두 근거를 안전성 점수로 합하지 않습니다.']}


def strand_inputs(result, ids, strand):
    if result.get('semantic_type') != 'explicit_proposed_rna_duplexes':
        raise ValueError('먼저 이중가닥 계산안을 선택해 주세요.')
    if not ids or len(ids)>12 or len(set(ids))!=len(ids) or strand not in ('guide', 'passenger', 'both'):
        raise ValueError('중복 없는 계산안1–12개와 가닥을 선택해 주세요.')
    selected = [r for r in result['rows'] if r['id'] in ids]
    if {r['id'] for r in selected} != set(ids):
        raise ValueError('계산안 ID가 원 결과에 없습니다.')
    unique, links = {}, []
    for row in selected:
        for role in (('guide', 'passenger') if strand == 'both' else (strand,)):
            core = row[role+'_core_5to3']; rc(core)
            # Only seed2–8 defines this scan. Different overhangs or contexts
            # share the calculation but retain distinct provenance links.
            key = core[1:8]
            sid = 'seed_'+hashlib.sha256(key.encode()).hexdigest()[:20]
            unique.setdefault(sid, {'id': sid, 'guide_5to3': core})
            links.append({'duplex_id': row['id'], 'source_candidate_id': row['source_candidate_id'],
                'strand_role': role, 'strand_5to3': row[role+'_5to3'], 'seed_2to8_5to3': key,
                'calculation_id': sid})
    return list(unique.values()), links


def scan_strands(result, arguments, work):
    from .rna_seed_sites import analyze
    guides, links = strand_inputs(result, arguments['duplex_ids'], arguments['strand'])
    proxy = {'semantic_type': 'rna_sequence_thermodynamics_and_exact_mapping',
             'reference': result['reference'], 'rows': guides}
    output = analyze(proxy, {'candidate_ids': [r['id'] for r in guides]}, work)
    output['semantic_type'] = 'explicit_duplex_strand_3utr_seed_sites_not_risk'
    output['strand_links'] = links
    output['summary'].update(duplexes=len(arguments['duplex_ids']), strand=arguments['strand'],
                             unique_seed_calculations=len(guides), strand_context_links=len(links))
    output['protocol']['strand_identity'] = 'candidate_id is a seed calculation ID; strand_links preserves role and every full duplex sequence'
    output['protocol']['duplicate_policy'] = 'same seed2–8 searched once; no duplicate evidence for overhang variants'
    output['limits'][-1] = '本 계산은 지정한 가닥의 seed 위치 검색입니다. 어느 가닥이 실제로 적재되는지·억제/독성·화학 수식·전달은 미측정입니다.'.replace('本', '이')
    output['limits'].append('guide_5to3는 기존 검색기의 입력 필드명입니다. 실제 가닥 역할은 strand_links를 따릅니다. 가이드·보조 가닥 점수를 합산하지 않습니다.')
    return output


def full_strand_inputs(result, ids, strand):
    # Reuse the validated selection contract, but long interactions depend on
    # the entire literal strand, including overhangs, rather than seed2–8.
    _, seed_links = strand_inputs(result, ids, strand)
    queries, links = {}, []
    for source in seed_links:
        sequence = source['strand_5to3']
        rc(sequence)
        if not 19 <= len(sequence) <= 30:
            raise ValueError('전체 가닥 길이는 현재 검색기의19–30nt 범위여야 합니다.')
        identifier = 'strand_' + hashlib.sha256(sequence.encode()).hexdigest()[:20]
        queries.setdefault(identifier, {'id': identifier, 'guide_5to3': sequence})
        links.append({**source, 'calculation_id': identifier})
    if len(queries) > 12:
        raise ValueError('서로 다른 전체 가닥은 한 번에12개까지 검색합니다. 설계안을 나눠 선택해 주세요. 기존 결과는 보존됩니다.')
    return list(queries.values()), links


def scan_full_strands(result, arguments, work):
    from .rna_resources import search_offtargets
    queries, links = full_strand_inputs(result, arguments['duplex_ids'], arguments['strand'])
    proxy = {'semantic_type': 'rna_sequence_thermodynamics_and_exact_mapping',
             'reference': result['reference'], 'rows': queries}
    output = search_offtargets(proxy, {
        'candidate_ids': [row['id'] for row in queries],
        'energy_cutoff_kcal_mol': arguments['energy_cutoff_kcal_mol'],
    }, work)
    output['semantic_type'] = 'explicit_duplex_strand_transcriptome_interactions_not_risk'
    output['strand_links'] = links
    output['summary'].update(duplexes=len(arguments['duplex_ids']), strand=arguments['strand'],
                             unique_full_strand_calculations=len(queries), strand_context_links=len(links))
    output['protocol']['strand_identity'] = 'Exact full5to3 sequence, including declared overhang. Same sequence reused with every duplex/role link retained.'
    output['protocol']['chemistry'] = 'Unmodified sequence energy only; declared chemistry/termini are not parameterized.'
    output['limits'].append('guide_5to3는 검색기의 필드명입니다. 실제 가이드·보조 가닥 역할은 strand_links로 구분하며, 긴 상보성과 짧은seed를 안전성 점수로 합하지 않습니다.')
    return output
