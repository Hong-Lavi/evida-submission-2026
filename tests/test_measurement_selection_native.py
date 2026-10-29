"""Native source/decision binding controls; all observations are synthetic."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from evida import reassessment as r, measurement_selection_native as native
from evida.finalization import prepare, commit
from evida.store import Store, dump
from test_research_loop import seed
from test_measurement_selection import spec, observation, gold
from planner_fixtures import current_final


class NativeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'db')
        self.wid, self.input_id, _, self.proposal = seed(self.store)
        self.doc = self.store.add_artifact(self.wid, 'Synthetic protocol and material records',
            'research_evidence', dump({'rows': [{'synthetic': True, 'candidate': 'A'},
                                               {'synthetic': True, 'candidate': 'C'}]}).encode(), {}, bump=False)
        self.received = {'snapshot_sha256': r.snapshot(self.store, self.wid)['snapshot_sha256'],
            'views': {key: {'kind': 'native_output', 'sha256': 'fixture', 'value': {'artifact_id': aid}}
                      for key, aid in [('input', self.input_id), ('doc', self.doc)]}}
        args = {'subject': 'hypothesis:h1', 'outcome': 'retained', 'new_content_json': '',
            'reason': 'Synthetic publication boundary', 'scope_description': 'Synthetic input only',
            'scope_complete': True, 'input_ids': [self.input_id], 'delivered_view_ids': ['input'],
            'upstream_review_ids': [], 'queries_json': '{}',
            'arguments_json': dump({'supports': [[self.input_id]], 'counterarguments': []})}
        self.review = r.record_review(self.store, self.wid, 1, 'j', args, self.received)
        self.received['views']['review'] = {'kind': 'native_output', 'sha256': 'fixture', 'value': self.review}
        def refs(value):
            if isinstance(value, list): return [refs(x) for x in value]
            if not isinstance(value, dict): return value
            if 'artifact_id' in value: return {'artifact_id': self.doc, 'json_pointer': '/rows/0'}
            return {k: refs(v) for k, v in value.items()}
        self.spec = refs(spec())
        self.spec['arms'][0] = {'id': 'explicit', 'kind': 'source_evidence',
            'reason': 'Synthetic source-led comparison', 'source_refs': [{'artifact_id': self.doc, 'json_pointer': '/rows/0'}],
            'order': ['A', 'B', 'C']}
        self.spec['next_check']['engine2_refs'] = [{'id': self.review['subject'], 'revision': self.review['content_hash'],
            'source_ref': {'artifact_id': self.review['artifact_id'], 'json_pointer': '/content'}}]
        for branch in self.spec['next_check']['branches']:
            branch['explanation_ids'] = [self.review['subject']]

    def tearDown(self):
        self.tmp.cleanup()

    def freeze(self):
        result = native.freeze(self.store, self.wid, 1, 'j', self.spec, self.received)
        self.received['views']['plan'] = {'kind': 'native_output', 'sha256': 'fixture', 'value': result}
        return result

    def final(self, result):
        proposal = deepcopy(self.proposal)
        proposal['research_loop']['next_checks'][0]['operation'] = {
            'kind': 'external_observation', 'request': 'Synthetic assay design', 'grounded_in': [self.doc]}
        proposal['research_loop']['next_checks'][0]['measurement_selection_id'] = result['artifact_id']
        value = current_final(self.store, self.wid, proposal)
        value['reassessment_review_ids'] = [self.review['artifact_id']]
        return value

    def test_plan_does_not_invalidate_its_upstream_draft(self):
        before = r.snapshot(self.store, self.wid)
        result = self.freeze()
        self.assertEqual(before, r.snapshot(self.store, self.wid))
        self.assertEqual(result['result']['evaluation']['ranking_value'], 'ranking_value_unproven')

    def test_csv_identity_reference_binds_exact_delivered_original_row(self):
        from evida.science import molecule_rows
        import hashlib
        raw = b'id;smiles;note\nA;CC;first\nC;CO;second\n'
        meta = {'delimiter': ';', 'id_column': 'id', 'smiles_column': 'smiles'}
        aid = self.store.add_artifact(self.wid, 'Synthetic original CSV',
            'molecule_csv', raw, meta, bump=False, media='text/csv')
        self.received['snapshot_sha256'] = r.snapshot(self.store, self.wid)['snapshot_sha256']
        self.received['views']['csv'] = {'kind': 'native_output', 'sha256': 'fixture',
            'value': {'artifact_id': aid}}
        ref = {'artifact_id': aid, 'json_pointer': '/rows/1'}
        bound, sources = native.bind_sources(self.store, self.wid, ref, self.received)
        original, body = native.read(self.store, self.wid, aid)
        self.assertEqual(body['rows'], molecule_rows(raw, meta)[1])
        self.assertEqual(native.pointer(body, '/rows/1')['candidate_id'], 'C')
        self.assertEqual(original['content'], raw)
        self.assertEqual(bound['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(sources[aid + '#/rows/1']['value_sha256'],
                         native.kernel.digest(body['rows'][1]))
        del self.received['views']['csv']
        with self.assertRaisesRegex(ValueError, '실제 전달본'):
            native.bind_sources(self.store, self.wid, ref, self.received)

    def test_raw_text_is_not_guessed_as_csv_or_rewritten(self):
        raw = b'Preserved original text, not JSON or molecule CSV'
        aid = self.store.add_artifact(self.wid, 'Synthetic source', 'source_file',
            raw, {}, bump=False, media='text/plain')
        with self.assertRaisesRegex(ValueError, aid + r'.*source_file'):
            native.read(self.store, self.wid, aid)
        self.assertEqual(self.store.artifact(self.wid, aid)['content'], raw)

    def test_unread_source_and_missing_pointer_cannot_be_bound(self):
        del self.received['views']['doc']
        with self.assertRaisesRegex(ValueError, '전달본'):
            self.freeze()
        self.received['views']['doc'] = {'kind': 'native_output', 'sha256': 'fixture', 'value': {'artifact_id': self.doc}}
        self.spec['context']['field_refs']['matrix'][0]['json_pointer'] = '/rows/99'
        with self.assertRaises((IndexError, ValueError)):
            self.freeze()

    def test_explanation_version_cannot_be_replaced_silently(self):
        self.spec['next_check']['engine2_refs'][0]['revision'] = 'unreviewed-new-wording'
        with self.assertRaisesRegex(ValueError, 'content_hash'):
            self.freeze()

    def test_native_final_publishes_same_design_then_flags_changed_conditions(self):
        result = self.freeze()
        value = self.final(result)
        p, records = prepare(self.store, self.wid, 1, value, True,
            reassessment_received=self.received, job_id='j')
        _, ok = commit(self.store, self.wid, 1, 'j', p, records, [], None)
        self.assertTrue(ok)
        public = native.view(self.store, self.wid, self.store.snapshot(self.wid))['c1']
        self.assertTrue(public['current'])
        self.assertEqual(public['handoff']['next_check']['specimen'], self.spec['next_check']['specimen'] | {
            'source_refs': result['result']['plan']['spec']['next_check']['specimen']['source_refs']})
        self.store.command(self.wid, 1, 'new-assay', {'kind': 'correction', 'text': 'New synthetic assay condition'})
        self.assertFalse(native.view(self.store, self.wid, self.store.snapshot(self.wid))['c1']['current'])

    def test_final_requires_same_consumed_explanation(self):
        result = self.freeze()
        value = self.final(result); value['reassessment_review_ids'] = []
        with self.assertRaisesRegex(ValueError, '최종 게시할 설명'):
            prepare(self.store, self.wid, 1, value, True, reassessment_received=self.received, job_id='j')

    def test_evaluation_requires_delivered_outcomes_and_preserves_retrospective_status(self):
        result = self.freeze()
        def refs(value):
            if isinstance(value, list): return [refs(x) for x in value]
            if not isinstance(value, dict): return value
            if 'artifact_id' in value: return {'artifact_id': self.doc, 'json_pointer': '/rows/0'}
            return {k: refs(v) for k, v in value.items()}
        outcome = refs(gold(result['result']['plan'], [observation('A', 1), observation('C', 4)]))
        outcome['rows'][1]['source_refs'] = [{'artifact_id': self.doc, 'json_pointer': '/rows/1'}]
        outcome['inspection_status'] = 'held_out_after_seal'
        aid = self.store.add_artifact(self.wid, 'Synthetic supplied outcomes', 'measurement_outcomes',
            dump(outcome).encode(), {'origin': 'source_dataset', 'synthetic': True}, bump=False)
        with self.assertRaisesRegex(ValueError, '실제 전달본'):
            native.evaluate(self.store, self.wid, 1, 'j', result['artifact_id'], aid, self.received)
        self.received['views']['outcomes'] = {'kind': 'native_output', 'sha256': 'fixture',
                                             'value': {'artifact_id': aid}}
        evaluation = native.evaluate(self.store, self.wid, 1, 'j', result['artifact_id'], aid, self.received)['result']
        self.assertEqual(evaluation['declared_inspection_status'], 'held_out_after_seal')
        self.assertEqual(evaluation['evaluation']['inspection_status'], 'retrospective')

    def test_prediction_score_requires_exact_saved_candidate_structure_and_number(self):
        rows = [{'candidate_id': c, 'structure_id': 'structure_' + c, 'predicted_p_activity': n}
                for c, n in zip('ABC', [3, 2, 1])]
        aid = self.store.add_artifact(self.wid, 'Synthetic prediction boundary', 'activity_prediction',
            dump({'rows': rows}).encode(), {'synthetic': True}, bump=False)
        # A newly arrived scientific result requires fresh review binding.
        self.received['snapshot_sha256'] = r.snapshot(self.store, self.wid)['snapshot_sha256']
        self.received['views']['prediction'] = {'kind': 'native_output', 'sha256': 'fixture', 'value': {'artifact_id': aid}}
        source = lambda path: {'artifact_id': aid, 'json_pointer': path}
        self.spec['arms'][0] = {'id': 'compute', 'kind': 'prediction', 'reason': 'Synthetic saved predictions',
            'source_refs': [source('/rows')], 'scores': {'A': 3, 'B': 2, 'C': 1},
            'prediction_context': deepcopy(self.spec['candidates'][0]['measurement_context'])}
        mapping = {c: {'score_ref': source(f'/rows/{i}/predicted_p_activity'),
            'candidate_ref': source(f'/rows/{i}/candidate_id'), 'structure_ref': source(f'/rows/{i}/structure_id'),
            'direction': 'higher'} for i,c in enumerate('ABC')}
        self.spec['prediction_bindings'] = {'compute': mapping}
        self.spec['arms'][0]['scores']['A'] = 9
        with self.assertRaisesRegex(ValueError, '원 예측값'):
            self.freeze()
        self.spec['arms'][0]['scores']['A'] = 3
        mapping['A']['candidate_ref'] = source('/rows/1/candidate_id')
        with self.assertRaisesRegex(ValueError, '후보·구조'):
            self.freeze()
        mapping['A']['candidate_ref'] = source('/rows/0/candidate_id')
        args = {'subject': 'hypothesis:h1', 'outcome': 'retained', 'new_content_json': '',
            'reason': 'Synthetic interpretation after a new prediction artifact',
            'scope_description': 'Stored synthetic input only', 'scope_complete': True,
            'input_ids': [self.input_id], 'delivered_view_ids': ['input'], 'upstream_review_ids': [],
            'queries_json': '{}', 'arguments_json': dump({'supports': [[self.input_id]], 'counterarguments': []})}
        fresh = r.record_review(self.store, self.wid, 1, 'j', args, self.received)
        self.received['views']['fresh'] = {'kind': 'native_output', 'sha256': 'fixture', 'value': fresh}
        self.spec['next_check']['engine2_refs'] = [{'id': fresh['subject'], 'revision': fresh['content_hash'],
            'source_ref': {'artifact_id': fresh['artifact_id'], 'json_pointer': '/content'}}]
        result = self.freeze()
        self.assertEqual(result['result']['plan']['arms'][0]['planned_ids'], ['A','B'])


if __name__ == '__main__': unittest.main()
