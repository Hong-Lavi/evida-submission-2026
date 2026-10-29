"""Native Runner requests retain exact read views through bounded corrections.

The Gateway test seam returns synthetic responses. No provider, scientific
worker, network, or original research database is used.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evida import runner as runner_module
from evida.gateway import Gateway
from evida.model_context import unpack
from evida.runner import Runner
from evida.store import Store, dump
from planner_fixtures import current_final, current_frame
from test_current_call_tools import current_call, proposal


ROOT = Path(__file__).resolve().parents[1]


def context(request):
    matches = []
    for item in request['input']:
        if item.get('role') != 'user' or not isinstance(item.get('content'), str):
            continue
        try:
            value = unpack(json.loads(item['content']))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and 'WORKING_READINGS' in value:
            matches.append(value)
    if len(matches) != 1:
        raise AssertionError(f'Expected one current scientific context, found {len(matches)}')
    return matches[0]


class TerminalReadingPreservationTests(unittest.TestCase):
    def exercise(self, *, early_tool_attempt=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = Store(Path(temp.name) / 'synthetic.sqlite3')
        wid = store.create('Synthetic terminal reading preservation')['id']
        sources, source_records = [], {}
        for index in range(5):
            body = {'rows': [{'paragraph': f'EXACT-REPORTED-PARAGRAPH-{index}',
                              'reported_value': [0, None, 3.8, 600, 'unread'][index],
                              'condition': f'Synthetic condition {index}; no empirical claim.'}]}
            aid = store.add_artifact(wid, f'Synthetic source {index}', 'repository_document',
                                     dump(body).encode(), {}, bump=False)
            sources.append(aid)
            source_records[aid] = {'body': body, 'sha256': store.artifact(wid, aid)['sha256']}
        calls, drafts = [], []
        focused_ids = []

        def function(name, arguments, number):
            return [{'type': 'function_call', 'name': name, 'arguments': dump(arguments),
                     'call_id': f'fixture-call-{number}', 'id': f'fixture-call-{number}'}]

        def notes():
            return {'findings': [], 'open_questions': ['Synthetic fixture only'], 'next_goal': 'Read retained rows'}

        def invalid(number):
            value = current_final(store, wid, proposal(1))
            value['decision']['recommendation'] = {'invalid_type': f'UNCHANGED-ORIGINAL-DRAFT-{number}'}
            text = dump(value)
            drafts.append(text)
            return [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}]}]

        def transport(request):
            calls.append(copy.deepcopy(request))
            number = len(calls)
            if number == 1:
                frame = current_frame(store, wid, {'intent_records': [], 'current_question': 'Synthetic comparison',
                    'task_brief': [], 'questions': [], 'hypotheses': []})
                output = function('frame_work', frame, number)
            elif early_tool_attempt and number == 6:
                # Keep an explicit source scope: three readings, not the fourth
                # already-read source or the fifth source never read.
                readings = [a for a in store.snapshot(wid)['artifacts'] if a['kind'] == 'tool_reading']
                focused_ids.extend(a['id'] for a in readings[:3])
                output = function('focus_readings', {'reading_ids': focused_ids, 'research_notes': notes()}, number)
            elif early_tool_attempt and number == 7:
                output = invalid(number)
            elif early_tool_attempt and number == 8:
                output = function('inspect_artifact', {'artifact_id': sources[4], 'offset': 0, 'limit': 1,
                                                       'research_notes': notes()}, number)
            elif early_tool_attempt and number > 8:
                # The old bug allowed that forbidden read. End the synthetic
                # flow deterministically instead of creating another loop.
                output = [{'type': 'message', 'role': 'assistant', 'content': [
                    {'type': 'output_text', 'text': dump(current_final(store, wid, proposal(1)))}]}]
            elif not early_tool_attempt and number >= 16:
                output = invalid(number)
            else:
                source = sources[min(number - 2, 3)]
                output = function('inspect_artifact', {'artifact_id': source, 'offset': 0, 'limit': 1,
                                                       'research_notes': notes()}, number)
            return {'id': f'synthetic-response-{number}', 'model': request['model'], 'status': 'completed',
                    'usage': {'input_tokens': 0, 'output_tokens': 0}, 'output': output}, {}

        policy = json.loads((ROOT / 'configs/api_policy.json').read_text())
        policy['secret_env'] = 'EVIDA_UNUSED_SYNTHETIC_TEST_CREDENTIAL'
        gateway = Gateway(policy, True, transport=transport)
        runner = object.__new__(Runner)
        runner.root, runner.store, runner.gateway = ROOT, store, gateway
        runner.prompt = (ROOT / 'configs/planner.md').read_text()
        runner.context_recent_views = 2
        jid = store.enqueue(wid, 1, 'planner', {})
        with patch.object(runner, 'read_view', wraps=runner.read_view) as reads:
            runner.run_planner(jid)
            read_count = reads.call_count
        state = store.snapshot(wid)
        job = next(j for j in state['jobs'] if j['id'] == jid)
        retained = {a['id']: {'sha256': a['sha256'],
                    'content': json.loads(store.artifact(wid, a['id'])['content'])}
                    for a in state['artifacts'] if a['kind'] == 'tool_reading'}
        rejected = [store.artifact(wid, a['id'])['content'].decode()
                    for a in state['artifacts'] if a['kind'] == 'decision_proposal'
                    and a['meta'].get('rejection_artifact_id')]
        proposals = [json.loads(store.artifact(wid, a['id'])['content'])
                    for a in state['artifacts'] if a['kind'] == 'decision_proposal'
                    and not a['meta'].get('rejection_artifact_id')]
        summaries = []
        for number, request in enumerate(calls, 1):
            current = context(request)
            summaries.append({'response_number': number, 'tool_choice': request['tool_choice'],
                'current_call': current_call(request),
                'synthesis_instruction': request['instructions'].endswith(runner_module.SYNTHESIS_SUFFIX),
                'delivery': current.get('CONTEXT_DELIVERY'),
                'full_reading_ids': [v['reading_id'] for v in current['WORKING_READINGS'] if 'content' in v],
                'paragraph_present': [f'EXACT-REPORTED-PARAGRAPH-{i}' in json.dumps(request) for i in range(5)]})
        self.capture = {'mode': 'early_tool_attempt_with_explicit_focus' if early_tool_attempt else 'terminal_two_corrections',
            'requests': calls, 'request_summaries': summaries, 'job': job, 'read_view_calls': read_count,
            'source_records': source_records, 'source_ids': sources, 'focused_reading_ids': focused_ids,
            'source_hashes_after': {aid: store.artifact(wid, aid)['sha256'] for aid in sources},
            'reading_records': retained, 'original_drafts': drafts, 'rejected_drafts': rejected,
            'model_proposal_records': proposals, 'published_decision': state['decision'],
            'new_provider_calls': 0, 'scientific_workers': 0, 'gpu_used': False}
        return self.capture

    def assert_full_views_match_originals(self, capture, request):
        delivered = context(request)
        sources = {entry['artifact_id']: entry for entry in delivered['RELEVANT_EVIDENCE']}
        for view in delivered['WORKING_READINGS']:
            saved = capture['reading_records'][view['reading_id']]
            self.assertIn('content', view)
            self.assertEqual(view['sha256'], saved['sha256'])
            self.assertEqual(view['content'], saved['content'])
            body = view['content']
            self.assertEqual(hashlib.sha256(dump(body).encode()).hexdigest(), view['sha256'])
            source = capture['source_records'][body['artifact_id']]
            self.assertEqual(sources[body['artifact_id']]['sha256'], source['sha256'])
            self.assertEqual(body['result']['rows'], source['body']['rows'])
        self.assertEqual(capture['source_hashes_after'],
                         {aid: record['sha256'] for aid, record in capture['source_records'].items()})

    def assert_correction_contract(self, request):
        self.assertEqual(request['tool_choice'], 'none')
        self.assertTrue(request['instructions'].endswith(runner_module.SYNTHESIS_SUFFIX))
        call = current_call(request)
        self.assertEqual(call['stage'], 'decision_correction')
        self.assertEqual(call['tool_choice'], 'none')
        self.assertEqual(call['callable_function_names'], [])
        self.assertEqual(call['research_responses_remaining_including_current'], 0)

    def test_terminal_full_readings_survive_both_corrections_and_budget(self):
        c = self.exercise()
        self.assertEqual(len(c['requests']), 16 + runner_module.MAXIMUM_DECISION_CORRECTIONS)
        self.assertEqual(c['request_summaries'][15]['paragraph_present'], [True, True, True, True, False])
        for index in (16, 17):
            with self.subTest(response_number=index + 1):
                self.assertEqual(c['request_summaries'][index]['paragraph_present'], [True, True, True, True, False])
                self.assert_correction_contract(c['requests'][index])
                self.assert_full_views_match_originals(c, c['requests'][index])
                self.assertEqual(len(context(c['requests'][index])['WORKING_READINGS']), 4)
                self.assertTrue(context(c['requests'][index])['CONTEXT_DELIVERY']['full_delivery_for_terminal_without_tools'])
        self.assertEqual(c['job']['status'], 'failed')
        self.assertEqual(c['read_view_calls'], 14)
        self.assertEqual(c['rejected_drafts'], c['original_drafts'][:2])
        self.assertEqual(len(c['model_proposal_records']), 18)
        for record, text in zip(c['model_proposal_records'][-3:], c['original_drafts']):
            self.assertEqual(record['output'][0]['content'][0]['text'], text)
        self.assertIsNone(c['published_decision'])

    def test_early_correction_keeps_explicit_focus_and_refuses_new_tool(self):
        c = self.exercise(early_tool_attempt=True)
        self.assertEqual(len(c['requests']), 8)
        self.assert_correction_contract(c['requests'][-1])
        self.assertEqual(c['request_summaries'][-1]['paragraph_present'], [True, True, True, False, False])
        self.assertEqual({v['reading_id'] for v in context(c['requests'][-1])['WORKING_READINGS']},
                         set(c['focused_reading_ids']))
        self.assert_full_views_match_originals(c, c['requests'][-1])
        self.assertEqual(c['job']['status'], 'paused')
        self.assertEqual(c['read_view_calls'], 4)
        self.assertEqual(len(c['reading_records']), 4)
        self.assertEqual(c['rejected_drafts'], c['original_drafts'])
        self.assertEqual(c['model_proposal_records'][-1]['output'][0]['name'], 'inspect_artifact')
        self.assertIsNone(c['published_decision'])


if __name__ == '__main__':
    unittest.main()
