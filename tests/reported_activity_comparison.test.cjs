const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/reported_activity_comparison_display.json'),'utf8'));
const code=fs.readFileSync(path.join(__dirname,'../web/reported-activity-comparison.js'),'utf8');
const clone=value=>JSON.parse(JSON.stringify(value));
function setup(){
 const ctx={SCIENCE_LABELS:{},busy:false,selected:'contrast-result',
  esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  sourceLinks:ids=>ids.map(id=>`<a data-artifact="${id}">${id}</a>`).join(''),
  button:(action,label,attributes='')=>`<button data-action="${action}" ${attributes}>${label}</button>`};
 vm.createContext(ctx);vm.runInContext(code,ctx);return ctx;
}

test('two original measurements, direction, provenance and unknown conditions stay connected',()=>{
 const ctx=setup(),result=clone(fixture.result),before=JSON.stringify(result);
 const html=ctx.reportedActivityComparisonTable(result);
 assert.match(html,/IC50 = 10 nM/);assert.match(html,/IC50 = 100 nM/);
 assert.match(html,/<strong>10<\/strong>/);assert.match(html,/log₁₀ 대비 1/);
 assert.match(html,/TARGET_A의 보고 IC50가 더 낮습니다/);
 assert.match(html,/synthetic-source-reference/);assert.match(html,/synthetic-source-comparator/);
 assert.match(html,/data-id="synthetic-source-reference" data-source-offset="0"/);
 assert.match(html,/다음에 확인할 조건: 세포, 조직, 상세 시험 조건/);
 assert.equal(JSON.stringify(result),before);
 assert.match(html,/data-action="science-review" data-id="contrast-result"/);
 ctx.busy=true;assert.match(ctx.reportedActivityComparisonTable(result),/data-id="contrast-result" disabled/);
});

test('a nested retained candidate measurement opens its own source row',()=>{
 const ctx=setup(),result=clone(fixture.result);
 result.rows[0].reference.source_ref.json_pointer='/rows/47/activities/2';
 assert.match(ctx.reportedActivityComparisonTable(result),/data-id="synthetic-source-reference" data-source-offset="47"/);
});

test('one-sided reporting keeps an open positive ratio limit and the logarithmic infinite limit',()=>{
 const ctx=setup(),result=clone(fixture.result),row=result.rows[0];
 row.status='computed_interval';row.reference.relation='>';row.direction='unresolved';
 row.ratio={kind:'interval',lower:0,upper:10,lower_unbounded:false,upper_unbounded:false,lower_closed:false,upper_closed:false};
 row.log10_ratio={kind:'interval',lower:null,upper:1,lower_unbounded:true,upper_unbounded:false,lower_closed:false,upper_closed:false};
 const html=ctx.reportedActivityComparisonTable(result);
 assert.match(html,/IC50 &gt; 10 nM/);assert.match(html,/<strong>\(0, 10\)<\/strong>/);
 assert.match(html,/log₁₀ 대비 \(−∞, 1\)/);assert.match(html,/측정 범위를 좁히면/);
 assert.doesNotMatch(html,/보고 IC50가 더 낮습니다/);
 assert.equal(ctx.reportedActivityRange({...row.ratio,lower:1,lower_closed:true,upper:null,upper_unbounded:true}),'[1, +∞)');
});

test('missing numeric bounds do not become zero and malformed ratio infinity stays unresolved',()=>{
 const ctx=setup();
 for(const point of [null,undefined,'0',Infinity,NaN])assert.equal(ctx.reportedActivityRange({kind:'point',point}),'원값 확인 필요');
 assert.equal(ctx.reportedActivityRange({kind:'point',point:0}), '0');
 const interval={kind:'interval',lower:null,upper:1,lower_unbounded:false,upper_unbounded:false,lower_closed:false,upper_closed:true};
 assert.equal(ctx.reportedActivityRange(interval),'범위 확인 필요');
 assert.equal(ctx.reportedActivityRange({...interval,lower_unbounded:true}),'범위 확인 필요');
 assert.equal(ctx.reportedActivityRange({...interval,lower_unbounded:true},true),'(−∞, 1]');
});

test('failed correspondence hides stale calculated values and retains the original measurements',()=>{
 const ctx=setup(),result=clone(fixture.result),row=result.rows[0];
 row.status='unresolved';row.ratio.point=666;row.log10_ratio.point=777;
 row.condition_review.mismatches=[{field:'assay_organism',reference:'Homo sapiens',comparator:'Mus musculus'}];
 const html=ctx.reportedActivityComparisonTable(result);
 assert.match(html,/원행·조건 확인/);assert.match(html,/Mus musculus/);assert.match(html,/IC50 = 10 nM/);
 assert.doesNotMatch(html,/666|777|같은 문헌의 화합물 기록을 대응했습니다|보고 IC50가 더 낮습니다/);
});

test('unrecorded original values and conditions are visible as unknown',()=>{
 const ctx=setup(),result=clone(fixture.result),row=result.rows[0];
 row.status='unresolved';row.reference.value=null;row.reference.units=null;row.reference.relation=null;
 row.reference.assay_context={};row.reference.raw_record={};row.reference.assay_description=null;
 const html=ctx.reportedActivityComparisonTable(result);
 assert.match(html,/IC50 관계 미상 값 미상 단위 미상/);assert.match(html,/세포: 미기록/);
 assert.match(html,/원 시험 설명을 이어서 확인합니다/);
});

test('researcher text and original source text are escaped',()=>{
 const ctx=setup(),result=clone(fixture.result),row=result.rows[0];
 result.reason='<img src=x>';row.candidate_id='<svg onload=x>';
 row.reference.assay_description='<script>x</script>';
 row.reference.condition_context={assay_cell_type:'<iframe>'};
 row.reasons=['<object>'];row.condition_review.mismatches=['<embed>'];
 const html=ctx.reportedActivityComparisonTable(result);
 assert.doesNotMatch(html,/<img|<svg|<script|<iframe|<object|<embed/);
 for(const name of ['img','svg','script','iframe','object','embed'])assert.match(html,new RegExp('&lt;'+name));
});

test('a copied condition without its retained assay response is labelled and not presented as verified',()=>{
 const ctx=setup(),result=clone(fixture.result),row=result.rows[0];
 row.reference.assay_context={assay_cell_type:'UNVERIFIED_HEK293'};
 row.reference.condition_context=null;row.reference.assay_context_status='unverified_copy';
 const html=ctx.reportedActivityComparisonTable(result);
 assert.match(html,/보존된 조건 사본 · 원응답 확인 필요/);assert.match(html,/UNVERIFIED_HEK293/);
 assert.doesNotMatch(html,/세포: UNVERIFIED_HEK293/);assert.match(html,/세포: 미기록/);
 row.reference.condition_context={assay_cell_type:'VERIFIED_CHO'};
 row.reference.assay_context_status='retained_assay_response';
 assert.match(ctx.reportedActivityComparisonTable(result),/세포: VERIFIED_CHO/);
});

test('an original tiny difference keeps its exact decimal and source-based direction despite display rounding',()=>{
 const ctx=setup(),result=clone(fixture.result),row=result.rows[0];
 row.ratio.point=1;row.ratio.point_decimal='1.0000000000000000000000000001';
 row.ratio.lower_decimal=row.ratio.point_decimal;row.direction='reference_lower';
 const html=ctx.reportedActivityComparisonTable(result);
 assert.match(html,/1\.0000000000000000000000000001/);assert.match(html,/전체 계산값/);
 assert.match(html,/TARGET_A의 보고 IC50가 더 낮습니다/);assert.match(html,/유효숫자 6자리/);
 assert.doesNotMatch(html,/보고 IC50가 같습니다/);
});

test('separate source records for one structure stay separate and in input order',()=>{
 const ctx=setup(),result=clone(fixture.result);
 result.rows=[1.4,1.2068965517,3].map((ratio,index)=>{
  const row=clone(fixture.result.rows[0]);row.source_record_id=100+index;row.pair_index=index;
  row.ratio.point=ratio;return row;
 });
 const html=ctx.reportedActivityComparisonTable(result);
 assert.equal((html.match(/data-activity-contrast-index=/g)||[]).length,3);
 assert.ok(html.indexOf('원 화합물 기록 100')<html.indexOf('원 화합물 기록 101'));
 assert.ok(html.indexOf('원 화합물 기록 101')<html.indexOf('원 화합물 기록 102'));
 assert.match(html,/<strong>1\.4<\/strong>/);assert.match(html,/<strong>1\.2069<\/strong>/);assert.match(html,/<strong>3<\/strong>/);
});

test('42 retained records display across two pages without changing the scientific denominator',()=>{
 const ctx=setup(),result=clone(fixture.result);
 result.summary={requested_pairs:42,computed_exact:42,computed_interval:0,unresolved:0};
 result.total_rows=42;result.offset=0;result.has_more=true;
 result.rows=Array.from({length:30},(_,i)=>({...clone(fixture.result.rows[0]),pair_index:i}));
 const first=ctx.reportedActivityComparisonTable(result);
 assert.match(first,/1–30 \/ 42쌍/);assert.match(first,/점값 42쌍/);
 assert.match(first,/data-action="prev" disabled/);assert.doesNotMatch(first,/data-action="next" disabled/);
 result.offset=30;result.has_more=false;result.rows=result.rows.slice(0,12).map((row,i)=>({...row,pair_index:30+i}));
 const last=ctx.reportedActivityComparisonTable(result);
 assert.match(last,/31–42 \/ 42쌍/);assert.match(last,/data-action="next" disabled/);
 assert.doesNotMatch(last,/data-action="prev" disabled/);
});
