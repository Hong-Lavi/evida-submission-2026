import copy
import json
from pathlib import Path
import tempfile
import unittest

import jsonschema
from evida.calculation_sections import presentation, read
from evida.contracts import FUNCTION_BY_NAME
from evida.provided_views import build
from evida.runner import Runner, READING_FUNCTIONS
from evida.store import Store


class CalculationSectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'db.sqlite3')
        self.wid = self.store.create('Synthetic exact calculation fixture')['id']
        self.value = {'status': 'succeeded', 'semantic_type': 'conditional_pathway_hypotheses',
            'rows': [{'source': 'A', 'sign': -1, 'target': 'B', 'network_index': 1}],
            'conditions': ['Unknown cell composition'], 'limits': ['Not causal validation'],
            'solver_review': {'unique_optimum_established': False},
            'author_result': {
                'weightedSIF': [{'Node1': f'N{i}', 'Weight': 0 if i % 2 else 1} for i in range(235)],
                'nodesAttributes': [{'Node': 'A', 'AvgAct': -1}, {'Node': 'B', 'AvgAct': None}],
                'sifAll': [[{'Node1': 'A', 'Sign': -1, 'Node2': 'B'}], [], [{'Node1': 'C', 'Sign': 1, 'Node2': 'D'}]],
                'attributesAll': [[{'Nodes': 'A', 'Activity': -1}], [], [{'Nodes': 'C', 'Activity': 0}]],
                'future_field': {'unrecognised_must_survive': True}}}
        self.raw = json.dumps(self.value).encode()
        self.aid = self.store.add_artifact(self.wid, 'Source calculation', 'pathway_hypotheses', self.raw, {}, bump=False)
        self.runner = object.__new__(Runner); self.runner.store = self.store

    def tearDown(self):
        self.temp.cleanup()

    def test_default_conditions_and_catalog_remain_without_all_internal_tables(self):
        before = copy.deepcopy(self.value)
        result = self.runner.inspect(self.wid, self.aid)['result']
        self.assertEqual(result['rows'], self.value['rows'])
        for key in ('conditions', 'limits', 'solver_review'):
            self.assertEqual(result[key], self.value[key])
        self.assertEqual(result['author_result'], {'future_field': {'unrecognised_must_survive': True}})
        self.assertEqual({x['section']: x['total_rows'] for x in result['calculation_sections']},
                         {'weightedSIF': 235, 'nodesAttributes': 2, 'sifAll': 2, 'attributesAll': 2})
        self.assertEqual(presentation(self.value), presentation(before))
        self.assertEqual(self.value, before)

    def test_all_pages_recover_exact_zero_and_unselected_rows_and_original_paths(self):
        recovered = []
        for offset in range(0, 235, 30):
            view = self.runner.read_view(self.wid, 'read_calculation_section',
                {'artifact_id': self.aid, 'section': 'weightedSIF', 'offset': offset, 'limit': 30})
            r = view['result']
            self.assertEqual(r['has_more'], offset + 30 < 235)
            self.assertEqual(r['conditions'], self.value['conditions'])
            for row in r['rows']:
                source = self.value
                for key in row['source_path']:
                    source = source[int(key)] if isinstance(source, list) else source[key]
                self.assertEqual(row['value'], source)
                recovered.append(row['value'])
        self.assertEqual(recovered, self.value['author_result']['weightedSIF'])
        self.assertEqual(self.store.artifact(self.wid, self.aid)['content'], self.raw)

    def test_grouped_network_offsets_do_not_relabel_original_network_indices(self):
        result = read(self.value, 'attributesAll', 1, 1)
        self.assertEqual(result['rows'], [{'source_path': ['author_result', 'attributesAll', '2', '0'],
            'network_index': 3, 'value': {'Nodes': 'C', 'Activity': 0}}])
        self.assertFalse(result['has_more'])
        self.assertEqual(read(self.value, 'attributesAll', 50, 1)['rows'], [])

    def test_provided_views_can_include_different_sections_but_not_duplicate_read(self):
        normal = {'artifact_id': self.aid, 'offset': 0, 'limit': 10}
        spec = {**normal, 'section': 'attributesAll'}
        packet = build(self.runner, self.wid, [normal, spec])
        self.assertEqual(len(packet['views']), 2)
        self.assertEqual(packet['views'][1]['view']['result']['rows'][0]['value'], {'Nodes': 'A', 'Activity': -1})
        with self.assertRaises(ValueError):
            build(self.runner, self.wid, [spec, spec])

    def test_invalid_shapes_unknown_sections_and_other_artifact_kinds_are_not_empty_evidence(self):
        for section, offset, limit in [('wrong', 0, 1), ('sifAll', -1, 1), ('sifAll', 0, 0), ('sifAll', True, 1)]:
            with self.assertRaises(ValueError): read(self.value, section, offset, limit)
        malformed = copy.deepcopy(self.value); malformed['author_result']['sifAll'] = None
        self.assertIsNone(presentation(malformed)['author_result']['sifAll'])
        with self.assertRaises(ValueError): read(malformed, 'sifAll', 0, 1)
        other = self.store.add_artifact(self.wid, 'Other', 'research_evidence', self.raw, {}, bump=False)
        with self.assertRaises(ValueError): self.runner.calculation_section(self.wid, other, 'sifAll')

    def test_real_read_contract_is_registered_and_rejects_unbounded_or_unknown_sections(self):
        self.assertIn('read_calculation_section', READING_FUNCTIONS)
        schema = FUNCTION_BY_NAME['read_calculation_section']['parameters']
        args = {'artifact_id': self.aid, 'section': 'weightedSIF', 'offset': 0, 'limit': 30}
        jsonschema.validate(args, schema)
        for bad in [{**args, 'limit': 101}, {**args, 'section': 'other'}]:
            with self.assertRaises(jsonschema.ValidationError): jsonschema.validate(bad, schema)


if __name__ == '__main__':
    unittest.main()
