"""Only 30-task synthetic fixtures; no official data or real predictions read."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from prescore_gate import guarded_score, sha, validate


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=True))


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'chemeleon-trial'
        self.gp = self.root.parent / 'tanimoto-trial'
        self.root.mkdir()
        self.gp.mkdir()
        write(self.gp / 'protocol.json', {'synthetic': True})
        write(self.root / 'score_comparison.py', {'synthetic': 'source pin only'})
        write(self.root / 'review/prescore_gate.py', {'synthetic': 'source pin only'})
        self.order = [f'SYNTH{i:02d}_Ki' for i in range(30)]
        self.p = {'order': self.order, 'tasks': [], 'source_pins': {
            'score_comparison.py': sha(self.root / 'score_comparison.py')},
            'native_source_pins': {}, 'gp_protocol_sha256': sha(self.gp / 'protocol.json'),
            'gp_prediction_pins': {}, 'gp_run': str(self.gp / 'run-01'),
            'data': str(self.root / 'synthetic-data'), 'weights_sha256': 'synthetic-weight-hash'}
        self.receipts = []
        for name in self.order:
            data = Path(self.p['data']) / name
            write(data / 'train.json', {'synthetic': True})
            write(data / 'test-features.json', [{'candidate_id': 'a', 'smiles': 'C'}, {'candidate_id': 'b', 'smiles': 'CC'}])
            self.p['tasks'].append({'task': name, 'official_test': 2,
                'train_sha256': sha(data / 'train.json'), 'features_sha256': sha(data / 'test-features.json')})
            prior = {'task': name, 'status': 'completed', 'test_gold_read': False, 'test_rows': 2,
                     'native_rf': {'usable': True, 'inner_mae': .5},
                     'author_gp': {'usable': True, 'inner_mae': .6}, 'selected_policy_arm': 'rf',
                     'inner_mean_mae': 1., 'training_rows': 3, 'inner_held_out_rows': 2,
                     'train_matrix_sha256': 'matrix', 'train_labels_sha256': 'labels',
                     'rows': [{'candidate_id': cid, 'rf_prediction': 1., 'gp_prediction': 1.,
                               'gp_latent_std': .1, 'gp_observation_std': .2} for cid in ('a', 'b')]}
            path = Path(self.p['gp_run']) / name / 'predictions.json'; write(path, prior)
            self.p['gp_prediction_pins'][name] = sha(path)
            out = self.root / 'run-01' / name
            write(out / 'embeddings.npz', {'synthetic': True})
            write(out / 'baseline-reproduced.json', {'same_native_training_matrix': True,
                'same_native_labels': True, 'same_test_predictions_atol': 1e-10})
            pred = copy.deepcopy(prior)
            pred.update(chemeleon_rf={'usable': True, 'inner_mae': .4, 'inner_spearman': .5},
                        selected_policy_arm='chemeleon_rf', prior_policy_arm='rf',
                        weights_sha256=self.p['weights_sha256'], embeddings_sha256=sha(out / 'embeddings.npz'))
            for row in pred['rows']:
                row['chemeleon_rf_prediction'] = 1.
            write(out / 'predictions.json', pred)
            receipt = {'task': name, 'status': 'completed', 'returncode': 0,
                       'prediction_sha256': sha(out / 'predictions.json'), 'seconds': .1}
            self.receipts.append(receipt); write(out / 'receipt.json', receipt)
        write(self.root / 'protocol.json', self.p)
        ph = sha(self.root / 'protocol.json')
        write(self.root / 'protocol-receipt.json', {'sha256': ph})
        self.seal = {'protocol_sha256': ph, 'test_gold_read_by_fitting': False, 'tasks': self.receipts}
        self.save_seal()
        write(self.root / 'run-01/started.json', {'protocol_sha256': ph, 'tasks': self.order})
        write(self.root / 'review/scoring-amendment.json', {'gate_sha256': sha(self.root / 'review/prescore_gate.py'),
            'original_protocol_sha256': ph, 'original_scorer_sha256': self.p['source_pins']['score_comparison.py']})
        write(self.root / 'review/scoring-amendment-receipt.json', {'sha256': sha(self.root / 'review/scoring-amendment.json')})
        self.label_open = Mock(name='synthetic_label_open')

    def tearDown(self):
        self.tmp.cleanup()

    def save_seal(self):
        write(self.root / 'run-01/sealed-predictions.json', self.seal)

    def denied(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            guarded_score(self.root, self.label_open)
        self.label_open.assert_not_called()
        self.assertFalse((self.root / 'review/prescore-gate-receipt.json').exists())

    def modify_last_prediction(self, change):
        out = self.root / 'run-01' / self.order[-1]
        value = json.loads((out / 'predictions.json').read_text()); change(value)
        write(out / 'predictions.json', value)
        self.receipts[-1]['prediction_sha256'] = sha(out / 'predictions.json')
        write(out / 'receipt.json', self.receipts[-1]); self.save_seal()

    def test_all_thirty_gate_before_label_callback(self):
        result = guarded_score(self.root, self.label_open)
        self.assertEqual(result['completed_tasks'], 30)
        self.label_open.assert_called_once_with()

    def test_corrupt_last_prior_prediction_prevents_first_label(self):
        write(Path(self.p['gp_run']) / self.order[-1] / 'predictions.json', {'corrupted': True})
        self.denied()

    def test_missing_last_receipt_prevents_first_label(self):
        (self.root / 'run-01' / self.order[-1] / 'receipt.json').unlink()
        self.denied()

    def test_completed_without_hash_prevents_first_label(self):
        self.receipts[-1]['prediction_sha256'] = None
        write(self.root / 'run-01' / self.order[-1] / 'receipt.json', self.receipts[-1]); self.save_seal()
        self.denied()

    def test_terminal_receipt_disagreement_prevents_first_label(self):
        receipt = dict(self.receipts[-1], seconds=999)
        write(self.root / 'run-01' / self.order[-1] / 'receipt.json', receipt)
        self.denied()

    def test_late_nonfinite_value_after_hash_gate_prevents_first_label(self):
        self.modify_last_prediction(lambda p: p['rows'][-1].update(chemeleon_rf_prediction=float('nan')))
        self.denied()

    def test_late_duplicate_ids_after_hash_gate_prevents_first_label(self):
        self.modify_last_prediction(lambda p: p['rows'][-1].update(candidate_id='a'))
        self.denied()

    def test_late_wrong_member_after_hash_gate_prevents_first_label(self):
        self.modify_last_prediction(lambda p: p['rows'][-1].update(candidate_id='foreign'))
        self.denied()

    def test_late_policy_mismatch_prevents_first_label(self):
        self.modify_last_prediction(lambda p: p.update(selected_policy_arm='rf'))
        self.denied()

    def test_failed_task_preserves_partial_and_uses_frozen_fallback(self):
        self.receipts[-1].update(status='failed', returncode=1)
        write(self.root / 'run-01' / self.order[-1] / 'receipt.json', self.receipts[-1]); self.save_seal()
        result = validate(self.root)
        self.assertEqual(result['completed_tasks'], 29)
        self.assertIn(str(self.root / 'run-01' / self.order[-1] / 'predictions.json'), result['verified_file_sha256'])

    def test_changed_original_source_prevents_first_label(self):
        write(self.root / 'score_comparison.py', {'changed': True})
        self.denied()


if __name__ == '__main__':
    unittest.main()
