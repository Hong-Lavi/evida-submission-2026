"""Actual runner requests with a synthetic transport; no model or network calls.

The triggering real fresh-workflow result W004 claimed that only frame_work was
available, although its second recorded request exposed 74 functions with auto
selection. This fixture reproduces that first/second request transition without
bundling the source database or pretending to reproduce the model's reasoning.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evida import runner as runner_module
from evida.gateway import Gateway
from evida.runner import Runner
from evida.store import Store
from planner_fixtures import current_frame, current_final

ROOT = Path(__file__).resolve().parents[1]


def proposal(rev):
    return {"based_on_state_rev": rev, "intent_records": [], "action": "defer",
            "recommendation": "synthetic transport fixture", "reason": "No scientific result",
            "evidence_refs": [], "alternatives": [], "changed": [], "preserved": [],
            "unknowns": [], "next_actions": [], "questions": [],
            "research_loop": {"hypotheses": [], "next_checks": [], "revision_rationale": "fixture"}}


def current_call(payload):
    contexts = []
    for item in payload['input']:
        if item.get('role') != 'user' or not isinstance(item.get('content'), str):
            continue
        try:
            value = json.loads(item['content'])
        except json.JSONDecodeError:
            continue
        if 'CURRENT_CALL' in value:
            contexts.append(value['CURRENT_CALL'])
    if len(contexts) != 1:
        raise AssertionError(f'Expected one current-call context, found {len(contexts)}')
    return contexts[0]


class CurrentCallToolsTests(unittest.TestCase):
    def exercise(self, synthesis_only=False, exposed_names=None, research_rounds=None):
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'synthetic.sqlite3')
            wid = store.create('Synthetic current-call transition')['id']

            def transport(request):
                calls.append(request)
                if len(calls) == 1:
                    arguments = {'intent_records': [], 'current_question': 'Synthetic transition',
                                 'task_brief': [], 'questions': [], 'hypotheses': []}
                    arguments = current_frame(store, wid, arguments)
                    output = [{'type': 'function_call', 'name': 'frame_work',
                               'arguments': json.dumps(arguments), 'call_id': 'fixture-frame',
                               'id': 'fixture-frame'}]
                else:
                    output = [{'type': 'message', 'role': 'assistant', 'content': [
                        {'type': 'output_text', 'text': json.dumps(current_final(store, wid, proposal(1)))}]}]
                return {'id': f'fixture-{len(calls)}', 'model': 'gpt-5.6-terra',
                        'status': 'completed', 'usage': {'input_tokens': 0, 'output_tokens': 0},
                        'output': output}, {}

            gateway = Gateway(json.loads((ROOT / 'configs/api_policy.json').read_text()),
                              True, transport=transport)
            runner = object.__new__(Runner)
            runner.root, runner.store, runner.gateway = ROOT, store, gateway
            runner.prompt = (ROOT / 'configs/planner.md').read_text()
            functions = runner_module.model_functions()
            if exposed_names is not None:
                functions = [f for f in functions if f['name'] in exposed_names]
            jid = store.enqueue(wid, 1, 'planner', {'synthesis_only': synthesis_only})
            with patch.object(runner_module, 'model_functions', return_value=functions), patch.object(
                    runner_module, 'RESEARCH_ROUNDS', research_rounds or runner_module.RESEARCH_ROUNDS):
                runner.run_planner(jid)
            job = next(j for j in store.snapshot(wid)['jobs'] if j['id'] == jid)
            self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(len(calls), 2)
        return calls

    def test_frame_then_research_reports_the_actual_second_request_tools(self):
        first, second = self.exercise()
        framing, research = current_call(first), current_call(second)
        self.assertEqual(framing['stage'], 'frame')
        self.assertEqual(framing['callable_function_names'], ['frame_work'])
        self.assertEqual(first['tool_choice'], {'type': 'function', 'name': 'frame_work'})
        self.assertEqual(research['stage'], 'research')
        self.assertEqual(second['tool_choice'], 'auto')
        self.assertEqual(research['callable_function_names'], [f['name'] for f in second['tools']])
        self.assertIn('search_literature', research['callable_function_names'])
        self.assertIn('read_open_article', research['callable_function_names'])
        self.assertEqual(research['model_response_number'], 2)
        self.assertEqual(research['maximum_responses_remaining_including_current'],
                         runner_module.RESEARCH_ROUNDS + runner_module.MAXIMUM_DECISION_CORRECTIONS - 1)
        self.assertTrue(any(i.get('type') == 'function_call_output' for i in second['input']))

    def test_synthesis_only_reports_no_callable_tools_despite_declared_schemas(self):
        first, second = self.exercise(synthesis_only=True)
        self.assertEqual(current_call(first)['callable_function_names'], ['frame_work'])
        final = current_call(second)
        self.assertTrue(second['tools'])
        self.assertEqual(second['tool_choice'], 'none')
        self.assertEqual(final['stage'], 'synthesis')
        self.assertEqual(final['callable_function_names'], [])
        self.assertEqual(final['research_responses_remaining_including_current'], 0)

    def test_filtered_menu_is_not_expanded_by_the_context(self):
        names = {'frame_work', 'search_literature'}
        first, second = self.exercise(exposed_names=names)
        self.assertEqual(set(current_call(second)['callable_function_names']), names)
        self.assertEqual(set(f['name'] for f in second['tools']), names)
        self.assertNotIn('read_open_article', current_call(second)['callable_function_names'])

    def test_post_research_guard_is_reflected_even_if_schemas_remain(self):
        first, second = self.exercise(research_rounds=1)
        final = current_call(second)
        self.assertEqual(final['stage'], 'decision_correction')
        self.assertEqual(final['callable_function_names'], [])
        self.assertEqual(final['research_responses_remaining_including_current'], 0)
        self.assertEqual(final['maximum_responses_remaining_including_current'],
                         runner_module.MAXIMUM_DECISION_CORRECTIONS)


if __name__ == '__main__':
    unittest.main()
