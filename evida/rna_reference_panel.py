"""Compare retained guides across explicit, versioned transcript references.

Exact complementarity is an observable sequence property, not knockdown or
isoform expression. Nonmatching and ambiguous references remain in the output.
"""
import hashlib
import re

from .rna_sequence import reverse_complement, sequence


def compare(result, references, candidate_ids):
    if result.get('semantic_type') != 'rna_sequence_thermodynamics_and_exact_mapping':
        raise ValueError('완료한 RNA 후보 계산을 선택해 주세요.')
    if not candidate_ids or len(candidate_ids) > 100 or len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError('중복 없는 후보 1–100개를 선택해 주세요.')
    candidates = {row['id']: row for row in result['rows']}
    if not set(candidate_ids) <= candidates.keys():
        raise ValueError('원 계산에 없는 후보입니다.')
    if not references or len(references) > 100:
        raise ValueError('서열이 확인된 전사체 참조 1–100개를 선택해 주세요.')
    if sum(len(r.get('sequence_5to3','')) for _,r in references)*len(candidate_ids)>5000000:
        raise ValueError('한 번의 서열 대조량을 초과했습니다. 후보나 참조를 나누어 계산하세요. 나머지 선택지는 제외되지 않습니다.')
    source_ref = result['reference']
    original_gene = (source_ref.get('gene_id') or '').split('.')[0]
    if not original_gene or not source_ref.get('organism') or not source_ref.get('assembly'):
        raise ValueError('원 후보의 유전자·종·assembly를 확인해 주세요.')
    seen, panel, rows = {}, [], []
    for artifact_id, reference in references:
        if reference.get('semantic_type') != 'versioned_transcript_sequence':
            raise ValueError('isoform 목록 대신 실제 서열이 있는 전사체를 선택해 주세요.')
        meta = reference['reference']
        target = reference['sequence_5to3']
        annotation_biotype = (reference.get('metadata_response') or {}).get('biotype')
        if not annotation_biotype:
            header = (reference.get('sequence_response') or {}).get('original_header','')
            match = re.search(r'(?:^|\s)transcript_biotype:([^\s]+)',header)
            annotation_biotype = match.group(1) if match else None
        if (not re.fullmatch('[ACGUN]+', target) or len(target) > 50000
                or hashlib.sha256(target.encode()).hexdigest() != meta['sequence_sha256']):
            raise ValueError('참조 서열의 형식·범위·해시를 확인해 주세요.')
        if (meta.get('organism') != source_ref['organism']
                or meta.get('assembly') != source_ref['assembly']
                or (meta.get('gene_id') or '').split('.')[0] != original_gene):
            raise ValueError('이 표적 isoform 비교에는 같은 유전자·종·assembly가 필요합니다. 다른 표적은 별도 비표적 분석으로 검토해 주세요.')
        identity = (meta['transcript_id'], meta['version'])
        if identity in seen:
            raise ValueError('같은 전사체 버전이 중복됐습니다. 서로 다른 서열이면 원자료 대응을 먼저 확인해 주세요.')
        seen[identity] = meta['sequence_sha256']
        panel.append({'artifact_id': artifact_id, **meta, 'annotation_biotype':annotation_biotype, 'length': len(target),
                      'unknown_bases': target.count('N'), 'source': reference.get('sequence_source')})
        for cid in candidate_ids:
            guide = sequence(candidates[cid]['guide_5to3'], 19, 30)
            word = reverse_complement(guide)
            positions, ambiguous, minimum = [], 0, None
            for start in range(max(0, len(target)-len(word)+1)):
                window = target[start:start+len(word)]
                if 'N' in window:
                    ambiguous += 1
                    continue
                mismatches = sum(a != b for a, b in zip(window, word))
                minimum = mismatches if minimum is None else min(minimum, mismatches)
                if mismatches == 0:
                    positions.append({'start_1_based': start+1, 'end_1_based': start+len(word)})
            status = 'exact_site_present' if positions else 'unresolved_unknown_bases' if ambiguous else 'no_exact_site'
            rows.append({'candidate_id': cid, 'guide_5to3': guide,
                'target_word_5to3': word, 'reference_artifact_id': artifact_id,
                'transcript_id': meta['transcript_id'], 'version': meta['version'],
                'annotation_biotype': annotation_biotype,
                'sequence_sha256': meta['sequence_sha256'], 'reference_length': len(target),
                'exact_sites': positions, 'exact_match_count': len(positions), 'match_status': status,
                'minimum_gapless_mismatches_known_windows': minimum,
                'unknown_windows': ambiguous, 'chemistry': candidates[cid].get('chemistry'),
                'knockdown_prediction': None, 'tissue_expression': 'not_measured'})
    summary_rows = [{'candidate_id': cid, 'references_with_exact_site': sum(bool(r['exact_sites']) for r in rows if r['candidate_id']==cid),
        'references_without_exact_site': sum(r['match_status']=='no_exact_site' for r in rows if r['candidate_id']==cid),
        'references_unresolved': sum(r['match_status']=='unresolved_unknown_bases' for r in rows if r['candidate_id']==cid),
        'references_with_unknown_windows': sum(r['unknown_windows']>0 for r in rows if r['candidate_id']==cid)} for cid in candidate_ids]
    return {'status': 'succeeded', 'semantic_type': 'selected_transcript_exact_complementarity_panel',
        'reference': source_ref, 'reference_panel': panel, 'rows': rows, 'candidate_summary': summary_rows,
        'summary': {'gene_id': original_gene, 'selected_candidates':len(candidate_ids), 'selected_references':len(panel),
                    'comparison_rows':len(rows), 'all_gene_isoforms_claimed':False,
                    'scope':'Only the explicitly selected versioned transcripts. Unselected/unretrieved isoforms remain unknown.'},
        'protocol': {'sequence_direction':'guide5to3 against its reverse-complement target word5to3',
                     'coordinates':'1-based inclusive transcript coordinates', 'mismatch_method':'gapless Hamming distance over known-base windows; no bulge/indel or cleavage model',
                     'reference_identity':'same gene/species/assembly, each transcript version and source hash preserved'},
        'limits':['선택한 전사체 서열의 정확 상보성입니다. 조직에서 그 isoform이 발현되거나 억제된다는 측정이 아닙니다.',
                  '완전 일치 부위가 없어도 생물학적 효과가 없다고 판정하지 않습니다. 불일치 수는 gap 없는 서열 거리이며 효능·절단 점수가 아닙니다.',
                  'N이 있는 창은 비교 미확정으로 보존합니다. 계산하지 않은 isoform·변이·미주석 전사체는 배제되지 않았습니다.',
                  'guide/passenger, 실제 수식·전달, 단백질 감소·기능은 별도 조건과 관측으로 확인합니다.']}
