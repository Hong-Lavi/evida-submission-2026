"""Scope transport and historical references; synthetic judgments, not science validation."""
import copy
import tempfile
import unittest
from pathlib import Path

from evida.model_context import decision_history
from evida.research_loop import validate_loop, validate_feedback
from evida.store import Store, dump
from test_research_loop import seed


def scoped(proposal):
    p = copy.deepcopy(proposal)
    h = p['research_loop']['hypotheses'][0]
    h['assessment_scope'] = {'parts': [
        {'id': 'identity', 'statement': 'Synthetic branch: sample identity differs.',
         'expected_observation': 'Different sample identifiers.', 'assessment': 'challenged',
         'rationale': 'Synthetic correction applies here only.', 'evidence': copy.deepcopy(h['evidence'])},
        {'id': 'stage', 'statement': 'Synthetic branch: measurement stage differs.',
         'expected_observation': 'Different measurement records.', 'assessment': 'inconclusive',
         'rationale': 'Stage records are missing.', 'evidence': []}],
        'synthesis': 'Synthetic test: one challenged branch does not decide the whole.'}
    p['research_loop']['next_checks'][0]['scope_targets'] = [{'hypothesis_id': h['id'], 'part_ids': ['stage']}]
    return p


class AssessmentScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'state.db')
        self.wid, self.aid, self.pid, self.original = seed(self.store)
        self.p = scoped(self.original)

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, p):
        validate_loop(p['research_loop'], self.store.snapshot(self.wid))
        aid = self.store.add_artifact(self.wid, 'Synthetic scoped judgment', 'decision_proposal', dump(p).encode(), {}, bump=False)
        self.assertTrue(self.store.publish_decision(self.wid, p['based_on_state_rev'], p, aid))
        return aid

    def test_partial_feedback_preserves_old_bytes_and_never_aggregates_assessments(self):
        old = self.store.artifact(self.wid, self.pid)['content']
        current = self.publish(self.p)
        context = {'decision_id': current, 'check_id': None, 'hypothesis_ids': ['h1'],
                   'comparison': 'different', 'scope_targets': [{'hypothesis_id': 'h1', 'part_ids': ['identity']}]}
        self.store.command(self.wid, 1, 'partial', {'kind': 'correction', 'text': 'Synthetic identity correction',
            'synthetic': True, 'research_context': context})
        state = self.store.snapshot(self.wid)
        self.assertEqual(state['decision'], self.p)
        self.assertEqual(state['decision']['research_loop']['hypotheses'][0]['assessment'], 'proposed')
        self.assertEqual(state['events'][-1]['body']['research_context'], context)
        self.assertEqual(state['review_status'], 'needs_review')
        self.assertEqual(self.store.artifact(self.wid, self.pid)['content'], old)
        for field in ('statement', 'expected_observation'):
            self.assertEqual(self.p['research_loop']['hypotheses'][0][field], self.original['research_loop']['hypotheses'][0][field])

    def test_wrong_or_duplicate_part_and_missing_evidence_are_rejected(self):
        def duplicate(p):
            p['hypotheses'][0]['assessment_scope']['parts'][1]['id'] = 'identity'
        def missing_evidence(p):
            p['hypotheses'][0]['assessment_scope']['parts'][0]['evidence'][0]['source_id'] = 'missing'
        def wrong_part(p):
            p['next_checks'][0]['scope_targets'][0]['part_ids'] = ['unknown']
        def wrong_hypothesis(p):
            p['next_checks'][0]['scope_targets'][0]['hypothesis_id'] = 'another'
        def repeated_part(p):
            p['next_checks'][0]['scope_targets'][0]['part_ids'] = ['stage', 'stage']
        for mutate in (duplicate, missing_evidence, wrong_part, wrong_hypothesis, repeated_part):
            with self.subTest(mutate=mutate.__name__):
                loop = copy.deepcopy(self.p['research_loop']); mutate(loop)
                with self.assertRaises(ValueError): validate_loop(loop, self.store.snapshot(self.wid))

    def test_check_feedback_cannot_silently_lose_or_change_its_scope(self):
        context = {'decision_id': self.pid, 'check_id': 'c1', 'hypothesis_ids': ['h1'], 'comparison': 'unclear'}
        validate_feedback(context, self.original)  # Old records need no migration.
        with self.assertRaises(ValueError): validate_feedback(context, self.p)
        context['scope_targets'] = [{'hypothesis_id': 'h1', 'part_ids': ['identity']}]
        with self.assertRaises(ValueError): validate_feedback(context, self.p)
        context['scope_targets'][0]['part_ids'] = ['stage']
        validate_feedback(context, self.p)

    def test_history_retains_parts_and_feedback_resolves_the_referenced_decision(self):
        scoped_id = self.publish(self.p)
        latest = copy.deepcopy(self.original)
        self.publish(latest)  # Same hypothesis ID now has no parts.
        context = {'decision_id': scoped_id, 'check_id': None, 'hypothesis_ids': ['h1'],
                   'comparison': 'unclear', 'scope_targets': [{'hypothesis_id': 'h1', 'part_ids': ['stage']}]}
        self.store.command(self.wid, 1, 'historical-scope', {'kind': 'observation', 'text': 'Synthetic older-part observation',
            'synthetic': True, 'research_context': context})
        state = self.store.snapshot(self.wid)
        history = decision_history(state['events'], lambda aid: self.store.artifact(self.wid, aid))
        indexed = history[-2]['hypotheses'][0]['assessment_scope']
        for part, original in zip(indexed['parts'], self.p['research_loop']['hypotheses'][0]['assessment_scope']['parts']):
            for key in ('id', 'statement', 'expected_observation', 'assessment'):
                self.assertEqual(part[key], original[key])
            self.assertNotIn('evidence', part)  # Retrieve full evidence by the preserved decision ID.
        self.assertEqual(indexed['synthesis'], self.p['research_loop']['hypotheses'][0]['assessment_scope']['synthesis'])
        self.assertNotIn('assessment_scope', history[-1]['hypotheses'][0])
        wrong = copy.deepcopy(context); wrong['decision_id'] = self.pid
        with self.assertRaises(ValueError):
            self.store.command(self.wid, 2, 'wrong-history', {'kind': 'observation', 'text': 'Synthetic', 'research_context': wrong})


if __name__ == '__main__': unittest.main()
