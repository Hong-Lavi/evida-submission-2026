"""Source fidelity checks, with synthetic inputs labelled as such; no new biology."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from evida.proposal_qualification_worker import digest, run
from evida.runner import Runner
from evida.store import Store, dump


ROOT = Path(__file__).resolve().parents[1]


class ProposalQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.source = {'rows': [
            {'candidate_id': 'actual', 'smiles': 'Oc1ccccc1', 'activities': [
                {'activity_id': 11, 'assay_chembl_id': 'ASSAY_A', 'standard_type': 'IC50',
                 'standard_relation': '=', 'standard_value': '10', 'standard_units': 'nM',
                 'assay_context': {'description': 'Synthetic fixture A, human isolated enzyme'}},
                {'activity_id': 12, 'assay_chembl_id': 'ASSAY_B', 'standard_type': 'IC50',
                 'standard_relation': '>', 'standard_value': '100', 'standard_units': 'nM',
                 'assay_context': {'description': 'Synthetic fixture B, mouse cells'}}]},
            {'candidate_id': 'nearest', 'smiles': 'COc1ccccc1', 'activities': []}]}
        self.proposal = {'semantic_type': 'proposed_structure', 'source_artifact_id': 'source',
                         'rows': [{'candidate_id': 'proposed-1', 'smiles': 'COc1ccccc1',
                                   'transformed_from': 'actual', 'nearest_retrieved': 'nearest',
                                   'nearest_retrieved_smiles': 'COc1ccccc1',
                                   'predicted_p_activity': 7.2,
                                   'predicted_p_activity_meaning': 'Synthetic prediction fixture'}]}

    def tearDown(self):
        self.temp.cleanup()

    def request(self, source=None, proposal=None, meta=None):
        source = self.source if source is None else source
        proposal = self.proposal if proposal is None else proposal
        raw = source if isinstance(source, bytes) else dump(source).encode()
        content = dump(proposal).encode()
        path = self.directory / 'source'
        path.write_bytes(raw)
        return {'workspace': 'fixture', 'arguments': {'artifact_id': 'proposal', 'source_artifact_id': 'source'},
                'qualification_source_path': str(path), 'qualification_source_sha256': digest(raw),
                'qualification_proposal_sha256': digest(content), 'qualification_source_meta': meta or {}}, content

    def test_native_prediction_and_mixed_assays_stay_separate_from_comparator(self):
        request, content = self.request()
        before = copy.deepcopy(self.proposal)
        result = run(request, content)
        row = result['rows'][0]
        self.assertEqual(self.proposal, before)
        self.assertEqual(row['original_prediction']['predicted_p_activity'], 7.2)
        self.assertNotIn('predicted_pIC50', row['original_prediction'])
        self.assertEqual([p['parent_id'] for p in row['actual_parents']], ['actual'])
        reports = row['actual_parents'][0]['reported_measurements']
        self.assertEqual([r['original_measurement'] for r in reports], self.source['rows'][0]['activities'])
        self.assertEqual([r['assay_id'] for r in reports], ['ASSAY_A', 'ASSAY_B'])
        self.assertEqual(reports[1]['original_measurement']['standard_relation'], '>')
        self.assertEqual(row['assay_equivalence'], 'not_established')
        self.assertFalse(row['complete_protocol_verified'])
        self.assertFalse(row['training_binding_verified'])
        self.assertIsNone(row['nearest_train_similarity'])
        self.assertEqual([r['parent_id'] for r in row['exact_source_matches']], ['nearest'])
        self.assertFalse(result['rank_or_selection_changed'])
        self.assertFalse(row['measured'])
        self.assertEqual(result['summary']['proposal_rows_with_parent_measurements'], 1)
        # The reviewed source-local format retains original values in label.
        frozen_source = {'assay_context': {'assay_id': 'ASSAY_SYNTHETIC', 'target': 'fixture'},
                         'rows': [{'id': 'actual', 'smiles': 'Oc1ccccc1',
                                   'label': {'source_values_nm': [10, 20], 'activity_ids': [11, 12]}}]}
        frozen_proposal = {'source_artifact_id': 'source',
                           'source_sha256': digest(dump(frozen_source).encode()),
                           'assay_id': 'ASSAY_SYNTHETIC', 'selected_ids': ['second', 'first'],
                           'rows': [{'id': 'first', 'smiles': 'COc1ccccc1', 'transformed_from': 'actual'},
                                    {'id': 'second', 'smiles': 'CCOc1ccccc1', 'transformed_from': 'actual'}]}
        frozen = run(*self.request(frozen_source, frozen_proposal))
        self.assertEqual(frozen['summary']['parents_with_original_measurements'], 2)
        self.assertEqual(frozen['reported_assay_context'], frozen_source['assay_context'])
        self.assertEqual([r['candidate_id'] for r in frozen['rows']], ['first', 'second'])
        self.assertEqual([(r['candidate_id'], r['original_rank'], r['row_index'])
                          for r in frozen['selected_preview']], [('second', 1, 1), ('first', 2, 0)])

    def test_declared_comparator_alone_does_not_become_parent(self):
        self.proposal['rows'][0].pop('transformed_from')
        self.proposal['rows'][0]['declared_comparators'] = ['nearest']
        result = run(*self.request())
        self.assertEqual(result['rows'][0]['actual_parents'], [])
        self.assertIn('actual_generation_parent_unresolved', result['rows'][0]['issues'])

    def test_hash_mismatch_or_recorded_path_contradiction_is_rejected(self):
        self.proposal['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'exact source snapshot'):
            run(*self.request())
        self.proposal.pop('source_sha256')
        self.proposal['rows'][0]['paths'] = [{'parent_id': 'actual', 'parent_smiles': 'Oc1ccccc1',
                                             'generated_smiles': 'CCO'}]
        with self.assertRaisesRegex(ValueError, 'path output'):
            run(*self.request())

    def test_ambiguous_parent_and_invalid_proposal_are_retained_for_review(self):
        self.source['rows'].append({'candidate_id': 'actual', 'smiles': 'CCO'})
        self.proposal['rows'].append({'candidate_id': 'bad', 'smiles': 'not a molecule'})
        result = run(*self.request())
        self.assertEqual(len(result['rows']), 2)
        self.assertIn('actual_generation_parent_unresolved', result['rows'][0]['issues'])
        self.assertEqual(result['rows'][1]['proposal_status'], 'identity_hold')
        self.assertEqual(result['selected_ids'], ['proposed-1', 'bad'])

    def test_legacy_guided_ids_do_not_alias_main_rows_and_paths_can_resolve(self):
        self.proposal['guided_search'] = {'rows': [
            {'candidate_id': 'proposed-1', 'round': 1, 'smiles': 'CCOc1ccccc1', 'transformed_from': 'actual'},
            {'candidate_id': 'proposed-1', 'round': 2, 'smiles': 'CCCOc1ccccc1', 'transformed_from': 'proposed-1'}]}
        result = run(*self.request())
        self.assertEqual(len({r['qualification_row_id'] for r in result['rows']}), 3)
        self.assertEqual(result['rows'][2]['actual_parents'], [])
        self.assertEqual(result['rows'][2]['unresolved_actual_parents'][0]['status'], 'unresolved_generated_parent')
        self.proposal['guided_search']['rows'][1]['paths'] = [
            {'parent_id': 'proposed-1', 'parent_round': 1, 'parent_branch': 'guided_search',
             'parent_smiles': 'CCOc1ccccc1', 'generated_smiles': 'CCCOc1ccccc1'}]
        result = run(*self.request())
        parent = result['rows'][2]['actual_parents'][0]
        self.assertEqual(parent['source_ref']['json_pointer'], '/guided_search/rows/0')
        self.assertEqual(parent['parent_kind'], 'generated_unmeasured')
        self.assertEqual(parent['reported_measurements'], [])

    def test_native_with_source_sha_still_uses_native_measurement_adapter(self):
        self.proposal['source_sha256'] = digest(dump(self.source).encode())
        result = run(*self.request())
        self.assertTrue(result['retained_source_conversion']['native_adapter_used'])
        self.assertEqual(result['rows'][0]['reported_measurement_count'], 2)

    def test_selected_csv_reconnects_only_exact_saved_identity_and_structure(self):
        pool_raw = dump(self.source).encode()
        pool_path = self.directory / 'pool'
        pool_path.write_bytes(pool_raw)
        meta = {'source_pool_id': 'pool', 'source_pool_sha256': digest(pool_raw),
                'candidate_ids': ['actual'], 'id_column': 'cid', 'smiles_column': 'smiles'}
        request, content = self.request(b'cid,smiles\nactual,Oc1ccccc1\n', meta=meta)
        request['qualification_source_pool'] = {'artifact_id': 'pool', 'sha256': digest(pool_raw),
                                                 'path': str(pool_path), 'meta': {}}
        request['qualification_source_pool_status'] = 'exact_saved_source_pool'
        result = run(request, content)
        parent = result['rows'][0]['actual_parents'][0]
        self.assertEqual(parent['reported_measurements'][0]['source_ref']['artifact_id'], 'pool')
        self.assertEqual(parent['source_ref']['artifact_id'], 'source')
        self.assertEqual(parent['source_ref']['logical_csv_record_0_based'], 1)
        self.assertNotIn('json_pointer', parent['source_ref'])
        self.assertEqual(result['measurement_source_recovery']['matched_rows'], 1)
        # Same candidate display name with a different material is not a measurement match.
        request, content = self.request(b'cid,smiles\nactual,CCO\n', meta=meta)
        request['qualification_source_pool'] = {'artifact_id': 'pool', 'sha256': digest(pool_raw),
                                                 'path': str(pool_path), 'meta': {}}
        result = run(request, content)
        self.assertEqual(result['rows'][0]['reported_measurement_count'], 0)
        self.assertIn('original_measurement_source_unresolved', result['rows'][0]['issues'])

    def test_saved_current_guided_fixture_keeps_all_rows_and_original_predictions(self):
        fixture = json.loads((ROOT / 'tests/fixtures/guided_proposals_20261002.json').read_text())
        source = next(s['value'] for s in fixture['sources']
                      if s['original_artifact_id'] == fixture['result']['source_artifact_id'])
        proposal = copy.deepcopy(fixture['result'])
        proposal['source_artifact_id'] = 'source'
        result = run(*self.request(source, proposal))
        originals = proposal['rows'] + proposal['guided_search']['rows']
        self.assertEqual(len(result['rows']), 54)
        self.assertEqual([r['candidate_id'] for r in result['rows']], [r['candidate_id'] for r in originals])
        self.assertEqual([r['original_prediction']['predicted_p_activity'] for r in result['rows']],
                         [r['predicted_p_activity'] for r in originals])
        self.assertEqual(result['summary']['guided_rows'], 24)

    def test_real_worker_publication_pages_rows_preserves_inputs_and_reuses(self):
        store = Store(self.directory / 'fixture.sqlite3')
        wid = store.create('Synthetic saved-proposal test')['id']
        source_id = store.add_artifact(wid, 'Synthetic source', 'compound_candidates',
                                       dump(self.source).encode(), {}, bump=False)
        self.proposal['source_artifact_id'] = source_id
        proposal_id = store.add_artifact(wid, 'Synthetic proposal', 'analogue_proposal',
                                         dump(self.proposal).encode(), {}, bump=False)
        preserved = {aid: store.artifact(wid, aid)['sha256'] for aid in (source_id, proposal_id)}
        args = {'artifact_id': proposal_id, 'source_artifact_id': source_id}
        runner = Runner(ROOT, store, None, self.directory / 'attempts')
        try:
            runner.validate_tool(wid, 'proposal_qualification', args)
            cache = runner.cache_key(wid, 'proposal_qualification', args)
            jid = store.enqueue(wid, 1, 'proposal_qualification', args, cache_key=cache)
            aid = runner.run_tool_job(jid, False)
            result = json.loads(store.artifact(wid, aid)['content'])
            self.assertEqual(result['status'], 'succeeded', result)
            self.assertEqual(runner.inspect(wid, aid, 0, 1)['result']['rows'], result['rows'])
            self.assertEqual(runner.inspect(wid, aid, 1, 1)['result']['rows'], [])
            self.assertEqual({a: store.artifact(wid, a)['sha256'] for a in preserved}, preserved)
            reused = store.enqueue(wid, 1, 'proposal_qualification', args, cache_key=cache)
            self.assertEqual(runner.run_tool_job(reused, False), aid)
            self.assertEqual(len(list((self.directory / 'attempts').glob('*/request.json'))), 1)
        finally:
            runner.pool.shutdown(wait=True)
            runner.explanation_pool.shutdown(wait=True)


if __name__ == '__main__':
    unittest.main()
