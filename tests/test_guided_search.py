"""Searching toward a score is where a weak score becomes dangerous, so the guards are the test.

Optimising against a proxy improves the proxy: that is the documented failure of generate-and-rank
pipelines, and rounds of transformation are exactly the pressure that produces it. Two guards have
to hold. The search must not run at all unless the model earned it on unseen scaffolds, and every
kept structure must record how far it has drifted from the compounds the model was fitted on, so
an extrapolation is visible instead of simply ranking first.
"""
import unittest

from evida.guided_search import APPLICABILITY_SIMILARITY, LIMITS, search

SCAFFOLDS = ['c1ccccc1', 'c1ccncc1', 'C1CCCCC1', 'c1ccc2ccccc2c1', 'C1CCNCC1', 'c1ccsc1',
             'C1CCOC1', 'c1ccc(F)cc1', 'c1ccc(Cl)cc1', 'C1CCCC1', 'c1ccc(O)cc1', 'c1ccc(N)cc1']


def retrieved():
    return {'rows': [{'candidate_id': f'C{i}_{j}', 'smiles': core + 'C' * (j + 1) + 'C(=O)NCC',
                      'activities': [{'pchembl_value': 5 + 0.3 * j + (1.5 if 'N' in core else 0),
                                      'standard_type': 'IC50', 'standard_relation': '='}]}
                     for i, core in enumerate(SCAFFOLDS) for j in range(6)]}


class RefusalTests(unittest.TestCase):
    def test_a_model_that_did_not_earn_it_does_not_get_to_steer(self):
        calls = []

        def never(seeds, number):
            calls.append(number)
            return []

        result = search(retrieved(), {'usable': False, 'meaning': '기준 미달'}, {}, never)
        self.assertIs(result['ran'], False)
        self.assertEqual(result['status'], 'not_run')
        self.assertEqual(calls, [], 'no round may run without a model that predicts unseen chemistry')
        self.assertIn('길잡이 없는 탐색', result['meaning'])
        self.assertEqual(result['limits'], LIMITS)


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from evida.activity_model import fit
        cls.value = retrieved()
        cls.fitted = fit(cls.value)
        assert cls.fitted['usable'], 'the fixture must produce a model that earns the search'

    def round_from(self, produced):
        state = {'round': 0}

        def rounds(seeds, number):
            state['round'] = number
            return [dict(row) for row in produced.get(number, [])]

        return rounds

    def test_seed_and_applicability_inputs_follow_the_actual_fitted_dataset(self):
        # The original input can be a CSV without activity rows. Its declared
        # extra source supplied the fit, so reconstructing rows from the CSV
        # alone would silently lose every seed.
        captured = []
        def one_round(seeds, number):
            captured.extend(seeds)
            return []
        result = search({'rows': []}, self.fitted, {'rounds': 1}, one_round)
        self.assertTrue(captured)
        self.assertEqual({r['smiles'] for r in captured},
                         {r['smiles'] for r in self.fitted['_seed_rows']})
        self.assertEqual(result['summary']['training_compounds'], self.fitted['summary']['trained_on'])
        self.assertEqual(result['summary']['seed_compounds'], self.fitted['summary']['compounds'])

    def test_each_round_keeps_the_best_and_feeds_them_back(self):
        seen_seeds = []

        def rounds(seeds, number):
            seen_seeds.append([s['smiles'] for s in seeds])
            base = 'c1ccccc1' + 'C' * number
            return [{'smiles': base + 'C(=O)NCC' + 'C' * i} for i in range(6)]

        result = search(self.value, self.fitted, {'rounds': 3, 'beam': 2}, rounds)
        self.assertEqual(result['status'], 'searched')
        self.assertEqual(len(result['history']), 3)
        self.assertEqual([h['kept'] for h in result['history']], [2, 2, 2])
        self.assertEqual(len(seen_seeds), 3)
        self.assertEqual(len(seen_seeds[0]), len(self.value['rows']), 'round 1 starts from what was retrieved')
        self.assertEqual(len(seen_seeds[1]), 2, 'later rounds start from what the last round kept')

    def test_every_kept_structure_says_how_far_it_drifted(self):
        def rounds(seeds, number):
            return [{'smiles': 'c1ccccc1' + 'C' * number + 'C(=O)NCC'},
                    {'smiles': 'C1=CC2=C(C=C1)N=C(S2)NC(=O)C3CCCCC3'}]  # nothing like the training set

        result = search(self.value, self.fitted, {'rounds': 1, 'beam': 5}, rounds)
        for row in result['rows']:
            self.assertIsInstance(row['nearest_training_similarity'], float)
            self.assertIs(row['inside_applicability'],
                          row['nearest_training_similarity'] >= APPLICABILITY_SIMILARITY)
            self.assertIsInstance(row['predicted_p_activity'], float)
        outside = [r for r in result['rows'] if not r['inside_applicability']]
        self.assertTrue(outside, 'the unrelated structure must be marked, not silently ranked')
        self.assertEqual(result['summary']['kept_outside_applicability'], len(outside))

    def test_repeated_local_ids_keep_the_exact_previous_round_parent(self):
        def rounds(seeds, number):
            parent = seeds[0]
            return [{'candidate_id': 'proposed-1', 'smiles': 'c1ccccc1' + 'C' * (number + 7),
                     'paths': [{'parent_id': parent['candidate_id'], 'parent_smiles': parent['smiles']}]}]

        result = search(self.value, self.fitted, {'rounds': 2, 'beam': 1}, rounds)
        rows = sorted(result['rows'], key=lambda r: r['round'])
        self.assertEqual(len({r['candidate_id'] for r in rows}), 2)
        self.assertEqual(rows[1]['paths'][0]['parent_id'], rows[0]['candidate_id'])
        self.assertEqual(rows[1]['paths'][0]['parent_smiles'], rows[0]['smiles'])
        self.assertEqual(rows[1]['paths'][0]['parent_branch'], 'guided_search')
        self.assertEqual(rows[1]['paths'][0]['parent_round'], 1)

    def test_a_round_that_proposes_nothing_new_ends_the_search_and_says_so(self):
        def rounds(seeds, number):
            return [] if number > 1 else [{'smiles': 'c1ccccc1CCC(=O)NCC'}]

        result = search(self.value, self.fitted, {'rounds': 4, 'beam': 3}, rounds)
        self.assertEqual(result['history'][-1]['proposed'], 0)
        self.assertIn('새 구조가 나오지 않았습니다', result['history'][-1]['reason'])
        self.assertLess(len(result['history']), 4)

    def test_the_same_structure_is_not_proposed_twice_across_rounds(self):
        def rounds(seeds, number):
            return [{'smiles': 'c1ccccc1CCC(=O)NCC'}, {'smiles': 'c1ccncc1CCC(=O)NCC'}]

        result = search(self.value, self.fitted, {'rounds': 3, 'beam': 4}, rounds)
        smiles = [row['smiles'] for row in result['rows']]
        self.assertEqual(len(smiles), len(set(smiles)))

    def test_the_result_reports_the_trajectory_and_what_it_is_not(self):
        def rounds(seeds, number):
            return [{'smiles': 'c1ccccc1' + 'C' * (number + i + 7) + 'C(=O)NCC'} for i in range(4)]

        result = search(self.value, self.fitted, {'rounds': 2, 'beam': 3}, rounds)
        for entry in result['history']:
            self.assertIn('best_predicted_p_activity', entry)
            self.assertIn('median_nearest_training_similarity', entry)
        self.assertEqual(result['summary']['held_out_spearman'],
                         self.fitted['summary']['held_out_spearman'])
        self.assertIsNotNone(result['summary']['best_measured_p_activity_in_training'])
        self.assertTrue(any('보상 과최적화' in line for line in result['limits']))
        self.assertIn('그 분자가 작동한다는 뜻이 아닙니다', result['meaning'])


if __name__ == '__main__':
    unittest.main()
