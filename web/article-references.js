const articleReferenceModes=new Map();
function articleReferenceQuery(id){
 const value=articleReferenceModes.get(id);if(!value)return '';
 return '&references=1'+value.map(x=>'&reference_id='+encodeURIComponent(x)).join('');
}
async function openArticleReferences(node){
 const ids=JSON.parse(node.dataset.referenceIds??'[]'),next=Number(node.dataset.offset??0);
 if(!Array.isArray(ids)||!Number.isInteger(next)||next<0)throw Error('참고문헌 위치를 확인해 주세요.');
 articleReferenceModes.set(selected,ids);offset=next;await readDetail();
 document.querySelector('.data-detail')?.scrollIntoView({block:'start'});
}
function articleCitationButtons(row){
 const ids=[...new Set((row.citation_markers??[]).flatMap(m=>m.reference_ids))];
 return ids.length?button('article-references','이 문단이 인용한 원전 찾기',`data-reference-ids="${esc(JSON.stringify(ids))}"`,'link-button small'):'';
}
function articleReferencesView(result){
 const ids=JSON.stringify(result.selected_reference_ids??[]);
 const links=r=>(r.article_ids??[]).filter((x,i,all)=>all.findIndex(y=>y.type===x.type&&y.value===x.value)===i).map(x=>{
  const url=x.type==='pmid'?'https://pubmed.ncbi.nlm.nih.gov/'+encodeURIComponent(x.value)+'/':x.type==='doi'?'https://doi.org/'+encodeURIComponent(x.value):null;
  return url?`<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(x.type.toUpperCase())} ${esc(x.value)} ↗</a>`:`<span>${esc(x.type)} ${esc(x.value)}</span>`;
 }).join(' · ');
 return `<h3>인용한 원전 · ${esc(result.title??result.pmc_id)}</h3><p>이 목록은 현재 논문이 인용한 문헌입니다. 원전을 열어 대상·조건과 실제 결과를 확인할 수 있습니다.</p>${button('article-section','본문으로 돌아가기','data-offset="0"','small')}${result.selected_reference_ids?.length?button('article-references','전체 참고문헌 보기','data-reference-ids="[]"','small'):''}${result.unresolved_reference_ids?.length?`<p class="notice-inline">목록에서 확인되지 않은 원 ID: ${esc(result.unresolved_reference_ids.join(', '))}</p>`:''}${result.rows.map(r=>`<article class="article-block"><div class="small muted">${esc(r.original_label??r.reference_id??'원 번호 없음')}</div><p>${esc(r.display_citation??r.text)}</p><p>${links(r)}</p><div class="detail-actions">${r.citation_contexts.map(c=>button('article-section',esc(c.section||'본문')+' · 인용 문맥 확인',`data-offset="${c.offset}"`,'small')).join('')}</div></article>`).join('')}<div class="pagination"><span>현재 선택의 ${result.rows.length?result.offset+1:0}–${result.offset+result.rows.length} / ${result.total_rows}개 · 원 목록 ${result.source_total_references}개</span><div>${button('article-references','앞 참고문헌',`data-reference-ids="${esc(ids)}" data-offset="${Math.max(0,result.offset-30)}" ${result.offset===0?'disabled':''}`,'small')}${button('article-references','뒤 참고문헌',`data-reference-ids="${esc(ids)}" data-offset="${result.offset+30}" ${!result.has_more?'disabled':''}`,'small')}</div></div><p class="limit">인용 목록과 연결을 확인한 것이며, 인용된 문헌의 읽기·주장 검증을 완료한 것은 아닙니다.</p>`;
}
