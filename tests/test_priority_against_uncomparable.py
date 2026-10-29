"""The model may rank an option the computed order cannot place. That is a finding, not a crash.

Decision 0040 gives an option no tier when it is not comparable - an eligibility gate holds it, or
an axis was never assessed. The model meanwhile assigns its own integer priority from its own
reading, and it can perfectly well rank something the axes cannot separate. The screen exists to
show exactly that kind of disagreement.

compare_with_model_priority compared tiers directly, so the first real published decision - the
preeclampsia case on 2026-10-01, after nineteen stored workspaces had never got this far - raised
TypeError: '>' not supported between instances of 'NoneType' and 'int', and stage 2 could not
render at all.

The honest report is that the model placed it and the computation could not, which is more
interesting than either number.
"""
from __future__ import annotations

import unittest

from evida.mechanism_ranking import compare_with_model_priority

PLACED = 'mechanism:placed'
ALSO_PLACED = 'mechanism:also-placed'
UNPLACED = 'mechanism:held-by-a-gate'


def ranking(tiers):
    return {'rows': [{'option_id': option, 'tier': tier} for option, tier in tiers.items()]}


def assessed(option, priority, group='같은 질환의 기전'):
    return {'option_id': option, 'priority': priority, 'comparison_group': group}


class UncomparableTests(unittest.TestCase):
    def test_an_option_without_a_tier_does_not_raise(self):
        found = compare_with_model_priority(
            ranking({PLACED: 1, UNPLACED: None}),
            [assessed(PLACED, 1), assessed(UNPLACED, 2)])
        self.assertTrue(found['pairs'])

    def test_the_pair_is_reported_as_not_placed_rather_than_agreeing(self):
        found = compare_with_model_priority(
            ranking({PLACED: 1, UNPLACED: None}),
            [assessed(PLACED, 1), assessed(UNPLACED, 2)])
        relations = {row['relation'] for row in found['pairs']}
        self.assertIn('computed_order_cannot_place_one_of_them', relations)
        self.assertNotIn('agree', relations, 'silence would read as the two orders matching')

    def test_two_unplaced_options_are_also_reported(self):
        found = compare_with_model_priority(
            ranking({UNPLACED: None, ALSO_PLACED: None}),
            [assessed(UNPLACED, 1), assessed(ALSO_PLACED, 2)])
        self.assertEqual({r['relation'] for r in found['pairs']},
                         {'computed_order_cannot_place_one_of_them'})

    def test_equal_priorities_with_one_unplaced_do_not_raise(self):
        # The equal-priority branch compared tiers too.
        found = compare_with_model_priority(
            ranking({PLACED: 2, UNPLACED: None}),
            [assessed(PLACED, 1), assessed(UNPLACED, 1)])
        self.assertEqual({r['relation'] for r in found['pairs']},
                         {'computed_order_cannot_place_one_of_them'})

    def test_an_unplaced_pair_counts_as_a_disagreement_to_show(self):
        found = compare_with_model_priority(
            ranking({PLACED: 1, UNPLACED: None}),
            [assessed(PLACED, 1), assessed(UNPLACED, 2)])
        self.assertTrue(found['disagreements'],
                        'a reader has to be told the model ranked something the axes could not')


class PlacedTests(unittest.TestCase):
    """What already worked has to keep working."""

    def test_agreement_is_still_agreement(self):
        found = compare_with_model_priority(
            ranking({PLACED: 1, ALSO_PLACED: 2}),
            [assessed(PLACED, 1), assessed(ALSO_PLACED, 2)])
        self.assertEqual({r['relation'] for r in found['pairs']}, {'agree'})
        self.assertFalse(found['disagreements'])

    def test_a_real_disagreement_is_still_reported(self):
        found = compare_with_model_priority(
            ranking({PLACED: 2, ALSO_PLACED: 1}),
            [assessed(PLACED, 1), assessed(ALSO_PLACED, 2)])
        self.assertEqual({r['relation'] for r in found['pairs']},
                         {'model_ranks_higher_but_computed_lower'})

    def test_equal_priorities_with_different_tiers_still_disagree(self):
        found = compare_with_model_priority(
            ranking({PLACED: 1, ALSO_PLACED: 2}),
            [assessed(PLACED, 1), assessed(ALSO_PLACED, 1)])
        self.assertEqual({r['relation'] for r in found['pairs']},
                         {'model_ranks_them_equal_computed_orders_them'})

    def test_an_option_with_no_priority_is_left_out(self):
        found = compare_with_model_priority(
            ranking({PLACED: 1, ALSO_PLACED: 2}),
            [assessed(PLACED, 1), {'option_id': ALSO_PLACED, 'priority': None,
                                   'comparison_group': 'g'}])
        self.assertEqual(found['pairs'], [])


if __name__ == '__main__':
    unittest.main()
