// Reading state belongs to the browser. Scientific records and their ordering stay unchanged.
const researchReaders = new Map(), experimentSelections = new Map(), candidateViews = new Map();
const researchSubjects = new Map(), outcomeSelections = new Map();
let workspaceWide=false, conversationOpen=false;
let readerRequest = 0, researchSearch = '', researchListMode = document.querySelector('meta[name="evida-demo-workspaces"]') ? 'demo' : 'recent', researchRailCollapsed = true;
const readerHistoryFrames=new Map();
let renderedResearchPanel=null;
const workspaceTabs = [['','한눈에 보기'],['mechanisms','기전'],['candidates','후보'],['next','실험'],['evidence','근거']];
function uiIcon(name){
  const paths={menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',mechanism:'<rect x="9" y="2" width="6" height="5" rx="1"/><rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/><path d="M12 7v5M5 17v-5h14v5"/>',molecule:'<path d="m12 2 8.5 5v10L12 22l-8.5-5V7Z"/><path d="m6.5 8.5 5.5-3.2M17.5 9v6M12 18.5l-5.5-3.2"/>',experiment:'<path d="M8 2h8M10 2v7l-6.5 10A2 2 0 0 0 5.2 22h13.6a2 2 0 0 0 1.7-3L14 9V2M7 15h10"/>'};
  return `<svg class="ui-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]??paths.molecule}</svg>`;
}
function uiQuickLinks(){return `<nav class="ui-quick-links" aria-label="연구 바로가기">${[['mechanisms','mechanism','기전과 후보의 연결'],['candidates','molecule','후보 구조와 검토'],['next','experiment','실험 설계와 판독']].map(([stage,icon,label])=>button('ui-stage',`${uiIcon(icon)}<span>${label}</span>`,`data-stage="${stage}"`,'ui-quick-link')).join('')}</nav>`}
function readerState(){return state?researchReaders.get(state.id):null}
function currentReader(){return readerState()?.stack.at(-1)??null}
function uiText(value){return judgmentText(researcherWording(value))}
// Recommendation display only; source quotations and stored text are untouched.
function uiRecommendationText(value){
  const raw=String(value??''),known=rnaDisplayOptions();let changed=false;
  const text=raw.replace(/(?<![A-Za-z0-9_])guide_[0-9a-f]+(?![A-Za-z0-9_])/g,id=>{
    const matches=known.filter(x=>x.label===id);
    if(matches.length!==1)return id;
    changed=true;return candidateDisplayName(matches[0]);
  });
  return `${uiText(text)}${changed?`<p class="small muted">RNA 후보 번호는 보존 목록의 표시 순서입니다. 후보별 추천 근거는 아래에서 확인하세요.</p><details><summary>추천 원문·후보 ID 보기</summary><p class="prose">${esc(raw)}</p></details>`:''}`;
}
function uiEmpty(text){return `<p class="ui-missing">${esc(text)}</p>`}
function syntheticInputNotice(){const rows=state.events.filter(e=>['message','observation','correction'].includes(e.kind)&&inputProvenance(e).synthetic);return rows.length?`<details><summary>가상 목표·입력 ${rows.length}건 포함</summary>${rows.map(e=>button('message-source','입력 원문',`data-id="${esc(e.body.message_id)}"`,'link-button small')).join('')}<p>가상 시연 입력으로 구분해 보존했습니다.</p></details>`:''}
function uiRevision(a){return !a?'검토 전':a.applicability?.current===true?'현재 입력에서 검토 유지':a.applicability?'근거·조건 재검토 필요':'적용 조건 확인 필요'}
function uiExcerpt(value){
  // A labelled verbatim first paragraph/sentence, never an inferred scientific summary.
  const text=String(value??'').trim();
  const boundary=text.search(/(?:[.!?。](?=\s|$)|\n)/);
  return boundary>=0?text.slice(0,boundary+1):text;
}
// Presentation excerpts preserve the original wording and keep explicit cautions visible.
function uiReadableExperimentText(value){
  return String(value??'')
    .replace(/\bmeasurement_context(?:는|은)?/g,match=>/[는은]$/.test(match)?'측정 조건은':'측정 조건')
    .replace(/\bunknown\b/gi,'미확인')
    .replace(/\(D\d{4},\s*s-[a-f0-9]+-p\d+\.txt,[^)]*\)/g,'')
    .replace(/\/rows\/\d+(?:\/[A-Za-z0-9_~.-]+)*/g,'')
    .replace(/[ \t]{2,}/g,' ').trim();
}
function uiExperimentExcerpt(value){
  const text=String(value??'').trim();
  if(!text)return uiEmpty('확인 필요 · 권고에 구분해 기록된 값이 없습니다.');
  const sentences=text.split(/(?<=[.!?。])\s+|\n+/).filter(Boolean);
  const caution=/미확인|확인\s*필요|불명|미정|미측정|불확실|지정하지|확정하지|검증하지|정하지|가정|추정|unknown|unmeasured|uncertain|not established|not measured/i;
  const lead=sentences[0]??text,cautions=sentences.slice(1).filter(line=>caution.test(line));
  const readable=value=>esc(uiReadableExperimentText(value));
  return `<div class="ui-field-excerpt"><p>${readable(lead)}</p>${cautions.length?`<div class="ui-field-caution"><strong class="small">남은 불확실성·조건</strong>${cautions.map(line=>`<p>${readable(line)}</p>`).join('')}</div>`:''}${sentences.length>1||uiReadableExperimentText(text)!==text?`<details class="ui-field-original"><summary>전체 원문·정확한 조건 보기</summary><p class="prose">${esc(text)}</p></details>`:''}</div>`;
}
const uiComputationKinds={
  "pose_interactions":{"kind":"pose_interactions","label":"포즈별 접촉 · ProLIF"},
  "protonation_states":{"kind":"protonation_states","label":"분자 전하상태 · Dimorphite-DL"},
  "rdkit":{"kind":"rdkit","label":"분자 물성 · RDKit"},
  "admet":{"kind":"admet","label":"ADMET 예측 · ADMET-AI"},
  "molecular_docking":{"kind":"molecular_docking","label":"결합 포즈 · Vina/PoseBusters"},
  "binding_pose_review":{"kind":"binding_pose_review","label":"포즈 순위·기준 구조 비교"},
  "analogue_proposal":{"kind":"analogue_proposal","label":"회수 구조 재조합 제안"},
  "molecule_preparation":{"kind":"molecule_preparation","label":"분자 상태·3D 준비 · Gypsum-DL"},
  "synthetic_complexity":{"kind":"synthetic_complexity","label":"합성 복잡도 · SCScore"},
  "xtb_geometry":{"kind":"xtb_geometry","label":"분자 기하 최적화 · xTB"},
  "crest_conformers":{"kind":"crest_conformers","label":"배좌 탐색 · CREST"},
  "rna_weighted_distribution":{"kind":"rna_weighted_distribution","label":"RNA 평균·전체 분포 비교"},
  "rna_seed_analysis":{"kind":"rna_seed_analysis","label":"RNA seed 분포 분석"},
  "rna_sequence_evaluation":{"kind":"rna_sequence_evaluation","label":"RNA 서열·접근성 계산"},
  "rna_candidate_generation":{"kind":"rna_candidate_generation","label":"RNA 결합 영역 후보 생성"},
  "rna_author_full":{"kind":"rna_author_full","label":"전체 ENsiRNA · 조건부 core 계산"},
  "rna_author_mod":{"kind":"rna_author_mod","label":"ENsiRNA-mod · 수식 위치 비교"},
  "rna_transcriptome_search":{"kind":"rna_transcriptome_search","label":"전체 전사체 상호작용 · RIsearch2"},
  "rna_activity_score":{"kind":"rna_activity_score","label":"RNA 활성 점수"},
  "rna_delivery_simulation":{"kind":"rna_delivery_simulation","label":"전달·RNA·단백질 모형 비교"},
  "rna_seed_sites":{"kind":"rna_seed_sites","label":"3′UTR seed·간 발현 근거"},
  "rna_allele_scenario":{"kind":"rna_allele_scenario","label":"변이 조건에서 후보 다시 비교"},
  "rna_candidate_space":{"kind":"rna_candidate_space","label":"RNA 전체 후보 구간"},
  "rna_candidate_selection":{"kind":"rna_sequence_evaluation","label":"선택한 RNA 후보 실제 계산"},
  "rna_duplex_transcriptome":{"kind":"rna_duplex_transcriptome","label":"가닥별 긴 상보성 검색"},
  "rna_duplex":{"kind":"rna_duplex","label":"가이드·보조 가닥 설계안"},
  "rna_duplex_seed":{"kind":"rna_duplex_seed","label":"양 가닥의 seed 위치"},
  "rna_region_annotation":{"kind":"rna_candidate_space","label":"RNA 후보의 CDS·UTR 구간"},
  "rna_delivery_response":{"kind":"rna_delivery_response","label":"전달 모형의 시점별 민감도"},
  "regulon_activity":{"kind":"regulon_activity","label":"발현 자료의 조절 패턴 비교"},
  "pathway_hypotheses":{"kind":"pathway_hypotheses","label":"관측을 설명하는 경로 후보 계산"},
  "pathway_node_states":{"kind":"pathway_node_states","label":"선택 요소의 변화 없이 설명되는 경로"},
  "pathway_robustness":{"kind":"pathway_robustness","label":"설명 경로의 조건별 비교"},
  "exposure_requirements":{"kind":"exposure_requirements","label":"노출과 시험 농도의 연결 조건"},
  "kinetic_conditions":{"kind":"kinetic_conditions","label":"효소 속도의 조건별 비교"},
  "next_observation_selection":{"kind":"next_observation_selection","label":"다음 확인의 조건별 선택"},
  "reported_activity_comparison":{"kind":"reported_activity_comparison","label":"보고 농도 대비"},
  "retrosynthesis":{"kind":"retrosynthesis","label":"역합성 경로 · AiZynthFinder"},
  "structure_pockets":{"kind":"structure_pockets","label":"구조 포켓 · fpocket"},
  "protein_dynamics":{"kind":"protein_dynamics","label":"단백질 동역학 · OpenMM"},
  "trajectory_analysis":{"kind":"trajectory_analysis","label":"궤적 분석 · MDAnalysis"},
  "rna_interactions":{"kind":"rna_interactions","label":"RNA 상호작용 · IntaRNA"},
  "pocket_docking":{"kind":"molecular_docking","label":"명시 포켓 도킹 · fpocket/Vina"},
  "rna_reference":{"kind":"rna_reference","label":"RNA 참조 조회"},
  "rna_reference_release":{"kind":"rna_reference_archive","label":"RNA 참조 보존본"},
  "rna_reference_archive":{"kind":"rna_reference_archive","label":"RNA 참조 보존본"},
  "rna_reference_panel":{"kind":"rna_reference_panel","label":"RNA 참조 패널 비교"},
  "rna_tissue_context":{"kind":"rna_tissue_context","label":"조직 발현 맥락 조회"},
  "target_structure":{"kind":"target_structure","label":"표적 구조 조회"}
};
const uiComputationResults=new Map();
function uiComputationDescriptor(artifact,job){return uiComputationKinds[job?.kind]??Object.values(uiComputationKinds).find(x=>x.kind===artifact?.kind)}
function uiComputationRecords(){
  const jobs=state?.jobs??[],artifacts=state?.artifacts??[];
  return [...artifacts].reverse().filter(a=>uiComputationDescriptor(a)).map(a=>{
    const matches=jobs.filter(j=>j.output_id===a.id),job=matches.at(-1),status=a.meta?.result_status;
    const linked=uiComputationKinds[job?.kind]?.kind===a.kind;
    const completed=linked&&status==='succeeded'&&['succeeded','reused'].includes(job?.status);
    const partial=linked&&status==='partial'&&job?.status==='partial';
    return {artifact:a,job,completed,partial,label:uiComputationDescriptor(a,job).label};
  });
}
function uiCompletedComputations(){return uiComputationRecords().filter(r=>r.completed).map(r=>r.artifact)}
function uiComputationCacheKey(a){return `${state.id}:${a.id}:${a.sha256??'unknown'}`}
const uiComputationMetricLabels={average_mass:'원자료 평균질량',exact_mass:'원자료 정확질량',MolWt:'분자량',LogP:'계산 logP',TPSA:'극성 표면적',HBD:'수소결합 주개',HBA:'수소결합 받개',QED:'QED 기술자',energy_hartree:'계산 에너지',final_potential_energy_kj_mol:'마지막 퍼텐셜 에너지',rmsd_angstrom:'RMSD',rg_angstrom:'회전반경',gc_fraction:'GC 비율',guide_mfe_kcal_mol:'가이드 접힘에너지',duplex_mfe_kcal_mol:'이중가닥 접힘에너지',length:'길이',formal_charge:'형식 전하'};
const uiComputationOperationalKeys=new Set(['record_index','returncode','elapsed_seconds','model_calls','offset','limit','total','total_rows','total_count','calculated','not_calculated','candidates','unique_model_inputs','conformer_count','frames','atoms','steps','total_picoseconds','source_ref','raw_values','summary','configuration','parameters','simulation_conditions','metadata_response','original_response','runtime_manifest','limits','command','input','files','source_row','row_index','logical_csv_record_0_based']);
function uiComputationIdentity(row,result,index){
  const headers=Array.isArray(result.header)?result.header:[],nameIndex=headers.findIndex(h=>/^(name|compound_name|preferred_name|label)$/i.test(String(h)));
  const name=row.name??row.compound_name??(nameIndex>=0?row.raw_values?.[nameIndex]:null),id=row.candidate_id??row.guide_id??row.id??row.row_id??(typeof row.smiles==='string'?`SMILES ${row.smiles}`:null);
  return [name,id].filter(v=>typeof v==='string'&&v.trim()).join(' · ')||`원결과 입력 ${index+1}`;
}
function uiComputationValues(result){
  const found=[],units=result.units??{},columns=result.columns??{},namedUnits={energy_hartree:'Hartree',potential_energy_kj_per_mol:'kJ/mol',potential_energy_kj_mol:'kJ/mol',final_potential_energy_kj_mol:'kJ/mol',affinity_kcal_mol:'kcal/mol',binding_score_kcal_mol:'kcal/mol',guide_mfe_kcal_mol:'kcal/mol',duplex_mfe_kcal_mol:'kcal/mol',rmsd_angstrom:'Å',rg_angstrom:'Å',temperature_kelvin:'K',total_picoseconds:'ps',timestep_femtoseconds:'fs'};
  function walk(value,path,group,depth=0,parent={}){
    // Inline drawing metadata belongs to the preview, not the source metric table.
    const key=path.split('.').at(-1);if(key==='depiction'||uiComputationOperationalKeys.has(key)||depth>6||found.filter(r=>r.group===group.id).length>=8)return;
    if(typeof value==='number'&&Number.isFinite(value)){
      const column=Array.isArray(columns)?columns.find(c=>c&&typeof c==='object'&&[c.key,c.name,c.field].includes(key)):null;
      const unit=typeof units[key]==='string'?units[key]:!Array.isArray(columns)&&typeof columns[key]==='string'?columns[key]:typeof column?.unit==='string'?column.unit:typeof parent.unit==='string'?parent.unit:namedUnits[key]?`${namedUnits[key]} · 필드명`:'원기록에서 단위 확인';
      found.push({path,value,unit,label:uiComputationMetricLabels[key]??key,group:group.id,identity:group.identity});return;
    }
    if(Array.isArray(value)){value.slice(0,3).forEach((v,i)=>walk(v,`${path}.${i}`,group,depth+1));return}
    if(value&&typeof value==='object')for(const [k,v]of Object.entries(value))if(!['source_ref','raw_values','summary','configuration','parameters','simulation_conditions','metadata_response','original_response','runtime_manifest','limits','command','input','files'].includes(k))walk(v,path?`${path}.${k}`:k,group,depth+1,value);
  }
  if(Array.isArray(result.rows)&&result.rows.length){
    result.rows.slice(0,3).forEach((row,index)=>{
      const group={id:`row-${index}`,identity:uiComputationIdentity(row,result,index)},base=`rows.${index}`;
      // Explicit per-compound properties precede any other numerical result.
      if(row.properties&&typeof row.properties==='object')walk(row.properties,base+'.properties',group);
      for(const [key,value]of Object.entries(row))if(key!=='properties')walk(value,base+'.'+key,group,0,row);
    });
  }else{
    const group={id:'result',identity:'보존된 원결과'};
    for(const [key,value]of Object.entries(result))if(!['summary','simulation_conditions','metadata_response','original_response','configuration','parameters','runtime_manifest','limits'].includes(key))walk(value,key,group);
  }
  return found;
}
function uiComputationDisplayValue(value){return Object.is(value,-0)?'-0':Number.isInteger(value)&&Math.abs(value)<1e9?String(value):String(Number(value.toPrecision(6)))}
function uiComputationResultView(a){
  const item=uiComputationResults.get(uiComputationCacheKey(a));
  if(!item)return '<p class="small muted">펼치면 보존된 원결과에서 값을 읽습니다.</p>';
  if(item.status==='loading')return '<p class="small muted">원결과를 읽고 있습니다.</p>';
  if(item.status==='failed')return '<p class="ui-missing">원결과 조회에 실패했습니다. 실행 상태는 위 카드에서, 보존 자료는 원자료 링크에서 확인하세요.</p>';
  const value=item.value.result,rows=uiComputationValues(value),groups=[...new Set(rows.map(r=>r.group))];
  const knownSemantic={computed_geometry_or_conformer_ensemble_not_binding_or_efficacy:'분자 구조·배좌 계산',rna_sequence_thermodynamics_and_exact_mapping:'서열·열역학과 참조 일치 계산'};
  const lead=[value.method,value.solvent,knownSemantic[value.semantic_type]].filter(v=>typeof v==='string');
  const unitText=unit=>({'Wildman–Crippen calculated logP':'계산 logP · Wildman–Crippen','dimensionless descriptor':'무차원 기술자','count':'개수'})[unit]??unit;
  const table=group=>{const cells=rows.filter(r=>r.group===group),index=Number(group.replace('row-','')),original=value.rows?.[index]??{},context=['atoms','frames','conformer_count','steps','total_picoseconds'].filter(k=>typeof original[k]==='number').map(k=>`${({atoms:'원자 수',frames:'프레임 수',conformer_count:'배좌 수',steps:'계산 단계 수',total_picoseconds:'시간 · ps'})[k]} ${original[k]}`).join(' · ');return `<section class="ui-computation-input"><h4 class="ui-computation-input-identity">${esc(cells[0].identity)}</h4>${context?`<p class="small muted">입력·계산 조건: ${esc(context)}</p>`:''}<div class="table-scroll"><table class="ui-computation-value-table"><thead><tr><th>항목</th><th>값</th><th>단위·원정의</th></tr></thead><tbody>${cells.map(r=>`<tr data-value-path="${esc(r.path)}" data-raw-value="${esc(r.value)}"><th>${esc(r.label)}</th><td>${esc(uiComputationDisplayValue(r.value))}</td><td>${esc(unitText(r.unit))}</td></tr>`).join('')}</tbody></table></div><details><summary>원기록 항목·단위 확인</summary>${cells.map(r=>`<p class="small"><code>${esc(r.path)}</code> · 원값 ${esc(r.value)} · ${esc(r.unit)}</p>`).join('')}</details></section>`;};
  const metadata=[...Object.entries(value.summary??{}),...['atoms','frames','conformer_count'].filter(k=>typeof value[k]==='number').map(k=>[k,value[k]])].filter(([k,v])=>typeof v==='number');
  return `<p class="small">${esc(lead.join(' · '))}</p>${rows.length?groups.map(table).join(''):'<p class="small">이 조회 범위에 수치 결과가 없습니다. 원결과에서 상태·문자 결과를 확인하세요.</p>'}<p class="small muted">입력은 원순서의 앞 3개, 각 입력의 수치는 최대 8개를 유효숫자 6자리로 표시합니다. 정확한 값은 원기록 항목에서, 전체 값·조건은 원결과에서 확인하세요.</p><details><summary>입력·실행 구분 기록</summary>${metadata.map(([key,v])=>`<p class="small">${esc(key)}: ${esc(v)}</p>`).join('')}${value.semantic_type?`<p class="small">원실행 구분값: <code>${esc(value.semantic_type)}</code></p>`:''}</details>`;
}
async function uiLoadComputationResult(id){
  const wid=state?.id,a=state?.artifacts?.find(x=>x.id===id);if(!a||!uiComputationDescriptor(a))return;
  const key=uiComputationCacheKey(a),old=uiComputationResults.get(key);if(old?.status==='loaded'||old?.status==='loading')return;
  uiComputationResults.set(key,{status:'loading'});
  try{
    const value=await api(`/api/workspaces/${wid}/artifacts/${id}?offset=0&limit=3`);
    if(value.artifact_id!==id||value.kind!==a.kind||!value.result||typeof value.result!=='object')throw Error('RESULT_IDENTITY_MISMATCH');
    uiComputationResults.set(key,{status:'loaded',value});
  }catch(error){uiComputationResults.set(key,{status:'failed'})}
  if(state?.id===wid&&state.artifacts.some(x=>x.id===id&&x.sha256===a.sha256))render();
}
function uiComputationSummary(){
  const records=uiComputationRecords(),jobs=state?.jobs??[],issues=jobs.filter(j=>uiComputationKinds[j.kind]&&(!j.output_id||!records.some(r=>r.artifact.id===j.output_id)));
  if(!records.length&&!issues.length)return '';
  const done=records.filter(r=>r.completed).length;
  const card=r=>{
    const a=r.artifact,summary=a.meta?.summary??{},status=r.completed?(r.job?.status==='reused'?'보존 결과 재사용':'완료 결과'):r.partial?'부분 결과':r.job?.status==='failed'?'실패 결과':'완료 상태·작업 연결 미확인';
    const counts=[['calculated','계산 행'],['total_rows','전체 행'],['endpoints','예측 항목'],['unique_model_inputs','모델 입력']].filter(([k])=>Number.isInteger(summary[k])&&summary[k]>=0).map(([k,label])=>`${label} ${summary[k]}`).join(' · ');
    return `<article class="ui-computation-card" data-computation-kind="${esc(a.kind)}" data-computation-artifact="${esc(a.id)}"><p>${button('source',esc(r.label),`data-id="${esc(a.id)}"`,'link-button')} · ${esc(status)}${counts?` · ${esc(counts)}`:''}</p><details data-computation-result="${esc(a.id)}" data-detail-key="computation-result:${esc(a.id)}:${esc(a.sha256)}"><summary>실제 계산값 보기 · 수치·단위·입력 조건</summary>${uiComputationResultView(a)}<p>${button('source','수치 상세 비교·원결과 전체',`data-id="${esc(a.id)}"`,'link-button small')}</p><p class="small muted">${Number.isInteger(a.meta?.based_rev)?`연구 기록 ${a.meta.based_rev} 당시 조건`:'계산 당시 조건은 원결과에서 확인'} · ${esc(a.id)}</p>${(a.meta?.consumed_artifacts??[]).length?`<details><summary>입력·근거 보기</summary>${sourceLinks(a.meta.consumed_artifacts)}</details>`:''}<details><summary>원본 식별 정보</summary><p class="mono">SHA256 ${esc(a.sha256??'미확인')}</p><p class="small">${esc(r.job?.id??'완료 작업 연결 미확인')}</p></details></details></article>`;
  };
  return `<section class="panel ui-computation-summary" aria-label="조회·계산 결과"><h3>조회·계산 결과 · 완료 ${done}개</h3>${records.slice(0,6).map(card).join('')}${records.length>6?`<details data-detail-key="computation-earlier"><summary>다른 보존 결과 ${records.length-6}개 더 보기</summary>${records.slice(6).map(card).join('')}</details>`:''}${issues.length?`<details><summary>결과 없는 실행 기록 ${issues.length}건</summary>${issues.map(j=>`<p>${esc(uiComputationKinds[j.kind].label)} · ${esc(({failed:'실패',partial:'부분 완료',running:'진행 중',queued:'대기 중',succeeded:'완료 작업의 원결과 미확인',reused:'재사용한 원결과 미확인'})[j.status]??'미완료·상태 확인 필요')} <span class="small muted">${esc(j.id)}</span></p>`).join('')}</details>`:''}<p class="small muted">계산 당시의 입력·조건과 결과를 함께 보존합니다. 재사용한 결과에는 재사용 표시가 있습니다. 질환·표적과의 연결은 연구 판단에서 확인하세요.</p></section>`;
}
document.addEventListener('toggle',event=>{
  const node=event.target;if(node?.matches?.('details[data-computation-result]')&&node.open)uiLoadComputationResult(node.dataset.computationResult);
},true);
function uiJudgePath(){
  const steps=[['goal','무엇을 해결하려는가'],['evidence','근거와 조건은 무엇인가'],['mechanisms','어떤 설명을 비교했는가'],['candidates','어떤 후보를 검토했는가'],['',`실제 조회·계산은${uiCompletedComputations().length?' · '+uiCompletedComputations().length+'건':''}`],['next','무엇을 시험하면 구별되는가'],['changes','결과 뒤 무엇을 유지·변경했는가']];
  return `<nav class="ui-judge-path" aria-label="연구 검토 순서"><span class="ui-eyebrow">질문에서 결과 반영까지</span><ol>${steps.map(([stage,label],i)=>`<li>${button('ui-stage',`<span aria-hidden="true">${i+1}</span> ${label}`,`data-stage="${stage}"`,'quiet small')}</li>`).join('')}</ol></nav>`;
}
function uiDiscriminationSummary(){
  const summary=state.demo_discrimination;if(!summary)return '';
  const count=summary.experiments_with_structural_difference,total=summary.experiments_denominator;
  const known=Number.isInteger(count)&&Number.isInteger(total)&&count>=0&&total>=0&&count<=total;
  const current=summary.current_input_accepted===true;
  const label=!known?'등록된 예상 표 비교 미확인':total===0?'등록된 예상 표 비교 전':`등록된 설명별 예상 표에서 차이가 확인된 실험 ${count}/${total}`;
  const mapping=summary.experiments_needing_textual_alternative_mapping;
  const mappingNote=Number.isInteger(mapping)&&mapping>0&&Number.isInteger(total)&&mapping<=total?`<p class="ui-field-caution">본문의 대안을 예상 표에 연결해야 하는 실험 ${mapping}개</p>`:'';
  return `<aside class="ui-discrimination-summary" data-current-input="${current}"><strong>${esc(label)}</strong>${!current?'<p class="ui-field-caution">현재 입력에 맞춰 설명별 예상과 비교 조건을 다시 확인할 차례입니다. 이전 검토 기록은 보존되어 있습니다.</p>':''}${mappingNote}<p class="small muted">각 설명이 예측한 결과를 비교합니다. 표에 연결된 설명·비교 조건·측정 정밀도를 함께 확인하고, 실제 관측을 연결해 판단을 갱신하세요.</p></aside>`;
}
function uiDemoResearchIds(){
  // Display-only catalogue. Empty configuration preserves ordinary navigation.
  const setting=document.querySelector('meta[name="evida-demo-workspaces"]');
  if(!setting)return null;
  try{const value=JSON.parse(setting.content);if(!Array.isArray(value))return new Set();
    if(value.length===0)return null;
    return new Set(value.filter(id=>typeof id==='string'&&/^ws_[A-Za-z0-9_-]+$/.test(id)));
  }catch{return new Set()}
}
function uiDemoResearchLabel(workspace){
  const original=workspace?.title??'새 연구';
  const setting=document.querySelector('meta[name="evida-demo-labels"]');
  if(!setting||typeof workspace?.id!=='string')return original;
  try{const labels=JSON.parse(setting.content);
    if(!labels||typeof labels!=='object'||Array.isArray(labels)||!Object.hasOwn(labels,workspace.id))return original;
    const label=labels[workspace.id];
    return typeof label==='string'&&label.trim()&&label.length<=200?label.trim():original;
  }catch{return original}
}
function uiDemoOriginalTitle(workspace){
  return workspace&&uiDemoResearchLabel(workspace)!==workspace.title?`<details class="ui-secondary"><summary>원래 연구 이름</summary><p>${esc(workspace.title)}</p></details>`:'';
}
function uiDemoResearchRows(rows,current){
  const configured=uiDemoResearchIds();
  if(configured===null)return rows;
  // Explicitly opened/current or newly created work remains usable without widening the saved catalogue.
  const visible=rows.filter(p=>configured.has(p.id)||p.id===current?.id);
  if(current?.id&&!visible.some(p=>p.id===current.id))visible.push({id:current.id,title:current.title??'현재 연구',rev:current.rev,review_status:current.review_status});
  return visible;
}

// Display only: the stored observation and raw reader remain unchanged.
function uiObservationDisplayText(value){
  const raw=String(value??'');
  const prefix="Published literature source-context observation, NOT execution or outcome of the proposed check. Original source assay conditions differ or remain unresolved; no plan outcome is mapped. Reassess only condition-bounded relevance and preserve competing explanations.\n";
  // Hide only this exact driver prefix, and only with the Korean provenance notice.
  const rest=raw.startsWith(prefix)?raw.slice(prefix.length):'';
  const notices=['[기존 문헌 결과 · EVIDA가 수행한 실험 아님]','[문헌의 후대 동물 관찰 · EVIDA가 수행한 실험 아님]'];
  return notices.some(notice=>rest.startsWith(notice))?rest:raw;
}
function uiObservationText(event){
  const text=uiObservationDisplayText(event.body?.text);
  const compact=text.length>240?text.slice(0,240)+'…':text;
  return `<p class="prose">${esc(compact)}</p><details><summary>관측 전문·조건 펼치기</summary><p class="prose ui-observation-full-text">${esc(text)}</p></details>`;
}

function uiObservationBridge(){
  const events=state?.events??[];
  const observations=events.filter(e=>e.kind==='observation'&&e.body?.message_id);
  if(!observations.length)return '';
  const event=observations.at(-1),index=events.indexOf(event),context=event.body.research_context??{};
  const published=e=>e.kind==='decision_published'&&typeof e.body?.receipt_id==='string'&&e.body.receipt_id;
  const prior=events.slice(0,index).reverse().find(published);
  const following=events.slice(index+1).find(published);
  const bound=events.find(e=>published(e)&&e.body.receipt_id===context.decision_id);
  const original=bound??prior;
  const exact=typeof context.check_id==='string'&&context.check_id.length>0;
  const sources=(event.body.source_artifact_ids??[]).filter(id=>(state.artifacts??[]).some(a=>a.id===id));
  return `<section class="panel ui-observation-bridge" aria-label="관측 기록에서 이후 판단으로"><h3>관측 기록과 이후 판단</h3><p class="small">${exact?'기록 당시의 확인에 연결한 관측입니다. 현재 확인의 결과인지는 당시 조건과 연결을 함께 보세요.':'연결 범위: 관측·문헌 맥락. 개별 확인과의 결과 연결은 미지정입니다. 원자료의 대상과 조건을 함께 확인하세요.'}</p>${typeof inputProvenanceNotice==='function'?inputProvenanceNotice(event):''}${uiObservationText(event)}${sources.length?`<div>${sourceLinks(sources)}</div>`:''}<p class="small muted">${following?'이 관측 뒤에 게시된 판단이 있습니다. 실제로 무엇을 유지하거나 바꿨는지는 판단 내용과 근거를 비교하세요.':'관측은 저장되어 있으며, 이후 게시된 판단은 아직 없습니다.'} 유지·변경 이유와 연결 근거에서 관측이 반영된 범위를 확인할 수 있습니다.</p><div class="detail-actions">${button('message-source','관측 원문·출처',`data-id="${esc(event.body.message_id)}"`,'link-button small')}${original?button('source',bound?'관측이 참조한 당시 판단':'관측 전 마지막 판단',`data-id="${esc(original.body.receipt_id)}"`,'link-button small'):''}${following?button('source','관측 후 첫 게시 판단',`data-id="${esc(following.body.receipt_id)}"`,'link-button small'):''}${state.decision_id&&following&&state.decision_id!==following.body.receipt_id?button('source','현재 게시 판단',`data-id="${esc(state.decision_id)}"`,'link-button small'):''}${following?button('ui-stage','유지·변경 이유와 실제 값 비교','data-stage="changes"','link-button small'):''}</div>${observations.length>1?`<p class="small muted">관측 ${observations.length}건 중 최근 기록입니다. ${button('tab','모든 관측 기록','data-id="history"','link-button small')}</p>`:''}</section>`;
}
function uiResultFeedback(check){
  const events=state.events??[],linked=events.filter(event=>event.kind==='observation'&&event.body?.research_context?.check_id===check.id);
  const latest=linked.at(-1);
  if(!latest)return `<section class="ui-result-feedback"><h4>결과를 연결하면 판단을 다시 검토합니다</h4><p>연결된 관측: 아직 없음. 위 표는 가능한 결과의 예상과 결과별 다음 행동입니다.</p></section>`;
  const observedAt=events.indexOf(latest),judgedAfter=events.slice(observedAt+1).some(event=>event.kind==='decision_published');
  return `<section class="ui-result-feedback"><h4>연결된 관측과 이후 판단</h4>${typeof inputProvenanceNotice==='function'?inputProvenanceNotice(latest):''}${uiObservationText(latest)}<p class="small">${judgedAfter?'이 관측이 저장된 뒤 판단 기록이 있습니다. 무엇을 유지하거나 바꿨는지 비교하세요.':'관측은 저장되어 있습니다. 이후 판단 기록은 아직 확인되지 않았습니다.'}</p>${button('ui-stage','관측 전후 판단 비교','data-stage="changes"','link-button small')}${button('message-source','관측 원문·출처',`data-id="${esc(latest.body.message_id)}"`,'link-button small')}</section>`;
}
function uiStage(){return tab==='research'?(roadmapChosen()??''):tab}
// Navigation preferences only. These IDs never enter a scientific ranking or a job.
const INITIAL_PINNED_RESEARCH=['ws_3c8fe9df9cd14339','ws_4475545a286541b2','ws_1ff05aa2d7c24e0e'];
// Exact manually seeded screen fixtures, verified against their original creation scripts.
// This is navigation metadata only: no title matching, job-state filtering or record deletion.
const ARCHIVED_RESEARCH_EXAMPLES=Object.freeze({
  ws_741a80721d08469f:'순위 화면 점검용 고정 자료',
  ws_05cd9d62e1664faa:'다섯 단계 화면 예시'
});
function isArchivedResearchExample(id){return Object.hasOwn(ARCHIVED_RESEARCH_EXAMPLES,id)}
function archivedResearchNotice(){
  if(!isArchivedResearchExample(state?.id))return '';
  return `<aside class="panel" data-archived-research="${esc(state.id)}" aria-label="보관된 개발 예시"><strong>보관된 개발 예시 · ${esc(ARCHIVED_RESEARCH_EXAMPLES[state.id])}</strong><p class="small">화면 점검용으로 직접 작성한 후보·판단입니다. 원 기록을 보존했습니다.</p>${button('project','실제 IPF 연구 열기','data-id="ws_3c8fe9df9cd14339"','link-button small')}</aside>`;
}
const RESEARCH_PIN_KEY='evida-pinned-research';
function pinnedResearchIds(){
  try{const saved=evidaStorage.getItem(RESEARCH_PIN_KEY);if(saved===null)return [...INITIAL_PINNED_RESEARCH];
    const ids=JSON.parse(saved);return Array.isArray(ids)?[...new Set(ids.filter(x=>typeof x==='string'))]:[];
  }catch{return []}
}
function researchRailGroups(){
  const q=researchSearch.trim().toLocaleLowerCase(),pins=pinnedResearchIds(),allRows=[...projects];
  if(state?.id&&!allRows.some(p=>p.id===state.id))allRows.push({id:state.id,title:state.title??'현재 연구',rev:state.rev,review_status:state.review_status});
  const scope=!q&&researchListMode==='demo'?uiDemoResearchRows(allRows,state):allRows;
  const rows=scope.filter(p=>!q||(p.title??'').toLocaleLowerCase().includes(q)||p.id.toLocaleLowerCase().includes(q)||uiDemoResearchLabel(p).toLocaleLowerCase().includes(q));
  const pinned=pins.map(id=>rows.find(p=>p.id===id)).filter(Boolean),unpinned=rows.filter(p=>!pins.includes(p.id));
  const archived=unpinned.filter(p=>isArchivedResearchExample(p.id)),others=unpinned.filter(p=>!isArchivedResearchExample(p.id));
  return {pinned,archived,totalCount:allRows.length,matchedCount:rows.length,visibleTotal:pinned.length+others.length,others:researchListMode==='recent'&&!q?others.slice(0,8):others,hasMore:researchListMode==='recent'&&!q&&others.length>8};
}
function toggleResearchPin(id){
  if(!projects.some(p=>p.id===id))return false;
  const ids=pinnedResearchIds(),next=ids.includes(id)?ids.filter(x=>x!==id):[...ids,id];
  try{evidaStorage.setItem(RESEARCH_PIN_KEY,JSON.stringify(next));return true}
  catch{notice('이 브라우저에 고정 목록을 저장할 수 없습니다.');return false}
}
function researchRailRow(p,pinned){
  const pinIcon='<svg class="ui-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m9 3 6 0-1 6 4 4v2H6v-2l4-4-1-6ZM12 15v7"/></svg>';
  return `<div class="ui-project-row ${pinned?'is-pinned':''}" data-research-id="${esc(p.id)}">${button('project',`<span class="project-name" title="${esc(p.title)}">${esc(uiDemoResearchLabel(p))}</span><small class="project-status">${isArchivedResearchExample(p.id)?'개발 예시 · ':''}${Number.isInteger(p.rev)?'연구 기록 '+p.rev+' · ':''}${esc(({reviewed:'판단 기록 있음',needs_review:'판단 갱신 필요',awaiting_input:'입력 대기'})[p.review_status]??'상태 확인 필요')}</small>`,`data-id="${esc(p.id)}" aria-current="${p.id===state?.id?'page':'false'}"`,`project ${p.id===state?.id?'active':''}`)}${button('ui-pin-research',pinIcon,`data-id="${esc(p.id)}" aria-label="${esc(uiDemoResearchLabel(p))} · ${pinned?'고정 해제':'연구 고정'}" title="${pinned?'고정 해제':'연구 고정'}" aria-pressed="${pinned}"`,'ui-project-pin quiet small')}</div>`;
}
function uiDecisionRecord(id){
  const event=[...(state?.events??[])].reverse().find(e=>e.kind==='decision_published'&&e.body.receipt_id===id);
  if(!event)return null;
  const current=id===state.decision_id;
  return {id,rev:event.body.state_rev,current,title:`${current?'현재 게시 판단':'이전 판단'} · 연구 기록 ${event.body.state_rev}`};
}
function renderResearchRail(){
  const {pinned,others,archived,hasMore,visibleTotal,totalCount,matchedCount}=researchRailGroups();
  return `<div class="rail-heading"><div class="brand">EVIDA</div>${button('ui-rail',uiIcon('menu'),`aria-label="연구 목록 ${researchRailCollapsed?'펼치기':'접기'}" aria-expanded="${!researchRailCollapsed}"`,'quiet small')}</div>
    ${button('new','＋ 새 연구','','new-button')}
    <div class="rail-browser"><label class="sr-only" for="research-search">저장된 연구 검색</label><input id="research-search" type="search" value="${esc(researchSearch)}" placeholder="모든 연구 이름·ID 검색">
    <div class="rail-list-modes">${[['demo','시연 연구'],['recent','최근 연구'],['all',`전체 연구 (${totalCount})`]].map(([id,label])=>button('ui-research-mode',label,`data-mode="${id}" aria-pressed="${researchListMode===id}"`,'quiet small')).join('')}</div>
    <p class="small muted" role="status">${researchSearch?`전체 ${totalCount}개 중 검색 결과 ${matchedCount}개`:researchListMode==='demo'?`시연 연구를 보고 있습니다. 저장된 전체 연구 ${totalCount}개는 위에서 열 수 있습니다.`:`저장된 전체 연구 ${totalCount}개 · 개발 예시는 아래 보관함에 있습니다.`}</p>
    <div class="project-list"><nav aria-label="저장된 연구">${pinned.length?`<p class="rail-group-label">고정한 연구 <small>이 브라우저</small></p>${pinned.map(p=>researchRailRow(p,true)).join('')}`:''}${others.length?`<p class="rail-group-label">${researchListMode==='recent'&&!researchSearch?'최근 연구':'다른 연구'}</p>${others.map(p=>researchRailRow(p,false)).join('')}`:''}${!pinned.length&&!others.length?uiEmpty('일치하는 연구가 없습니다.'):''}</nav>
    ${hasMore?button('ui-research-mode',`연구 ${visibleTotal}개 보기`,'data-mode="all"','quiet small'):''}
    ${archived.length?`<details class="ui-secondary" data-detail-key="research-archive"><summary>개발 예시 보관함 · ${archived.length}개</summary><p class="small muted">화면 점검용 기록입니다. 원문과 후보를 그대로 보존합니다.</p><nav aria-label="보관된 개발 예시">${archived.map(p=>researchRailRow(p,false)).join('')}</nav></details>`:''}</div></div>`;
}
function uiPlannerStoppedState(){
  const goalStopped=goalLifecycleStoppedJob(state);
  if(state.decision&&!goalStopped)return null;
  const latest=goalStopped??[...(state.jobs??[])].reverse().find(j=>j.kind==='planner'&&j.based_rev===state.rev);
  const states={
    failed:['이번 검토가 실패해 판단을 만들지 못했습니다.','질문과 자료는 저장되어 있습니다. 실행 기록을 확인한 뒤 같은 질문으로 다시 검토할 수 있습니다.'],
    quota_exhausted:['대회 API 토큰 한도로 이번 검토가 중단됐습니다.','완료한 자료와 요청은 저장되어 있습니다. 모델 이용 안내에서 다음에 사용할 경로를 선택하세요.'],
    quota_or_rate_limit:['서비스 한도로 이번 검토가 중단됐습니다.','완료한 조회는 저장되어 있습니다. 이어가기 가능 여부와 실행 기록을 확인하세요.'],
    refused:['서비스가 응답을 거절해 이번 검토가 중단됐습니다.','완료된 자료는 저장되어 있습니다. 실행 기록에서 거절 사유를 확인하세요.'],
    identity_unverified:['응답 모델을 확인하지 못해 판단을 게시하지 않았습니다.','검토를 이어가기 전에 실행 기록에서 요청한 모델과 실제 응답 모델을 확인하세요.'],
    outcome_unknown:['응답 완료 여부를 확인하지 못했습니다.','저장된 실행 기록에서 응답 도착 여부와 마지막 완료 단계를 확인하세요.'],
    paused:['판단 생성이 일시 중단됐습니다.','완료한 조회는 저장되어 있습니다. 실행 기록에서 중단 이유와 이어갈 조건을 확인하세요.'],
    interrupted:['판단 생성의 중단 기록이 있습니다.','완료한 자료는 보존되어 있습니다. 실행 기록에서 어디까지 완료됐는지 확인하세요.'],
    route_unavailable:['선택한 모델 경로를 현재 사용할 수 없습니다.','모델 이용 안내에서 경로의 현재 상태를 확인하고 실행 기록을 살펴보세요.'],
    input_missing:['판단에 필요한 입력을 확인해야 합니다.','실행 기록에 남은 입력 항목을 확인하세요. 저장된 자료와 기존 판단은 보존됩니다.']};
  return latest&&states[latest.status]?{job:latest,title:goalStopped&&latest.status==='failed'?'부분 판단을 보존한 채 원목표 검토가 중단됐습니다.':states[latest.status][0],next:states[latest.status][1],partial_preserved:!!goalStopped}:null;
}
function uiPlannerFailureNotice(){
  const stopped=uiPlannerStoppedState();if(!stopped)return '';
  const latest=stopped.job,reason=typeof latest.error==='string'&&latest.error.trim()?latest.error.slice(0,700):'자세한 원인은 실행 기록에서 확인하세요.';
  const retry=latest.status==='failed'?button('retry-planner',`${modelDisplayName(currentModel())}로 저장한 질문 다시 검토`,!status.gateway.available||busy?'disabled':'','primary small'):'';
  const modelInfo=['quota_exhausted','route_unavailable'].includes(latest.status)?button('model-help','모델 이용 안내','','small'):'';
  return `<section class="notice-inline" role="status" aria-label="판단 생성 중단"><h2>${esc(stopped.title)}</h2>${stopped.partial_preserved?'<p>게시한 부분 판단과 원자료는 보존되어 있습니다. 원목표의 남은 연결을 검토하려면 아래 실행 상태와 모델 이용 안내를 확인하세요.</p>':''}<p>${esc(reason)}</p><p class="small">${esc(stopped.next)}</p><div class="detail-actions">${retry}${modelInfo}${button('show-jobs','실행 기록 보기','','small')}</div></section>`;
}
function renderDecisionWorkspace(){
  const stage=uiStage(),model=roadmapModel(),reading=currentReader();
  if(tab==='research'){queueMicrotask(()=>loadCandidateStructures());queueMicrotask(()=>loadMechanismRanking());queueMicrotask(()=>uiWarmSources());if(stage==='candidates')queueMicrotask(()=>uiLoadComputedInputStructures())}
  const active=state.jobs.some(j=>['running','queued'].includes(j.status));
  const body=tab==='data'?dataView():tab==='history'?historyPanel():stage==='mechanisms'?renderResearchPath():stage==='candidates'?uiCandidates():stage==='next'?uiExperiments():stage==='evidence'?`${renderEvidenceWorkbench()}<details class="ui-secondary"><summary>계산·조회·근거의 전체 기록</summary>${roadmapEvidencePanel()}</details>`:stage==='goal'?roadmapGoalPanel():stage==='changes'?roadmapChangesPanel(model):uiOverview(model);
  return `${archivedResearchNotice()}<header class="ui-workspace-heading"><div><span class="ui-eyebrow">연구 워크스페이스</span><h1>${esc(uiDemoResearchLabel(state))}</h1>${uiDemoOriginalTitle(state)}<p>${esc(roadmapRevisionText(model))}</p></div><div class="ui-workspace-tools">${button('ui-question','질문하기',`aria-expanded="${conversationOpen}"`,'small ui-question-button')}${button('ui-wide',workspaceWide?'대화와 함께 보기':'넓게 보기',`aria-pressed="${workspaceWide}"`,'small quiet')}${button('ui-stage','목표·조건','data-stage="goal"','small quiet')}</div></header>
    ${uiPlannerFailureNotice()}${quotaNotice()}${typeof renderCurrentEvidenceScope==='function'?renderCurrentEvidenceScope():''}${uiJudgePath()}${active||goalLifecycleActivity(state)?roadmapActivity():''}
    <div class="ui-research-layout"><aside class="ui-conversation" aria-label="연구 대화"><header class="ui-conversation-heading"><h2>연구 대화</h2>${button('ui-question-close','닫기','aria-label="연구 대화 닫기"','small quiet ui-conversation-close')}</header>${uiConversation()}${uiQuickLinks()}<div class="ui-conversation-compose">${uiComposer(active)}</div><details class="ui-secondary" data-detail-key="workspace-log"><summary>입력 변경·실행 기록</summary>${roadmapRunLine(active)}${renderInputChanges()}${syntheticInputNotice()}</details></aside>
    <div class="ui-work-product"><header class="ui-product-heading"><span>작업물</span><nav class="ui-stage-nav" aria-label="연구 작업 화면">${[...workspaceTabs,['data','원자료']].map(([id,label])=>button('ui-stage',label,`data-stage="${id}" aria-current="${stage===id?'page':'false'}"`,`ui-stage ${stage===id?'active':''}`)).join('')}</nav></header><div class="workspace-split ${reading?'with-reader':''}"><div class="workspace-content" id="workspace-content"><section id="roadmap-inspector" tabindex="-1">${body}</section></div>${reading?renderResearchPanel():''}</div></div></div>`;
}
function uiConversation(){
  const messages=state.events.filter(e=>['message','observation','correction'].includes(e.kind));
  const original=messages[0],latest=messages.at(-1),shown=original===latest?[original]:[original,latest];
  const source=e=>`${inputProvenanceNotice(e)}${button('message-source','입력 원문·출처',`data-id="${esc(e.body.message_id)}"`,'link-button small')}`;
  return `<div class="ui-conversation-thread">${original?`<article class="ui-conversation-message"><div class="ui-conversation-meta"><strong>연구자</strong><span>처음 요청</span></div><p class="prose">${esc(uiExcerpt(original.body.text))}</p>${String(original.body.text??'')!==uiExcerpt(original.body.text)?`<details><summary>입력 전문</summary><p class="prose">${esc(original.body.text)}</p></details>`:''}${source(original)}</article>`:uiEmpty('저장된 연구자 입력 확인 필요')}${latest&&latest!==original?`<details class="ui-latest-input"><summary>최근 입력·정정</summary><p class="prose">${esc(latest.body.text)}</p>${source(latest)}</details>`:''}<article class="ui-conversation-response"><div class="ui-conversation-meta"><strong>EVIDA</strong><span>${esc(uiDecisionScope())}</span></div>${state.decision?`<ul class="ui-conversation-paths">${uiPathSummary()}</ul><details><summary>판단 원문 앞부분</summary><p>${uiText(uiExcerpt(state.decision.recommendation))}</p></details>`:'<p>아직 판단이 기록되지 않았습니다.</p>'}${state.decision?button('ui-judgment','판단 전체·근거','','link-button small'):''}</article>${messages.length>shown.filter(Boolean).length?button('ui-stage',`중간 입력 ${messages.length-shown.filter(Boolean).length}건 · 변경 기록`,'data-stage="history"','link-button small'):''}</div>`;
}
function uiOverview(model){
  const d=state.decision,node=model.nodes.find(n=>n.id==='candidates'),mechanisms=model.nodes.find(n=>n.id==='mechanisms');
  const candidate=node?.recommended?.[0]??node?.options?.[0];
  const selected=candidate&&node?.recommended?.some(x=>x.option_id===candidate.option_id);
  const checks=d?.research_loop?.next_checks??[];
  const paths=uiCurrentPaths();
  const row=candidate&&candidateStructureRow(candidate.option_id),picture=row&&structureThumb(row),assessment=candidate?.assessment,parent=row?.transformed_from??row?.core_from;
  return `<section class="ui-overview" aria-label="연구 핵심 요약">
    ${renderIntentReassessment()}
    <article class="ui-judgment"><span class="ui-eyebrow">${model.current?(state.intent_dependencies?.latest_review_status==='unknown'&&state.intent_dependencies?.prior_record_status==='available'?'잠정 판단 · 목표 연결 검토 필요':'현재 판단'):'마지막으로 기록한 판단'}</span><h2>${d?esc(uiDecisionScope()):uiPlannerStoppedState()?esc(uiPlannerStoppedState().title):'연구 질문을 검토하고 있습니다.'}</h2>${d?`<div class="ui-overview-decision-text">${uiRecommendationText(d.recommendation)}</div>${typeof d.reason==='string'&&d.reason.trim()?`<p class="small"><strong>추천 이유 · 첫 문장</strong> ${uiText(uiExcerpt(d.reason))}</p>`:''}`:''}
      <div class="ui-judgment-links">${d?'<span class="small muted">저장된 현재 검토와 다음 확인</span>':''}${d?button('ui-judgment','추천 이유·판단 전체 보기','','link-button small'):uiEmpty(uiPlannerStoppedState()?'실행이 중단되어 새 판단이 아직 없습니다. 위 상태와 실행 기록을 확인하세요.':'자료 조회 후 판단이 기록되면 이곳에서 확인할 수 있습니다.')}</div></article>
    ${uiObservationBridge()}
    <div class="ui-overview-grid"><div class="ui-overview-visual" ${candidate?`data-candidate-option="${esc(candidate.option_id)}"`:''}><div class="ui-candidate-picture">${picture||uiEmpty(candidate&&['rna','rna_candidate'].includes(optionKind(candidate))?'RNA 서열·전사체 조건':!candidate?(uiCompletedComputations().length?'계산 결과와 입력 조건 확인':'아직 구조가 확인된 후보가 없습니다.'):'2D 구조 확인 필요')}</div>${candidate?button('discovery-detail',`${esc(candidateDisplayName(candidate))} · 후보 상세`, `data-id="${esc(candidate.option_id)}"`,'link-button small'):''}</div>
    <article class="ui-overview-mechanisms"><h3>검토 기전·접근</h3>${paths.length?`<ul class="ui-path-list">${paths.map(p=>`<li><span class="ui-eyebrow">${esc(uiPathKind(p))}</span><strong>${esc(researcherWording(p.label))}</strong><span>${esc(optionStatus[p.assessment?.status??'unreviewed'])} · ${uiRevision(p.assessment)}</span>${p.assessment?.priority!=null?`<small>${esc(researcherWording(p.assessment.comparison_group??'기록한 비교 범위'))} · ${p.assessment.priority}</small>`:''}</li>`).join('')}</ul>`:uiEmpty('검토할 기전과 질환의 연결 근거 확인 필요')}${button('ui-stage',paths.length>1?`기전·접근 ${paths.length}개와 질환 연결 보기`:'질환과의 연결 보기','data-stage="mechanisms"','link-button small')}</article>
    <article class="ui-overview-candidate"><h3>${selected?'현재 추천에 포함된 후보':'확대해서 보는 후보'}</h3>${candidate?`<h4>${esc(candidateDisplayName(candidate))}</h4>${uiCandidateRole(candidate)}${uiGenerationLink(candidate)}${parent?`<p class="small muted">출발 화합물 ${esc(parent)}</p>`:''}<p class="small">${esc(optionStatus[assessment?.status??'unreviewed'])} · ${uiRevision(assessment)}</p>${candidate.origin==='generated_structure_proposal'?'<p class="small muted">설계 구조 · 생성 단계 활성 미측정</p>':''}`:uiEmpty(uiCompletedComputations().length?'조회·계산은 보존되어 있습니다. 치료 추천 후보·기전 연결은 아직 등록되지 않았습니다.':'비교할 후보와 구조 확인 필요')}${button('ui-stage','수치·후보 상세 비교','data-stage="candidates"','link-button small')}</article>
    <article class="ui-overview-next"><h3>다음 실험·확인</h3>${checks.length?`<ul class="ui-overview-checks">${checks.map(c=>`<li>${button('ui-overview-experiment',esc(uiExperimentAlias(c)),`data-id="${esc(c.id)}"`,'link-button')}<span class="small muted">${esc(uiExperimentStatus(c))}</span></li>`).join('')}</ul>`:uiEmpty('다음 실험 권고 확인 필요')}${button('ui-stage','대상·대조군·판독 검토','data-stage="next"','link-button small')}</article></div>
    <nav class="detail-actions" aria-label="수치와 판단의 상세 확인">${button('ui-stage','추천 행동·판독 보기','data-stage="next"','small')}${button('ui-stage','수치·후보 상세 비교','data-stage="candidates"','small')}${button('ui-stage','근거 보기','data-stage="evidence"','small')}</nav>
    ${uiComputationSummary()}
    ${d?`<div class="ui-overview-foot">${button('ui-stage','이전 판단과 비교','data-stage="changes"','quiet small')}<span class="small muted">추천·계산·실제 관측은 각 근거에서 확인합니다.</span></div>`:''}</section>`;
}
const uiInputStructureViews=new Map();
function uiComputedStructureArtifact(){return uiCompletedComputations().find(a=>a.kind==='rdkit')??null}
async function uiLoadComputedInputStructures(){
  const artifact=uiComputedStructureArtifact();if(!artifact)return;
  const wid=state.id,key=candidateStructuresKey()+':'+artifact.id;if(uiInputStructureViews.has(key))return;
  uiInputStructureViews.set(key,{status:'loading',artifact_id:artifact.id});
  try{const value=await api(`/api/workspaces/${encodeURIComponent(wid)}/artifacts/${encodeURIComponent(artifact.id)}?offset=0&limit=30`);uiInputStructureViews.set(key,{status:'ready',artifact_id:artifact.id,value})}
  catch{uiInputStructureViews.set(key,{status:'failed',artifact_id:artifact.id})}
  if(state?.id===wid&&key===candidateStructuresKey()+':'+artifact.id)render();
}
function uiComputedInputStructures(){
  const artifact=uiComputedStructureArtifact();if(!artifact)return '';
  const view=uiInputStructureViews.get(candidateStructuresKey()+':'+artifact.id);
  const value=view?.value,result=value?.result??value,rows=result?.rows??[];
  return `<section class="ui-secondary" aria-label="계산한 입력 구조" data-source-artifact="${esc(artifact.id)}"><h3>실제 계산에 사용한 입력 구조</h3><p class="small muted">원 계산의 입력 구조입니다. 후보와의 동일성·적용 가능성은 해당 후보의 검토 상태에서 확인하세요.</p>${view?.status==='failed'?uiEmpty('입력 구조 표시를 불러오지 못했습니다. 아래 원 계산 결과는 보존되어 있습니다.'):view?.status!=='ready'?uiEmpty('계산한 입력의 2D 구조를 불러오고 있습니다.'):`<div class="ui-candidate-grid">${rows.map(row=>`<article class="ui-candidate compact"><div class="ui-candidate-picture">${structureFigure(row.depiction,row.candidate_id??row.name??'계산 입력')}</div><div><strong>${esc(row.candidate_id??row.name??'원 계산 입력')}</strong><p class="small muted">원 계산 결과의 입력 구조</p></div></article>`).join('')||uiEmpty('원 계산 반환 범위에 구조 행이 없습니다.')}</div>${result?.has_more||rows.length===30?'<p class="small muted">반환된 첫 30행입니다. 나머지는 원 계산 결과에서 확인하세요.</p>':''}`}${sourceLinks([artifact.id])}</section>`;
}
function uiCandidateStructureReason(item,row){
  if(['rna','rna_candidate'].includes(optionKind(item)))return 'RNA 서열·전사체 조건을 근거에서 확인하세요.';
  if(item.structure_status==='not_resolved'&&!row?.depiction)return '출처에 나온 후보 이름은 보존되어 있지만 분자 구조와의 연결은 아직 확인되지 않았습니다.';
  const key=candidateStructuresKey();
  if(candidateStructuresPendingFor===key)return '저장된 구조의 2D 그림을 불러오고 있습니다.';
  if(candidateStructuresFor===key&&candidateStructures?.load_error)return '구조 표시 요청을 완료하지 못했습니다. 후보 원자료는 보존되어 있습니다.';
  if(row?.depiction?.status==='unparsed')return '저장된 구조 문자열을 읽지 못해 2D 그림을 그리지 못했습니다.';
  if(row?.depiction?.status==='failed'||candidateStructures?.depiction_status?.startsWith('unavailable'))return '저장된 구조의 2D 그림을 만들지 못했습니다. 원자료의 SMILES를 확인할 수 있습니다.';
  if(row){const smiles=row.depiction?.smiles??row.smiles??row.structure?.canonical_smiles;return smiles?'저장된 구조는 있지만 2D 그림이 반환되지 않았습니다.':'이 후보 기록에 구조 문자열(SMILES)이 없습니다.';}
  return candidateStructuresFor===key?'이 후보와 연결된 구조 기록을 찾지 못했습니다. 후보 상세와 원자료를 확인하세요.':'2D 구조를 불러오는 중입니다.';
}
function uiCandidateTile(item,compact=false){
  const row=candidateStructureRow(item.option_id),picture=row&&structureThumb(row),a=item.assessment,parent=row?.transformed_from??row?.core_from;
  return `<article class="ui-candidate ${compact?'compact':''} ${readerState()?.stack[0]?.id===item.option_id?'is-selected':''}" data-candidate-option="${esc(item.option_id)}"><div class="ui-candidate-picture">${picture||uiEmpty(uiCandidateStructureReason(item,row))}</div><div><h4>${esc(candidateDisplayName(item))}</h4>${uiCandidateRole(item)}${uiGenerationLink(item)}${parent?`<p class="small muted">출발 화합물 ${esc(parent)}</p>`:''}<p class="small">${esc(optionStatus[a?.status??'unreviewed'])} · ${uiRevision(a)}</p>${item.origin==='generated_structure_proposal'?'<p class="small muted">설계 구조 · 생성 단계 활성 미측정</p>':''}${a?.priority?`<p class="small muted">${esc(researcherWording(a.comparison_group))} 내 검토 순서 ${esc(a.priority)}</p>`:''}${button('discovery-detail','후보 상세',`data-id="${esc(item.option_id)}"`,'small')}</div></article>`;
}
const uiReturnedStructureExpanded=new Map();
function uiReturnedStructureRecords(){
  if(candidateStructuresFor!==candidateStructuresKey())return '';
  const rows=(candidateStructures?.rows??[]).filter(row=>row.depiction?.status==='drawn'&&row.depiction?.svg);
  if(!rows.length)return '';
  const expanded=uiReturnedStructureExpanded.get(candidateStructuresKey())===true,shown=expanded?rows:rows.slice(0,6);
  const toggle=rows.length>6?button('ui-returned-structures',expanded?'접기':'더 보기',`aria-expanded="${expanded}"`,'small'):'';
  return `<section class="ui-secondary" aria-label="조회된 구조 기록"><h3>조회된 구조와 후보별 검토</h3><p class="small muted">조회 목록에서 구조가 확보된 ${rows.length}건입니다. 원 자료의 반환 순서로 표시하며, 개별 추천 근거·검토 상태·출처는 발견 기록에서 확인할 수 있습니다.</p><p class="small">구조 ${rows.length}개 중 ${shown.length}개 · 원 자료의 반환 순서입니다. ${toggle}</p><div class="ui-candidate-grid">${shown.map(row=>`<article class="ui-candidate compact" data-source-candidate-option="${esc(row.option_id)}"><div class="ui-candidate-picture">${structureFigure(row.depiction,row.candidate_id??row.name)}</div><div><strong>${esc(row.candidate_id??row.name??'조회 구조')}</strong><p class="small muted">조회 자료의 구조 · 추천 검토 대기</p><details><summary>원 구조 문자열·기록 ID</summary><p class="mono">${esc(row.depiction.smiles??row.smiles??'')}</p><code>${esc(row.option_id)}</code></details></div></article>`).join('')}</div>${expanded?toggle:''}</section>`;
}
function uiCandidates(){
  const all=candidateOptions(),focus=mechanismFocus.get(state.id);
  const groups={current:all.filter(x=>x.assessment?.current_conditions===true&&x.assessment?.status!=='deferred'),earlier:all.filter(x=>x.assessment?.current_conditions!==true||x.assessment?.status==='deferred')};
  const mode=candidateViews.get(state.id)??(groups.current.length?'current':groups.earlier.length?'earlier':'current');
  const showingRetainedDefault=!candidateViews.has(state.id)&&mode==='earlier';
  const rows=(groups[mode]??[]).filter(x=>!focus||candidateMechanismId(x)===focus);
  return `<section class="ui-candidates"><div class="ui-section-heading"><div><h2>후보·구조</h2><p>같은 이름도 출처와 기록 ID를 기준으로 구분합니다.</p></div>${button('discovery-propose','다른 후보·경로 제안','','small')}</div>
    ${typeof proposalQualificationCollection==='function'?proposalQualificationCollection():''}
    <nav class="ui-subnav" aria-label="후보 범위">${[['current',`현재 검토 ${groups.current.length}건`],['earlier',`보류·이전·미확인 ${groups.earlier.length}건`],['all','발견 기록 전체']].map(([id,label])=>button('ui-candidate-view',label,`data-view="${id}" aria-pressed="${mode===id}"`,'small')).join('')}</nav>
    ${showingRetainedDefault?'<p class="small muted" role="status">현재 조건의 검토 후보: 0개. 보류·이전·미확인 후보는 원래 검토 상태와 함께 아래에 보존돼 있습니다.</p>':''}
    ${focus?`<p>연결 기전: ${esc(candidateMechanismLabel(focus))} ${button('roadmap-focus-clear','필터 해제','','small')}</p>`:''}
    ${mode==='all'?`<p class="small muted">전체 ${number(state.discovery?.total??0)}개 선택지 기록입니다. 기전·표적·접근도 포함하며, 화합물의 고유 개수와 구분합니다.</p>${renderOptionBrowser()}`:`<div class="ui-candidate-grid">${rows.map(x=>uiCandidateTile(x)).join('')||uiEmpty('이 범위의 후보 기록이 없습니다. 발견 기록 전체에서 미검토 후보를 확인할 수 있습니다.')}</div>`}
    ${!all.length?uiReturnedStructureRecords():''}${uiComputedInputStructures()}
    ${uiComputationSummary()}
    ${state.artifacts.filter(a=>a.kind==='rna_candidate_space').map(a=>`<div class="ui-secondary"><strong>보존한 RNA 서열 ${number(a.meta.summary?.unique_guide_sequences)}개</strong>${sourceLinks([a.id])}</div>`).join('')}</section>`;
}
function experimentFields(check){
  const selected=state.measurement_selections?.[check.id];
  if(selected){
    const design=selected.handoff.next_check;
    return {found:{'측정 대상':[design.specimen.description], '조건·비교군':[design.controls.description],
      '판독 지표':[design.readout.description,design.precision.description]},rest:[]};
  }
  const lines=String(check.operation?.request??'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean),found={},rest=[];
  for(const line of lines){const match=REQUEST_FIELDS.map(([key,re])=>[key,line.match(re)]).find(([,m])=>m);if(match){(found[match[0]]??=[]).push(match[1][1])}else rest.push(line)}
  return {found,rest};
}
function selectedExperiment(){
  const checks=state.decision?.research_loop?.next_checks??[];
  return checks.find(x=>x.id===experimentSelections.get(state.id))??checks[0]??null;
}
function uiExperimentStatus(check){
  const run=state.research_checks?.find(x=>x.decision_id===state.decision_id&&x.check_id===check.id),job=run&&state.jobs.find(x=>x.id===run.job_id);
  return job?jobLabels[job.status]??job.status:'제안됨 · 수행 결과 확인 전';
}
function uiExperiments(){
  const checks=state.decision?.research_loop?.next_checks??[],selected=selectedExperiment();
  return `<section class="ui-experiments"><div class="ui-section-heading"><div><h2>다음 실험·확인</h2><p>무엇을 비교하고, 어떤 결과에 따라 판단을 바꿀지 검토합니다.</p></div></div>
    ${!roadmapModel().current&&state.decision?uiEmpty('이전 조건의 권고입니다. 새 입력에 맞춘 검토가 필요합니다.'):''}
    ${uiExperimentReturns.has(state.id)?button('ui-candidate-return','← 후보 상세로 돌아가기','','quiet small'):''}${uiDiscriminationSummary()}<div class="ui-experiment-layout"><nav class="ui-experiment-list" aria-label="실험·확인 목록">${checks.map(c=>button('ui-experiment',`<span class="ui-eyebrow">${esc(CHECK_KIND[c.operation.kind])}</span><strong>${esc(uiExperimentAlias(c))}</strong><small>${esc(uiExperimentStatus(c))}</small>`,`data-id="${esc(c.id)}" aria-pressed="${selected?.id===c.id}"`,'ui-experiment-choice')).join('')||uiEmpty('실험·확인 제안이 아직 없습니다.')}</nav>${selected?uiExperimentDetail(selected):''}</div></section>`;
}
function uiExperimentDetail(check){
  const {found,rest}=experimentFields(check),op=check.operation,loop=state.decision.research_loop;
  const designed=reasoningCheckHypothesis(check);
  const field=(key)=>found[key]?.map(uiExperimentExcerpt).join('')||uiEmpty('확인 필요 · 권고에 구분해 기록된 값이 없습니다.');
  const hypotheses=(check.hypothesis_ids??[]).map(id=>loop.hypotheses.find(h=>h.id===id)).filter(Boolean);
  const scopes=(check.scope_targets??[]).flatMap(t=>(loop.hypotheses.find(h=>h.id===t.hypothesis_id)?.assessment_scope?.parts??[]).filter(p=>t.part_ids.includes(p.id)).map(p=>p.statement));
  return `<article class="ui-experiment-detail" data-research-check="${esc(check.id)}"><header><span class="ui-eyebrow">판별 질문 · ${esc(CHECK_KIND[op.kind])} · 연구 기록 ${state.decision_rev}</span><h3>${esc(uiExperimentAlias(check))}</h3><p class="small muted">${esc(uiExperimentStatus(check))}</p></header>
    <details class="ui-check-question" data-detail-key="check-question:${esc(check.id)}"><summary>전체 질문·권고 목적·연결 가설</summary><h4>원 질문</h4><p>${uiText(check.question)}</p>${check.purpose?`<p>${uiText(check.purpose)}</p>`:''}${scopes.length?list(scopes.map(researcherWording)):hypotheses.length?list(hypotheses.map(h=>researcherWording(h.statement))):uiEmpty('연결된 가설 확인 필요')}</details>
    ${typeof renderObservationReview==='function'?renderObservationReview(check):''}
    ${uiMeasurementSelection(check)}
    ${designed?renderReasoningDesign(designed):`<div class="ui-experiment-fields"><section><h4>시험 대상·시료</h4>${field('측정 대상')}</section><section><h4>비교 대상·대조</h4>${field('조건·비교군')}</section></div><section class="ui-experiment-readout"><h4>읽을 값·단위와 시점</h4>${field('판독 지표')}</section>`}
    <section class="ui-experiment-outcomes"><h4>${designed?'관측을 연결할 모델 해석 · 조건표와 일치하는지 확인':'결과별 다음 행동 · 아직 예상입니다'}</h4>${uiOutcomeBranches(check)}</section>${uiResultFeedback(check)}${designed?'':uiExecutionConditions(check)}
    <details class="ui-check-conditions" data-detail-key="check-conditions:${esc(check.id)}"><summary>${designed?'모델의 추가 설명 · 위 조건표와의 일치 검토 필요':'전체 조건·설계 원문'}</summary>${rest.length?rest.map(x=>`<p>${uiText(x)}</p>`).join(''):''}<p class="prose">${esc(op.request??op.method??'연결된 도구로 자료를 확인하는 단계입니다.')}</p>${op.needed_inputs?list(op.needed_inputs):''}</details>
    <details class="ui-secondary" data-detail-key="check-sources:${esc(check.id)}"><summary>실험 제안에 연결된 원자료 ${op.grounded_in?.length??0}건</summary><p class="small">실험 기록 ID: <code>${esc(check.id)}</code></p>${op.grounded_in?.length?sourceLinks(op.grounded_in):uiEmpty('구체적인 근거 자료 연결 확인 필요')}</details>
    ${uiExperimentControls(check)}
    </article>`;
}

function uiMeasurementSelection(check){
  const selected=state.measurement_selections?.[check.id];if(!selected)return '';
  const h=selected.handoff,e=selected.evaluation;
  const options=typeof candidateOptions==='function'?candidateOptions():[];
  const names=ids=>(ids??[]).map(id=>{const candidate=options.find(option=>[option.option_id,option.entity_id,option.candidate_id].includes(id));return candidate&&typeof candidateDisplayName==='function'?candidateDisplayName(candidate):'이름 확인이 필요한 후보'});
  const arms=selected.arms??[],sets=arms.map(arm=>[...new Set(arm.planned_ids??[])].sort().join('|'));
  const same=sets.length>1&&sets.every(set=>set===sets[0]);
  return `<section class="ui-secondary ui-measurement-summary"><h4>어떤 후보를 먼저 측정하나</h4>
    <p>측정할 고유 후보 ${h.planned_ids.length}개 · 계획 비용 ${esc(String(h.cost.total))} ${esc(h.cost.unit??'')}</p>
    ${same?'<p class="ui-field-caution">비교한 선택 방법들이 같은 후보를 골랐습니다. 이 비교에서는 계산 순위가 후보 선택을 개선했다고 말할 수 없습니다.</p>':''}
    <p>${e.ranking_value==='ranking_value_unproven'?'계산 순위의 선택 가치: 같은 조건의 실측 비교가 다음 확인입니다.':uiText(e.ranking_value)}</p>
    <details><summary>선택 방법별 후보·이유와 원기록</summary>${arms.map((a,index)=>`<h5>선택 방법 ${index+1} · ${esc(names(a.planned_ids).join(' · '))}</h5>${uiExperimentExcerpt(a.reason)}<details><summary>정확한 방법·후보 식별자</summary><p>${esc(a.id)} · ${esc((a.planned_ids??[]).join(' · '))}</p></details>`).join('')}${sourceLinks([selected.artifact_id])}</details>
    ${!selected.current?uiEmpty('설명 또는 입력 조건이 바뀌었습니다. 이 측정 계획을 다시 검토하세요.'):''}
    <p class="small">${h.status==='declared_ready'?'기록한 준비 조건이 갖춰졌습니다. 실험실 검토 후 진행하세요.':'실행 준비: 시료·물질·대조와 판독 정밀도를 확인하면 이 계획을 확정할 수 있습니다.'}</p></section>`;
}
function uiOutcomeBranches(check){
  const outcomes=check.possible_outcomes??[],key=`${state.id}:${state.decision_id}:${check.id}`;
  const chosen=Math.min(outcomeSelections.get(key)??0,Math.max(0,outcomes.length-1));
  const label=(i)=>{
    const text=String(outcomes[i]?.observation??'').replace(/\s+/g,' ').trim();
    return `${i+1}. ${text.length>64?text.slice(0,64)+'…':text||'예상 결과 확인 필요'}`;
  };
  const reviewStatus=(i)=>typeof outcomeInterpretationReview==='function'?outcomeInterpretationReview(check,i):null;
  if(!outcomes.length)return uiEmpty('결과별 판단 분기 확인 필요');
  return `<nav class="ui-result-tabs" aria-label="예상 결과별 해석">${outcomes.map((o,i)=>button('ui-outcome',esc(label(i)),`data-key="${esc(key)}" data-index="${i}" aria-pressed="${chosen===i}" aria-controls="outcome-${i}"`,'small')).join('')}</nav><div class="ui-result-branches">${outcomes.map((o,i)=>`<article id="outcome-${i}" ${chosen!==i?'hidden':''}><span class="ui-eyebrow">예상 결과 ${i+1} · 실제 관측 전</span>${reviewStatus(i)?.needs_review?`<p class="small ui-field-caution">해석 조건: ${esc(reviewStatus(i).label)}</p>`:''}<h5>관측할 결과</h5><p>${uiText(o.observation)}</p><h5>판단·후속 확인</h5>${renderOutcomeInterpretation(check,i,uiText)}</article>`).join('')}</div>`;
}
function uiExperimentControls(check){
  const current=roadmapModel().current,op=check.operation,running=state.jobs.some(j=>['running','queued'].includes(j.status)),ready=state.check_readiness?.[check.id];
  const run=state.research_checks?.find(x=>x.decision_id===state.decision_id&&x.check_id===check.id),job=run&&state.jobs.find(x=>x.id===run.job_id);
  return `<footer class="ui-experiment-actions"><div><strong>기존 자료 검토</strong>
    ${job?.output_id?sourceLinks([job.output_id]):op.kind==='tool'?button('run-check','자료 조회·결과 검토',`data-check="${esc(check.id)}" ${!current||busy||running||!ready?.executable?'disabled':''}`,'small'):['external_observation','researcher_input'].includes(op.kind)?button('delegate-check','기존 자료로 먼저 확인',`data-check="${esc(check.id)}" ${!current||busy?'disabled':''}`,'small'):uiEmpty('연결할 방법·자료 확인 필요')}</div><div class="ui-observation-action"><strong>${op.kind==='external_observation'?'새 관측 기록':'정보·정정 기록'}</strong>${button('check-feedback',op.kind==='external_observation'?'실험 결과 연결':'확인한 내용 연결',`data-check="${esc(check.id)}"`,'primary small')}</div></footer>`;
}

function readerSnapshot(){
  const current=currentReader();if(!current||current!==renderedResearchPanel)return;
  current.scroll=document.querySelector('#research-reader-body')?.scrollTop??0;
  current.openDetails=[...document.querySelectorAll('#research-reader-body details')].map((n,i)=>n.open?i:-1).filter(i=>i>=0);
}
function readerOpener(){
  const node=document.activeElement;
  if(!node?.dataset?.action)return null;
  const target={action:node.dataset.action,id:node.dataset.id??'',stage:node.dataset.stage??'',detailKey:node.closest('[data-detail-key]')?.dataset.detailKey??''};
  return {...target,index:readerOpenerMatches(target).indexOf(node)};
}
function readerOpenerMatches(target){
  if(!target)return [];
  return [...document.querySelectorAll('[data-action]')].filter(n=>n.dataset.action===target.action&&(n.dataset.id??'')===(target.id??'')&&(n.dataset.stage??'')===(target.stage??'')&&(target.detailKey===undefined||(n.closest('[data-detail-key]')?.dataset.detailKey??'')===target.detailKey));
}
function restoreReaderOpener(target){
  const matches=readerOpenerMatches(target),exact=matches[target?.index??0];
  // The same paper can appear in collapsed search records and several claims.
  // Restore the exact expanded claim's link, never a hidden duplicate.
  const opener=exact?.getClientRects().length?exact:matches.find(n=>n.getClientRects().length);
  (opener??document.querySelector('#roadmap-inspector'))?.focus({preventScroll:true});
}
function rememberWorkspaceView(push=false){
  history[push?'pushState':'replaceState']({evida_view:{workspace:state.id,tab,stage:roadmapChosen(),scroll:window.scrollY,opener:readerOpener()}},'',location.href);
}
async function openResearchPanel(panel){
  if(!state)return;
  if(['candidate','relation'].includes(panel.kind)&&panel.subject)researchSubjects.set(state.id,panel.subject);
  readerSnapshot();
  let reader=readerState();
  if(!reader){rememberWorkspaceView();reader={stack:[],opener:readerOpener(),pageScroll:window.scrollY};researchReaders.set(state.id,reader)}
  if(dialog.open)dialog.close();
  const item={...panel,workspace:state.id,rev:state.rev,scroll:0,openDetails:[]};
  // Switching between candidates keeps one inspector; following a citation preserves its parent.
  const replacing=panel.kind==='candidate'&&reader.stack[0]?.kind==='candidate';
  if(replacing)reader.stack=[item];else reader.stack.push(item);
  const token=crypto.randomUUID();readerHistoryFrames.set(token,{reader,stack:[...reader.stack],stage:roadmapChosen(),tab});
  history[replacing?'replaceState':'pushState']({evida_reader:{workspace:state.id,token}},'',location.href);
  render();
  requestAnimationFrame(()=>document.querySelector('#research-reader-title')?.focus({preventScroll:true}));
}
function closeResearchPanel(back=false,fromHistory=false){
  const reader=readerState();if(!reader)return;
  ++readerRequest;
  if(back&&reader.stack.length>1){reader.stack.pop();if(!fromHistory)history.back();render();requestAnimationFrame(()=>document.querySelector('#research-reader-title')?.focus({preventScroll:true}));return}
  if(!fromHistory&&history.state?.evida_reader?.workspace===state.id)history.go(-reader.stack.length);
  researchReaders.delete(state.id);render();
  requestAnimationFrame(()=>{window.scrollTo(0,reader.pageScroll);restoreReaderOpener(reader.opener)});
}
function renderResearchPanel(){
  const panel=currentReader(),reader=readerState();if(!panel)return '';
  const body=panel.kind==='generated-group'?uiGeneratedGroup(panel):panel.kind==='candidate'?uiCandidateDetail(panel):panel.kind==='source'?uiSourceDetail(panel):panel.body??'';
  return `<aside class="research-reader" id="research-reader" aria-labelledby="research-reader-title"><header class="reader-heading"><div>${reader.stack.length>1?button('ui-reader-back','← 돌아가기','','quiet small'):panel.historyContext?button('ui-history-return','← 같은 판단 이력으로','','quiet small'):''}<h2 id="research-reader-title" tabindex="-1">${esc(panel.title)}</h2></div>${button('ui-reader-close','닫기','aria-label="근거 상세 닫기"','small')}</header>
    <div class="reader-context"><span>${esc(panel.subject?.label??state.title)}</span><small>열어본 시점 · 연구 기록 ${panel.rev}${panel.rev!==state.rev?` · 현재 연구 기록 ${state.rev}, 새 판단 확인 필요`:''}</small>${panel.subject&&panel.kind!=='candidate'&&panel.kind!=='local-draft'?button('ui-subject','이 대상에 질문',`data-kind="${esc(panel.subject.kind)}" data-id="${esc(panel.subject.id)}" data-label="${esc(panel.subject.label)}"`,'link-button small'):''}</div>
    <div id="research-reader-body" class="reader-body">${body}</div></aside>`;
}
const uiKnownReadScopes={
  'Whitespace-normalized itertext of exact p element, 1-based document order':{read:'원문의 해당 본문 단락 · 문서 순서 기준'},
  'Exact normalized main paragraph; cited prior work not independently verified':{read:'해당 논문의 본문 단락',next:'본문에서 인용한 선행 연구의 원자료'},
  'Mainparagraphtext,not independent validation of its citedearlierwork':{read:'해당 논문의 본문 단락',next:'본문에서 인용한 선행 연구의 원자료'},
  'Caption/table text; no independent panel remeasurement':{read:'그림 설명과 표의 문자 내용',next:'그림 패널의 원자료와 별도 정량 검토'},
  'Caption/tabletext; quantitativepanel reanalysis not claimed':{read:'그림 설명과 표의 문자 내용',next:'그림 패널의 원자료와 별도 정량 검토'},
  'Main PDF page text; whitespace-normalized pypdf6.14.2 extract_text; page number1-based':{read:'원문 PDF의 해당 페이지 문자 내용'},
  'Actual DOCX text/table read;embedded forest image visually inspected':{read:'보충 문서의 글·표와 삽입된 forest 그림'},
  'Actual forest-plot numerical rows and footnotes visually read':{read:'forest 그림의 수치 행과 각주'},
  'Complete caption text read; images/traces not requantified':{read:'그림 설명 전체',next:'이미지·신호 궤적의 원자료와 별도 정량 검토'},
  'Published caption text, not image reanalysis':{read:'발표된 그림 설명',next:'이미지 원자료와 별도 정량 검토'}
};
function uiSourceLocatorLabel(locator){
  const original=String(locator??''),match=/^body\.p([1-9]\d*)(?:;\s*xml_id=[A-Za-z0-9_.:-]+)?$/.exec(original);
  return match?`본문 ${match[1]}번째 단락`:'원문 위치는 식별 기록에서 확인';
}
function uiReadScopePresentation(scope){
  const known=uiKnownReadScopes[String(scope??'')];
  return known?`<p class="small">읽은 문헌: ${esc(known.read)}</p>${known.next?`<p class="small muted">추가 확인 대상: ${esc(known.next)}</p>`:''}`:scope?'<p class="small">읽은 범위의 원기록은 아래에서 확인할 수 있습니다.</p>':'';
}
function uiReasoningPrincipleBody(result){
  const section=result.section,id=result.principle_id;
  const select=(part,label)=>button('ui-reasoning-principle',label,`data-id="${esc(id)}" data-section="${part}"`,'quiet small');
  const nav=`<nav aria-label="추론 관점 상세">${select('principle','적용 조건과 판단 흐름')}${select('sources','원출처 위치')}${select('cases','도출 사례와 한계')}</nav>`;
  const text=value=>typeof value==='string'?`<p>${esc(value)}</p>`:Array.isArray(value)?list(value):Object.entries(value??{}).map(([key,v])=>`<p><strong>${esc(({distinctive_prediction_supported:'구별 예측이 지지된 경우',valid_null_or_opposite:'유효한 음성 또는 반대 결과',measurement_or_intervention_failure:'측정·개입이 유효하지 않은 경우'})[key]??key.replaceAll('_',' '))}</strong><br>${esc(v)}</p>`).join('');
  let body='';
  if(section==='principle')body=result.rows.map(row=>`<h3>${esc(row.title_ko)}</h3><h4>언제 참고하는가</h4>${text(row.when_to_use)}<h4>가설을 만드는 관점</h4>${text(row.principle)}${[['investigate','선택할 정보와 이유'],['compare','설명을 구별하는 비교'],['update','결과에 따른 재판단']].map(([key,label])=>`<h4>${label}</h4>${text(row.stage_use?.[key])}`).join('')}${row.limits?`<h4>적용 한계</h4>${text(row.limits)}`:''}`).join('');
  else if(section==='sources')body=result.rows.map(row=>`<article><h3>${externalAnchor('pmcid',row.id,row.id)}</h3><p>원문 위치: ${esc(uiSourceLocatorLabel(row.locator))}</p>${uiReadScopePresentation(row.read_scope)}<details><summary>원출처 식별 기록</summary><p>위치 원문 <code>${esc(row.locator)}</code></p>${row.read_scope?`<p>읽은 범위 원문: ${esc(row.read_scope)}</p>`:''}<p>문서 SHA256 <code>${esc(row.source_sha256)}</code></p><p>위치 SHA256 <code>${esc(row.locator_sha256)}</code></p></details></article>`).join('');
  else body=result.rows.map(row=>`<article><h3>${externalAnchor('pmcid',row.pmcid,row.pmcid)}</h3>${text(row.reason)}${row.source_argument_amendment?`<h4>독립 검수의 정정·제한</h4>${text(row.source_argument_amendment.text)}`:''}<details><summary>논증과 검수 범위</summary><p>${esc(row.case_id)}</p>${text(row.review_scope)}</details></article>`).join('');
  if(!result.rows.length)body=uiEmpty(result.historical_examples_suppressed?'현재 허용된 자료 범위에서는 과거 도출 사례와 출처 상세를 제공하지 않습니다.':'이 조회 범위에 기록이 없습니다.');
  const total=result.total_rows,offset=result.offset;
  const page=(next,label)=>button('ui-reasoning-principle',label,`data-id="${esc(id)}" data-section="${esc(section)}" data-offset="${next}"`,'small');
  return `<p class="small muted">문헌 속 연구자의 판단을 추상화한 관점입니다. 적용 조건과 원출처를 확인하고 현재 연구의 관측과 연결해 사용합니다.</p>${nav}${body}${total>10?`<nav aria-label="추론 관점 페이지">${offset>0?page(Math.max(0,offset-10),'이전'):''}<span>${offset+1}–${Math.min(offset+10,total)} / ${total}</span>${offset+10<total?page(offset+10,'다음'):''}</nav>`:''}`;
}
async function uiOpenReasoningPrinciple(id,section='principle',offset=0){
  const wid=state.id,token=++readerRequest,current=currentReader();
  // Only a stored compact perspective with an explicit detail route offers this
  // control. Old RP contexts keep their own historical examples unchanged.
  const allowed=state.reasoning_design_review?.context?.perspectives?.some(p=>p.id===id&&p.detail_function==='read_reasoning_principle');
  if(!allowed)return;
  let panel;
  if(current?.kind==='reasoning-principle'&&current.id===id){panel=current;panel.body=uiEmpty('추론 관점 기록을 읽고 있습니다.');render()}
  else{await openResearchPanel({kind:'reasoning-principle',id,title:'사용한 추론 관점 · 적용 조건과 원출처',body:uiEmpty('추론 관점 기록을 읽고 있습니다.')});panel=currentReader()}
  try{
    const query=new URLSearchParams({principle_id:id,section,offset:String(offset),limit:'10'});
    const value=await api(`/api/workspaces/${encodeURIComponent(wid)}/reasoning-principle?${query}`);
    if(token!==readerRequest||state?.id!==wid||currentReader()!==panel)return;
    panel.body=uiReasoningPrincipleBody(value.result);render();
  }catch(error){if(token===readerRequest&&currentReader()===panel){panel.body=uiEmpty(error.message);render()}}
}
async function uiOpenCandidate(id){
  const token=++readerRequest,item=await getOption(id);if(token!==readerRequest)return;
  await loadCandidateStructures();if(token!==readerRequest)return;
  // The initial thumbnail page is bounded. Resolve an opened candidate by its exact
  // catalog ID and stored source relation, never a name guess or a changed ranking.
  let structureError=null;
  if(!candidateStructureRow(id)&&['molecule','rna_candidate'].includes(optionKind(item))){
    try{
    const key=candidateStructuresKey();
    const value=await api(`/api/workspaces/${encodeURIComponent(state.id)}/candidate-structures?option_id=${encodeURIComponent(id)}`);
    if(token!==readerRequest||candidateStructuresKey()!==key)return;
    if(candidateStructuresFor!==key){candidateStructures={rows:[]};candidateStructuresFor=key}
    candidateStructures??={rows:[]};candidateStructures.rows??=[];
    for(const row of value.rows??[])if(row.option_id===id&&!candidateStructures.rows.some(x=>x.option_id===id))candidateStructures.rows.push(row);
    }catch(error){if(token!==readerRequest)return;structureError='후보 구조를 읽지 못했습니다. 보존된 후보 정보와 원자료를 확인할 수 있습니다.'}
  }
  const mechanism=['mechanism','target','approach','researcher_proposal'].includes(optionKind(item));
  if(mechanism){await openResearchPanel({kind:'relation',id,title:item.label,subject:{kind:'mechanism',id,label:item.label},body:optionDetail(item)});return}
  await openResearchPanel({kind:'candidate',id,title:candidateDisplayName(item),item,structureError,section:'summary',subject:{kind:'candidate',id,label:candidateDisplayName(item)}});
  const panel=currentReader();if(panel?.id===id)void uiLoadParentStructures(panel);
  if(item.candidate_artifact_id)void uiLoadGeneration(item.candidate_artifact_id);
}
function uiCandidateDetail(panel){
  const item=panel.item,a=item.assessment,row=candidateStructureRow(item.option_id),section=panel.section??'summary';
  const name=candidateDisplayName(item),parent=row?.transformed_from??row?.core_from;
  const siblings=candidateOptions(),index=siblings.findIndex(x=>x.option_id===item.option_id);
  const tabs=[['summary','요약'],['evidence','근거'],['properties','구조·물성'],['experiments','관련 실험']];
  let content='';
  if(section==='summary')content=`<p>${esc(item.description??'')}</p>${a?`<h3>검토 이유</h3><p>${uiText(a.reason)}</p><h3>다음 확인</h3><p>${uiText(a.next_action)}</p>${a.priority?`<p class="small">비교 집합: ${esc(researcherWording(a.comparison_group))} · 검토 순서 ${a.priority}</p>`:''}`:uiEmpty('후보의 개별 검토 기록 확인 필요')}${parent?`<p>출발 화합물: <strong>${esc(parent)}</strong></p><p class="small muted">구조를 생성한 이력입니다. 기능 비교는 관련 실험에서 확인합니다.</p>`:''}${sourceCandidateInfo(item,true)}${rnaOptionContext(item)}`;
  if(section==='evidence')content=`<h3>평가의 지지 근거</h3>${sourceLinks(a?.support_source_ids)||uiEmpty('연결된 지지 근거 확인 필요')}<h3>반대 근거·적용 조건</h3>${sourceLinks(a?.challenge_source_ids)}${list(a?.uncertainties)}<h3>발견한 원자료</h3>${sourceLinks((item.sources??[]).map(x=>x.artifact_id))}${(row?.name_mentions??[]).filter(m=>state.artifacts.some(a=>a.id===m.artifact_id)&&/^rows\/\d+$/.test(m.locator??'')).length?`<h3>이름이 등장한 원문 구절</h3><p class="small muted">원문에 등장한 이름과 데이터베이스 구조를 연결한 기록입니다. 활성·시료 동일성 확인 상태는 해당 후보의 평가에서 확인하세요.</p>${(row.name_mentions??[]).filter(m=>state.artifacts.some(a=>a.id===m.artifact_id)&&/^rows\/\d+$/.test(m.locator??'')).map(m=>button('source',esc(artifactName(m.artifact_id))+' · 원문 '+esc(m.locator),`data-id="${esc(m.artifact_id)}" data-source-offset="${Number(m.locator.split('/')[1])}"`,'link-button small')).join('')}`:''}${sourceCandidateInfo(item,true)}${item.assessments?.length>1?`<details><summary>이전 검토 ${item.assessments.length-1}개</summary>${item.assessments.slice(0,-1).reverse().map(x=>`<p>${esc(optionStatus[x.status])} · ${uiRevision(x)}</p><p>${uiText(x.reason)}</p>${sourceLinks([x.artifact_id])}`).join('')}</details>`:''}`;
  if(section==='properties')content=row?`${uiCandidatePair(panel,row)}${uiCandidateProperties(row)}${item.candidate_artifact_id?sourceLinks([item.candidate_artifact_id]):''}`:uiEmpty('이 후보에 연결된 구조·물성 기록 확인 필요');
  if(section==='experiments')content=uiRelatedExperiments(item,row);
  return `${panel.structureError?`<p role="status">${esc(panel.structureError)}</p>`:''}<div class="reader-candidate-identity">${row&&structureThumb(row)?structureFigure(row.depiction,name):uiEmpty(uiCandidateStructureReason(item,row))}<div><strong>${esc(name)}</strong>${uiCandidateRole(item)}${uiGenerationLink(item)}<p>${esc(optionStatus[a?.status??'unreviewed'])} · ${uiRevision(a)}</p>${item.origin==='generated_structure_proposal'?'<p>설계 구조 · 생성 단계 활성 미측정</p>':''}<details><summary>정확한 후보 식별자</summary><code>${esc(item.option_id)}</code>${item.label!==name?`<p>원 기록명: ${esc(item.label)}</p>`:''}</details></div></div>
    <nav class="ui-subnav" aria-label="후보 상세 항목">${tabs.map(([id,label])=>button('ui-candidate-tab',label,`data-section="${id}" aria-pressed="${section===id}"`,'small')).join('')}</nav>${content}
    <footer class="reader-candidate-footer">${index>0?button('discovery-detail','← 이전 후보',`data-id="${esc(siblings[index-1].option_id)}"`,'small'):''}${index>=0&&index<siblings.length-1?button('discovery-detail','다음 후보 →',`data-id="${esc(siblings[index+1].option_id)}"`,'small'):''}${button('ui-subject','이 후보에 질문·정정',`data-kind="candidate" data-id="${esc(item.option_id)}" data-label="${esc(name)}"`,'small')}</footer>`;
}
async function uiOpenSource(id,anchor={}){
  const wid=state.id,token=++readerRequest,artifact=state.artifacts.find(a=>a.id===id.split('#')[0]);
  if(!artifact)throw Error('현재 연구에서 이 자료를 찾을 수 없습니다.');
  const parent=currentReader(),subject=parent?.subject??researchSubjects.get(wid)??{kind:'research',id:wid,label:state.title};
  const start=Number.isInteger(anchor.offset)&&anchor.offset>=0?anchor.offset:0;
  const historyContext=dialog.open&&typeof evidenceHistorySelection!=='undefined'&&evidenceHistorySelection?.wid===wid&&dialog.querySelector('.history-evidence-decision')?{hypothesisId:evidenceHistorySelection.value.hypothesis_id,offset:evidenceHistorySelection.value.offset}:parent?.historyContext;
  await openResearchPanel({kind:'source',id:artifact.id,title:artifactName(artifact.id),subject,parentTitle:parent?.title??(workspaceTabs.find(([stage])=>stage===uiStage())?.[1]??'연구'),offset:start,loading:true,anchor,historyContext,quoteRef:id.includes('#')?id.split('#').slice(1).join('#'):null});
  try{const value=await api(`/api/workspaces/${wid}/artifacts/${artifact.id}?offset=${start}&limit=30`);if(state?.id!==wid||token!==readerRequest||currentReader()?.id!==artifact.id)return;Object.assign(currentReader(),{value,loading:false,title:sourceDisplayLabel(artifact,value.result,Number.isInteger(anchor.offset)?value.result?.rows?.[0]:undefined)});render()}catch(error){if(state?.id===wid&&token===readerRequest){Object.assign(currentReader(),{loading:false,error:error.message});render()}}
}
function uiRecordedDecisionView(result,artifact){
  const record=uiDecisionRecord(artifact.id),checks=result.research_loop?.next_checks??[],hypotheses=result.research_loop?.hypotheses??[];
  return `<section class="ui-recorded-decision" data-decision-id="${esc(artifact.id)}"><h3>${esc(record?.title??'게시 전 판단 제안')}</h3><p>${esc(result.recommendation??'')}</p><details><summary>당시 판단 이유·가설 ${hypotheses.length}개</summary><p>${esc(result.reason??'')}</p>${hypotheses.map(h=>`<article><h4>${esc(h.statement)}</h4><p>${esc(hypothesisLabels[h.assessment]??h.assessment)}</p><p>${esc(h.expected_observation)}</p>${sourceLinks((h.evidence??[]).filter(e=>e.source_type==='artifact').map(e=>e.source_id))}</article>`).join('')}</details><h3>당시의 다음 실험·확인</h3>${checks.map(check=>`<details class="ui-recorded-check" data-recorded-check="${esc(check.id)}"><summary>${esc(check.purpose||check.question)}</summary><p class="small">${esc(CHECK_KIND[check.operation.kind]??check.operation.kind)} · ${esc(check.id)}</p><h4>판별 질문</h4><p>${esc(check.question)}</p><h4>당시 기록한 대상·대조·판독</h4><p class="prose">${esc(check.operation.request??check.operation.method??'기록한 도구의 실행 조건은 원문에서 확인하세요.')}</p>${check.operation.needed_inputs?list(check.operation.needed_inputs):''}${sourceLinks(check.operation.grounded_in)}${(check.possible_outcomes??[]).map((outcome,i)=>`<article class="ui-recorded-outcome"><h4>당시 예상 결과 ${i+1}</h4><p>${esc(outcome.observation)}</p><p>${esc(outcome.implication)}</p></article>`).join('')}</details>`).join('')}<details class="ui-recorded-raw"><summary>원 판단 JSON·출처 그대로 보기</summary>${json(result)}<p class="small">저장 당시 자료명: ${esc(artifact.title)}</p><p class="mono">SHA256 ${esc(artifact.sha256)}</p></details>${button('download','원본·전체 결과 내려받기',`data-id="${esc(artifact.id)}"`,'small')}</section>`;
}
function uiSourceDetail(panel){
  if(panel.loading)return '<p role="status">보존한 원자료를 읽고 있습니다.</p>';
  if(panel.error)return `<p role="alert">${esc(panel.error)}</p>`;
  const artifact=state.artifacts.find(a=>a.id===panel.id),result=panel.value?.result;if(!artifact)return uiEmpty('자료 기록 확인 필요');
  // Existing readers preserve endpoint units and uncertainties. Their execution controls are
  // removed here: reading evidence cannot submit a job or change a selected research option.
  const old={selected,detail,offset};let html;
  try{selected=panel.id;detail=panel.value;offset=panel.offset;html=artifact.kind==='decision_proposal'&&result?.research_loop?uiRecordedDecisionView(result,artifact):artifactDetail()}finally{selected=old.selected;detail=old.detail;offset=old.offset}
  const template=document.createElement('template');template.innerHTML=html;normalizeSourceTitleNodes(template.content);
  const readable=new Set(['source','download','row','prev','next','article-section','article-references','transport-handle']);
  for(const node of template.content.querySelectorAll('[data-action]')){
    if(!readable.has(node.dataset.action)){node.remove();continue}
    if(node.dataset.action==='prev'||node.dataset.action==='next'){const direction=node.dataset.action==='prev'?-30:30;node.dataset.action='ui-source-page';node.dataset.offset=String(Math.max(0,panel.offset+direction))}
    if(node.dataset.action==='row')node.dataset.action='ui-source-row';
    if(node.dataset.action==='article-section'){node.dataset.action='ui-source-page'}
    if(node.dataset.action==='article-references')node.remove();
  }
  const total=result?.total_rows??result?.retained_total_rows??result?.rows?.length;
  const guidance=result?.next_steps??result?.next_actions??result?.recommendation;
  const decisionRecord=artifact.kind==='decision_proposal'?uiDecisionRecord(artifact.id):null;
  return `<div class="reader-source-role"><strong>${decisionRecord?esc(decisionRecord.title):'원자료 · '+esc(panel.parentTitle)+'에서 열었습니다'}</strong><p class="small">자료 저장: ${new Date(artifact.created).toLocaleString('ko-KR')}${decisionRecord?' · 당시 게시 기록':' · 현재 판단의 연구 기록 '+esc(state.decision_rev??'미기록')}</p>${panel.quoteRef?`<p>연결 위치: <code>${esc(panel.quoteRef)}</code></p>`:''}${sourceLocatorDetails(artifact,panel.anchor)}${panel.anchor?.quote?`<span class="ui-eyebrow">이 판단에 연결된 원문 인용</span><blockquote>${esc(panel.anchor.quote)}</blockquote>`:''}</div>${decisionRecord?'':`<section class="reader-current-recommendation"><strong>${roadmapModel().current?'현재 판단':'마지막 판단 · 새 입력 검토 필요'}</strong><p>${uiText(uiExcerpt(state.decision?.recommendation??'판단 확인 필요'))}</p>${button('ui-stage','현재 실험·확인 권고','data-stage="next"','link-button small')}</section>`}${['literature','article'].includes(artifact.kind)?sourceBibliographyView(result,Number.isInteger(panel.anchor?.offset)?result?.rows?.[0]:undefined):''}<section class="reader-original-result"><h3>자료 생성 당시의 결과·안내</h3><p class="small muted">아래 결과와 안내는 이 자료가 생성된 시점의 기록입니다.</p>${template.innerHTML}</section>
    ${guidance?`<details><summary>이 도구 결과에 기록된 후속 안내</summary>${typeof guidance==='string'?`<p>${esc(guidance)}</p>`:json(guidance)}<p class="small">이 자료 생성 시점의 안내입니다. 현재 권고는 ‘다음 실험’에서 확인합니다.</p></details>`:''}
    ${typeof total==='number'&&total>30?`<nav class="reader-pagination" aria-label="원자료 페이지">${button('ui-source-page','이전',`data-offset="${Math.max(0,panel.offset-30)}" ${panel.offset===0?'disabled':''}`,'small')}<span>${panel.offset+1}–${Math.min(panel.offset+30,total)} / ${total}행</span>${button('ui-source-page','다음',`data-offset="${panel.offset+30}" ${panel.offset+30>=total?'disabled':''}`,'small')}</nav>`:''}
    ${button('ui-full-source','자료 작업 화면에서 열기',`data-id="${esc(panel.id)}"`,'small')}`;
}
function uiCurrentSubject(){
  const explicit=researchSubjects.get(state.id);if(explicit)return explicit;
  const panel=currentReader();if(panel?.subject)return panel.subject;
  if(uiStage()==='mechanisms'){const id=mechanismFocus.get(state.id),item=pathMechanisms().find(x=>x.option_id===id);if(item)return {kind:'mechanism',id,label:item.label}}
  if(uiStage()==='next'){const c=selectedExperiment();if(c)return {kind:'check',id:c.id,label:c.question,decision_id:state.decision_id}}
  return researchSubjects.get(state.id)??{kind:'research',id:state.id,label:state.title};
}
function uiComposer(active){
  const subject=uiCurrentSubject();
  let original=renderRoadmapComposer(active).replace('이 지점에서 개입하기','질문·조건·관측 추가').replace('관측이나 아이디어로 방향을 바꿀 수 있어요.','새로 추가할 내용의 대상과 종류를 확인하세요.').replace('data-action="roadmap-send"','data-action="ui-send-preview"').replace(/(data-action="ui-send-preview"[^>]*?)disabled/g,'$1').replace('>보내기</button>','>초안 확인</button>');
  if(!status.gateway.available)original=`<section class="research-composer roadmap-composer"><label class="input-label" for="message">현재 대상에 질문하기</label><textarea id="message" placeholder="질문, 확인할 조건 또는 새로 관측한 내용을 적으세요.">${esc(draft)}</textarea><div class="roadmap-input-tools"><select id="input-kind" aria-label="추가 내용 종류">${[['message','질문·아이디어'],['observation','새 관측'],['correction','조건·해석 정정']].map(([v,label])=>`<option value="${v}" ${inputKind===v?'selected':''}>${label}</option>`).join('')}</select><div class="actions">${button('ui-send-preview','초안 확인','','primary small')}</div></div><p class="small muted">로컬 초안 · 연구에 저장하거나 실행하기 전입니다.</p></section>`;
  if(!status.gateway.available&&((state.explanations??[]).length||(state.jobs??[]).some(j=>j.kind==='explanation')))original+=`<details class="roadmap-help" data-detail-key="explain-question"><summary>저장된 연구 설명 보기</summary>${renderLiveInteraction()}</details>`;
  return `<div class="ui-composer-context"><span>입력 대상</span><strong>${esc(subject.kind==='check'&&state.decision?.research_loop?.next_checks?.find(c=>c.id===subject.id)?uiExperimentAlias(state.decision.research_loop.next_checks.find(c=>c.id===subject.id)):roadmapSummary(researcherWording(subject.label),64))}</strong><details><summary>연결 ID 확인</summary><code>${esc(subject.id)}</code></details>${subject.kind==='check'&&status.gateway.available?button('check-feedback','이 실험의 관측·정정 연결',`data-check="${esc(subject.id)}"`,'small'):subject.kind!=='research'?button('ui-subject-clear','연구 전체로 변경','','small'):''}</div>${original}`;
}
function uiPreparedInput(){
  const subject=uiCurrentSubject(),body=draft.trim();
  return subject.kind==='research'?body:`[연결 대상: ${researcherWording(subject.label)}]\n[기록 ID: ${subject.id}]\n${body}`;
}
function workspaceAfterRender(){
  document.body.classList.toggle('ui-rail-collapsed',researchRailCollapsed);
  document.body.classList.toggle('ui-reading',!!currentReader());
  document.body.classList.toggle('ui-workspace-wide',workspaceWide);
  document.body.classList.toggle('ui-conversation-open',conversationOpen);
  const panel=currentReader(),body=document.querySelector('#research-reader-body');
  renderedResearchPanel=panel;
  if(panel&&body){body.scrollTop=panel.scroll??0;for(const [i,node] of [...body.querySelectorAll('details')].entries())if(panel.openDetails?.includes(i))node.open=true}
  const mobile=matchMedia('(max-width: 1100px)').matches&&!!panel;
  for(const node of document.querySelectorAll('#workspace-content,.rail,.ui-stage-nav,.ui-workspace-heading,.ui-conversation'))node.inert=mobile;
  const conversationModal=matchMedia('(max-width:850px)').matches&&conversationOpen&&!panel;
  for(const node of document.querySelectorAll('.topbar,.ui-work-product'))node.inert=conversationModal;
  if(conversationModal)for(const node of document.querySelectorAll('.rail,.ui-workspace-heading'))node.inert=true;
  const conversation=document.querySelector('.ui-conversation');if(conversation){conversation.setAttribute('role',conversationModal?'dialog':'complementary');if(conversationModal)conversation.setAttribute('aria-modal','true')}
  const reader=document.querySelector('#research-reader');if(reader){reader.setAttribute('role',mobile?'dialog':'region');if(mobile)reader.setAttribute('aria-modal','true')}
  fitResearchReader();
}
function fitResearchReader(){const node=document.querySelector('#research-reader');if(!node)return;if(matchMedia('(max-width:1100px)').matches){node.style.height='';return}const top=Math.max(16,node.getBoundingClientRect().top);node.style.height=`${Math.max(200,innerHeight-top-16)}px`}
window.addEventListener('scroll',fitResearchReader,{passive:true});
async function workspaceAction(action,node){
  if(action.startsWith('path-')){await pathAction(action,node);return true}
  if(action==='discovery-detail'){await uiOpenCandidate(node.dataset.id);return true}
  if(action==='source'&&state){await uiOpenSource(node.dataset.id,{offset:node.dataset.sourceOffset===undefined?undefined:Number(node.dataset.sourceOffset),quote:node.dataset.sourceQuote});return true}
  if(action==='show-check'){researchSubjects.delete(state.id);experimentSelections.set(state.id,node.dataset.check);closeResearchPanel();tab='research';roadmapSelections.set(state.id,'next');render();return true}
  if(!action.startsWith('ui-'))return false;
  if(action==='ui-reasoning-principle'){await uiOpenReasoningPrinciple(node.dataset.id,node.dataset.section??'principle',Number(node.dataset.offset??0));return true}
  if(action==='ui-pin-research'){if(toggleResearchPin(node.dataset.id)){const id=node.dataset.id;render();[...document.querySelectorAll('[data-action="ui-pin-research"]')].find(n=>n.dataset.id===id)?.focus()}return true}
  if(action==='ui-history-return'){const previous=currentReader()?.historyContext;if(previous){closeResearchPanel();await openEvidenceHistory(previous.hypothesisId,previous.offset)}return true}
  if(action==='ui-stage'){
    const stage=node.dataset.stage;uiExperimentReturns.delete(state.id);researchSubjects.delete(state.id);researchReaders.delete(state.id);++readerRequest;
    tab=['data','history'].includes(stage)?stage:'research';roadmapSelections.set(state.id,tab==='research'?(stage||null):null);render();window.scrollTo(0,0);rememberWorkspaceView();document.querySelector('#roadmap-inspector')?.focus({preventScroll:true});return true;
  }
  if(action==='ui-wide'){workspaceWide=!workspaceWide;conversationOpen=false;render();return true}
  if(action==='ui-question'){conversationOpen=true;workspaceWide=false;render();document.querySelector('#message')?.focus();return true}
  if(action==='ui-question-close'){conversationOpen=false;render();document.querySelector('[data-action="ui-question"]')?.focus();return true}
  if(action==='ui-outcome'){outcomeSelections.set(node.dataset.key,Number(node.dataset.index));render();document.querySelector(`[data-action="ui-outcome"][data-index="${node.dataset.index}"]`)?.focus({preventScroll:true});return true}
  if(action==='ui-rail'){researchRailCollapsed=!researchRailCollapsed;render();return true}
  if(action==='ui-research-mode'){researchListMode=node.dataset.mode;render();return true}
  if(action==='ui-reader-close'||action==='ui-reader-back'){closeResearchPanel(action==='ui-reader-back');return true}
  if(action==='ui-judgment'){await openResearchPanel({kind:'judgment',title:'판단 전체와 근거',subject:{kind:'research',id:state.id,label:state.title},body:`<h3>판단 원문</h3><p>${uiText(state.decision.recommendation)}</p><h3>판단 이유</h3><p>${uiText(state.decision.reason)}</p>${sourceLinks(state.decision.evidence_refs)}${questions(state.decision.questions)}`});return true}
  if(action==='ui-returned-structures'){const key=candidateStructuresKey();uiReturnedStructureExpanded.set(key,uiReturnedStructureExpanded.get(key)!==true);render();return true}
  if(action==='ui-candidate-view'){candidateViews.set(state.id,node.dataset.view);if(node.dataset.view==='all'){optionsOpen=true;optionsStage='candidates';optionsOffset=0;optionsKind='';optionsPage=null;render();await loadOptions()}else render();return true}
  if(action==='ui-candidate-tab'){readerSnapshot();Object.assign(currentReader(),{section:node.dataset.section,scroll:0,openDetails:[]});render();return true}
  if(action==='ui-generated-group'){await uiLoadGeneration(node.dataset.id);await openResearchPanel({kind:'generated-group',id:node.dataset.id,title:'같은 생성 집합',subject:uiCurrentSubject()});return true}
  if(action==='ui-candidate-return'){const saved=uiExperimentReturns.get(state.id);if(saved?.rev===state.rev){researchReaders.set(state.id,saved.reader);tab=saved.tab;roadmapSelections.set(state.id,saved.stage);render()}uiExperimentReturns.delete(state.id);return true}
  if(['ui-experiment','ui-related-experiment','ui-overview-experiment'].includes(action)){researchSubjects.delete(state.id);experimentSelections.set(state.id,node.dataset.id);if(action!=='ui-experiment'){if(action==='ui-related-experiment'){readerSnapshot();uiExperimentReturns.set(state.id,{reader:readerState(),rev:state.rev,tab,stage:roadmapChosen()})}researchReaders.delete(state.id);tab='research';roadmapSelections.set(state.id,'next')}render();return true}
  if(action==='ui-subject'){conversationOpen=true;workspaceWide=false;researchSubjects.set(state.id,{kind:node.dataset.kind,id:node.dataset.id,label:node.dataset.label});closeResearchPanel();render();document.querySelector('#message')?.focus();return true}
  if(action==='ui-subject-clear'){researchSubjects.set(state.id,{kind:'research',id:state.id,label:state.title});render();return true}
  if(action==='ui-source-page'){
    const p=currentReader(),next=Number(node.dataset.offset),wid=state.id,token=++readerRequest;
    if(!p||p.kind!=='source'||!Number.isInteger(next)||next<0)return true;
    const value=await api(`/api/workspaces/${wid}/artifacts/${p.id}?offset=${next}&limit=30`);
    if(state?.id===wid&&token===readerRequest&&currentReader()===p){Object.assign(p,{value,offset:next,scroll:0,openDetails:[]});render()}return true;
  }
  if(action==='ui-source-row'){const p=currentReader(),r=p?.value?.result,row=r?.rows?.[Number(node.dataset.index)];if(row!==undefined)await openResearchPanel({kind:'row',id:p.id,title:'원행의 전체 값',subject:p.subject,body:json(r.header?{header:r.header,row}:row)});return true}
  if(action==='ui-full-source'){researchReaders.delete(state.id);await chooseArtifact(node.dataset.id);return true}
  if(action==='ui-send-preview'){
    if(!draft.trim()){notice('추가할 내용을 입력해 주세요.');return true}
    const subject=uiCurrentSubject();
    if(!status.gateway.available){await openResearchPanel({kind:'local-draft',id:subject.id,title:'질문 초안',subject,body:`<h3>로컬 초안 · 저장·실행 전</h3><p>종류: ${esc(({message:'질문·아이디어',observation:'새 관측',correction:'조건·해석 정정'})[inputKind])}</p><p class="prose">${esc(uiPreparedInput())}</p><p class="small muted">이 미리보기에서는 연구 기록을 바꾸거나 모델을 실행하지 않습니다. 닫으면 입력으로 돌아갑니다.</p>`});return true}
    if(subject.kind==='check'&&['observation','correction'].includes(inputKind)){openResearchFeedback(subject.id,null);document.querySelector('#feedback-text').value=draft;document.querySelector('#feedback-kind').value=inputKind;return true}
    const prepared=uiPreparedInput();await openResearchPanel({kind:'input-preview',id:subject.id,title:'보내기 전에 확인',subject,prepared,originalDraft:draft,inputKind,sendMode,body:`<h3>저장할 내용</h3><p class="prose">${esc(prepared)}</p><p>종류: ${esc(({message:'질문·아이디어',observation:'새 관측',correction:'조건·해석 정정'})[inputKind])}</p><p>${sendMode==='record'?'기록만 저장합니다.':'자료와 연결된 도구를 사용해 검토합니다.'}</p>${button('ui-send-confirm','확인하고 보내기','','primary small')}`});return true;
  }
  if(action==='ui-send-confirm'){
    const panel=currentReader();if(!panel||panel.kind!=='input-preview'||panel.rev!==state.rev||panel.originalDraft!==draft||panel.inputKind!==inputKind||panel.sendMode!==sendMode)throw Error('입력 또는 연구 조건이 바뀌었습니다. 보낼 내용을 다시 확인해 주세요.');
    draft=panel.prepared;evidaStorage.setItem(draftKey(),draft);researchReaders.delete(state.id);await roadmapAction('roadmap-send',node);return true;
  }
  return true;
}
document.addEventListener('input',event=>{if(event.target.id==='research-search'){researchSearch=event.target.value;render()}});
document.addEventListener('keydown',event=>{
  if(!currentReader()&&conversationOpen&&matchMedia('(max-width:850px)').matches&&!dialog.open){
    if(event.key==='Escape'){event.preventDefault();conversationOpen=false;render();document.querySelector('[data-action="ui-question"]')?.focus();return}
    if(event.key==='Tab'){const nodes=[...document.querySelectorAll('.ui-conversation button:not([disabled]),.ui-conversation a[href],.ui-conversation textarea,.ui-conversation select,.ui-conversation summary')].filter(n=>n.getClientRects().length),first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}}
    return;
  }
  if(!currentReader()||dialog.open)return;
  if(event.key==='Escape'){event.preventDefault();closeResearchPanel(currentReader()?.kind==='source'&&readerState().stack.length>1);return}
  if(event.key==='Tab'&&matchMedia('(max-width: 1100px)').matches){const nodes=[...document.querySelectorAll('#research-reader button:not([disabled]),#research-reader a[href],#research-reader input,#research-reader select,#research-reader textarea,#research-reader summary')].filter(n=>n.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&(document.activeElement===first||document.activeElement.id==='research-reader-title')){event.preventDefault();last?.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}}
});
window.addEventListener('resize',()=>{if(typeof state!=='undefined'&&state)workspaceAfterRender()});
window.addEventListener('popstate',event=>{
  if(typeof state==='undefined'||!state)return;
  readerSnapshot();
  const key=event.state?.evida_reader,frame=key?.workspace===state.id&&readerHistoryFrames.get(key.token);
  const view=event.state?.evida_view;
  ++readerRequest;
  if(frame){frame.reader.stack=[...frame.stack];researchReaders.set(state.id,frame.reader);tab=frame.tab;roadmapSelections.set(state.id,frame.stage);render();requestAnimationFrame(()=>document.querySelector('#research-reader-title')?.focus({preventScroll:true}))}
  else if(view?.workspace===state.id){
    const reader=readerState();researchReaders.delete(state.id);tab=view.tab;roadmapSelections.set(state.id,view.stage);render();
    requestAnimationFrame(()=>{window.scrollTo(0,reader?.pageScroll??view.scroll??0);restoreReaderOpener(reader?.opener??view.opener)});
  }else if(readerState())closeResearchPanel(false,true);
});
