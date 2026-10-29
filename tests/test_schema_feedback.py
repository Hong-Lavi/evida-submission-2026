"""Structural rejection feedback and synthetic Runner transport; no model calls."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from evida import runner as runner_module
from evida.decision_preservation import DecisionPreservationError
from evida.gateway import Gateway
from evida.model_context import artifact_overview
from evida.runner import Runner
from evida.schema_feedback import MAX_SCHEMA_FEEDBACK_CHARS, schema_feedback
from evida.store import Store
from planner_fixtures import current_final, current_frame
from test_current_call_tools import proposal

ROOT = Path(__file__).resolve().parents[1]


def reject(instance, schema):
    try:
        jsonschema.validate(instance, schema)
    except jsonschema.ValidationError as exc:
        return exc
    raise AssertionError('Fixture must fail the unchanged validator')


class SchemaFeedbackTests(unittest.TestCase):
    def test_long_instance_does_not_displace_exact_escaped_pointer_and_type(self):
        value = {'a/b~c': [{'payload': 'PRIVATE-SCIENTIFIC-TEXT' * 1000}]}
        schema = {'properties': {'a/b~c': {'items': {'type': 'string'}}}}
        before = copy.deepcopy(value)
        error = reject(value, schema)
        text = schema_feedback(error)
        d = json.loads(text)['diagnostic']
        self.assertEqual(d['pointer'], '/a~1b~0c/0')
        self.assertEqual(d['expected_type'], 'string')
        self.assertEqual(d['actual_type'], 'object')
        self.assertNotIn('PRIVATE-SCIENTIFIC-TEXT', text)
        self.assertLessEqual(len(text), MAX_SCHEMA_FEEDBACK_CHARS)
        self.assertEqual(value, before)
        self.assertEqual(reject(value, schema).validator, 'type')

    def test_required_lists_only_absent_keys_and_distinguishes_present_null(self):
        error = reject({'present': None}, {'required': ['present', 'missing']})
        d = json.loads(schema_feedback(error))['diagnostic']
        self.assertEqual(d['pointer'], '')
        self.assertEqual(d['missing_required'], ['missing'])

    def test_alternative_branch_requirements_are_never_merged(self):
        for keyword, rule in [('anyOf', 'at_least_one_branch'),
                              ('oneOf', 'exactly_one_branch')]:
            schema = {keyword: [{'required': ['a']}, {'required': ['b']}]}
            d = json.loads(schema_feedback(reject({}, schema)))['diagnostic']
            self.assertEqual(d['alternatives_rule'], rule)
            self.assertNotIn('missing_required', d)
            self.assertEqual([b['errors'][0]['missing_required'] for b in d['branches']],
                             [['a'], ['b']])
            # Either branch alone is sufficient for both of these schemas.
            jsonschema.validate({'a': 1}, schema)
            jsonschema.validate({'b': 1}, schema)

    def test_nested_alternatives_keep_branch_boundaries(self):
        schema = {'anyOf': [{'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                            {'type': 'boolean'}]}
        d = json.loads(schema_feedback(reject([], schema)))['diagnostic']
        # The validate() best-match heuristic may select the inner rejection.
        self.assertEqual(d['alternatives_rule'], 'at_least_one_branch')
        self.assertIn('branches', d)
        self.assertNotIn('missing_required', d)
        self.assertLessEqual(len(schema_feedback(reject([], schema))), MAX_SCHEMA_FEEDBACK_CHARS)

    def test_oneof_multiple_matching_branches_does_not_invent_missing_keys(self):
        d = json.loads(schema_feedback(reject(1, {'oneOf': [{}, {'type': 'number'}]})))['diagnostic']
        self.assertEqual(d['alternatives_rule'], 'exactly_one_branch')
        self.assertNotIn('branches', d)
        self.assertNotIn('missing_required', d)

    def test_alternative_and_long_path_budgets_are_explicit_not_invalid_pointers(self):
        schema = {'anyOf': [{'required': [f'branch{i}']} for i in range(40)]}
        text = schema_feedback(reject({}, schema))
        self.assertLessEqual(len(text), MAX_SCHEMA_FEEDBACK_CHARS)
        self.assertTrue(json.loads(text)['diagnostic']['details_omitted'])
        name = 'x' * 4000
        d = json.loads(schema_feedback(reject({name: []}, {'properties': {name: {'type': 'string'}}})))['diagnostic']
        self.assertNotIn('pointer', d)
        self.assertTrue(d['pointer_omitted_due_to_budget'])

    def test_null_boolean_and_allowed_values_are_structural_only(self):
        for value, kind in [(None, 'null'), (True, 'boolean')]:
            d = json.loads(schema_feedback(reject(value, {'type': 'string'})))['diagnostic']
            self.assertEqual(d['actual_type'], kind)
        d = json.loads(schema_feedback(reject('wrong', {'enum': ['kept', 'unknown']})))['diagnostic']
        self.assertEqual(d['allowed_values'], ['kept', 'unknown'])

    def test_late_named_tool_branch_reports_its_bad_argument_without_accepting_it(self):
        branches = [{'type': 'object', 'properties': {
            'kind': {'enum': ['tool']}, 'name': {'enum': ['tool_' + str(i)]},
            'arguments': {'type': 'object', 'properties': {'query': {'type': 'string'}},
                          'required': ['query'], 'additionalProperties': False}},
            'required': ['kind', 'name', 'arguments'], 'additionalProperties': False}
            for i in range(180)]
        value = {'kind': 'tool', 'name': 'tool_179',
                 'arguments': {'query': 'PRIVATE-VALUE', 'research_notes': {'text': 'PRIVATE-VALUE'}}}
        schema = {'anyOf': branches}
        error = next(jsonschema.Draft202012Validator(schema).iter_errors(value))
        text = schema_feedback(error)
        d = json.loads(text)['diagnostic']
        self.assertEqual(d['branches'][0]['branch_index'], 179)
        self.assertEqual(d['branches'][0]['errors'][0]['unexpected_properties'], ['research_notes'])
        self.assertNotIn('PRIVATE-VALUE', text)
        self.assertLessEqual(len(text), MAX_SCHEMA_FEEDBACK_CHARS)
        self.assertTrue(list(jsonschema.Draft202012Validator(schema).iter_errors(value)))

    def test_additional_properties_respects_pattern_properties(self):
        schema = {'type': 'object', 'properties': {'known': {}},
                  'patternProperties': {'^allowed_': {}}, 'additionalProperties': False}
        value = {'known': None, 'allowed_one': 1, 'unexpected': 'PRIVATE-VALUE'}
        text = schema_feedback(reject(value, schema))
        self.assertEqual(json.loads(text)['diagnostic']['unexpected_properties'], ['unexpected'])
        self.assertNotIn('PRIVATE-VALUE', text)


class RunnerFeedbackTests(unittest.TestCase):
    def exercise(self, rejection=None):
        calls, response_texts = [], []
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = Store(Path(temp.name) / 'workspace.sqlite')
        wid = store.create('Synthetic schema correction boundary')['id']

        def transport(request):
            calls.append(request)
            if len(calls) == 1:
                frame = current_frame(store, wid, {'intent_records': [], 'current_question': 'Fixture',
                    'task_brief': [], 'questions': [], 'hypotheses': []})
                output = [{'type': 'function_call', 'name': 'frame_work', 'arguments': json.dumps(frame),
                           'call_id': 'fixture-frame', 'id': 'fixture-frame'}]
            else:
                value = current_final(store, wid, proposal(1))
                value['decision']['recommendation'] = {'payload': 'SENTINEL-LONG-INSTANCE' * 200}
                text = json.dumps(value)
                response_texts.append(text)
                output = [{'type': 'message', 'role': 'assistant',
                           'content': [{'type': 'output_text', 'text': text}]}]
            return {'id': f'fixture-{len(calls)}', 'model': 'gpt-5.6-terra', 'status': 'completed',
                    'usage': {'input_tokens': 0, 'output_tokens': 0}, 'output': output}, {}

        gateway = Gateway(json.loads((ROOT / 'configs/api_policy.json').read_text()), True, transport=transport)
        runner = object.__new__(Runner)
        runner.root, runner.store, runner.gateway = ROOT, store, gateway
        runner.prompt = (ROOT / 'configs/planner.md').read_text()
        jid = store.enqueue(wid, 1, 'planner', {'synthesis_only': True})
        if rejection is None:
            runner.run_planner(jid)
        else:
            with patch('evida.finalization.finalize', side_effect=rejection):
                runner.run_planner(jid)
        return runner, store, wid, calls, response_texts

    def test_native_corrections_preserve_draft_and_error_but_catalog_stays_small(self):
        runner, store, wid, calls, texts = self.exercise()
        self.assertEqual(len(calls), 2 + runner_module.MAXIMUM_DECISION_CORRECTIONS)
        state = store.snapshot(wid)
        self.assertEqual(state['jobs'][-1]['status'], 'failed')
        proposals = [a for a in state['artifacts'] if a['kind'] == 'decision_proposal'
                     and a['meta'].get('rejection_artifact_id')]
        self.assertEqual(len(proposals), 2)
        for i, proposal_record in enumerate(proposals):
            saved = store.artifact(wid, proposal_record['id'])
            self.assertEqual(saved['content'], texts[i].encode())
            original = store.artifact(wid, saved['meta']['rejection_artifact_id'])
            error = reject(json.loads(texts[i]), runner_module.model_final_decision())
            self.assertEqual(json.loads(original['content'])['message'], str(error))
            viewed = runner.inspect(wid, original['id'])
            self.assertEqual(viewed['result']['message'], str(error))
            overview = json.dumps(artifact_overview(original))
            self.assertNotIn('SENTINEL-LONG-INSTANCE', overview)
            self.assertLess(len(overview), 1800)
        for request in calls[2:]:
            self.assertEqual(request['tool_choice'], 'none')
            prompt = next(i['content'] for i in request['input']
                          if i.get('role') == 'user' and isinstance(i.get('content'), str)
                          and i['content'].startswith('방금 반환한 판단'))
            reason = prompt.split('사유: ', 1)[1].split('\n', 1)[0]
            d = json.loads(reason)['diagnostic']
            self.assertEqual(d['pointer'], '/decision/recommendation')
            self.assertEqual(d['expected_type'], 'string')
            self.assertEqual(d['actual_type'], 'object')
            self.assertNotIn('SENTINEL-LONG-INSTANCE', reason)

    def test_semantic_valueerror_keeps_existing_reason_and_budget(self):
        error = ValueError('의미 연결을 확인하세요: ' + 'x' * 600)
        _, _, _, calls, _ = self.exercise(error)
        self.assertEqual(len(calls), 4)
        prompt = next(i['content'] for i in calls[2]['input']
                      if i.get('role') == 'user' and isinstance(i.get('content'), str)
                      and i['content'].startswith('방금 반환한 판단'))
        self.assertEqual(prompt,
                         runner_module.DECISION_REJECTED.format(reason=str(error)[:400]))

    def test_preservation_conflict_still_stops_without_rewrite_or_new_error_artifact(self):
        error = DecisionPreservationError({'status': 'synthetic_protected_change'})
        _, store, wid, calls, _ = self.exercise(error)
        self.assertEqual(len(calls), 2)
        self.assertFalse(any(a['kind'] == 'decision_validation_error' for a in store.snapshot(wid)['artifacts']))
        self.assertEqual(store.snapshot(wid)['jobs'][-1]['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
