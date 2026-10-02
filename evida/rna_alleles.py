"""Frozen exon coordinates, live public variants and separate allele scenarios.

Genomic REF and transcript orientation must agree before an edit. Scenario
sequences never become archived references or patient genotype observations.
"""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re

from .rna_context import public_json
from .rna_sequence import reverse_complement, sequence


def reference_geometry(reference, config):
    if reference.get('semantic_type') != 'versioned_transcript_sequence':
        raise ValueError('실제 전사체 서열을 선택해 주세요.')
    meta, target = reference['reference'], reference['sequence_5to3']
    if (meta.get('assembly') != 'GRCh38' or meta.get('organism') != 'homo_sapiens'
            or not re.fullmatch('[ACGUN]+', target) or len(target) > 50000
            or hashlib.sha256(target.encode()).hexdigest() != meta['sequence_sha256']):
        raise ValueError('인간 GRCh38 실제 참조 서열·해시·범위를 확인해 주세요.')
    gtf = config['genomic_annotation']
    with Path(gtf['path']).open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != gtf['sha256']:
            raise ValueError('보존 GTF의 해시가 달라졌습니다.')
    tid = meta['transcript_id']
    exons, raw_rows = [], []
    with gzip.open(gtf['path'], 'rt') as handle:
        for line in handle:
            if f'transcript_id "{tid}";' not in line:
                continue
            fields = line.rstrip('\n').split('\t')
            if len(fields) != 9 or fields[2] != 'exon':
                continue
            attrs = dict(re.findall(r'(\w+) "([^"]*)";', fields[8]))
            if str(meta['version']) != attrs.get('transcript_version'):
                continue
            if attrs.get('gene_id') != (meta.get('gene_id') or '').split('.')[0]:
                raise ValueError('GTF와 참조의 유전자가 다릅니다.')
            exons.append({'chromosome': fields[0], 'start': int(fields[3]), 'end': int(fields[4]),
                'strand': fields[6], 'exon_number': int(attrs['exon_number']),
                'exon_id': attrs.get('exon_id'), 'version': attrs.get('exon_version')})
            raw_rows.append(line.rstrip('\n'))
    exons.sort(key=lambda x: x['exon_number'])
    if (not exons or [x['exon_number'] for x in exons] != list(range(1, len(exons)+1))
            or len({(x['chromosome'], x['strand']) for x in exons}) != 1
            or sum(x['end']-x['start']+1 for x in exons) != len(target)):
        raise ValueError('같은 버전의 완전한 exon chain과 cDNA 길이를 확인할 수 없습니다.')
    strand = exons[0]['strand']
    if strand not in ('+', '-'):
        raise ValueError('GTF 가닥을 확인해야 합니다.')
    positions = [g for e in exons for g in (range(e['start'], e['end']+1)
        if strand == '+' else range(e['end'], e['start']-1, -1))]
    if len(set(positions)) != len(positions) or positions != sorted(positions, reverse=strand == '-'):
        raise ValueError('겹치거나 순서가 다른 exon chain은 자동 적용하지 않습니다.')
    return {'reference': meta, 'length': len(target), 'chromosome': exons[0]['chromosome'],
        'strand': strand, 'exons': exons, 'annotation': gtf, 'original_gtf_rows': raw_rows,
        'coordinate_contract': '1-based inclusive; exon order follows transcript5to3',
        'verification': 'exact transcript version/gene/length/hash; genome sequence reconstruction is separate'}


def coordinate_map(geometry):
    return {g: i+1 for i, g in enumerate(g for e in geometry['exons'] for g in
        (range(e['start'], e['end']+1) if geometry['strand'] == '+' else range(e['end'], e['start']-1, -1)))}


def genomic_blocks(geometry, start, end):
    blocks, cursor = [], 1
    for exon in geometry['exons']:
        length = exon['end']-exon['start']+1
        low, high = max(start, cursor), min(end, cursor+length-1)
        if low <= high:
            left, right = ((exon['start']+low-cursor, exon['start']+high-cursor)
                if geometry['strand'] == '+' else (exon['end']-high+cursor, exon['end']-low+cursor))
            blocks.append({'chromosome': geometry['chromosome'], 'start_1_based': left,
                'end_1_based': right, 'strand': geometry['strand'], 'exon_number': exon['exon_number']})
        cursor += length
    if sum(x['end_1_based']-x['start_1_based']+1 for x in blocks) != end-start+1:
        raise ValueError('cDNA 부위가 exon chain 범위를 벗어납니다.')
    return blocks


def oriented_allele(value, variant_strand, transcript_strand):
    text = '' if value == '-' else value.replace('T', 'U')
    if bool(variant_strand == -1) != bool(transcript_strand == '-'):
        text = reverse_complement(text)
    return text


def allele_mapping(variant, geometry, target):
    """Return a half-open transcript edit interval, or an explicit unapplied state."""
    result = {'status': 'not_applied', 'reason': '', 'cdna_start_0_based': None,
        'cdna_end_exclusive': None, 'ref_in_transcript_5to3': None, 'available_alternates': []}
    def reject(reason):
        return {**result, 'reason': reason}
    if (variant.get('assembly_name') != geometry['reference']['assembly']
            or variant.get('seq_region_name') != geometry['chromosome'] or variant.get('strand') not in (-1, 1)):
        return reject('assembly/염색체/가닥 대응 미확인')
    alleles = variant.get('alleles', [])
    if not alleles or not all(isinstance(a, str) for a in alleles):
        return reject('명시적 REF/ALT 없음')
    ref = alleles[0]
    if not re.fullmatch(r'(?:[ACGT]{1,200}|-)', ref):
        return reject('상징적/긴 REF: 별도 정규화와 구조 변이 검토 필요')
    mapping = coordinate_map(geometry)
    start, end = variant.get('start'), variant.get('end')
    if type(start) is not int or type(end) is not int:
        return reject('유전체 위치 미확인')
    if ref == '-':
        same_exon = any(e['start'] <= end < start <= e['end'] for e in geometry['exons'])
        if start != end+1 or start not in mapping or end not in mapping or abs(mapping[start]-mapping[end]) != 1 or not same_exon:
            return reject('삽입 경계가 같은 exon 내부의 인접한 두 염기로 확인되지 않음')
        left = right = min(mapping[start], mapping[end])
    else:
        if end-start+1 != len(ref) or not all(g in mapping for g in range(start, end+1)):
            return reject('exon 밖/경계 교차 또는 REF 길이 불일치: 스플라이싱 영향은 별도 검토')
        positions = sorted(mapping[g] for g in range(start, end+1))
        if positions != list(range(positions[0], positions[-1]+1)):
            return reject('연속된 cDNA 부위로 확인되지 않음')
        left, right = positions[0]-1, positions[-1]
    expected = oriented_allele(ref, variant['strand'], geometry['strand'])
    if target[left:right] != expected:
        return reject('REF가 보존 전사체 서열과 다름: 원 버전/좌표 정규화 확인 필요')
    alternates = [a for a in dict.fromkeys(alleles[1:]) if a != ref and re.fullmatch(r'(?:[ACGT]{1,200}|-)', a)]
    return {**result, 'status': 'ref_verified' if alternates else 'not_applied',
        'reason': '단일 allele 서열 시나리오 가능' if alternates else '지원하는 명시적 ALT 없음',
        'cdna_start_0_based': left, 'cdna_end_exclusive': right,
        'ref_in_transcript_5to3': expected, 'available_alternates': alternates}


def variant_catalog(reference, reference_id, config, directory):
    geometry = reference_geometry(reference, config)
    start, end = min(e['start'] for e in geometry['exons']), max(e['end'] for e in geometry['exons'])
    if end-start+1 > 250000:
        raise ValueError('한 번의 변이 목록 조회는250kb까지입니다. 더 긴 유전자는 부위별 조회 연결이 필요하며 제외로 처리하지 않습니다.')
    chrom = geometry['chromosome']
    if not re.fullmatch(r'[A-Za-z0-9_.]+', chrom):
        raise ValueError('염색체 식별자를 확인해 주세요.')
    url = f'https://rest.ensembl.org/overlap/region/human/{chrom}:{start}-{end}?feature=variation;content-type=application/json'
    raw, receipt = public_json(url, directory, 'variant-overlap')
    release, release_receipt = public_json('https://rest.ensembl.org/info/data?content-type=application/json', directory, 'release')
    if not isinstance(raw, list):
        raise ValueError('변이 목록 응답 형식을 확인해 주세요.')
    rows = []
    for variant in raw:
        key = 'variant_' + hashlib.sha256(json.dumps(variant, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:24]
        rows.append({'variant_key': key, 'variant_id': variant.get('id'), 'source_record': variant,
            'mapping': allele_mapping(variant, geometry, reference['sequence_5to3'])})
    rows.sort(key=lambda r: (r['source_record'].get('start', 0), r['variant_key']))
    return {'status': 'succeeded', 'semantic_type': 'public_variant_catalog_on_frozen_reference',
        'reference': reference['reference'], 'reference_artifact_id': reference_id,
        'geometry': geometry, 'rows': rows, 'sources': [receipt, release_receipt], 'source_release': release,
        'summary': {'variants_returned': len(rows), 'ref_verified': sum(r['mapping']['status']=='ref_verified' for r in rows),
            'not_applied': sum(r['mapping']['status']!='ref_verified' for r in rows),
            'region': f'{chrom}:{start}-{end}', 'transcript_accession': f"{reference['reference']['transcript_id']}.{reference['reference']['version']}",
            'patient_genotypes_used': False},
        'limits': ['공개 변이 목록입니다. 이 연구자/환자의 변이·빈도·병인성을 확인한 것이 아닙니다.',
            'REF가 실제 참조와 맞는 단일 allele만 별도 시나리오로 비교합니다. 기존 참조를 바꾸지 않습니다.',
            '현재 variation 릴리스와 보존 GTF/cDNA 릴리스는 다를 수 있습니다. 버전·원응답·REF 대응을 함께 남깁니다.',
            'exon 밖/경계·상징적/긴 변이는 버리지 않고 미적용으로 보존합니다. 스플라이싱·phase·환자 haplotype·전달은 별도입니다.']}


def scan(target, word):
    sites, unknown, minimum = [], 0, None
    for i in range(max(0, len(target)-len(word)+1)):
        window = target[i:i+len(word)]
        if 'N' in window:
            unknown += 1
            continue
        distance = sum(a != b for a, b in zip(window, word))
        minimum = distance if minimum is None else min(minimum, distance)
        if distance == 0:
            sites.append({'start_1_based': i+1, 'end_1_based': i+len(word)})
    return {'exact_sites': sites, 'unknown_windows': unknown, 'minimum_gapless_mismatches': minimum}


def compare_scenario(evaluation, catalog, reference, args):
    if (evaluation.get('semantic_type') != 'rna_sequence_thermodynamics_and_exact_mapping'
            or catalog.get('semantic_type') != 'public_variant_catalog_on_frozen_reference'):
        raise ValueError('실제 후보 계산과 공개 변이 목록이 필요합니다.')
    ref, target = reference['reference'], reference['sequence_5to3']
    if catalog['reference'] != ref or hashlib.sha256(target.encode()).hexdigest() != ref['sequence_sha256']:
        raise ValueError('변이 목록과 원 참조의 버전/해시가 다릅니다.')
    src = evaluation['reference']
    if (any(src.get(k) != ref.get(k) for k in ('assembly', 'organism'))
            or (src.get('gene_id') or '').split('.')[0] != (ref.get('gene_id') or '').split('.')[0]):
        raise ValueError('후보 계산과 변이 시나리오의 유전자/종/assembly가 다릅니다.')
    entries = [r for r in catalog['rows'] if r['variant_key'] == args['variant_key']]
    if len(entries) != 1:
        raise ValueError('목록의 정확한 변이 행을 선택해 주세요.')
    entry = entries[0]
    mapping = allele_mapping(entry['source_record'], catalog['geometry'], target)
    if mapping['status'] != 'ref_verified' or args['alternate'] not in mapping['available_alternates']:
        raise ValueError('REF를 확인한 변이 행과 실제 ALT를 선택해 주세요.')
    if not args['reason'].strip():
        raise ValueError('이 변이 조건을 비교하려는 이유를 남겨 주세요.')
    candidates = {r['id']: r for r in evaluation['rows']}
    ids = args['candidate_ids']
    if not ids or len(ids)>100 or len(set(ids))!=len(ids) or not set(ids)<=candidates.keys() or len(target)*len(ids)>5000000:
        raise ValueError('원 결과의 중복 없는 후보1–100개와 현재 대조량 범위를 확인해 주세요.')
    left, right = mapping['cdna_start_0_based'], mapping['cdna_end_exclusive']
    alt = oriented_allele(args['alternate'], entry['source_record']['strand'], catalog['geometry']['strand'])
    changed = target[:left]+alt+target[right:]
    scenario_hash = hashlib.sha256(changed.encode()).hexdigest()
    rows = []
    for cid in ids:
        guide = sequence(candidates[cid]['guide_5to3'], 19, 30)
        word = reverse_complement(guide)
        original, edited = scan(target, word), scan(changed, word)
        uncertain_absence = any(not s['exact_sites'] and s['unknown_windows'] for s in (original, edited))
        effect = ('unresolved_unknown_bases' if uncertain_absence else
            'exact_site_lost' if original['exact_sites'] and not edited['exact_sites'] else
            'exact_site_gained' if not original['exact_sites'] and edited['exact_sites'] else
            'exact_positions_changed' if original['exact_sites'] != edited['exact_sites'] else 'exact_sites_unchanged')
        rows.append({'candidate_id': cid, 'guide_5to3': guide, 'target_word_5to3': word,
            'original': original, 'scenario': edited, 'effect': effect,
            'original_genomic_sites': [{'cdna_site': s, 'genomic_blocks': genomic_blocks(catalog['geometry'], s['start_1_based'], s['end_1_based'])} for s in original['exact_sites']],
            'knockdown_prediction': None})
    return {'status': 'succeeded', 'semantic_type': 'constructed_allele_exact_sequence_comparison',
        'reference': ref, 'rows': rows, 'variant': entry, 'sources': catalog['sources'],
        'selection_reason': args['reason'],
        'scenario': {'semantic_type': 'constructed_single_allele_sequence', 'parent_reference_id': catalog['reference_artifact_id'],
            'parent_sequence_sha256': ref['sequence_sha256'], 'sequence_sha256': scenario_hash,
            'sequence_5to3': changed, 'alternate': args['alternate'], 'alternate_in_transcript_5to3': alt,
            'edit_interval_0_based_half_open': [left, right], 'length_change_nt': len(changed)-len(target),
            'not_patient_genotype': True, 'not_archived_reference': True},
        'summary': {'selected_candidates': len(ids), 'variant_id': entry['variant_id'], 'alternate': args['alternate'],
            'effects': dict(Counter(r['effect'] for r in rows)), 'length_change_nt': len(changed)-len(target),
            'patient_genotypes_used': False},
        'limits': ['공개 단일 allele을 원 참조에 적용한 서열 시나리오입니다. 환자 genotype/haplotype·실험 관측이 아닙니다.',
            '원 참조와 시나리오 전체 서열에서 정확 부위를 다시 찾습니다. 하류 위치 이동을 부위 소실로 세지 않습니다.',
            '시나리오 좌표는 바뀐 cDNA 기준입니다. 새 좌표를 원 유전체 좌표로 그대로 옮기지 않습니다.',
            'gap 없는 불일치/완전 일치는 억제 확률이 아닙니다. bulge·스플라이싱·phase·화학수식·전달·기능은 별도 확인입니다.']}


def filtered_variants(value, query):
    query = query.strip().lower()
    if len(query) > 200:
        raise ValueError('검색어는200자 이내로 입력해 주세요.')
    return [r for r in value['rows'] if not query or query in json.dumps(r, ensure_ascii=False).lower()]
