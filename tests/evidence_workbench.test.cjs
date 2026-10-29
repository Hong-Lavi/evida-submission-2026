const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const web=path.join(__dirname,'..','web','evidence-workbench.js');
const research=fs.readFileSync(path.join(__dirname,'..','web','research.js'),'utf8');
const wordingSource=research.slice(research.indexOf('function researcherWording('),research.indexOf('function candidateDisplayName('));
const fixtures=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures','evidence_workbench_saved_cases.json'),'utf8'));
const htmlEscape=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
function load(saved){
  const context={state:saved,esc:htmlEscape,artifactName:id=>id,
    sourceLinks:ids=>ids.map(id=>`<button data-action="source" data-id="${htmlEscape(id)}">원자료</button>`).join(''),
    button:(action,label,attrs)=>`<button data-action="${action}" ${attrs}>${label}</button>`};
  vm.createContext(context);
  vm.runInContext(wordingSource,context);
  vm.runInContext(fs.readFileSync(web,'utf8')+'\nglobalThis.audit={renderEvidenceWorkbench,evidenceWorkbenchScope,evidenceWorkbenchRow};',context);
  context.audit.researcherWording=value=>vm.runInContext(`researcherWording(${JSON.stringify(value)})`,context);
  return context.audit;
}
function claimsFromSaved(saved){
  return (saved.decision?.research_loop?.hypotheses??[]).flatMap(h=>[h,...(h.assessment_scope?.parts??[]),...(h.conditional_alternatives??[])]);
}

for(const [name,saved] of Object.entries(fixtures)){
  const original=JSON.stringify(saved);
  const audit=load(saved),scope=audit.evidenceWorkbenchScope(saved),html=audit.renderEvidenceWorkbench(saved);
  const claims=claimsFromSaved(saved),evidence=claims.flatMap(c=>c.evidence??[]);
  assert.equal(scope.claims.length,claims.length,`${name}: all typed claims remain inspectable`);
  assert.equal(scope.evidence.length,evidence.length,`${name}: every linked interpretation row remains inspectable`);
  assert.equal((html.match(/class="ew-row"/g)||[]).length,evidence.length,`${name}: one row per recorded interpretation`);
  for(const claim of claims){
    assert.ok(html.includes(htmlEscape(audit.researcherWording(claim.statement))),`${name}: display claim missing ${claim.id}`);
    for(const field of ['statement','expected_observation','rationale'])if(claim[field]){
      const display=audit.researcherWording(claim[field]);
      assert.ok(html.includes(htmlEscape(display)),`${name}: display ${field} missing ${claim.id}`);
      for(const scientificToken of String(claim[field]).match(/BDBM:?\d+|CHEMBL\d+|IC50|\d+(?:\.\d+)?\s*(?:%|nM|µM|μM|mg\/kg)/g)??[])
        assert.ok(display.includes(scientificToken),`${name}: scientific token changed in ${field}: ${scientificToken}`);
    }
    for(const alternative of claim.alternatives??[])assert.ok(html.includes(htmlEscape(alternative)),`${name}: recorded competing explanation omitted`);
  }
  for(const row of evidence){
    assert.ok(html.includes(htmlEscape(row.applicability)),`${name}: recorded condition omitted`);
    assert.ok(html.includes(htmlEscape(row.detail)),`${name}: recorded interpretation omitted`);
    assert.ok(html.includes(htmlEscape(row.source_id)),`${name}: exact source ID omitted`);
  }
  assert.equal(scope.searches.length,saved.artifacts.filter(a=>['literature','clinical_trial_search','drug_label_search','entity_search'].includes(a.kind)&&Number.isInteger(a.meta?.summary?.returned)).length);
  assert.ok(html.includes('확인 필요 · 원문 인용과 행 위치'),`${name}: unrecorded quotation must stay missing`);
  assert.ok(!html.includes('검색 포괄률 100%'),`${name}: no invented coverage rate`);
  assert.equal(JSON.stringify(saved),original,`${name}: rendering must not mutate stored records or original source text`);
  console.log(`${name}: ${scope.claims.length} claims, ${scope.evidence.length} evidence rows, ${scope.searches.length} search records, ${scope.fullText.length} returned full texts`);
}

{
  const saved=structuredClone(fixtures.preeclampsia),audit=load(saved);
  const first=saved.decision.research_loop.hypotheses[0].evidence[0];
  assert.ok(first.detail.includes('42%'),'saved synthetic value should stay as recorded interpretation');
  assert.ok(audit.evidenceWorkbenchRow(first,saved).includes('확인 필요 · 원문 인용과 행 위치'));
  const orphan={...first,source_type:'artifact',source_id:'art_not_in_workspace'};
  const orphanHtml=audit.evidenceWorkbenchRow(orphan,saved);
  assert.ok(orphanHtml.includes('현재 연구에 연결된 원자료 확인 필요'));
  assert.ok(!orphanHtml.includes('data-action="source"'),'missing artifact must not become an action');
  const exact={...first,source_type:'artifact',source_id:saved.artifacts[0].id,
    anchor:{artifact_id:saved.artifacts[0].id,quote:'recorded exact quote',offset:12}};
  assert.ok(audit.evidenceWorkbenchRow(exact,saved).includes('recorded exact quote'));
  assert.ok(audit.evidenceWorkbenchRow({...exact,anchor:{...exact.anchor,artifact_id:'wrong'}},saved).includes('확인 필요 · 원문 인용과 행 위치'));
}
{
  const saved=structuredClone(fixtures.ipf),audit=load(saved);
  const first=saved.artifacts.find(a=>Number.isInteger(a.meta?.summary?.returned));
  first.meta.summary.total=999999;
  const html=audit.renderEvidenceWorkbench(saved);
  assert.ok(html.includes(`이 요청의 반환 ${first.meta.summary.returned}행`));
  assert.ok(!html.includes('999999'),'a source total is not the fetched row count or unique-paper denominator');
}
