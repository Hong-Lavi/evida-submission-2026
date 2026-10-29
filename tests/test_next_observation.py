"""Conditional action choice and retained native identities; entirely synthetic fixtures."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import jsonschema

from evida.next_observation import SCHEMA, select
from evida.next_observation_binding import evaluate, prepare
from evida.store import Store, dump


def problem_fixture(source=None):
    worlds = [{'id': wid, 'description': description,
               'members': [{'hypothesis_id': 'h', 'alternative_ids': [], 'part_ids': []}],
               'adequate_decision_ids': ['continue' if wid != 'input_changed' else 'repair_input']}
              for wid, description in [('contribution', 'Conditional contribution'),
                                       ('coexisting', 'Contribution with another pathway'),
                                       ('input_changed', 'Initial functional input changed')]]
    def action(cid, price, outcomes):
        return {'check_id': cid, 'available': True, 'design_validated': True, 'precision_plan_defined': True,
                'declaration_basis': 'Synthetic validation declaration only', 'precision_rule': 'Synthetic prespecified paired equivalence margin',
                'incremental_cost': price, 'shared_control_ids': ['paired'] if cid != 'repeat' else [],
                'adequate_outcome_indices': [0] if cid == 'repeat' else [0, 1],
                'predictions': [{'world_id': w['id'], 'coverage': 'complete', 'conditions_satisfied': True,
                                 'condition_basis': 'Fixed synthetic conditions', 'outcome_indices': [outcomes[i]],
                                 'origin': 'prospective', 'basis': 'Authored synthetic prediction',
                                 'source_artifact_ids': [source] if source else []} for i, w in enumerate(worlds)]}
    return {'id': 'synthetic', 'immediate_decision': 'Retain a limited contribution or check changed input',
            'declaration': {'kind': 'synthetic_fixture', 'basis': 'Software control only', 'conditions': ['All conditions are synthetic declarations.']},
            'decisions': [{'id': 'continue', 'label': 'Retain limited contribution', 'adequacy_basis': 'Conditional setup'},
                          {'id': 'repair_input', 'label': 'Review initial input', 'adequacy_basis': 'Conditional setup'}],
            'worlds': worlds, 'actions': [action('repeat', 1, [0, 0, 0]), action('function', 2, [0, 0, 1])],
            'shared_controls': [{'id': 'paired', 'cost': 1, 'declaration_basis': 'Shared paired setup'}],
            'cost_unit': 'synthetic effort', 'budget': 4, 'max_checks': 3}


def result_fixture(**changes):
    return {'message_id': 'synthetic_message', 'check_id': 'function', 'outcome_index': 0, 'context_match': True,
            'intervention_status': 'validated', 'measurement_validity': 'validated', 'precision': 'adequate',
            'assessment_basis': 'Synthetic result declaration, not a performed measurement', **changes}


def publish_fixture(store, wid, prefix='Synthetic', prediction_sources=()):
    from evida.finalization import commit
    from evida.hypothesis_review import prepare as prepare_review
    source = store.add_artifact(wid, 'Synthetic source', 'article', dump({'text': 'Synthetic development source.'}).encode(), {}, bump=False)
    problem = problem_fixture(source)
    checks = [{'id': a['check_id'], 'question': prefix + ' ' + a['check_id'] + ' question', 'purpose': 'Distinguish the next decision',
               'hypothesis_ids': ['h'], 'possible_outcomes': [{'observation': text, 'implication': 'Synthetic only'} for text in ('Preserved', 'Lost', 'Unexpected')],
               'operation': {'kind': 'external_observation', 'request': 'Synthetic measurement request', 'grounded_in': [source]}}
              for a in problem['actions']]
    loop = {'hypotheses': [{'id': 'h', 'statement': 'Synthetic conditional claim', 'expected_observation': 'Synthetic response'}],
            'next_checks': checks, 'revision_rationale': 'Synthetic software control'}
    review = {'schema_version': '1', 'causal_steps': [], 'observations': [
        {'check_id': c['id'], 'validity_requirements': ['Declared matched controls pass'],
         'precision_requirement': 'Declared paired interval meets the fixed margin',
         'outcomes': [{'outcome_index': i, 'interpretation': 'adequate_measurement'} for i in range(3)], 'predictions': []} for c in checks]}
    if prediction_sources:
        review['observations'][0]['predictions'] = [{'hypothesis_id': 'h', 'alternative_id': '',
            'outcome_indices': [0], 'coverage': 'partial', 'origin': 'previously_recorded',
            'assumptions': ['Synthetic conditions only'], 'rationale': 'Earlier source statements include counterevidence.',
            'source_ids': list(prediction_sources)}]
    rev = store.snapshot(wid)['rev']
    record = prepare_review(store, wid, rev, review, loop)
    decision, published = commit(store, wid, rev, 'synthetic-publication',
                                {'based_on_state_rev': rev, 'intent_records': [], 'research_loop': loop}, [record], [], None)
    assert published
    args = {'mode': 'plan', 'artifact_id': decision, 'source_artifact_ids': [source], 'problem': problem, 'result': None}
    return args, loop


class NextObservationTests(unittest.TestCase):
    def test_complete_native_source_history_is_not_limited_to_twelve_messages(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'test.db'); wid = store.create('Thirteen original message sources')['id']
            sources = []
            for i in range(13):
                saved = store.command(wid, store.snapshot(wid)['rev'], 'source-' + str(i), {'kind': 'message',
                    'text': 'Synthetic source statement ' + str(i) + '; keep counterevidence too.', 'synthetic': True})
                sources.append(saved['message_id'])
            args, _ = publish_fixture(store, wid, prediction_sources=sources)
            bundle = prepare(store, wid, args)
            result = evaluate(bundle)
            self.assertEqual(set(bundle['source_message_ids']), set(sources))
            self.assertEqual(len(result['source_events']), 13)
            self.assertEqual(set(result['provenance']['source_message_hashes']), set(sources))
            self.assertEqual(result['observed_events'], [])
            tampered = copy.deepcopy(bundle); tampered['source_message_ids'].append(sources[0])
            with self.assertRaises(ValueError): evaluate(tampered)

    def test_action_changes_decision_and_coexistence_is_retained(self):
        p = problem_fixture(); before = copy.deepcopy(p)
        out = select(p)
        self.assertEqual(out['summary']['selected_check_ids'], ['function'])
        self.assertEqual(out['summary']['cost'], 3)
        self.assertEqual(out['rows'][0]['retained_configuration_ids'], ['contribution', 'coexisting'])
        updated = select(p, result=result_fixture())
        self.assertEqual(updated['summary']['selection_status'], 'decision_region_reached')
        self.assertEqual(updated['summary']['retained_configuration_ids'], ['contribution', 'coexisting'])
        self.assertEqual(p, before)

    def test_failure_unknown_precision_unmeasured_and_model_gap_never_eliminate(self):
        p = problem_fixture()
        for change, status in [({'context_match': False}, 'context_unresolved'),
                               ({'intervention_status': 'failed'}, 'repair_intervention'),
                               ({'measurement_validity': 'failed'}, 'repair_readout'),
                               ({'measurement_validity': 'unknown'}, 'validity_unresolved'),
                               ({'precision': 'unknown'}, 'precision_check'),
                               ({'precision': 'insufficient'}, 'precision_check'),
                               ({'outcome_index': None}, 'conditional_plan'),
                               ({'outcome_index': 2}, 'model_gap')]:
            with self.subTest(change=change):
                out = select(p, result=result_fixture(**change))
                self.assertEqual(out['summary']['selection_status'], status)
                self.assertEqual(len(out['summary']['retained_configuration_ids']), 3)
                self.assertEqual(out['conditional_exclusions'], [])

    def test_unknown_partial_missing_and_unmet_condition_allow_whole_domain(self):
        for change in ('unknown', 'partial', 'missing', 'condition_false'):
            p = problem_fixture(); predictions = p['actions'][1]['predictions']
            if change == 'missing':
                predictions.pop()
            elif change == 'condition_false':
                predictions[-1]['conditions_satisfied'] = False
            else:
                predictions[-1]['coverage'] = change
            with self.subTest(change=change):
                out = select(p, result=result_fixture())
                self.assertEqual(len(out['summary']['retained_configuration_ids']), 3)
                self.assertEqual(out['conditional_exclusions'], [])

    def test_pairwise_overlap_is_not_a_global_common_decision(self):
        p = problem_fixture()
        p['decisions'] = [{'id': x, 'label': x, 'adequacy_basis': 'Synthetic'} for x in ('x', 'y', 'z')]
        for w, values in zip(p['worlds'], [('x', 'y'), ('y', 'z'), ('x', 'z')]):
            w['adequate_decision_ids'] = list(values)
        out = select(p)
        self.assertEqual(out['summary']['selection_status'], 'conditional_plan')
        self.assertEqual(out['summary']['selected_check_ids'], ['function'])

    def test_no_available_tool_and_zero_budget_preserve_unresolved(self):
        for how in ('available', 'budget'):
            p = problem_fixture()
            if how == 'available':p['actions'][1]['available'] = False
            else:p['budget'] = 0
            out = select(p)
            self.assertEqual(out['summary']['selection_status'], 'stop_specific_claim')
            self.assertEqual(len(out['summary']['retained_configuration_ids']), 3)

    def test_two_checks_share_one_setup_and_each_alone_is_only_partial(self):
        p = problem_fixture()
        p['worlds'] = [{'id': 'w' + str(i), 'description': 'Synthetic combination',
                        'members': [{'hypothesis_id': 'h', 'alternative_ids': [], 'part_ids': []}],
                        'adequate_decision_ids': ['d' + str(i)]} for i in range(4)]
        p['decisions'] = [{'id': 'd' + str(i), 'label': 'd' + str(i), 'adequacy_basis': 'Synthetic'} for i in range(4)]
        template = copy.deepcopy(p['actions'][1]); p['actions'] = []
        for bit in (0, 1):
            a = copy.deepcopy(template); a['check_id'] = 'bit' + str(bit)
            a['predictions'] = [{**copy.deepcopy(template['predictions'][0]), 'world_id': 'w' + str(i), 'outcome_indices': [(i >> bit) & 1]} for i in range(4)]
            p['actions'].append(a)
        p.update(budget=5, max_checks=2)
        out = select(p)
        self.assertEqual(out['summary']['selected_check_ids'], ['bit0', 'bit1'])
        self.assertEqual(out['summary']['cost'], 5)  # 2 + 2 + one shared setup
        self.assertEqual(len(out['rows']), 4)
        p['max_checks'] = 1
        self.assertEqual(select(p)['summary']['selection_status'], 'partial_only')

    def test_malformed_declarations_are_rejected_before_scientific_filtering(self):
        mutations = [lambda p: p.update(budget=float('nan')), lambda p: p.update(budget=float('inf')),
                     lambda p: p.update(budget=True), lambda p: p.update(budget=-1),
                     lambda p: p.update(max_checks=True), lambda p: p.update(max_checks=4),
                     lambda p: p['worlds'][0].update(id=''), lambda p: p['worlds'][1].update(id=p['worlds'][0]['id']),
                     lambda p: p['actions'][1].update(check_id=p['actions'][0]['check_id']),
                     lambda p: p['actions'][1].update(available='false'),
                     lambda p: p['actions'][1].update(adequate_outcome_indices=[0, 0]),
                     lambda p: p['actions'][1]['predictions'][0].update(outcome_indices=[5]),
                     lambda p: p['actions'][1]['predictions'][0].update(outcome_indices=[]),
                     lambda p: p['actions'][1]['predictions'][0].update(conditions_satisfied='yes'),
                     lambda p: p['actions'][1].update(shared_control_ids=['missing']),
                     lambda p: p['actions'][1].update(incremental_cost=1e308) or p['actions'][0].update(incremental_cost=1e308)]
        for i, mutation in enumerate(mutations):
            p = problem_fixture(); mutation(p); before = json.dumps(p, sort_keys=True)
            with self.subTest(i=i), self.assertRaises(ValueError): select(p, result=result_fixture())
            self.assertEqual(before, json.dumps(p, sort_keys=True))
        for change in ({'precision': 'sufficient'}, {'precision': None}, {'check_id': 'missing'}, {'outcome_index': True}):
            with self.subTest(change=change), self.assertRaises(ValueError): select(problem_fixture(), result=result_fixture(**change))

    def test_native_binding_is_read_only_and_transfer_tampering_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'test.db'); wid = store.create('Synthetic selection')['id']
            args, loop = publish_fixture(store, wid)
            before = store.snapshot(wid)
            jsonschema.validate(args, SCHEMA)
            bundle = prepare(store, wid, args); out = evaluate(bundle)
            self.assertEqual(before, store.snapshot(wid))
            self.assertEqual(out['checks'], [{k: c[k] for k in ('id', 'question', 'possible_outcomes')} for c in loop['next_checks']])
            self.assertFalse(out['provenance']['scientific_validation'])
            tampered = copy.deepcopy(bundle)
            tampered['artifacts'][args['artifact_id']]['content_base64'] = 'e30='
            with self.assertRaises(ValueError):evaluate(tampered)
            for mutate in [lambda a: a['problem']['actions'][1].update(check_id='wrong'),
                           lambda a: a['problem']['actions'][1].update(adequate_outcome_indices=[999]),
                           lambda a: a['problem']['worlds'][0]['members'][0].update(hypothesis_id='wrong'),
                           lambda a: a.update(result=result_fixture())]:
                changed = copy.deepcopy(args); mutate(changed)
                with self.assertRaises(ValueError): prepare(store, wid, changed)


if __name__ == '__main__':unittest.main()
