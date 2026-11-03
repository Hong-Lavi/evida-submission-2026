"""Maintainer export only; reads preserved experiment, writes this package.
No method execution or network access. Supply --source benchmark directory.
"""
from pathlib import Path
import argparse,json,hashlib,gzip,shutil
P=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);args=parser.parse_args();src=Path(args.source).resolve();workspace=src.parents[1];home=workspace.parents[1]
 replacements=[(str(workspace),'${WORKSPACE}'),(str(home),'${USER_HOME}'),('/tmp/','${TMPDIR}/')]
 def clean(x):
  if isinstance(x,str):
   for old,new in replacements:x=x.replace(old,new)
   return x
  if isinstance(x,list):return [clean(v) for v in x]
  if isinstance(x,dict):return {clean(k):clean(v) for k,v in x.items()}
  return x
 mapping=[]
 def read(path):return json.loads(path.read_text())
 def write(name,obj):
  p=P/name;p.parent.mkdir(parents=True,exist_ok=True);data=(json.dumps(clean(obj),indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode();p.write_bytes(gzip.compress(data,mtime=0) if name.endswith('.gz') else data)
 def record(path,dest,selector=None):
  mapping.append({'source_locator':str(path.relative_to(src)),'source_sha256':sha(path),'export':dest,'selector':selector,'transform':'JSON host-root strings only; scientific numbers/text unchanged; deterministic gzip where indicated'})
 def export(path,dest):record(path,dest);write(dest,read(path))
 result_paths=sorted((src/'run-01/results').glob('*/*.json'));detail_paths=sorted((src/'scored-01/comparisons').glob('*/*.json'))
 assert len(result_paths)==420 and len(detail_paths)==780
 for paths,dest in [(result_paths,'data/terminal-records.json.gz'),(detail_paths,'data/comparison-details.json.gz')]:
  write(dest,[read(p) for p in paths])
  for i,p in enumerate(paths):record(p,dest,f'/{i}')
 for name in ['availability.json','scored-results.json','scoring-seal.json']:export(src/'scored-01'/name,'data/'+name)
 labels=read(src/'selection-labels.json');write('data/panel.json',[{'task_id':x['opaque_id'],'published_task_id':x['task_id'],'target':x['metadata']['TF'],'profile_id':x['metadata']['Profile.ID'],'perturbation_method':x['metadata']['Knock.Method']} for x in labels['selected']]);record(src/'selection-labels.json','data/panel.json','selected minimal factual locators; original full metadata omitted')
 for name in ['protocol.json','execution-freeze.json','pinned-product-regulon-resources.json']:
  export(src/'protocol-v2'/name,'frozen/'+name)
 for name in ['run_trial.py','trial_core.py','worker_runtime.py','method_worker.R','score_trial.py']:
  path=src/'protocol-v2'/name;dest=P/'frozen'/name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(path,dest);mapping.append({'source_locator':str(path.relative_to(src)),'source_sha256':sha(path),'export':'frozen/'+name,'transform':'byte-identical EVIDA harness; no author package source'})
 # Frozen original draft remains explicitly a preregistration record, not current execution status.
 path=src/'protocol-v2/PROTOCOL.md';(P/'frozen/PROTOCOL.md').write_text(clean(path.read_text()));record(path,'frozen/PROTOCOL.md')
 for name in ['supervisor-receipt.json','terminal-seal.json','run-started.json']:
  export(src/'run-01'/name,'receipts/'+name)
 for source,dest in [('download-receipt.json','receipts/acquisition-01.json'),('recovery-01/download-receipt.json','receipts/acquisition-02.json'),('recovery-02/download-receipt.json','receipts/acquisition-03.json'),('independent-output-review-01/verification.json','receipts/output-review.json'),('independent-code-review-v2-01/verification.json','receipts/code-review.json'),('protocol-v2/synthetic-author-01/result.json','receipts/synthetic-author.json'),('protocol-v2/offline-boundaries-06/result.json','receipts/offline-boundaries.json'),('protocol-v2/scorer-synthetic-05/verification.json','receipts/synthetic-scorer.json')]:export(src/source,dest)
 failed=[read(p) for p in result_paths if read(p)['status']!='succeeded'];write('data/failures.json',failed)
 for r in failed:
  for ref in r.get('artifacts',[]):
   path=src/'run-01'/ref['path']
   if path.suffix=='.json' and path.name!='request.json':export(path,'receipts/failure/'+path.name)
 # Preserve observed method identity/budgets without raw original input matrices.
 calls=[]
 for p in sorted((src/'run-01/calls').glob('*/call-*/receipt.json')):calls.append(read(p));record(p,'receipts/method-receipts.json.gz',f'/{len(calls)-1}')
 write('receipts/method-receipts.json.gz',calls)
 write('source-map.json',{'policy':'Only host roots replaced by explicit placeholders; keys, all scientific numeric values, output strings and identifiers retained. Source hashes identify original bytes, not transformed exports. Aggregation/gzip is lossless. Panel uses explicit selected-field projection. Full inputs and prior interaction tables excluded.','path_root_placeholders':['${WORKSPACE}','${USER_HOME}','${TMPDIR}'],'sources':mapping})
 print(json.dumps({'exported_terminal_records':len(result_paths),'comparison_rows':len(detail_paths),'source_mappings':len(mapping)}))
if __name__=='__main__':main()
