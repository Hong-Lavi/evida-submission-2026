const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function view(){
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const context={esc,state:{id:'research'},document:{addEventListener(){}},list:values=>(values??[]).map(esc).join(' '),sourceLinks:ids=>ids.map(esc).join(' '),button:(action,label,attrs,cls)=>`<button data-action="${action}" class="${cls}" ${attrs}>${label}</button>`};
 vm.createContext(context);
 for(const name of ['external-links','source-display','review-record','discovery','mechanism-rank'])vm.runInContext(fs.readFileSync(path.join(__dirname,`../web/${name}.js`),'utf8'),context);
 return context;
}
function uploadedAnchor(){
 return {artifact_id:'extracted',row_index:41,quote:'C6 reduced the marker; the paired outcome was unchanged. <script>change()</script>',source_binding:{source_kind:'source_document',origin:'researcher_upload',artifact_id:'extracted',artifact_sha256:'extraction-sha',row_index:41,row_id:'text:paragraph:42',text_locator:'/rows/41/text',original:{artifact_id:'original',sha256:'original-sha'},location:{paragraph_number:42,byte_start:1123,byte_end:1400,line_start:83,line_end:84},supplied_metadata:{citation:'PMC9999999 — unverified declaration'},bibliographic_identity_verified:false}};
}

test('candidate and mechanism citations open the same preserved paragraph without promoting supplied bibliography',()=>{
 const context=view(),anchor=uploadedAnchor(),before=JSON.stringify(anchor);
 const candidate={kind:'source_candidate',modality:'small_molecule',role:'candidate',conditions:['Synthetic source context'],next_check:'Read the unchanged outcome.',candidate_records:[{record:{mention:anchor}}]};
 const clause={text:'A conditional marker effect',context:{species:'synthetic'},anchor:{artifact_id:anchor.artifact_id,row_index:anchor.row_index,quote:anchor.quote}};
 const check={clauses:[{clause_index:0,status:'verified',source_binding:anchor.source_binding}]};
 for(const html of [context.sourceCandidateInfo(candidate,true),context.reviewClauses({clauses:[clause]},check),context.mechanismClauses({clauses:[clause]},check)]){
  assert.match(html,/연구자가 제공한 문서 · 원문 문단 42/);
  assert.match(html,/data-source-offset="41"/);
  assert.match(html,/data-source-quote="C6 reduced the marker; the paired outcome was unchanged\./);
  assert.match(html,/\/artifacts\/original\?original=1/);
  assert.match(html,/원본 바이트 1123–1400/);
  assert.doesNotMatch(html,/PMC9999999|<script>/);
  assert.match(html,/&lt;script&gt;change/);
 }
 assert.equal(JSON.stringify(anchor),before,'presentation preserves all original statements and receipts');
});

test('PDF and web citations preserve their distinct original locations and reject unsafe external links',()=>{
 const context=view(),pdf=uploadedAnchor();
 pdf.row_index=2;pdf.source_binding.location={page_number:3};pdf.source_binding.extraction={details:{status:'partial_text'}};
 const html=context.sourceAssertionAnchorView(pdf);
 assert.match(html,/원문 3쪽/);assert.match(html,/original=1#page=3/);assert.match(html,/data-source-offset="2"/);assert.match(html,/문서에 추출 한계/);
 const web={artifact_id:'web',row_index:5,quote:'A measured observation.',source_binding:{source_kind:'webpage',row_index:5,text_locator:'/rows/5/text',original:{resolved_url:'https://example.org/source?x=1&y=2',sha256:'html-sha'},location:{}}};
 assert.match(context.sourceAssertionAnchorView(web),/웹에서 가져온 본문/);
 assert.match(context.sourceAssertionAnchorView(web),/href="https:\/\/example.org\/source\?x=1&amp;y=2"/);
 web.source_binding.original.resolved_url='javascript:alterResearch()';
 assert.doesNotMatch(context.sourceAssertionAnchorView(web),/href="javascript:|alterResearch/);
});

test('existing anchors keep exact row navigation and an absent source adds no invented provenance',()=>{
 const context=view();
 const html=context.sourceAssertionAnchorView({artifact_id:'old-article',row_index:0,quote:'Original sentence.'});
 assert.match(html,/data-id="old-article" data-source-offset="0"/);
 assert.doesNotMatch(html,/연구자가 제공한|웹에서 가져온|SHA256/);
 assert.equal(context.sourceAssertionAnchorView({quote:'No source provided.'}),'');
});
