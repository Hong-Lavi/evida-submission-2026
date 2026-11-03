"""Bind unchanged selection/scoring functions to a new local replay directory."""
from pathlib import Path
import argparse,hashlib,json,shutil,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--attempt',choices=['acquisition-01','acquisition-02'],default='acquisition-02');ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 entries=load(ROOT/'source-map.json')['files']
 for e in entries:assert sha(ROOT/e['public_path'])==e['public_sha256'],e['public_path']
 original=ROOT/'records'/a.attempt;protocol=load(original/'protocol.json');source_names=['acquisition.py','common.py','selection_worker.py','run_selection.py','score_selection.py']
 for name in source_names:shutil.copy2(original/name,out/name)
 inputs=out/'inputs';inputs.mkdir();task_bindings=[];pins={}
 for task in protocol['tasks']:
  name=task['task'];packet=load(ROOT/'records/acquisition-01/inputs'/ (name+'.json'));posterior=ROOT/'posterior'/ (name+'.npz');assert sha(posterior)==packet['posterior_sha256']
  packet['posterior_path']=str(posterior);file=inputs/(name+'.json');write(file,packet)
  task_bindings.append({**task,'packet':str(file),'gold_path':str(ROOT/'data'/name/'gold.json')});pins[str(file)]=sha(file);pins[str(posterior)]=sha(posterior)
 # Paths and active integrity pins change; all scientific configuration stays fixed.
 bound={**protocol,'status':'PORTABLE_REPLAY_PREPARED','tasks':task_bindings,'source_pins':{str(out/n):sha(out/n)for n in source_names},'input_pins':pins}
 write(out/'protocol.json',bound)
 write(out/'protocol-receipt.json',{'at':datetime.now(timezone.utc).isoformat(),'protocol_sha256':sha(out/'protocol.json'),'root_review_reference':'PACKAGED_FROZEN_SCIENCE_AND_EXPLICIT_LOCAL_PATH_BINDING','real_selection_started':False,'gold_opened':False})
 preserved={k:v for k,v in protocol.items()if k not in ['status','tasks','source_pins','input_pins']};assert all(bound[k]==v for k,v in preserved.items())
 for before,after in zip(protocol['tasks'],bound['tasks']):assert all(before[k]==after[k]for k in before if k not in ['packet','gold_path'])
 report={'status':'PREPARED_NOT_EXECUTED','attempt':a.attempt,'unchanged_runtime_source_bytes':{n:sha(out/n)for n in source_names},'scientific_fields_unchanged':True,'adaptations':['Resolve local packet/posterior/gold paths','Replace historical integrity graph with active local source/input pins after full export integrity verification','Generate new protocol receipt for the local binding'],'model_calls':0,'GPU':False,'selection_executed':False,'scoring_executed':False,'warning':'This preparation does not rerun acquisition. New runtime, CPU and BLAS details can change numerical sampling; preserve all new outputs and failures.'}
 write(out/'portable-preparation.json',report);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
