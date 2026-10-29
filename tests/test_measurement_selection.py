"""Independent boundary controls and hand arithmetic; no new science measurements."""
import copy
from decimal import Decimal
import unittest

from evida import measurement_selection as m


def ref(aid='synthetic_source', pointer='/rows/0'):
    return {'artifact_id': aid, 'sha256': 'a' * 64, 'json_pointer': pointer}


def context_values():
    return {'target_id': 'abstract_target', 'endpoint': 'rate', 'units': 'h-1',
            'matrix': 'declared_matrix', 'construct': 'construct_v1',
            'measurement_mechanism': 'time_curve', 'concentration': 'declared_series', 'time': 'declared_times'}


def correspondence():
    return {'values': context_values(), 'field_refs': {k: [ref()] for k in context_values()}}


def observation(cid, value, relation='=', **changes):
    return {'id': 'o_' + cid, 'lineage_id': 'original_' + cid, 'candidate_id': cid,
            'structure_id': 'structure_' + cid, 'material_id': 'lot_' + cid,
            'context': correspondence(), 'source_refs': [ref(pointer='/measurements/' + cid)], 'observed': True,
            'valid': True, 'precise_enough': True, 'relation': relation, 'value': value, **changes}


def spec():
    condition = {'id': 'contract1', 'revision': 'v1', 'required_fields': sorted(context_values()), **correspondence()}
    fields = {k: {'description': 'Declared synthetic ' + k, 'basis': 'design',
                  'source_refs': [ref('synthetic_design')], 'ready': True}
              for k in ('specimen', 'controls', 'readout', 'precision')}
    branches = [{'id': k, 'kind': k, 'condition': 'Declared ' + k, 'action': 'Review or repair',
                 'explanation_ids': ['E1'], 'scientific_judgment': 'hold' if k in
                 ('invalid_measurement', 'insufficient_precision') else 'review'}
                for k in ('valid_improvement', 'valid_no_improvement', 'invalid_measurement', 'insufficient_precision')]
    return {'schema_version': 1, 'purpose': 'ranking_evaluation', 'context': condition,
            'candidates': [{'id': cid, 'structure_id': 'structure_' + cid, 'parent_group_id': 'group_' + cid,
                            'origin': 'original', 'parent_candidate_id': None, 'identity_refs': [ref()],
                            'material': {'id': 'lot_' + cid, 'ready': True, 'identity_verified': True, 'source_refs': [ref()]},
                            'measurement_context': correspondence(), 'observations': []} for cid in 'ABC'],
            'arms': [{'id': 'compute', 'kind': 'prediction', 'reason': 'Frozen external synthetic prediction',
                      'source_refs': [ref('prediction')], 'scores': {'A': 3, 'B': 2, 'C': 1},
                      'prediction_context': correspondence()},
                     {'id': 'simple', 'kind': 'source_evidence', 'reason': 'Declared fixed simple control',
                      'source_refs': [ref('rule')], 'order': ['B', 'C', 'A']}],
            'budget': {'B': 2, 'maximum_cost': 7, 'cost_unit': 'synthetic_slots'},
            'cost_items': [{'id': 'curve_' + cid, 'kind': 'measurement', 'candidate_ids': [cid],
                           'cost': 2, 'ready': True, 'source_refs': [ref()]} for cid in 'ABC'] +
                          [{'id': 'vehicle', 'kind': 'control', 'candidate_ids': [], 'cost': 1,
                            'ready': True, 'source_refs': [ref()]}],
            'utility': {'direction': 'lower', 'minimum_difference': 0, 'top_q': 1},
            'inspection_ledger': [{'status': 'synthetic_controls_only'}],
            'next_check': {**fields, 'engine2_refs': [{'id': 'E1', 'revision': 'draft_v1', 'source_ref': ref('review_draft')}],
                           'branches': branches}}


def gold(plan, rows):
    return {'schema_version': 1, 'plan_seal': plan['seal'], 'inspection_status': 'retrospective', 'rows': rows}


class SelectionBoundaryTests(unittest.TestCase):
    def test_source_order_and_score_ties_are_reproducible(self):
        first = spec()
        first['arms'][0]['scores'] = dict.fromkeys('ABC', 1)
        second = copy.deepcopy(first)
        second['candidates'].reverse()
        second['cost_items'].reverse()
        second['context']['required_fields'].reverse()
        a, b = m.freeze_plan(first), m.freeze_plan(second)
        self.assertEqual(a['seal'], b['seal'])
        self.assertEqual(a['arms'][0]['planned_ids'], ['A', 'B'])
        self.assertEqual(a['planned_measurement_union'], ['A', 'B', 'C'])

    def test_missing_material_keeps_planned_comparison_without_execution(self):
        s = spec()
        s['candidates'][0]['material'] = {'id': None, 'ready': False, 'identity_verified': False, 'source_refs': []}
        p = m.freeze_plan(s)
        self.assertEqual(p['arms'][0]['planned_ids'], ['A', 'B'])
        self.assertEqual(p['arms'][0]['physically_ready_ids'], ['B'])
        self.assertIn('material:A', m.handoff(p)['unresolved_gates'])
        self.assertEqual(m.evaluate(p)['ranking_value'], 'ranking_value_unproven')

    def test_historical_mismatch_does_not_block_new_measurement(self):
        s = spec()
        old = observation('A', 3)
        old['context']['values']['matrix'] = 'different_matrix'
        s['candidates'][0]['observations'] = [old]
        p = m.freeze_plan(s)
        row = p['candidate_reviews'][0]
        self.assertTrue(row['physically_ready'])
        self.assertFalse(row['historical_label_reviews'][0]['eligible'])
        self.assertEqual(row['historical_label_reviews'][0]['condition_review']['fields']['matrix']['status'], 'mismatch')

    def test_both_empty_never_match_and_nonempty_without_refs_stays_unknown(self):
        for empty in (None, '', [], {}, '  '):
            s = spec()
            s['context']['values']['construct'] = empty
            s['candidates'][0]['measurement_context']['values']['construct'] = empty
            p = m.freeze_plan(s)
            self.assertEqual(p['candidate_reviews'][0]['condition_review']['fields']['construct']['status'], 'unknown')
        s = spec()
        s['candidates'][0]['measurement_context']['field_refs']['time'] = []
        self.assertFalse(m.freeze_plan(s)['candidate_reviews'][0]['physically_ready'])

    def test_parent_generated_labels_and_replicated_lineage_are_not_gold(self):
        s = spec()
        child = s['candidates'][0]
        child.update(origin='generated', parent_candidate_id='B', parent_group_id='group_B')
        child['observations'] = [observation('B', 3)]
        p = m.freeze_plan(s)
        self.assertFalse(p['candidate_reviews'][0]['historical_label_reviews'][0]['eligible'])
        s = spec()
        for row in s['candidates'][:2]:
            row['observations'] = [observation(row['id'], 3, lineage_id='same_original')]
        p = m.freeze_plan(s)
        self.assertTrue(all(not x['historical_label_reviews'][0]['eligible'] for x in p['candidate_reviews'][:2]))
        p = m.freeze_plan(spec())
        with self.assertRaisesRegex(ValueError, 'original observation'):
            m.evaluate(p, gold(p, [observation('A', 1, lineage_id='x'), observation('C', 4, lineage_id='x')]))

    def test_cost_union_controls_and_missing_items_not_hidden(self):
        p = m.freeze_plan(spec())
        self.assertEqual(p['cost']['total'], '7')  # A,B,C once each plus vehicle, not four candidates.
        self.assertEqual(p['cost']['candidate_B_per_arm'], 2)
        s = spec()
        s['budget']['maximum_cost'] = 6
        self.assertIn('physical_budget_exceeded', m.handoff(m.freeze_plan(s))['unresolved_gates'])
        s = spec()
        s['cost_items'][-1]['source_refs'] = []
        self.assertIn('physical_item:vehicle', m.handoff(m.freeze_plan(s))['unresolved_gates'])
        s = spec()
        s['cost_items'].pop(0)
        with self.assertRaisesRegex(ValueError, 'cost coverage'):
            m.freeze_plan(s)

    def test_multiple_lots_do_not_inflate_distinct_compound_denominator(self):
        s = spec()
        s['candidates'][1]['structure_id'] = s['candidates'][0]['structure_id']
        self.assertNotEqual(s['candidates'][0]['material']['id'], s['candidates'][1]['material']['id'])
        with self.assertRaisesRegex(ValueError, 'distinct compound pool'):
            m.freeze_plan(s)

    def test_wrong_prediction_condition_and_short_pool_do_not_refill(self):
        s = spec()
        s['arms'][0]['prediction_context']['values']['endpoint'] = 'binding'
        p = m.freeze_plan(s)
        self.assertEqual(p['arms'][0]['status'], 'unavailable_no_refill')
        self.assertIsNone(m.evaluate(p)['contrast']['lower'])
        s = spec()
        s['budget']['B'] = 4
        self.assertTrue(all(not x['planned_ids'] for x in m.freeze_plan(s)['arms']))

    def test_usable_prediction_does_not_repair_failed_source_label_or_refill(self):
        s = spec()
        old = observation('B', 1)
        old['context']['values']['endpoint'] = 'binding_endpoint'
        s['candidates'][1]['observations'] = [old]
        p = m.freeze_plan(s)
        self.assertEqual(p['arms'][0]['status'], 'frozen')
        self.assertEqual(p['arms'][1]['planned_ids'], ['B', 'C'])
        self.assertFalse(p['candidate_reviews'][1]['historical_label_reviews'][0]['eligible'])
        r = m.evaluate(p, gold(p, [old, observation('A', 2)]))
        self.assertEqual(r['ranking_value'], 'ranking_value_unproven')
        self.assertEqual(r['required_measurements'], ['C'])
        self.assertEqual(r['fixed_B'], 2)

    def test_tampering_and_cross_plan_outcomes_require_review(self):
        p = m.freeze_plan(spec())
        p['arms'][0]['planned_ids'].reverse()
        with self.assertRaisesRegex(ValueError, 'changed after sealing'):
            m.evaluate(p)
        p = m.freeze_plan(spec())
        out = gold(p, [])
        out['plan_seal'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'exact frozen plan'):
            m.evaluate(p, out)


class OutcomeBoundaryTests(unittest.TestCase):
    def test_signed_contrast_uses_original_B_and_cancels_missing_shared_candidate(self):
        p = m.freeze_plan(spec())
        r = m.evaluate(p, gold(p, [observation('A', 2), observation('C', 8)]))
        # Lower rate is better; (-2 - -8)/2 = +3. B is shared and cancels without measurement.
        self.assertEqual(r['contrast']['lower'], '3')
        self.assertEqual(r['contrast']['upper'], '3')
        self.assertFalse(r['whole_pool_gold'])
        self.assertIsNone(r['top_set_capture'])
        self.assertEqual(r['fixed_B'], 2)
        self.assertEqual(r['differing_ids'], ['A', 'C'])

    def test_missing_failed_condition_or_imprecise_does_not_claim_advantage(self):
        p = m.freeze_plan(spec())
        for rows in ([observation('A', 2)],
                     [observation('A', 2), observation('C', 8, valid=False)],
                     [observation('A', 2), observation('C', 8, precise_enough=False)]):
            r = m.evaluate(p, gold(p, rows))
            self.assertEqual(r['ranking_value'], 'ranking_value_unproven')
        wrong = observation('C', 8)
        wrong['context']['values']['time'] = 'different_time'
        r = m.evaluate(p, gold(p, [observation('A', 2), wrong]))
        self.assertIsNone(r['contrast']['lower'])
        self.assertEqual(r['required_measurements'], ['C'])

    def test_censoring_propagates_signed_bounds_without_fake_CI(self):
        s = spec()
        s['utility']['bounds'] = [-10, 0]
        p = m.freeze_plan(s)
        r = m.evaluate(p, gold(p, [observation('A', 2, '<='), observation('C', 8, '>=')]))
        self.assertEqual((r['contrast']['lower'], r['contrast']['upper']), ('3', '5'))
        self.assertEqual(r['status'], 'finite_pool_identification_bounds')
        self.assertIn('not statistical confidence', r['contrast']['meaning'])
        r = m.evaluate(p, gold(p, [observation('A', 2)]))
        self.assertEqual((r['contrast']['lower'], r['contrast']['upper']), ('-1', '4'))
        self.assertEqual(r['ranking_value'], 'ranking_value_unproven')

    def test_identical_choice_zero_even_without_labels_is_not_ranking_proof(self):
        s = spec()
        s['arms'][1]['order'] = ['A', 'B', 'C']
        r = m.evaluate(m.freeze_plan(s))
        self.assertEqual(r['status'], 'zero_by_identical_selection')
        self.assertEqual(r['contrast']['lower'], '0')
        self.assertEqual(r['ranking_value'], 'ranking_value_unproven')

    def test_top_capture_requires_entire_pool_and_fractional_boundary_ties(self):
        p = m.freeze_plan(spec())
        rows = [observation('A', 2), observation('B', 2), observation('C', 8)]
        r = m.evaluate(p, gold(p, rows))
        self.assertTrue(r['whole_pool_gold'])
        self.assertEqual(r['top_set_capture'], {'compute': '1.0', 'simple': '0.5'})
        rows[-1]['relation'] = '>'
        self.assertIsNone(m.evaluate(p, gold(p, rows))['top_set_capture'])

    def test_long_decimal_direction_does_not_round_to_equality(self):
        p = m.freeze_plan(spec())
        r = m.evaluate(p, gold(p, [observation('A', '1.00000000000000000000000000000000000000001'),
                                 observation('C', '1.00000000000000000000000000000000000000003')]))
        self.assertEqual(Decimal(r['contrast']['lower']), Decimal('1E-41'))

    def test_unobserved_zero_is_not_a_measured_zero(self):
        p = m.freeze_plan(spec())
        r = m.evaluate(p, gold(p, [observation('A', 0, observed=False), observation('C', 8)]))
        self.assertEqual(r['required_measurements'], ['A'])
        self.assertEqual(r['ranking_value'], 'ranking_value_unproven')

    def test_copied_source_pointer_cannot_create_two_independent_labels(self):
        p = m.freeze_plan(spec())
        rows = [observation('A', 2), observation('C', 8)]
        rows[1]['source_refs'] = copy.deepcopy(rows[0]['source_refs'])
        with self.assertRaisesRegex(ValueError, 'source observation pointer'):
            m.evaluate(p, gold(p, rows))

    def test_unready_precision_or_control_keeps_finite_contrast_unproven(self):
        s = spec()
        s['next_check']['precision']['ready'] = False
        p = m.freeze_plan(s)
        r = m.evaluate(p, gold(p, [observation('A', 2), observation('C', 8)]))
        self.assertEqual(r['contrast']['lower'], '3')
        self.assertEqual(r['ranking_value'], 'ranking_value_unproven')

    def test_source_design_and_invalid_precision_branches_preserved(self):
        s = spec()
        s['next_check']['specimen']['basis'] = 'source'
        s['next_check']['precision']['ready'] = False
        h = m.handoff(m.freeze_plan(s))
        self.assertEqual(h['status'], 'preparation_required')
        self.assertEqual(h['next_check']['specimen']['basis'], 'source')
        self.assertEqual(h['next_check']['readout']['basis'], 'design')
        s['next_check']['branches'][2]['scientific_judgment'] = 'review'
        with self.assertRaisesRegex(ValueError, 'cannot refute biology'):
            m.handoff(m.freeze_plan(s))

    def test_malformed_booleans_nonfinite_values_and_unknown_fields_rejected(self):
        for mutation in ('boolbudget', 'nanprediction', 'rawgoldfield', 'badref'):
            s = spec()
            if mutation == 'boolbudget': s['budget']['B'] = True
            if mutation == 'nanprediction': s['arms'][0]['scores']['A'] = float('nan')
            if mutation == 'rawgoldfield': s['gold'] = {'A': 1}
            if mutation == 'badref': s['arms'][0]['source_refs'][0]['sha256'] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                m.freeze_plan(s)


if __name__ == '__main__':
    unittest.main()
