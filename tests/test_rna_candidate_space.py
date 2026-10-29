"""Retained origins, ambiguity, outside-page selection and real worker handoff."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evida.rna_candidate_space import enumerate_space, filtered_rows, select_and_evaluate
from evida.store import Store, dump
from test_rna_reference_panel import ref, SITE, GUIDE, candidates


class CandidateSpaceTests(unittest.TestCase):
    def test_all_origins_and_original_ids_retained_without_ranking(self):
        result = enumerate_space([('a', ref(SITE + 'CCC' + SITE)), ('b', ref(SITE, 'T2'))], 19,
                                 [('old', candidates())])
        row = next(r for r in result['rows'] if r['guide_5to3'] == GUIDE)
        self.assertEqual([(o['reference_artifact_id'], o['start_1_based']) for o in row['origins']],
                         [('a', 1), ('a', 23), ('b', 1)])
        self.assertEqual(row['prior_evaluations'][0]['candidate_id'], 'g')
        self.assertFalse(result['summary']['ranking_performed'])
        self.assertIsNone(row['efficacy_prediction'])
        self.assertEqual(result['summary']['known_base_origins'], 24)
        old = candidates(); old['rows'][0]['guide_5to3'] = 'A' * 19
        result = enumerate_space([('a', ref(SITE))], 19, [('outside', old)])
        self.assertEqual(result['summary']['previous_candidates_outside_selected_space'], 1)
        self.assertEqual(result['prior_candidate_links'][0]['candidate_id'], 'g')

    def test_unknown_windows_and_invalid_reference_identity(self):
        result = enumerate_space([('a', ref(SITE + 'N'))], 19)
        self.assertEqual(result['summary']['known_base_origins'], 1)
        self.assertEqual(result['summary']['unknown_base_windows'], 1)
        for field in ('gene_id', 'assembly', 'organism'):
            other = ref(SITE, 'T2'); other['reference'][field] = 'different'
            with self.assertRaises(ValueError):
                enumerate_space([('a', ref(SITE)), ('b', other)], 19)
        with self.assertRaises(ValueError):
            enumerate_space([('a', ref(SITE)), ('b', ref(SITE))], 19)
        bad = ref(SITE); bad['sequence_5to3'] = 'U' + SITE[1:]
        with self.assertRaises(ValueError): enumerate_space([('a', bad)], 19)

    def test_selection_rejects_changed_or_unmapped_reference_and_preserves_reason(self):
        reference = ref(SITE)
        space = enumerate_space([('a', reference)], 19)
        cid = space['rows'][0]['id']
        for rid, r in [('missing', reference), ('a', ref(SITE, 'T2'))]:
            with self.assertRaises(ValueError):
                select_and_evaluate(space, rid, r, [cid], 'unknown', 'check')
        bad = copy.deepcopy(space); bad['rows'][0]['origins'][0]['start_1_based'] = 2
        with self.assertRaises(ValueError):
            select_and_evaluate(bad, 'a', reference, [cid], 'unknown', 'check')
        with self.assertRaises(ValueError):
            select_and_evaluate(space, 'a', reference, ['invented'], 'unknown', 'check')
        with self.assertRaises(ValueError):
            select_and_evaluate(space, 'a', reference, [cid], 'unknown', '')

    def test_real_worker_whole_pool_pagination_selection_and_followup(self):
        from evida.runner import Runner
        from evida.gateway import Gateway
        root = Path(__file__).resolve().parents[1]
        # Deterministic explicit synthetic sequence, not a biological observation.
        sequence = ''.join('ACGU'[b % 4] for i in range(12)
                           for b in hashlib.sha256(str(i).encode()).digest())
        reference = ref(sequence)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'db'); wid = store.create('synthetic retained pool')['id']
            rid = store.add_artifact(wid, 'ref', 'rna_reference_archive', dump(reference).encode(), {}, bump=False)
            runner = Runner(root, store, Gateway(json.loads((root/'configs/api_policy.json').read_text()), False), Path(tmp)/'attempts')
            try:
                def run(tool, args):
                    runner.validate_tool(wid, tool, args)
                    jid = store.enqueue(wid, store.snapshot(wid)['rev'], tool, args, runner.cache_key(wid, tool, args))
                    aid = runner.run_tool_job(jid, True)
                    self.assertIsNotNone(aid)
                    data = store.artifact(wid, aid)
                    self.assertEqual(data['meta']['result_status'], 'succeeded')
                    return data, json.loads(data['content'])
                pool_art, pool = run('rna_candidate_space', {'reference_ids': [rid], 'paired_length': 19, 'prior_candidate_artifact_ids': []})
                self.assertEqual(len(pool['rows']), len(sequence) - 18)
                self.assertEqual(pool_art['meta']['consumed_artifacts'], [rid])
                choice = pool['rows'][150]
                page = runner.inspect(wid, pool_art['id'], 150, 1)['result']
                self.assertEqual(page['rows'][0]['id'], choice['id'])
                found = runner.inspect(wid, pool_art['id'], candidate_query=choice['guide_5to3'])['result']
                self.assertEqual(found['total_rows'], 1)
                self.assertEqual(found['retained_total_rows'], len(sequence)-18)
                args = {'artifact_id': pool_art['id'], 'reference_id': rid, 'candidate_ids': [choice['id']],
                        'chemistry': 'unknown', 'reason': 'Explicit outside-first-page synthetic check'}
                key = runner.cache_key(wid, 'rna_candidate_selection', args)
                self.assertNotEqual(key, runner.cache_key(wid, 'rna_candidate_selection', {**args, 'chemistry': 'unmodified'}))
                selected_art, selected = run('rna_candidate_selection', args)
                self.assertEqual(selected_art['kind'], 'rna_sequence_evaluation')
                self.assertEqual(selected_art['meta']['consumed_artifacts'], [pool_art['id'], rid])
                self.assertEqual(selected['rows'][0]['perfect_complementary_sites'][0]['start_1_based'], 151)
                self.assertIsInstance(selected['rows'][0]['guide_mfe_kcal_mol'], float)
                self.assertEqual(selected['selection']['reason'], args['reason'])
                self.assertTrue(selected['selection']['unselected_candidates_preserved'])
                _, compared = run('rna_reference_panel', {'artifact_id': selected_art['id'], 'candidate_ids': [choice['id']], 'reference_ids': [rid]})
                self.assertEqual(compared['rows'][0]['exact_sites'], [{'start_1_based': 151, 'end_1_based': 169}])
                self.assertEqual(json.loads(store.artifact(wid, pool_art['id'])['content']), pool)
            finally:
                runner.pool.shutdown(wait=True)


if __name__ == '__main__':
    unittest.main()
