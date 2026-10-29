from pathlib import Path
import tempfile
import unittest

from evida.incremental_discovery import record_notes
from evida.research_progress import view
from evida.store import Store, dump


class ResearchProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'state.sqlite3')
        self.wid = self.store.create('Progress fixture')['id']
        self.jid = self.store.enqueue(self.wid, 1, 'planner', {})
        self.store.start_job(self.jid)
        self.source = self.store.add_artifact(self.wid, 'Actual saved source', 'literature',
            dump({'rows': []}).encode(), {}, bump=False)
        self.notes = {'findings': [{'text': 'Possible mechanism, tissue unresolved.',
            'source_ids': [self.source]}], 'open_questions': ['Which tissue?'],
            'next_goal': 'Read tissue applicability'}

    def tearDown(self): self.tmp.cleanup()

    def test_public_notes_are_read_only_and_return_requires_matching_operation(self):
        aid = record_notes(self.store, self.wid, 1, self.jid, self.notes, call_id='first')
        before = self.store.snapshot(self.wid)
        result = view(self.store, self.wid, before)
        self.assertEqual(result['notes'], self.notes)
        self.assertEqual(result['artifact_id'], aid)
        self.assertFalse(result['following_operation_returned'])
        self.assertEqual(self.store.snapshot(self.wid), before)
        self.store.add_artifact(self.wid, 'unrelated return', 'tool_reading', b'{}',
            {'job_id': self.jid, 'call_id': 'other'}, bump=False)
        self.assertFalse(view(self.store, self.wid, self.store.snapshot(self.wid))['following_operation_returned'])
        self.store.add_artifact(self.wid, 'actual matching return', 'tool_reading', b'{}',
            {'job_id': self.jid, 'call_id': 'first'}, bump=False)
        self.assertTrue(view(self.store, self.wid, self.store.snapshot(self.wid))['following_operation_returned'])

    def test_other_job_and_old_revision_are_not_current_research_progress(self):
        record_notes(self.store, self.wid, 1, 'other-job', self.notes, call_id='other')
        self.assertIsNone(view(self.store, self.wid, self.store.snapshot(self.wid)))
        record_notes(self.store, self.wid, 1, self.jid, self.notes, call_id='first')
        self.store.command(self.wid, 1, 'new-condition',
                           {'kind': 'correction', 'text': 'Different tissue.', 'synthetic': True})
        self.assertIsNone(view(self.store, self.wid, self.store.snapshot(self.wid)))

    def test_tampered_notes_do_not_become_a_valid_display(self):
        aid = record_notes(self.store, self.wid, 1, self.jid, self.notes, call_id='first')
        with self.store.connect(True) as db:
            db.execute('UPDATE artifacts SET content=? WHERE id=?', (b'{}', aid))
        result = view(self.store, self.wid, self.store.snapshot(self.wid))
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('notes', result)


if __name__ == '__main__': unittest.main()
