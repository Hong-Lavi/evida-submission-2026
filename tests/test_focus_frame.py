"""Run actual patched frame-selection call sites with synthetic store metadata."""
import sys
sys.dont_write_bytecode = True
import ast
import copy
import importlib.util
from pathlib import Path
import types
import unittest

B = Path(__file__).resolve().parents[1]
P = B / 'evida'
spec = importlib.util.spec_from_file_location('frame318', P / 'frame_context.py')
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
pkg = types.ModuleType('focus318'); pkg.__path__ = [str(P)]; sys.modules[pkg.__name__] = pkg
intent = types.ModuleType('focus318.intent_dependencies')
intent.model_view = lambda store, wid, state: {'question_reassessment_required': store.changed}
sys.modules[intent.__name__] = intent


def methods():
    tree = ast.parse((P / 'runner.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Runner')
    focus = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'focus_readings'))
    model = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'model_context')
    # Execute the real model_context intent/frame statements, not a duplicated rule.
    selected = [copy.deepcopy(n) for n in model.body if
        (isinstance(n, ast.ImportFrom) and n.module == 'intent_dependencies') or
        (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in
         ('state', 'intent_context', 'frame') for t in n.targets))]
    scaffold = ast.parse('def context_frame(self, wid, rev):\n    pass\n').body[0]
    scaffold.body = selected + [ast.Return(value=ast.Name(id='frame', ctx=ast.Load()))]
    mod = ast.Module(body=[focus, scaffold], type_ignores=[]); ast.fix_missing_locations(mod)
    env = {'__package__': 'focus318', 'current_research_frame': f.current_research_frame}
    exec(compile(mod, '<actual-runner-focus-and-context>', 'exec'), env)
    return env['focus_readings'], env['context_frame']


class Store:
    def __init__(self, based_rev, changed=False):
        self.changed = changed; self.events = []
        self.state = {'rev': 8, 'events': [{'kind': 'work_framed', 'body': {
            'based_rev': based_rev, 'current_question': 'synthetic question'}}],
            'artifacts': [{'id': 'reading', 'kind': 'tool_reading', 'meta': {'function': 'inspect_artifact'}}]}
    def snapshot(self, wid): return self.state
    def connect(self, write=False): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, statement, args):
        assert statement == 'SELECT rev FROM workspaces WHERE id=?'
        return self
    def fetchone(self): return (self.state['rev'],)
    def event(self, db, wid, kind, body): self.events.append((kind, body))


class SharedFrameTests(unittest.TestCase):
    def setUp(self): self.focus, self.context = methods()
    def runner(self, rev, changed=False): return types.SimpleNamespace(store=Store(rev, changed))
    def test_current_frame_is_shared_and_accepted(self):
        runner = self.runner(8)
        frame = self.context(runner, 'w', 8)
        out = self.focus(runner, 'w', 8, 'j', {'reading_ids': ['reading']})
        self.assertEqual(out['status'], 'applied')
        self.assertEqual(out['current_question'], frame['current_question'])
        self.assertNotIn('carried_from_rev', frame)
    def test_valid_carried_frame_pins_existing_reading_without_reframing(self):
        runner = self.runner(7)
        frame = self.context(runner, 'w', 8)
        self.assertEqual((frame['carried_from_rev'], frame['current_rev']), (7, 8))
        out = self.focus(runner, 'w', 8, 'j', {'reading_ids': ['reading']})
        self.assertEqual(out['current_question'], frame['current_question'])
        self.assertEqual(runner.store.events, [('reading_focus_set', {
            'based_rev': 8, 'job_id': 'j', 'current_question': frame['current_question'],
            'reading_ids': ['reading'], 'existing_reading_ids': ['reading']})])
        self.assertEqual(len(runner.store.state['events']), 1)
    def test_changed_intent_does_not_carry_or_allow_focus(self):
        runner = self.runner(7, changed=True)
        self.assertIsNone(self.context(runner, 'w', 8))
        with self.assertRaisesRegex(ValueError, 'frame_work'):
            self.focus(runner, 'w', 8, 'j', {'reading_ids': ['reading']})
        self.assertEqual(runner.store.events, [])
    def test_wrong_reading_still_rejected_under_valid_carried_frame(self):
        runner = self.runner(7)
        self.assertIsNotNone(self.context(runner, 'w', 8))
        with self.assertRaisesRegex(ValueError, '실제 원문 전달본'):
            self.focus(runner, 'w', 8, 'j', {'reading_ids': ['wrong']})
        self.assertEqual(runner.store.events, [])


if __name__ == '__main__': unittest.main()
