"""Verify saved public structures offline; RDKit required, no generation/scoring."""
import sqlite3  # Match the product's shared-library load order.
import argparse
import csv
import hashlib
import json
from pathlib import Path
from rdkit import Chem

HERE = Path(__file__).resolve().parent

def identity(smiles, stereo=True):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError('Invalid returned structure')
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=stereo)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--official-dir', type=Path)
    args = ap.parse_args()
    meta = json.loads((HERE/'returned-structure-sources.json').read_text())
    raw = (HERE/'returned-structures.csv').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == meta['returned_csv_sha256']
    with (HERE/'returned-structures.csv').open(newline='') as f:
        all_rows = list(csv.DictReader(f))
    assert len(all_rows) == meta['rows'] == 300
    assert {r['task'] for r in all_rows} == {s['task'] for s in meta['tasks']}
    checked = []
    for source in meta['tasks']:
        task = source['task']
        rows = [r for r in all_rows if r['task'] == task]
        iso = {identity(r['smiles']) for r in rows}
        conn = {identity(r['smiles'],False) for r in rows}
        counts = {'rows':len(rows),'valid_rows':len(rows),'unique_isomeric':len(iso),'unique_connectivity':len(conn),'unchanged_transformed_parent':sum(identity(r['smiles'])==identity(r['source_smiles']) for r in rows)}
        assert all(r['source_id'] in source['prepared_source_ids'] and int(r['context_radius']) in [1,2,3] and json.loads(r['transformation']) for r in rows)
        if args.official_dir:
            path = args.official_dir/source['official_file']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == source['official_file_sha256']
            with path.open(newline='') as f:
                official = list(csv.DictReader(f))
            seeds = [official[int(i.rsplit(':',1)[1])] for i in source['prepared_source_ids']]
            assert len(seeds)==120 and all(r['split']=='train' for r in seeds)
            for row in rows:
                original = official[int(row['source_id'].rsplit(':',1)[1])]
                assert original['split']=='train' and identity(original['smiles'])==identity(row['source_smiles'])
            for stereo,label,values in [(True,'isomeric',iso),(False,'connectivity',conn)]:
                seed_set = {identity(r['smiles'],stereo) for r in seeds}
                train_set = {identity(r['smiles'],stereo) for r in official if r['split']=='train'}
                counts['novel_vs_source_'+label] = len(values-seed_set)
                counts['novel_vs_official_train_'+label] = len(values-train_set)
        for key,value in counts.items():
            assert value == source['expected_counts'][key], (task,key,value)
        checked.append({'task':task,**counts})
    print(json.dumps({'status':'PASS','tasks':checked,'official_inputs_and_novelty_checked':args.official_dir is not None,'original_yield_trace_replayed':False,'trace_scope':'Original trace hashes are preserved; this public check validates saved structures and source rows, not the full generation trace.','cross_task_unique_claim':False,'new_generation_scoring_network':0},indent=2))

if __name__=='__main__':
    main()
