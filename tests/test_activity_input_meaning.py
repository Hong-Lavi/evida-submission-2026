"""Reported assay relations and endpoints survive the actual fitting input path."""
import copy
import unittest

from evida.activity_inputs import nanomolar, prepare
from evida.activity_model import training_rows


def binding(rows):
    return {'semantic_type': 'reported_bindingdb_measurements', 'rows': [
        {'row_id': 'bindingdb:'+str(i), 'candidate_id': 'BDBM:'+str(i), 'smiles': smiles,
         'same_returned_representation_as_row': None,
         'raw': {'smile': smiles, 'affinity_type': kind, 'affinity': value,
                 'doi': 'fixture-doi', 'pmid': 'fixture-pmid'}, 'assay_context': None}
        for i, (smiles, kind, value) in enumerate(rows)]}


class ActivityInputMeaningTests(unittest.TestCase):
    def test_bounds_are_preserved_but_never_point_labels(self):
        data = binding([('CCO', 'IC50', '<100'), ('CCN', 'IC50', '>100'), ('CCC', 'IC50', '100')])
        rows = training_rows({'rows': []}, extra_sources=[data])
        self.assertEqual([r['smiles'] for r in rows], ['CCC'])
        reviewed = prepare(data)
        self.assertEqual([r['p_relation'] for r in reviewed['measurements']], ['>', '<', '='])
        self.assertEqual([r['point_value'] for r in reviewed['measurements']], [None, None, 7.0])
        self.assertEqual(reviewed['summary']['retained_bound_records'], 2)
        self.assertEqual(reviewed['measurements'][0]['raw_value'], '<100')

    def test_primary_bindingdb_has_the_same_meaning_as_an_extra_source(self):
        data = binding([('CCO', 'Ki', '10'), ('CCN', 'Ki', '20')])
        self.assertEqual(training_rows(data), training_rows({'rows': []}, extra_sources=[data]))
        self.assertEqual(len(training_rows(data)), 2)

    def test_median_contains_only_exact_records_of_one_endpoint(self):
        data = binding([('CCO', 'IC50', '100'), ('CCO', 'Ki', '1'), ('CCO', 'IC50', '<1'),
                        ('CCN', 'IC50', '1000')])
        rows = training_rows({'rows': []}, extra_sources=[data])
        row = next(r for r in rows if r['smiles'] == 'CCO')
        self.assertEqual(row['p_activity'], 7.0)
        self.assertEqual(row['records'], 1)
        self.assertEqual(row['assay_types'], ['IC50'])

    def test_endpoint_selection_uses_coverage_before_any_model_result(self):
        data = binding([('CCO', 'Ki', '10'), ('CCN', 'Ki', '20'), ('CCC', 'IC50', '1')])
        reviewed = prepare(data)
        self.assertEqual(reviewed['summary']['selected_endpoint'], 'Ki')
        self.assertEqual({r['smiles'] for r in reviewed['rows']}, {'CCO', 'CCN'})
        self.assertEqual(prepare(data, endpoint='IC50')['rows'][0]['smiles'], 'CCC')
        self.assertEqual(len(reviewed['measurements']), 3)

    def test_explicit_contradictory_chembl_relation_is_not_a_point(self):
        data = {'rows': [{'candidate_id': 'C', 'smiles': 'CCO', 'activities': [
            {'standard_type': 'IC50', 'standard_units': 'nM', 'standard_value': '100',
             'standard_relation': '>', 'pchembl_value': '7.0', 'assay_chembl_id': 'ASSAY'}]}]}
        before = copy.deepcopy(data)
        self.assertEqual(training_rows(data), [])
        reviewed = prepare(data)
        self.assertEqual(reviewed['measurements'][0]['assay_id'], 'ASSAY')
        self.assertEqual(reviewed['measurements'][0]['p_relation'], '<')
        self.assertEqual(data, before)

    def test_untyped_values_stay_available_for_endpoint_review(self):
        data = {'rows': [{'candidate_id': 'C', 'smiles': 'CCO', 'activities': [{'pchembl_value': 7}]}]}
        self.assertEqual(training_rows(data), [])
        reviewed = prepare(data)
        self.assertEqual(reviewed['measurements'][0]['point_value'], 7)
        self.assertEqual(reviewed['measurements'][0]['fit_exclusion'], 'unresolved_endpoint')

    def test_numeric_parser_keeps_unicode_bounds_and_approximation_separate(self):
        for text, relation in [('≤100', '>='), ('≥100', '<='), ('~100', '~'), ('≈100', '~')]:
            value = nanomolar(text)
            self.assertEqual(value['p_relation'], relation)
            self.assertIsNone(value['point_value'])
        for bad in ('nan', 'inf', '>>100', '0', '-1', '', None):
            self.assertIsNone(nanomolar(bad)['point_value'])
        self.assertEqual(nanomolar(' = 1e2 ')['point_value'], 7)

    def test_source_preference_never_crosses_measurement_types(self):
        data = {'rows': [{'candidate_id': 'C', 'smiles': 'CCO', 'activities': [
            {'pchembl_value': 4, 'standard_type': 'Ki', 'standard_relation': '='}]}]}
        extra = binding([('CCO', 'IC50', '100'), ('CCN', 'IC50', '10')])
        rows = training_rows(data, extra_sources=[extra])
        self.assertEqual({r['source'] for r in rows}, {'bindingdb'})
        self.assertEqual(next(r for r in rows if r['smiles'] == 'CCO')['p_activity'], 7)


if __name__ == '__main__':
    unittest.main()
