"""A proposal that does not beat the compound it came from is not a candidate.

Enumeration produces far more structures than anyone can check, and the only cheap discriminator
available here is the same docking the parent gets. The rule is therefore strict and stated: same
run, same receptor, same seed; better than its own parent or it is not kept. This checks that the
verdict follows the scores rather than the order of the rows, that an invalid pose cannot win,
and that a missing parent leaves the proposal uncompared instead of quietly kept.
"""
import json
import tempfile
import unittest
from pathlib import Path

from evida.proposal_docking import LIMITS, compare
from evida.runner import Runner
from evida.store import Store

PASSING = {'sanitization': True, 'distance_to_protein': True, 'volume_overlap': True}
FAILING = {'sanitization': True, 'distance_to_protein': False, 'volume_overlap': True}


def docked(**scores):
    return {'status': 'succeeded',
            'rows': [{'candidate_id': cid, 'status': 'succeeded', 'vina_score_kcal_mol': value,
                      'posebusters': checks} for cid, (value, checks) in scores.items()]}


class ProposalDockingTests(unittest.TestCase):
    def test_a_better_score_than_its_own_parent_is_kept(self):
        result = docked(**{'proposed-1': (-9.4, PASSING), 'CHEMBL103': (-8.1, PASSING)})
        value = compare(result, {'proposed-1': 'CHEMBL103'})
        row = value['rows'][0]
        self.assertIs(row['keep'], True)
        self.assertEqual(row['difference_kcal_mol'], -1.3)
        self.assertEqual({k: value['summary'][k] for k in ('compared', 'kept', 'dropped', 'not_compared')},
                         {'compared': 1, 'kept': 1, 'dropped': 0, 'not_compared': 0})
        self.assertIn('결합의 근거는 아닙니다', row['reason'])

    def test_a_worse_or_equal_score_is_dropped(self):
        result = docked(**{'proposed-1': (-7.2, PASSING), 'proposed-2': (-8.1, PASSING),
                           'CHEMBL103': (-8.1, PASSING)})
        value = compare(result, {'proposed-1': 'CHEMBL103', 'proposed-2': 'CHEMBL103'})
        self.assertEqual([r['keep'] for r in value['rows']], [False, False],
                         'a tie is not an improvement over a compound already in hand')
        self.assertEqual(value['summary']['dropped'], 2)

    def test_an_invalid_pose_cannot_win_on_score(self):
        result = docked(**{'proposed-1': (-11.0, FAILING), 'CHEMBL103': (-8.1, PASSING)})
        row = compare(result, {'proposed-1': 'CHEMBL103'})['rows'][0]
        self.assertIs(row['keep'], False)
        self.assertIs(row['pose_valid'], False)
        self.assertIn('물리 검사', row['reason'])

    def test_the_verdict_is_against_the_best_of_the_declared_comparators(self):
        # Beating only the weakest of the three compounds a proposal came from is not an
        # improvement, and picking the comparator after seeing the scores would hide that.
        result = docked(**{'proposed-1': (-8.6, PASSING), 'CORE': (-8.9, PASSING),
                           'SUB': (-7.0, PASSING)})
        row = compare(result, {'proposed-1': ['CORE', 'SUB']})['rows'][0]
        self.assertEqual(row['parent_candidate_id'], 'CORE')
        self.assertEqual(row['comparator_scores'], {'CORE': -8.9, 'SUB': -7.0})
        self.assertIs(row['keep'], False)

    def test_one_undocked_comparator_holds_the_whole_comparison(self):
        result = docked(**{'proposed-1': (-9.9, PASSING), 'CORE': (-8.1, PASSING)})
        row = compare(result, {'proposed-1': ['CORE', 'SUB']})['rows'][0]
        self.assertIsNone(row['keep'])
        self.assertIn('도킹되지 않은', row['reason'])

    def test_a_parent_missing_from_this_run_leaves_the_proposal_uncompared(self):
        result = docked(**{'proposed-1': (-9.9, PASSING)})
        value = compare(result, {'proposed-1': 'CHEMBL103'})
        row = value['rows'][0]
        self.assertIsNone(row['keep'], 'never keep or drop on a comparison that did not happen')
        self.assertEqual({k: value['summary'][k] for k in ('compared', 'kept', 'dropped', 'not_compared')},
                         {'compared': 0, 'kept': 0, 'dropped': 0, 'not_compared': 1})

    def test_a_failed_docking_row_is_not_scored(self):
        result = {'status': 'partial',
                  'rows': [{'candidate_id': 'proposed-1', 'status': 'failed', 'error': 'x'},
                           {'candidate_id': 'CHEMBL103', 'status': 'succeeded',
                            'vina_score_kcal_mol': -8.1, 'posebusters': PASSING}]}
        row = compare(result, {'proposed-1': 'CHEMBL103'})['rows'][0]
        self.assertIsNone(row['keep'])
        self.assertIn('성공하지 않았습니다', row['reason'])

    def test_a_gap_within_seed_noise_is_not_an_improvement(self):
        # Vina's search is stochastic; a re-run moves the score by about 0.06 kcal/mol, so a
        # 0.05 gap says nothing about the molecule.
        result = docked(**{'proposed-1': (-8.15, PASSING), 'CHEMBL103': (-8.1, PASSING)})
        row = compare(result, {'proposed-1': 'CHEMBL103'})['rows'][0]
        self.assertIs(row['keep'], False)
        self.assertIn('시드에 따른 편차', row['reason'])

    def test_a_bigger_molecule_does_not_win_on_size_alone(self):
        # Docking scores rise with heavy-atom count, and recombination usually adds atoms.
        result = docked(**{'proposed-1': (-9.0, PASSING), 'CHEMBL103': (-8.1, PASSING)})
        pair = {'proposed-1': 'CHEMBL103'}
        grown = compare(result, pair, {'proposed-1': 40, 'CHEMBL103': 24})
        self.assertIs(grown['rows'][0]['keep'], False)
        self.assertIs(grown['rows'][0]['size_explained'], True)
        self.assertEqual(grown['rows'][0]['ligand_efficiency'], round(-9.0 / 40, 4))
        # The same score gap from a molecule that did not grow is still an improvement.
        same = compare(result, pair, {'proposed-1': 24, 'CHEMBL103': 24})
        self.assertIs(same['rows'][0]['keep'], True)

    def test_a_default_search_effort_is_flagged_rather_than_trusted(self):
        result = {**docked(**{'proposed-1': (-9.4, PASSING), 'CHEMBL103': (-8.1, PASSING)}),
                  'protocol': {'exhaustiveness': 8}}
        value = compare(result, {'proposed-1': 'CHEMBL103'})
        self.assertIn('탐색량', value['search_caution'])
        thorough = compare({**result, 'protocol': {'exhaustiveness': 32}}, {'proposed-1': 'CHEMBL103'})
        self.assertIsNone(thorough['search_caution'])

    def test_it_says_a_docking_score_is_not_a_measurement(self):
        value = compare(docked(**{'p': (-9.0, PASSING)}), {})
        self.assertEqual(value['limits'], LIMITS)
        self.assertTrue(any('측정 친화도' in line for line in value['limits']))


class RunnerWiringTests(unittest.TestCase):
    """The comparison must actually run on a docking whose input carried proposals."""

    def test_the_runner_compares_when_the_input_csv_carries_proposal_parents(self):
        source = Path(__file__).resolve().parents[1].joinpath('evida/runner.py').read_text()
        self.assertIn("if tool=='molecular_docking' and status in ('succeeded','partial')", source)
        self.assertIn("inp['meta']['proposal_parents']", source)
        self.assertIn("result['proposal_comparison']=compare(result", source)

    def test_a_proposal_run_stores_a_docking_ready_csv_of_proposals_and_parents(self):
        source = Path(__file__).resolve().parents[1].joinpath('evida/runner.py').read_text()
        self.assertIn("if tool=='analogue_proposal' and status=='succeeded'", source)
        self.assertIn("'proposal_parents':result['proposal_parents']", source)
        # The docking tool only accepts a molecule_csv, which is what this stores.
        from evida.contracts import CAPABILITIES
        spec = next(c for c in CAPABILITIES if c['id'] == 'molecular_docking')
        self.assertEqual(spec['input_kind'], 'molecule_csv')
        self.assertIn("'molecule_csv',result['csv_text'].encode()", source)

    def test_the_stored_csv_is_readable_by_the_docking_parser(self):
        from evida.science import molecule_rows
        from evida.analogue_proposal import propose
        value = propose({'rows': [
            {'candidate_id': 'A', 'smiles': 'COc1ccc(cc1OCC1CC1)C(=O)Nc1c(Cl)cncc1Cl'},
            {'candidate_id': 'B', 'smiles': 'OC(=O)C1(CCC(CC1)c1ccc(OC)c(OCC2CC2)c1)C#N'}]},
            {'maximum_proposals': 3})
        header, rows = molecule_rows(value['csv_text'].encode(),
                                     {'id_column': 'cid', 'smiles_column': 'smiles',
                                      'encoding': 'utf-8', 'delimiter': ','})
        self.assertEqual(header, ['cid', 'smiles', 'role', 'parent_cid'])
        ids = [r['candidate_id'] for r in rows]
        self.assertTrue(set(value['proposal_parents']) <= set(ids))
        declared = {p for group in value['proposal_parents'].values() for p in group}
        self.assertTrue(declared <= set(ids),
                        'every declared comparator must be docked in the same run')
        self.assertTrue(all(isinstance(group, list) and group
                            for group in value['proposal_parents'].values()))
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'p.sqlite3')
            wid = store.create('proposal')['id']
            aid = store.add_artifact(wid, '제안', 'molecule_csv', value['csv_text'].encode(),
                                     {'id_column': 'cid', 'smiles_column': 'smiles',
                                      'proposal_parents': value['proposal_parents']}, 'text/csv')
            stored = store.artifact(wid, aid)
            self.assertEqual(stored['meta']['proposal_parents'], value['proposal_parents'])
            self.assertIsInstance(json.dumps(stored['meta']), str)


if __name__ == '__main__':
    unittest.main()
