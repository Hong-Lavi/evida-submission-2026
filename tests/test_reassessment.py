"""Dependency/publication boundaries; these fixtures are not biological results."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from evida import reassessment as r
from evida.finalization import prepare, commit
from evida.store import Store, dump
import test_finalization
from test_research_loop import seed


class ReassessmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'db')
        self.wid, self.source, self.parent, self.proposal = seed(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def received(self):
        return {'snapshot_sha256': r.snapshot(self.store, self.wid)['snapshot_sha256'],
                'views': {'read': {'kind': 'native_output', 'sha256': 'test-delivery',
                                  'value': {'artifact_id': self.source, 'result': {'rows': [{'cid': 'fixture', 'smiles': 'CCO'}]}}}}}

    def arguments(self):
        return {'subject': 'hypothesis:h1', 'outcome': 'retained', 'new_content_json': '',
                'reason': 'Synthetic fixture: declared context remains applicable.',
                'scope_description': 'Only the stored input structure; biological efficacy remains untested.',
                'scope_complete': True, 'input_ids': [self.source], 'delivered_view_ids': ['read'],
                'upstream_review_ids': [], 'queries_json': '{}',
                'arguments_json': json.dumps({'supports': [[self.source]], 'counterarguments': []})}

    def test_legacy_same_revision_is_unknown(self):
        value = r.view(self.store, self.wid)
        self.assertEqual(value['plan']['required'], ['hypothesis:h1'])
        self.assertFalse(r.applicability(self.store, self.wid)['hypothesis:h1']['current'])

    def test_same_revision_new_source_changes_snapshot(self):
        before = r.snapshot(self.store, self.wid)
        self.store.add_artifact(self.wid, 'New evidence', 'literature', b'{"rows":[]}', {}, bump=False)
        after = r.snapshot(self.store, self.wid)
        self.assertEqual(before['state_revision'], after['state_revision'])
        self.assertNotEqual(before['snapshot_sha256'], after['snapshot_sha256'])

    def test_delivery_and_drafts_do_not_invalidate_snapshot(self):
        before = r.snapshot(self.store, self.wid)
        r.record_delivery(self.store, self.wid, 'j', self.received())
        r.record_review(self.store, self.wid, 1, 'j', self.arguments(), self.received())
        self.assertEqual(before, r.snapshot(self.store, self.wid))

    def test_catalog_reference_cannot_establish_source_delivery(self):
        received = self.received()
        received['views']['read']['value'] = {'metadata': {'artifact_id': self.source}}
        with self.assertRaisesRegex(ValueError, '실제 전달본'):
            r.record_review(self.store, self.wid, 1, 'j', self.arguments(), received)

    def test_reference_only_reading_is_not_delivered(self):
        context = {'WORKING_READINGS': [{'reading_id': 'a', 'content_view': 'saved_reference_only'}],
                   'REASSESSMENT': {'snapshot_sha256': 's', 'drafts': []}}
        received = r.delivery_manifest([{'role': 'user', 'content': dump(context)}])
        self.assertEqual(received['views'], {})

    def test_native_source_alias_survives_catalog_but_requires_exact_returned_body(self):
        from evida.catalog_delivery import apply_catalog_delivery
        from evida.model_context import model_json
        body = {'kind': 'evidence_bundle', 'rows': [
            {'source_artifact_id': self.source, 'content': {'smiles': 'CCO'}}]}
        context = apply_catalog_delivery({
            'REASSESSMENT': {'snapshot_sha256': r.snapshot(self.store, self.wid)['snapshot_sha256'], 'drafts': []},
            'RELEVANT_EVIDENCE': [],
            'COMPLETED_VIEWS': [{'reading_id': 'reading-fixture', 'sha256': r.digest(body),
                                 'call_id': 'call-fixture', 'function': 'read_evidence_bundle'}]})
        messages = [{'role': 'user', 'content': model_json(context)}]
        self.assertNotIn('reading-fixture', r.delivery_manifest(messages)['views'])
        native = {'type': 'function_call_output', 'call_id': 'call-fixture', 'output': model_json(body)}
        received = r.delivery_manifest(messages + [native])
        self.assertIn('reading-fixture', received['views'])
        args = self.arguments(); args['delivered_view_ids'] = ['reading-fixture']
        self.assertEqual(r.record_review(self.store, self.wid, 1, 'j', args, received)['outcome'], 'retained')
        tampered = deepcopy(body); tampered['rows'][0]['content']['smiles'] = 'CCC'
        native['output'] = model_json(tampered)
        self.assertNotIn('reading-fixture', r.delivery_manifest(messages + [native])['views'])

    def test_empty_query_new_member_and_missing_condition_are_watched(self):
        query = {'equals': {'kind': 'assay', 'matrix': 'CSF'}}
        self.assertEqual(r.subscription(query, {})['members'], {})
        result = r.subscription(query, {'x': {'kind': 'assay'}})
        self.assertEqual(result['uncertain']['x']['missing_fields'], ['matrix'])
        self.assertEqual(r.subscription(query, {'x': {'kind': 'assay', 'matrix': 'plasma'}})['uncertain'], {})

    def test_upstream_help_never_infers_consumption_from_delivery(self):
        received = self.received()
        body = {'snapshot_sha256': received['snapshot_sha256'],
                'subject': 'hypothesis:synthetic-upstream', 'outcome': 'unknown', 'content': None}
        aid = self.store.add_artifact(self.wid, 'Synthetic upstream', 'reassessment_draft',
            dump(body).encode(), {'job_id': 'j'}, bump=False)
        result = {'artifact_id': aid, **body}
        received['views']['draft:' + aid] = {'kind': 'assessment_result',
            'sha256': r.digest(result), 'value': result}
        args = self.arguments()
        args.update(outcome='unknown', input_ids=[], delivered_view_ids=[],
                    upstream_review_ids=[aid], scope_complete=False,
                    arguments_json=dump({'supports': [], 'counterarguments': []}))
        with self.assertRaises(ValueError) as caught:
            r.record_review(self.store, self.wid, 1, 'j', args, received)
        help_record = json.loads(str(caught.exception).split('. ', 1)[1])
        self.assertEqual(help_record['currently_delivered_view_ids'], ['draft:' + aid])
        self.assertFalse(help_record['saved'])
        args['delivered_view_ids'] = ['draft:' + aid]
        accepted = r.record_review(self.store, self.wid, 1, 'j', args, received)
        self.assertEqual(accepted['outcome'], 'unknown')
        self.assertEqual(accepted['trace']['upstream_reviews'][0]['artifact_id'], aid)

    def test_upstream_help_does_not_offer_catalog_mentions(self):
        received = self.received()
        body = {'snapshot_sha256': received['snapshot_sha256'],
                'subject': 'hypothesis:synthetic-upstream', 'outcome': 'unknown', 'content': None}
        aid = self.store.add_artifact(self.wid, 'Synthetic upstream', 'reassessment_draft',
            dump(body).encode(), {'job_id': 'j'}, bump=False)
        received['views']['catalog-only'] = {'kind': 'native_output', 'sha256': 'fixture',
            'value': {'drafts': [{'artifact_id': aid, **body}]}}
        args = self.arguments()
        args.update(outcome='unknown', input_ids=[], delivered_view_ids=['catalog-only'],
                    upstream_review_ids=[aid], scope_complete=False,
                    arguments_json=dump({'supports': [], 'counterarguments': []}))
        with self.assertRaises(ValueError) as caught:
            r.record_review(self.store, self.wid, 1, 'j', args, received)
        help_record = json.loads(str(caught.exception).split('. ', 1)[1])
        self.assertEqual(help_record['currently_delivered_view_ids'], [])
        self.assertIn('inspect_artifact', help_record['next_step'])
        with self.assertRaisesRegex(ValueError, '같은 입력의 다른'):
            r.record_review(self.store, self.wid, 1, 'other-job', args, received)

    def test_unrelated_input_stays_retained_but_changed_dependency_propagates(self):
        rows = {'a': {'original_ref': 'r/a', 'original_hash': 'h'},
                'b': {'original_ref': 'r/b', 'original_hash': 'h'}}
        for row in rows.values(): row['original'] = {}
        snap = {'inputs': {'x': 1, 'y': 2}, 'evidence': {}, 'context': {}, 'rules': {}}
        prior = {'reviews': {key: {'outcome': 'retained', 'trace': {
            'output_ref': row['original_ref'], 'output_hash': 'h',
            'scope': {'description': 'Fixture scope', 'complete': True},
            'input_hashes': {dep: r.digest(snap['inputs'][dep])}, 'context_hash': r.digest({}),
            'rules_hash': r.digest({}), 'queries': {}, 'query_results': {}, 'upstream_subjects': []}}
            for key, row, dep in [('a', rows['a'], 'x'), ('b', rows['b'], 'y')]}}
        changed = deepcopy(snap); changed['inputs']['x'] = 3
        plan = r.build_plan(rows, changed, prior)
        self.assertEqual(plan['required'], ['a']); self.assertEqual(plan['retained'], ['b'])
        prior['reviews']['b']['trace']['upstream_subjects'] = ['a']
        self.assertEqual(r.build_plan(rows, changed, prior)['required'], ['a', 'b'])

    def test_changed_value_must_match_final_exactly(self):
        received = self.received()
        args = self.arguments(); args['outcome'] = 'changed'
        h = deepcopy(self.proposal['research_loop']['hypotheses'][0]); h['rationale'] = 'New reviewed interpretation.'
        args['new_content_json'] = json.dumps(h)
        result = r.record_review(self.store, self.wid, 1, 'j', args, received)
        received['views']['draft'] = {'kind': 'native_output', 'sha256': r.digest(result), 'value': result}
        with self.assertRaisesRegex(ValueError, '초안과 다릅니다'):
            r.prepare_bundle(self.store, self.wid, self.proposal, None, [result['artifact_id']], received, 'j')

    def test_omitted_required_review_is_explicit_unknown(self):
        bundle = r.prepare_bundle(self.store, self.wid, self.proposal, None, [], self.received(), 'j')
        self.assertEqual(bundle['value']['reviews']['hypothesis:h1']['outcome'], 'unknown')

    def test_imprecise_measurement_holds_only_its_support_path(self):
        with self.store.connect(True) as db:
            self.store.event(db, self.wid, 'observation', {'text': 'Synthetic imprecise readout',
                'validity': 'valid', 'precision': 'insufficient', 'synthetic': True})
        measurement = next(k for k, v in r.snapshot(self.store, self.wid)['inputs'].items() if v['kind'] == 'measurement')
        args = self.arguments(); args['input_ids'].append(measurement)
        args['arguments_json'] = json.dumps({'supports': [[measurement]], 'counterarguments': []})
        result = r.record_review(self.store, self.wid, 1, 'j', args, self.received())
        self.assertEqual(result['outcome'], 'unknown')
        args['arguments_json'] = json.dumps({'supports': [[measurement], [self.source]], 'counterarguments': []})
        independent = r.record_review(self.store, self.wid, 1, 'j', args, self.received())
        self.assertEqual(independent['outcome'], 'retained')
        self.assertTrue(independent['holds'])

    def test_failed_measurement_cannot_challenge_hypothesis(self):
        with self.store.connect(True) as db:
            self.store.event(db, self.wid, 'observation', {'text': 'Synthetic failed positive control',
                'validity': 'invalid', 'precision': 'sufficient', 'synthetic': True})
        measurement = next(k for k, v in r.snapshot(self.store, self.wid)['inputs'].items() if v['kind'] == 'measurement')
        args = self.arguments(); args['input_ids'].append(measurement)
        args['outcome'] = 'changed'
        h = deepcopy(self.proposal['research_loop']['hypotheses'][0]); h['assessment'] = 'challenged'
        args['new_content_json'] = json.dumps(h)
        args['arguments_json'] = json.dumps({'supports': [[self.source]], 'counterarguments': [[measurement]]})
        result = r.record_review(self.store, self.wid, 1, 'j', args, self.received())
        self.assertEqual(result['outcome'], 'unknown')
        self.assertIsNone(result['content'])

    def test_full_bundle_publication_establishes_currentness_and_changed_input_removes_it(self):
        args = self.arguments(); received = self.received()
        result = r.record_review(self.store, self.wid, 1, 'j', args, received)
        received['views']['batch'] = {'kind': 'native_output', 'sha256': 'fixture-batch',
            'value': {'kind': 'reassessment_draft_batch', 'results': [result]}}
        value = {'decision': self.proposal, 'discovery_review': None, 'judgment_context': None,
            'hypothesis_review': {'schema_version': '2', 'causal_steps': [], 'observations': [],
                'scope': {'hypotheses': [{'hypothesis_id': 'h1', 'status': 'not_reviewed',
                    'reason': 'Synthetic dependency test; no causal validation.'}],
                    'checks': [{'check_id': 'c1', 'status': 'not_reviewed',
                               'reason': 'Synthetic dependency test.'}]}},
            'reassessment_review_ids': [result['artifact_id']]}
        prepared, records = prepare(self.store, self.wid, 1, value, True,
                                    reassessment_received=received, job_id='j')
        aid, published = commit(self.store, self.wid, 1, 'j', prepared, records, [], None)
        self.assertTrue(published)
        view = r.view(self.store, self.wid)
        self.assertEqual(view['plan']['required'], [])
        self.assertTrue(r.applicability(self.store, self.wid)['hypothesis:h1']['current'])
        self.assertTrue(view['assessments']['hypothesis:h1']['original_ref'].startswith(aid))
        self.store.command(self.wid, 1, 'different-context', {'kind': 'correction', 'text': 'Different assay condition'})
        self.assertFalse(r.applicability(self.store, self.wid)['hypothesis:h1']['current'])


class ReassessmentAtomicTests(unittest.TestCase):
    setUp = test_finalization.FinalizationTests.setUp
    tearDown = test_finalization.FinalizationTests.tearDown

    def test_new_source_same_revision_cannot_publish_old_review(self):
        proposal, records = prepare(self.store, self.wid, 1, self.value, True)
        self.store.add_artifact(self.wid, 'Source arriving during inference', 'literature', b'{"rows":[1]}', {}, bump=False)
        aid, published = commit(self.store, self.wid, 1, 'j', proposal, records, [], None)
        self.assertFalse(published)
        state = self.store.snapshot(self.wid)
        self.assertFalse(any(a['kind'] in ('hypothesis_review', 'discovery_review', 'reassessment_bundle') for a in state['artifacts']))
        self.assertTrue(any(e['kind'] == 'decision_science_snapshot_stale' for e in state['events']))

    def test_parent_published_at_same_revision_stales_prepared_bundle(self):
        proposal, records = prepare(self.store, self.wid, 1, self.value, True)
        aid = self.store.add_artifact(self.wid, 'Other completed interpretation', 'decision_proposal', dump(proposal).encode(), {}, bump=False)
        self.store.publish_decision(self.wid, 1, proposal, aid)
        _, published = commit(self.store, self.wid, 1, 'j', proposal, records, [], None)
        self.assertFalse(published)


if __name__ == '__main__':
    unittest.main()
