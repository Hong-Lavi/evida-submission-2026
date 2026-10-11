args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==2L)
suppressPackageStartupMessages({library(decoupleR);library(jsonlite)})
request <- fromJSON(args[[1]],simplifyVector=FALSE)
stopifnot(as.character(getRversion())=="4.4.3",as.character(packageVersion("decoupleR"))=="2.12.0")
stopifnot(request$method %in% c("ulm","mlm","wmean"))
started <- proc.time(); warnings_seen <- character(); entered_method <- FALSE
result <- tryCatch(withCallingHandlers({
 genes <- unlist(request$genes,use.names=FALSE)
 ids <- vapply(request$tasks,function(x)x$task_id,character(1))
 stopifnot(!anyDuplicated(genes),!anyDuplicated(ids))
 mat <- vapply(request$tasks,function(x)as.numeric(unlist(x$values)),numeric(length(genes)))
 if (is.null(dim(mat)))mat <- matrix(mat,ncol=1)
 rownames(mat)<-genes;colnames(mat)<-ids
 stopifnot(all(is.finite(mat)))
 net<-read.delim(request$network_path,check.names=FALSE)
 entered_method <- TRUE
 scores <- switch(request$method,
  ulm=decoupleR::run_ulm(mat,net,minsize=5L,center=FALSE,sparse=FALSE,na.rm=FALSE),
  mlm=decoupleR::run_mlm(mat,net,minsize=5L,center=FALSE,sparse=FALSE,na.rm=FALSE),
  wmean=decoupleR::run_wmean(mat,net,minsize=5L,times=2L,seed=0L,sparse=FALSE,randomize_type="rows"))
 list(status="succeeded",method=request$method,rows=as.data.frame(scores),error=NULL)
},warning=function(w){warnings_seen<<-c(warnings_seen,conditionMessage(w));invokeRestart("muffleWarning")}),error=function(e){list(status="failed_method",method=request$method,rows=list(),error=conditionMessage(e))})
result$versions<-list(R=as.character(getRversion()),decoupleR=as.character(packageVersion("decoupleR")))
result$package_path<-normalizePath(find.package("decoupleR"));result$r_home<-normalizePath(R.home())
result$warnings<-warnings_seen;result$entered_method<-entered_method
result$cpu_seconds<-unname((proc.time()-started)[1:2]);result$elapsed_seconds<-unname((proc.time()-started)[3])
tmp<-paste0(args[[2]],".partial")
write_json(result,tmp,auto_unbox=TRUE,pretty=TRUE,digits=NA,na="null")
stopifnot(file.rename(tmp,args[[2]]))
