import tempfile
import unittest
from pathlib import Path
from evida.store import Store
from evida.evidence_scope import check_tool, validate


class EvidenceScopeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'study.sqlite3')
        self.state = self.store.create('Historical evidence')

    def message(self, scope):
        state = self.store.snapshot(self.state['id'])
        return self.store.command(state['id'], state['rev'], 'scope-' + str(state['rev']),
            {'kind': 'message', 'text': 'Use this evidence boundary.', 'evidence_scope': scope})

    def test_external_retrieval_blocked_but_computation_retained(self):
        self.message({'mode': 'supplied_only', 'as_of': '2006-11-30', 'note': 'Retrospective evidence.'})
        state = self.store.snapshot(self.state['id'])
        for tool in ('literature', 'article', 'webpage', 'public_lookup_bundle', 'future_unknown_tool'):
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                check_tool(state, tool)
        for tool in ('rdkit', 'source_document', 'next_observation_selection'):
            check_tool(state, tool)
        self.assertEqual(state['evidence_scope']['as_of'], '2006-11-30')

    def test_default_and_explicit_scope_change_preserve_existing_work(self):
        check_tool(self.state, 'literature')
        self.message({'mode': 'supplied_only', 'as_of': None, 'note': 'Fixed source set.'})
        self.message({'mode': 'unrestricted', 'as_of': None, 'note': 'Researcher expands sources.'})
        state = self.store.snapshot(self.state['id'])
        check_tool(state, 'literature')
        self.assertEqual(len([e for e in state['events'] if e['kind'] == 'message']), 2)

    def test_bad_scope_does_not_advance_revision(self):
        with self.assertRaises(ValueError):
            self.message({'mode': 'supplied_only', 'as_of': '2006-02-30', 'note': 'Invalid date.'})
        self.assertEqual(self.store.snapshot(self.state['id'])['rev'], 1)

    def test_observation_cannot_change_scope(self):
        with self.assertRaises(ValueError):
            self.store.command(self.state['id'], 1, 'bad', {'kind': 'observation', 'text': 'Result',
                'evidence_scope': {'mode': 'unrestricted', 'as_of': None, 'note': 'Scope edit.'}})


if __name__ == '__main__':
    unittest.main()
