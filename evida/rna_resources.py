"""Explicit archived reference and RIsearch2 alignment; no tissue risk scores."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess

from .rna_sequence import sequence
from .resource_integrity import verify_resources


def configuration():
    return json.loads((Path(__file__).parents[1] / 'configs/rna-resources.json').read_text())


def selected_release_configuration(complete_cfg, release):
    if type(release) is not int:
        raise ValueError('명시적인 정수 Ensembl 판본이 필요합니다.')
    ref = complete_cfg['reference'] if release == complete_cfg['reference']['release'] else complete_cfg.get('additional_references', {}).get(str(release))
    if ref is None or ref.get('release') != release:
        raise ValueError('선택한 판본의 검증된 보존 참조가 설치되지 않았습니다. 다른 판본으로 자동 대체하지 않습니다.')
    return {**complete_cfg, 'reference': ref}


def release_reference(arguments):
    cfg = selected_release_configuration(configuration(), arguments['release'])
    return archived_reference(arguments, selected_configuration=cfg)


def archived_reference(arguments, selected_configuration=None):
    complete_cfg = configuration() if selected_configuration is None else selected_configuration
    verify_resources(complete_cfg, 'rna_reference_archive')
    cfg = complete_cfg['reference']
    release = cfg['release']
    accession = arguments['ensembl_id'].strip()
    if not re.fullmatch(r'ENS[GT][0-9]{11}(?:\.[0-9]+)?', accession):
        raise ValueError('보존 참조는 인간 Ensembl 유전자/전사체 ID만 지원합니다.')
    plain, _, requested = accession.partition('.')
    with sqlite3.connect('file:' + cfg['annotations'] + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(x) for x in db.execute('SELECT * FROM transcripts WHERE '+('gene_plain' if plain.startswith('ENSG') else 'plain')+'=?', (plain,))]
    if not rows:
        raise ValueError(f'선택한 Ensembl {release} 참조에 해당 ID가 없습니다. 현재 주석으로 자동 대체하지 않습니다.')
    source = {'url': cfg['url'], 'release': release, 'assembly': 'GRCh38', 'organism': 'homo_sapiens',
              'fasta_sha256': cfg['fasta_sha256'], 'selection': f'explicit archived Ensembl{release}; not current REST fallback'}
    if plain.startswith('ENSG'):
        if requested and any(x['gene'] != accession for x in rows):
            raise ValueError('요청 유전자 버전과 보존 주석이 다릅니다.')
        return {'status': 'succeeded', 'semantic_type': 'transcript_identifier_candidates', 'source': source,
            'rows': [{'transcript_id': x['plain'], 'version': int(x['id'].split('.')[1]), 'display_name': x['symbol'],
                      'biotype': x['biotype'], 'canonical_annotation': None, 'original_header': x['header']} for x in rows],
            'summary': {'gene_id': rows[0]['gene'], 'transcripts': len(rows), 'organism': 'homo_sapiens',
                        'assembly': 'GRCh38', 'release': release, 'requires_transcript_selection': True},
            'limits': [f'인간 Ensembl {release}의 모든 spliced cDNA 목록입니다. 조직 발현·canonical 여부를 이 FASTA로 결정하지 않습니다.']}
    row = rows[0]
    if requested and row['id'] != accession:
        raise ValueError('요청 전사체 버전과 보존 주석이 다릅니다.')
    with Path(cfg['fasta']).open('rb') as f:
        f.seek(row['start']); raw = f.read(row['end']-row['start'])
    parts = raw.decode().splitlines()
    if parts[0].split()[0] != '>'+row['id']:
        raise ValueError('참조 색인과 FASTA 위치가 일치하지 않습니다.')
    dna = ''.join(parts[1:]).upper(); rna = dna.replace('T','U')
    if not re.fullmatch('[ACGUN]+',rna):
        raise ValueError('해석할 수 없는 참조 염기입니다.')
    source.update(byte_start=row['start'], byte_end=row['end'], raw_record_sha256=hashlib.sha256(raw).hexdigest())
    return {'status': 'succeeded', 'semantic_type': 'versioned_transcript_sequence', 'source': source, 'sequence_source': source,
        'sequence_5to3': rna, 'sequence_response': {'seq': dna, 'id': row['id'], 'original_header': row['header']},
        'reference': {'transcript_id': row['plain'], 'version': int(row['id'].split('.')[1]), 'gene_id': row['gene'],
                      'organism': 'homo_sapiens', 'assembly': 'GRCh38', 'release': release, 'sequence_type': 'spliced_cdna',
                      'sequence_sha256': hashlib.sha256(rna.encode()).hexdigest(), 'dna_to_rna_normalization': 'T converted to U; DNA retained'},
        'rows': [{'start_1_based': i+1, 'end_1_based': min(i+1000,len(rna)), 'sequence_5to3': rna[i:i+1000]} for i in range(0,len(rna),1000)],
        'summary': {'length':len(rna), 'unknown_bases':rna.count('N'), 'release':release, 'requires_transcript_selection':False},
        'limits': [f'명시적으로 선택한 Ensembl {release}의 보존 서열입니다. 현재 주석/조직별 발현과 구분합니다.', '새 전사체 버전이 과거 실험 참조를 자동 대체하지 않습니다.']}


def candidate_rows(result, ids):
    rows = result.get('rows', [])
    if result.get('semantic_type') != 'rna_sequence_thermodynamics_and_exact_mapping':
        raise ValueError('완료한 가이드 서열 계산이 필요합니다.')
    if not ids or len(ids) > 12 or len(set(ids)) != len(ids):
        raise ValueError('서로 다른 후보 1–12개를 명시해 주세요.')
    selected = [r for r in rows if r['id'] in ids]
    if {r['id'] for r in selected} != set(ids):
        raise ValueError('원 결과에서 후보 ID를 확인할 수 없습니다.')
    return selected


def search_offtargets(result, arguments, work):
    cfg = configuration(); ref = cfg['reference']; engine = cfg['risearch']
    rows = candidate_rows(result, arguments['candidate_ids'])
    if result['reference'].get('organism') != 'homo_sapiens':
        raise ValueError('현재 전체 참조는 인간입니다. 다른 종의 가이드를 자동 비교하지 않습니다.')
    verified_assets = verify_resources(cfg, 'rna_transcriptome_search')
    index = Path(engine['index'])
    if not index.is_file():
        raise ValueError('전체 전사체 색인이 아직 준비되지 않았습니다.')
    work = Path(work); work.mkdir(exist_ok=False)
    query = work/'guides.fa'; mapping = {f'q{i}': r for i,r in enumerate(rows)}
    query.write_text(''.join('>'+key+'\n'+sequence(r['guide_5to3'],19,30)+'\n' for key,r in mapping.items()))
    command = [engine['binary'],'-i',str(index),'-q',str(query),'-s','1:12/6','-e',str(arguments['energy_cutoff_kcal_mol']),'-l','20','-p2','-t','2']
    with (work/'worker.log').open('wb') as log:
        subprocess.run(command,cwd=work,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    hits=[]; summaries=[]
    with sqlite3.connect('file:'+ref['annotations']+'?mode=ro',uri=True) as db:
        annotation={}
        for key,r in mapping.items():
            files=list(work.glob('risearch_'+key+'.out.gz'))
            if len(files)!=1: raise ValueError('RIsearch2 결과 파일을 확인할 수 없습니다.')
            candidate_hits=[]
            with gzip.open(files[0],'rt') as f:
                for line in f:
                    fields=line.rstrip('\n').split('\t')
                    if len(fields)<8: raise ValueError('RIsearch2 출력 열을 확인해 주세요.')
                    q,qs,qe,target,ts,te,strand,energy,*rest=fields
                    if q!=key or strand not in ('+','-'): raise ValueError('쿼리/가닥 출력이 다릅니다.')
                    if target not in annotation:
                        v=db.execute('SELECT gene,symbol,biotype FROM transcripts WHERE id=?',(target,)).fetchone()
                        annotation[target]=v or (None,None,None)
                    gene,symbol,biotype=annotation[target]
                    same_transcript=target.split('.')[0]==result['reference']['transcript_id']
                    same_gene=(gene or '').split('.')[0]==result['reference'].get('gene_id','').split('.')[0]
                    hit={'candidate_id':r['id'],'guide_5to3':r['guide_5to3'],'query_start_1_based':int(qs),'query_end_1_based':int(qe),
                        'transcript_id':target,'gene_id':gene,'gene_symbol':symbol,'biotype':biotype,
                        'target_start_1_based':int(ts),'target_end_1_based':int(te),'index_strand':strand,'energy_kcal_mol':float(energy),
                        'alignment_fields':rest,'same_selected_transcript':same_transcript,'same_target_gene':same_gene,
                        'interpretation':'annotated_spliced_transcript' if strand=='+' else 'artificial_reverse_complement_index_not_expressed_transcript'}
                    candidate_hits.append(hit)
            plus=[h for h in candidate_hits if h['index_strand']=='+']
            other=[h for h in plus if not h['same_target_gene']]
            summaries.append({'candidate_id':r['id'],'annotated_transcript_hits':len(plus),'other_gene_hits':len(other),
                'other_genes':len({h['gene_id'] for h in other if h['gene_id']}),'reverse_index_hits':len(candidate_hits)-len(plus),
                'best_other_gene_energy_kcal_mol':min((h['energy_kcal_mol'] for h in other),default=None)})
            hits.extend(candidate_hits)
    return {'status':'succeeded','semantic_type':'transcriptome_sequence_interaction_candidates_not_tissue_risk',
        'reference':result['reference'],'source':{'url':ref['url'],'release':115,'assembly':'GRCh38','transcripts':ref['transcripts'],'fasta_sha256':ref['fasta_sha256'], 'verified_assets':verified_assets},
        'rows':sorted(hits,key=lambda h:(h['index_strand']!='+',h['energy_kcal_mol'],h['candidate_id'])),
        'candidate_summary':summaries,'summary':{'candidates':len(rows),'hits':len(hits),'release':115,'tissue_expression_applied':False},
        'protocol':{'method':'RIsearch2 v2.1','commit':engine['commit'],'binary_sha256':engine['binary_sha256'],
                    'seed':'1:12/6','extension':20,'energy_cutoff_kcal_mol':arguments['energy_cutoff_kcal_mol'],'threads':2,'alignment_format':2},
        'limits':['전체 인간 spliced cDNA에 실제 정렬한 잠재 상호작용입니다. 조직 발현·RISC·실제 off-target 억제 확률을 계산하지 않았습니다.',
                  '− 가닥은 색인이 만든 역상보 서열이며 실제 전사체로 세지 않습니다. 원 결과는 별도로 보존합니다.',
                  '표적 유전자의 다른 isoform, 다른 유전자, 합성 역상보 hit를 구분합니다. 전사체 수를 독립 유전자 수로 해석하지 않습니다.',
                  'unspliced RNA·미주석 전사체·유전체·개인 변이를 포함하지 않으며 화학수식 에너지를 계산하지 않습니다.']}
