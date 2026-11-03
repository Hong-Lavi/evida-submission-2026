"""Freeze the exact native scaffold split without opening official test labels."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.Scaffolds import MurckoScaffold

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE / 'repo/product'))
from evida.activity_model import training_rows, _scaffold


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    protocol = json.loads((BASE / 'tanimoto-trial/protocol.json').read_text())
    source = Path(protocol['data'])
    destination = HERE / 'inputs'
    destination.mkdir(exist_ok=False)
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)
    tasks = []
    for task in protocol['tasks']:
        name = task['task']
        original = source / name
        assert sha(original / 'train.json') == task['train_sha256']
        assert sha(original / 'test-features.json') == task['features_sha256']
        rows = training_rows(json.loads((original / 'train.json').read_text()), endpoint=task['endpoint'])
        groups = {}
        for row in rows:
            key = _scaffold(row['smiles'], Chem, MurckoScaffold)
            if key is None:
                raise ValueError('Unexpected invalid prepared structure: ' + name)
            groups.setdefault(key, []).append(row)
        train, validation = [], []
        for _, members in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
            (train if len(train) < len(rows) * .75 else validation).extend(members)
        features = json.loads((original / 'test-features.json').read_text())
        if isinstance(features, dict):
            features = features['rows']
        previous = BASE / 'tanimoto-trial/run-01' / name / 'predictions.json'
        reference = json.loads(previous.read_text())
        matrix = np.asarray([list(generator.GetFingerprint(Chem.MolFromSmiles(row['smiles'])))
                             for row in train], dtype=float)
        labels = np.asarray([row['p_activity'] for row in train])
        assert hashlib.sha256(matrix.tobytes()).hexdigest() == reference['train_matrix_sha256']
        assert hashlib.sha256(labels.tobytes()).hexdigest() == reference['train_labels_sha256']
        assert len(validation) == reference['inner_held_out_rows']
        keep = lambda row: {key: row[key] for key in ('candidate_id', 'smiles', 'p_activity')}
        payload = {'task': name, 'endpoint': task['endpoint'], 'train': list(map(keep, train)),
                   'validation': list(map(keep, validation)),
                   'prediction_rows': [{key: row[key] for key in ('candidate_id', 'smiles')} for row in features],
                   'original_train_sha256': task['train_sha256'],
                   'original_prediction_features_sha256': task['features_sha256'],
                   'native_train_matrix_sha256': reference['train_matrix_sha256'],
                   'native_train_labels_sha256': reference['train_labels_sha256']}
        output = destination / (name + '.json')
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        tasks.append({'task': name, 'endpoint': task['endpoint'], 'input_sha256': sha(output),
                      'reference_predictions_sha256': sha(previous), 'training_rows': len(train),
                      'validation_rows': len(validation), 'prediction_rows': len(features),
                      'official_gold_sha256': task['gold_sha256']})
    (HERE / 'input-manifest.json').write_text(json.dumps({'tasks': tasks, 'official_test_labels_read': False,
        'scope': 'Same source/preparation/split as the recorded native RF/GP trial'}, indent=2) + '\n')
    print(json.dumps({'prepared_tasks': len(tasks), 'prediction_rows': sum(t['prediction_rows'] for t in tasks),
                      'all_native_train_matrix_and_label_hashes_match': True, 'official_test_labels_read': False}))


if __name__ == '__main__':
    main()
