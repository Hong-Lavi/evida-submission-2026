"""Fixed isolated Gypsum-DL/SCScore entry points. No arbitrary code or paths from LLM."""
from collections import Counter
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
from pathlib import Path
import sys


def save(path, body):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(body, allow_nan=False)); temp.replace(path)


def main():
    incoming, output = map(Path, sys.argv[1:])
    envelope = json.loads(incoming.read_text()); request = envelope['input']; cfg = envelope['runtime']
    versions = {name: importlib.metadata.version(name) for name in cfg['packages']}
    if versions != cfg['packages']:
        raise ValueError('Isolated author runtime version differs.')
    from rdkit import Chem
    import numpy as np
    body = {'status':'running', 'rows':[], 'versions':versions, 'tool':request['tool'],
            'parameters':{k:request[k]for k in ('ph_min','ph_max','precision','max_variants','random_seed')if k in request},
            'limits':[], 'author_files':[]}
    if request['tool'] == 'synthetic_complexity':
        spec = importlib.util.spec_from_file_location('scscore_author',cfg['scscore_module'])
        author = importlib.util.module_from_spec(spec); spec.loader.exec_module(author)
        def scalar_sigmoid(x):
            scalar = np.asarray(x)
            if scalar.size != 1: raise ValueError('Expected single author output.')
            return 1/(1+math.exp(-scalar.item()))
        # NumPy 2 no longer implicitly casts a length-one array to float. Only
        # that scalar conversion changes; source, fingerprints and weights stay original.
        author.sigmoid = scalar_sigmoid
        model = author.SCScorer().restore(cfg['scscore_weights'])
        body.update(semantic_type='author_learned_synthetic_complexity_not_route_or_yield',
            compatibility_change='single-output ndarray.item before unchanged scalar sigmoid',
            limits=['SCScore 1–5 estimates learned synthetic complexity, not a synthesis route, yield, potency or safety.',
                    'Author model trained on Reaxys reactions; representation/domain and precursor availability may differ.'])
    else:
        from gypsum_dl.start import prepare_molecules
        body.update(semantic_type='author_3d_state_preparation_not_measured_population_or_affinity',
            limits=['Enumerated protomers, tautomers, stereoisomers and 3D variants are proposed computational states, not measured populations.',
                    'Gypsum force-field conformer energies are not binding free energies or comparable across different compositions/charges.',
                    'Variant and thoroughness bounds can omit states. Source-parent mapping and all returned states are retained.'])
    save(output.parent/'progress.json',body)
    elements = lambda mol: dict(Counter(a.GetAtomicNum()for a in mol.GetAtoms()if a.GetAtomicNum()>1))
    for number, choice in enumerate(request['structures']):
        row = dict(choice, exact_parent_smiles=choice['smiles'], states=[])
        try:
            parent = Chem.MolFromSmiles(choice['smiles'])
            if parent is None: raise ValueError('Invalid saved SMILES; not a zero score.')
            if request['tool']=='synthetic_complexity':
                canonical, score = model.get_score_from_smi(choice['smiles'])
                if not canonical or not math.isfinite(score) or not 1<=score<=5:
                    raise ValueError('Invalid author score.')
                row.update(canonical_author_smiles=canonical, scscore=float(score), status='returned')
            else:
                folder=output.parent/f'parent-{number}';folder.mkdir()
                # Generated names only. No input SMILES can supply a second line or filename.
                if any(c.isspace()for c in choice['smiles']):raise ValueError('SMILES whitespace is not allowed in the author file format.')
                source=folder/'input.smi';source.write_text(choice['smiles']+' parent\n')
                prepare_molecules({'source':str(source),'output_folder':str(folder),
                    'job_manager':'serial','num_processors':1,'min_ph':request['ph_min'],
                    'max_ph':request['ph_max'],'pka_precision':request['precision'],
                    'max_variants_per_compound':request['max_variants'],'thoroughness':1,
                    'random_seed':request['random_seed']})
                for path in sorted(folder.glob('*.sdf')):
                    raw=path.read_bytes()
                    body['author_files'].append({'source_pointer':choice['source_pointer'],
                        'name':str(path.relative_to(output.parent)), 'sha256':hashlib.sha256(raw).hexdigest(),
                        'format':'sdf','content':raw.decode('utf-8')})
                    for index,mol in enumerate(Chem.ForwardSDMolSupplier(io.BytesIO(raw),removeHs=False)):
                        if mol is None:
                            row['states'].append({'status':'unparsed_author_record','record_index':index});continue
                        if mol.GetNumAtoms()==0:continue  # Author parameter record, retained in original SDF.
                        smiles=Chem.MolToSmiles(Chem.RemoveHs(mol),isomericSmiles=True)
                        positions=np.asarray(mol.GetConformer().GetPositions())
                        row['states'].append({'exact_author_smiles':smiles,'rdkit_parse_valid':True,
                            'heavy_atom_element_counts_preserved':elements(parent)==elements(mol),
                            'formal_charge':Chem.GetFormalCharge(mol),'record_index':index,
                            'finite_3d_coordinates':bool(np.isfinite(positions).all()),
                            'author_properties':{k:mol.GetProp(k)for k in mol.GetPropNames()},
                            'sdf_sha256':hashlib.sha256(raw).hexdigest()})
                valid = sum(s.get('rdkit_parse_valid') is True and
                            s.get('heavy_atom_element_counts_preserved') is True and
                            s.get('finite_3d_coordinates') is True for s in row['states'])
                row.update(status='returned' if valid else 'no_usable_states', usable_states=valid,
                           at_variant_budget=len(row['states'])>=request['max_variants'])
        except Exception as error:
            row.update(status='author_failure',error_type=type(error).__name__,error=str(error)[:600])
        body['rows'].append(row);save(output.parent/'progress.json',body)
    passed=sum(r['status']=='returned'for r in body['rows'])
    body['status']='succeeded'if passed==len(body['rows'])else'partial'if passed else'failed'
    save(output,body)


if __name__=='__main__':main()
