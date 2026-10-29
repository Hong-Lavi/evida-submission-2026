"""Conditions that must survive a source join; fixtures are not biological evidence."""
import copy
import json
from unittest.mock import patch
import unittest

from evida.intervention_direction import audit


def evidence():
    def row(rid, molecule, direction):
        return {'id': rid, 'drug': {'id': molecule, 'name': molecule},
            'target': {'id': 'ENSG00000118271'}, 'disease': {'id': 'EFO_0700065'},
            'datasourceId': 'clinical_precedence', 'directionOnTarget': direction,
            'directionOnTrait': 'protect', 'trialWhyStopped': 'fixture: enrollment',
            'studyOverview': 'fixture adult condition, not a real study'}
    return {'status': 'succeeded', 'semantic_type': 'curated_target_disease_evidence_records',
        'source': {'sha256': 'fixture'}, 'rows': [row('A', 'CHEMBL1', 'GoF'),
            row('B', 'CHEMBL2', 'LoF'), row('C', 'CHEMBL1', 'GoF'), row('D', 'CHEMBL3', None)],
        'summary': {'target_id': 'ENSG00000118271', 'disease_id': 'EFO_0700065',
            'returned': 4, 'total': 100, 'next_cursor': 'fixture-more'}}


def mechanism(mid, action, target):
    return {'molecule_chembl_id': mid, 'action_type': action, 'target_chembl_id': target}


class DirectionTests(unittest.TestCase):
    @patch('evida.intervention_direction.fetch')
    def test_source_cursor_and_mechanism_completion_are_independent(self, fetch):
        fetch.return_value = json.dumps({'mechanisms': [mechanism('CHEMBL1', 'STABILISER', 'CHEMBL11')],
            'page_meta': {'next': None, 'total_count': 1, 'offset': 0}}).encode(), {}
        result = audit(evidence(), {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1']})
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['summary']['source_query_coverage']['status'], 'partial')
        self.assertEqual(result['summary']['mechanism_query_coverage']['status'], 'complete')
        self.assertEqual(result['summary']['source_query_coverage']['reported_total'], 100)

    @patch('evida.intervention_direction.fetch')
    def test_last_source_page_is_not_the_whole_query(self, fetch):
        fetch.return_value = b'{"mechanisms":[],"page_meta":{"next":null,"total_count":0}}', {}
        source = evidence(); source['summary']['next_cursor'] = None
        result = audit(source, {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1']})
        self.assertEqual(result['summary']['source_query_coverage']['status'], 'partial')
        self.assertEqual(result['rows'][0]['mechanism_status'], 'not_returned_not_negative')

    @patch('evida.intervention_direction.fetch')
    def test_unknown_totals_and_duplicate_rows_cannot_look_complete(self, fetch):
        fetch.return_value = b'{"mechanisms":[],"page_meta":{"next":null}}', {}
        source = evidence(); source['summary'].update(total=None, next_cursor=None)
        result = audit(source, {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1']})
        self.assertEqual(result['summary']['source_query_coverage']['status'], 'unknown')
        self.assertEqual(result['summary']['mechanism_query_coverage']['status'], 'unknown')
        source['summary']['total'] = 4; source['rows'][1]['id'] = source['rows'][0]['id']
        result = audit(source, {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1']})
        self.assertEqual(result['summary']['source_query_coverage']['status'], 'inconsistent')

    @patch('evida.intervention_direction.fetch')
    def test_complete_query_preserves_original_disease_and_dates(self, fetch):
        fetch.return_value = b'{"mechanisms":[],"page_meta":{"next":null,"total_count":0}}', {}
        source = evidence(); source['summary'].update(total=4, next_cursor=None)
        source['rows'][0].update(diseaseFromSource='original fixture condition', evidenceDate='2020', releaseDate='2026')
        result = audit(source, {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1']})
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['rows'][0]['source_evidence'], source['rows'][0])
        self.assertTrue(result['summary']['source_query_coverage']['complete_for_reported_query'])

    @patch('evida.intervention_direction.fetch')
    def test_stabilizer_and_rnai_keep_original_records_and_conditions(self, fetch):
        body = {'mechanisms': [mechanism('CHEMBL1', 'STABILISER', 'CHEMBL11'),
                              mechanism('CHEMBL2', 'RNAI INHIBITOR', 'CHEMBL22')], 'page_meta': {'next': None}}
        fetch.return_value = json.dumps(body).encode(), {'url': 'fixture'}
        source = evidence(); original = copy.deepcopy(source)
        result = audit(source, {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1', 'CHEMBL2']})
        self.assertEqual(source, original)
        self.assertEqual([r['row_id'] for r in result['rows']], ['A', 'B', 'C'])
        self.assertEqual([r['source_evidence'] for r in result['rows']], source['rows'][:3])
        self.assertEqual(result['rows'][0]['action_types'], ['STABILISER'])
        self.assertEqual(result['rows'][1]['mechanisms'][0]['target_chembl_id'], 'CHEMBL22')
        self.assertEqual(result['original_mechanism_response'], body)
        self.assertEqual(result['summary']['unselected_molecule_ids'], ['CHEMBL3'])
        self.assertEqual(result['summary']['source_evidence_coverage']['total'], 100)
        self.assertTrue(result['summary']['counts_are_not_independent_support'])
        self.assertNotIn('recommended_direction', result)

    @patch('evida.intervention_direction.fetch')
    def test_missing_is_not_negative_and_partial_source_remains_partial(self, fetch):
        fetch.return_value = b'{"mechanisms":[],"page_meta":{"next":null}}', {}
        source = evidence(); source['status'] = 'partial'
        result = audit(source, {'artifact_id': 'art', 'molecule_ids': ['CHEMBL3']})
        self.assertEqual(result['status'], 'partial')
        self.assertIsNone(result['rows'][0]['direction_on_target'])
        self.assertEqual(result['rows'][0]['mechanism_status'], 'not_returned_not_negative')

    @patch('evida.intervention_direction.fetch')
    def test_unmatched_source_scope_or_selection_does_not_issue_lookup(self, fetch):
        for field, value in [('semantic_type', 'wrong'), ('status', 'input_missing')]:
            source = evidence(); source[field] = value
            with self.assertRaises(ValueError):
                audit(source, {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1']})
        source = evidence(); source['rows'][0]['target']['id'] = 'ENSG00000141510'
        with self.assertRaises(ValueError):
            audit(source, {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1']})
        for selected in ([], ['CHEMBL9'], ['CHEMBL1', 'CHEMBL1'], ['CHEMBL1&x=bad'], 'CHEMBL1'):
            with self.assertRaises(ValueError):
                audit(evidence(), {'artifact_id': 'art', 'molecule_ids': selected})
        fetch.assert_not_called()

    @patch('evida.intervention_direction.fetch')
    def test_parent_salt_and_target_mappings_are_not_inferred(self, fetch):
        fetch.return_value = json.dumps({'mechanisms': [mechanism('CHEMBL9', 'STABILISER', 'CHEMBL11')]}).encode(), {}
        result = audit(evidence(), {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1']})
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['unrequested_records'][0]['molecule_chembl_id'], 'CHEMBL9')
        self.assertEqual(result['summary']['mechanism_action_counts'], {})
        self.assertEqual(result['rows'][0]['mechanism_status'], 'not_returned_not_negative')
        fetch.return_value = json.dumps({'mechanisms': [mechanism('CHEMBL1', 'STABILISER', None)],
                                        'page_meta': {'next': '/next'}}).encode(), {}
        result = audit(evidence(), {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1']})
        self.assertEqual(result['status'], 'partial')
        self.assertIsNone(result['rows'][0]['mechanisms'][0]['target_chembl_id'])
        self.assertNotIn('target_match_verified', result['rows'][0])
        self.assertFalse(result['rows'][0]['mechanism_records_complete'])

    @patch('evida.intervention_direction.fetch')
    def test_counts_separate_parent_record_and_partial_page_coverage(self, fetch):
        records = [{**mechanism('CHEMBL1', 'STABILISER', 'CHEMBL11'), 'parent_molecule_chembl_id': 'CHEMBL1'},
                   {**mechanism('CHEMBL2', 'STABILISER', 'CHEMBL11'), 'parent_molecule_chembl_id': 'CHEMBL1'}]
        fetch.return_value = json.dumps({'mechanisms': records, 'page_meta': {'next': None}}).encode(), {}
        result = audit(evidence(), {'artifact_id': 'art', 'molecule_ids': ['CHEMBL1', 'CHEMBL2']})
        self.assertEqual(result['summary']['mechanism_action_counts'], {'STABILISER': 2})
        self.assertEqual(result['summary']['parent_action_counts'], {'STABILISER': 1})
        self.assertEqual(result['summary']['distinct_explicit_parents'], 1)
        self.assertEqual(result['explicit_parent_groups'][0]['molecule_ids'], ['CHEMBL1', 'CHEMBL2'])
        coverage = result['summary']['direction_field_coverage']['clinical_precedence']
        self.assertEqual(coverage['total'], 4)
        self.assertEqual(coverage['directionOnTarget_reported'], 3)
        self.assertEqual(coverage['directionOnTarget_unreported'], 1)
        self.assertEqual(result['rows'][0]['trial_stop']['reason'], 'fixture: enrollment')

    def test_live_lookup_is_never_reused_as_a_fresh_response(self):
        from evida.runner import Runner
        self.assertIsNone(Runner.cache_key(None, 'ws', 'intervention_direction_audit',
                                          {'artifact_id': 'any', 'molecule_ids': ['CHEMBL1']}))


if __name__ == '__main__':
    unittest.main()
