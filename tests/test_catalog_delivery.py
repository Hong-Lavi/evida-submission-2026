import copy
import hashlib
import json
import unittest

from evida.catalog_delivery import apply_catalog_delivery, encoded
from evida.model_context import next_model_context, unpack


class CatalogDeliveryTests(unittest.TestCase):
    def test_large_arguments_are_addressed_without_dropping_sources_or_conditions(self):
        arguments = {'observations': [{'id': str(i), 'value': None, 'unit': 'unknown',
                                      'opposes': 'hypothesis-1'} for i in range(200)]}
        source = {'artifact_id': 'a', 'kind': 'tool_reading', 'sha256': 'original',
                  'meta': {'arguments': arguments, 'source_artifact_id': 'source-a'},
                  'summary_view': {'contrast': {'shared_control': True}, 'limits': ['not independent']}}
        view = {'reading_id': 'a', 'sha256': 'original', 'arguments': arguments}
        context = {'RELEVANT_EVIDENCE': [source], 'COMPLETED_VIEWS': [view],
                   'CURRENT_INTENT': {'text': 'keep counterevidence'},
                   'WORKING_READINGS': [{'reading_id': 'a', 'content': arguments}],
                   'PREVIOUS_DECISION': {'hypotheses': ['exact original']}}
        original = copy.deepcopy(context)
        result = apply_catalog_delivery(context)
        self.assertEqual(context, original)
        self.assertEqual(result['CURRENT_INTENT'], context['CURRENT_INTENT'])
        self.assertEqual(result['WORKING_READINGS'], context['WORKING_READINGS'])
        self.assertEqual(result['PREVIOUS_DECISION'], context['PREVIOUS_DECISION'])
        catalog = result['RELEVANT_EVIDENCE'][0]
        self.assertEqual(catalog['artifact_id'], 'a')
        self.assertEqual(catalog['summary_view'], source['summary_view'])
        self.assertIn('COMPLETED_VIEWS', catalog['catalog_location'])
        self.assertNotIn('arguments', catalog['meta'])
        self.assertEqual(result['COMPLETED_VIEWS'][0]['arguments_sha256'], hashlib.sha256(encoded(arguments)).hexdigest())
        self.assertLess(len(encoded(result['RELEVANT_EVIDENCE'])), len(encoded(context['RELEVANT_EVIDENCE'])))

    def test_navigation_folding_requires_same_id_and_hash_and_preserves_conditions(self):
        entry = {'artifact_id': 'r1', 'kind': 'tool_reading', 'sha256': 'a',
                 'title': 'original title',
                 'meta': {'function': 'read', 'scientific_context_verified': False,
                          'consumed_artifacts': ['source-x']},
                 'summary_view': {'limits': ['opposes earlier hypothesis'],
                                  'context': {'dose': None}, 'contrast': {'independent': False}}}
        for digest in ['b', 'a']:
            context = {'RELEVANT_EVIDENCE': [entry], 'COMPLETED_VIEWS': [{'reading_id': 'r1', 'sha256': digest}]}
            result = apply_catalog_delivery(context)['RELEVANT_EVIDENCE'][0]
            self.assertEqual(result['summary_view'], entry['summary_view'])
            self.assertEqual(result['meta']['scientific_context_verified'], False)
            self.assertEqual(result['meta']['consumed_artifacts'], ['source-x'])
            self.assertEqual('catalog_location' in result, digest == 'a')

    def test_small_null_zero_false_and_duplicate_source_entries_are_exact(self):
        source = {'artifact_id': 'a', 'meta': {'source_artifact_id': None, 'based_rev': 0, 'scientific_context_verified': False},
                  'summary_view': {'limits': [], 'contrast': {'matched': False}}}
        context = {'RELEVANT_EVIDENCE': [source, source], 'COMPLETED_VIEWS': []}
        result = apply_catalog_delivery(context)
        self.assertEqual([a['meta'] for a in result['RELEVANT_EVIDENCE']], [source['meta'], source['meta']])
        self.assertEqual([a['summary_view'] for a in result['RELEVANT_EVIDENCE']], [source['summary_view'], source['summary_view']])

    def test_large_summary_is_explicitly_unread_and_latest_tool_pair_is_exact(self):
        source = {'artifact_id': 'a', 'meta': {}, 'summary_view': {'limits': ['condition'] * 900}}
        context = {'RELEVANT_EVIDENCE': [source], 'COMPLETED_VIEWS': []}
        result = apply_catalog_delivery(context)
        ref = result['RELEVANT_EVIDENCE'][0]['summary_view']['limits']
        self.assertEqual(ref['item_count'], 900)
        self.assertEqual(ref['field_path'], ['result', 'limits'])
        output = [{'type': 'reasoning', 'id': 'opaque', 'encrypted_content': 'synthetic', 'summary': []},
                  {'type': 'function_call', 'call_id': 'read1', 'name': 'inspect_artifact', 'arguments': '{}'}]
        returned = [{'type': 'function_call_output', 'call_id': 'read1', 'output': json.dumps(source)}]
        request = next_model_context(result, output, returned)
        self.assertEqual(request[1:], output + returned)
        self.assertEqual(unpack(json.loads(request[0]['content'])), result)


if __name__ == '__main__':
    unittest.main()
