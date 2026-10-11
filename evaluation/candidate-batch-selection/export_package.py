"""Allowlisted public export; omit unlicensed author code and private locators."""
import argparse,ast,hashlib,json,re,shutil
from pathlib import Path

def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(x):return(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();base=a.base.resolve();out=a.out.resolve();trial=base/'batch-selection-trial';workspace=base.parents[1]
 out.mkdir(exist_ok=True);entries=[];parity=[]
 if (out/'source-map.json').exists():raise ValueError('Already exported')
 def cleantext(s,ops,ptr):
  old=s;s=s.replace(str(base),'@AUDIT').replace(str(workspace),'@WORKSPACE')
  s=re.sub(r'(?i)(exec session|session)\s*[=:]?\s*\d{4,}',r'\1 [operational-id-redacted]',s)
  s=re.sub(r'(?<![:/])/(?:data/user_home|home|tmp)/[^\s\"\'<>),;]*','@PRIVATE_HOST_PATH',s)
  # Remove operational process/session identifiers, never scientific seed/row IDs.
  if s!=old:ops.append({'pointer':ptr,'operation':'replace_private_filesystem_locator','original_value_sha256':sha(old.encode())})
  return s
 def clean(v,ops,ptr=''):
  if isinstance(v,str):return cleantext(v,ops,ptr)
  if isinstance(v,list):return[clean(x,ops,ptr+'/'+str(i))for i,x in enumerate(v)]
  if isinstance(v,dict):
   result={}
   for k,x in v.items():
    if k in {'exec_session','session_id','thread_id'}:
     ops.append({'pointer':ptr+'/'+k,'operation':'remove_operational_session_id','original_value_sha256':sha(encoded(x))});continue
    result[cleantext(k,ops,ptr+'/[key]')]=clean(x,ops,ptr+'/'+k.replace('~','~0').replace('/','~1'))
   return result
  return v
 def add(src,dest,exact=False):
  raw=src.read_bytes();ops=[]
  if src.suffix in {'.npz','.csv'}:data=raw
  elif src.suffix=='.json':
   try:
    obj=json.loads(raw);new=clean(obj,ops);data=encoded(new)if ops else raw
   except json.JSONDecodeError:
    data=cleantext(raw.decode(),ops,'[invalid-json-fixture-text]').encode()
  else:data=cleantext(raw.decode(),ops,'[text]').encode()
  if exact and data!=raw:raise ValueError('Scientific bytes changed: '+str(src))
  f=out/dest;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
  logical='@AUDIT/'+str(src.relative_to(base))if src.is_relative_to(base)else'@WORKSPACE/'+str(src.relative_to(workspace))
  entries.append({'original_locator':logical,'original_sha256':sha(raw),'public_path':dest,'public_sha256':sha(data),'operations':ops})
  if src.suffix=='.py':
   before=ast.parse(raw.decode());after=ast.parse(data.decode());functions=lambda t:{n.name:ast.dump(n,include_attributes=False)for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
   assert functions(before)==functions(after),src
   parity.append({'public_path':dest,'byte_identical':raw==data,'all_function_class_ast_equal':True,'original_sha256':sha(raw),'public_sha256':sha(data)})
 for version in ['acquisition-01','acquisition-02']:
  root=trial/version
  for f in sorted(root.iterdir()):
   if f.is_file()and f.suffix in {'.py','.json','.md','.patch','.stdout','.stderr'}and f.name not in {'author-acquisition_functions.py','author_probe.py'}:
    add(f,'records/'+version+'/'+f.name)
  for sub in ['run-01','inputs','revision-02','synthetic-worker']:
   folder=root/sub
   if not folder.exists():continue
   for f in sorted(folder.rglob('*')):
    if f.is_file()and f.suffix in {'.json','.txt','.py','.md','.stdout','.stderr'}and f.name not in {'author-acquisition_functions.py','author_probe.py'}:
     add(f,'records/'+version+'/'+str(f.relative_to(root)))
 for f in sorted((trial/'reconstruction-01').iterdir()):
  if f.is_file()and f.suffix in {'.npz','.json'}:add(f,'posterior/'+f.name,exact=f.suffix=='.npz')
 for name in ['reconstruct_gp.py','run_reconstruction.py','root-review-01.json']:
  add(trial/name,'provenance/'+name)
 for sub in ['review-01','review-02']:
  for f in sorted((trial/sub).iterdir()):
   if f.is_file()and f.suffix in {'.py','.json','.md','.stdout','.stderr'}:add(f,'review/'+sub+'/'+f.name)
 gp=base/'gp-public-package'
 for f in (gp/'licenses').iterdir():
  if f.is_file():add(f,'licenses/'+f.name,exact=True)
 add(gp/'dataset-pins.json','data/dataset-pins.json',exact=True)
 tasks=json.loads((trial/'acquisition-01/protocol.json').read_text())['tasks']
 for task in tasks:
  name=task['task'];add(Path(task['gold_path']),'data/'+name+'/gold.json',exact=True)
  for f in (gp/'source-data').rglob(name+'.csv'):add(f,'source-data/'+name+'.csv',exact=True)
  for filename in ['gp-fit.json','predictions.json']:
   add(base/'tanimoto-trial/run-01'/name/filename,'model-reference/'+name+'/'+filename)
 for name in ['protocol.json','protocol-receipt.json']:
  add(base/'tanimoto-trial'/name,'model-reference/'+name)
 for name in ['scored-results.json','scored-results-v2.json','sealed-predictions.json']:
  add(base/'tanimoto-trial/run-01'/name,'model-reference/'+name)
 (out/'source-map.json').write_bytes(encoded({'format':'evida.explicit-export.v1','excluded':['qPO author-acquisition_functions.py and author_probe.py: no redistribution license established','raw private provider context or credentials','cached binaries and Python bytecode'],'filesystem_locators':'@AUDIT and @WORKSPACE are logical archival locators, not public absolute paths. Portable preparation binds them explicitly.','scientific_values':'Selections, activity labels, predictions, posterior NPZ and scientific metric values are preserved. Only host locators and operational session metadata are removed.','files':entries}))
 (out/'source-parity.json').write_bytes(encoded({'status':'PASS','files':parity,'scope':'Every exported Python function/class AST compared to its original. Untouched methods, sampler and scorer scientific bodies remain exact; acquisition-02 numerical amendment remains explicitly separate.'}))
 print(json.dumps({'files':len(entries),'source_parity_files':len(parity),'bytes':sum(f.stat().st_size for f in out.rglob('*')if f.is_file())}))
if __name__=='__main__':main()
