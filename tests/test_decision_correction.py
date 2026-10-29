"""A decision refused by our own validation gets one chance to be corrected, not the bin.

Two real runs on 2026-10-01 read 88 and 87 sources over roughly twenty model rounds and published
nothing. One gave two options the same priority inside one comparison group; the other pointed a
scope target at a part its hypothesis did not have. Both are genuine inconsistencies and both were
rightly refused - but refusing ended the job, and everything the run had read went unpublished
with the decision, because the assessments that fill stage 2 travel inside the decision bundle.

The distinction this rests on: the provider call SUCCEEDED. It returned a well-formed response
that our cross-field checks then refused. Showing the model what we refused and asking for a
corrected decision is a new request about new information, not a retry of a failed call - the
thing this product does not do, because a retry can bill twice for one answer.

So it is bounded, the refused version is preserved, and when the corrections run out the job
fails with the reason it would have failed with anyway.
"""
from __future__ import annotations

import unittest
import ast
import copy
import inspect
import textwrap

from evida import runner


def planner_loop_indices(first=0):
    """Evaluate the actual Runner loop expression with a finite policy, no model call."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(runner.Runner.run_planner)))
    loop = next(n for n in ast.walk(tree) if isinstance(n, ast.For)
                and isinstance(n.target, ast.Name) and n.target.id == 'round_index')
    expression = ast.fix_missing_locations(ast.Expression(copy.deepcopy(loop.iter)))
    return eval(compile(expression, '<actual Runner finite iterator>', 'eval'), vars(runner),
                {'first_round': first, 'response_limit': runner.RESEARCH_ROUNDS})


def correction_guard():
    """Extract the actual final-validation guard rather than matching its spelling."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(runner.Runner.run_planner)))
    for handler in ast.walk(tree):
        if not isinstance(handler, ast.ExceptHandler) or handler.name != 'rejection':
            continue
        for index, node in enumerate(handler.body):
            if not isinstance(node, ast.If):
                continue
            comparisons = [x for x in ast.walk(node.test) if isinstance(x, ast.Compare)]
            if any(isinstance(x.left, ast.Name) and x.left.id == 'corrections'
                   and any(isinstance(op, ast.GtE) for op in x.ops) for x in comparisons):
                return handler, index, node
    raise AssertionError('No final-validation correction guard found')


def run_actual_correction_guard(limit, corrections, original):
    """Run the extracted guard inside an active validation-exception handler."""
    _, _, node = correction_guard()
    program = ast.Module(body=[ast.Try(
        body=[ast.Raise(exc=ast.Name(id='original', ctx=ast.Load()), cause=None)],
        handlers=[ast.ExceptHandler(type=ast.Name(id='ValueError', ctx=ast.Load()),
                                   name='rejection', body=[copy.deepcopy(node)])],
        orelse=[], finalbody=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(program), '<actual Runner correction guard>', 'exec'),
         {'ValueError': ValueError, 'original': original, 'response_limit': limit,
          'corrections': corrections, 'MAXIMUM_DECISION_CORRECTIONS': runner.MAXIMUM_DECISION_CORRECTIONS})


class BoundTests(unittest.TestCase):
    def test_a_correction_budget_exists_and_is_small(self):
        self.assertTrue(1 <= runner.MAXIMUM_DECISION_CORRECTIONS <= 3,
                        'an unbounded correction loop is a retry loop wearing another name')

    def test_the_message_tells_the_model_what_was_refused(self):
        filled = runner.DECISION_REJECTED.format(reason='우선순위가 중복됐습니다')
        self.assertIn('우선순위가 중복됐습니다', filled)

    def test_the_message_asks_for_a_correction_not_a_fresh_investigation(self):
        filled = runner.DECISION_REJECTED.format(reason='x')
        self.assertIn('새로 조회하지 말고', filled,
                      'a correction round that re-runs retrieval spends the budget twice')

    def test_the_message_says_the_reading_is_still_there(self):
        # Otherwise the model may believe it has to gather the evidence again.
        self.assertIn('그대로 남아', runner.DECISION_REJECTED.format(reason='x'))


class SourceTests(unittest.TestCase):
    """The loop is long and stateful; these pin the parts of it this change depends on."""

    def setUp(self):
        import inspect
        self.source = inspect.getsource(runner.Runner.run_planner)

    def test_only_validation_errors_are_corrected(self):
        # A GatewayError must keep falling through to its own handler: a provider failure is not
        # something the model can fix by rewriting its answer.
        self.assertIn('except (ValueError, jsonschema.ValidationError) as rejection:', self.source)
        self.assertNotIn('except Exception as rejection', self.source)

    def test_the_refused_decision_is_preserved(self):
        self.assertIn('rejected_because', self.source,
                      'the refused version has to be inspectable, not merely described')

    def test_the_budget_is_checked_before_another_round_is_spent(self):
        handler, index, _ = correction_guard()
        increments = [i for i, n in enumerate(handler.body) if isinstance(n, ast.AugAssign)
                      and isinstance(n.target, ast.Name) and n.target.id == 'corrections']
        self.assertTrue(increments, 'the guarded correction must still be recorded')
        self.assertLess(index, increments[0], 'guard before spending another correction')
        run_actual_correction_guard(runner.RESEARCH_ROUNDS,
                                    runner.MAXIMUM_DECISION_CORRECTIONS - 1, ValueError('original'))
        with self.assertRaises(ValueError):
            run_actual_correction_guard(runner.RESEARCH_ROUNDS,
                                        runner.MAXIMUM_DECISION_CORRECTIONS, ValueError('original'))

    def test_the_loop_is_still_bounded(self):
        # The actual finite iterator, including correction rounds, must exhaust.
        expected = list(range(runner.RESEARCH_ROUNDS + runner.MAXIMUM_DECISION_CORRECTIONS))
        self.assertEqual(list(planner_loop_indices()), expected)
        tail = planner_loop_indices(first=runner.RESEARCH_ROUNDS)
        self.assertEqual(list(tail), expected[runner.RESEARCH_ROUNDS:])
        with self.assertRaises(StopIteration):
            next(tail)

    def test_the_original_reason_is_what_finally_fails(self):
        # `raise` with no argument, so the job records the validation error rather than a
        # secondary one about having run out of corrections.
        original = ValueError('the original validation failure')
        with self.assertRaises(ValueError) as caught:
            run_actual_correction_guard(runner.RESEARCH_ROUNDS,
                                        runner.MAXIMUM_DECISION_CORRECTIONS, original)
        self.assertIs(caught.exception, original, 'preserve the exact original validation error')
        # The explicit None mode has a different policy; this guard must not impose a finite cap.
        run_actual_correction_guard(None, runner.MAXIMUM_DECISION_CORRECTIONS + 3, original)



class BudgetBoundaryTests(unittest.TestCase):
    """The first run with the correction path never used it.

    pde4b, 2026-10-01: sixteen model rounds, sixteen decision proposals, zero refusal records, and
    the job failed on the same validation error the correction was written for. The model spends
    the whole research budget and returns its decision on the last round, so a correction that
    needs a round inside that budget never gets one.

    A correction is not research. It rewrites a field of an answer already written, so it runs
    past the budget - and must not be able to start new retrieval there.
    """

    def setUp(self):
        import inspect
        self.source = inspect.getsource(runner.Runner.run_planner)

    def test_the_loop_reaches_past_the_research_budget(self):
        indices = list(planner_loop_indices())
        self.assertEqual(indices[runner.RESEARCH_ROUNDS:],
                         list(range(runner.RESEARCH_ROUNDS,
                                    runner.RESEARCH_ROUNDS + runner.MAXIMUM_DECISION_CORRECTIONS)))
        self.assertEqual(len(indices), runner.RESEARCH_ROUNDS + runner.MAXIMUM_DECISION_CORRECTIONS)

    def test_the_correction_guard_no_longer_depends_on_rounds_left(self):
        self.assertNotIn('round_index + 1 >= 16', self.source)
        self.assertNotIn('round_index + 1 >= RESEARCH_ROUNDS', self.source)

    def test_a_correction_round_may_not_call_tools(self):
        # The same guard now covers early rejected decisions and terminal
        # corrections; native request/transport coverage is in the reading tests.
        self.assertIn('if calls and correcting:', self.source,
                      'a correction must not start fresh retrieval at any round')

    def test_the_research_budget_is_still_sixteen(self):
        self.assertEqual(runner.RESEARCH_ROUNDS, 16)

    def test_the_extra_rounds_are_exactly_the_correction_budget(self):
        # Two numbers that must move together; a stray constant here would silently buy the model
        # more research rounds.
        self.assertEqual(runner.MAXIMUM_DECISION_CORRECTIONS, 2)


class KnownRefusalTests(unittest.TestCase):
    """Four real runs produced three different refusals. The message names all three.

    duplicate priority inside a comparison group (IPF), a scope target pointing at a part its
    hypothesis does not have (preeclampsia, pde4b), and an assessment citing an artifact this
    research never made (the preeclampsia revision round). The model gets one round and cannot
    ask what we meant, so a generic "please fix it" wastes the round.
    """

    def test_it_names_the_duplicate_priority_fix(self):
        self.assertIn('comparison_group', runner.DECISION_REJECTED)
        self.assertIn('null', runner.DECISION_REJECTED)

    def test_it_names_the_missing_scope_part_fix(self):
        self.assertIn('assessment_scope', runner.DECISION_REJECTED)

    def test_it_names_the_dangling_source_fix(self):
        self.assertIn('support_source_ids', runner.DECISION_REJECTED)
        self.assertIn('challenge_source_ids', runner.DECISION_REJECTED)

    def test_it_says_calling_a_tool_ends_the_job(self):
        # True since corrections run past the research budget, and the model should know.
        self.assertIn('도구를 호출하면', runner.DECISION_REJECTED)

    def test_it_asks_for_a_format_fix_not_a_new_judgement(self):
        self.assertIn('과학적 내용은 바꾸지 마세요', runner.DECISION_REJECTED)

if __name__ == '__main__':
    unittest.main()
