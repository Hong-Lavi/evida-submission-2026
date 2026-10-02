// Browser-only projections of saved records. Never a scientific rank or a stored relation.
const uiGenerationViews=new Map(), uiExperimentReturns=new Map();
function uiCurrentPaths(){
  return pathMechanisms().filter(x=>pathCurrent(x.assessment)&&x.assessment.status!=='deferred');
}
function uiPathKind(option){return option.kind==='approach'?'설계·시험 접근':'생물학적 기전'}
function uiDecisionScope(){
  const paths=uiCurrentPaths(),mechanisms=paths.filter(x=>x.kind==='mechanism').length;
  const approaches=paths.filter(x=>x.kind==='approach').length,checks=state.decision?.research_loop?.next_checks?.length??0;
  return [mechanisms?`기전 ${mechanisms}개`:null,approaches?`접근 ${approaches}개`:null,`다음 확인 ${checks}건`].filter(Boolean).join(' · ');
}
function uiPathSummary(){return uiCurrentPaths().map(x=>`<li><span class="ui-eyebrow">${esc(uiPathKind(x))}</span><strong>${esc(researcherWording(x.label))}</strong><span>${esc(optionStatus[x.assessment.status])}</span></li>`).join('')}
function uiGenerationKey(id){return `${candidateStructuresKey()}:${id}`}
function uiGenerationData(id){return uiGenerationViews.get(uiGenerationKey(id))}
async function uiLoadGeneration(id){
  const wid=state.id,key=uiGenerationKey(id);if(uiGenerationViews.has(key))return;
  const artifact=state.artifacts.find(x=>x.id===id&&x.kind==='analogue_proposal');if(!artifact)return;
  uiGenerationViews.set(key,{loading:true});
  try{const value=await api(`/api/workspaces/${encodeURIComponent(wid)}/artifacts/${encodeURIComponent(id)}?offset=0&limit=100`);
    if(uiGenerationKey(id)!==key)return;
    uiGenerationViews.set(key,{value,artifact});
  }catch(error){if(uiGenerationKey(id)===key)uiGenerationViews.set(key,{error:'생성 원자료를 읽지 못했습니다.'})}
  if(uiGenerationKey(id)===key)render();
}
function uiGenerationCount(item){
  const data=uiGenerationData(item?.candidate_artifact_id)?.value?.result;
  return Number.isInteger(data?.total_rows)?data.total_rows:data?.has_more===false?data.rows?.length:null;
}
function uiCandidateRole(item){
  if(item?.origin!=='generated_structure_proposal')return '';
  const a=item.assessment,reason=a?.reason??'',count=uiGenerationCount(item);
  const role=reason.includes('시험 대응 예시')?'시험 대응 예시':a?'개별 검토한 생성 후보':'생성 집합의 후보 · 개별 검토 전';
  return `<p class="ui-candidate-role"><strong>${esc(role)}</strong>${count!=null?` · 생성 집합 ${count}개 중 1개`:''}${reason.includes('시험 대응 예시')&&a.priority==null?' · 효능 순위 미부여':''}</p>`;
}
function uiGenerationLink(item){
  if(item?.origin!=='generated_structure_proposal'||!item.candidate_artifact_id)return '';
  const count=uiGenerationCount(item);
  queueMicrotask(()=>uiLoadGeneration(item.candidate_artifact_id));
  return button('ui-generated-group',count!=null?`같은 생성 집합 ${count}개 · 출발 화합물 보기`:'같은 생성 집합 · 출발 화합물 보기',`data-id="${esc(item.candidate_artifact_id)}"`,'link-button small');
}
function uiGeneratedGroup(panel){
  const data=uiGenerationData(panel.id);if(!data||data.loading)return '<p role="status">보존된 생성 목록을 읽고 있습니다.</p>';
  if(data.error)return uiEmpty(data.error);
  const result=data.value?.result??{},rows=result.rows??[];
  return `<p>같은 실행에서 생성한 ${esc(result.total_rows??rows.length)}개 구조를 원자료 순서로 표시합니다. 후보별 개별 검토 여부를 함께 확인하세요.</p><div class="ui-generated-list">${rows.map((row,i)=>{
    const id=`molecule:generated:${panel.id}:${row.candidate_id}`;
    const item=candidateOptions().find(x=>x.option_id===id),a=item?.assessment;
    return `<article class="ui-generated-row" data-generated-candidate="${esc(id)}">${structureThumb(row)}<div><h3>${esc(row.candidate_id)}</h3><p>출발 화합물 <strong>${esc(row.transformed_from??row.core_from??'확인 필요')}</strong></p><p class="small">${a?`${esc(optionStatus[a.status])} · ${uiRevision(a)}`:'개별 검토 전'} · 생성 단계 활성 미측정</p>${button('discovery-detail','이 후보 상세',`data-id="${esc(id)}"`,'small')}${button('source','생성 원행',`data-id="${esc(panel.id)}" data-source-offset="${(result.offset??0)+i}"`,'link-button small')}</div></article>`;
  }).join('')}</div>${result.has_more?uiEmpty('첫 페이지입니다. 생성 원자료에서 나머지 행을 확인하세요.'):''}${sourceLinks([panel.id])}`;
}
function uiTokenMention(text,value){
  if(!value)return false;
  const escaped=String(value).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  return new RegExp(`(^|[^A-Za-z0-9_-])${escaped}(?=$|[^A-Za-z0-9_-])`,'i').test(text);
}
function uiCandidateExperimentLinks(item,row,checks){
  const exact=[],mentioned=[],shared=[];
  const a=item.assessment??{},h=a.basis?.hypothesis_id;
  const sourceIds=new Set([item.candidate_artifact_id,...(a.support_source_ids??[]),...(item.sources??[]).map(x=>x.artifact_id)].filter(Boolean));
  const parent=item.generation?.transformed_from??row?.transformed_from??row?.core_from;
  const entity=item.entity_id??row?.candidate_id,match=String(entity??'').match(/^proposed-(\d+)$/);
  const aliases=[entity,item.option_id,...(match?[`제안 ${match[1]}`,`설계 후보 ${match[1]}`]:[])].filter(Boolean);
  for(const check of checks){
    const refs=[...(check.candidate_refs??[]),...(check.operation?.candidate_refs??[])];
    const explicit=refs.some(ref=>ref===item.option_id||ref?.option_id===item.option_id||(ref?.candidate_id===entity&&ref?.artifact_id===item.candidate_artifact_id));
    if(explicit||(h&&check.hypothesis_ids?.includes(h))){exact.push({check,label:explicit?'후보 ID로 연결됨':'후보 평가와 같은 가설에 연결됨'});continue}
    const text=[check.question,check.purpose,check.operation?.request].filter(Boolean).join('\n');
    const common=(check.operation?.grounded_in??[]).filter(id=>sourceIds.has(id));
    if(!common.length)continue;
    const named=aliases.some(alias=>uiTokenMention(text,alias));
    if(named&&(!parent||uiTokenMention(text,parent))){mentioned.push({check,label:'본문에 후보·비교 대상 명시 · 연결 확인 필요',common});continue}
    // A shared source is not a candidate edge. Do not associate another numbered proposal.
    if(!/(?:proposed-|제안\s*|설계 후보\s*)\d+/i.test(text))shared.push({check,label:'같은 자료를 인용한 권고 · 후보별 연결 확인 필요',common});
  }
  return {exact,mentioned,shared};
}
function uiRelatedExperiments(item,row){
  const links=uiCandidateExperimentLinks(item,row,state.decision?.research_loop?.next_checks??[]);
  const group=(title,rows)=>rows.length?`<section class="ui-related-group"><h3>${title}</h3>${rows.map(({check,label})=>`<p class="small muted">${esc(label)}</p>${button('ui-related-experiment',esc(uiExperimentAlias(check)),`data-id="${esc(check.id)}"`,'ui-linked-check')}<details><summary>권고 본문에서 확인</summary><p>${uiText(check.question)}</p></details>`).join('')}</section>`:'';
  return group('기록된 연결',links.exact)+group('본문으로 연결을 확인할 실험',links.mentioned)+group('자료를 함께 사용하는 권고',links.shared)+
    (!links.exact.length&&!links.mentioned.length&&!links.shared.length?uiEmpty('이 후보를 특정한 실험 연결 확인 필요'):'')+`<p class="small muted">본문 명시와 공통 자료는 저장된 후보–실험 ID 연결과 구분합니다.</p>${button('ui-stage','현재 연구의 실험 전체','data-stage="next"','small')}`;
}
async function uiLoadParentStructures(panel){
  const key=candidateStructuresKey(),wid=state.id;
  const links=panel.item.generation?.parent_links??[];
  const parent=panel.item.generation?.transformed_from??candidateStructureRow(panel.id)?.transformed_from;
  const actual=links.filter(x=>x.candidate_id===parent);
  panel.parentStructures=[];
  for(const link of actual){
    if(link.status!=='resolved'||link.option_ids?.length!==1){panel.parentStructures.push({link,missing:'출발 화합물의 유일한 구조 연결 확인 필요'});continue}
    try{const value=await api(`/api/workspaces/${encodeURIComponent(wid)}/candidate-structures?option_id=${encodeURIComponent(link.option_ids[0])}`);
      if(candidateStructuresKey()!==key)return;
      const row=value.rows?.find(x=>x.option_id===link.option_ids[0]);
      panel.parentStructures.push({link,row,missing:row?.depiction?.status==='drawn'?null:'연결된 출발 화합물에 그릴 수 있는 구조가 없습니다.'});
    }catch{panel.parentStructures.push({link,missing:'출발 화합물의 구조 자료를 읽지 못했습니다.'})}
  }
  panel.parentStructuresLoaded=true;if(candidateStructuresKey()===key&&currentReader()===panel)render();
}
function uiCandidatePair(panel,row){
  const item=panel.item;if(item.origin!=='generated_structure_proposal')return '';
  const actual=item.generation?.transformed_from??row?.transformed_from;
  const sources=item.generation?.source_artifact_ids??[];
  return `<section class="ui-structure-comparison"><h3>출발 화합물과 생성 후보</h3><p class="small muted">저장된 변환 관계와 구조 문자열을 나란히 표시합니다.</p><div class="ui-structure-pair"><article><h4>출발 화합물 · ${esc(actual??'관계 확인 필요')}</h4>${!panel.parentStructuresLoaded?'<p role="status">연결된 구조를 읽고 있습니다.</p>':panel.parentStructures?.length?panel.parentStructures.map(p=>`${p.row?structureFigure(p.row.depiction,p.link.candidate_id):''}${p.missing?uiEmpty(p.missing):''}${p.row?`<details><summary>출발 구조·원 기록</summary>${structureFacts(p.row)}${json(Object.fromEntries(Object.entries(p.row).filter(([k])=>k!=='depiction')))}</details>`:''}`).join(''):uiEmpty('출발 화합물의 구조화된 연결 확인 필요')}<p class="small">측정값과 시험 조건은 출발 자료에서 확인합니다.</p>${sourceLinks(sources)}</article><article><h4>생성 후보 · ${esc(item.entity_id)}</h4>${row?structureFigure(row.depiction,item.entity_id):uiEmpty('후보 구조 확인 필요')}<p class="small">생성 단계 활성 미측정</p>${sourceLinks([item.candidate_artifact_id])}</article></div></section>`;
}
function uiCandidateProperties(row){
  const copy={...row,depiction:{...row.depiction}};
  const massKnown=Number.isFinite(row.MolWt)&&Number.isFinite(row.depiction?.average_mass);
  const sameRounding=massKnown&&Math.abs(row.MolWt-row.depiction.average_mass)<=0.050001;
  if(Number.isFinite(row.MolWt)&&(sameRounding||!Number.isFinite(row.depiction?.average_mass)))copy.depiction.average_mass=String(row.MolWt);
  const massConflict=massKnown&&!sameRounding?`<p class="ui-missing">계산 기록 사이의 분자량 차이 확인 필요 · 생성 기록 ${esc(row.MolWt)} g/mol · 구조 묘사 계산 ${esc(row.depiction.average_mass)} g/mol</p>`:'';
  const defs=[['LogP','LogP','지용성 추정값입니다. 값이 높을수록 지용성이 큽니다.'],['TPSA','극성 표면적','구조에서 계산한 극성 표면적(Å²)입니다.'],['QED','QED','일반적인 경구 약물 물성의 균형을 나타내는 0–1 지표입니다.'],['SA_score','합성 접근성','구조 복잡도 기반 추정입니다. 낮을수록 합성이 수월할 것으로 추정합니다.']];
  return `${massConflict}${structureFacts(copy)}<dl class="ui-facts">${defs.filter(([key])=>row[key]!==undefined).map(([key,label,meaning])=>`<div><dt>${label}</dt><dd>${esc(row[key])}<small>${meaning}</small></dd></div>`).join('')}</dl><p class="small muted">물성·구조 기반 지표이며 활성, 체내 효능, 실제 합성 성공은 각 실험으로 확인합니다.</p><details><summary>계산별 원값·구조·생성 기록</summary><p>반올림 차이는 생성 기록의 정밀도로 표시하며, 그보다 큰 차이는 별도로 표시합니다. 각 계산의 원값을 보존합니다.</p>${json(Object.fromEntries(Object.entries(row).filter(([k])=>k!=='depiction')))}${json(Object.fromEntries(Object.entries(row.depiction??{}).filter(([k])=>k!=='svg')))}</details>`;
}
function uiExperimentAlias(check){
  const text=[check.question,check.operation?.request].join(' '),read=experimentFields(check).found;
  const targets=[...new Set(text.match(/\b(?:PDE\d+[A-Z]\d*|LPAR\d+|STMN\d+|FAAH|LOX|FTIR|sFlt-?1|TTR)\b/g)??[])];
  if(targets.length)return targets.slice(0,3).join(' · ')+(text.includes('IC50')?' 효소 기능 비교':text.includes('칼슘')?' 기능 반응 비교':' 판별 실험');
  const n=(state.decision?.research_loop?.next_checks??[]).findIndex(c=>c.id===check.id)+1;
  return `${CHECK_KIND[check.operation?.kind]??'확인'} ${n>0?n:''} · ${roadmapSummary(researcherWording(read['측정 대상']?.[0]??check.question),42)}`;
}
function uiExecutionConditions(check){
  if(check.operation?.kind!=='external_observation')return '';
  const needed=check.operation.needed_inputs??[],request=check.operation.request??'';
  const explicit=request.split(/\n/).filter(x=>/확인|실제|기록|정하지|지정하지|미정|반복/.test(x));
  return `<details class="ui-execution-conditions"><summary>실행 전에 확인할 조건</summary><p class="small">시료·시험계, 농도·시점, 반복 단위와 수, 분석·판정 기준을 실제 수행 조건으로 확인해 주세요. 아래는 저장된 권고의 확인 사항입니다.</p>${needed.length?list(needed):''}${explicit.map(x=>`<p>${uiText(x)}</p>`).join('')||uiEmpty('구체적인 수행 조건의 확인 기록이 필요합니다.')}<p class="small muted">이 확인 목록은 수행 완료나 실측 결과를 뜻하지 않습니다.</p></details>`;
}

const uiSourcesWarmed=new Set();
function uiWarmSources(){const key=candidateStructuresKey();if(uiSourcesWarmed.has(key))return;uiSourcesWarmed.add(key);const snapshot=state;void warmSourceDisplayAnchors(snapshot).then(()=>{if(candidateStructuresKey()===key)render()})}
