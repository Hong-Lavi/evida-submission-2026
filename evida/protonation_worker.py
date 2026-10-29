"""Fixed isolated author API worker; no paths or commands accepted in scientific inputs."""
from collections import Counter
import importlib.metadata
import json
from pathlib import Path
import sys
import time


def save(path, value):
    temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(value, allow_nan=False)); temp.replace(path)


def main():
    request_path, output = map(Path, sys.argv[1:])
    wrapper = json.loads(request_path.read_text()); request = wrapper['input']
    versions = {name: importlib.metadata.version(name) for name in wrapper['expected_versions']}
    if versions != wrapper['expected_versions']: raise ValueError('Author runtime versions changed')
    from dimorphite_dl import protonate_smiles
    from rdkit import Chem
    body = {'semantic_type': 'author_protonation_enumeration_not_efficacy_prediction',
            'source_artifact_id': request['source_artifact_id'],
            'source_artifact_sha256': request['source_artifact_sha256'], 'versions': versions,
            'parameters': {k: request[k] for k in ('ph_min', 'ph_max', 'precision', 'max_variants')},
            'rows': [], 'status': 'running', 'total_rows': len(request['structures'])}
    progress = output.parent / 'progress.json'; save(progress, body)
    for row in request['structures']:
        entry = {**row, 'exact_parent_smiles': row['smiles'], 'states': []}
        try:
            parent = Chem.MolFromSmiles(row['smiles'])
            elements = lambda molecule: dict(Counter(a.GetAtomicNum() for a in molecule.GetAtoms() if a.GetAtomicNum() > 1))
            parent_elements = elements(parent) if parent is not None else None
            values = protonate_smiles(row['smiles'], **body['parameters'])
            for value in values:
                mol = Chem.MolFromSmiles(value)
                entry['states'].append({'exact_author_smiles': value, 'rdkit_parse_valid': mol is not None,
                                       'formal_charge': Chem.GetFormalCharge(mol) if mol else None,
                                       'heavy_atom_element_counts_preserved': elements(mol) == parent_elements if mol else False})
            entry.update(status=('returned' if all(s['rdkit_parse_valid'] and s['heavy_atom_element_counts_preserved'] for s in entry['states']) else 'invalid_author_states') if values else 'no_states',
                         at_variant_budget=len(values) >= request['max_variants'])
        except Exception as error:
            entry.update(status='author_failure', error_type=type(error).__name__, error=str(error)[:1000])
        body['rows'].append(entry); body['completed_rows'] = len(body['rows']); save(progress, body)
    good = sum(row['status'] == 'returned' for row in body['rows'])
    body['status'] = 'succeeded' if good == len(body['rows']) else 'partial' if good else 'failed'
    body['limits'] = ['Bounded enumeration, not measured pKa, populations, affinity, BBB or efficacy.',
                      'All returned states and row failures retained; variant budget may limit coverage.']
    save(output, body)


if __name__ == '__main__': main()
