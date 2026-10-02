"""All known-base windows of explicit references, before candidate evaluation.

Sequence identity unifies origins, not experimental observations. Existing
candidate IDs/results remain separate, linked records. Enumeration is unranked.
"""
import hashlib
import re

from .rna_sequence import evaluate, reverse_complement


def enumerate_space(references, paired_length, prior_results=()):
    if type(paired_length) is not int or not 19 <= paired_length <= 30:
        raise ValueError('상보 영역 길이는19–30nt 정수로 선택해 주세요.')
    if not references or len(references) > 100:
        raise ValueError('실제 서열이 있는 전사체1–100개를 선택해 주세요.')
    if sum(len(r.get('sequence_5to3', '')) for _, r in references) > 300000:
        raise ValueError('선택한 참조가 한 번의 열거 범위를 넘습니다. 참조를 나누어 실행하세요. 나머지 참조는 제외되지 않습니다.')
    seen, scope, pool, reference_rows = set(), None, {}, []
    total_windows = unknown_windows = origins = 0
    for aid, reference in references:
        if reference.get('semantic_type') != 'versioned_transcript_sequence':
            raise ValueError('전사체 목록 대신 실제 서열을 선택해 주세요.')
        meta = reference['reference']
        target = reference['sequence_5to3']
        if (not isinstance(target, str) or not re.fullmatch('[ACGUN]+', target)
                or len(target) > 50000 or hashlib.sha256(target.encode()).hexdigest() != meta['sequence_sha256']):
            raise ValueError('참조의 실제 서열·해시·길이를 확인해 주세요.')
        current_scope = ((meta.get('gene_id') or '').split('.')[0], meta.get('organism'), meta.get('assembly'))
        if not all(current_scope) or (scope is not None and scope != current_scope):
            raise ValueError('같은 유전자·종·assembly의 전사체만 함께 열거할 수 있습니다.')
        scope = current_scope
        identity = (meta.get('transcript_id'), meta.get('version'))
        if not all(v is not None and v != '' for v in identity) or identity in seen:
            raise ValueError('중복 없는 명시적 전사체 버전이 필요합니다.')
        seen.add(identity)
        known = skipped = 0
        for start in range(max(0, len(target) - paired_length + 1)):
            total_windows += 1
            word = target[start:start + paired_length]
            if 'N' in word:
                unknown_windows += 1
                skipped += 1
                continue
            guide = reverse_complement(word)
            cid = 'guide_' + hashlib.sha256(guide.encode()).hexdigest()[:20]
            row = pool.setdefault(guide, {'id': cid, 'guide_5to3': guide,
                'target_word_5to3': word, 'length': paired_length, 'origins': [],
                'prior_evaluations': [], 'assessment_status': 'sequence_enumerated_only',
                'efficacy_prediction': None, 'tissue_expression': 'not_measured',
                'genomic_mapping': 'not_attached_to_this_product_result'})
            row['origins'].append({'reference_artifact_id': aid, 'transcript_id': identity[0],
                'version': identity[1], 'sequence_sha256': meta['sequence_sha256'],
                'start_1_based': start + 1, 'end_1_based': start + paired_length})
            known += 1
            origins += 1
        reference_rows.append({'artifact_id': aid, **meta, 'length': len(target),
            'possible_windows': max(0, len(target) - paired_length + 1),
            'known_base_windows': known, 'unknown_base_windows': skipped,
            'sequence_source': reference.get('sequence_source')})
    rows = list(pool.values())
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('후보 식별자 충돌입니다. 원 서열을 유지하고 확인해 주세요.')
    prior_links = []
    for aid, result in prior_results:
        if result.get('semantic_type') != 'rna_sequence_thermodynamics_and_exact_mapping':
            raise ValueError('이전 평가 연결에는 실제 가이드 계산 결과가 필요합니다.')
        for old in result['rows']:
            guide = old.get('guide_5to3')
            link = {'artifact_id': aid, 'candidate_id': old['id'],
                'guide_5to3': guide, 'source_reference': result.get('reference'),
                'chemistry': old.get('chemistry'), 'in_selected_sequence_space': guide in pool}
            prior_links.append(link)
            if guide in pool:
                pool[guide]['prior_evaluations'].append(link)
    return {'status': 'succeeded', 'semantic_type': 'retained_versioned_rna_candidate_space',
        'reference_panel': reference_rows, 'rows': rows, 'prior_candidate_links': prior_links,
        'summary': {'gene_id': scope[0], 'organism': scope[1], 'assembly': scope[2],
            'selected_references': len(references), 'paired_length': paired_length,
            'possible_windows': total_windows, 'known_base_origins': origins,
            'unknown_base_windows': unknown_windows, 'unique_guide_sequences': len(rows),
            'previous_evaluation_links': len(prior_links),
            'previous_candidates_outside_selected_space': sum(not x['in_selected_sequence_space'] for x in prior_links),
            'ranking_performed': False, 'all_gene_isoforms_claimed': False},
        'protocol': {'coordinates': '1-based inclusive spliced transcript coordinates',
            'generation': 'every window in the explicit references; no stride, top-k or GC filter',
            'identity': 'same guide sequence unifies all origins; evaluation IDs and contexts remain separate',
            'row_order': 'first encountered reference/position; not an efficacy ranking'},
        'limits': ['선택한 버전별 참조에서 가능한 상보 영역을 열거했습니다. 효능 순위·완성 siRNA 설계가 아닙니다.',
            '같은 가이드 서열의 모든 출처와 이전 평가를 연결하되 조건이 다른 관측을 독립 증거로 합산하지 않습니다.',
            'N이 포함된 창은 미확정으로 집계합니다. 선택 밖 isoform·변이·미주석 전사체는 미검색입니다.',
            '조직 발현·수식·전달·RISC·비표적은 별도 검토 대상이며 이 결과에는 genomic exon 대응을 첨부하지 않았습니다.'],
    }


def select_and_evaluate(space, reference_id, reference, candidate_ids, chemistry, reason):
    if space.get('semantic_type') != 'retained_versioned_rna_candidate_space':
        raise ValueError('전체 후보를 보존한 RNA 후보 공간이 필요합니다.')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('후보를 선택한 이유를 남겨 주세요.')
    if not candidate_ids or len(candidate_ids) > 12 or len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError('중복 없는 후보1–12개를 선택해 주세요. 전체 후보 공간은 보존됩니다.')
    saved_ref = next((r for r in space['reference_panel'] if r['artifact_id'] == reference_id), None)
    if not saved_ref or any(saved_ref.get(k) != reference['reference'].get(k)
                            for k in ('transcript_id', 'version', 'sequence_sha256', 'assembly', 'organism', 'gene_id')):
        raise ValueError('후보 열거에 사용한 정확한 참조·버전·해시를 선택해 주세요.')
    by_id = {r['id']: r for r in space['rows']}
    if not set(candidate_ids) <= by_id.keys():
        raise ValueError('보존된 후보 공간에 없는 후보입니다.')
    chosen = [by_id[cid] for cid in candidate_ids]
    for row in chosen:
        word = reverse_complement(row['guide_5to3'])
        matching = [o for o in row['origins'] if o['reference_artifact_id'] == reference_id]
        if not matching or any(reference['sequence_5to3'][o['start_1_based'] - 1:o['end_1_based']] != word for o in matching):
            raise ValueError('선택 참조와 후보의 실제 출처 구간이 일치하지 않습니다.')
    result = evaluate(reference, [{'id': r['id'], 'guide_5to3': r['guide_5to3']} for r in chosen], chemistry)
    result['selection'] = {'reason': reason.strip(), 'reference_artifact_id': reference_id,
        'selected_candidate_ids': candidate_ids, 'source_pool_summary': space['summary'],
        'origins_and_prior_evaluations': [{k: r[k] for k in ('id', 'origins', 'prior_evaluations')} for r in chosen],
        'unselected_candidates_preserved': True, 'selection_is_validation': False}
    return result


def filtered_rows(space, query):
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError('검색어는200자 이내로 입력해 주세요.')
    query = query.strip().lower()
    if not query:
        return space['rows']
    def matches(row):
        fields = [row['id'], row['guide_5to3'], row['target_word_5to3']]
        fields += [x['candidate_id'] for x in row['prior_evaluations']]
        fields += [o.get('annotated_region','') for o in row['origins']]
        fields += [f"{o['transcript_id']}.{o['version']}:{o['start_1_based']}-{o['end_1_based']}" for o in row['origins']]
        # Researchers often paste a transcript/location without its version.
        # Match that address too; return original versioned origins unchanged.
        fields += [f"{o['transcript_id']}:{o['start_1_based']}-{o['end_1_based']}" for o in row['origins']]
        return any(query in x.lower() for x in fields)
    return [r for r in space['rows'] if matches(r)]
