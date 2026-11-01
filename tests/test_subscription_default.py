"""Explicit subscription default keeps the API selectable and failures on their route."""
import unittest
from evida.gateway import GatewayError
from evida.model_routes import RouteGateway
from tests.test_model_routes import routes, answering, PAYLOAD, CODEX


class SubscriptionDefaultTests(unittest.TestCase):
    def configured(self):
        transport, seen = answering('gpt-6-sol')
        legacy, claude, codex = routes(transport)
        return RouteGateway(legacy.api, [claude, codex], legacy.quota,
                            default_route=CODEX), claude, codex, seen

    def test_default_uses_subscription_and_manual_api_remains_distinct(self):
        gateway, claude, codex, seen = self.configured()
        gateway.request(PAYLOAD)
        self.assertEqual(len(codex.calls), 1)
        self.assertEqual(seen, [])
        gateway.request(PAYLOAD, model='gpt-6-sol')
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(codex.calls), 1)
        self.assertEqual(claude.calls, [])

    def test_default_status_is_unambiguous_and_api_quota_does_not_block_it(self):
        gateway, _, _, seen = self.configured()
        gateway.quota.mark({'http_status': 403})
        status = gateway.status()
        self.assertEqual(status['default_model'], CODEX)
        self.assertEqual([r['id'] for r in status['routes'] if r['default']], [CODEX])
        self.assertTrue(any(r['kind'] == 'competition' for r in status['routes']))
        self.assertFalse(status['competition_available'])
        gateway.check_model_available(None)
        gateway.request(PAYLOAD)
        self.assertEqual(seen, [])

    def test_unavailable_default_does_not_fall_back(self):
        gateway, claude, codex, seen = self.configured()
        codex.available = False
        with self.assertRaises(GatewayError):
            gateway.check_model_available(None)
        self.assertEqual((claude.calls, codex.calls, seen), ([], [], []))

    def test_unrecognized_default_is_refused(self):
        gateway, _, _, _ = self.configured()
        with self.assertRaises(ValueError):
            RouteGateway(gateway.api, (), default_route=CODEX)


if __name__ == '__main__':
    unittest.main()
