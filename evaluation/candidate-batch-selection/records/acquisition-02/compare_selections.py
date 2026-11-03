"""After seal, compare selections only. Gold and scored outputs are forbidden."""
from pathlib import Path
import sys,json,collections
from common import HERE,load,save,sha,frozen_protocol
from score_selection import gate

def deny(event,args):
 if event=='open'and isinstance(args[0],(str,bytes)):
  if any(s in str(args[0])for s in ['evaluation-only','test-gold','scored-results']):raise PermissionError('Selection comparison cannot open gold or scores')
sys.addaudithook(deny)
old=HERE.parent/'acquisition-01';protocol=frozen_protocol()
oldrows=gate(load(old/'protocol.json'),old/'run-01',sha(old/'protocol.json'))
newrows=gate(protocol,HERE/'run-01',sha(HERE/'protocol.json'))
assert len(oldrows)==len(newrows)==3600
counts=collections.Counter();by_method=collections.Counter();by_task=collections.Counter();changes=[]
for before,after in zip(oldrows,newrows):
 keys=['task','method','seed','batch'];assert all(before[k]==after[k]for k in keys)
 changed=[field for field in ['selected_ids','fallback_selected_ids','status']if before[field]!=after[field]]
 if changed:
  for field in changed:counts[field]+=1
  by_method[after['method']]+=1;by_task[after['task']]+=1
  changes.append({**{k:after[k]for k in keys},'changed_fields':changed})
result={'status':'COMPLETE_BEFORE_NEW_SCORING','compared_rows':3600,'changed_rows':len(changes),'unchanged_rows':3600-len(changes),'changed_field_counts':{f:counts[f]for f in ['selected_ids','fallback_selected_ids','status']},'by_method':dict(by_method),'by_task':dict(by_task),'changes':changes,'original_selection_seal_sha256':sha(old/'run-01/selection-seal.json'),'corrected_selection_seal_sha256':sha(HERE/'run-01/selection-seal.json'),'new_gold_reads':0,'new_scoring_performed':False,'old_and_new_complete_gate':'PASS','claim':'Selection identity comparison only; no new scientific metric or performance inference.'}
save(HERE/'selection-comparison.json',result)
print(json.dumps(result,indent=2))
