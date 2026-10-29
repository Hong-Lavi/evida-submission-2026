import tempfile
from pathlib import Path
import unittest
from evida.runner import Runner
from evida.store import Store


class FramePreservation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'db.sqlite3')
        self.wid = self.store.create('frame preservation fixture')['id']
        self.runner = object.__new__(Runner)
        self.runner.store = self.store
        self.frame = {'current_question':'Which source condition accounts for this discrepancy?',
                      'intent_records':[], 'task_brief':[], 'questions':[], 'hypotheses':[]}
        self.runner.frame(self.wid, 1, self.frame)

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_model_frame_cannot_hide_existing_research_question(self):
        before = self.store.snapshot(self.wid)
        for text in ['', '  \n\t']:
            with self.assertRaisesRegex(ValueError, '현재 연구 질문이 비어'):
                self.runner.frame(self.wid, 1, {**self.frame, 'current_question':text})
        self.assertEqual(self.store.snapshot(self.wid), before)

    def test_reframing_without_hypotheses_is_still_allowed(self):
        next_frame = {**self.frame, 'current_question':'Which missing input should the researcher clarify?'}
        self.runner.frame(self.wid, 1, next_frame)
        events = [e for e in self.store.snapshot(self.wid)['events'] if e['kind']=='work_framed']
        self.assertEqual(events[-1]['body']['current_question'], next_frame['current_question'])
        self.assertEqual(events[-1]['body']['hypotheses'], [])


if __name__ == '__main__':
    unittest.main()
