// Scientific distinctions that must survive rendering, independently of the worker.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const ctx = vm.createContext({
  esc: s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  json: v => JSON.stringify(v), sourceLinks: () => '', button: () => '',
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/proposal-qualification.js'), 'utf8'), ctx);

test('Ki with no retained unit is not displayed as IC50 or nM', () => {
  const html = ctx.qualificationParent({parent_id:'BDBM:14364', reported_measurements:[{
    original_measurement:{affinity_type:'Ki',affinity:'270'}}]});
  assert.match(html, /Ki/); assert.match(html, /270/); assert.match(html, /단위 미확인/);
  assert.doesNotMatch(html, /IC50|nM/);
});
test('A generated intermediate is identified separately from a measured parent', () => {
  const html = ctx.qualificationParent({parent_id:'guided-1-proposed-1', parent_kind:'generated_unmeasured'});
  assert.match(html, /생성 중간체/); assert.match(html, /원 측정값은.*확인이 필요/);
});
test('A prediction and an exact source rediscovery have separate meanings', () => {
  const html = ctx.qualificationCandidate({candidate_id:'p',proposal_status:'proposed_unmeasured',
    original_prediction:{predicted_pIC50:8.2},exact_source_matches:[{parent_id:'known',
      original_parent:{label:{source_values_nm:[4.6],pIC50:8.337}}}],actual_parents:[]});
  assert.match(html, /8\.2.*새 측정값 아님/); assert.match(html, /원출처의 동일 구조/);
  assert.match(html, /4\.6 nM/); assert.match(html, /원 보고값/);
});
