"""Synthetic regression tests; no provider, product DB, or benchmark data."""
import ast
import copy
import importlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
from evida import reassessment as r
from evida import provenance_repair as repair
from evida import private_supervision as policy



class FakeStore:
    def __init__(self, artifact=None):
        self.value = artifact
        self.saved = []
    def artifact(self, wid, aid):
        return self.value
    def add_artifact(self, *args, **kwargs):
        self.saved.append((args, kwargs))
        return 'retained-' + str(len(self.saved))


def rejected_branch():
    """Execute the actual patched Runner rejection handler, including artifact retention."""
    tree = ast.parse((ROOT / 'evida/runner.py').read_text())
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)
                   and 'DECISION_REJECTED.format' in ast.unparse(n)
                   and 'rejection_id' in ast.unparse(n))
    wrapped = ast.parse('def run_case(exc, response_limit, corrections, synthesis_only=False):\n'
                        '    conversation = []\n'
                        '    job = {"request": {"synthesis_only": synthesis_only}}\n'
                        '    for _ in range(1):\n'
                        '        try:\n'
                        '            raise exc\n'
                        '        except ValueError:\n'
                        '            pass\n'
                        '    return corrections, conversation\n')
    wrapped.body[0].body[2].body[0].handlers = [copy.deepcopy(handler)]
    ast.fix_missing_locations(wrapped)
    store = FakeStore()
    runner = types.SimpleNamespace(store=store, model_context=lambda *a, **k: [])
    import jsonschema
    env = dict(self=runner, jsonschema=jsonschema, MAXIMUM_DECISION_CORRECTIONS=2,
               schema_feedback=str, correction_reason=lambda e, **k: str(e),
               reasoning_context={}, text='{}', wid='synthetic-w', rev=8, jid='synthetic-j',
               protocol_id='synthetic-p', result={'output': []}, framed=True,
               dump=json.dumps, next_model_context=lambda context, output, tools: context,
               DECISION_REJECTED='GENERIC_TOOL_FORBIDDEN:{reason}',
               repair_instruction=repair.repair_instruction)
    exec(compile(wrapped, '<actual-runner-handler>', 'exec'), env)
    return env['run_case'], store


class ProvenanceGuards(unittest.TestCase):
    def setUp(self):
        self.h = {'id': 'H', 'statement': 'synthetic unchanged proposition'}
        self.value = dict(snapshot_sha256='current', subject='hypothesis:H', outcome='changed',
                          content_hash=r.digest(self.h), trace={'upstream_reviews': []})
        self.artifact = dict(kind='reassessment_draft', meta={'job_id': 'job'},
                             sha256='synthetic-sha', content=json.dumps(self.value))
        self.received = dict(snapshot_sha256='current', views={'draft:d': {'value': {'artifact_id': 'd'}}})
        self.stack = [patch.object(r, 'snapshot', return_value={'snapshot_sha256': 'current'}),
                      patch.object(r, 'assessments', return_value={}),
                      patch.object(r, 'prior_bundle', return_value=None),
                      patch.object(r, 'build_plan', return_value={'retained': []})]
        for p in self.stack: p.start(); self.addCleanup(p.stop)
    def call(self):
        self.artifact['content'] = json.dumps(self.value)
        return r.prepare_bundle(FakeStore(self.artifact), 'w',
            {'research_loop': {'hypotheses': [self.h]}, 'intent_records': []}, None,
            ['d'], self.received, 'job')
    def test_fresh_draft_is_validated_normally(self):
        self.assertEqual(self.call()['value']['reviews']['hypothesis:H']['draft_id'], 'd')
    def test_stale_draft_is_typed_and_never_accepted(self):
        self.value['snapshot_sha256'] = 'old'
        with self.assertRaises(repair.StaleReassessmentContextError) as got: self.call()
        self.assertEqual(got.exception.current_snapshot, 'current')
        self.assertEqual(got.exception.previous_snapshot, 'old')
        self.assertEqual(got.exception.draft_id, 'd')
    def test_stale_received_context_is_typed(self):
        self.received['snapshot_sha256'] = 'old'
        with self.assertRaises(repair.StaleReassessmentContextError): self.call()
    def test_wrong_job_is_not_promoted_to_repair(self):
        self.artifact['meta']['job_id'] = 'other'
        self.value['snapshot_sha256'] = 'old'
        with self.assertRaises(ValueError) as got: self.call()
        self.assertNotIsInstance(got.exception, repair.StaleReassessmentContextError)
    def test_wrong_kind_and_missing_delivery_still_rejected(self):
        self.artifact['kind'] = 'tool_reading'
        with self.assertRaises(ValueError): self.call()
        self.artifact['kind'] = 'reassessment_draft'; self.received['views'] = {}
        with self.assertRaises(ValueError): self.call()
    def test_changed_final_content_still_rejected(self):
        self.h['statement'] = 'different final proposition'
        with self.assertRaisesRegex(ValueError, '최종 가설'): self.call()
    def test_wrong_upstream_binding_still_rejected(self):
        self.value['trace']['upstream_reviews'] = [{'subject': 'hypothesis:U', 'artifact_id': 'u', 'sha256': 'x'}]
        with self.assertRaisesRegex(ValueError, '최종 상위 판단'): self.call()


class RunnerRecovery(unittest.TestCase):
    def stale(self):
        return repair.StaleReassessmentContextError('stale', current_snapshot='new', previous_snapshot='old', draft_id='d')
    def test_actual_handler_retains_both_artifacts_and_counter(self):
        run, store = rejected_branch()
        count, context = run(self.stale(), None, 3)
        self.assertEqual(count, 4)
        self.assertEqual(len(store.saved), 2)
        self.assertEqual([x[0][2] for x in store.saved], ['decision_validation_error', 'decision_proposal'])
        self.assertIn('REASSESSMENT_CONTEXT_REPAIR=', context[-1]['content'])
        self.assertNotIn('GENERIC_TOOL_FORBIDDEN', context[-1]['content'])
        self.assertFalse(policy.response_state(12, None, count)['synthesize'])
        self.assertFalse(policy.response_state(12, None, count)['correcting'])
    def test_finite_handler_and_limit_unchanged(self):
        run, store = rejected_branch()
        count, context = run(self.stale(), 16, 0)
        self.assertEqual(count, 1)
        self.assertTrue(context[-1]['content'].startswith('GENERIC_TOOL_FORBIDDEN'))
        self.assertTrue(policy.response_state(12, 16, count)['synthesize'])
        with self.assertRaises(repair.StaleReassessmentContextError): run(self.stale(), 16, 2)
        self.assertEqual(len(store.saved), 2)
    def test_generic_or_synthesis_only_never_get_repair(self):
        run, _ = rejected_branch()
        for exc, synthesis in [(ValueError('stale'), False), (self.stale(), True)]:
            _, context = run(exc, None, 0, synthesis)
            self.assertTrue(context[-1]['content'].startswith('GENERIC_TOOL_FORBIDDEN'))
    def test_string_lookalike_cannot_enable_repair(self):
        self.assertIsNone(repair.repair_instruction(ValueError('stale_reassessment_context'), None))


if __name__ == '__main__': unittest.main()
