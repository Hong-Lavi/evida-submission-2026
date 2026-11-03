"""Independently reconstruct every native split; never open official test labels."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.Scaffolds import MurckoScaffold

HERE = Path(__file__).resolve().parent
TRIAL = HERE.parent
BASE = TRIAL.parent
sys.path.insert(0, str(BASE / 'tanimoto-trial/frozen-product'))
from evida.activity_model import training_rows, _scaffold


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guard(event, args):
    if event == 'open' and isinstance(args[0], str) and ('evaluation-only' in args[0] or 'test-gold' in args[0]):
        raise PermissionError('Input audit cannot read official test labels')


sys.addaudithook(guard)
protocol = json.loads((HERE / 'original-freeze/protocol.json').read_text())
old_protocol = json.loads((BASE / 'tanimoto-trial/protocol.json').read_text())
old_tasks = {row['task']: row for row in old_protocol['tasks']}
fingerprint = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)
results = []
for task in protocol['tasks']:
    name = task['task']
    prepared = TRIAL / 'inputs' / (name + '.json')
    assert sha(prepared) == task['input_sha256']
    data = json.loads(prepared.read_text())
    original = Path(protocol['official_data']) / name
    assert sha(original / 'train.json') == old_tasks[name]['train_sha256']
    assert sha(original / 'test-features.json') == old_tasks[name]['features_sha256']
    rows = training_rows(json.loads((original / 'train.json').read_text()), endpoint=task['endpoint'])
    groups = {}
    for row in rows:
        scaffold = _scaffold(row['smiles'], Chem, MurckoScaffold)
        assert scaffold is not None
        groups.setdefault(scaffold, []).append(row)
    expected_train, expected_validation = [], []
    for _, members in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        (expected_train if len(expected_train) < len(rows) * .75 else expected_validation).extend(members)
    keep = lambda row: {key: row[key] for key in ('candidate_id', 'smiles', 'p_activity')}
    expected_train, expected_validation = list(map(keep, expected_train)), list(map(keep, expected_validation))
    original_features = json.loads((original / 'test-features.json').read_text())
    matrix = np.asarray([list(fingerprint.GetFingerprint(Chem.MolFromSmiles(row['smiles'])))
                         for row in data['train']], dtype=float)
    labels = np.asarray([row['p_activity'] for row in data['train']])
    train_ids, val_ids, test_ids = [{row['candidate_id'] for row in data[key]}
                                  for key in ('train', 'validation', 'prediction_rows')]
    train_scaffolds, val_scaffolds = [{_scaffold(row['smiles'], Chem, MurckoScaffold) for row in data[key]}
                                    for key in ('train', 'validation')]
    canonical = lambda row: Chem.MolToSmiles(Chem.MolFromSmiles(row['smiles']))
    fitted_structures = {canonical(row) for row in data['train'] + data['validation']}
    test_structures = {canonical(row) for row in data['prediction_rows']}
    checks = {'exact_native_training_rows_and_order': data['train'] == expected_train,
              'exact_native_validation_rows_and_order': data['validation'] == expected_validation,
              'exact_original_prediction_features': data['prediction_rows'] == original_features,
              'prediction_rows_have_no_labels': all(set(row) == {'candidate_id', 'smiles'} for row in data['prediction_rows']),
              'training_matrix_hash_matches_GP': hashlib.sha256(matrix.tobytes()).hexdigest() == data['native_train_matrix_sha256'],
              'training_label_hash_matches_GP': hashlib.sha256(labels.tobytes()).hexdigest() == data['native_train_labels_sha256'],
              'all_split_ids_unique': all(len({r['candidate_id'] for r in data[key]}) == len(data[key]) for key in ('train', 'validation', 'prediction_rows')),
              'partition_ids_disjoint': not bool(train_ids & val_ids or train_ids & test_ids or val_ids & test_ids),
              'training_validation_scaffolds_disjoint': not bool(train_scaffolds & val_scaffolds),
              'outer_structures_disjoint_from_train_validation': not bool(fitted_structures & test_structures),
              'declared_counts_match': all(len(data[key]) == task[count] for key, count in
                                          [('train', 'training_rows'), ('validation', 'validation_rows'), ('prediction_rows', 'prediction_rows')])}
    results.append({'task': name, 'checks': checks,
                    'training_rows': len(data['train']), 'validation_rows': len(data['validation']),
                    'prediction_rows': len(data['prediction_rows']),
                    'singleton_tail_at_batch64': [key for key in ('train', 'validation', 'prediction_rows') if len(data[key]) % 64 == 1]})
receipt = {'status': 'PASS' if all(all(r['checks'].values()) for r in results) else 'FAIL',
           'tasks': results, 'task_count': len(results),
           'total_prediction_rows': sum(row['prediction_rows'] for row in results),
           'source_protocol_sha256': sha(HERE / 'original-freeze/protocol.json'),
           'official_test_labels_read': False, 'model_fits': 0, 'gpu_used': False, 'network_calls': 0}
(HERE / 'input-partition-review.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({key: receipt[key] for key in ('status', 'task_count', 'total_prediction_rows', 'official_test_labels_read')}))
assert receipt['status'] == 'PASS'
