// Uploaded originals and extracted text remain separate, linked records.
function uploadedSourceOriginalURL(id){
  return `/api/workspaces/${encodeURIComponent(state.id)}/artifacts/${encodeURIComponent(id)}?original=1`;
}
function uploadedSourceMetadata(result){
  const metadata=result.supplied_metadata??{};
  return metadata.context||metadata.citation
    ? `<details class="meta-details"><summary>연구자가 함께 적은 조건·출처</summary>${metadata.context?`<p class="prose small">${esc(metadata.context)}</p>`:''}${metadata.citation?`<p class="prose small">${esc(typeof metadata.citation==='string'?metadata.citation:JSON.stringify(metadata.citation))}</p>`:''}</details>`:'';
}
function uploadedSourceReadingScope(result){
  return result.limits?.length?`<details class="meta-details"><summary>읽은 범위와 원본에서 확인할 부분</summary>${result.limits.map(value=>`<p class="small">${esc(value)}</p>`).join('')}</details>`:'';
}
function uploadedSourceFileView(result,artifact){
  const original=uploadedSourceOriginalURL(artifact.id);
  // A source drawer retains its original reading snapshot. Job status and newly
  // linked extraction records come from the current workspace, as in native inspect.
  const currentJobs=(state.jobs??[]).filter(job=>job.kind==='source_document'&&job.request?.artifact_id===artifact.id);
  const jobs=currentJobs.length?currentJobs.slice(-1):result.extraction_jobs??(result.extraction_job?[result.extraction_job]:[]);
  const derived=[...new Set([...(result.source_document_artifact_ids??result.derived_artifact_ids??[]),
    ...(state.artifacts??[]).filter(item=>item.kind==='source_document'&&item.meta?.consumed_artifacts?.includes(artifact.id)).map(item=>item.id)])];
  const statusLabels={queued:'본문 준비 대기',running:'문서의 문자층 읽는 중',succeeded:'문서 본문 준비 완료',partial:'일부 본문 준비',failed:'문서 판독 확인 필요',interrupted:'문서 판독 중단'};
  return `<p>업로드한 원본 파일을 보존했습니다.</p><a href="${original}" target="_blank" rel="noopener noreferrer">보존한 원본 파일 열기 ↗</a>${uploadedSourceMetadata(result)}
    ${jobs.map(job=>`<p class="small" role="status">${esc(statusLabels[job.status]??job.status)}${job.error?` · ${esc(job.error)}`:''}</p>`).join('')}
    ${derived.length?`<h3>원본에서 읽은 문서 본문</h3>${sourceLinks(derived)}<p class="small muted">본문의 문단·페이지와 읽기 상태를 확인한 뒤 연구 질문에 연결하세요.</p>`:'<p class="small muted">문자층 읽기가 끝나면 여기에서 문서 본문을 열 수 있습니다.</p>'}${uploadedSourceReadingScope(result)}`;
}
function uploadedSourceDocumentView(result){
  const extraction=result.extraction??{},rows=result.rows??[];
  const original=uploadedSourceOriginalURL(result.source_artifact_id);
  const outcome={text_extracted:'문서 본문 준비 완료',partial_text:'일부 본문 준비 · 원본 확인 필요',no_text:'읽을 수 있는 문자층을 찾지 못했습니다',failed:'문서 판독 확인 필요'};
  const warnings=extraction.warnings??[];
  const emptyPages=Array.isArray(extraction.empty_text_pages)?extraction.empty_text_pages:rows.filter(row=>row.kind==='pdf_page'&&!row.text).map(row=>row.page_number);
  const emptyCount=typeof result.summary?.empty_text_pages==='number'?result.summary.empty_text_pages:emptyPages.length;
  const pageLabel=result.document_format==='pdf'?'페이지':'문단';
  const start=result.offset??0,total=result.total_rows??rows.length;
  return `<p><strong>${esc(outcome[extraction.status]??'보존한 원본에서 읽은 본문')}</strong></p>
    <a href="${original}" target="_blank" rel="noopener noreferrer">보존한 원본 파일 열기 ↗</a>
    ${uploadedSourceMetadata(result)}
    ${uploadedSourceReadingScope(result)}
    ${warnings.length?`<aside class="notice-inline"><strong>원본과 대조할 부분</strong>${warnings.map(w=>`<p class="small">${esc(typeof w==='string'?w:w.message??JSON.stringify(w))}</p>`).join('')}</aside>`:''}
    ${emptyCount?`<p class="limit">문자층이 없는 페이지 ${number(emptyCount)}개${emptyPages.length?` · 현재 범위의 ${emptyPages.map(esc).join(', ')}쪽`:''}. 해당 페이지의 그림·표는 원본에서 확인하세요.</p>`:''}
    ${!rows.length?'<p class="small">원본을 열어 내용을 확인하고, 필요한 본문을 UTF-8 텍스트로 추가하면 문단 위치와 연결해 검토할 수 있습니다.</p>':''}
    ${rows.map((row,index)=>{
      const pdf=row.kind==='pdf_page',position=pdf?`원문 ${row.page_number}쪽`:`문단 ${row.paragraph_number??start+index+1}`;
      const pageURL=pdf&&Number.isInteger(row.page_number)&&row.page_number>0?`${original}#page=${row.page_number}`:original;
      return `<article class="article-block source-document-block"><h3>${esc(position)}</h3>${row.text?`<pre class="raw">${esc(row.text)}</pre>`:'<p class="small muted">이 위치의 문자층이 비어 있습니다. 보존한 원본에서 확인하세요.</p>'}
        <a class="small" href="${pageURL}" target="_blank" rel="noopener noreferrer">${pdf?'보존한 원본의 이 페이지 열기':'보존한 원본 파일 열기'} ↗</a>
        <details class="source-technical-locator"><summary>이 ${pdf?'페이지':'문단'}의 원본 위치</summary><p class="small">${esc(row.row_id??'')} · 저장된 본문 ${number(start+index+1)}행</p>${Number.isInteger(row.line_start)?`<p class="small">원본 텍스트 ${number(row.line_start)}–${number(row.line_end)}행</p>`:''}${Number.isInteger(row.byte_start)?`<p class="small">원본 바이트 ${number(row.byte_start)}–${number(row.byte_end)} (끝 위치 제외)</p>`:''}</details>
      </article>`;
    }).join('')}
    <div class="pagination"><span>${pageLabel} ${rows.length?start+1:0}–${start+rows.length} / ${number(total)}</span><div>${button('prev','이전',start===0?'disabled':'','small')}${button('next','다음',!result.has_more?'disabled':'','small')}</div></div>`;
}
