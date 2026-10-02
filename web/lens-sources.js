Object.assign(SCIENCE_LABELS,{lens_literature:'문헌 검색과 인용 연결'});
function lensEntry(){return '<section class="panel science-form"><h3>다른 접근과 연결 문헌 찾기</h3><p>질환·기전 검색과 원전의 참고문헌·후속 인용을 함께 살펴볼 수 있습니다.</p>'+scienceInput('lens-query','검색어 또는 논문 DOI','질환, 확인할 질문, 논문 DOI 또는 Lens ID')+button('science-lens-search','Lens 문헌 검색',busy?'disabled':'','small')+'<p class="limit">검색된 문헌은 읽기 후보입니다. 제목이나 인용만으로 치료 후보로 추천하지 않습니다.</p></section>'}
async function lensAction(action,node){
 const mode=action==='science-lens-search'?'search':node.dataset.mode;
 const query=mode==='search'?(node.dataset.query||document.querySelector('#lens-query').value.trim()):'';
 await runTool('lens_literature',{mode,query,lens_id:mode==='search'?'':node.dataset.lensId,offset:Number(node.dataset.offset||0),limit:20});
}
function lensTable(result){
 const names={search:'독립 문헌 검색',references:'이 논문의 참고문헌',citing:'이 논문을 인용한 후속 문헌'};
 const summary=result.summary||{},query=result.query||{};
 return '<h3>'+esc(names[query.mode]||'문헌 조회')+'</h3><p>이번 원페이지 '+number(summary.returned)+'편 / 검색 범위 전체 '+number(summary.source_total)+'편. 원문·주장의 타당성은 추가로 확인합니다.</p>'+
 '<div class="lens-records">'+(result.rows||[]).map(r=>'<article class="lens-record"><h4>'+esc(r.title||'제목 미반환')+'</h4><p>'+esc(r.year_published||'발행연도 미반환')+' · Lens '+esc(r.lens_id)+'</p>'+
 (r.abstract?'<details><summary>반환된 초록</summary><p>'+esc(r.abstract)+'</p></details>':'<p class="limit">초록 미반환 · 원문 확인 필요</p>')+
 '<div class="detail-actions">'+button('science-lens-citation','참고문헌 찾기','data-mode="references" data-lens-id="'+esc(r.lens_id)+'"','small')+button('science-lens-citation','후속 인용 찾기','data-mode="citing" data-lens-id="'+esc(r.lens_id)+'"','small')+'</div></article>').join('')+'</div>'+
 storedSourcePages(result)+
 (summary.source_has_more?button('science-lens-next','다음 원페이지 조회','data-mode="'+esc(query.mode)+'" data-query="'+esc(query.query)+'" data-lens-id="'+esc(query.lens_id)+'" data-offset="'+result.frontier.next_source_offset+'"','small'):'')+
 '<p class="limit">한 번의 인용 조회는 탐색 깊이의 상한이 아닙니다. 필요한 원전을 다시 출발점으로 삼을 수 있으며, 인용망 밖 검색도 열려 있습니다.</p>';
}

function storedSourcePages(result){
 if(!Number.isInteger(result.total_rows))return '';
 const start=result.offset||0,count=(result.rows||[]).length;
 return '<div class="pagination"><span>보존한 자료 '+number(count?start+1:0)+'–'+number(start+count)+' / '+number(result.total_rows)+'행</span><div>'+button('prev','이전',start===0?'disabled':'','small')+button('next','다음',!result.has_more?'disabled':'','small')+'</div></div>';
}
