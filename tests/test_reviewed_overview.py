"""Screen projections retain pending candidates without promoting them to recommendations."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from evida.discovery import catalog, choice_command, overview, record_review
from evida.store import Store, dump
from evida.runner import Runner
from evida.server import handler_for


class ReviewedOverviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'copy.sqlite3')
        self.wid = self.store.create('Synthetic UI projection test')['id']
        fixture = json.loads((Path(__file__).parent / 'fixtures/generated_proposals_20261002.json').read_text())
        self.aid = self.store.add_artifact(self.wid, 'Saved real generation, replay only',
            'analogue_proposal', dump(fixture['records'][0]['result']).encode(), {}, bump=False)
        self.keys = [x['option_id'] for x in catalog(self.store, self.wid)['options']]

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_pending_and_deferred_candidates_remain_visible_without_recommendation(self):
        states = ['needs_evidence', 'deferred', 'alternative']
        review = {'question': 'Synthetic UI review only',
            'new_options': [{'option_id': 'mechanism:ui', 'kind': 'mechanism', 'label': 'UI fixture',
                            'description': 'Not scientific evidence', 'source_ids': [self.aid]}],
            'assessments': [{'option_id': key, 'status': status, 'priority': None,
                'comparison_group': 'UI fixture', 'reason': 'unmeasured',
                'support_source_ids': [self.aid], 'challenge_source_ids': [],
                'uncertainties': ['no assay'], 'next_action': 'Test function',
                'targets_mechanism': {'option_id': 'mechanism:ui', 'reason': 'fixture link'}}
                for key, status in zip(self.keys, states)], 'unsearched_scope': []}
        record_review(self.store, self.wid, 1, 'synthetic', review)
        value = overview(self.store, self.wid, for_ui=True)
        self.assertEqual(value['recommendations'], [])
        self.assertEqual(value['reconsidered_options'], [])
        rows = value['reviewed_options']
        self.assertEqual(len(rows), 3)
        self.assertEqual([x['assessment']['status'] for x in rows], states)
        self.assertTrue(all(x['assessment']['targets_mechanism']['option_id']=='mechanism:ui' for x in rows))
        self.assertEqual(value['counts']['molecule'], 12)
        self.assertEqual(value['reviewed'], 3)

    def test_selected_unreviewed_candidate_has_current_structure_identity_and_no_assessment(self):
        key = self.keys[-1]
        choice_command(self.store, self.wid, {'expected_rev': 1, 'command_id': 'ui-select',
            'option_id': key, 'text': 'Synthetic UI choice only', 'review_requested': False})
        value = overview(self.store, self.wid, for_ui=True)
        self.assertEqual(value['recommendations'], [])
        self.assertEqual(value['reviewed_options'], [])
        self.assertEqual(value['selected_option']['option_id'], key)
        self.assertEqual(value['selected_option']['candidate_artifact_id'], self.aid)
        self.assertIsNone(value['selected_option']['assessment'])
        self.assertEqual(value['selected']['option_id'], key)

    def test_model_context_retains_prior_projection_without_duplicate_ui_rows(self):
        record_review(self.store, self.wid, 1, 'synthetic', {
            'question': 'Synthetic context boundary', 'new_options': [],
            'assessments': [{'option_id': self.keys[0], 'status': 'recommended',
                'priority': 1, 'comparison_group': 'UI fixture', 'reason': 'Synthetic only',
                'support_source_ids': [self.aid], 'challenge_source_ids': [],
                'uncertainties': ['no assay'], 'next_action': 'Test function'}],
            'unsearched_scope': []})
        runner = Runner.__new__(Runner)
        runner.root = Path(__file__).resolve().parents[1]
        runner.store = self.store
        value = runner.model_context(self.wid, 1, False)['DISCOVERY_OPTIONS']
        self.assertNotIn('reviewed_options', value)
        self.assertNotIn('selected_option', value)
        self.assertEqual(value['recommendations'][0]['option_id'], self.keys[0])
        for field in ('candidate_artifact_id', 'entity_id', 'origin', 'structure_status'):
            self.assertNotIn(field, value['recommendations'][0])
        self.assertEqual(value['total'], 12)

    def test_workspace_get_explicitly_includes_current_selected_ui_projection(self):
        key = self.keys[-1]
        choice_command(self.store, self.wid, {'expected_rev': 1, 'command_id': 'http-ui-select',
            'option_id': key, 'text': 'Synthetic UI choice only', 'review_requested': False})
        # Execute the real GET dispatch without a socket or an Application. The
        # only store is this test's newly created temporary SQLite fixture.
        handler_class = handler_for(SimpleNamespace(
            store=self.store, root=Path(__file__).resolve().parents[1]))
        handler = handler_class.__new__(handler_class)
        handler.path = '/api/workspaces/' + self.wid
        handler.headers = {'Host': '127.0.0.1'}
        handler.command = 'GET'
        response = []
        handler.send = lambda value, status=200, **kwargs: response.append((status, value))
        handler.dispatch(False)
        self.assertEqual(response[0][0], 200)
        self.assertEqual(response[0][1]['editable_intents'], [])
        value = response[0][1]['discovery']
        self.assertEqual(value['selected_option']['option_id'], key)
        self.assertEqual(value['selected_option']['candidate_artifact_id'], self.aid)
        self.assertEqual(value['reviewed_options'], [])


if __name__ == '__main__':
    unittest.main()
