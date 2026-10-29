import json
from pathlib import Path
import tempfile
import unittest

from evida.model_context import find_rows
from evida.runner import Runner
from evida.store import Store


class TableRowSearch(unittest.TestCase):
    def test_parent_analogue_repeats_and_missing_are_not_collapsed(self):
        rows = [{'candidate_id': 'CACHE_1', 'value': None},
                {'candidate_id': 'CACHE-HO_1', 'value': 5},
                {'candidate_id': 'CACHE_1', 'value': 0},
                {'candidate_id': 'cache_1', 'value': 2}, {'value': 3}]
        view = find_rows(rows, ['candidate_id'], ['CACHE_1', 'absent'], 0, 1)
        self.assertEqual(view['total_rows'], 2)
        self.assertEqual(view['rows'], [rows[0]])
        self.assertEqual(view['source_row_indices_0_based'], [0])
        self.assertEqual(view['selection']['unmatched_values'], ['absent'])
        self.assertEqual(view['selection']['rows_without_selected_path'], 1)
        self.assertTrue(view['has_more'])
        second = find_rows(rows, ['candidate_id'], ['CACHE_1'], 1, 1)
        self.assertEqual(second['rows'], [rows[2]])
        self.assertEqual(second['source_row_indices_0_based'], [2])
        self.assertFalse(second['has_more'])

    def test_nested_cell_strings_are_not_coerced_or_stripped(self):
        rows = [{'cells': [{'value': v}]} for v in [None, 0, '0', '', ' C1 ', 'C1']]
        view = find_rows(rows, ['cells', '0', 'value'], ['0', 'C1'], 0, 100)
        self.assertEqual(view['rows'], [rows[2], rows[5]])
        self.assertEqual(view['source_total_rows'], 6)

    def test_registered_reading_keeps_original_and_omits_binary_from_model(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'db.sqlite3'); wid = store.create('source fixture')['id']
            data = {'rows': [{'cells': [{'value': 'P1'}]}, {'cells': [{'value': 'A1'}]}],
                    'original_file_base64': 'preserved-original-placeholder', 'limits': ['Not a scientific match.']}
            aid = store.add_artifact(wid, 'workbook', 'repository_document', json.dumps(data).encode(), {})
            before = store.artifact(wid, aid)
            runner = object.__new__(Runner); runner.store = store
            args = {'artifact_id': aid, 'column_path': ['cells', '0', 'value'],
                    'values': ['P1'], 'offset': 0, 'limit': 100}
            check = {'operation': {'kind': 'tool', 'name': 'find_table_rows', 'arguments': args}}
            self.assertTrue(runner.check_readiness(wid, check)['executable'])
            view = runner.read_view(wid, 'find_table_rows', args)
            self.assertEqual(view['result']['rows'], [data['rows'][0]])
            self.assertNotIn('original_file_base64', view['result'])
            self.assertEqual(store.artifact(wid, aid), before)


if __name__ == '__main__':
    unittest.main()
