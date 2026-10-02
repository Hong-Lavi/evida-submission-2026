"""Exact-version GTF region navigation for a retained pool; no candidate removal."""
from collections import Counter, defaultdict
import gzip
import hashlib
from pathlib import Path
import re

from .resource_integrity import verify_file

FEATURES = {'CDS', 'five_prime_utr', 'three_prime_utr', 'stop_codon'}


def coordinate_labels(exons, features, length):
    ordered = sorted(exons, key=lambda e: e['number'])
    if not ordered or [e['number'] for e in ordered] != list(range(1, len(ordered)+1)):
        raise ValueError('완전한 exon 순서가 없습니다.')
    if len({(e['chromosome'], e['strand']) for e in ordered}) != 1:
        raise ValueError('같은 염색체·가닥의 exon chain이 아닙니다.')
    strand = ordered[0]['strand']
    if strand not in ('+', '-'):
        raise ValueError('가닥이 미확정입니다.')
    positions = [p for e in ordered for p in (range(e['start'], e['end']+1) if strand=='+'
                                            else range(e['end'], e['start']-1, -1))]
    if len(positions)!=length or len(set(positions))!=length or positions!=sorted(positions, reverse=strand=='-'):
        raise ValueError('참조 길이와 겹침 없는 exon chain이 대응하지 않습니다.')
    if any((chrom, s)!=(ordered[0]['chromosome'], strand) for _, _, _, chrom, s in features):
        raise ValueError('기능 영역의 염색체·가닥이 exon과 다릅니다.')
    labels=[]
    for p in positions:
        types={kind for kind, start, end, _, _ in features if start<=p<=end}
        if len(types)>1:
            raise ValueError('서로 겹치는 기능 주석입니다.')
        labels.append(next(iter(types)) if types else 'no_region_annotation')
    return labels


def annotate(space, references, config, artifact_id):
    if space.get('semantic_type')!='retained_versioned_rna_candidate_space':
        raise ValueError('원 출처가 보존된 전체 RNA 후보 목록이 필요합니다.')
    refs={aid:r for aid,r in references}
    wanted={}; gtf=config['genomic_annotation']
    verify_file(gtf['path'], gtf['sha256'])
    for panel in space['reference_panel']:
        ref=refs.get(panel['artifact_id'])
        if not ref or ref.get('semantic_type')!='versioned_transcript_sequence':
            raise ValueError('원 후보 목록의 모든 참조가 필요합니다.')
        m=ref['reference']; sequence=ref['sequence_5to3']
        if (any(m.get(k)!=panel.get(k) for k in ('transcript_id','version','sequence_sha256','gene_id','assembly','organism'))
                or hashlib.sha256(sequence.encode()).hexdigest()!=m['sequence_sha256']):
            raise ValueError('후보 목록과 참조의 버전·서열 해시가 다릅니다.')
        if m.get('organism')!='homo_sapiens' or m.get('assembly')!=gtf['assembly']:
            raise ValueError('현재 보존 주석은 인간 GRCh38입니다.')
        wanted[(m['transcript_id'],str(m['version']))]={'panel':panel,'length':len(sequence)}
    records=defaultdict(lambda:{'exons':[], 'features':[], 'rows':[]})
    with gzip.open(gtf['path'],'rt') as f:
        for line in f:
            if line.startswith('#'):continue
            fields=line.rstrip('\n').split('\t')
            if len(fields)!=9 or fields[2] not in FEATURES|{'exon'}:continue
            attrs=dict(re.findall(r'(\w+) "([^"]*)";',fields[8]))
            key=(attrs.get('transcript_id'),attrs.get('transcript_version'))
            if key not in wanted:continue
            expected=wanted[key]['panel']['gene_id'].split('.')[0]
            if attrs.get('gene_id')!=expected:raise ValueError('GTF와 참조 유전자가 다릅니다.')
            record=records[key];record['rows'].append(line.rstrip('\n'))
            if fields[2]=='exon':
                record['exons'].append({'number':int(attrs['exon_number']), 'chromosome':fields[0],
                    'start':int(fields[3]),'end':int(fields[4]),'strand':fields[6]})
            else:record['features'].append((fields[2],int(fields[3]),int(fields[4]),fields[0],fields[6]))
    maps={}; coverage=[]
    for key, value in wanted.items():
        record=records[key]
        try:
            labels=coordinate_labels(record['exons'],record['features'],value['length'])
            status='exact_version_chain_length_matched';reason=''
        except ValueError as exc:
            labels=['unresolved_annotation']*value['length'];status='unresolved_annotation';reason=str(exc)
        aid=value['panel']['artifact_id'];maps[aid]=labels
        coverage.append({'reference_artifact_id':aid,'transcript_id':key[0],'version':key[1],
            'status':status,'reason':reason,'base_counts':dict(Counter(labels)),
            'source_gtf_rows':record['rows'],
            'verification':'Exact version/gene/exon order/length; independent genome-to-cDNA sequence reconstruction is separate'})
    rows=[];counts=Counter()
    for row in space['rows']:
        origins=[]
        for origin in row['origins']:
            labels=maps[origin['reference_artifact_id']][origin['start_1_based']-1:origin['end_1_based']]
            if len(labels)!=len(row['guide_5to3']):raise ValueError('후보 원위치가 참조 범위 밖입니다.')
            label='+'.join(sorted(set(labels)));counts[label]+=1
            origins.append({**origin,'annotated_region':label,'region_base_counts':dict(Counter(labels))})
        rows.append({**row,'origins':origins})
    return {**space, 'rows':rows,
        'summary':{**space['summary'],'region_annotated':True,'origin_region_counts':dict(counts)},
        'region_annotation':{'source_pool_artifact_id':artifact_id,'source':gtf,'reference_coverage':coverage,
            'method':'Exact-version exon positions mapped to explicit CDS/5UTR/3UTR/stop GTF features',
            'candidate_generation_or_reranking':False},
        'limits':[*space['limits'],'기능 영역은 원 창의 주석입니다. CDS·3′UTR 중 하나를 자동 우선하거나 미주석 창을 제외하지 않습니다. 같은 서열은 여러 isoform에서 서로 다른 영역일 수 있습니다.']}
