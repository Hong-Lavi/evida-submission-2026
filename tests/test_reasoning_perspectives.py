"""Contract regressions for optional, source-bound reasoning guidance."""
from copy import deepcopy
import hashlib
import json
import unittest

from evida.reasoning_core import context, validate_design
from evida.reasoning_perspectives import allowed_ids, cards_required, for_stage
from test_reasoning_core import design


class SharedReasoningPerspectives(unittest.TestCase):
    def test_new_context_does_not_force_an_inapplicable_card(self):
        core = context('An unfamiliar research objective')
        value = design()
        value['cards_used'] = []
        validate_design(value, allowed_cards=allowed_ids(core), cards_required=cards_required(core))
        self.assertFalse(cards_required(core))
        self.assertTrue(cards_required({'version': 'reasoning-core-v1', 'cards_enabled': True}))
        with self.assertRaises(ValueError):
            validate_design(value, cards_required=True)

    def test_only_delivered_perspective_identity_is_accepted(self):
        core = context('An unfamiliar research objective')
        pid = core['perspectives'][0]['id']
        validate_design(design(pid), allowed_cards=allowed_ids(core))
        with self.assertRaises(ValueError):
            validate_design(design('RP-not-delivered'), allowed_cards=allowed_ids(core))
        self.assertEqual(context('An unfamiliar research objective', cards_enabled=False)['perspectives'], [])

    def test_excluded_source_removes_derived_perspective_not_just_its_example(self):
        core = context('Unrelated goal', excluded_cases=['pmc7614055'])
        self.assertNotIn('RP01', allowed_ids(core))
        self.assertNotIn('RP06', allowed_ids(core))
        self.assertTrue(core['perspectives'])
        bounded = context('Unrelated goal', evidence_scope={'mode': 'supplied_only'})
        self.assertTrue(all(not p['worked_examples'] for p in bounded['perspectives']))
        self.assertTrue(all('not time-blinded' in p['example_delivery_note'] for p in bounded['perspectives']))

    def test_stage_guidance_keeps_the_same_source_bound_core_and_preserves_old_replay(self):
        frame = context('Unrelated goal')
        original = deepcopy(frame)
        for stage in ('research', 'synthesis', 'decision_correction'):
            current = for_stage(frame, stage)
            self.assertEqual(current['stage'], stage)
            self.assertEqual(current['perspectives'], frame['perspectives'])
            self.assertNotEqual(current['sha256'], frame['sha256'])
            digest = current.pop('sha256')
            self.assertEqual(digest, hashlib.sha256(json.dumps(current, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
        self.assertEqual(frame, original)
        historical = {'version': 'reasoning-core-v1', 'cards_enabled': True, 'sha256': 'preserved-old-hash'}
        self.assertEqual(for_stage(historical, 'research'), historical)


if __name__ == '__main__':
    unittest.main()
