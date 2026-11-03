#!/usr/bin/env python3
"""Offline integrity and arithmetic; never automated scientific adjudication."""
import argparse, collections, hashlib, json
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def pointer(obj,path):
 for t in path.strip('/').split('/'):
  t=t.replace('~1','/').replace('~0','~');obj=obj[int(t)] if isinstance(obj,list) else obj[t]
 return obj

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source-packet',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args()
 here=Path(__file__).resolve().parent;records=here/'records';manifest=read(here/'export-manifest.json')
 if (here/'package-seal.json').exists():
  for rel,want in read(here/'package-seal.json')['files'].items():assert sha(here/rel)==want,rel
 pins={e['original_relative_path']:e for e in manifest['files']}
 for e in pins.values():
  assert sha(here/e['public_path'])==e['public_sha256'],e['public_path']
  if not e['operations']:assert e['public_sha256']==e['original_sha256']
 def original_pin(rel,want):assert pins[rel]['original_sha256']==want,(rel,'original pin')
 descriptor=read(here/'source-descriptor.json');source=None
 if a.source_packet:
  assert sha(a.source_packet)==descriptor['original_file_sha256'],'Wrong original source packet'
  source=read(a.source_packet)
  for row,desc in zip(source['rows'],descriptor['rows']):
   assert row['id']==desc['id']
   assert hashlib.sha256(json.dumps(row['content'],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()==desc['content_sha256']
 review=records/'independent-review';criterion=read(review/'criterion-interpretation-01.seal.json')
 for rel,want in criterion['files'].items():
  if rel=='frozen-source.json':assert want==descriptor['original_file_sha256']
  else:original_pin(rel,want)
 assert criterion['answers_read']==0 and not criterion['identity_key_opened']
 sealed={}
 for path in sorted(review.glob('manual-batch-*.seal.json')):
  b=read(path);assert not b['key_opened'];draft=path.name.replace('.seal.json','.json')
  original_pin('independent-review/'+draft,b['manual_draft_sha256'])
  for row in b['judgments']:
   rel='independent-review/'+row['judgment_path'];original_pin(rel,row['judgment_sha256'])
   assert row['blind_id'] not in sealed;sealed[row['blind_id']]=read(records/rel)
 finalseal=read(review/'blinded_review_final.seal.json')
 for rel,want in finalseal['files'].items():original_pin('independent-review/'+rel,want)
 comparison=read(records/'unblinded-comparison.json');assert finalseal['at_utc']<comparison['at_utc']
 original_pin('independent-review/blinded_review_final.seal.json',comparison['review_seal_sha256'])
 original_pin('component-protocol.json',comparison['protocol_sha256'])
 original_pin('attempt-03/output-seal.json',comparison['output_seal_sha256'])
 ids={f'B{i:02}' for i in range(1,19)};assert set(sealed)==ids
 assert {r['blind_id'] for r in comparison['rows']}==ids
 arms=collections.defaultdict(lambda:{'cases':0,'primary_pass':0,'criteria_passed':0,'criteria_total':0})
 quotes=0;schema=collections.Counter();anchors=0;casecounts=collections.Counter();restored=0
 for mapping in comparison['rows']:
  bid=mapping['blind_id'];call=records/'attempt-03/component-calls'/bid;judgment=sealed[bid]
  assert mapping['case_id']==judgment['case_id'];casecounts[judgment['case_id']]+=1
  assert not judgment['key_opened'] and not judgment['arm_identity_known']
  assert criterion['at_utc']<judgment['reviewed_at_utc']<finalseal['at_utc']
  answer=(call/'answer.txt').read_text();assert sha(call/'answer.txt')==judgment['answer_sha256']
  visible=records/'attempt-03/blind-review'/bid/'visible-case.json';assert sha(visible)==judgment['visible_case_sha256']
  request=read(call/'request.json');receipt=read(call/'receipt.json');provider=read(call/'provider-response.json')
  assert provider['payload']['answer']==answer
  assert receipt['status']=='COMPLETED' and receipt['provider_attempts']==1
  assert receipt['requested_model']==receipt['actual_model']==provider['actual_model']=='gpt-6-astra'
  assert receipt['requested_effort']=='max' and provider['actual_provider']=='openai-codex'
  assert provider['identity_observation']['actual_model']=='gpt-6-astra'
  assert provider['substitution_mechanism']=='NONE'
  original_pin(f'attempt-03/component-calls/{bid}/request.json',receipt['request_sha256'])
  contract=request['response_contract'];parsed=json.loads(answer) if contract else None
  if contract:
   import jsonschema
   jsonschema.validate(parsed,contract);assert read(call/'parsed-scientific-records.json')==parsed
   schema['valid']+=1
  else:schema['not_applicable_prose']+=1
  for c in judgment['criteria']:
   for e in c['evidence']:
    q=e['quote'];assert q in answer;assert hashlib.sha256(q.encode()).hexdigest()==e['quote_utf8_sha256']
    start=answer.index(q);assert answer.count('\n',0,start)+1==e['answer_line_start'];assert answer.count('\n',0,start+len(q))+1==e['answer_line_end']
    if 'json_pointer' in e:assert q in pointer(parsed,e['json_pointer'])
    quotes+=1
  if source is not None:
   request['source_packet']=source
   restored_bytes=(json.dumps(request,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
   assert hashlib.sha256(restored_bytes).hexdigest()==receipt['request_sha256'];restored+=1
   if parsed:
    for step in parsed.get('hypothesis_review',{}).get('causal_steps',[]):
     for group in step.get('evidence_groups',[]):
      for anchor in group.get('anchors',[]):
       if anchor.get('artifact_id')=='source_packet':
        assert anchor['quote'] in pointer(source,anchor['path']);anchors+=1
  assert mapping['primary_result']==judgment['primary_result']
  counts=collections.Counter(c['status'] for c in judgment['criteria'])
  assert dict(counts)==mapping['criterion_counts']
  if judgment['primary_result']=='pass':assert set(counts)=={'pass'} and not judgment['failure_conditions_observed']
  arm=arms[mapping['arm']];arm['cases']+=1;arm['primary_pass']+=judgment['primary_result']=='pass';arm['criteria_passed']+=counts['pass'];arm['criteria_total']+=sum(counts.values())
 assert len(casecounts)==6 and set(casecounts.values())=={3}
 assert set(arms)==set(comparison['arms'])
 for arm,v in arms.items():
  published=comparison['arms'][arm];assert v['cases']==published['cases']==6;assert v['primary_pass']==published['primary_counts']['pass'];assert v['criteria_passed']==published['criteria_passed'];assert v['criteria_total']==published['criteria_total']
 setup={}
 for prefix,label in [('', 'original'),('attempt-02/','attempt-02')]:
  receipts=[read(records/f'{prefix}component-calls/B{i:02}/receipt.json') for i in range(1,19)]
  assert all(r['status']=='FAILED' for r in receipts)
  setup[label]={'failed_local_attempts':len(receipts),'recorded_adapter_invocations':sum(r.get('provider_calls',0) for r in receipts),'observed_model_responses':0}
 result={'status':'PASS','scope':'Integrity and arithmetic over sealed manual judgments; no automatic semantic regrading or population accuracy inference.','arms':dict(arms),'model_responses':18,'schema':dict(schema),'verified_judgment_quotes':quotes,'setup_attempts':setup,'source_anchor_check':{'status':'PASS' if source is not None else 'NOT_RUN_REQUIRES_LOCAL_ORIGINAL_PACKET','matched_occurrences':anchors if source is not None else None,'scope':'String/path integrity, not scientific score'},'byte_identical_restored_requests':restored if source is not None else None}
 if a.output:
  with a.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
