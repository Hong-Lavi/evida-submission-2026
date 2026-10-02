"""Actual SeedMatchR counting and ECDF test with explicit input/provenance checks.

The public author's three R source files are executed unchanged. The installed R
and Biostrings runtime is recorded; this is a tested component adaptation, not an
installation/replication of the complete SeedMatchR 2.0 package environment.
"""
from __future__ import annotations
import csv,hashlib,json,math,re,subprocess
from pathlib import Path

SEEDS=['mer7m8','mer8']
AUTHOR_COMMIT='2fc0c4fba31e7306377488ac8b4c81d6445df5e2'
def runtime_fingerprint():
    code='cat(jsonlite::toJSON(list(R=R.version.string,Biostrings=as.character(packageVersion("Biostrings")),dplyr=as.character(packageVersion("dplyr")),jsonlite=as.character(packageVersion("jsonlite"))),auto_unbox=TRUE))'
    raw=subprocess.check_output(['/usr/bin/Rscript','--vanilla','-e',code],
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},text=True,timeout=30)
    return json.loads(raw)

R_DRIVER='''args <- commandArgs(trailingOnly=TRUE)
suppressPackageStartupMessages(library(dplyr))
source(file.path(args[1], "get_seed.R"))
source(file.path(args[1], "SeedMatchR.R"))
source(file.path(args[1], "deseq_fc_ecdf.R"))
seqs <- Biostrings::readDNAStringSet(args[2])
res <- read.delim(args[3], stringsAsFactors=FALSE, check.names=FALSE)
for (seed in c("mer7m8", "mer8")) {
  res <- SeedMatchR(seqs=seqs, sequence=args[4], res=res,
    res.format="DESEQ2", seed.name=seed, shared_genes=TRUE,
    allow_wobbles=FALSE, max.mismatch=0, with.indels=FALSE, fixed=TRUE)
}
write.table(res, file=args[5], sep="\\t", quote=FALSE, row.names=FALSE, na="NA")
eligible <- res[res$eligible_for_distribution == 1, ]
background <- eligible$gene_id[eligible$mer7m8 == 0 & eligible$mer8 == 0]
tests <- list()
for (seed in c("mer7m8", "mer8")) {
  target <- eligible$gene_id[eligible[[seed]] > 0]
  warnings <- character()
  if (length(target) >= 2 && length(background) >= 2) {
    test <- withCallingHandlers(ecdf_stat_test(eligible, target, background,
        stats_test="KS", alternative="greater"), warning=function(w) {
          warnings <<- c(warnings, conditionMessage(w)); invokeRestart("muffleWarning")
        })
    tests[[seed]] <- list(status="computed", seed=seed, target_genes=length(target),
      background_genes=length(background), statistic=unname(test$statistic),
      pvalue=test$p.value, method=test$method, alternative=test$alternative,
      target_median=median(eligible$log2FoldChange[eligible$gene_id %in% target]),
      background_median=median(eligible$log2FoldChange[eligible$gene_id %in% background]),
      warnings=warnings)
  } else tests[[seed]] <- list(status="insufficient_groups", seed=seed,
    target_genes=length(target), background_genes=length(background))
}
ok <- vapply(tests, function(x) identical(x$status,"computed"), logical(1))
if (any(ok)) {
  adjusted <- p.adjust(vapply(tests[ok],function(x) x$pvalue,numeric(1)), method="holm")
  for (name in names(adjusted)) tests[[name]]$pvalue_holm_two_seed_family <- unname(adjusted[name])
}
out <- list(tests=unname(tests), runtime=list(R=R.version.string,
  Biostrings=as.character(packageVersion("Biostrings")),
  dplyr=as.character(packageVersion("dplyr")), jsonlite=as.character(packageVersion("jsonlite"))))
writeLines(jsonlite::toJSON(out, auto_unbox=TRUE, pretty=TRUE, null="null", digits=NA),args[6])
'''

def analyze(observations,input_meta,reference,guide,scratch,vendor):
    scratch=Path(scratch);scratch.mkdir(parents=True,exist_ok=True);vendor=Path(vendor)
    if observations.get('semantic_type')!='reported_observation':raise ValueError('Processed RNA observations required.')
    if reference.get('semantic_type')!='rna_3utr_reference' or guide.get('semantic_type')!='published_rna_guide':
        raise ValueError('Versioned RNA reference and sourced existing guide required.')
    if reference.get('organism')!=guide.get('organism') or reference.get('organism')!='Rattus norvegicus':
        raise ValueError('Reference and guide organism correspondence is not established.')
    filename=input_meta.get('original_filename')
    if filename not in guide.get('verified_input_filenames',[]):raise ValueError('Guide identity has not been verified for this input contrast.')
    expected=guide.get('verified_input_sha256',{}).get(filename)
    if expected and input_meta.get('actual_input_sha256')!=expected:raise ValueError('Input source hash differs from verified guide pairing.')
    sequence=guide.get('sequence_5to3','')
    if not re.fullmatch('[ACGU]{9,100}',sequence):raise ValueError('A verified 5-to-3 RNA guide is required.')
    refs=reference['rows'];by_gene={r['gene_id']:r for r in refs}
    if len(by_gene)!=len(refs):raise ValueError('Reference must specify one transcript policy per gene.')
    ids=[r['gene_id'] for r in observations['rows']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate gene IDs require explicit handling before a distribution analysis.')
    id_set=set(ids)
    selected=[r for r in refs if r['gene_id'] in id_set]
    for r in selected:
        if not re.fullmatch('[ACGTN]+',r['sequence']) or len(r['sequence'])!=r['length']:
            raise ValueError('Reference sequence/length contract failed.')
        if hashlib.sha256(r['sequence'].encode()).hexdigest()!=r['sequence_sha256']:
            raise ValueError('Reference sequence hash changed.')
    with (scratch/'reference.fa').open('w') as f:
        for r in selected:f.write('>'+r['gene_id']+'\n'+r['sequence']+'\n')
    eligible={}
    for r in observations['rows']:
        ref=by_gene.get(r['gene_id']);v=r['values'];reason=[]
        if ref is None:reason.append('reference_not_mapped')
        elif 'N' in ref['sequence']:reason.append('ambiguous_reference_sequence')
        if v.get('log2FoldChange') is None:reason.append('fold_change_missing_or_invalid')
        if v.get('baseMean') is None or v['baseMean']<=0:reason.append('base_mean_not_positive')
        if r['gene_id']==guide.get('target_gene_id'):reason.append('intended_target_excluded_from_offtarget_distribution')
        eligible[r['gene_id']]=reason
    with (scratch/'observations.tsv').open('w') as f:
        w=csv.writer(f,delimiter='\t');w.writerow(['gene_id','log2FoldChange','eligible_for_distribution'])
        for r in observations['rows']:
            v=r['values'].get('log2FoldChange');w.writerow([r['gene_id'],v if v is not None else 'NA',int(not eligible[r['gene_id']])])
    (scratch/'driver.R').write_text(R_DRIVER)
    command=['/usr/bin/Rscript','--vanilla',str(scratch/'driver.R'),str(vendor),str(scratch/'reference.fa'),
             str(scratch/'observations.tsv'),sequence,str(scratch/'matched.tsv'),str(scratch/'statistics.json')]
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'}
    with (scratch/'r-worker.log').open('w') as log:
        subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    counted={r['gene_id']:r for r in csv.DictReader((scratch/'matched.tsv').open(),delimiter='\t')}
    assert set(counted)=={r['gene_id'] for r in selected}
    rows=[]
    for r in observations['rows']:
        ref=by_gene.get(r['gene_id']);found=counted.get(r['gene_id'])
        counts={seed:int(found[seed]) for seed in SEEDS} if found else None
        rows.append({**r,'reference_mapping':'mapped' if ref else 'not_mapped',
            'selected_transcript':ref['transcript_id'] if ref else None,
            'reference_sequence_sha256':ref['sequence_sha256'] if ref else None,
            'reference_contains_ambiguous_bases':('N' in ref['sequence']) if ref else None,
            'seed_counts':counts,'distribution_eligible':not eligible[r['gene_id']],
            'distribution_exclusion_reasons':eligible[r['gene_id']]})
    stats=json.loads((scratch/'statistics.json').read_text())
    return {'status':'succeeded','semantic_type':'rna_seed_distribution_analysis','rows':rows,
        'summary':{'total_rows':len(rows),'mapped_genes':len(counted),'unmapped_genes':len(rows)-len(counted),
            'distribution_eligible_genes':sum(r['distribution_eligible'] for r in rows),
            'intended_target_rows':[r for r in rows if r['gene_id']==guide['target_gene_id']],
            'tests':stats['tests']},'contrast':observations.get('contrast'),'context':observations.get('context'),
        'reference':{k:v for k,v in reference.items() if k!='rows'},'guide':guide,'runtime':stats['runtime'],
        'author_component':{'repository':'https://github.com/tacazares/SeedMatchR','commit':AUTHOR_COMMIT,
            'functions':['get_seed','SeedMatchR','.get_counts_column','ecdf_stat_test'],
            'files':{name:hashlib.sha256((vendor/name).read_bytes()).hexdigest() for name in ['get_seed.R','SeedMatchR.R','deseq_fc_ecdf.R']},
            'full_package_installed':False},
        'analysis_policy':{'seed_names':SEEDS,'max_mismatch':0,'with_indels':False,'allow_wobbles':False,
            'eligibility':'Mapped, unambiguous 3UTR; finite reported fold change, positive baseMean; intended target excluded. No significance prefilter.',
            'background':'Eligible genes with zero matches to both selected seeds.',
            'test':'Author ecdf_stat_test KS greater: seed-positive FC cumulative distribution above background means shift toward smaller FC.',
            'multiplicity':'Holm across two seed comparisons; nested seed groups are not independent biological evidence.'},
        'limits':['기존 처리표를 이용한 새 seed 매칭·분포 계산입니다. 새 차등발현 적합이나 독립 생물학적 실험이 아닙니다.',
            '참조 미대응·모호 염기·결측을 일치 0개나 효과 없음으로 바꾸지 않았습니다. 원행은 모두 유지합니다.',
            '유전자 간 의존성·UTR 길이·발현·간접 반응 등으로 KS p값은 개별 off-target이나 인과 기전의 확률이 아닙니다.',
            'Ensembl104/Rnor_6.0·명시적 transcript 선택의 새 분석이며 원 논문 또는 저자 AnnotationHub 실행과 동일한 수치 재현을 주장하지 않습니다.',
            '검증된 해당 가이드·처리표 연결에 한합니다. 다른 siRNA·대조·코호트·인간 치료 효능으로 일반화하지 않습니다.']}
