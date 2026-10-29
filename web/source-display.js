// Presentation only: never rewrite a quote, original record, locator or identity.
function sourceDisplayText(value){
 let text=String(value??'');
 const entities={amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' ',ndash:'–',mdash:'—',micro:'µ'};
 for(let i=0;i<2;i++)text=text.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp|ndash|mdash|micro);/gi,(whole,name)=>{if(name[0]!=='#')return entities[name.toLowerCase()]??whole;const n=name[1].toLowerCase()==='x'?parseInt(name.slice(2),16):parseInt(name.slice(1),10);return n>0&&n<=0x10ffff&&!(n>=0xd800&&n<=0xdfff)?String.fromCodePoint(n):whole});
 return text.replace(/<\/?(?:sub|sup)\b[^>]*>/gi,'');
}
function sourceBibliography(result,row){
 const actual=row??(Array.isArray(result?.rows)&&result.rows.length===1?result.rows[0]:null);
 const value=actual??(result?.semantic_type==='open_article'||result?.pmc_id?result:null);
 if(!value)return null;
 const title=value.title??value.articleTitle;
 if(typeof title!=='string'||!title.trim())return null;
 const authors=value.authorString??value.authors??value.author;
 return {title:sourceDisplayText(title),authors:typeof authors==='string'?sourceDisplayText(authors):null,year:value.pubYear??value.year??value.publicationYear??null,studyType:value.publicationType??value.study_type??value.publication_types??value.pubTypeList?.pubType??null,pmid:value.pmid??(value.source==='MED'?value.id:null),doi:value.doi??null};
}
function sourceDisplayLabel(artifact,result,row){
 const b=sourceBibliography(result,row);
 if(b)return [b.authors?.includes(',')?b.authors.split(',')[0]+' 외':b.authors,b.year,b.title.length>130?b.title.slice(0,130)+'…':b.title].filter(Boolean).join(' · ');
 if(artifact?.kind==='literature')return '검색 결과 묶음';
 if(artifact?.kind==='public_lookup_bundle')return '공개 자료 조회 묶음';
 if(artifact?.kind==='webpage')return '웹 자료 · '+sourceDisplayText(artifact.source_title??artifact.title??'문헌');
 if(artifact?.kind==='article')return '보존한 원문 · '+sourceDisplayText(artifact.title??'문헌');
 return sourceDisplayText(artifact?.title??'자료 묶음');
}
function sourceBibliographyView(result,row){
 const b=sourceBibliography(result,row);if(!b)return '<p class="small muted">검색 결과 묶음 · 특정 문헌은 연결된 원행에서 확인하세요.</p>';
 return `<section class="source-bibliography"><strong>${esc(b.title)}</strong><p class="small">${[b.authors,b.year,Array.isArray(b.studyType)?b.studyType.join(' · '):b.studyType].filter(Boolean).map(esc).join(' · ')}</p>${b.pmid||b.doi?`<p class="small">${b.pmid?'PMID '+esc(b.pmid):''}${b.doi?' · DOI '+esc(b.doi):''}</p>`:''}</section>`;
}
function sourceLocatorDetails(artifact,anchor){return `<details class="source-technical-locator"><summary>출처 위치·조회 기록</summary><p>${esc(artifact?.title??'')} · <code>${esc(artifact?.id??'')}</code></p>${Number.isInteger(anchor?.offset)?`<p>저장 원행 인덱스 ${anchor.offset} · 0부터 셈</p>`:''}${Number.isInteger(anchor?.row_index)?`<p>저장 원행 인덱스 ${anchor.row_index} · 0부터 셈</p>`:''}</details>`;}
function sourceAssertionAnchorView(anchor,check){
 if(!anchor?.artifact_id)return '';
 const binding=check?.source_binding??anchor.source_binding,location=binding?.location??{},original=binding?.original??{};
 const row=Number.isInteger(anchor.row_index)?anchor.row_index:binding?.row_index;
 const located=Number.isInteger(row)&&row>=0;
 const page=Number.isInteger(location.page_number)&&location.page_number>0?location.page_number:null;
 const paragraph=Number.isInteger(location.paragraph_number)&&location.paragraph_number>0?location.paragraph_number:null;
 const position=page?`원문 ${page}쪽`:paragraph?`원문 문단 ${paragraph}`:located?`보존한 본문 ${row+1}행`:'';
 const origin=binding?.source_kind==='source_document'?'연구자가 제공한 문서':binding?.source_kind==='webpage'?'웹에서 가져온 본문':'';
 const attrs=`data-id="${esc(anchor.artifact_id)}"${located?` data-source-offset="${row}"`:''}${anchor.quote?` data-source-quote="${esc(anchor.quote)}"`:''}`;
 let originalLink='';
 if(binding?.source_kind==='source_document'&&original.artifact_id){
  const href=`/api/workspaces/${encodeURIComponent(state.id)}/artifacts/${encodeURIComponent(original.artifact_id)}?original=1${page?`#page=${page}`:''}`;
  originalLink=`<a class="source-link" href="${href}" target="_blank" rel="noopener noreferrer">${page?'보존한 원본의 이 페이지 열기':'보존한 원본 파일 열기'} ↗</a>`;
 }else if(binding?.source_kind==='webpage'&&typeof externalAnchor==='function'){
  originalLink=externalAnchor('url',original.resolved_url??original.url,'웹 원본 열기 ↗');
 }
 const technical=binding?`<details class="source-technical-locator"><summary>연결한 원문 판본·위치</summary><p class="small">${esc(binding.text_locator??'')} · ${esc(binding.row_id??'')}</p>${Number.isInteger(location.line_start)?`<p class="small">원본 텍스트 ${location.line_start}–${esc(location.line_end)}행</p>`:''}${Number.isInteger(location.byte_start)?`<p class="small">원본 바이트 ${location.byte_start}–${esc(location.byte_end)} (끝 위치 제외)</p>`:''}${original.sha256?`<p class="small">원본 SHA256 <code>${esc(original.sha256)}</code></p>`:''}${binding.artifact_sha256?`<p class="small">인용 자료 SHA256 <code>${esc(binding.artifact_sha256)}</code></p>`:''}</details>`:'';
 const extractionNote=binding?.extraction?.details?.status==='partial_text'?'<p class="small">문서에 추출 한계가 있습니다. 인용한 위치를 원본과 대조해 주세요.</p>':'';
 return `<div class="source-assertion" data-source-assertion="${esc(anchor.artifact_id)}">${origin||position?`<p class="small muted">${esc([origin,position].filter(Boolean).join(' · '))}</p>`:''}${extractionNote}<div class="source-links">${button('source',located?'인용한 원문 위치 열기':'연결한 원문 열기',attrs,'link-button small')}${originalLink}</div>${technical}</div>`;
}
// Call only for display titles in an already-created source view. TextContent prevents external HTML execution.
function normalizeSourceTitleNodes(container){for(const node of container.querySelectorAll('.source-bibliography strong, .source-paragraph h3, td a[href*="europepmc.org"]'))node.textContent=sourceDisplayText(node.textContent);}
function sourceFigureScope(figure){
 // Caption remains exact; no guessed drug/model/readout from a title or thumbnail.
 const caption=String(figure?.caption??'');
 if(!/BI\s*1015550/i.test(caption)||!/PBMC|peripheral blood mononuclear/i.test(caption)||!/TNF|tumor necrosis/i.test(caption)||!/IL-2|interleukin-2/i.test(caption))return '<p class="small muted">원논문의 시험 물질·모델·판독은 원 캡션에서 확인하세요.</p>';
 return '<p class="small muted">원논문 범위: BI 1015550 · 사람 PBMC의 cytokine 판독(TNF-α·IL-2). 이 그림의 측정 대상은 BI 1015550이며, 생성 후보의 기능은 후보별 시험에서 확인합니다.</p>';
}

const sourceDisplayCache=new Map();
function sourceDisplayRow(artifact,anchor,wid=state?.id){
 if(!artifact||anchor?.artifact_id!==artifact.id||!Number.isInteger(anchor.row_index))return null;
 return sourceDisplayCache.get(`${wid}:${artifact.id}:${artifact.sha256}:${anchor.row_index}`)?.row??null;
}
async function warmSourceDisplayAnchors(snapshot,request=api){
 const anchors=(snapshot?.discovery?.mechanisms_and_approaches??[]).concat(snapshot?.discovery?.recommendations??[]).flatMap(item=>item.assessment?.basis?.clauses??[]).map(c=>c.anchor).filter(a=>a?.artifact_id&&Number.isInteger(a.row_index)&&a.row_index>=0);
 const requests=[];
 for(const anchor of anchors){
  const artifact=snapshot.artifacts.find(a=>a.id===anchor.artifact_id);if(!artifact)continue;
  const key=`${snapshot.id}:${artifact.id}:${artifact.sha256}:${anchor.row_index}`;if(sourceDisplayCache.has(key))continue;
  sourceDisplayCache.set(key,{pending:true});
  requests.push((async()=>{try{const value=await request(`/api/workspaces/${encodeURIComponent(snapshot.id)}/artifacts/${encodeURIComponent(artifact.id)}?offset=${anchor.row_index}&limit=1`);const row=value.result?.rows?.[0];sourceDisplayCache.set(key,{row:value.result?.offset===anchor.row_index?row:null});}catch(_){sourceDisplayCache.set(key,{row:null});}})());
  if(requests.length>=16)break;
 }
 await Promise.all(requests);
}
