"""Discrimination readiness on actual native hypothesis review fixtures."""
import unittest
from evida.hypothesis_review import _observation
from evida.demo_discrimination import assess_demo_discrimination
from tests import test_hypothesis_review as fixtures

def synthetic_state(change=None):
    loop = fixtures.loop_fixture()
    loop['next_checks'][0]['operation'] = {'kind': 'external_observation'}
    authored = fixtures.review_fixture('synthetic-source')
    if change:
        change(loop, authored)
    obs = _observation(loop['next_checks'][0], authored['observations'][0], loop, {})
    return {'decision_id': 'synthetic-decision', 'decision': {'research_loop': loop},
            'hypothesis_review': {'status': 'available', 'published_decision_id': 'synthetic-decision',
                                  'is_current_input': True, 'observation_checks': [obs]}}


class DiscriminationAdapterTests(unittest.TestCase):
    def test_native_exclusive_split_counts_two_outcomes_and_passes(self):
        result = assess_demo_discrimination(synthetic_state())
        self.assertEqual(result['experiments_denominator'], 1)
        self.assertEqual(result['experiments_prospectively_ready'], 1)
        self.assertEqual(result['checks'][0]['declared_contrast_pair_outcomes'], 2)
        self.assertEqual(result['checks'][0]['outcomes_denominator'], 3)
        self.assertFalse(result['scientific_validation'])

    def test_identical_predictions_fail_observable_contrast(self):
        def change(loop, review):
            review['observations'][0]['predictions'][1]['outcome_indices'] = [0]
        result = assess_demo_discrimination(synthetic_state(change))
        self.assertEqual(result['experiments_with_structural_difference'], 0)
        self.assertFalse(result['all_experiments_have_structural_difference'])

    def test_coexistence_keeps_raw_contrast_but_requires_joint_prediction(self):
        def change(loop, review):
            loop['hypotheses'][0]['conditional_alternatives'][0]['relations'][0]['relation'] = 'can_coexist'
        result = assess_demo_discrimination(synthetic_state(change))
        row = result['checks'][0]
        self.assertTrue(row['structural_difference_pass'])
        self.assertEqual(row['joint_prediction_required_pair_outcomes'], 2)
        self.assertFalse(row['conditional_discrimination_ready'])
        self.assertFalse(row['prospective_selection_ready'])

    def test_unknown_precision_is_a_hold_not_a_negative_result(self):
        def change(loop, review):
            review['observations'][0]['precision_requirement'] = 'unknown'
        row = assess_demo_discrimination(synthetic_state(change))['checks'][0]
        self.assertTrue(row['structural_difference_pass'])
        self.assertEqual(row['guarded_outcomes'], 3)
        self.assertFalse(row['conditional_discrimination_ready'])

    def test_reconstructed_contrast_never_counts_as_prospective(self):
        def change(loop, review):
            for pred in review['observations'][0]['predictions']:
                pred['origin'] = 'reconstructed_after_result'
        row = assess_demo_discrimination(synthetic_state(change))['checks'][0]
        self.assertTrue(row['conditional_discrimination_ready'])
        self.assertFalse(row['prospective_selection_ready'])
        self.assertEqual(row['prediction_origins']['reconstructed_after_result'], 2)

    def test_missing_or_wrong_bound_review_cannot_pass(self):
        state = synthetic_state()
        state['hypothesis_review']['published_decision_id'] = 'other-decision'
        result = assess_demo_discrimination(state)
        self.assertFalse(result['all_experiments_have_structural_difference'])
        self.assertEqual(result['experiments_denominator'], 1)

    def test_stale_or_unspecified_currentness_retains_counts_without_current_badge(self):
        for flag in (False, None):
            with self.subTest(is_current_input=flag):
                state = synthetic_state()
                state['hypothesis_review']['is_current_input'] = flag
                result = assess_demo_discrimination(state)
                self.assertTrue(result['bound_review_available'])
                self.assertEqual(result['historical_experiments_with_structural_difference'], 1)
                self.assertEqual(result['checks'][0]['declared_contrast_pair_outcomes'], 2)
                self.assertFalse(result['current_input_accepted'])
                self.assertEqual(result['experiments_with_structural_difference'], 0)
                self.assertEqual(result['experiments_conditionally_ready'], 0)
                self.assertEqual(result['experiments_prospectively_ready'], 0)
                self.assertFalse(result['all_experiments_have_structural_difference'])
                self.assertFalse(result['all_experiments_conditionally_ready'])


    def test_partial_patterns_differ_without_complete_separability(self):
        def change(loop, review):
            for p in review['observations'][0]['predictions']:
                p['coverage'] = 'partial'
        row = assess_demo_discrimination(synthetic_state(change))['checks'][0]
        self.assertEqual(row['declared_pattern_different_pairs'], 1)
        self.assertTrue(row['structural_difference_pass'])
        self.assertEqual(row['complete_separating_pair_outcomes'], 0)
        self.assertFalse(row['complete_separability_pass'])
        self.assertFalse(row['conditional_discrimination_ready'])

    def test_partial_same_patterns_do_not_differ(self):
        def change(loop, review):
            for p in review['observations'][0]['predictions']:
                p.update(coverage='partial', outcome_indices=[0])
        row = assess_demo_discrimination(synthetic_state(change))['checks'][0]
        self.assertEqual(row['pairs_with_nonempty_known_patterns_denominator'], 1)
        self.assertEqual(row['declared_pattern_different_pairs'], 0)
        self.assertFalse(row['structural_difference_pass'])

    def test_unknown_sets_do_not_create_pattern_difference(self):
        def change(loop, review):
            review['observations'][0]['predictions'][0]['coverage'] = 'unknown'
        row = assess_demo_discrimination(synthetic_state(change))['checks'][0]
        self.assertEqual(row['nonempty_known_prediction_patterns'], 1)
        self.assertEqual(row['declared_pattern_different_pairs'], 0)
        self.assertFalse(row['structural_difference_pass'])

if __name__ == "__main__":
    unittest.main()
