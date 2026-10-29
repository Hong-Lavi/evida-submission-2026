"""Dominance ranking over weight bounds (decision D1). No solver, no invented order.

These exercise the general machinery over the four recorded axes, which is why every call names
its axis set, bounds and order. What the PRODUCT compares by default is narrower - two axes, no
weight assumptions, and an eligibility gate - and that contract is in test_ranking_profile.py.
"""
from fractions import Fraction
import random
import unittest

from evida.mechanism_ranking import (AXES, DEFAULT_BOUNDS, DEFAULT_ORDER, compare,
                                      compare_with_model_priority, rank, weight_vertices)

# The four-axis setting these tests are written for; the product default is two axes.
FOUR = {'bounds': DEFAULT_BOUNDS, 'order': DEFAULT_ORDER, 'axes': AXES}


def aspects(disease_match=None, clinical_precedent=None, evidence_grade=None, actionability=None):
    return {'disease_match': disease_match, 'clinical_precedent': clinical_precedent,
            'evidence_grade': evidence_grade, 'actionability': actionability}


def option(name, **kwargs):
    return {'option_id': name, 'aspects': aspects(**kwargs), 'kind': 'mechanism',
            'support_source_ids': ['art_support'], 'challenge_source_ids': []}


FULL = dict(disease_match=0.5, clinical_precedent=0.5, evidence_grade=0.5, actionability=0.5)


class DominanceTests(unittest.TestCase):
    def test_better_on_one_axis_and_equal_elsewhere_dominates(self):
        better = aspects(**{**FULL, 'evidence_grade': 0.9})
        self.assertEqual(compare(better, aspects(**FULL)), 'dominates')
        self.assertEqual(compare(aspects(**FULL), better), 'dominated')

    def test_a_tradeoff_between_axes_of_unstated_order_stays_incomparable(self):
        """clinical_precedent and actionability have no stated order, so neither can win."""
        left = aspects(**{**FULL, 'clinical_precedent': 0.9})
        right = aspects(**{**FULL, 'actionability': 0.9})
        self.assertEqual(compare(left, right), 'incomparable')
        self.assertEqual(compare(right, left), 'incomparable')

    def test_a_tradeoff_the_stated_axis_order_settles_is_decided(self):
        """disease_match >= actionability is stated, so trading one for the other is decidable.

        This is the point of stating the order: without it the weight set contains vectors where
        actionability outweighs disease_match, which nobody would defend, and that vector alone
        vetoes the comparison.
        """
        left = aspects(**{**FULL, 'disease_match': 0.9})
        right = aspects(**{**FULL, 'actionability': 0.9})
        self.assertEqual(compare(left, right), 'dominates')
        self.assertEqual(compare(right, left), 'dominated')
        self.assertEqual(compare(left, right, bounds=DEFAULT_BOUNDS, order=(), axes=AXES), 'incomparable',
                         'dropping the stated order returns the pair to undecided')

    def test_identical_profiles_are_incomparable_not_dominating(self):
        self.assertEqual(compare(aspects(**FULL), aspects(**FULL)), 'incomparable')

    def test_an_unchecked_axis_is_never_imputed_as_equal_or_zero(self):
        checked = aspects(**FULL)
        unchecked = aspects(**{**FULL, 'clinical_precedent': None})
        # A null spans [0,1]: it neither wins nor loses the pair on its own.
        self.assertEqual(compare(checked, unchecked), 'incomparable')
        self.assertEqual(compare(unchecked, checked), 'incomparable')
        # Only a margin that survives every value of the unknown produces an edge.
        self.assertEqual(compare(aspects(disease_match=1, clinical_precedent=1,
                                         evidence_grade=1, actionability=1),
                                 aspects(disease_match=0, clinical_precedent=None,
                                         evidence_grade=0, actionability=0)), 'dominates')

    def test_all_unchecked_options_are_incomparable(self):
        self.assertEqual(compare(aspects(), aspects()), 'incomparable')

    def test_frontier_and_tiers_report_undecided_order_explicitly(self):
        result = rank([option('a', **{**FULL, 'evidence_grade': 0.9}),
                       option('b', **FULL),
                       option('c', **{**FULL, 'disease_match': 0.9})], **FOUR)
        tiers = {r['option_id']: r['tier'] for r in result['rows']}
        self.assertEqual(sorted(result['frontier']), ['a', 'c'])
        self.assertIsNone(result['single_leader'])
        self.assertEqual(tiers['b'], 2)
        row = next(r for r in result['rows'] if r['option_id'] == 'a')
        self.assertEqual(row['dominates'], ['b'])
        self.assertEqual(row['incomparable_with'], ['c'])

    def test_a_single_leader_is_named_only_when_it_dominates_every_other(self):
        result = rank([option('leader', disease_match=1, clinical_precedent=1, evidence_grade=1, actionability=1),
                       option('mid', **FULL),
                       option('low', disease_match=0.1, clinical_precedent=0.1, evidence_grade=0.1, actionability=0.1)], **FOUR)
        self.assertEqual(result['single_leader'], 'leader')
        self.assertEqual(result['tiers'], 3)

    def test_every_admissible_weighting_agrees_with_the_dominance_edges(self):
        """With no unchecked axis, an edge must not contradict any weighting the set allows.

        Admissible means inside the bounds, summing to 1, and respecting the stated axis order -
        the same set the engine minimises over. Sampling the raw box instead would test weightings
        the bounds themselves exclude.
        """
        generator = random.Random(20260930)
        options = [option(f'o{i}', **{axis: generator.randrange(0, 11) / 10 for axis in AXES})
                   for i in range(6)]
        result = rank(options, **FOUR)
        values = {o['option_id']: o['aspects'] for o in options}
        checked = 0
        while checked < 2000:
            draw = {axis: generator.uniform(*DEFAULT_BOUNDS[axis]) for axis in AXES}
            total = sum(draw.values())
            weights = {axis: value / total for axis, value in draw.items()}
            if any(not DEFAULT_BOUNDS[axis][0] <= weights[axis] <= DEFAULT_BOUNDS[axis][1] for axis in AXES):
                continue
            if any(weights[high] < weights[low] for high, low in DEFAULT_ORDER):
                continue
            checked += 1
            score = {i: sum(weights[axis] * values[i][axis] for axis in AXES) for i in values}
            for edge in result['edges']:
                self.assertGreaterEqual(round(score[edge['from']] - score[edge['to']], 9), 0,
                                        (edge, weights))

    def test_narrower_bounds_can_decide_a_pair_the_wide_range_leaves_open(self):
        left = aspects(**{**FULL, 'clinical_precedent': 0.9})
        right = aspects(**{**FULL, 'actionability': 0.9})
        self.assertEqual(compare(left, right), 'incomparable')
        narrow = {'disease_match': (0.3, 0.3), 'clinical_precedent': (0.3, 0.3),
                  'evidence_grade': (0.3, 0.3), 'actionability': (0.1, 0.1)}
        self.assertEqual(compare(left, right, narrow, DEFAULT_ORDER, AXES), 'dominates')

    def test_bad_input_is_refused_rather_than_silently_scored(self):
        for bad in ({'disease_match': (0.5, 0.2)}, {'disease_match': (-0.1, 0.2)}):
            with self.assertRaises(ValueError):
                compare(aspects(**FULL), aspects(**FULL), {**DEFAULT_BOUNDS, **bad}, DEFAULT_ORDER, AXES)
        with self.assertRaises(ValueError):
            rank([option('a', **FULL), option('a', **FULL)], **FOUR)
        with self.assertRaises(ValueError):
            rank([{'option_id': 'a', 'aspects': {**aspects(**FULL), 'disease_match': 1.5}}], **FOUR)

    def test_empty_and_single_inputs_stay_well_defined(self):
        self.assertEqual(rank([], **FOUR)['frontier'], [])
        single = rank([option('only', **FULL)], **FOUR)
        self.assertEqual(single['frontier'], ['only'])
        self.assertEqual(single['rows'][0]['incomparable_with'], [])

    def test_one_option_is_not_announced_as_first_place(self):
        # The frontier of a single option is that option by construction. Calling it the leader
        # would claim it wins across the whole weight range after no comparison at all, and this
        # is the normal early state of a case rather than a failure.
        single = rank([option('only', **FULL)], **FOUR)
        self.assertIsNone(single['single_leader'])
        self.assertEqual(single['single_leader_withheld'], 'only_one_option_graded')
        two = rank([option('a', **{**FULL, 'evidence_grade': 0.9}), option('b', **FULL)], **FOUR)
        self.assertEqual(two['single_leader'], 'a', 'a real comparison still names a leader')


class ModelPriorityComparisonTests(unittest.TestCase):
    def assessment(self, option_id, priority, group='g'):
        return {'option_id': option_id, 'priority': priority, 'comparison_group': group}

    def test_agreement_and_disagreement_are_both_reported_without_overwriting(self):
        ranking = rank([option('a', **{**FULL, 'evidence_grade': 0.9}), option('b', **FULL)], **FOUR)
        agree = compare_with_model_priority(ranking, [self.assessment('a', 1), self.assessment('b', 2)])
        self.assertEqual(agree['disagreements'], [])
        conflict = compare_with_model_priority(ranking, [self.assessment('b', 1), self.assessment('a', 2)])
        self.assertEqual(len(conflict['disagreements']), 1)
        self.assertEqual(conflict['disagreements'][0]['relation'], 'model_ranks_higher_but_computed_lower')

    def test_same_tier_model_ordering_is_surfaced_not_treated_as_agreement(self):
        ranking = rank([option('a', **{**FULL, 'clinical_precedent': 0.9}),
                        option('b', **{**FULL, 'actionability': 0.9})], **FOUR)
        result = compare_with_model_priority(ranking, [self.assessment('a', 1), self.assessment('b', 2)])
        self.assertEqual(result['disagreements'][0]['relation'], 'same_tier_model_orders_them')

    def test_unranked_and_cross_group_priorities_are_not_compared(self):
        ranking = rank([option('a', **{**FULL, 'evidence_grade': 0.9}), option('b', **FULL)], **FOUR)
        result = compare_with_model_priority(ranking, [
            {'option_id': 'a', 'priority': None, 'comparison_group': 'g'},
            {'option_id': 'b', 'priority': 1, 'comparison_group': 'other'},
            {'option_id': 'missing', 'priority': 1, 'comparison_group': 'g'}])
        self.assertEqual(result['pairs'], [])
        self.assertEqual(result['ranked_by_model'], ['b'])


class AdmissibleWeightTests(unittest.TestCase):
    """The weight set is the box intersected with sum(w)=1, not the raw box."""

    def test_every_vertex_is_inside_the_bounds_and_sums_to_one(self):
        vertices = weight_vertices(DEFAULT_BOUNDS, DEFAULT_ORDER, AXES)
        self.assertTrue(vertices)
        for vertex in vertices:
            self.assertEqual(sum(vertex.values()), 1)
            for axis in AXES:
                # Exact comparison: Fraction(7, 20) is 0.35, the float 0.35 is slightly less.
                low, high = (Fraction(str(x)) for x in DEFAULT_BOUNDS[axis])
                self.assertLessEqual(low, vertex[axis])
                self.assertLessEqual(vertex[axis], high)

    def test_bounds_that_cannot_sum_to_one_are_refused(self):
        impossible = {axis: (0.0, 0.1) for axis in AXES}  # at most 0.4
        with self.assertRaises(ValueError):
            weight_vertices(impossible)

    def test_a_pair_decidable_only_under_normalised_weights_is_decided(self):
        """Un-normalised corners describe weightings the bounds themselves exclude.

        Ahead on three axes by 0.1, behind on actionability by 0.15. The raw box's worst corner
        puts every advantage at its floor and the one disadvantage at its ceiling, a vector
        summing to 0.70 rather than 1, and reports no dominance. Under sum-to-one the loss is at
        most 0.35 of weight against at least 0.65 for the gains, so the pair is decided.
        """
        left = aspects(disease_match=0.6, clinical_precedent=0.6,
                       evidence_grade=0.6, actionability=0.35)
        right = aspects(disease_match=0.5, clinical_precedent=0.5,
                        evidence_grade=0.5, actionability=0.5)
        raw_worst = (0.1 * DEFAULT_BOUNDS['disease_match'][0] + 0.1 * DEFAULT_BOUNDS['clinical_precedent'][0]
                     + 0.1 * DEFAULT_BOUNDS['evidence_grade'][0] - 0.15 * DEFAULT_BOUNDS['actionability'][1])
        self.assertLess(raw_worst, 0, 'the raw box would not decide this pair')
        self.assertEqual(compare(left, right), 'dominates')
        self.assertEqual(compare(right, left), 'dominated')

    def test_the_verdict_does_not_depend_on_which_axis_holds_which_value(self):
        """Exact arithmetic: a true zero must not round into a tiny negative."""
        left = aspects(disease_match=0.4, clinical_precedent=0.7,
                       evidence_grade=0.2, actionability=0.6)
        right = aspects(disease_match=0.1, clinical_precedent=0.3,
                        evidence_grade=0.4, actionability=0.1)
        swapped_left = aspects(disease_match=0.2, clinical_precedent=0.7,
                               evidence_grade=0.4, actionability=0.6)
        swapped_right = aspects(disease_match=0.4, clinical_precedent=0.3,
                                evidence_grade=0.1, actionability=0.1)
        self.assertEqual(compare(left, right, **FOUR), compare(swapped_left, swapped_right, **FOUR))


class RecordedChallengeTests(unittest.TestCase):
    """No axis records which way the evidence points, so a recorded challenge stops the comparison.

    Decision 0040 made this stronger than it was: a challenge used to withhold first place while
    the option still took part in every pairwise order. An option whose contradicting evidence has
    not been scoped is now held out of the comparison entirely, and says so.
    """

    def strongest(self, **extra):
        return {'option_id': 'tested', 'kind': 'mechanism',
                'support_source_ids': ['art_support'], 'challenge_source_ids': [],
                'aspects': aspects(**{'disease_match': 1.0, 'clinical_precedent': 0.75,
                                      'evidence_grade': 1.0, 'actionability': 1.0}), **extra}

    def weaker(self):
        return option('weaker', disease_match=0.5, clinical_precedent=0.25,
                      evidence_grade=0.5, actionability=0.75)

    def test_an_unscoped_challenge_holds_the_option_out_of_the_comparison(self):
        result = rank([self.strongest(challenge_source_ids=['art_null_result']), self.weaker()], **FOUR)
        held = next(h for h in result['held'] if h['option_id'] == 'tested')
        self.assertEqual(held['reasons'], ['applicable_challenge_unresolved'])
        self.assertIsNone(result['single_leader'])
        self.assertEqual(result['contradicted'], ['tested'])
        self.assertNotIn('tested', result['frontier'])

    def test_a_challenge_reviewed_as_out_of_scope_returns_the_option_to_the_comparison(self):
        result = rank([self.strongest(challenge_source_ids=['art_null_result'], challenge_applies=False),
                       self.weaker()], **FOUR)
        self.assertEqual(result['held'], [])
        self.assertEqual(result['frontier'], ['tested'])
        # It can lead the order again, but the top slot still says contradicting evidence exists.
        self.assertIsNone(result['single_leader'])
        self.assertEqual(result['single_leader_withheld'], 'contradicting_evidence_recorded')

    def test_a_held_option_is_not_deleted_and_does_not_rewrite_the_others(self):
        challenged = rank([self.strongest(challenge_source_ids=['art_null_result']), self.weaker()], **FOUR)
        row = next(r for r in challenged['rows'] if r['option_id'] == 'tested')
        self.assertEqual(row['aspects']['disease_match'], 1.0, 'the record itself is untouched')
        self.assertEqual(row['challenge_source_ids'], ['art_null_result'])
        self.assertIs(row['comparable'], False)
        self.assertIsNone(row['tier'], 'a held option has no place in the order')
        self.assertTrue(row['hold_meanings'][0])
        alone = rank([self.weaker()], **FOUR)
        self.assertEqual([r['tier'] for r in alone['rows']],
                         [r['tier'] for r in challenged['rows'] if r['option_id'] == 'weaker'])

    def test_an_option_with_no_checked_axis_is_not_announced_as_a_leader(self):
        result = rank([{'option_id': 'nothing_checked', 'aspects': {}, 'kind': 'mechanism',
                        'support_source_ids': ['s'], 'challenge_source_ids': []}], **FOUR)
        self.assertIsNone(result['single_leader'])
        self.assertEqual(result['frontier'], [])
        self.assertEqual(result['held'][0]['reasons'], ['unassessed_axis'])
        self.assertIn('미평가는 0점이 아닙니다', result['held'][0]['meanings'][0])

    def test_options_without_the_field_are_unaffected(self):
        result = rank([option('a', **{**FULL, 'evidence_grade': 0.9}), option('b', **FULL)], **FOUR)
        self.assertEqual(result['contradicted'], [])
        self.assertEqual(result['single_leader'], 'a')
        for row in result['rows']:
            self.assertFalse(row['contradicted'])
            self.assertEqual(row['challenge_source_ids'], [])


class RefusedInputTests(unittest.TestCase):
    """Bad input is refused in this module's own words, never quietly reinterpreted."""

    def test_a_bare_string_of_challenges_is_refused_not_split_into_characters(self):
        with self.assertRaises(ValueError):
            rank([{'option_id': 'a', 'aspects': aspects(**FULL), 'challenge_source_ids': 'art_1'}], **FOUR)
        kept = rank([{'option_id': 'a', 'aspects': aspects(**FULL),
                      'challenge_source_ids': ['art_1']}])
        self.assertEqual(kept['rows'][0]['challenge_source_ids'], ['art_1'])

    def test_bounds_built_by_float_arithmetic_still_describe_one_weight_set(self):
        drifted = {'disease_match': (0.30 - 0.15, 0.30 + 0.15),
                   'clinical_precedent': (0.20 - 0.15, 0.20 + 0.15),
                   'evidence_grade': (0.30 - 0.15, 0.30 + 0.15),
                   'actionability': (0.20 - 0.15, 0.20 + 0.15)}
        self.assertEqual(len(weight_vertices(drifted, DEFAULT_ORDER, AXES)),
                         len(weight_vertices(DEFAULT_BOUNDS, DEFAULT_ORDER, AXES)),
                         'float dust must not split a vertex into near-duplicates')

    def test_a_model_priority_that_cannot_be_ordered_is_refused(self):
        ranking = rank([option('a', **{**FULL, 'evidence_grade': 0.9}), option('b', **FULL)], **FOUR)
        graded = lambda i, p, g='g': {'option_id': i, 'priority': p, 'comparison_group': g}
        for bad in (graded('a', '1'), graded('a', 1, ''), {'priority': 1, 'comparison_group': 'g'}):
            with self.assertRaises(ValueError):
                compare_with_model_priority(ranking, [bad])

    def test_equal_model_priorities_are_reported_rather_than_dropped(self):
        ranking = rank([option('a', **{**FULL, 'evidence_grade': 0.9}), option('b', **FULL)], **FOUR)
        graded = lambda i, p: {'option_id': i, 'priority': p, 'comparison_group': 'g'}
        result = compare_with_model_priority(ranking, [graded('a', 1), graded('b', 1)])
        self.assertEqual(len(result['pairs']), 1)
        self.assertEqual(result['disagreements'][0]['relation'],
                         'model_ranks_them_equal_computed_orders_them')


if __name__ == '__main__':
    unittest.main()


class ApprovalTests(unittest.TestCase):
    """The approval belongs to four exact statements, so it is reported only when they were used."""

    def test_the_default_order_carries_its_approval_record(self):
        from evida.mechanism_ranking import DEFAULT_ORDER_APPROVAL
        ranking = rank([option('a', **FULL), option('b', **FULL)], **FOUR)
        self.assertEqual(ranking['stated_axis_order_approval'], DEFAULT_ORDER_APPROVAL)
        self.assertIn('0038', ranking['stated_axis_order_approval']['decision'])

    def test_a_different_order_is_never_shown_as_approved(self):
        for order in ((), (('disease_match', 'clinical_precedent'),)):
            with self.subTest(order=order):
                ranking = rank([option('a', **FULL), option('b', **FULL)], DEFAULT_BOUNDS, order, AXES)
                self.assertIsNone(ranking['stated_axis_order_approval'])
