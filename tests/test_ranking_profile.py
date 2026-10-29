"""What the product actually compares, after the 2026-09-30 ranking round (decision 0040).

Two things were wrong with comparing on all four axes. `actionability` says what OUR tools can
reach today, so a mechanism could rank higher because we happen to have a tool for it. And an
option was ordered against others as soon as it had axis values, before anyone had looked at the
evidence that could overturn it.

So the scientific order now uses applicability and validity only, it is non-compensatory - a
large win on one axis cannot buy a loss on the other - and an option joins the comparison only
once support, challenges and (for a candidate) the mechanism it targets have been reviewed.
"""
import unittest

from evida.mechanism_ranking import (AXIS_ROLES, COMPARISON_AXES, CONTEXT_AXES, OPERATIONS_AXES,
                                     compare, eligibility, rank)


def option(name, applicability, validity, **extra):
    aspects = {'disease_match': applicability, 'evidence_grade': validity,
               'clinical_precedent': extra.pop('clinical_precedent', 0.5),
               'actionability': extra.pop('actionability', 0.5)}
    return {'option_id': name, 'kind': extra.pop('kind', 'mechanism'), 'aspects': aspects,
            'support_source_ids': extra.pop('support_source_ids', ['art_support']),
            'challenge_source_ids': extra.pop('challenge_source_ids', []), **extra}


class ComparisonProfileTests(unittest.TestCase):
    def test_only_applicability_and_validity_decide_the_order(self):
        self.assertEqual(COMPARISON_AXES, ('disease_match', 'evidence_grade'))
        self.assertEqual(AXIS_ROLES['disease_match'], 'applicability')
        self.assertEqual(AXIS_ROLES['evidence_grade'], 'validity')
        self.assertEqual(CONTEXT_AXES, ('clinical_precedent',))
        self.assertEqual(OPERATIONS_AXES, ('actionability',))

    def test_a_tool_we_happen_to_have_does_not_move_the_scientific_order(self):
        ready = option('ready', 0.5, 0.5, actionability=1.0)
        unready = option('unready', 0.5, 0.5, actionability=0.0)
        result = rank([ready, unready])
        self.assertEqual(result['edges'], [], 'identical science, different tooling: no order')
        self.assertIsNone(result['single_leader'])
        row = next(r for r in result['rows'] if r['option_id'] == 'ready')
        self.assertEqual(row['operations_axes'], {'actionability': 1.0},
                         'still shown, just not compared')

    def test_clinical_precedent_is_shown_but_does_not_order(self):
        result = rank([option('a', 0.5, 0.5, clinical_precedent=1.0),
                       option('b', 0.5, 0.5, clinical_precedent=0.0)])
        self.assertEqual(result['edges'], [])
        row = next(r for r in result['rows'] if r['option_id'] == 'a')
        self.assertEqual(row['context_axes'], {'clinical_precedent': 1.0})

    def test_a_big_win_on_one_axis_does_not_buy_a_loss_on_the_other(self):
        # Directly applicable but weakly designed, against barely applicable and well designed.
        self.assertEqual(compare({'disease_match': 1.0, 'evidence_grade': 0.2},
                                 {'disease_match': 0.1, 'evidence_grade': 0.3}), 'incomparable')
        self.assertEqual(compare({'disease_match': 1.0, 'evidence_grade': 0.3},
                                 {'disease_match': 0.1, 'evidence_grade': 0.3}), 'dominates')

    def test_the_lopsided_case_is_explained_without_a_number(self):
        result = rank([option('a', 0.9, 0.2), option('b', 0.2, 0.25)])
        note = result['mostly_ahead_notes'][0]
        self.assertEqual(note['mostly_ahead'], 'a')
        self.assertEqual(sorted(note['pair']), ['a', 'b'])
        self.assertIn('순서의 근거도 확률도 아닙니다', note['meaning'])
        text = repr(result['mostly_ahead_notes'])
        self.assertNotIn('%', text, 'a share of an assumed weight range reads as a probability')
        self.assertFalse(any(key.endswith('share') or key.endswith('probability') for key in note))

    def test_an_even_tradeoff_gets_no_note_at_all(self):
        result = rank([option('a', 1.0, 0.0), option('b', 0.0, 1.0)])
        self.assertEqual(result['edges'], [])
        self.assertEqual(result['mostly_ahead_notes'], [])


class EligibilityTests(unittest.TestCase):
    def test_each_gate_names_itself(self):
        self.assertEqual(eligibility(option('a', 0.5, 0.5)), [])
        self.assertEqual(eligibility(option('a', None, 0.5)), ['unassessed_axis'])
        self.assertEqual(eligibility(option('a', 0.5, 0.5, support_source_ids=[])),
                         ['support_not_confirmed'])
        no_field = option('a', 0.5, 0.5)
        del no_field['challenge_source_ids']
        self.assertEqual(eligibility(no_field), ['challenge_not_reviewed'])
        self.assertEqual(eligibility(option('a', 0.5, 0.5, challenge_source_ids=['art_x'])),
                         ['applicable_challenge_unresolved'])
        self.assertEqual(eligibility(option('a', 0.5, 0.5, challenge_source_ids=['art_x'],
                                            challenge_applies=False)), [])

    def test_a_candidate_must_have_had_its_mechanism_link_reviewed(self):
        candidate = option('c', 1.0, 1.0, kind='molecule')
        self.assertEqual(eligibility(candidate), ['bridge_not_reviewed'])
        linked = option('c', 1.0, 1.0, kind='molecule',
                        targets_mechanism={'option_id': 'mechanism:x', 'reason': '이 효소를 억제한다'})
        self.assertEqual(eligibility(linked), [])

    def test_a_held_option_takes_no_part_in_the_order_and_wins_nothing(self):
        result = rank([option('graded', 1.0, 1.0, support_source_ids=[]), option('other', 0.2, 0.2)])
        self.assertEqual(result['frontier'], ['other'])
        self.assertEqual(result['edges'], [], 'a held option neither dominates nor is dominated')
        held = next(r for r in result['rows'] if r['option_id'] == 'graded')
        self.assertIs(held['comparable'], False)
        self.assertIsNone(held['tier'])
        self.assertEqual(held['comparison_profile'], {'applicability': 1.0, 'validity': 1.0},
                         'the record is kept and shown, it just does not order anything')

    def test_two_comparison_groups_are_not_ordered_against_each_other(self):
        result = rank([option('a', 1.0, 1.0, comparison_group='기전'),
                       option('b', 0.2, 0.2, comparison_group='후보')])
        self.assertEqual(result['edges'], [])
        self.assertEqual(result['pair_holds'][0]['reason'], 'different_comparison_group')

    def test_one_eligible_option_is_still_not_a_first_place(self):
        result = rank([option('a', 1.0, 1.0), option('b', 0.5, 0.5, support_source_ids=[])])
        self.assertIsNone(result['single_leader'])
        self.assertEqual(result['single_leader_withheld'], 'only_one_option_graded')

    def test_the_rules_are_stated_in_the_output(self):
        result = rank([option('a', 1.0, 1.0), option('b', 0.5, 0.5)])
        self.assertIn('적용성', result['comparison_axes_meaning'])
        self.assertIn('상쇄하지 않습니다', result['comparison_rule'])
        self.assertIn('반대 근거 검토', result['eligibility_rule'])


if __name__ == '__main__':
    unittest.main()
