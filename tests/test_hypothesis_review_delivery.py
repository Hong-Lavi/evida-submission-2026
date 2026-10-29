"""Current authorship requirements and legacy reading; synthetic records only."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import jsonschema

from evida.contracts import model_final_decision
from evida.finalization import finalize, prepare as prepare_final
from evida.hypothesis_review import prepare, validate, view
from evida.runner import Runner
from test_experiment_is_grounded import research, with_experiment
from test_hypothesis_review import loop_fixture, review_fixture


def current_review(source):
    review = review_fixture(source)
    review.update(schema_version='2', scope={
        'hypotheses': [{'hypothesis_id': 'h1', 'status': 'reviewed',
                        'reason': 'Synthetic causal step is reviewed below.'}],
        'checks': [{'check_id': 'c1', 'status': 'reviewed',
                    'reason': 'Synthetic predictions are reviewed below.'}]})
    return review


class ReviewDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp, self.store, self.wid, self.source = research()
        self.loop = loop_fixture()
        self.review = current_review(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def bundle(self):
        decision = with_experiment(self.source, grounded_in=[])
        decision['research_loop']['next_checks'][0]['outcome_links'] = []
        review = copy.deepcopy(self.review)
        observation = review['observations'][0]
        observation['outcomes'] = [{'outcome_index': 0, 'interpretation': 'adequate_measurement'}]
        observation['predictions'] = [{'hypothesis_id': 'h1', 'alternative_id': '',
            'outcome_indices': [], 'coverage': 'unknown', 'origin': 'prospective',
            'assumptions': [], 'rationale': 'No prediction has been established in this synthetic case.',
            'source_ids': []}]
        group = review['causal_steps'][0]['evidence_groups'][0]
        group.update(anchors=[], evidence_role='unknown', text_support='unknown',
                     text_support_rationale='No retained quotation establishes the statement.',
                     causal_support='unknown', causal_support_rationale='Causality is not established.',
                     applicability='unknown', applicability_rationale='Conditions are not established.')
        return {'decision': decision, 'discovery_review': None, 'judgment_context': None,
                'hypothesis_review': review}

    def test_current_schema_and_publication_reject_null_omitted_or_v1_review_without_writes(self):
        for variant in ('null', 'omitted', 'v1'):
            with self.subTest(variant=variant):
                bundle = self.bundle()
                if variant == 'null':
                    bundle['hypothesis_review'] = None
                elif variant == 'omitted':
                    del bundle['hypothesis_review']
                else:
                    bundle['hypothesis_review'] = review_fixture(self.source)
                before = self.store.snapshot(self.wid)
                frozen = copy.deepcopy(bundle)
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(bundle, model_final_decision())
                with self.assertRaises((ValueError, jsonschema.ValidationError)):
                    prepare_final(self.store, self.wid, 1, bundle, True)
                self.assertEqual(bundle, frozen)
                self.assertEqual(self.store.snapshot(self.wid), before)

    def test_missing_duplicate_and_foreign_scope_ids_cannot_hide_unreviewed_items(self):
        for field in ('hypotheses', 'checks'):
            for variant in ('missing', 'duplicate', 'foreign'):
                with self.subTest(field=field, variant=variant):
                    review = copy.deepcopy(self.review)
                    rows = review['scope'][field]
                    if variant == 'missing':
                        rows.clear()
                    elif variant == 'duplicate':
                        rows.append(copy.deepcopy(rows[0]))
                    else:
                        rows[0]['hypothesis_id' if field == 'hypotheses' else 'check_id'] = 'foreign'
                    with self.assertRaises(ValueError):
                        validate(review, {}, self.loop)

    def test_scope_cannot_claim_reviewed_without_content_or_hide_existing_review(self):
        for field, content in (('hypotheses', 'causal_steps'), ('checks', 'observations')):
            with self.subTest(field=field):
                review = copy.deepcopy(self.review)
                review[content] = []
                with self.assertRaises(ValueError):
                    validate(review, {}, self.loop)
                review['scope'][field][0]['status'] = 'not_reviewed'
                review['scope'][field][0]['reason'] = 'This synthetic item was not examined.'
                validate(review, {}, self.loop)
                review[content] = copy.deepcopy(self.review[content])
                with self.assertRaises(ValueError):
                    validate(review, {}, self.loop)

    def test_unreviewed_and_not_applicable_require_visible_reasons_and_make_no_verdict(self):
        review = copy.deepcopy(self.review)
        review['causal_steps'] = []
        review['observations'] = []
        review['scope']['hypotheses'][0].update(status='not_reviewed', reason='Mediator evidence was not examined.')
        review['scope']['checks'][0].update(status='not_applicable', reason='This is a data-location request, not a measurement comparison.')
        frozen = copy.deepcopy(review)
        record = prepare(self.store, self.wid, 1, review, self.loop)['value']
        self.assertEqual(record['review'], frozen)
        self.assertEqual(record['summary']['declared_scope']['hypotheses']['not_reviewed'], ['h1'])
        self.assertEqual(record['summary']['eligible_pair_outcomes'], 0)
        self.assertEqual(record['observation_checks'][0]['status'], 'not_reviewed')
        review['scope']['checks'][0]['reason'] = '  '
        with self.assertRaises(ValueError):
            validate(review, {}, self.loop)

    def test_reviewed_observation_accounts_for_every_outcome_and_explanation(self):
        for key in ('outcomes', 'predictions'):
            review = copy.deepcopy(self.review)
            review['observations'][0][key].pop()
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(review, {}, self.loop)

    def test_empty_sources_and_unknown_assessments_publish_without_invented_support(self):
        bundle = self.native_bundle()
        jsonschema.validate(bundle, model_final_decision())
        frozen = copy.deepcopy(bundle)
        aid, published = finalize(self.store, self.wid, 1, 'synthetic-review', bundle, True, [], None,
                                  require_intent_review=True)
        self.assertTrue(published)
        current = view(self.store, self.wid, self.store.snapshot(self.wid))
        self.assertEqual(current['published_decision_id'], aid)
        self.assertEqual(current['review'], frozen['hypothesis_review'])
        self.assertEqual(bundle, frozen)
        group = current['causal_step_checks'][0]['evidence_groups'][0]
        self.assertFalse(group['all_anchors_verified'])
        self.assertFalse(group['causal_support_automatically_verified'])
        self.assertEqual(group['issues'], ['no_anchors'])
        self.assertEqual(current['summary']['verified_anchors'], 0)
        self.assertEqual(current['summary']['eligible_pair_outcomes'], 0)
        self.assertEqual(current['observation_checks'][0]['explanations'][0]['source_basis'], 'not_named')

    def native_bundle(self):
        """Current native input with server-bound framing; no invented intent or support."""
        from evida.intent_dependencies import consumers, view as intent_view
        runner = Runner.__new__(Runner)
        runner.store = self.store
        frame = {'intent_records': [], 'current_question': 'Synthetic review coverage question',
                 'hypotheses': [], 'task_brief': [], 'questions': []}
        def declared(values, question_only=False):
            return {'uses': [{'consumer_kind': kind, 'consumer_id': cid, 'intent_ids': [],
                             'reason': 'Intent linkage is unknown in this synthetic scientific-review fixture.'}
                            for kind, cid in values],
                    'reassessments': [{k: c[k] for k in ('consumer_kind', 'consumer_id')} |
                        {'outcome': 'unknown', 'reason': 'This fixture tests source support; intent impact remains unknown.'}
                        for c in intent_view(self.store, self.wid)['required_reassessments']
                        if not question_only or c['consumer_kind'] == 'question']}
        frame['intent_review'] = declared(consumers(frame), question_only=True)
        runner.frame(self.wid, 1, frame, require_intent_review=True)
        bundle = self.bundle()
        bundle['intent_review'] = declared(consumers(frame, bundle['decision']))
        bundle['reassessment_review_ids'] = []
        from planner_fixtures import _active_reasoning_core, synthetic_reasoning_design
        core = _active_reasoning_core(self.store, self.wid)
        if core is not None:
            for hypothesis in bundle['decision']['research_loop']['hypotheses']:
                hypothesis.setdefault('reasoning_design', synthetic_reasoning_design(core))
        for check in bundle['decision']['research_loop']['next_checks']:
            check['measurement_selection_id'] = None
            if core is not None:
                check.setdefault('design_hypothesis_id', check['hypothesis_ids'][0]
                    if check['operation']['kind'] == 'external_observation' and check['hypothesis_ids'] else None)
        return bundle

    def test_empty_usage_only_decision_needs_no_invented_causal_claims(self):
        bundle = self.bundle()
        bundle['decision']['research_loop'].update(hypotheses=[], next_checks=[])
        bundle['hypothesis_review'] = {'schema_version': '2', 'causal_steps': [], 'observations': [],
                                      'scope': {'hypotheses': [], 'checks': []}}
        proposal, records = prepare_final(self.store, self.wid, 1, bundle, True)
        self.assertEqual(proposal, bundle['decision'])
        self.assertEqual(records[0]['value']['summary']['causal_steps'], 0)

    def test_old_null_decision_is_explicit_replay_only_and_still_readable(self):
        bundle = self.bundle()
        bundle['hypothesis_review'] = None
        aid, published = finalize(self.store, self.wid, 1, 'legacy-replay', bundle, True, [], None,
                                  legacy_response=True)
        self.assertTrue(published)
        state = self.store.snapshot(self.wid)
        self.assertEqual(state['decision'], bundle['decision'])
        self.assertEqual(json.loads(self.store.artifact(self.wid, aid)['content']), bundle['decision'])
        self.assertIsNone(view(self.store, self.wid, state))

    def test_current_review_cannot_attach_to_another_decision_even_with_identical_loop(self):
        bundle = self.bundle()
        finalize(self.store, self.wid, 1, 'first', bundle, True, [], None)
        before = self.store.snapshot(self.wid)
        current = view(self.store, self.wid, before)
        from evida.store import dump
        aid = self.store.add_artifact(self.wid, 'Synthetic other decision', 'decision_proposal',
            dump(bundle['decision']).encode(), {'finalization_records': {'hypothesis_review': current['artifact_id']}}, bump=False)
        self.store.publish_decision(self.wid, 1, bundle['decision'], aid)
        shown = view(self.store, self.wid, self.store.snapshot(self.wid))
        self.assertEqual(shown['status'], 'binding_mismatch')
        self.assertIsNone(shown['review'])

    def test_current_context_delivers_authorship_duty_without_a_model_or_new_source_request(self):
        runner = Runner.__new__(Runner)
        runner.root = Path(__file__).resolve().parents[1]
        runner.store = self.store
        context = runner.model_context(self.wid, 1, True, force_full=True)
        contract = context['FINALIZATION']
        self.assertNotIn('hypothesis_review(nullable)', contract['response_shape'])
        self.assertIn('every exact final ID', contract['hypothesis_review']['responsibility'])
        self.assertIn('measurement time', contract['hypothesis_review']['causal_conditions'])
        self.assertEqual(self.store.snapshot(self.wid)['jobs'], [])

    def test_actual_runner_uses_v2_request_and_cannot_publish_null_or_bypass_with_legacy(self):
        from evida.store import dump
        from test_requested_operation_correction import start_runner

        store, wid = self.store, self.wid
        class OfflineResponse:
            model, effort = 'synthetic-model', 'synthetic'
            def __init__(self, value):
                self.value, self.calls = value, []
            def status(self):
                return {'available': True, 'transport_mode': 'offline_test'}
            def approved_models(self):
                return [self.model]
            def request(self, payload, model=None):
                self.calls.append(payload)
                # The real start has now saved the actual protocol. Adapt only
                # synthetic interface fields, keeping null/legacy review invalid.
                from planner_fixtures import _active_reasoning_core, synthetic_reasoning_design
                value = copy.deepcopy(self.value)
                core = _active_reasoning_core(store, wid)
                if core is not None:
                    for hypothesis in value['decision']['research_loop']['hypotheses']:
                        hypothesis.setdefault('reasoning_design', synthetic_reasoning_design(core))
                    for check in value['decision']['research_loop']['next_checks']:
                        check.setdefault('design_hypothesis_id', check['hypothesis_ids'][0]
                            if check['operation']['kind'] == 'external_observation' and check['hypothesis_ids'] else None)
                self.last_value = value
                return ({'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': dump(value)}]}]},
                        {'requested_model': self.model, 'status': 'COMPLETED', 'semantic_type': 'synthetic_test'})

        root = Path(__file__).resolve().parents[1]
        runner = start_runner(self.store, root)
        runner.prompt = (root/'configs/planner.md').read_text()
        invalid = self.native_bundle()
        invalid['hypothesis_review'] = None
        runner.gateway = OfflineResponse(invalid)
        jid = runner.start(self.wid, 1, 'planner', {})
        with patch('evida.runner.MAXIMUM_DECISION_CORRECTIONS', 0):
            runner.run_planner(jid)
        failed = next(j for j in self.store.snapshot(self.wid)['jobs'] if j['id'] == jid)
        self.assertEqual(failed['status'], 'failed')
        self.assertIsNone(self.store.snapshot(self.wid)['decision'])
        self.assertEqual(len(runner.gateway.calls), 1)
        self.assertIsNone(runner.gateway.last_value['hypothesis_review'])
        self.assertTrue(all('reasoning_design' in h for h in
                            runner.gateway.last_value['decision']['research_loop']['hypotheses']))
        self.assertEqual(runner.gateway.calls[0]['text']['format']['schema']['properties']
                         ['hypothesis_review']['properties']['schema_version']['enum'], ['2'])
        runner.gateway = OfflineResponse(self.native_bundle())
        jid = runner.start(self.wid, 1, 'planner', {})
        runner.run_planner(jid)
        state = self.store.snapshot(self.wid)
        passed = next(j for j in state['jobs'] if j['id'] == jid)
        self.assertEqual(passed['status'], 'succeeded', passed.get('error'))
        self.assertEqual(len(runner.gateway.calls), 1)
        self.assertEqual(view(self.store, self.wid, state)['review']['schema_version'], '2')
        self.assertEqual(state['review_status'], 'needs_review')  # Unknown intent linkage remains visible.


if __name__ == '__main__':
    unittest.main()
