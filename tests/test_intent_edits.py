"""One-field edits must not promote unrelated model text to a human decision."""
import copy
import tempfile
import unittest
from pathlib import Path

from evida.store import Conflict, Store


class IntentEditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'state.db')
        self.wid = self.store.create('Intent edit fixture')['id']
        self.records = [
            {'id': 'goal', 'label': 'Goal', 'text': 'Original goal', 'origin': 'researcher', 'source_refs': ['msg_original']},
            {'id': 'condition', 'label': 'Condition', 'text': 'Unknown context', 'origin': 'unknown', 'source_refs': ['msg_condition']},
            {'id': 'branch', 'label': 'Branch', 'text': 'Provisional branch', 'origin': 'inferred', 'source_refs': ['art_source']},
        ]
        self.publish(1, self.records)

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, revision, records):
        proposal = {'intent_records': copy.deepcopy(records), 'research_loop': {'hypotheses': []}}
        self.store.publish_decision(self.wid, revision, proposal, 'fixture_receipt')

    def edit(self, base, rows, key='edit'):
        state = self.store.snapshot(self.wid)
        body = {'kind': 'intent_edit', 'base_records': copy.deepcopy(base), 'records': copy.deepcopy(rows)}
        return self.store.command(self.wid, state['rev'], key, body)

    def test_only_changed_field_gets_new_origin_and_source(self):
        rows = copy.deepcopy(self.records)
        rows[0]['text'] = 'New goal'
        result = self.edit(self.records, rows)
        state = self.store.snapshot(self.wid)
        self.assertEqual(state['intent'][1:], self.records[1:])
        self.assertEqual(state['intent'][0]['source_refs'], [result['message_id']])
        event = state['events'][-1]['body']
        self.assertEqual(event['changed_ids'], ['goal'])
        self.assertEqual(event['protected_ids'], ['goal'])

    def test_successive_edits_remain_protected_but_other_fields_can_evolve(self):
        rows = copy.deepcopy(self.records)
        rows[0]['text'] = 'New goal'
        self.edit(self.records, rows)
        first = self.store.snapshot(self.wid)['intent']
        second = copy.deepcopy(first)
        second[2]['text'] = 'Researcher branch'
        self.edit(first, second, 'second')
        model = copy.deepcopy(self.records)
        model[1]['text'] = 'Context refined with new evidence'
        model[1]['origin'] = 'inferred'
        self.publish(3, model)
        saved = {r['id']: r for r in self.store.snapshot(self.wid)['intent']}
        self.assertEqual(saved['goal']['text'], 'New goal')
        self.assertEqual(saved['branch']['text'], 'Researcher branch')
        self.assertEqual(saved['condition'], model[1])

    def test_removed_field_not_silently_resurrected_and_can_be_readded(self):
        self.edit(self.records, self.records[:2])
        self.publish(2, self.records)
        base = self.store.snapshot(self.wid)['intent']
        self.assertEqual([r['id'] for r in base], ['goal', 'condition'])
        self.edit(base, base + [self.records[2]], 'restore-branch')
        self.publish(3, self.records)
        self.assertIn('branch', [r['id'] for r in self.store.snapshot(self.wid)['intent']])

    def test_same_revision_publication_cannot_overwrite_open_editor(self):
        revised = copy.deepcopy(self.records)
        revised[1]['text'] = 'Newly published interpretation'
        self.publish(1, revised)
        rows = copy.deepcopy(self.records)
        rows[0]['text'] = 'Desired edit'
        with self.assertRaises(Conflict):
            self.edit(self.records, rows)
        self.assertEqual(self.store.snapshot(self.wid)['intent'], revised)

    def test_duplicate_ids_rejected_without_partial_write(self):
        with self.assertRaises(ValueError):
            self.edit(self.records, [self.records[0], self.records[0]])
        self.assertEqual(self.store.snapshot(self.wid)['rev'], 1)

    def test_empty_explicit_intent_does_not_fall_back_to_old_frame(self):
        with self.store.connect(True) as db:
            self.store.event(db, self.wid, 'work_framed', {'based_rev': 2, 'intent_records': self.records})
        self.edit(self.records, [])
        self.edit([], [], 'keep-empty')
        self.publish(3, self.records)
        self.assertEqual(self.store.snapshot(self.wid)['intent'], [])

    def test_first_editor_can_use_current_unpublished_frame(self):
        self.wid = self.store.create('Unpublished frame fixture')['id']
        with self.store.connect(True) as db:
            self.store.event(db, self.wid, 'work_framed', {'based_rev': 1, 'intent_records': self.records})
        rows = copy.deepcopy(self.records)
        rows[0]['text'] = 'First explicit goal edit'
        self.edit(self.records, rows)
        self.assertEqual(self.store.snapshot(self.wid)['intent'][1:], self.records[1:])

    def test_empty_publication_rejects_obsolete_frame_editor_and_accepts_current_baseline(self):
        self.wid = self.store.create('Empty published intent fixture')['id']
        with self.store.connect(True) as db:
            self.store.event(db, self.wid, 'work_framed', {'based_rev': 1, 'intent_records': self.records})
        self.publish(1, [])
        with self.assertRaises(Conflict):
            self.edit(self.records, self.records, 'obsolete-editor')
        self.assertEqual(self.store.snapshot(self.wid)['intent'], [])
        self.edit([], self.records[:1], 'current-editor')
        state = self.store.snapshot(self.wid)
        self.assertEqual(state['intent'][0]['text'], self.records[0]['text'])
        self.assertEqual(state['intent'][0]['origin'], 'researcher')
        self.assertEqual(next(e['body']['intent_records'] for e in state['events'] if e['kind'] == 'work_framed'), self.records)


if __name__ == '__main__':
    unittest.main()
