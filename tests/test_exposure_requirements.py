from copy import deepcopy
import math
import unittest

import jsonschema

from evida.contracts import EXPOSURE_REQUIREMENTS, model_functions
from evida.exposure_requirements import compare


class ExposureRequirementTests(unittest.TestCase):
    def setUp(self):
        self.sources = {'a': {'rows': [{'text': 'CONTROLLED FIXTURE: threshold 2 uM; Cmax 5 ug/mL; alternate 5000 ng/mL; AUC 24 ug*h/mL over 24 hours; molecular weight 500 g/mol.'}]}}
        binding = {'artifact_id': 'a', 'path': ['rows', 0, 'text'], 'quote': self.sources['a']['rows'][0]['text']}
        self.args = {
            'source_artifact_ids': ['a'], 'context': 'CONTROLLED FIXTURE; no reported biological result.',
            'assay_benchmark': {'value': 2, 'unit': 'uM', 'metric': 'nominal test threshold', 'context': 'fixture cell assay', 'source': binding},
            'exposures': [{'id': 'peak', 'label': 'fixture peak', 'value': 5, 'unit': 'ug/mL', 'statistic': 'Cmax', 'interval_hours': None, 'context': 'fixture total plasma', 'source': binding}],
            'mass_bases': [{'id': 'form', 'label': 'fixture chemical form', 'molecular_weight_g_mol': 500, 'status': 'sensitivity_only', 'source': binding}],
        }

    def test_mass_units_and_auc_mean_are_distinct(self):
        first = self.args['exposures'][0]
        self.args['exposures'] += [{**first, 'id': 'ng', 'value': 5000, 'unit': 'ng/mL'},
                                   {**first, 'id': 'auc', 'value': 24, 'unit': 'ug*h/mL', 'statistic': 'AUC', 'interval_hours': 24}]
        original = deepcopy((self.args, self.sources))
        rows = compare(self.args, self.sources)['rows']
        self.assertEqual([r['comparison_concentration_uM'] for r in rows], [10, 10, 2])
        self.assertEqual([r['required_effective_translation_factor'] for r in rows], [.2, .2, 1])
        self.assertEqual(rows[-1]['comparison_statistic'], 'AUC_divided_by_interval_mean')
        self.assertTrue(all(r['actual_translation_factor'] is None and r['efficacy_prediction'] is None for r in rows))
        self.assertEqual(original, (self.args, self.sources))

    def test_missing_mass_basis_keeps_gap_and_does_not_choose_parent(self):
        self.args['mass_bases'] = []
        result = compare(self.args, self.sources)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['unresolved_inputs'][0]['exposure_id'], 'peak')

    def test_unmatched_number_quote_or_locator_is_not_accepted(self):
        for replacement in [
            {'value': 6},
            {'source': {'artifact_id': 'a', 'path': ['rows', 0, 'text'], 'quote': 'not present 5'}},
            {'source': {'artifact_id': 'a', 'path': ['rows', -1, 'text'], 'quote': 'Cmax 5'}},
            {'source': {'artifact_id': 'a', 'path': ['rows', 8, 'text'], 'quote': 'Cmax 5'}},
        ]:
            with self.subTest(replacement=replacement):
                args = deepcopy(self.args); args['exposures'][0].update(replacement)
                with self.assertRaises(ValueError): compare(args, self.sources)

    def test_auc_cannot_be_used_as_a_peak_or_without_interval(self):
        for replacement in [{'unit': 'ug*h/mL'}, {'statistic': 'AUC'},
                            {'unit': 'ug*h/mL', 'statistic': 'AUC', 'interval_hours': None},
                            {'interval_hours': 24}]:
            args = deepcopy(self.args); args['exposures'][0].update(replacement)
            with self.assertRaises(ValueError): compare(args, self.sources)

    def test_missing_zero_and_nonfinite_values_do_not_become_exposure(self):
        for value in [0, -1, None, math.nan, math.inf, True]:
            args = deepcopy(self.args); args['exposures'][0]['value'] = value
            with self.assertRaises(ValueError): compare(args, self.sources)

    def test_function_contract_and_research_notes_remain_separate(self):
        jsonschema.validate(self.args, EXPOSURE_REQUIREMENTS)
        wire = next(f for f in model_functions() if f['name'] == 'compare_exposure_requirements')
        jsonschema.validate({**self.args, 'research_notes': {'findings': [], 'open_questions': [], 'next_goal': 'Check the actual transfer condition.'}}, wire['parameters'])
        self.assertNotIn('research_notes', EXPOSURE_REQUIREMENTS['properties'])

    def relative_input(self):
        text = 'CONTROLLED FIXTURE: geometric trough was approximately 10% to 15% of geometric peak.'
        self.sources['relative'] = {'text': text}
        self.args['source_artifact_ids'].append('relative')
        self.args['exposures'].append({'id': 'trough', 'label': 'derived fixture trough',
            'statistic': 'Ctrough', 'context': 'Same fixture population; no clinical observation.',
            'derivation': {'kind': 'percent_of_reported_concentration', 'base_exposure_id': 'peak',
                'percent_min': 10, 'percent_max': 15,
                'source': {'artifact_id': 'relative', 'path': ['text'], 'quote': text}}})
        return self.args['exposures'][-1]

    def test_relative_range_is_derived_with_reciprocal_order_and_both_sources(self):
        self.relative_input()
        jsonschema.validate(self.args, EXPOSURE_REQUIREMENTS)
        original = deepcopy((self.args, self.sources))
        result = compare(self.args, self.sources)
        row = result['rows'][-1]
        self.assertEqual(row['derived_value_range'], [.5, .75])
        self.assertEqual(row['comparison_concentration_uM_range'], [1, 1.5])
        self.assertEqual(row['required_effective_translation_factor_range'], [2/1.5, 2])
        self.assertIsNone(row['reported_value'])
        self.assertIsNone(row['comparison_concentration_uM'])
        self.assertIsNone(row['required_effective_translation_factor'])
        self.assertFalse(row['automatic_candidate_rejection'])
        self.assertFalse(result['criterion_is_required_for_efficacy'])
        self.assertEqual({b['artifact_id'] for b in row['source_bindings']}, {'a', 'relative'})
        self.assertEqual(original, (self.args, self.sources))

    def test_relative_unreported_percent_or_reversed_range_rejected(self):
        row = self.relative_input()
        for change in [{'percent_min': 8}, {'percent_min': 15, 'percent_max': 10},
                       {'percent_max': 0}, {'percent_min': True}]:
            args = deepcopy(self.args)
            args['exposures'][-1]['derivation'].update(change)
            with self.assertRaises(ValueError): compare(args, self.sources)

    def test_relative_cannot_reference_missing_derived_or_auc_base(self):
        self.relative_input()
        for base_id in ['missing', 'trough']:
            args = deepcopy(self.args)
            args['exposures'][-1]['derivation']['base_exposure_id'] = base_id
            with self.assertRaises(ValueError): compare(args, self.sources)
        self.args['exposures'][0].update(value=24, unit='ug*h/mL', statistic='AUC', interval_hours=24)
        with self.assertRaises(ValueError): compare(self.args, self.sources)

    def test_relative_unknown_fraction_is_not_completed_by_a_default(self):
        row = self.relative_input()
        row['derivation']['percent_max'] = None
        with self.assertRaises(jsonschema.ValidationError): jsonschema.validate(self.args, EXPOSURE_REQUIREMENTS)
        with self.assertRaises(ValueError): compare(self.args, self.sources)

    def test_relative_and_direct_fields_cannot_be_blended(self):
        row = self.relative_input()
        row['value'] = .5
        with self.assertRaises(jsonschema.ValidationError): jsonschema.validate(self.args, EXPOSURE_REQUIREMENTS)
        with self.assertRaises(ValueError): compare(self.args, self.sources)

    def test_distinct_locator_errors_are_reported_without_fixing_paths(self):
        from evida.exposure_requirements import SourceBindingError
        args=deepcopy(self.args)
        args['assay_benchmark']['source']={**args['assay_benchmark']['source'],'path':['result','rows',0,'text']}
        args['mass_bases'][0]['source']={**args['mass_bases'][0]['source'],'path':['content','rows',0,'text']}
        original=deepcopy(args)
        with self.assertRaises(SourceBindingError) as caught:compare(args,self.sources)
        errors=caught.exception.source_binding_errors
        self.assertEqual(len(errors),2)
        self.assertEqual({tuple(e['path']) for e in errors},{('result','rows',0,'text'),('content','rows',0,'text')})
        self.assertTrue(all('keys=["rows"]' in e['message'] for e in errors))
        self.assertEqual(args,original)

    def test_actual_nested_result_key_is_valid_and_never_automatically_unwrapped(self):
        args=deepcopy(self.args);sources={'a':{'result':deepcopy(self.sources['a'])}}
        for binding in [args['assay_benchmark']['source'],args['exposures'][0]['source'],args['mass_bases'][0]['source']]:
            binding['path']=['result','rows',0,'text']
        self.assertEqual(compare(args,sources)['rows'][0]['comparison_concentration_uM'],10)
        with self.assertRaises(ValueError):compare(self.args,sources)


if __name__ == '__main__':
    unittest.main()
