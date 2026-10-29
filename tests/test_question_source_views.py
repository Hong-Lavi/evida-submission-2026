"""Selected evidence must keep conditions, provenance and discrepant observations."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import jsonschema
from evida.contracts import FUNCTION_BY_NAME, model_functions
from evida.model_context import select_columns
from evida.runner import Runner
from evida.store import Store


class QuestionSourceViewTests(unittest.TestCase):
    def test_matching_rows_projection_keeps_conflict_and_all_source_locations(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'db.sqlite3')
            wid = store.create('question-source-view fixture')['id']
            rows = []
            for number, (cid, result) in enumerate([('P1', 'no'), ('P2', None), ('P1', 'Confirms')], 4):
                rows.append({'kind': 'xlsx_row', 'row_id': f'xlsx:observations:row:{number}',
                             'sheet': 'observations', 'row_number': number, 'hidden_row': number == 6,
                             'requires_original_review': True, 'source_url': 'https://example.test/source',
                             'cells': [{'coordinate': f'A{number}', 'value': cid, 'data_type': 's', 'number_format': 'General'},
                                       {'coordinate': f'B{number}', 'value': result, 'data_type': 's', 'number_format': 'General'},
                                       {'coordinate': f'C{number}', 'value': number, 'data_type': 'n', 'number_format': '0.00 "µM"',
                                        'comment': 'Measured in a different condition.'}],
                             'text': 'source-derived duplicated text'})
            data = {'rows': rows, 'limits': ['Sample linkage unverified.'],
                    'original_file_base64': 'fixture-not-a-real-file', 'extraction': {'sheets': ['observations']}}
            aid = store.add_artifact(wid, 'source', 'repository_document', json.dumps(data).encode(), {})
            original = store.artifact(wid, aid)
            runner = object.__new__(Runner); runner.store = store
            args = {'artifact_id': aid, 'column_path': ['cells', '0', 'value'], 'values': ['P1', 'unknown'],
                    'columns': [['cells', '1', 'value'], ['cells', '2', 'value']], 'offset': 0, 'limit': 1}
            args_before = copy.deepcopy(args)
            jsonschema.validate(args, FUNCTION_BY_NAME['find_table_columns']['parameters'])
            self.assertTrue(runner.check_readiness(wid, {'operation': {'kind': 'tool', 'name': 'find_table_columns', 'arguments': args}})['executable'])
            first = runner.read_view(wid, 'find_table_columns', args)['result']
            self.assertEqual(args, args_before)
            self.assertEqual(first['selected_columns'][0], ['cells', '0', 'value'])
            self.assertEqual(first['source_row_indices_0_based'], [0])
            self.assertTrue(first['has_more'])
            self.assertEqual(first['selection']['unmatched_values'], ['unknown'])
            self.assertEqual(first['total_rows'], 2)
            self.assertEqual(first['rows'][0]['cells'][1]['value'], 'no')
            self.assertEqual(first['rows'][0]['cells'][2]['source_cell'], rows[0]['cells'][2])
            self.assertEqual(first['limits'], data['limits'])
            second = runner.read_view(wid, 'find_table_columns', {**args, 'offset': 1})['result']
            self.assertEqual(second['source_row_indices_0_based'], [2])
            self.assertFalse(second['has_more'])
            self.assertEqual(second['rows'][0]['cells'][1]['value'], 'Confirms')
            self.assertTrue(second['rows'][0]['identity']['hidden_row'])
            self.assertEqual(second['rows'][0]['identity']['row_number'], 6)
            self.assertEqual(store.artifact(wid, aid), original)
            self.assertNotIn('original_file_base64', first)
            self.assertNotIn('text', first['rows'][0])

    def test_absent_null_zero_and_formula_provenance_survive_projection(self):
        raw = {'kind': 'xlsx_row', 'row_id': 'xlsx:Sheet1:row:2', 'cells': [
            {'coordinate': 'A2', 'value': None, 'data_type': 'n'},
            {'coordinate': 'B2', 'value': 0, 'data_type': 'n'},
            {'coordinate': 'C2', 'value': '=B2*2', 'data_type': 'f', 'cached_value': 0,
             'formula_evaluated_here': False}]}
        view = {'result': {'rows': [raw]}}
        original = copy.deepcopy(view)
        selected = select_columns(view, [['cells', '0', 'value'], ['cells', '1', 'value'],
                                        ['cells', '2', 'cached_value'], ['cells', '3', 'value']])
        cells = selected['result']['rows'][0]['cells']
        self.assertEqual([(c['present'], c['value']) for c in cells], [(True, None), (True, 0), (True, 0), (False, None)])
        self.assertEqual(cells[2]['source_cell']['value'], '=B2*2')
        self.assertFalse(cells[2]['source_cell']['formula_evaluated_here'])
        self.assertEqual(view, original)

    def test_selected_compounds_do_not_reinject_unselected_provider_bodies(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'db.sqlite3')
            wid = store.create('source envelope fixture')['id']
            rows = [
                {'candidate_id': 'A', 'activities': [{'value': 0, 'units': 'nM', 'relation': '<', 'assay': 'cell'}]},
                {'candidate_id': 'B', 'activities': [{'value': 9, 'units': 'uM', 'relation': '=', 'assay': 'binding'}]},
                {'candidate_id': 'A', 'activities': [{'value': None, 'units': None, 'relation': None, 'assay': 'different'}]},
            ]
            raw = {'rows': rows, 'original_activity_response': {'activities': rows},
                   'structure_response': {'molecules': [{'candidate_id': 'B', 'unread_structure': 'source-only'}]},
                   'limits': ['No cross-assay potency ordering.'], 'context': {'species': 'not supplied'}}
            aid = store.add_artifact(wid, 'source', 'compound_candidates', json.dumps(raw).encode(), {})
            original = store.artifact(wid, aid)
            runner = object.__new__(Runner); runner.store = store
            args = {'artifact_id': aid, 'column_path': ['candidate_id'], 'values': ['A', 'missing'],
                    'offset': 0, 'limit': 1}
            first = runner.read_view(wid, 'find_table_rows', args)['result']
            second = runner.read_view(wid, 'find_table_columns',
                                      {**args, 'offset': 1, 'columns': [['activities']]})['result']
            self.assertEqual(first['rows'], rows[:1])
            self.assertTrue(first['has_more'])
            self.assertEqual(first['source_row_indices_0_based'], [0])
            self.assertEqual(second['source_row_indices_0_based'], [2])
            self.assertEqual(second['rows'][0]['cells'][1]['value'], rows[2]['activities'])
            self.assertFalse(second['has_more'])
            for result in (first, second):
                self.assertNotIn('original_activity_response', result)
                self.assertNotIn('structure_response', result)
                self.assertEqual(result['limits'], raw['limits'])
                self.assertEqual(result['context'], raw['context'])
                self.assertEqual(result['selection']['unmatched_values'], ['missing'])
                self.assertEqual(result['source_total_rows'], 3)
            self.assertEqual(store.artifact(wid, aid), original)

    def test_original_lookup_contract_and_shared_note_contract_remain_available(self):
        specs = {s['name']: s for s in model_functions()}
        self.assertNotIn('columns', FUNCTION_BY_NAME['find_table_rows']['parameters']['properties'])
        self.assertIn('columns', specs['find_table_columns']['parameters']['required'])
        self.assertIn('research_notes', specs['find_table_columns']['parameters']['required'])
        self.assertNotIn('research_notes', FUNCTION_BY_NAME['find_table_columns']['parameters']['properties'])


if __name__ == '__main__':
    unittest.main()
