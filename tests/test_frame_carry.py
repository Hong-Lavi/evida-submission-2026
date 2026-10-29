"""A continuation must not force the research to start over.

Every command raises rev, including a researcher's or coordinator's "carry on", and frames were
bound to the rev they were made under. So each continuation left the new job with no frame, the
first research tool was refused until the model reframed, and one live case framed five times
without ever reaching a review. The latest decomposition is now carried forward and marked, and
the model decides whether the new input actually changed the question.
"""
import json
import tempfile
import unittest
from pathlib import Path

from evida.runner import Runner
from evida.store import Store


def frame_body(question='폐 기능 저하를 늦출 기전을 고른다'):
    return {'current_question': question, 'intent_records': [], 'task_brief': [],
            'questions': [], 'hypotheses': []}


class FrameCarryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'carry.sqlite3')
        self.wid = self.store.create('frame carry')['id']
        self.runner = object.__new__(Runner)
        self.runner.store = self.store
        self.runner.frame(self.wid, 1, frame_body())

    def tearDown(self):
        self.temp.cleanup()

    def frame_at(self, rev):
        # The same selection model_context makes, read from the store the way it reads it.
        state = self.store.snapshot(self.wid)
        frame = next((e['body'] for e in reversed(state['events'])
                      if e['kind'] == 'work_framed' and e['body']['based_rev'] == rev), None)
        if frame is None:
            earlier = next((e['body'] for e in reversed(state['events'])
                            if e['kind'] == 'work_framed'), None)
            if earlier is not None:
                frame = {**earlier, 'carried_from_rev': earlier['based_rev'], 'current_rev': rev}
        return frame

    def test_a_later_rev_sees_the_earlier_decomposition_marked_as_carried(self):
        carried = self.frame_at(5)
        self.assertEqual(carried['current_question'], '폐 기능 저하를 늦출 기전을 고른다')
        self.assertEqual(carried['carried_from_rev'], 1, 'the reader can tell it was made earlier')
        self.assertEqual(carried['current_rev'], 5)

    def test_the_frame_of_the_current_rev_wins_and_is_not_marked(self):
        # Advance the real state: a frame cannot invent a future revision.
        for rev in range(1, 5):
            self.store.command(self.wid, rev, f'continue-{rev}',
                               {'kind': 'message', 'text': 'Continue the synthetic fixture.'})
        self.runner.frame(self.wid, 5, frame_body('새 질문'))
        current = self.frame_at(5)
        self.assertEqual(current['current_question'], '새 질문')
        self.assertNotIn('carried_from_rev', current)

    def test_the_runner_and_this_selection_agree(self):
        # Guards against the test's copy drifting from the runner's own code.
        source = Path(__file__).resolve().parents[1].joinpath('evida/runner.py').read_text()
        self.assertIn('"carried_from_rev": earlier["based_rev"]', source)
        self.assertIn('carried = (not job["request"].get("synthesis_only", False)', source)

    def test_the_prompt_says_to_keep_a_carried_frame_unless_the_question_changed(self):
        prompt = Path(__file__).resolve().parents[1].joinpath('configs/planner.md').read_text()
        self.assertIn('carried_from_rev', prompt)
        self.assertIn('frame_work를 다시 부르지 말라', prompt)
        self.assertIn('질문을 실제로 바꿨을 때만 frame_work로 갱신한다', prompt)


if __name__ == '__main__':
    unittest.main()
