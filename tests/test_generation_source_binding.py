"""A displayed origin must be the exact input identity, even when IDs collide."""
from copy import deepcopy
import unittest

from evida.generation_source_binding import attach_source_binding


class SourceBindingTests(unittest.TestCase):
    def test_origin_binding_preserves_predictions_and_does_not_bind_a_different_stereoisomer(self):
        source = {'rows': [{'candidate_id': 'same-id', 'smiles': 'F/C=C/F'}]}
        result = {'rows': [{'candidate_id': 'new', 'smiles': 'CCO', 'predicted_p_activity': 7.2,
                           'paths': [{'parent_id': 'same-id', 'parent_smiles': 'F/C=C\\F',
                                      'parent_branch': 'source'}]}]}
        before = deepcopy(result)
        attach_source_binding(result, source, 'source', 'source-sha')
        self.assertNotIn('source_ref', result['rows'][0]['paths'][0])
        self.assertEqual(result['rows'][0]['predicted_p_activity'], before['rows'][0]['predicted_p_activity'])
        self.assertEqual(result['rows'][0]['smiles'], before['rows'][0]['smiles'])

    def test_a_measured_source_and_a_generated_intermediate_with_the_same_id_stay_distinct(self):
        source = {'rows': [{'candidate_id': 'parent', 'smiles': 'CCO'}]}
        result = {'rows': [{'candidate_id': 'main', 'paths': [
            {'parent_id': 'parent', 'parent_smiles': 'OCC', 'parent_branch': 'source'}]}],
            'guided_search': {'rows': [{'candidate_id': 'guided', 'round': 2, 'paths': [
                {'parent_id': 'parent', 'parent_smiles': 'CCO', 'parent_branch': 'guided_search', 'parent_round': 1}]}]}}
        attach_source_binding(result, source, 'source', 'sha')
        self.assertEqual(result['rows'][0]['paths'][0]['source_ref']['row_index'], 0)
        generated = result['guided_search']['rows'][0]
        self.assertNotIn('source_ref', generated['paths'][0])
        self.assertEqual(generated['generation_locator']['branch'], 'guided_search/rows')


if __name__ == '__main__':
    unittest.main()
