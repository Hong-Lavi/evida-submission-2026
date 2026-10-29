"""The competition API stays the default; a spent allowance is told, never silently replaced.

When the competition gateway answers HTTP 403 its token allowance is spent. The product then has
to say so and let the visitor pick one of the submitter's subscription routes by hand. Nothing
may switch on its own, a subscription route may only run when it was chosen, and the competition
key must never sit in the environment that subscription CLIs inherit.

Nothing here reaches the network; the competition gateway uses its transport seam and the
subscription routes are recording fakes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error

from evida.gateway import Gateway, GatewayError
from evida.model_routes import QuotaState, RouteGateway, workspace_model
from evida.runner import Runner
from evida.store import Store

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / 'configs/api_policy.json').read_text())
PAYLOAD = {'input': [{'role': 'user', 'content': 'x'}]}
CLAUDE = 'subscription:claude-opus-5'
CODEX = 'subscription:gpt-6-sol'


def refusing_403(body):
    raise urllib.error.HTTPError('https://example.invalid', 403, 'forbidden', {}, None)


def answering(model):
    seen = []

    def transport(body):
        seen.append(body)
        return {'model': model, 'id': 'resp_1', 'status': 'completed', 'output': [], 'usage': {}}, {}

    return transport, seen


class FakeRoute:
    def __init__(self, model, provider='anthropic', available=True):
        self.route_id, self.model, self.provider, self.available = 'subscription:' + model, model, provider, available
        self.calls = []

    def status(self):
        return {'id': self.route_id, 'provider': self.provider, 'label': self.model, 'model': self.model,
                'effort': 'medium', 'available': self.available,
                'message': '사용 가능' if self.available else '로그인 확인 필요',
                'caution': '제출자(연구자) 개인 구독으로 운용됩니다.'}

    def request(self, payload):
        self.calls.append(payload)
        return ({'model': self.model, 'status': 'completed', 'output': []},
                {'requested_model': self.model, 'route': self.route_id})


class RecordingPool:
    def __init__(self):
        self.submissions = []

    def submit(self, function, *arguments):
        self.submissions.append((function.__name__, arguments))


def routes(transport, *, quota=None, claude_available=True):
    api = Gateway(POLICY, enabled=True, model='gpt-6-sol', effort='medium', transport=transport)
    api.set_credential('k' * 32)  # configured, as the launcher does; the transport seam answers
    claude, codex = FakeRoute('claude-opus-5', available=claude_available), FakeRoute('gpt-6-sol', 'openai')
    return RouteGateway(api, [claude, codex], quota or QuotaState()), claude, codex


class CompetitionGatewayTests(unittest.TestCase):
    def test_http_403_is_reported_as_a_spent_allowance(self):
        api = Gateway(POLICY, enabled=True, model='gpt-6-sol', effort='medium', transport=refusing_403)
        with self.assertRaises(GatewayError) as caught:
            api.request(PAYLOAD)
        self.assertEqual(caught.exception.status, 'quota_exhausted')
        self.assertEqual(caught.exception.receipt['http_status'], 403)
        self.assertIn('HTTP 403', str(caught.exception))

    def test_a_credential_given_in_memory_never_enters_the_environment(self):
        api = Gateway(POLICY, enabled=True, model='gpt-6-sol', effort='medium')
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(api.status()['credential_configured'])
            api.set_credential('k' * 32)
            self.assertTrue(api.status()['credential_configured'])
            self.assertNotIn(POLICY['secret_env'], os.environ)


class RouteGatewayTests(unittest.TestCase):
    def test_the_default_stays_on_the_competition_api(self):
        transport, seen = answering('gpt-6-sol')
        gateway, claude, codex = routes(transport)
        result, _ = gateway.request(PAYLOAD)
        self.assertEqual(result['model'], 'gpt-6-sol')
        self.assertEqual(len(seen), 1)
        self.assertEqual((claude.calls, codex.calls), ([], []))

    def test_a_403_is_remembered_and_nothing_switches_on_its_own(self):
        gateway, claude, codex = routes(refusing_403)
        with self.assertRaises(GatewayError) as caught:
            gateway.request(PAYLOAD)
        self.assertEqual(caught.exception.status, 'quota_exhausted')
        status = gateway.status()
        self.assertIsNotNone(status['competition_quota'])
        self.assertFalse(status['competition_available'])
        self.assertTrue(status['available'], 'the subscription routes remain choosable')
        self.assertFalse(status['automatic_fallback'])
        with self.assertRaises(GatewayError) as again:
            gateway.check_model_available(None)
        self.assertEqual(again.exception.status, 'quota_exhausted')
        with self.assertRaises(GatewayError):
            gateway.request(PAYLOAD)
        self.assertEqual((claude.calls, codex.calls), ([], []), 'no route was used without being chosen')

    def test_a_chosen_subscription_route_runs_only_that_route(self):
        gateway, claude, codex = routes(refusing_403)
        gateway.check_model_available(CLAUDE)
        result, receipt = gateway.request(PAYLOAD, model=CLAUDE)
        self.assertEqual((result['model'], receipt['route']), ('claude-opus-5', CLAUDE))
        self.assertEqual((len(claude.calls), codex.calls), (1, []))
        gateway.request(PAYLOAD, model=CODEX)
        self.assertEqual(len(codex.calls), 1)

    def test_status_lists_every_route_with_its_caution(self):
        gateway, _, _ = routes(answering('gpt-6-sol')[0])
        status = gateway.status()
        ids = [r['id'] for r in status['routes']]
        self.assertEqual(ids[-2:], [CLAUDE, CODEX])
        self.assertEqual(status['approved_models'], ids)
        default = [r for r in status['routes'] if r['default']]
        self.assertEqual([r['id'] for r in default], ['gpt-6-sol'])
        for route in status['routes']:
            if route['kind'] == 'subscription':
                self.assertIn('개인 구독', route['caution'])

    def test_unknown_and_unavailable_choices_are_refused_before_any_call(self):
        gateway, claude, _ = routes(answering('gpt-6-sol')[0], claude_available=False)
        with self.assertRaises(GatewayError) as unknown:
            gateway.request(PAYLOAD, model='subscription:something-else')
        self.assertEqual(unknown.exception.status, 'invalid_input')
        with self.assertRaises(GatewayError) as unavailable:
            gateway.check_model_available(CLAUDE)
        self.assertEqual(unavailable.exception.status, 'route_unavailable')
        self.assertEqual(claude.calls, [])

    def test_the_spent_allowance_survives_a_restart_and_is_rechecked_later(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'competition-quota.json'
            now = [1000.0]
            first = QuotaState(path, recheck_seconds=60, clock=lambda: now[0])
            first.mark({'http_status': 403})
            restarted = QuotaState(path, recheck_seconds=60, clock=lambda: now[0])
            self.assertTrue(restarted.active())
            now[0] += 61
            self.assertFalse(restarted.active(), 'a restored allowance is tried again')


class RunnerRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(Path(self.directory.name) / 'evida.sqlite3')
        state = self.store.create('route test')
        self.wid, self.rev = state['id'], state['rev']

    def runner(self, gateway):
        runner = Runner.__new__(Runner)
        runner.root, runner.store, runner.gateway = Path(self.directory.name), self.store, gateway
        runner.pool = RecordingPool()
        return runner

    def test_a_spent_allowance_is_refused_before_a_job_is_queued(self):
        gateway, _, _ = routes(refusing_403)
        gateway.quota.mark({'http_status': 403})
        runner = self.runner(gateway)
        with self.assertRaises(GatewayError) as caught:
            runner.start(self.wid, self.rev, 'planner', {})
        self.assertEqual(caught.exception.status, 'quota_exhausted')
        self.assertEqual(self.store.snapshot(self.wid)['jobs'], [])
        self.assertEqual(runner.pool.submissions, [])

    def test_a_chosen_route_is_queued_and_inherited_by_later_runs(self):
        gateway, _, _ = routes(refusing_403)
        gateway.quota.mark({'http_status': 403})
        runner = self.runner(gateway)
        runner.start(self.wid, self.rev, 'planner', {'model': CLAUDE})
        self.assertEqual(workspace_model(self.store, self.wid, gateway), CLAUDE)
        self.assertEqual(runner.workspace_model(self.wid), CLAUDE)

    def test_a_single_route_gateway_keeps_its_old_behaviour(self):
        api = Gateway(POLICY, enabled=True, model='gpt-6-sol', effort='medium', transport=refusing_403)
        api.set_credential('k' * 32)
        runner = self.runner(api)
        self.assertIsNone(runner.workspace_model(self.wid))
        runner.start(self.wid, self.rev, 'planner', {})
        self.assertEqual(len(runner.pool.submissions), 1)


if __name__ == '__main__':
    unittest.main()
