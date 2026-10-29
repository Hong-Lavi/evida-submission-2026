"""A public instance must not be able to spend the whole competition allocation.

The demo is handed to people who did not start the server, and a research run makes many calls.
Rate limiting alone does not bound the total: 45 seconds between calls still spends everything
given a day. So the gateway carries an optional ceiling on how many requests this process may
make, and refuses past it rather than slowing down.

Refusing is the point. A request that is not sent costs nothing, and the refusal names the limit
so a reader can tell it apart from a provider failure or a quota error at the organizer's end.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from evida.gateway import Gateway, GatewayError

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / 'configs/api_policy.json').read_text())
PAYLOAD = {'input': [{'role': 'user', 'content': 'x'}]}


def counting():
    """A transport that answers as the process default and counts how often it was reached."""
    sent = []

    def transport(body):
        sent.append(body)
        return {'model': POLICY['development_model_policy']['default_model'], 'id': 'r',
                'status': 'completed', 'output': [], 'usage': {}}, {}

    return transport, sent


def gateway(transport, maximum=None):
    return Gateway(POLICY, enabled=True, model=POLICY['development_model_policy']['default_model'],
                   transport=transport, maximum_requests=maximum)


class BudgetTests(unittest.TestCase):
    def test_without_a_ceiling_nothing_changes(self):
        transport, sent = counting()
        g = gateway(transport)
        for _ in range(5):
            g.request(PAYLOAD)
        self.assertEqual(len(sent), 5)

    def test_calls_up_to_the_ceiling_go_through(self):
        transport, sent = counting()
        g = gateway(transport, maximum=3)
        for _ in range(3):
            g.request(PAYLOAD)
        self.assertEqual(len(sent), 3)

    def test_the_call_after_the_ceiling_is_not_sent(self):
        transport, sent = counting()
        g = gateway(transport, maximum=2)
        g.request(PAYLOAD)
        g.request(PAYLOAD)
        with self.assertRaises(GatewayError) as caught:
            g.request(PAYLOAD)
        self.assertEqual(len(sent), 2, 'the refused request still reached the provider')
        self.assertEqual(caught.exception.status, 'budget_exhausted')

    def test_a_refused_call_does_not_consume_more_budget(self):
        # Otherwise a reader could not tell how many calls the instance actually made.
        transport, _ = counting()
        g = gateway(transport, maximum=1)
        g.request(PAYLOAD)
        for _ in range(3):
            with self.assertRaises(GatewayError):
                g.request(PAYLOAD)
        self.assertEqual(g.status()['requests_made'], 1)

    def test_the_status_says_what_is_left(self):
        transport, _ = counting()
        g = gateway(transport, maximum=4)
        g.request(PAYLOAD)
        status = g.status()
        self.assertEqual(status['maximum_requests'], 4)
        self.assertEqual(status['requests_made'], 1)
        self.assertEqual(status['requests_remaining'], 3)

    def test_an_unlimited_gateway_says_so_rather_than_reporting_a_number(self):
        status = gateway(counting()[0]).status()
        self.assertIsNone(status['maximum_requests'])
        self.assertIsNone(status['requests_remaining'])

    def test_a_ceiling_has_to_be_a_positive_whole_number(self):
        for bad in (0, -1, 1.5, '10'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                gateway(counting()[0], maximum=bad)


if __name__ == '__main__':
    unittest.main()
