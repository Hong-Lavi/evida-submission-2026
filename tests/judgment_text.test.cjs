const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const context=vm.createContext({
  esc:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  state:{artifacts:[{id:'art_1234567890abcdef',title:'Source'}]},artifactName:()=> 'Source',
  button:(action,label,attributes)=>`<button data-action="${action}" ${attributes}>${label}</button>`,
  document:{addEventListener(){},querySelector(){return null},getElementById(){return null}},
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/research.js'),'utf8'),context);
test('Actual IPF generated candidate identity survives rationale rendering',()=>{
  const text='복구 목록의 proposed-1은 BDBM:251737에 연결된 미측정 구조다.';
  assert.equal(context.judgmentText(text),text);
});
test('Source prose and longer scientific identifiers are never translated as enum values',()=>{
  for(const text of ['The authors proposed a mechanism that was challenged.',
      'molecule:generated:art_deadbeefdeadbeef:proposed-12',
      'inconclusive-assay; consistent_in_context-v2'])assert.equal(context.judgmentText(text),text);
});
test('A standalone known status retains its readable label',()=>{
  assert.equal(context.judgmentText('proposed'),'잠정 가설 상태');
  assert.equal(context.judgmentText('challenged'),'다시 검토할 근거 있음 상태');
});
test('Source links still resolve while unrelated markup and candidate IDs stay safe',()=>{
  const html=context.judgmentText('<script>x</script> proposed-1 art_1234567890abcdef');
  assert.match(html,/&lt;script&gt;x&lt;\/script&gt; proposed-1/);
  assert.match(html,/data-action="source" data-id="art_1234567890abcdef"/);
  assert.doesNotMatch(html,/<script>/);
});
test('Chemical display vocabulary preserves identifiers and nonchemical parent meaning',()=>{
  assert.equal(context.researcherWording('부모 BDBM:14364와 제안 2를 비교한다.'),
    '출발 화합물 BDBM:14364와 설계 후보 2를 비교한다.');
  assert.equal(context.researcherWording('부모 화합물 proposed-2'), '출발 화합물 proposed-2');
  assert.equal(context.researcherWording('부모와 환자의 유전형을 비교한다.'), '부모와 환자의 유전형을 비교한다.');
  assert.equal(context.judgmentText('부모 BDBM:14364와 proposed-2'), '부모 BDBM:14364와 proposed-2');
});
