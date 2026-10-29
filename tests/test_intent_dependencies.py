"""Synthetic dependency/transaction tests. No model, network or science claims."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import jsonschema

from evida.contracts import FRAME, model_final_decision, model_functions
from evida.finalization import commit, finalize, prepare
from evida.intent_dependencies import consumers, digest, input_snapshot, records, view
from evida.model_context import delivered_intent_snapshot, model_json
from evida.runner import Runner
from evida.store import Conflict, Store, dump
from test_integrity import proposal

ROOT = Path(__file__).resolve().parents[1]


class IntentDependencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'state.db')
        self.wid = self.store.create('Synthetic intent dependency fixture')['id']
        self.runner = Runner(ROOT, self.store, None, Path(self.tmp.name) / 'attempts')
        self.intents = [{'id': 'goal', 'label': 'Goal', 'text': 'Long-term urate reduction',
                         'origin': 'inferred', 'source_refs': []}]

    def tearDown(self):
        self.tmp.cleanup()

    def scope(self):
        return view(self.store, self.wid)

    def declaration(self, values, *, frame=False, ids=None, outcome=None):
        scope = self.scope()
        inputs = ids if ids is not None else list(scope['input_snapshot']['intents']) or ['goal']
        uses = [{'consumer_kind': kind, 'consumer_id': cid, 'intent_ids': inputs,
                 'reason': 'Synthetic declaration: this goal sets the endpoint.'} for kind, cid in values]
        reassessments = []
        for item in scope['required_reassessments']:
            if frame and item['consumer_kind'] != 'question':
                continue
            key = item['consumer_kind'], item['consumer_id']
            result = ('removed' if key not in values else
                      'retained' if item.get('content_sha256') == digest(values[key]) else 'changed')
            reassessments.append({'consumer_kind': key[0], 'consumer_id': key[1],
                'outcome': outcome or result, 'reason': 'Synthetic reassessment under the current conditions.'})
        return {'uses': uses, 'reassessments': reassessments}

    def frame(self, question='Which intervention reduces urate?', ids=None, outcome=None):
        state = self.store.snapshot(self.wid)
        args = {'intent_records': state['intent'] or self.intents, 'current_question': question,
                'hypotheses': [], 'task_brief': [], 'questions': []}
        args['intent_review'] = self.declaration(consumers(args), frame=True, ids=ids, outcome=outcome)
        self.runner.frame(self.wid, state['rev'], args, require_intent_review=True,
                          expected_intent_snapshot=input_snapshot(state)['snapshot_sha256'])
        return args

    def bundle(self, recommendation='Compare urate lowering mechanisms', ids=None, outcome=None):
        state = self.store.snapshot(self.wid)
        p = proposal(state['rev'])
        p['intent_records'] = copy.deepcopy(state['intent'] or self.intents)
        p['recommendation'] = recommendation
        frame = next(e['body'] for e in reversed(state['events']) if e['kind'] == 'work_framed')
        return {'decision': p, 'discovery_review': None, 'judgment_context': None,
                'hypothesis_review': {'schema_version': '2', 'causal_steps': [], 'observations': [],
                                      'scope': {'hypotheses': [], 'checks': []}},
                'intent_review': self.declaration(consumers(frame, p), ids=ids, outcome=outcome)}

    def publish(self, value=None):
        value = value or self.bundle()
        return finalize(self.store, self.wid, self.store.snapshot(self.wid)['rev'], 'synthetic-job',
                        value, True, [], None, require_intent_review=True,
                        expected_intent_snapshot=self.scope()['input_snapshot']['snapshot_sha256'])

    def edit(self, text='Acute MSU inflammation', rows=None):
        state = self.store.snapshot(self.wid)
        changed = copy.deepcopy(state['intent']) if rows is None else rows
        if rows is None:
            changed[0]['text'] = text
        return self.store.command(self.wid, state['rev'], f'edit-{state["rev"]}', {
            'kind': 'intent_edit', 'base_records': state['intent'], 'records': changed})

    def test_first_question_is_required_and_hashes_are_server_bound(self):
        self.assertTrue(self.scope()['question_reassessment_required'])
        self.assertEqual(self.scope()['required_reassessments'][0]['trigger'], 'consumption_history_unknown')
        self.frame()
        aid, published = self.publish()
        self.assertTrue(published)
        scope = self.scope()
        self.assertFalse(scope['question_reassessment_required'])
        self.assertEqual(scope['prior_record_status'], 'available')
        consumer = scope['latest_consumers'][0]
        self.assertEqual(consumer['inputs'][0]['content_sha256'], digest(self.intents[0]))
        self.assertEqual(consumer['inputs'][0]['state_revision'], 1)
        self.assertEqual(consumer['reason_origin'], 'model_declared')
        saved = json.loads(self.store.artifact(self.wid, scope['prior_record_id'])['content'])
        self.assertEqual(saved['decision_id'], aid)
        self.assertEqual(saved['decision_sha256'], self.store.artifact(self.wid, aid)['sha256'])

    def test_goal_edit_invalidates_question_and_recommendation_but_preserves_originals(self):
        self.frame(); first, _ = self.publish()
        original = self.store.artifact(self.wid, first)['content']
        self.edit()
        scope = self.scope()
        self.assertEqual(scope['changed_intent_ids'], ['goal'])
        self.assertEqual({x['consumer_kind'] for x in scope['required_reassessments']}, {'question', 'recommendation'})
        self.assertTrue(scope['question_reassessment_required'])
        with self.assertRaisesRegex(ValueError, 'frame_work'):
            self.publish()
        self.frame('Which intervention changes acute MSU inflammation?')
        second, published = self.publish(self.bundle('Compare acute inflammatory interventions'))
        self.assertTrue(published)
        self.assertNotEqual(first, second)
        self.assertEqual(self.store.artifact(self.wid, first)['content'], original)
        self.assertTrue(all(r['outcome'] == 'changed' for r in self.scope()['latest_reassessments']))

    def test_retained_question_is_valid_with_new_condition_reason(self):
        self.frame(); self.publish(); self.edit('Long-term urate reduction; spelling corrected')
        self.frame(outcome='retained')
        _, ok = self.publish(self.bundle(outcome='retained'))
        self.assertTrue(ok)
        self.assertEqual(self.scope()['latest_review_status'], 'declared_review_complete')

    def test_empty_usage_remains_unknown_not_unaffected_or_false_reviewed(self):
        self.frame(ids=[])
        _, ok = self.publish(self.bundle(ids=[]))
        self.assertTrue(ok)
        self.assertEqual(self.store.snapshot(self.wid)['review_status'], 'needs_review')
        self.assertEqual(self.scope()['latest_review_status'], 'unknown')
        self.assertEqual(len(self.scope()['required_reassessments']), 2)
        self.assertTrue(all(c['trigger'] == 'consumption_unknown' for c in self.scope()['required_reassessments']))

    def test_explicit_unknown_reassessment_remains_visible(self):
        self.frame(outcome='unknown')
        _, ok = self.publish(self.bundle(outcome='unknown'))
        self.assertTrue(ok)
        self.assertEqual(self.store.snapshot(self.wid)['review_status'], 'needs_review')
        self.assertEqual(self.scope()['latest_reassessments'][0]['outcome'], 'unknown')
        self.assertEqual(self.scope()['required_reassessments'][0]['trigger'], 'prior_review_unknown')
        value = self.bundle(); value['intent_review']['reassessments'] = []
        with self.assertRaisesRegex(ValueError, '재검토가 빠졌습니다'):
            self.publish(value)

    def test_no_consumption_history_does_not_mean_no_impact(self):
        p = proposal(1); p['intent_records'] = self.intents
        aid = self.store.add_artifact(self.wid, 'Legacy', 'decision_proposal', dump(p).encode(), {}, bump=False)
        self.store.publish_decision(self.wid, 1, p, aid)
        with self.store.connect(True) as db:
            self.store.event(db, self.wid, 'work_framed', {'based_rev': 1, 'current_question': 'Legacy question',
                                                         'intent_records': self.intents})
        self.assertTrue(self.scope()['question_reassessment_required'])
        self.assertEqual(self.scope()['prior_record_status'], 'legacy_decision_without_consumption_record')

    def test_carry_on_keeps_bound_frame_but_correction_requires_reassessment(self):
        self.frame(); self.publish()
        self.store.command(self.wid, 1, 'continue', {'kind': 'message', 'text': 'Carry on'})
        self.assertFalse(self.scope()['question_reassessment_required'])
        self.store.command(self.wid, 2, 'correct', {'kind': 'correction', 'text': 'The endpoint needs reconsideration'})
        self.assertTrue(self.scope()['question_reassessment_required'])
        self.assertEqual(self.scope()['required_reassessments'][0]['consumer_kind'], 'question')

    def test_removed_intent_cannot_resurrect_and_original_draft_is_preserved(self):
        self.frame(); first, _ = self.publish()
        self.edit(rows=[])
        stale = self.bundle()['decision']
        self.assertFalse(self.store.publish_decision(self.wid, 2, stale, 'direct-fixture-no-artifact'))
        state = self.store.snapshot(self.wid)
        self.assertEqual(state['intent'], [])
        self.assertEqual(state['decision_rev'], 1)
        self.assertEqual(state['review_status'], 'needs_review')
        event = state['events'][-1]
        self.assertEqual(event['kind'], 'decision_intent_conflict')
        self.assertEqual(event['body']['proposal'], stale)
        self.assertEqual(event['body']['proposal_sha256'], digest(stale))
        self.assertEqual(json.loads(self.store.artifact(self.wid, first)['content']), state['decision'])

    def test_protected_conflict_keeps_merge_without_applying_sidecars(self):
        self.frame(); self.publish(); self.edit()
        self.frame('Acute endpoint?')
        value = self.bundle()
        value['decision']['intent_records'] = copy.deepcopy(self.intents)
        value['decision']['intent_records'].append({'id': 'new', 'label': 'Unprotected interpretation',
            'text': 'Can evolve', 'origin': 'inferred', 'source_refs': []})
        before = self.store.snapshot(self.wid)
        aid, ok = self.publish(value)
        after = self.store.snapshot(self.wid)
        self.assertFalse(ok)
        self.assertEqual(after['decision'], before['decision'])
        self.assertEqual(after['intent'][0]['text'], 'Acute MSU inflammation')
        self.assertEqual(after['intent'][1]['id'], 'new')
        self.assertEqual(self.store.artifact(self.wid, aid)['meta']['finalization_records'], {})
        self.assertEqual(json.loads(self.store.artifact(self.wid, aid)['content']), value['decision'])

    def test_same_revision_publication_rejects_prepared_sidecars_atomically(self):
        self.frame()
        value = self.bundle()
        p, records = prepare(self.store, self.wid, 1, value, True, require_intent_review=True)
        newer, _ = self.publish()
        aid, ok = commit(self.store, self.wid, 1, 'older-job', p, records, [], None)
        self.assertFalse(ok)
        self.assertEqual(self.store.artifact(self.wid, aid)['meta']['finalization_records'], {})
        self.assertEqual(self.scope()['input_snapshot']['publication']['decision_id'], newer)
        self.assertEqual(self.store.snapshot(self.wid)['events'][-1]['kind'], 'decision_intent_snapshot_stale')

    def test_same_revision_reframe_cannot_attach_old_consumption_to_new_question(self):
        self.frame(); value = self.bundle()
        p, records = prepare(self.store, self.wid, 1, value, True, require_intent_review=True)
        self.frame('A different scientific endpoint?')
        aid, ok = commit(self.store, self.wid, 1, 'old-frame-job', p, records, [], None)
        self.assertFalse(ok)
        self.assertEqual(self.store.artifact(self.wid, aid)['meta']['finalization_records'], {})

    def test_actual_delivered_snapshot_detects_same_revision_change_before_prepare(self):
        self.frame()
        old = self.runner.model_context(self.wid, 1, True)
        token = delivered_intent_snapshot([{'role': 'user', 'content': model_json(old)}])
        self.publish()
        with self.assertRaisesRegex(ValueError, '동일 버전'):
            prepare(self.store, self.wid, 1, self.bundle(), True, require_intent_review=True,
                    expected_intent_snapshot=token)

    def test_stale_revision_preserves_only_original_proposal(self):
        self.frame(); value = self.bundle()
        p, records = prepare(self.store, self.wid, 1, value, True, require_intent_review=True)
        self.store.command(self.wid, 1, 'change', {'kind': 'correction', 'text': 'New condition'})
        aid, ok = commit(self.store, self.wid, 1, 'j', p, records, [], None)
        self.assertFalse(ok)
        self.assertEqual(self.store.artifact(self.wid, aid)['content'], dump(p).encode())
        self.assertFalse(any(a['kind'] == 'intent_dependencies' for a in self.store.snapshot(self.wid)['artifacts']))

    def test_failed_transaction_rolls_back_dependency_and_decision(self):
        self.frame(); value = self.bundle()
        p, records = prepare(self.store, self.wid, 1, value, True, require_intent_review=True)
        before = self.store.snapshot(self.wid)
        with patch.object(self.store, '_publish_decision', side_effect=OSError('Injected failure')):
            with self.assertRaises(OSError):
                commit(self.store, self.wid, 1, 'j', p, records, [], None)
        self.assertEqual(before, self.store.snapshot(self.wid))

    def test_native_requires_review_but_historical_bundle_remains_compatible(self):
        self.frame(); value = self.bundle(); del value['intent_review']
        prepare(self.store, self.wid, 1, value, True)
        with self.assertRaisesRegex(ValueError, 'intent_review'):
            prepare(self.store, self.wid, 1, value, True, require_intent_review=True)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(value, model_final_decision())
        spec = next(f for f in model_functions() if f['name'] == 'frame_work')['parameters']
        self.assertIn('intent_review', spec['required'])
        self.assertNotIn('intent_review', FRAME['required'])

    def test_model_cannot_invent_hash_or_foreign_intent_or_omit_consumer(self):
        self.frame()
        for variant in ('hash', 'foreign', 'duplicate', 'omitted', 'blank_reason'):
            with self.subTest(variant=variant):
                value = self.bundle()
                use = value['intent_review']['uses'][0]
                if variant == 'hash': use['content_sha256'] = 'invented'
                elif variant == 'foreign': use['intent_ids'] = ['not-a-current-intent']
                elif variant == 'duplicate': use['intent_ids'] = ['goal', 'goal']
                elif variant == 'omitted': value['intent_review']['uses'].pop()
                else: use['reason'] = ' '
                before = self.store.snapshot(self.wid)
                with self.assertRaises((ValueError, jsonschema.ValidationError)):
                    self.publish(value)
                self.assertEqual(before, self.store.snapshot(self.wid))
        injected = {'intent_records': self.intents, 'current_question': 'Injected binding?',
                    'hypotheses': [], 'task_brief': [], 'questions': [],
                    'intent_dependencies': {'input_snapshot': {'snapshot_sha256': 'invented'}}}
        with self.assertRaisesRegex(ValueError, '서버가 생성'):
            self.runner.frame(self.wid, 1, injected)

    def test_missing_reassessment_cannot_be_silently_reviewed(self):
        self.frame(); value = self.bundle(); value['intent_review']['reassessments'] = []
        with self.assertRaisesRegex(ValueError, '재검토가 빠졌습니다'):
            self.publish(value)

    def test_sidecar_must_belong_to_exact_published_decision(self):
        self.frame(); first, _ = self.publish()
        copied = self.store.artifact(self.wid, first)
        p = json.loads(copied['content']); p['recommendation'] = 'Different same-revision proposal'
        other = self.store.add_artifact(self.wid, 'Different proposal', 'decision_proposal',
            dump(p).encode(), copied['meta'], bump=False)
        self.store.publish_decision(self.wid, 1, p, other)
        self.assertEqual(self.scope()['prior_record_status'], 'consumption_record_owner_mismatch')
        self.assertEqual(self.scope()['required_reassessments'][0]['trigger'], 'consumption_history_unknown')

    def test_reordering_records_is_not_a_content_change(self):
        self.intents.append({'id': 'constraint', 'label': 'Constraint', 'text': 'Public sources only',
                             'origin': 'researcher', 'source_refs': []})
        self.frame(); self.publish()
        state = self.store.snapshot(self.wid)
        self.edit(rows=list(reversed(state['intent'])))
        self.assertEqual(self.scope()['changed_intent_ids'], [])
        self.assertFalse(self.scope()['question_reassessment_required'])

    def test_hypothesis_and_check_consumption_and_removal_are_explicit(self):
        self.frame(); value = self.bundle()
        p = value['decision']
        p['research_loop']['hypotheses'] = [{'id': 'h-goal', 'statement': 'Synthetic hypothesis',
            'expected_observation': 'Synthetic observation', 'alternatives': [], 'assessment': 'proposed',
            'rationale': 'Synthetic only', 'evidence': []}]
        p['research_loop']['next_checks'] = [{'id': 'c-goal', 'question': 'Synthetic endpoint check',
            'purpose': 'Synthetic only', 'hypothesis_ids': ['h-goal'], 'possible_outcomes': [],
            'outcome_links': [], 'operation': {'kind': 'researcher_input', 'request': 'Clarify endpoint'}}]
        frame = {'current_question': 'Which intervention reduces urate?'}
        value['intent_review'] = self.declaration(consumers(frame, p))
        value['hypothesis_review']['scope'] = {
            'hypotheses': [{'hypothesis_id': 'h-goal', 'status': 'not_reviewed', 'reason': 'Synthetic dependency test only'}],
            'checks': [{'check_id': 'c-goal', 'status': 'not_reviewed', 'reason': 'Synthetic dependency test only'}]}
        _, ok = self.publish(value)
        self.assertTrue(ok)
        self.edit(); self.frame('Acute endpoint?')
        self.assertEqual({c['consumer_kind'] for c in self.scope()['required_reassessments']},
                         {'question', 'recommendation', 'hypothesis', 'check'})
        _, ok = self.publish(self.bundle('Acute options; previous check no longer proposed'))
        self.assertTrue(ok)
        removed = [r for r in self.scope()['latest_reassessments'] if r['outcome'] == 'removed']
        self.assertEqual({r['consumer_id'] for r in removed}, {'h-goal', 'c-goal'})

    def native_current_bundle(self):
        from planner_fixtures import current_final
        value = self.bundle()
        adapted = current_final(self.store, self.wid, value['decision'])
        value['decision'] = adapted['decision']
        value['hypothesis_review'] = adapted['hypothesis_review']
        value['reassessment_review_ids'] = []
        state = self.store.snapshot(self.wid)
        frame = next(e['body'] for e in reversed(state['events']) if e['kind'] == 'work_framed')
        value['intent_review'] = self.declaration(consumers(frame, value['decision']))
        return value

    def test_native_runner_frames_before_research_and_publishes_bound_review(self):
        from evida.gateway import Gateway
        calls = []
        def transport(request):
            calls.append(request)
            if len(calls) == 1:
                self.assertEqual(request['tool_choice'], {'type': 'function', 'name': 'frame_work'})
                args = {'intent_records': self.intents, 'current_question': 'Which intervention reduces urate?',
                        'task_brief': [], 'questions': [], 'hypotheses': []}
                from planner_fixtures import current_frame
                args = current_frame(self.store, self.wid, args)
                args['intent_review'] = self.declaration(consumers(args), frame=True)
                jsonschema.validate(args, request['tools'][0]['parameters'])
                output = [{'type': 'function_call', 'name': 'frame_work', 'arguments': json.dumps(args),
                           'call_id': 'synthetic-frame', 'id': 'synthetic-frame'}]
            else:
                self.assertEqual(len(calls), 2, 'No retry or model call is expected in this fixture')
                value = self.native_current_bundle()
                value['reassessment_review_ids'] = []
                jsonschema.validate(value, request['text']['format']['schema'])
                output = [{'type': 'message', 'role': 'assistant', 'content': [
                    {'type': 'output_text', 'text': json.dumps(value)}]}]
            return {'id': f'synthetic-{len(calls)}', 'model': request['model'], 'status': 'completed',
                    'usage': {'input_tokens': 0, 'output_tokens': 0}, 'output': output}, {}
        self.runner.gateway = Gateway(json.loads((ROOT / 'configs/api_policy.json').read_text()), True, transport=transport)
        jid = self.store.enqueue(self.wid, 1, 'planner', {})
        self.runner.run_planner(jid)
        state = self.store.snapshot(self.wid)
        job = next(j for j in state['jobs'] if j['id'] == jid)
        self.assertEqual(job['status'], 'succeeded', job['error'])
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.scope()['prior_record_status'], 'available')

    def test_native_dependency_objects_are_strict_and_repeated_schema_calls_do_not_mutate(self):
        def check(schema):
            if isinstance(schema, list):
                for item in schema: check(item)
            elif isinstance(schema, dict):
                if schema.get('type') == 'object':
                    self.assertEqual(set(schema['properties']), set(schema['required']))
                    self.assertFalse(schema['additionalProperties'])
                for item in schema.values(): check(item)
        first = model_final_decision()
        self.assertEqual(first, model_final_decision())
        check(first['properties']['intent_review'])
        spec = next(f for f in model_functions() if f['name'] == 'frame_work')
        check(spec['parameters'])

    def test_inflight_same_revision_publication_stops_tool_execution(self):
        from evida.gateway import Gateway
        calls = []
        def transport(request):
            calls.append(request)
            args = {'intent_records': self.intents, 'current_question': 'Original question',
                    'task_brief': [], 'questions': [], 'hypotheses': []}
            args['intent_review'] = self.declaration(consumers(args), frame=True)
            other = proposal(1); other['intent_records'] = copy.deepcopy(self.intents)
            self.store.publish_decision(self.wid, 1, other, 'concurrent-synthetic-publication')
            return {'id': 'synthetic-inflight', 'model': request['model'], 'status': 'completed',
                'usage': {'input_tokens': 0, 'output_tokens': 0},
                'output': [{'type': 'function_call', 'name': 'frame_work', 'arguments': json.dumps(args),
                            'call_id': 'old-frame', 'id': 'old-frame'}]}, {}
        self.runner.gateway = Gateway(json.loads((ROOT / 'configs/api_policy.json').read_text()), True, transport=transport)
        jid = self.store.enqueue(self.wid, 1, 'planner', {})
        self.runner.run_planner(jid)
        state = self.store.snapshot(self.wid)
        self.assertEqual(next(j for j in state['jobs'] if j['id'] == jid)['status'], 'stale')
        self.assertFalse(any(e['kind'] == 'work_framed' for e in state['events']))
        self.assertEqual(len(calls), 1)
        self.assertTrue(any(a['kind'] == 'model_receipt' for a in state['artifacts']))

    def interpreted_fixture(self):
        self.intents.append({'id': 'condition', 'label': 'Condition', 'text': 'Inferred blood cell condition',
                             'origin': 'inferred', 'source_refs': []})
        self.frame(); self.publish(); self.edit('Protected synthetic researcher goal')

    def inferred_frame(self, *, add=False):
        state = self.store.snapshot(self.wid)
        args = {'intent_records': copy.deepcopy(state['intent']),
                'current_question': 'Which intervention applies to the inferred synovial cell condition?',
                'hypotheses': [], 'task_brief': [], 'questions': []}
        if add:
            args['intent_records'].append({'id': 'new_condition', 'label': 'New condition',
                'text': 'Inferred synovial cell condition', 'origin': 'inferred', 'source_refs': []})
        else:
            args['intent_records'][1]['text'] = 'Inferred synovial cell condition'
        args['intent_review'] = self.declaration(consumers(args), frame=True,
            ids=[r['id'] for r in args['intent_records']])
        received = input_snapshot(state)
        self.runner.frame(self.wid, state['rev'], args, require_intent_review=True,
                          expected_intent_snapshot=received['snapshot_sha256'])
        return args, received

    def interpreted_bundle(self, args):
        value = self.bundle('Synthetic comparison under the new inferred condition')
        value['decision']['intent_records'] = copy.deepcopy(args['intent_records'])
        value['intent_review'] = self.declaration(consumers(args, value['decision']),
                                                  ids=[r['id'] for r in args['intent_records']])
        return value

    def test_protected_goal_allows_new_inferred_frame_id_without_promoting_it(self):
        self.interpreted_fixture()
        before = copy.deepcopy(self.store.snapshot(self.wid)['intent'])
        args, received = self.inferred_frame(add=True)
        state = self.store.snapshot(self.wid)
        self.assertEqual(state['intent'], before)  # Framing is provisional, not a human edit.
        self.assertEqual(args['intent_records'][0], before[0])
        binding = next(e['body']['intent_dependencies'] for e in reversed(state['events']) if e['kind'] == 'work_framed')
        self.assertEqual(binding['received_input_snapshot'], received)
        self.assertNotIn('new_condition', received['intents'])
        used = next(r for r in binding['consumers'][0]['inputs'] if r['intent_id'] == 'new_condition')
        self.assertEqual(used['record_basis'], 'model_structured_in_frame')
        self.assertEqual(used['consumption_relation'], 'model_structured_record')
        self.assertIsNone(used['delivered_record_sha256'])
        self.assertEqual(used['record']['origin'], 'inferred')
        _, ok = self.publish(self.interpreted_bundle(args))
        self.assertTrue(ok)
        self.assertEqual(self.scope()['changed_intent_ids'], [])
        self.assertFalse(self.scope()['question_reassessment_required'])

    def test_updated_inferred_frame_and_final_bind_exact_new_body_not_old_input(self):
        self.interpreted_fixture(); args, received = self.inferred_frame()
        state = self.store.snapshot(self.wid)
        active = next(r for r in records(state) if r['id'] == 'condition')
        self.assertEqual(active['text'], 'Inferred synovial cell condition')
        self.assertEqual(received['intents']['condition']['record']['text'], 'Inferred blood cell condition')
        binding = next(e['body']['intent_dependencies'] for e in reversed(state['events']) if e['kind'] == 'work_framed')
        self.assertEqual(binding['input_snapshot']['intents']['condition']['content_sha256'], digest(active))
        _, ok = self.publish(self.interpreted_bundle(args))
        self.assertTrue(ok)
        scope = self.scope()
        self.assertEqual(scope['changed_intent_ids'], [])
        self.assertFalse(scope['question_reassessment_required'])
        dependency = json.loads(self.store.artifact(self.wid, scope['prior_record_id'])['content'])
        used = next(r for r in dependency['consumers'][0]['inputs'] if r['intent_id'] == 'condition')
        self.assertEqual(used['content_sha256'], digest(active))
        self.assertEqual(used['consumption_relation'], 'received_record_used_unchanged')
        self.assertEqual(used['record_basis'], 'model_structured_in_frame')

    def test_final_only_inferred_change_requires_question_review_and_binds_new_structure(self):
        self.frame(); self.publish()
        value = self.bundle()
        added = {'id': 'qualifier', 'label': 'Qualifier', 'text': 'Provisional endpoint refinement',
                 'origin': 'inferred', 'source_refs': []}
        value['decision']['intent_records'].append(added)
        for use in value['intent_review']['uses']:
            use['intent_ids'] = [*use['intent_ids'], 'qualifier']
        received = self.scope()['input_snapshot']
        with self.assertRaisesRegex(ValueError, '재검토가 빠졌습니다'):
            self.publish(value)
        value['intent_review']['reassessments'] = [{'consumer_kind': 'question', 'consumer_id': 'current_question',
            'outcome': 'retained', 'reason': 'The same question applies under this newly inferred qualifier.'}]
        _, ok = self.publish(value)
        self.assertTrue(ok)
        scope = self.scope()
        self.assertEqual(scope['changed_intent_ids'], [])
        self.assertFalse(scope['question_reassessment_required'])
        dependency = json.loads(self.store.artifact(self.wid, scope['prior_record_id'])['content'])
        self.assertEqual(dependency['received_input_snapshot'], received)
        used = next(r for r in dependency['consumers'][0]['inputs'] if r['intent_id'] == 'qualifier')
        self.assertEqual(used['record_basis'], 'model_structured_in_final')
        self.assertEqual(used['consumption_relation'], 'model_structured_record')
        self.assertEqual(used['record']['origin'], 'inferred')
        self.assertEqual(used['content_sha256'], digest(added))
        self.assertIsNone(used['delivered_record_sha256'])

    def test_provisional_frame_survives_continuation_but_not_authoritative_edit(self):
        self.interpreted_fixture(); args, _ = self.inferred_frame()
        state = self.store.snapshot(self.wid)
        self.store.command(self.wid, state['rev'], 'carry-provisional', {'kind': 'message', 'text': 'Carry on'})
        self.assertEqual(next(r for r in records(self.store.snapshot(self.wid)) if r['id'] == 'condition')['text'],
                         'Inferred synovial cell condition')
        self.assertFalse(self.scope()['question_reassessment_required'])
        current = self.store.snapshot(self.wid)
        baseline = records(current)
        updated = copy.deepcopy(baseline)
        next(r for r in updated if r['id'] == 'condition')['text'] = 'Researcher-confirmed different condition'
        self.store.command(self.wid, current['rev'], 'override-condition',
            {'kind': 'intent_edit', 'base_records': baseline, 'records': updated})
        self.assertEqual(next(r for r in records(self.store.snapshot(self.wid)) if r['id'] == 'condition')['text'],
                         'Researcher-confirmed different condition')
        with self.assertRaisesRegex(ValueError, '정정·삭제'):
            self.runner.frame(self.wid, self.store.snapshot(self.wid)['rev'], args, require_intent_review=True)

    def test_final_inferred_change_keeps_same_revision_concurrent_publication_guard(self):
        self.frame(); self.publish()
        value = self.bundle(); value['decision']['intent_records'][0]['text'] = 'New inferred goal wording'
        value['intent_review']['reassessments'] = [
            {'consumer_kind': kind, 'consumer_id': cid, 'outcome': 'retained',
             'reason': 'Same consumer text under the newly inferred wording.'}
            for kind, cid in [('question', 'current_question'), ('recommendation', 'recommendation')]]
        p, bound = prepare(self.store, self.wid, 1, value, True, require_intent_review=True)
        newer, _ = self.publish()
        aid, ok = commit(self.store, self.wid, 1, 'stale-new-structure', p, bound, [], None)
        self.assertFalse(ok)
        self.assertEqual(self.store.artifact(self.wid, aid)['meta']['finalization_records'], {})
        self.assertEqual(self.scope()['input_snapshot']['publication']['decision_id'], newer)

    def test_empty_publication_invalidates_provisional_frame_without_resurrection(self):
        self.frame()
        self.assertEqual([r['id'] for r in records(self.store.snapshot(self.wid))], ['goal'])
        newer = proposal(1); newer['intent_records'] = []
        self.assertTrue(self.store.publish_decision(self.wid, 1, newer, 'legacy-empty-publication'))
        self.assertEqual(records(self.store.snapshot(self.wid)), [])
        self.assertEqual(self.scope()['input_snapshot']['intents'], {})
        self.assertTrue(self.scope()['question_reassessment_required'])

    def test_native_empty_final_keeps_editor_baseline_authoritative(self):
        self.frame()
        obsolete = records(self.store.snapshot(self.wid))
        value = self.bundle(ids=[])
        value['decision']['intent_records'] = []
        _, published = self.publish(value)
        self.assertTrue(published)
        with self.assertRaises(Conflict):
            self.store.command(self.wid, 1, 'obsolete-editor',
                {'kind': 'intent_edit', 'base_records': obsolete, 'records': obsolete})
        self.assertEqual(self.store.snapshot(self.wid)['intent'], [])
        self.store.command(self.wid, 1, 'current-editor',
            {'kind': 'intent_edit', 'base_records': [], 'records':
             [{'id': 'new-goal', 'label': 'Goal', 'text': 'Researcher supplied goal'}]})
        state = self.store.snapshot(self.wid)
        self.assertEqual([r['id'] for r in records(state)], ['new-goal'])
        self.assertEqual(state['intent'][0]['origin'], 'researcher')

    def test_native_multi_call_frame_responses_are_all_rejected_before_mutation(self):
        from evida.gateway import Gateway
        from evida.model_context import unpack
        for second_name in ('frame_work', 'inspect_artifact'):
            with self.subTest(second_name=second_name):
                calls = []
                # Each subcase gets an untouched workspace.
                self.wid = self.store.create('Synthetic multiple-frame-call fixture')['id']
                def transport(request):
                    calls.append(request)
                    args = {'intent_records': self.intents, 'current_question': 'Which intervention reduces urate?',
                            'task_brief': [], 'questions': [], 'hypotheses': []}
                    from planner_fixtures import current_frame
                    args = current_frame(self.store, self.wid, args)
                    args['intent_review'] = self.declaration(consumers(args), frame=True)
                    if len(calls) == 1:
                        output = [{'type': 'function_call', 'name': name, 'arguments': json.dumps(args),
                                   'call_id': cid, 'id': cid}
                                  for name, cid in [('frame_work', 'batch-frame'), (second_name, 'batch-second')]]
                    elif len(calls) == 2:
                        state = self.store.snapshot(self.wid)
                        self.assertFalse(any(e['kind'] == 'work_framed' for e in state['events']))
                        self.assertFalse(any(a['kind'] == 'tool_reading' for a in state['artifacts']))
                        outputs = [v for v in request['input'] if v.get('type') == 'function_call_output']
                        self.assertEqual({v['call_id'] for v in outputs}, {'batch-frame', 'batch-second'})
                        self.assertTrue(all(unpack(json.loads(v['output']))['status'] == 'invalid_input' for v in outputs))
                        output = [{'type': 'function_call', 'name': 'frame_work', 'arguments': json.dumps(args),
                                   'call_id': 'single-frame', 'id': 'single-frame'}]
                    else:
                        self.assertEqual(len(calls), 3)
                        value = self.native_current_bundle()
                        output = [{'type': 'message', 'role': 'assistant', 'content': [
                            {'type': 'output_text', 'text': json.dumps(value)}]}]
                    return {'id': f'synthetic-{len(calls)}', 'model': request['model'], 'status': 'completed',
                            'usage': {'input_tokens': 0, 'output_tokens': 0}, 'output': output}, {}
                self.runner.gateway = Gateway(json.loads((ROOT / 'configs/api_policy.json').read_text()),
                                              True, transport=transport)
                jid = self.store.enqueue(self.wid, 1, 'planner', {})
                self.runner.run_planner(jid)
                state = self.store.snapshot(self.wid)
                job = next(j for j in state['jobs'] if j['id'] == jid)
                self.assertEqual(job['status'], 'succeeded', job['error'])
                self.assertEqual(len(calls), 3)
                self.assertEqual(sum(e['kind'] == 'work_framed' for e in state['events']), 1)


if __name__ == '__main__':
    unittest.main()
