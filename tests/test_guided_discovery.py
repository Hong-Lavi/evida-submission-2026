"""Replay real retained guided rows; no generation, scoring, or model calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evida.discovery import (catalog, candidate_structures_view, choice_command,
                             mechanism_candidate_pairs, record_review)
from evida.store import Store, dump

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/guided_proposals_20261002.json').read_text())


class GuidedDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'synthetic.sqlite3')
        self.wid = self.store.create('Saved guided-result replay')['id']
        sources = {}
        for source in FIXTURE['sources']:
            sources[source['original_artifact_id']] = self.store.add_artifact(
                self.wid, 'Actual parent structure projection', source['kind'],
                dump(source['value']).encode(), {}, bump=False)
        self.value = copy.deepcopy(FIXTURE['result'])
        self.value['source_artifact_id'] = sources[self.value['source_artifact_id']]
        self.aid = self.store.add_artifact(self.wid, 'Actual saved generation with guided branch',
            'analogue_proposal', dump(self.value).encode(),
            {'consumed_artifacts': [sources[s] for s in FIXTURE['original_consumed_artifacts']]}, bump=False)

    def tearDown(self):
        self.temp.cleanup()

    def options(self):
        return [o for o in catalog(self.store, self.wid)['options']
                if o.get('candidate_artifact_id') == self.aid]

    def guided(self):
        return [o for o in self.options() if o['generation'].get('branch') == 'guided_search']

    def test_all_24_retained_guided_rows_are_distinct_unmeasured_options(self):
        options = self.options()
        self.assertEqual(len(options), 54)
        guided = self.guided()
        self.assertEqual(len(guided), 24)
        self.assertEqual(len({o['option_id'] for o in guided}), 24)
        self.assertEqual(len({o['entity_id'] for o in guided}), 18)
        for index, row in enumerate(self.value['guided_search']['rows']):
            option = next(o for o in guided if o['generation']['row_index'] == index)
            self.assertEqual(option['generation']['round'], row['round'])
            self.assertEqual(option['sources'][0], {'artifact_id': self.aid,
                'locator': 'guided_search/rows/'+str(index)})
            self.assertEqual(option['generation']['parent_candidate_ids'], row['declared_comparators'])
            self.assertIsNone(option['assessment'])
            self.assertEqual(option['review_status'], 'unreviewed')
            self.assertEqual(option['activity_evidence_status'], 'not_measured_in_this_generation')

    def test_existing_30_ids_and_reviewed_priority_are_unchanged(self):
        key = 'molecule:generated:'+self.aid+':proposed-1'
        record_review(self.store, self.wid, 1, 'synthetic-reviewed-main', {
            'question': 'Fixture review, no efficacy claim', 'new_options': [],
            'assessments': [{'option_id': key, 'status': 'needs_evidence', 'priority': 1,
                'comparison_group': 'fixture', 'reason': 'Original main-row review',
                'support_source_ids': [self.aid], 'challenge_source_ids': [],
                'uncertainties': ['Unmeasured'], 'next_action': 'Compare with parent'}],
            'unsearched_scope': []})
        original = self.store.artifact
        def without_guided(wid, aid):
            item = original(wid, aid)
            if aid == self.aid:
                value = json.loads(item['content']);value['guided_search']['rows'] = []
                item = {**item, 'content': dump(value).encode()}
            return item
        with patch.object(self.store, 'artifact', side_effect=without_guided):
            before = {o['option_id']: o for o in catalog(self.store, self.wid)['options']}
        after = {o['option_id']: o for o in catalog(self.store, self.wid)['options']}
        for option_id, option in before.items():
            self.assertEqual(after[option_id], option)
        self.assertEqual(after[key]['assessment']['priority'], 1)
        self.assertTrue(all(o['assessment'] is None for o in self.guided()))
        for row in self.value['rows']:
            self.assertIn('molecule:generated:'+self.aid+':'+row['candidate_id'], after)

    def test_generated_parent_name_does_not_link_to_a_same_named_main_row(self):
        option = next(o for o in self.guided() if o['generation']['row_index'] == 0)
        self.assertEqual(option['generation']['parent_candidate_ids'], ['proposed-18'])
        self.assertEqual(option['generation']['declared_parent_structure']['smiles'],
                         self.value['guided_search']['rows'][0]['nearest_retrieved_smiles'])
        self.assertEqual(option['generation']['parent_links'][0]['status'], 'unresolved_generated_parent')
        self.assertEqual(option['generation']['parent_links'][0]['option_ids'], [])
        self.assertNotIn('molecule:generated:'+self.aid+':proposed-18',
                         option['generation']['parent_links'][0]['option_ids'])

    def test_selected_guided_row_uses_its_exact_structure_and_can_link_to_a_mechanism(self):
        option = next(o for o in self.guided() if o['generation']['row_index'] == 0)
        key = option['option_id']
        record_review(self.store, self.wid, 1, 'synthetic-guided-review', {
            'question': 'Fixture followthrough', 'new_options': [{'option_id': 'mechanism:fixture',
                'kind': 'mechanism', 'label': 'Fixture mechanism', 'description': 'Not efficacy evidence',
                'source_ids': [self.aid]}],
            'assessments': [{'option_id': key, 'status': 'needs_evidence', 'priority': None,
                'comparison_group': 'fixture', 'reason': 'Proposal with unresolved function',
                'support_source_ids': [self.aid], 'challenge_source_ids': [],
                'uncertainties': ['Unmeasured'], 'next_action': 'Paired functional assay',
                'targets_mechanism': {'option_id': 'mechanism:fixture', 'reason': 'Fixture question'}}],
            'unsearched_scope': []})
        choice_command(self.store, self.wid, {'expected_rev': 1, 'command_id': 'select-guided-fixture',
            'option_id': key, 'text': 'Inspect the saved guided structure'})
        with patch('evida.structure_depiction.attach', side_effect=lambda value,*args: value):
            shown = candidate_structures_view(self.store, self.wid, limit=1)
        self.assertEqual(shown['rows'][0]['option_id'], key)
        self.assertEqual(shown['rows'][0]['smiles'], self.value['guided_search']['rows'][0]['smiles'])
        wrong = next(r for r in self.value['rows'] if r['candidate_id'] == option['entity_id'])
        self.assertNotEqual(shown['rows'][0]['smiles'], wrong['smiles'])
        pairs = mechanism_candidate_pairs(self.store, self.wid, {'rows': []})['pairs']
        self.assertEqual([p['candidate_id'] for p in pairs], [key])


if __name__ == '__main__':
    unittest.main()
