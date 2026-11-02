// Display server-reported waiting state; never changes model or starts a retry.
function renderModelRecovery(workspace=state){
  const recovery=workspace?.model_recovery;
  if(!recovery||!workspace.jobs?.some(job=>job.id===recovery.job_id&&job.status==='running'))return '';
  const retryAt=new Date(recovery.retry_at);
  const retryLabel=recovery.retry_at&&!Number.isNaN(retryAt.getTime())?retryAt.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'';
  return `<div class="model-recovery" role="status" aria-live="polite"><p>모델이 혼잡해 같은 모델의 응답을 기다리고 있습니다. 연구 기록을 보존하고 이어서 실행합니다.</p>${retryLabel?`<p class="small muted">다음 응답 요청 예정 · ${esc(retryLabel)} (현재 기기 시각)</p>`:''}</div>`;
}
