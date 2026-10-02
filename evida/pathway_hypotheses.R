args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==2L)
suppressPackageStartupMessages({library(CARNIVAL);library(jsonlite)})
input <- fromJSON(args[1],simplifyVector=FALSE)
stopifnot(as.character(getRversion())==input$required_versions$R,
  as.character(packageVersion("CARNIVAL"))==input$required_versions$CARNIVAL)
network <- do.call(rbind,lapply(input$network,function(x)data.frame(
  source=x$source,interaction=x$interaction,target=x$target)))
selected <- input$selected_inferred_observations
measurements <- setNames(vapply(selected,function(x)x$score,numeric(1)),
  vapply(selected,function(x)x$source,character(1)))
options <- defaultCbcSolveCarnivalOptions()
options$solverPath <- input$solver_path
options$outputFolder <- file.path(dirname(args[2]),"solver")
dir.create(options$outputFolder)
options$workdir <- options$outputFolder
options$timelimit <- input$solver_time_limit_seconds
options$threads <- 1
options$cleanTmpFiles <- FALSE
options$keepLPFiles <- TRUE
write_json(options,file.path(dirname(args[2]),"solver-options.json"),pretty=TRUE,auto_unbox=TRUE,digits=NA)
fit <- runInverseCarnival(measurements=measurements,priorKnowledgeNetwork=network,carnivalOptions=options)
saveRDS(fit,file.path(dirname(args[2]),"author-result.rds"))
stopifnot(length(fit$attributesAll)>0L,length(fit$sifAll)>0L)
rows <- list()
for (i in seq_along(fit$sifAll)) {
  for (j in seq_len(nrow(fit$sifAll[[i]]))) {
    edge <- fit$sifAll[[i]][j,,drop=FALSE]
    rows[[length(rows)+1L]] <- list(network_index=i,source=edge$Node1,
      sign=edge$Sign,target=edge$Node2,artificial_root_edge=edge$Node1=="Perturbation")
  }
}
result <- list(status="returned_requires_solver_review",semantic_type="conditional_pathway_hypotheses",
  method="Actual CARNIVAL runInverseCarnival with CBC on a declared bounded signed prior",
  author_result=fit,rows=rows,selected_inferred_observations=selected,
  source_conditions=input$source_conditions,conditions=input$requested_conditions,
  selection_reason=input$selection_reason,search_scope=input$search_scope,
  versions=list(R=as.character(getRversion()),CARNIVAL=as.character(packageVersion("CARNIVAL"))),
  limits=c("알려진 상호작용과 선택한 추정 신호를 설명하는 경로 후보입니다. 원인·치료 표적·효능을 검증한 결과가 아닙니다.",
    "전사인자 입력도 발현 자료에서 추정한 값입니다. 실제 단백질 활성 관측이나 인과 확률로 치환하지 않습니다.",
    "전체 후보와 원 상호작용망은 보존하지만 이 계산은 명시한 상류 탐색 범위에 한정됩니다. 범위 밖에 경로가 없다는 뜻이 아닙니다.",
    "가상 Perturbation 노드와 그 연결은 최적화 표현입니다. 이름이 없는 실제 약물·처치나 확인한 생물학적 원인으로 해석하지 않습니다.",
    "최적해 한 개가 유일한 기전을 뜻하지 않습니다. 선택한 관측·조절망·상호작용망이 달라지면 다른 설명이 나올 수 있습니다.",
    "최적성은 계산한 목적함수와 탐색 범위에 대한 뜻이며 임상적 타당성이나 후보 우열의 보증이 아닙니다."))
write_json(result,args[2],pretty=TRUE,auto_unbox=TRUE,digits=NA,na="null")
