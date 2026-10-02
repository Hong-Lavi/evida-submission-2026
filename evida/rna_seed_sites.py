"""Actual author seed definitions/position search plus explicit liver-expression joins."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from .rna_resources import candidate_rows, configuration
from .resource_integrity import verify_file
from .rna_seed import AUTHOR_COMMIT

SEEDS=('mer6','mer7m8','mer7A1','mer8')
R_DRIVER='''args <- commandArgs(trailingOnly=TRUE)
suppressPackageStartupMessages(library(Biostrings))
source(args[1])
seqs <- readDNAStringSet(args[2])
guides <- read.delim(args[3], stringsAsFactors=FALSE)
con <- file(args[4], "wt")
writeLines("candidate_id\\tseed_type\\ttranscript_id\\tstart_1_based\\tend_1_based", con)
patterns <- list()
for (i in seq_len(nrow(guides))) {
 for (seed in c("mer6","mer7m8","mer7A1","mer8")) {
  pattern <- get_seed(guides$guide[i], seed.name=seed, allow_wobbles=FALSE)$Target.Seq
  patterns[[paste(guides$id[i],seed,sep=":")]] <- as.character(pattern)
  matches <- vmatchPattern(pattern, seqs, max.mismatch=0, min.mismatch=0, with.indels=FALSE, fixed=TRUE)
  counts <- elementNROWS(matches)
  hit <- which(counts>0)
  if (length(hit)>0) {
   starts <- unlist(start(matches[hit]), use.names=FALSE)
   lines <- paste(guides$id[i], seed, rep(names(seqs)[hit], counts[hit]),
     starts, starts+length(pattern)-1L, sep="\\t")
   writeLines(lines, con)
  }
 }
}
close(con)
writeLines(jsonlite::toJSON(list(patterns=patterns, R=R.version.string,
 Biostrings=as.character(packageVersion("Biostrings"))), auto_unbox=TRUE, pretty=TRUE), args[5])
'''

def patterns(guide):
    dna=guide.upper().replace('U','T')
    rc=lambda s:s.translate(str.maketrans('ACGT','TGCA'))[::-1]
    return {'mer6':rc(dna[1:7]),'mer7m8':rc(dna[1:8]),'mer7A1':rc(dna[1:7])+'A','mer8':rc(dna[1:8])+'A'}

def exact_positions(text,pattern):
    found=[];start=0
    while (at:=text.find(pattern,start))>=0:
        found.append((at+1,at+len(pattern)));start=at+1
    return found

def core_start(site):
    # The same paired guide2-7 core has a preceding m8 target base in m8/8mer.
    return site['start_1_based']+int(site['seed_type'] in ('mer7m8','mer8'))

def expression_join(gene,expression):
    entries=expression.get(gene.split('.')[0],[])
    return {'status':'not_mapped','liver_median_tpm':None,'original_rows':[]} if not entries else (
        {'status':'ambiguous_stable_id','liver_median_tpm':None,'original_rows':entries} if len(entries)!=1 else
        {'status':'mapped_gene_not_site_isoform','liver_median_tpm':entries[0]['liver_median_tpm'],'original_rows':entries})

def author_scan(guides,fasta,vendor,work):
    work=Path(work);work.mkdir(exist_ok=False,parents=True)
    with (work/'guides.tsv').open('w') as f:
        w=csv.writer(f,delimiter='\t');w.writerow(['id','guide'])
        for g in guides:w.writerow([g['id'],g['guide_5to3']])
    (work/'driver.R').write_text(R_DRIVER)
    command=['/usr/bin/Rscript','--vanilla',str(work/'driver.R'),str(vendor/'get_seed.R'),str(fasta),str(work/'guides.tsv'),str(work/'matches.tsv'),str(work/'runtime.json')]
    with (work/'worker.log').open('w') as f:
        subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=900,
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'})
    runtime=json.loads((work/'runtime.json').read_text())
    for g in guides:
        for name,pattern in patterns(g['guide_5to3']).items():
            if runtime['patterns'][g['id']+':'+name]!=pattern:raise ValueError('저자 seed 정의와 독립 정의가 다릅니다.')
    return runtime

def summarize(guides,raw,annotation,expression,target_gene):
    per_candidate=[];sites=[]
    grouped=collections.defaultdict(list)
    for r in raw:grouped[(r['candidate_id'],r['transcript_id'],core_start(r))].append(r)
    priority={'mer8':0,'mer7m8':1,'mer7A1':2,'mer6':3}
    for (candidate,tid,core),matches in grouped.items():
        best=min(matches,key=lambda r:priority[r['seed_type']]);ann=annotation[tid];exp=expression_join(ann['gene'],expression)
        sites.append({'candidate_id':candidate,'transcript_id':tid,'gene_id':ann['gene'],'gene_symbol':ann['symbol'],
            'site_type':best['seed_type'],'nested_site_types':sorted({r['seed_type'] for r in matches}),
            'utr_start_1_based':best['start_1_based'],'utr_end_1_based':best['end_1_based'],
            'cdna_start_1_based':ann['utr_start']+best['start_1_based']-1,'cdna_end_1_based':ann['utr_start']+best['end_1_based']-1,
            'sequence':ann['utr_sequence'][best['start_1_based']-1:best['end_1_based']],
            'liver_median_tpm':exp['liver_median_tpm'],'expression_mapping':exp['status'],'expression_source_rows':exp['original_rows'],
            'same_target_gene':ann['gene'].split('.')[0]==target_gene.split('.')[0],
            'isoform_expression':'unknown; gene-level median does not establish expression of this site-containing isoform'})
    for g in guides:
        own=[r for r in sites if r['candidate_id']==g['id']];other=[r for r in own if not r['same_target_gene']]
        counts={seed:sum(r['candidate_id']==g['id'] and r['seed_type']==seed for r in raw) for seed in SEEDS}
        sensitivity={str(t):len({r['gene_id'] for r in other if r['liver_median_tpm'] is not None and r['liver_median_tpm']>=t}) for t in (.1,1,10)}
        m8genes={r['gene_id'] for r in other if r['site_type'] in ('mer8','mer7m8')}
        a1genes={r['gene_id'] for r in other if r['site_type']=='mer7A1'}
        per_candidate.append({'candidate_id':g['id'],'guide_5to3':g['guide_5to3'],'raw_nested_counts':counts,'distinct_sites':len(own),
            'other_gene_sites':len(other),'other_genes':len({r['gene_id'] for r in other}),'m8_or8mer_other_genes':len(m8genes),
            'additional_A1_other_genes':len(a1genes-m8genes),'other_genes_with_liver_tpm_at_least':sensitivity,
            'other_genes_expression_unmapped_or_ambiguous':len({r['gene_id'] for r in other if r['liver_median_tpm'] is None})})
    return sorted(sites,key=lambda r:(r['candidate_id'],r['transcript_id'],r['utr_start_1_based'])),per_candidate

def analyze(result,arguments,work):
    guides=candidate_rows(result,arguments['candidate_ids'])
    if result['reference'].get('organism')!='homo_sapiens':raise ValueError('현재 seed 참조는 인간 Ensembl115입니다.')
    cfg=configuration()['seed_sites'];work=Path(work)
    hashes={key:verify_file(cfg[key],cfg[key+'_sha256']) for key in ('database','fasta','expression')}
    vendor=Path(__file__).parent/'vendor/seedmatchr'
    verify_file(vendor/'get_seed.R',cfg['author_get_seed_sha256'])
    runtime=author_scan(guides,Path(cfg['fasta']),vendor,work)
    with sqlite3.connect('file:'+cfg['database']+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;annotation={r['id']:dict(r) for r in db.execute('SELECT * FROM transcripts')}
    expression=json.loads(Path(cfg['expression']).read_text())
    raw=[];actual=collections.defaultdict(set)
    for r in csv.DictReader((work/'matches.tsv').open(),delimiter='\t'):
        r['start_1_based']=int(r['start_1_based']);r['end_1_based']=int(r['end_1_based'])
        if r['transcript_id'] not in annotation:raise ValueError('검색 결과 전사체가 참조와 다릅니다.')
        raw.append(r);actual[(r['candidate_id'],r['seed_type'],r['transcript_id'])].add((r['start_1_based'],r['end_1_based']))
    comparisons=0
    for g in guides:
        for seed,pat in patterns(g['guide_5to3']).items():
            for tid,ann in annotation.items():
                expected=set(exact_positions(ann['utr_sequence'],pat));found=actual.get((g['id'],seed,tid),set())
                if expected!=found:raise ValueError('저자 위치 검색과 독립 대조가 다릅니다.')
                comparisons+=1
    sites,summaries=summarize(guides,raw,annotation,expression['genes'],result['reference'].get('gene_id',''))
    return {'status':'succeeded','semantic_type':'canonical_3utr_seed_sites_with_gene_expression_not_risk',
        'rows':sites,'candidate_summary':summaries,'reference':result['reference'],
        'summary':{'candidates':len(guides),'eligible_transcripts':len(annotation),'distinct_sites':len(sites),'raw_nested_matches':len(raw),
            'independent_position_comparisons':comparisons,'tissue':'liver','expression_resolution':'gene median; site isoform expression unknown'},
        'source':{'Ensembl_release':115,'assembly':'GRCh38','GTEx_release':'v8 / GENCODE26','verified_assets':hashes,'reference_coverage':cfg['coverage'],
            'gtf_url':cfg['gtf_url'],'expression_url':expression['source']['url']},
        'protocol':{'author_commit':AUTHOR_COMMIT,'author_get_seed_sha256':cfg['author_get_seed_sha256'],'author_functions':['get_seed','Biostrings::vmatchPattern'],
            'full_SeedMatchR_or_siSPOTR_reproduction':False,'max_mismatch':0,'indels':False,'wobble':False,
            'nested_site_policy':'all raw classes retained in matches.tsv; one site per same guide2-7 core per transcript; strongest8mer/m8/A1/6 shown',
            'expression_sensitivity_tpm':[.1,1,10],'runtime':runtime},
        'limits':['실제 3′UTR seed 위치와 간 유전자 median TPM을 연결했습니다. 억제 확률·안전성·활성 예측이 아닙니다.',
            '발현은 유전자 단위이며 그 부위를 가진 isoform의 발현·개인 변이·질환 세포에서의 발현은 미확인입니다.',
            '6mer/7mer/8mer의 중첩 원결과는 보존하며 같은 부위를 여러 독립 근거로 세지 않습니다.',
            '명시적 번역 종료·UTR/전사체 대응을 확인하지 못한 전사체는 누락 이유와 함께 참조 기록에 남깁니다. 일치0개가 아닙니다.',
            'TPM0.1/1/10은 민감도 보기 기준이며 안전성 문턱이 아닙니다. 미대응/발현0/낮은발현을 구분합니다.',
            '안정성·전달·화학수식·AGO2 및 passenger 가닥은 평가하지 않았습니다.']}
