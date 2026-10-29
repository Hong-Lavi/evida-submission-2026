const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function view(){
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const context={esc,number:esc,state:{id:'workspace'},sourceLinks:ids=>ids.map(esc).join(' '),button:(action,label,attrs)=>`<button data-action="${action}" ${attrs}>${label}</button>`};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/source-documents.js'),'utf8'),context);
  return context;
}

test('an uploaded text source keeps its long counterevidence, supplied citation and original locator visible',()=>{
  const context=view(),tail='However, the paired functional outcome was preserved. µM · β · 한글';
  const text='Reported observation.\r\n'.repeat(500)+tail;
  const html=context.uploadedSourceDocumentView({source_artifact_id:'original',document_format:'text',extraction:{status:'text_extracted'},supplied_metadata:{citation:'Researcher entry <script>alterSource()</script>'},rows:[{kind:'text_paragraph',row_id:'text:paragraph:42',paragraph_number:42,text,byte_start:22140,byte_end:45100,line_start:45,line_end:546}],offset:41,total_rows:42});
  assert.ok(html.includes(text));assert.ok(html.includes(tail));
  assert.match(html,/원본 바이트 22140–45100/);assert.match(html,/문단 42/);
  assert.match(html,/연구자가 함께 적은 조건·출처/);assert.match(html,/&lt;script&gt;alterSource/);assert.doesNotMatch(html,/<script>/);
  assert.match(html,/\/artifacts\/original\?original=1/);
});

test('partial PDF extraction retains warnings and blank physical pages alongside the original',()=>{
  const context=view(),html=context.uploadedSourceDocumentView({source_artifact_id:'pdf-original',document_format:'pdf',extraction:{status:'partial_text',warnings:['Rotated text discovered. Output will be incomplete.']},summary:{empty_text_pages:2},rows:[{kind:'pdf_page',row_id:'pdf:page:1',page_number:1,text:'A measured value'},{kind:'pdf_page',row_id:'pdf:page:2',page_number:2,text:''},{kind:'pdf_page',row_id:'pdf:page:3',page_number:3,text:''}]});
  assert.match(html,/일부 본문 준비/);assert.match(html,/Rotated text discovered/);
  assert.match(html,/문자층이 없는 페이지 2개/);assert.match(html,/원문 2쪽/);assert.match(html,/원문 3쪽/);
  assert.match(html,/original=1#page=2/);assert.match(html,/문자층이 비어 있습니다/);
  const raw=context.uploadedSourceFileView({source_document_artifact_ids:['readable-pdf'],extraction_job:{id:'job',status:'succeeded'}},{id:'pdf-original'});
  assert.match(raw,/원본 파일을 보존/);assert.match(raw,/readable-pdf/);
});

test('a preserved source drawer reflects completed extraction and a later attempt from the live workspace',()=>{
  const context=view();
  context.state.jobs=[{id:'old',kind:'source_document',status:'failed',request:{artifact_id:'original'}},{id:'new',kind:'source_document',status:'succeeded',request:{artifact_id:'original'}},{id:'unrelated',kind:'source_document',status:'running',request:{artifact_id:'another-source'}}];
  context.state.artifacts=[{id:'readable-text',kind:'source_document',meta:{consumed_artifacts:['original']}},{id:'unrelated-document',kind:'source_document',meta:{consumed_artifacts:['another-source']}}];
  const html=context.uploadedSourceFileView({extraction_job:{id:'old',status:'queued'},source_document_artifact_ids:[],limits:['Read the original figures before interpreting the extracted text.']},{id:'original'});
  assert.match(html,/문서 본문 준비 완료/);assert.match(html,/readable-text/);
  assert.doesNotMatch(html,/본문 준비 대기|unrelated-document/);
  assert.match(html,/Read the original figures/);
});
