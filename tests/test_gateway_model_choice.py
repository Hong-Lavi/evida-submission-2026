"""A research may choose which competition model runs it, under the same policy as the default.

The gateway fixed one model for the whole process, so a public demo could only ever offer what
the operator started it with. A per-request choice has to clear exactly the checks the constructor
applies — the competition allowlist and the narrower approved-for-this-run list — and, more
easily missed, the identity gate has to compare against the model that was actually asked for.
A choice that is sent but not verified is worse than no choice: the caller believes they ran
gpt-6-sol and the receipt would agree, while the provider answered with something else.

Nothing here reaches the network; every call goes through the explicit transport seam.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from evida.gateway import Gateway, GatewayError

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / 'configs/api_policy.json').read_text())
DEFAULT = 'gpt-5.6-terra'
OTHER = 'gpt-6-sol'
PAYLOAD = {'input': [{'role': 'user', 'content': 'x'}]}


def answering(model, *, status='completed'):
    """A transport that answers as `model`, recording the body it was handed."""
    seen = {}

    def transport(body):
        seen.update(body)
        return {'model': model, 'id': 'resp_1', 'status': status, 'output': [], 'usage': {}}, {}

    return transport, seen


def gateway(transport, model=DEFAULT):
    return Gateway(POLICY, enabled=True, model=model, transport=transport)


class PolicyTests(unittest.TestCase):
    def test_the_two_approved_models_differ_so_this_suite_means_something(self):
        approved = POLICY.get('development_api_models', POLICY['allowed_models'])
        self.assertIn(DEFAULT, approved)
        self.assertIn(OTHER, approved)

    def test_a_model_outside_the_competition_allowlist_never_reaches_the_provider(self):
        transport, seen = answering(OTHER)
        with self.assertRaises(GatewayError) as caught:
            gateway(transport).request(PAYLOAD, model='gpt-4o')
        self.assertEqual(caught.exception.status, 'invalid_input')
        self.assertEqual(seen, {}, 'the request was sent before the model was checked')

    def test_an_allowlisted_but_unapproved_model_is_also_refused(self):
        # This run approves every allowlisted model, so the narrowing is exercised against a
        # policy that does narrow. Both checks have to hold whichever way the lists are set.
        narrowed = {**POLICY, 'development_api_models': [DEFAULT]}
        held_back = next(m for m in POLICY['allowed_models'] if m != DEFAULT)
        transport, seen = answering(held_back)
        with self.assertRaises(GatewayError) as caught:
            Gateway(narrowed, enabled=True, model=DEFAULT,
                    transport=transport).request(PAYLOAD, model=held_back)
        self.assertEqual(caught.exception.status, 'invalid_input')
        self.assertEqual(seen, {}, 'the request was sent before the model was checked')

    def test_the_offered_list_is_the_allowlist_narrowed_by_this_run(self):
        narrowed = {**POLICY, 'development_api_models': [DEFAULT, 'gpt-4o']}
        offered = Gateway(narrowed, enabled=True, model=DEFAULT).approved_models()
        self.assertEqual(offered, [DEFAULT],
                         'a name approved for this run but outside the competition allowlist '
                         'must not become an option in the interface')


class ChoiceTests(unittest.TestCase):
    def test_the_chosen_model_is_what_gets_sent(self):
        transport, seen = answering(OTHER)
        gateway(transport).request(PAYLOAD, model=OTHER)
        self.assertEqual(seen['model'], OTHER)

    def test_omitting_the_choice_keeps_the_process_default(self):
        transport, seen = answering(DEFAULT)
        gateway(transport).request(PAYLOAD)
        self.assertEqual(seen['model'], DEFAULT)

    def test_the_receipt_records_the_model_that_was_asked_for(self):
        transport, _ = answering(OTHER)
        _, receipt = gateway(transport).request(PAYLOAD, model=OTHER)
        self.assertEqual(receipt['requested_model'], OTHER)
        self.assertEqual(receipt['actual_model'], OTHER)


class IdentityTests(unittest.TestCase):
    def test_answering_as_the_process_default_does_not_satisfy_a_different_choice(self):
        # The gate must compare against the chosen model. Comparing against self.model would
        # let this through, because the provider answered with exactly the process default.
        transport, _ = answering(DEFAULT)
        with self.assertRaises(GatewayError) as caught:
            gateway(transport).request(PAYLOAD, model=OTHER)
        self.assertEqual(caught.exception.status, 'identity_unverified')

    def test_a_dated_variant_of_the_chosen_model_still_counts(self):
        transport, _ = answering(OTHER + '-2026-09-24')
        _, receipt = gateway(transport).request(PAYLOAD, model=OTHER)
        self.assertEqual(receipt['status'], 'RETURNED')


if __name__ == '__main__':
    unittest.main()
