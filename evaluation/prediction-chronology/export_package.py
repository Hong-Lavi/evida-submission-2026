#!/usr/bin/env python3
"""Explicit, allowlisted public export. No provider calls or original mutations."""
import argparse, ast, hashlib, json, re
from pathlib import Path

def digest(b): return hashlib.sha256(b).hexdigest()
def encoded(x): return (json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 src=a.source.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 if (out/'export-manifest.json').exists():raise SystemExit('Refusing to overwrite an existing export')
 entries=[]
 # Replace private absolute filesystem locators only; retain the scientific content.
 prefixes=[(str(src),'SOURCE'),(str(src.parent),'AUDIT'),(str(src.parents[2]),'WORKSPACE')]
 def cleantext(s,ops,ptr):
  old=s
  for prefix,label in prefixes:s=s.replace(prefix,'<'+label+'>')
  # Remaining absolute host locations (e.g. CLI interpreter); no URL matching.
  s=re.sub(r'(?<![:/])/(?:data/user_home|home|tmp)/[^\s\"\'<>),;]*','<PRIVATE_HOST_PATH>',s)
  if old!=s:ops.append({'pointer':ptr,'operation':'replace_private_filesystem_locator','original_value_sha256':digest(old.encode())})
  return s
 def clean(v,ops,ptr=''):
  if isinstance(v,str):return cleantext(v,ops,ptr)
  if isinstance(v,list):return [clean(x,ops,ptr+'/'+str(i)) for i,x in enumerate(v)]
  if isinstance(v,dict):
   return {cleantext(k,ops,ptr+'/[key]'):clean(x,ops,ptr+'/'+k.replace('~','~0').replace('/','~1')) for k,x in v.items()}
  return v
 def export(rel,target=None,exact=False,request=False):
  p=src/rel;raw=p.read_bytes();ops=[];target=target or 'records/'+rel
  if request:
   obj=json.loads(raw);original=obj['source_packet']
   obj['source_packet']={'external_input_required':True,'original_file_sha256':digest((src/'frozen-source.json').read_bytes()),'descriptor':'source-descriptor.json'}
   ops.append({'pointer':'/source_packet','operation':'omit_restricted_adapted_source_packet','original_value_canonical_sha256':digest(json.dumps(original,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())})
   transformed=encoded(clean(obj,ops))
  elif p.suffix=='.json':
   obj=json.loads(raw);new=clean(obj,ops);transformed=encoded(new) if ops else raw
  else:
   new=cleantext(raw.decode(),ops,'[text]');transformed=new.encode()
  if exact and transformed!=raw:raise ValueError('Scientific record would be changed: '+rel)
  dest=out/target;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(transformed)
  entries.append({'original_relative_path':rel,'original_sha256':digest(raw),'public_path':target,'public_sha256':digest(transformed),'operations':ops})
 for rel in ['component-protocol.json','component-protocol-receipt.json','fixed-challenges.json','BLIND_REVIEW_GUIDE.md','unblinded-comparison.json','COMPARISON.md','EXECUTION_HANDOFF.md','setup-attempt-accounting.json','startup-failure-audit.json','frozen-arm-identity-audit.json','schema-validation.json','chronology-only.patch']:
  export(rel)
 for rel in ['run_component_assay.py','execute_controlled.py','launch_attempt_02.py','launch_attempt_03.py','seal_component_outputs.py']:
  export(rel)
 for p in sorted((src/'frozen-product-inputs').rglob('*')):
  if p.is_file() and p.suffix in {'.py','.md'}:export(str(p.relative_to(src)))
 for p in sorted((src/'independent-review').rglob('*')):
  if p.is_file() and p.suffix in {'.json','.md','.py'}:
   rel=str(p.relative_to(src));export(rel,exact=('judgments/' in rel or 'criterion-interpretation' in rel or 'manual-batch' in rel))
 for rel in ['component-terminal.json']:
  export(rel)
 for rel in ['component-terminal.json','component-protocol-receipt.json']:
  export('attempt-02/'+rel)
 for rel in ['component-terminal.json','component-protocol-receipt.json','output-seal.json','controlled-execution-receipt.json','execution-amendment.json','blind-file-manifest.json']:
  export('attempt-03/'+rel)
 for i in range(1,19):
  b=f'B{i:02}'
  export(f'component-calls/{b}/receipt.json');export(f'attempt-02/component-calls/{b}/receipt.json')
  for name in ['answer.txt','receipt.json','provider-response.json','parsed-scientific-records.json']:
   rel=f'attempt-03/component-calls/{b}/{name}'
   if (src/rel).exists():export(rel,exact=name in {'answer.txt','receipt.json','parsed-scientific-records.json'})
  export(f'attempt-03/component-calls/{b}/request.json',request=True)
  export(f'attempt-03/blind-review/{b}/visible-case.json',exact=True)
 # Exact author-defined TASK/ENVELOPE/QUESTION without importing the execution driver.
 tree=ast.parse((src/'run_component_assay.py').read_text());sem={}
 for node in tree.body:
  if isinstance(node,ast.Assign):
   for name in node.targets:
    if isinstance(name,ast.Name) and name.id in {'TASK','ENVELOPE','QUESTION'}:sem[name.id]=ast.literal_eval(node.value)
 (out/'transport-semantics.json').write_bytes(encoded(sem))
 packet=json.loads((src/'frozen-source.json').read_text())
 descriptor={'doi':packet['doi'],'citation':packet['citation'],'original_file_sha256':digest((src/'frozen-source.json').read_bytes()),'original_bytes':(src/'frozen-source.json').stat().st_size,'included':False,'reason':'Paper is CC BY-NC-ND 4.0; redistribution rights for translated/adapted extraction not established. No source packet text exported.','license_evidence_urls':['https://pmc.ncbi.nlm.nih.gov/articles/PMC12618868/','https://www.atsjournals.org/doi/pdf/10.1165/rcmb.2024-0614OC'],'content_hash_encoding':'JSON UTF-8 ensure_ascii=False sort_keys=True separators=(comma,colon)','rows':[]}
 for row in packet['rows']:
  descriptor['rows'].append({k:row[k] for k in ['id','doi','source_url','section']} | {'content_fields':list(row['content']) if isinstance(row['content'],dict) else None,'content_sha256':digest(json.dumps(row['content'],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()),'row_sha256':digest(json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())})
 (out/'source-descriptor.json').write_bytes(encoded(descriptor))
 # Local exact-sequence check is a review aid, not a license or plagiarism verdict.
 def strings(v):
  if isinstance(v,str):yield v
  elif isinstance(v,dict):
   for x in v.values():yield from strings(x)
  elif isinstance(v,list):
   for x in v:yield from strings(x)
 source_strings=[s for row in packet['rows'] for s in strings(row['content'])]
 import difflib
 overlaps=[]
 for i in range(1,19):
  b=f'B{i:02}';answer=(src/f'attempt-03/component-calls/{b}/answer.txt').read_text()
  match=max((difflib.SequenceMatcher(None,answer,s,autojunk=False).find_longest_match() for s in source_strings),key=lambda x:x.size)
  overlaps.append({'blind_id':b,'longest_exact_contiguous_match_characters':match.size,'answer_offset':match.a,'matched_answer_text':answer[match.a:match.a+match.size]})
 (out/'source-overlap-audit.json').write_bytes(encoded({'method':'Longest exact contiguous character overlap against frozen row content string values. Does not compare full publisher text or establish redistribution rights. Outputs and quoted judgments are unchanged.','rows':overlaps}))
 manifest={'format':'evida.explicit-export.v1','excluded':['source packet body and its internal extraction/permission metadata','provider trace directories and raw CLI logs','prepared-input indexed payload/context bodies','private identity-key file; published mapping is the authorized unblinded results'],'scientific_strings':'All raw answers, parsed records, visible cases, rubric interpretations, manual judgments and batch seals retained byte-for-byte. Request source slot externalized explicitly. Filesystem locators alone redacted in remaining exported records.','original_hash_meaning':'Hashes refer to original bytes before export; retained historical seal hashes bind those originals, not path-redacted exports.','files':entries}
 (out/'export-manifest.json').write_bytes(encoded(manifest));print(json.dumps({'exported_files':len(entries),'answer_count':18,'maximum_exact_overlap_characters':max(x['longest_exact_contiguous_match_characters'] for x in overlaps)}))
if __name__=='__main__':main()
