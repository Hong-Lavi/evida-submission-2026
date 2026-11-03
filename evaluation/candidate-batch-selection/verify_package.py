"""Offline archive/source/dataset identity checks, no model or GPU calls."""
from pathlib import Path
import ast,csv,hashlib,json
ROOT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
manifest=load(ROOT/'source-map.json')
for entry in manifest['files']:
 assert sha(ROOT/entry['public_path'])==entry['public_sha256'],entry['public_path']
 if not entry['operations']:assert entry['original_sha256']==entry['public_sha256']
for row in load(ROOT/'source-parity.json')['files']:
 assert sha(ROOT/row['public_path'])==row['public_sha256'];ast.parse((ROOT/row['public_path']).read_text())
 assert row['all_function_class_ast_equal']
for f in ROOT.rglob('*'):
 if f.is_file():assert f.name not in ['author-acquisition_functions.py','author_probe.py']
protocol=load(ROOT/'records/acquisition-01/protocol.json');total=0
for task in protocol['tasks']:
 name=task['task'];gold=load(ROOT/'data'/name/'gold.json')
 with (ROOT/'source-data'/ (name+'.csv')).open()as f:rows=list(csv.DictReader(f))
 expected={f'{name}:{i}':float(r['y [pEC50/pKi]'])for i,r in enumerate(rows)if r['split']=='test'}
 assert {r['candidate_id']:r['p_activity']for r in gold}==expected;total+=len(gold)
 packet=load(ROOT/'records/acquisition-01/inputs'/ (name+'.json'))
 assert set(packet['candidate_ids'])==set(expected)
 assert sha(ROOT/'posterior'/ (name+'.npz'))==packet['posterior_sha256']
assert total==9802
if (ROOT/'package-seal.json').exists():
 for path,digest in load(ROOT/'package-seal.json')['files'].items():assert sha(ROOT/path)==digest,path
print(json.dumps({'status':'PASS','exported_artifacts':len(manifest['files']),'source_function_parity_records':len(load(ROOT/'source-parity.json')['files']),'tasks':30,'gold_source_csv_identity_rows':total,'unlicensed_qpo_author_code_included':False,'posterior_npz_included':30,'model_calls':0,'GPU':False}))
