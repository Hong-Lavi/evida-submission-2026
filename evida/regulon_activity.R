args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==2L)
suppressPackageStartupMessages({library(decoupleR);library(jsonlite)})
input <- fromJSON(args[1],simplifyVector=FALSE)
stopifnot(as.character(packageVersion("decoupleR"))==input$required_versions$decoupleR)
stopifnot(as.character(getRversion())==input$required_versions$R)
prepared <- input$prepared
genes <- vapply(prepared$rows,function(x)x$gene,character(1))
values <- vapply(prepared$rows,function(x)x$statistic,numeric(1))
mat <- matrix(values,ncol=1,dimnames=list(genes,"provided_contrast"))
focus <- unlist(prepared$focus_tfs)
allScores <- list();coverage <- list();missing <- list();versions <- list(R=as.character(getRversion()),decoupleR=as.character(packageVersion("decoupleR")))
for (resource in names(input$resources)) {
  net <- read.delim(input$resources[[resource]]$path,check.names=FALSE)
  stopifnot(all(c("source","target","mor") %in% names(net)))
  stopifnot(!anyDuplicated(paste(net$source,net$target,sep="\t")))
  present <- net$target %in% genes
  universe <- sort(unique(net$source))
  counts <- setNames(vapply(universe,function(tf)sum(net$source==tf & present),integer(1)),universe)
  eligible <- names(counts[counts>=5L])
  if (length(eligible)==0L) {
    score <- data.frame(statistic=character(),source=character(),condition=character(),score=numeric(),p_value=numeric())
  } else {
    score <- as.data.frame(run_ulm(mat,net,minsize=5L,center=FALSE))
  }
  score$BH_resource_family <- p.adjust(score$p_value,"BH")
  score$resource <- rep(resource,nrow(score))
  score$measured_targets <- unname(counts[score$source])
  score$result_kind <- rep("inferred_regulon_contrast_not_measured_TF_activity",nrow(score))
  allScores[[resource]] <- score
  coverage[[resource]] <- list(resource_TFs=length(universe),eligible_TFs=length(eligible),
    input_genes=length(genes),mapped_input_genes=length(intersect(genes,unique(net$target))),minsize=5L)
  for (tf in union(names(counts[counts<5L]),setdiff(focus,universe))) {
    missing[[paste(resource,tf)]] <- list(resource=resource,TF=tf,
      status=if(tf %in% universe)"insufficient_measured_targets"else"resource_not_present",
      measured_targets=if(tf %in% universe) unname(counts[tf]) else 0L)
  }
}
rows <- do.call(rbind,allScores)
stopifnot(all(is.finite(rows$score)),all(is.finite(rows$p_value)))
focusRows <- rows[rows$source %in% focus,,drop=FALSE]
result <- list(status="succeeded",semantic_type="inferred_regulon_activity",
  method="decoupleR run_ulm on supplied gene-contrast statistics; full supplied gene background, two fixed human regulon resources",
  rows=rows,focus_rows=focusRows,coverage=coverage,unestimated=unname(missing),
  conditions=prepared$conditions,comparison=prepared$comparison,
  source_statistic_kind_declared=prepared$statistic_kind_declared,
  versions=versions,summary=list(input_genes=length(genes),returned_TF_resource_rows=nrow(rows),
    retained_unestimated_TF_resource_rows=length(missing),independent_replications=FALSE),
  limits=c("ULM infers associations from TF target patterns. It does not measure TF protein activity, establish causal direction, or validate a treatment target.",
    "ULM pvalues use a gene-background regression. They are not patient-level causal probabilities; correlated genes and shared priors matter.",
    "DoRothEA and CollecTRI are partly overlapping knowledge on the same input, not independent experimental replications.",
    "Resources and confidence/sign transformations are frozen. Opposite signs or missing TFs require conditional review, not automatic rejection.",
    "All eligible TF results and resource gaps are retained. The optional focus list does not limit inference or discovery.",
    "Input identity, gene mapping, contrast and covariate assumptions require source review. A declared statistic kind alone does not prove its scientific validity."))
write_json(result,args[2],pretty=TRUE,auto_unbox=TRUE,digits=NA,na="null")
