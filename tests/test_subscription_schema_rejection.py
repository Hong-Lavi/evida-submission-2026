"""Synthetic transport-rejection tests; no provider or scientific evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evida.gateway import Gateway
from evida.model_context import unpack
from evida.runner import Runner
from evida.store import Store, dump
from planner_fixtures import current_final, current_frame
from test_integrity import proposal
from test_reasoning_core import design, hypothesis

ROOT = Path(__file__).resolve().parents[1]


class SubscriptionSchemaRejection(unittest.TestCase):
    def run_case(self, permanent):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary) / 'db')
            wid = store.create('합성 구독 응답 정정 시험')['id']
            policy = json.loads((ROOT / 'configs/api_policy.json').read_text())
            policy['min_request_interval_seconds'] = 0
            gateway = Gateway(policy, True, model='gpt-6-sol', effort='medium')
            runner = Runner(ROOT, store, gateway, Path(temporary) / 'runs')
            calls = []
            def transport(request):
                calls.append(request)
                if permanent or len(calls) == 1:
                    output = [{'type': 'function_call', 'name': 'frame_work',
                               'arguments': '{"invalid":true}', 'call_id': 'rejected-frame'}]
                    return {'model': gateway.model, 'status': 'completed', 'usage': {},
                        'output': output, 'schema_rejection': {'status': 'REJECTED',
                            'errors': [{'path': [], 'message': 'Missing required frame fields'}]}}, {}
                core = unpack(json.loads(request['input'][-1]['content']))['CURRENT_CALL']['reasoning_core']
                p = deepcopy(proposal(1))
                p['research_loop']['hypotheses'] = [hypothesis(design(core['cards'][0]['id']))]
                if len(calls) == 2:
                    self.assertFalse(any(e['kind'] == 'frame_updated' for e in store.snapshot(wid)['events']))
                    self.assertTrue(any(item.get('type') == 'function_call_output'
                        and 'invalid_input' in item['output'] for item in request['input']))
                    frame = current_frame(store, wid, {'intent_records': [],
                        'current_question': '합성 설계 기능 시험', 'task_brief': [], 'questions': [],
                        'hypotheses': p['research_loop']['hypotheses']})
                    output = [{'type': 'function_call', 'name': 'frame_work',
                               'arguments': dump(frame), 'call_id': 'valid-frame'}]
                else:
                    output = [{'type': 'message', 'role': 'assistant', 'content': [
                        {'type': 'output_text', 'text': dump(current_final(store, wid, p))}]}]
                return {'model': gateway.model, 'status': 'completed', 'usage': {}, 'output': output}, {}
            gateway.transport = transport
            jid = store.enqueue(wid, 1, 'planner', {}, 'synthetic-format-test')
            try:
                with patch.object(gateway, 'status', return_value={'available': True}):
                    runner.run_planner(jid)
                state = store.snapshot(wid)
                self.assertEqual(len(calls), 3)
                self.assertEqual(state['jobs'][0]['status'], 'failed' if permanent else 'succeeded', state['jobs'][0].get('error'))
                errors = [a for a in state['artifacts'] if a['kind'] == 'model_output_validation_error']
                self.assertEqual(len(errors), 3 if permanent else 1)
                self.assertTrue(all(a['meta']['executed'] is False for a in errors))
                if permanent:
                    self.assertFalse(any(e['kind'] == 'decision_published' for e in state['events']))
            finally:
                runner.pool.shutdown(wait=True)
                runner.explanation_pool.shutdown(wait=True)

    def test_verified_schema_rejection_corrects_without_executing_bad_frame(self):
        self.run_case(False)

    def test_repeated_rejection_stops_at_two_corrections(self):
        self.run_case(True)


if __name__ == '__main__':
    unittest.main()
