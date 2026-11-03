"""Recreate the exact frozen opaque packets from separately acquired official CSVs.
No download, R, model, inference or score execution. Does not overwrite output.
"""
from pathlib import Path
import argparse,csv,hashlib,json,math,random
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()
def reconstruct(expression,metadata,output):
 protocol=json.loads((ROOT/'frozen/protocol.json').read_text());panel=json.loads((ROOT/'data/panel.json').read_text())
 assert sha(expression)=='a97264b92be783e84c974af5090ea4f8fd3c27c087aac5d44e45fa7fc4e22a80'
 expected_meta=[v for k,v in protocol['source_pins'].items() if k.endswith('/knockTF_meta.csv')];assert len(expected_meta)==1 and sha(metadata)==expected_meta[0]
 with Path(metadata).open(newline='') as f:rows=list(csv.DictReader(f))
 assert len(rows)==907;random.Random(20261011).shuffle(rows);chosen=[];tfs=set();profiles=set()
 for row in rows:
  if len(chosen)==30:break
  if row['TF'] in tfs or row['Profile.ID'] in profiles:continue
  tfs.add(row['TF']);profiles.add(row['Profile.ID']);chosen.append(row)
 for actual,saved in zip(chosen,panel):assert (actual[''],actual['TF'],actual['Profile.ID'])==(saved['published_task_id'],saved['target'],saved['profile_id'])
 selection={p['published_task_id']:p['task_id'] for p in panel};packets={};seen=set()
 with Path(expression).open(newline='') as f:
  reader=csv.reader(f);genes=next(reader)[1:];assert len(genes)==len(set(genes))==21985
  for row in reader:
   task=row[0];assert task not in seen and len(row)==21986;seen.add(task)
   if task not in selection:continue
   values=[float(v) for v in row[1:]];assert all(math.isfinite(v) for v in values)
   opaque=selection[task];x={'task_id':opaque,'gene_values':[{'gene':g,'value':v} for g,v in zip(genes,values)]}
   raw=(json.dumps(x,separators=(',',':'),allow_nan=False)+'\n').encode();assert hashlib.sha256(raw).hexdigest()==protocol['packet_sha256'][opaque+'.json'];packets[opaque]=raw
 assert len(seen)==907 and len(packets)==30
 out=Path(output);out.mkdir(parents=True,exist_ok=False)
 for name,raw in packets.items():(out/(name+'.json')).write_bytes(raw)
 return {'status':'PASS','source_rows':907,'selected_packets':30,'packet_hashes_match':30,'selection_seed':20261011,'method_calls':0}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--expression',required=True);p.add_argument('--metadata',required=True);p.add_argument('--output',required=True);args=p.parse_args();print(json.dumps(reconstruct(args.expression,args.metadata,args.output)))
