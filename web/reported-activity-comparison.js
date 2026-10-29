Object.assign(SCIENCE_LABELS,{reported_activity_comparison:'같은 화합물의 두 표적 보고값 대비'});

function reportedActivityNumber(value){
 return typeof value==='number'&&Number.isFinite(value)
  ? new Intl.NumberFormat('ko-KR',{maximumSignificantDigits:6}).format(value)
  : null;
}

function reportedActivityRange(quantity,logarithmic=false){
 if(!quantity||!['point','interval'].includes(quantity.kind))return '원값 확인 필요';
 if(quantity.kind==='point')return reportedActivityNumber(quantity.point)??'원값 확인 필요';
 if(quantity.lower_unbounded===true&&!logarithmic)return '범위 확인 필요';
 const lower=quantity.lower_unbounded===true?'−∞':reportedActivityNumber(quantity.lower);
 const upper=quantity.upper_unbounded===true?'+∞':reportedActivityNumber(quantity.upper);
 if(lower===null||upper===null||typeof quantity.lower_closed!=='boolean'||typeof quantity.upper_closed!=='boolean')return '범위 확인 필요';
 const left=quantity.lower_unbounded===true||quantity.lower_closed===false?'(':'[';
 const right=quantity.upper_unbounded===true||quantity.upper_closed===false?')':']';
 return `${left}${lower}, ${upper}${right}`;
}

function reportedActivityTarget(measurement){
 return measurement?.target_name??measurement?.raw_record?.target_pref_name??measurement?.target_id??'표적 확인 필요';
}

function reportedActivityValue(measurement){
 if(!measurement)return '원 측정 확인 필요';
 return [measurement.endpoint??'측정량 미상',measurement.relation??'관계 미상',
  measurement.value??'값 미상',measurement.units??'단위 미상'].map(value=>esc(value)).join(' ');
}

function reportedActivityDirection(row){
 if(!['computed_exact','computed_interval'].includes(row.status))return '대응할 원행과 조건을 확인해 다시 비교합니다.';
 const endpoint=esc(row.reference?.endpoint??'보고 농도');
 const reference=esc(reportedActivityTarget(row.reference)),comparator=esc(reportedActivityTarget(row.comparator));
 if(row.direction==='reference_lower')return `${reference}의 보고 ${endpoint}가 더 낮습니다.`;
 if(row.direction==='comparator_lower')return `${comparator}의 보고 ${endpoint}가 더 낮습니다.`;
 if(row.direction==='equal')return `두 표적의 보고 ${endpoint}가 같습니다.`;
 return '측정 범위를 좁히면 두 표적의 농도 차이를 구별할 수 있습니다.';
}

const REPORTED_ACTIVITY_CONDITION_LABELS={assay_organism:'종',target_organism:'표적 종',
 assay_cell_type:'세포',assay_tissue:'조직',assay_type:'시험 유형',bao_format:'측정 형식',
 bao_label:'측정 형식',assay_parameters:'상세 시험 조건',assay_strain:'균주',assay_subcellular_fraction:'시료 분획',
 substrate_concentration:'기질 농도',preincubation_time:'전처리 시간',readout_time:'판독 시간'};
Object.assign(REPORTED_ACTIVITY_CONDITION_LABELS,{'activity.target_organism':'표적 종','activity.target_tax_id':'표적 종 식별자',
 'activity.assay_type':'시험 유형','activity.bao_format':'측정 형식','activity.bao_endpoint':'측정값 정의',
 complete_protocol_and_construct_comparability:'전체 시험법·단백질 구성의 대응'});

function reportedActivityConditions(measurement){
 if(!measurement)return '<p>원 측정 자료를 확인해 주세요.</p>';
 const context=measurement.condition_context??{},raw=measurement.raw_record??{};
 const authority=measurement.assay_context_status==='retained_assay_response'
  ?'보존된 시험 조건 원응답과 대조한 내용입니다.'
  :'시험 조건의 원응답을 확인하면 세부 조건의 대응을 판단할 수 있습니다.';
 const fields=['assay_organism','assay_cell_type','assay_tissue','assay_strain','assay_subcellular_fraction','assay_type','bao_format'];
 const values=fields.map(key=>{
  const value=context[key]??raw[key];
  return `<li>${esc(REPORTED_ACTIVITY_CONDITION_LABELS[key]??key)}: ${esc(value===null||value===undefined||value===''?'미기록':value)}</li>`;
 }).join('');
 const description=measurement.assay_description??context.description??raw.assay_description;
 const aid=measurement.source_ref?.artifact_id;
 const row=/^\/rows\/(0|[1-9]\d*)(?:\/|$)/.exec(measurement.source_ref?.json_pointer??'');
 const link=aid?button('source','보존 원측정 보기',`data-id="${esc(aid)}"${row?` data-source-offset="${Number(row[1])}"`:''}`,'link-button small'):'';
 return `<section><h5>${esc(reportedActivityTarget(measurement))} · ${esc(measurement.assay_id??'시험 ID 미상')}</h5><p>${description?esc(description):'원 시험 설명을 이어서 확인합니다.'}</p><p class="small muted">${authority}</p><ul>${values}</ul>${measurement.assay_context_status==='unverified_copy'?`<details><summary>보존된 조건 사본 · 원응답 확인 필요</summary><pre class="raw">${esc(JSON.stringify(measurement.assay_context??{},null,2))}</pre></details>`:''}${link}</section>`;
}

function reportedActivityPairDetails(row){
 const review=row.condition_review??{},unknown=Array.isArray(review.unknown_fields)?review.unknown_fields:[];
 const mismatches=Array.isArray(review.mismatches)?review.mismatches:[];
 const reasons=Array.isArray(row.reasons)?row.reasons:[];
 const correspondence=['computed_exact','computed_interval'].includes(row.status)
  ?'같은 문헌의 화합물 기록을 대응했습니다. 원 실험의 시료·기질 농도·측정법을 함께 확인해 적용 범위를 정합니다.'
  :'문헌·화합물·원행의 대응과 조건 차이를 확인하면 두 측정값을 다시 비교할 수 있습니다.';
 return `<details><summary>두 측정의 조건과 원행</summary><p class="small">${esc(row.document_id??'문헌 확인 필요')} · 원 화합물 기록 ${esc(row.source_record_id??'확인 필요')}</p>${reportedActivityConditions(row.reference)}${reportedActivityConditions(row.comparator)}${unknown.length?`<p class="small">다음에 확인할 조건: ${unknown.map(key=>esc(REPORTED_ACTIVITY_CONDITION_LABELS[key]??key)).join(', ')}</p>`:''}${mismatches.length?`<p class="notice-inline">두 기록의 조건 차이를 먼저 검토합니다.</p><pre class="raw">${esc(JSON.stringify(mismatches,null,2))}</pre>`:''}${reasons.length?`<details><summary>계산 검토 기록</summary><pre class="raw">${esc(JSON.stringify(reasons,null,2))}</pre></details>`:''}<p class="small muted">${correspondence}</p></details>`;
}

function reportedActivityComparisonTable(result){
 const rows=Array.isArray(result.rows)?result.rows:[],summary=result.summary??{};
 const pieces=[['점값',summary.computed_exact],['보고 범위',summary.computed_interval],['원행·조건 확인',summary.unresolved]]
  .filter(([,value])=>typeof value==='number'&&value>0).map(([label,value])=>`${label} ${reportedActivityNumber(value)}쌍`);
 const ownId=typeof selected==='string'?selected:'';
 const start=Number.isInteger(result.offset)&&result.offset>=0?result.offset:0;
 const total=Number.isInteger(result.total_rows)?result.total_rows:(summary.requested_pairs??rows.length);
 const table=rows.length?`<div class="table-scroll"><table data-reported-activity-comparison><thead><tr><th>화합물 · 원 조건<br>두 표적의 보고값</th><th>비교 / 기준</th></tr></thead><tbody>${rows.map(row=>{
  const computed=['computed_exact','computed_interval'].includes(row.status);
  return `<tr data-activity-contrast-index="${esc(row.pair_index)}"><td><strong>${esc(row.candidate_id??'화합물 확인 필요')}</strong><p><span class="small">기준 · ${esc(reportedActivityTarget(row.reference))}</span><br>${reportedActivityValue(row.reference)}</p><p><span class="small">비교 · ${esc(reportedActivityTarget(row.comparator))}</span><br>${reportedActivityValue(row.comparator)}</p>${reportedActivityPairDetails(row)}</td><td>${computed?`<strong>${esc(reportedActivityRange(row.ratio))}</strong><p class="small">log₁₀ 대비 ${esc(reportedActivityRange(row.log10_ratio,true))}</p>${row.ratio?.lower_decimal?`<details><summary>전체 계산값</summary><pre class="raw">${esc(JSON.stringify({ratio:row.ratio,log10_ratio:row.log10_ratio},null,2))}</pre></details>`:''}`:'<strong>원행·조건 확인</strong>'}<p class="small">${reportedActivityDirection(row)}</p></td></tr>`;
 }).join('')}</tbody></table></div>`:'<p>대응할 두 원 측정 기록을 선택하면 대비값을 확인할 수 있습니다.</p>';
 const pagination=Number.isInteger(result.total_rows)?`<div class="pagination"><span>${rows.length?`${start+1}–${start+rows.length}`:'0'} / ${esc(total)}쌍</span><div>${button('prev','이전',start===0?'disabled':'','small')}${button('next','다음',result.has_more===true?'':'disabled','small')}</div></div>`:'';
 return `<section data-reported-activity-result><h3>같은 화합물의 두 표적 보고값 대비</h3><p>${esc(result.reason??'')}</p>${pieces.length?`<p>${pieces.join(' · ')}</p>`:''}<p class="small">비율은 비교 표적의 농도를 기준 표적의 농도로 나눈 값입니다. 1보다 크면 기준 표적의 보고 농도가 더 낮습니다.</p>${table}${pagination}<p class="small muted">대괄호는 경계값 포함, 소괄호는 경계값 제외입니다. 범위는 원보고의 부등호를 계산한 결과입니다. 대비값은 유효숫자 6자리로 표시하며 방향은 원값으로 계산합니다.</p>${ownId?`<div class="detail-actions">${button('science-review','두 표적의 보고값으로 다음 확인 검토',`data-id="${esc(ownId)}" ${typeof busy!=='undefined'&&busy?'disabled':''}`,'small')}</div>`:''}</section>`;
}
