"""Selection failures must preserve independently usable predictions and their evidence."""
import unittest
from unittest.mock import patch

import numpy as np

from evida.activity_selection import choose


class ConditionalModelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.reference_model = object()
        self.fingerprint = object()
        self.base = {'usable': True, 'model': self.reference_model, 'fingerprint': self.fingerprint,
                     'meaning': 'reference', 'summary': {'held_out_spearman': 0.7,
                     'held_out_mean_absolute_error': 0.3, 'beats_predicting_the_mean': True}}
        self.config = {'enabled': True, 'maximum_training_compounds': 3000,
                       'maximum_iterations': 100, 'fit_timeout_seconds': 180, 'packages': {}}
        self.y = np.array([1., 2., 3., 4.])

    def select(self, predicted, *, converged=True, reference_usable=True, error=None):
        fitted = {**self.base, 'summary': dict(self.base['summary']), 'usable': reference_usable}
        if not reference_usable:
            fitted.update(model=None, fingerprint=None)
        with patch('evida.activity_selection._config', return_value=self.config), \
             patch('evida.activity_gp.fit_gp', return_value=(object(), {'optimization': {'converged': converged}}), side_effect=error) as fit, \
             patch('evida.activity_gp.predict_gp', return_value=(np.array(predicted), None, None)):
            result = choose(fitted, np.eye(4), self.y.copy(), np.eye(4), self.y.copy(),
                            self.fingerprint, .3, 1., 20260930)
        return result, fit

    def test_a_lower_error_fit_must_converge_before_replacing_the_reference(self):
        result, _ = self.select(self.y, converged=False)
        self.assertIs(result['model'], self.reference_model)
        self.assertEqual(result['model_selection']['selected'], 'random_forest')
        self.assertFalse(result['model_selection']['candidates'][1]['usable'])

    def test_gp_can_rescue_an_unusable_reference_without_refitting_on_validation_labels(self):
        result, fit = self.select(self.y, reference_usable=False)
        self.assertTrue(result['usable'])
        self.assertEqual(result['model_selection']['selected'], 'tanimoto_gp')
        self.assertIs(result['fingerprint'], self.fingerprint)
        self.assertEqual(fit.call_count, 1)
        self.assertEqual(len(fit.call_args.args), 2)
        self.assertEqual(result['summary']['validation_role'], 'model_selection')

    def test_a_computation_failure_keeps_the_reference_and_the_failed_candidate(self):
        result, _ = self.select(self.y, error=RuntimeError('fixed numerical failure'))
        self.assertIs(result['model'], self.reference_model)
        record = result['model_selection']['candidates'][1]
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['error'], 'fixed numerical failure')

    def test_nonfinite_gp_predictions_cannot_displace_finite_reference_predictions(self):
        result, _ = self.select([1., 2., float('nan'), 4.])
        self.assertIs(result['model'], self.reference_model)
        self.assertEqual(result['model_selection']['candidates'][1]['status'], 'failed')

    def test_gp_runtime_io_failure_preserves_a_usable_reference(self):
        result, _ = self.select(self.y, error=OSError('fixed GP library load failure'))
        self.assertIs(result['model'], self.reference_model)
        self.assertTrue(result['usable'])
        self.assertEqual(result['model_selection']['candidates'][1]['error_type'], 'OSError')

    def test_two_unusable_candidates_leave_no_scorer(self):
        result, _ = self.select(list(reversed(self.y)), reference_usable=False)
        self.assertFalse(result['usable'])
        self.assertIsNone(result['model'])
        self.assertIsNone(result['model_selection']['selected'])
        self.assertEqual(len(result['model_selection']['candidates']), 2)

    def test_resource_limit_is_recorded_before_any_gp_fit(self):
        self.config['maximum_training_compounds'] = 3
        result, fit = self.select(self.y)
        fit.assert_not_called()
        self.assertIs(result['model'], self.reference_model)
        self.assertEqual(result['model_selection']['candidates'][1]['status'], 'resource_bound')


if __name__ == '__main__':
    unittest.main()
