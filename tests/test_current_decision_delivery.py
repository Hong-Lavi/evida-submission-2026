"""Current model requests retain actionable references; old records still load."""
import copy
import unittest

import jsonschema

from evida import contracts
from evida.discovery import overview, record_review
from evida.research_loop import validate_loop, validate_scope_targets
from test_experiment_is_grounded import research, with_experiment


class CurrentDecisionDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp, self.store, self.wid, self.aid = research()

    def tearDown(self):
        self.temp.cleanup()

    def schema(self):
        # Exercise the previously transmitted schema when reproducing this bug.
        return getattr(contracts, 'model_final_decision', lambda: contracts.FINAL_DECISION)()

    def current(self, bundle):
        # This fixture tests source/outcome fields, not intent interpretation.
        # Supply the current delivery contract with explicit unknown linkage.
        value = copy.deepcopy(bundle)
        loop = value['decision']['research_loop']
        for check in loop['next_checks']:
            check.setdefault('measurement_selection_id', None)
        consumers = [('question', 'current_question'), ('recommendation', 'recommendation')]
        consumers += [('hypothesis', h['id']) for h in loop['hypotheses']]
        consumers += [('check', c['id']) for c in loop['next_checks']]
        value['intent_review'] = {'uses': [
            {'consumer_kind': kind, 'consumer_id': cid, 'intent_ids': [],
             'reason': 'Synthetic source/outcome delivery fixture; intent linkage is not assessed.'}
            for kind, cid in consumers], 'reassessments': []}
        value['reassessment_review_ids'] = []
        return value

    def bundle(self, sources=True):
        decision = with_experiment(self.aid, **({'grounded_in': [self.aid]} if sources else {}))
        check = decision['research_loop']['next_checks'][0]
        check['outcome_links'] = [{'outcome_index': 0, 'effects': [{
            'hypothesis_id': 'h1', 'part_ids': [], 'alternative_ids': [],
            'relation': 'supports', 'rationale': 'Synthetic whole-hypothesis comparison.'}],
            'followup_check_ids': []}]
        return {'decision': decision, 'discovery_review': None, 'judgment_context': None,
                'hypothesis_review': {'schema_version': '2', 'causal_steps': [], 'observations': [],
                    'scope': {'hypotheses': [{'hypothesis_id': 'h1', 'status': 'not_reviewed',
                                             'reason': 'Synthetic delivery test does not assess causality.'}],
                              'checks': [{'check_id': 'c1', 'status': 'not_reviewed',
                                          'reason': 'Synthetic delivery test does not assess predictions.'}]}}}

    def test_current_request_requires_source_field_but_history_remains_valid(self):
        bundle = self.bundle(sources=False)
        jsonschema.validate({**bundle, 'hypothesis_review': None}, contracts.REVIEWED_FINAL_DECISION)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(self.current(bundle), self.schema())

    def test_explicit_empty_sources_remain_a_valid_new_proposal(self):
        bundle = self.bundle()
        bundle['decision']['research_loop']['next_checks'][0]['operation']['grounded_in'] = []
        jsonschema.validate(self.current(bundle), self.schema())
        validate_loop(bundle['decision']['research_loop'], self.store.snapshot(self.wid))

    def test_current_request_requires_outcome_field_with_empty_list_allowed(self):
        bundle = self.bundle()
        check = bundle['decision']['research_loop']['next_checks'][0]
        del check['outcome_links']
        jsonschema.validate({**bundle, 'hypothesis_review': None}, contracts.REVIEWED_FINAL_DECISION)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(self.current(bundle), self.schema())
        check['outcome_links'] = []
        jsonschema.validate(self.current(bundle), self.schema())

    def test_whole_hypothesis_outcome_needs_no_invented_parts(self):
        bundle = self.bundle()
        jsonschema.validate(self.current(bundle), self.schema())
        validate_loop(bundle['decision']['research_loop'], self.store.snapshot(self.wid))

    def test_legacy_bundle_still_loads_without_new_review_field(self):
        bundle = self.bundle()
        del bundle['hypothesis_review']
        jsonschema.validate(bundle, contracts.FINAL_DECISION)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(self.current(bundle), self.schema())

    def test_invalid_part_feedback_names_valid_parts_without_rewriting(self):
        hypotheses = [{'id': 'h1', 'assessment_scope': {'parts': [{'id': 'identity'}]}}]
        before = copy.deepcopy(hypotheses)
        with self.assertRaises(ValueError) as caught:
            validate_scope_targets([{'hypothesis_id': 'h1', 'part_ids': ['old-part']}], hypotheses, ['h1'])
        self.assertIn('old-part', str(caught.exception))
        self.assertIn('identity', str(caught.exception))
        self.assertEqual(hypotheses, before)

    def test_unrecommended_mechanism_and_approach_ids_reach_current_context(self):
        options = [{'option_id': kind + ':fixture', 'kind': kind, 'label': kind,
                    'description': 'Synthetic retained research path', 'source_ids': [self.aid]}
                   for kind in ('mechanism', 'approach')]
        assessment = {'option_id': 'mechanism:fixture', 'status': 'needs_evidence',
                      'priority': None, 'comparison_group': 'fixture', 'reason': 'Needs a matched assay',
                      'support_source_ids': [self.aid], 'challenge_source_ids': [],
                      'uncertainties': ['assay pending'], 'next_action': 'Measure the pair'}
        record_review(self.store, self.wid, 1, 'fixture', {'question': 'fixture',
                      'new_options': options, 'assessments': [assessment], 'unsearched_scope': []})
        shown = overview(self.store, self.wid)
        self.assertEqual(shown['recommendations'], [])
        pool = {o['option_id']: o for o in shown.get('mechanisms_and_approaches', [])}
        self.assertEqual(set(pool), {'mechanism:fixture', 'approach:fixture'})
        self.assertEqual(pool['mechanism:fixture']['assessment']['reason'], assessment['reason'])
        self.assertIsNone(pool['approach:fixture']['assessment'])
        self.assertEqual(pool['mechanism:fixture']['assessment']['support_source_ids'], [self.aid])
        self.assertTrue(pool['mechanism:fixture']['sources'])

    def test_model_schema_does_not_mutate_legacy_contract(self):
        before = copy.deepcopy(contracts.FINAL_DECISION)
        schema = self.schema()
        schema['properties']['decision']['properties']['based_on_state_rev']['description'] = 'local mutation'
        self.assertEqual(contracts.FINAL_DECISION, before)

    def test_observation_instructions_stay_on_the_observation_request(self):
        schema = self.schema()
        decision = schema['properties']['decision']['properties']
        self.assertNotIn('description', decision['recommendation'])
        self.assertNotIn('description', decision['intent_records']['items']['properties']['id'])
        for variant in decision['research_loop']['properties']['next_checks']['items']['anyOf']:
            for operation in variant['properties']['operation']['anyOf']:
                if operation['properties']['kind'].get('enum') == ['external_observation']:
                    request = operation['properties']['request']
                    self.assertIn('observation unit', request['description'])
        request['description'] = 'Local observation instruction'
        self.assertNotIn('description', decision['recommendation'])


if __name__ == '__main__':
    unittest.main()
