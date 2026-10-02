Object.assign(SCIENCE_LABELS,{gtopdb_pharmacology:'표적의 작용 물질과 약리 근거'});

function gtopdbEntry(){
 return '<section class="panel science-form"><h3>이 표적에 작용하는 물질 찾아보기</h3><p>GtoPdb에서 작용 물질과 측정 근거를 확인합니다. 찾은 물질은 전체 선택지에도 남습니다.</p>'+
 scienceInput('gtopdb-gene','확인할 표적의 유전자 기호','예: AVPR2')+
 '<label>표적의 종<select id="gtopdb-species"><option value="Human">사람 표적</option><option value="Mouse">마우스 표적</option><option value="Rat">랫드 표적</option></select></label>'+
 button('science-gtopdb-fetch','작용 물질과 근거 찾기',busy?'disabled':'','small')+
 '<p class="limit">물질을 찾았다는 사실만으로 이 질환의 치료 후보로 추천하지 않습니다.</p></section>';
}

async function gtopdbAction(action,node){
 const gene=node.dataset.gene||document.querySelector('#gtopdb-gene').value.trim();
 const species=node.dataset.gene?'Human':document.querySelector('#gtopdb-species').value;
 await runTool('gtopdb_pharmacology',{gene_symbol:gene,species});
}

function gtopdbTable(result){
 const labels={Agonist:'작용제',Antagonist:'길항제',None:'작용 미확인',Inhibitor:'억제제'};
 const action=r=>r.curated_action?.status==='reported'?(labels[r.curated_action.action]||r.curated_action.action):'작용 미확인';
 const measure=r=>[r.measurement?.parameter,r.measurement?.value_as_reported].filter(x=>x!==null&&x!==undefined&&x!=='').join(' ')||'측정값 미반환';
 const meaning=r=>r.measurement?.kind==='binding_affinity'?'결합 지표 · 기능 효과 아님':r.measurement?.kind==='unclassified'?'측정 해석 미확인':'시험 조건 확인 필요';
 const plain=v=>String(v||'').replace(/<\/?(?:sub|sup|i|b)>/gi,'');
 const pmids=r=>(r.pmids||[]).filter(x=>/^\d+$/.test(String(x))).map(x=>'<a href="https://pubmed.ncbi.nlm.nih.gov/'+esc(x)+'/" target="_blank" rel="noopener noreferrer">PMID '+esc(x)+'</a>').join(', ')||'PMID 미반환';
 return '<h3>'+esc(result.target?.queried_gene_symbol||result.query?.gene_symbol||'표적')+' · '+esc(plain(result.target?.name||'표적 확인 필요'))+'</h3>'+
 '<p>작용 방향은 GtoPdb의 큐레이션 기록이며, 결합 수치와 별도로 봅니다. 사람 표적 실험이 사람 임상시험을 뜻하지는 않습니다.</p>'+
 (result.status!=='succeeded'?'<p class="limit">'+esc(result.error||'조회 미완료 · 약리 근거 0건이 아닙니다.')+'</p>':'')+
 '<div class="table-scroll"><table class="pharmacology-table"><thead><tr><th>물질</th><th>기록된 작용</th><th>측정</th><th>실험 조건</th><th>원문 확인</th></tr></thead><tbody>'+
 (result.rows||[]).map(r=>'<tr><td>'+esc(plain(r.ligand_name))+'</td><td>'+esc(action(r))+'</td><td>'+esc(measure(r))+'<br><small>'+esc(meaning(r))+'</small></td><td>'+esc(r.missing_condition_fields?.length?'일부 조건 미확인':r.raw_record?.assayDescription||'상세 원자료 확인')+'</td><td>'+'<details><summary>원문 '+number((r.pmids||[]).length)+'편</summary>'+pmids(r)+'</details></td></tr>').join('')+
 '</tbody></table></div>'+storedSourcePages(result)+'<p>IUPHAR/BPS Guide to PHARMACOLOGY · 데이터베이스 ODbL · 콘텐츠 CC BY-SA 4.0</p>'+
 '<details><summary>전체 근거와 미확인 범위</summary><p>참고문헌 링크는 원문 읽기 완료 표시가 아닙니다. 전체 결과를 내려받으면 원 측정값·조건·참고문헌을 확인할 수 있습니다.</p>'+
 (result.limits||[]).map(x=>'<p>'+esc(x)+'</p>').join('')+'</details>';
}
