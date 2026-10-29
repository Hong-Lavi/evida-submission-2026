"""Real registered CPU worker and saved observation binding; no model gateway."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evida.next_observation_binding import digest, evaluate, prepare
from evida.runner import Runner
from evida.store import Store
from tests.test_next_observation import publish_fixture, result_fixture

ROOT = Path(__file__).resolve().parents[1]


class NoModelGateway:
    def __getattr__(self, name):
        raise AssertionError('No model call is authorized by this test: ' + name)


class NextObservationWorkerTests(unittest.TestCase):
    def test_queued_cache_rebinds_after_provenance_correction(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'test.db'); wid = store.create('Queued correction fixture')['id']
            args, _ = publish_fixture(store, wid)
            runner = Runner(ROOT, store, NoModelGateway(), Path(temp) / 'attempts')
            try:
                def enqueue(arguments):
                    return store.enqueue(wid, store.snapshot(wid)['rev'], 'next_observation_selection', arguments,
                                         runner.cache_key(wid, 'next_observation_selection', arguments))
                initial_id = runner.run_tool_job(enqueue(args), False)
                observed = store.command(wid, store.snapshot(wid)['rev'], 'result', {'kind': 'observation',
                    'text': 'Synthetic preserved response.', 'synthetic': True,
                    'research_context': {'decision_id': args['artifact_id'], 'check_id': 'function',
                                         'hypothesis_ids': ['h'], 'comparison': 'consistent'}})
                update = {'mode': 'review_result', 'artifact_id': initial_id, 'source_artifact_ids': [], 'problem': None,
                          'result': result_fixture(message_id=observed['message_id'])}
                old_id = runner.run_tool_job(enqueue(update), False)
                old_bytes = store.artifact(wid, old_id)['content']
                old = json.loads(old_bytes)
                queued_key = runner.cache_key(wid, 'next_observation_selection', update)
                queued = store.enqueue(wid, store.snapshot(wid)['rev'], 'next_observation_selection', update, queued_key)
                store.command(wid, store.snapshot(wid)['rev'], 'correction', {'kind': 'correction',
                    'text': 'Software fixture correction, not empirical validation.', 'synthetic': False,
                    'provenance_correction': {'target_message_id': observed['message_id'], 'corrected_synthetic': False,
                                              'reason': 'Fixture correction', 'researcher_reply': 'Fixture reply'}})
                fresh_bundle = prepare(store, wid, update)
                fresh_key = runner.cache_key(wid, 'next_observation_selection', update)
                self.assertNotEqual(queued_key, fresh_key)
                new_id = runner.run_tool_job(queued, False)
                self.assertNotEqual(new_id, old_id)
                job = next(j for j in store.snapshot(wid)['jobs'] if j['id'] == queued)
                self.assertEqual(job['status'], 'succeeded', job)
                self.assertEqual(job['cache_key'], fresh_key)
                artifact = store.artifact(wid, new_id); new = json.loads(artifact['content'])
                binding = artifact['meta']['next_observation_input_binding']
                self.assertEqual(binding, {'queued_cache_key': queued_key, 'execution_cache_key': fresh_key,
                                          'input_bundle_sha256': digest(fresh_bundle), 'rebound_at_execution': True})
                self.assertEqual(new['provenance']['input_bundle_sha256'], binding['input_bundle_sha256'])
                self.assertEqual(new['observed_events'][0]['effective_provenance']['origin'], 'researcher_report')
                self.assertEqual(new['observed_events'][0]['event_sha256'], old['observed_events'][0]['event_sha256'])
                self.assertEqual(store.artifact(wid, old_id)['content'], old_bytes)
                event = next(e for e in store.snapshot(wid)['events'] if e['kind'] == 'next_observation_input_bound'
                             and e['body']['job_id'] == queued)
                self.assertEqual(event['body']['queued_cache_key'], queued_key)
                repeated = enqueue(update)
                self.assertEqual(runner.run_tool_job(repeated, False), new_id)
                self.assertEqual(next(j for j in store.snapshot(wid)['jobs'] if j['id'] == repeated)['status'], 'reused')
            finally:
                runner.pool.shutdown(wait=True); runner.explanation_pool.shutdown(wait=True)

    def test_original_message_sources_are_bound_without_becoming_new_results(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'test.db'); wid = store.create('Message source fixture')['id']
            source_ids = []
            for i, (kind, text) in enumerate([('message', 'Synthetic earlier conditional prediction.'),
                                             ('observation', 'Synthetic historical counterevidence; not this result.')]):
                result = store.command(wid, store.snapshot(wid)['rev'], 'source-' + str(i),
                                       {'kind': kind, 'text': text, 'synthetic': True})
                source_ids.append(result['message_id'])
            args, _ = publish_fixture(store, wid, prediction_sources=source_ids)
            bundle = prepare(store, wid, args)
            self.assertEqual(set(bundle['source_message_ids']), set(source_ids))
            changed = copy.deepcopy(bundle)
            changed['events'][0]['body']['text'] = 'Tampered source'
            with self.assertRaises(ValueError): evaluate(changed)
            runner = Runner(ROOT, store, NoModelGateway(), Path(temp) / 'attempts')
            try:
                jid = store.enqueue(wid, store.snapshot(wid)['rev'], 'next_observation_selection', args,
                                    runner.cache_key(wid, 'next_observation_selection', args))
                aid = runner.run_tool_job(jid, False)
                job = next(j for j in store.snapshot(wid)['jobs'] if j['id'] == jid)
                self.assertEqual(job['status'], 'succeeded', job)
                artifact = store.artifact(wid, aid); result = json.loads(artifact['content'])
                # Detached worker results must identify the code that governs report conflicts.
                self.assertEqual(result['provenance']['code_sha256']['measurement_report.py'],
                                 hashlib.sha256((ROOT / 'evida/measurement_report.py').read_bytes()).hexdigest())
                self.assertEqual(result['observed_events'], [])
                self.assertIsNone(result['result_assessment'])
                self.assertEqual(len(result['summary']['retained_configuration_ids']), 3)
                self.assertEqual(set(artifact['meta']['consumed_source_messages']), set(source_ids))
                self.assertEqual({r['kind'] for r in result['source_events']}, {'message', 'observation'})
                originals = {e['body']['message_id']: e for e in bundle['events']}
                for source in result['source_events']:
                    original = originals[source['message_id']]
                    self.assertEqual(source['body'], original['body'])
                    self.assertEqual(source['event_sha256'], digest(original))
                observed = store.command(wid, store.snapshot(wid)['rev'], 'new-result', {'kind': 'observation',
                    'text': 'Synthetic new result is unmeasured.', 'synthetic': True,
                    'research_context': {'decision_id': args['artifact_id'], 'check_id': 'function',
                                         'hypothesis_ids': ['h'], 'comparison': 'unclear'}})
                updated = evaluate(prepare(store, wid, {'mode': 'review_result', 'artifact_id': aid,
                    'source_artifact_ids': [], 'problem': None,
                    'result': result_fixture(message_id=observed['message_id'], outcome_index=None)}))
                self.assertEqual(updated['provenance']['source_message_hashes'], result['provenance']['source_message_hashes'])
                self.assertEqual([e['message_id'] for e in updated['observed_events']], [observed['message_id']])
                self.assertEqual(len(updated['summary']['retained_configuration_ids']), 3)
            finally:
                runner.pool.shutdown(wait=True); runner.explanation_pool.shutdown(wait=True)

    def test_registered_job_chain_keeps_original_decision_and_observation(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'test.db'); wid = store.create('Synthetic native selection')['id']
            args, original_loop = publish_fixture(store, wid)
            runner = Runner(ROOT, store, NoModelGateway(), Path(temp) / 'attempts')
            try:
                def run(arguments):
                    runner.validate_tool(wid, 'next_observation_selection', arguments)
                    key = runner.cache_key(wid, 'next_observation_selection', arguments)
                    jid = store.enqueue(wid, store.snapshot(wid)['rev'], 'next_observation_selection', arguments, key)
                    aid = runner.run_tool_job(jid, False)
                    job = next(j for j in store.snapshot(wid)['jobs'] if j['id'] == jid)
                    self.assertEqual(job['status'], 'succeeded', job)
                    return aid, json.loads(store.artifact(wid, aid)['content'])
                initial_id, initial = run(args)
                self.assertEqual(initial['summary']['selected_check_ids'], ['function'])
                self.assertEqual(runner.inspect(wid, initial_id)['result']['problem'], args['problem'])
                self.assertIn(args['artifact_id'], store.artifact(wid, initial_id)['meta']['consumed_artifacts'])
                self.assertIn(initial['binding']['hypothesis_review_id'], store.artifact(wid, initial_id)['meta']['consumed_artifacts'])
                context = {'decision_id': args['artifact_id'], 'check_id': 'function', 'hypothesis_ids': ['h'], 'comparison': 'consistent'}
                message = store.command(wid, store.snapshot(wid)['rev'], 'observation-1', {'kind': 'observation',
                    'text': 'Synthetic functional response preserved under explicitly adequate conditions.', 'synthetic': True, 'research_context': context})
                update_args = {'mode': 'review_result', 'artifact_id': initial_id, 'source_artifact_ids': [], 'problem': None,
                               'result': result_fixture(message_id=message['message_id'])}
                result_id, result = run(update_args)
                self.assertEqual(result['summary']['selection_status'], 'decision_region_reached')
                self.assertEqual(result['summary']['retained_configuration_ids'], ['contribution', 'coexisting'])
                self.assertEqual(result['binding']['decision_id'], args['artifact_id'])
                self.assertEqual(result['provenance']['observation_origins'][message['message_id']], 'synthetic')
                self.assertEqual(result['observed_events'][0]['text'], 'Synthetic functional response preserved under explicitly adequate conditions.')
                self.assertFalse(result['provenance']['researcher_authority_verified'])
                self.assertEqual(store.snapshot(wid)['decision']['research_loop'], original_loop)
                self.assertEqual(json.loads(store.artifact(wid, initial_id)['content']), initial)
                repeat = {**update_args, 'artifact_id': result_id}
                with self.assertRaises(ValueError):runner.validate_tool(wid, 'next_observation_selection', repeat)
                wrong = copy.deepcopy(update_args); wrong['result']['message_id'] = 'missing'
                with self.assertRaises(ValueError):runner.validate_tool(wid, 'next_observation_selection', wrong)
                # Publish another decision with different text. The old result keeps old text.
                new_args, new_loop = publish_fixture(store, wid, prefix='Different later wording')
                bundle = prepare(store, wid, update_args)
                self.assertNotEqual(new_args['artifact_id'], args['artifact_id'])
                self.assertEqual(bundle['decision_id'], args['artifact_id'])
                inspected = runner.inspect(wid, result_id)['result']
                self.assertEqual(inspected['checks'], initial['checks'])
                self.assertNotEqual(inspected['checks'][0]['question'], new_loop['next_checks'][0]['question'])
                self.assertIn('not_automatically_current', inspected['binding']['display_scope'])
                # Classification annotations can change; original event bytes cannot.
                store.command(wid, store.snapshot(wid)['rev'], 'classification-correction', {'kind': 'correction',
                    'text': 'Synthetic software exercise of a provenance correction.', 'synthetic': False,
                    'provenance_correction': {'target_message_id': message['message_id'], 'corrected_synthetic': False,
                                              'reason': 'Synthetic test of append-only reclassification', 'researcher_reply': 'Fixture reply only'}})
                next_message = store.command(wid, store.snapshot(wid)['rev'], 'observation-2', {'kind': 'observation',
                    'text': 'Synthetic later unmeasured check', 'synthetic': True, 'research_context': context})
                after_correction = {'mode': 'review_result', 'artifact_id': result_id, 'source_artifact_ids': [], 'problem': None,
                                    'result': result_fixture(message_id=next_message['message_id'], outcome_index=None)}
                corrected = evaluate(prepare(store, wid, after_correction))
                self.assertEqual(corrected['binding']['observation_hashes'][message['message_id']], result['binding']['observation_hashes'][message['message_id']])
                self.assertEqual(corrected['observed_events'][0]['origin'], 'synthetic')
                self.assertEqual(corrected['observed_events'][0]['effective_provenance']['origin'], 'researcher_report')
                self.assertEqual(corrected['observed_events'][0]['effective_provenance']['empirical_status'], 'researcher_report_unverified')
            finally:
                runner.pool.shutdown(wait=True); runner.explanation_pool.shutdown(wait=True)


if __name__ == '__main__':unittest.main()
