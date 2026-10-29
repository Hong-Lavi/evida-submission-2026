"""A ranking of proposals is only worth what it predicts on chemistry it has never seen.

The point of this module is the refusal. Any fingerprint model will fit a congeneric series and
report a fine number on a random split; the proposals it would then rank are made by recombining
that same series, so the number is circular. The split is therefore by Murcko scaffold, and when
the held-out correlation is not better than predicting the mean, nothing is scored at all.

Uses the pinned science runtime's RDKit and scikit-learn.
"""
import unittest

from evida.activity_model import (LIMITS, MINIMUM_HELD_OUT_SPEARMAN, MINIMUM_TRAINING_COMPOUNDS,
                                  fit, score, training_rows)

SCAFFOLDS = ['c1ccccc1', 'c1ccncc1', 'C1CCCCC1', 'c1ccc2ccccc2c1', 'C1CCNCC1', 'c1ccsc1',
             'C1CCOC1', 'c1ccc(F)cc1', 'c1ccc(Cl)cc1', 'C1CCCC1', 'c1ccc(O)cc1', 'c1ccc(N)cc1',
             'C1CCNC1', 'c1cnc2ccccc2c1']


def retrieved(label, scaffolds=SCAFFOLDS, per=6):
    rows = []
    for index, core in enumerate(scaffolds):
        for step in range(per):
            rows.append({'candidate_id': f'C{index}_{step}', 'smiles': core + 'C' * (step + 1) + 'C(=O)NCC',
                         'activities': [{'pchembl_value': label(index, step), 'standard_type': 'IC50', 'standard_relation': '='}]})
    return {'rows': rows}


class TrainingRowTests(unittest.TestCase):
    def test_only_records_with_a_comparable_value_are_used(self):
        value = {'rows': [
            {'candidate_id': 'A', 'smiles': 'CCO', 'activities': [{'pchembl_value': 7.2, 'standard_type': 'IC50', 'standard_relation': '='}]},
            {'candidate_id': 'B', 'smiles': 'CCC', 'activities': [{'standard_value': 30}]},
            {'candidate_id': 'C', 'smiles': None, 'activities': [{'pchembl_value': 8.0}]},
            {'candidate_id': 'D', 'smiles': 'CCN', 'activities': []},
        ]}
        rows = training_rows(value)
        self.assertEqual([r['candidate_id'] for r in rows], ['A'],
                         'a record without a comparable value must not be given one')

    def test_several_records_of_one_compound_become_its_median(self):
        value = {'rows': [{'candidate_id': 'A', 'smiles': 'CCO',
                           'activities': [{'pchembl_value': 6, 'standard_type': 'IC50'}, {'pchembl_value': 8, 'standard_type': 'IC50'},
                                          {'pchembl_value': 7, 'standard_type': 'IC50'}]}]}
        self.assertEqual(training_rows(value)[0]['p_activity'], 7.0)
        self.assertEqual(training_rows(value)[0]['records'], 3)


class SecondSourceTests(unittest.TestCase):
    """BindingDB reports distinct measurement types with nanomolar values."""

    def binding(self, rows):
        return {'rows': [{'row_id': f'bindingdb:{i}', 'candidate_id': f'BDBM:{i}',
                          'smiles': smiles, 'same_returned_representation_as_row': None,
                          'raw': {'smile': smiles, 'affinity_type': kind, 'affinity': value}}
                         for i, (smiles, kind, value) in enumerate(rows)]}

    def test_a_nanomolar_affinity_becomes_the_same_scale_as_pchembl(self):
        rows = training_rows({'rows': []}, extra_sources=[self.binding([('CCO', 'Ki', '10')])])
        self.assertEqual(rows[0]['p_activity'], 8.0, '10 nM is pKi 8')
        self.assertEqual(rows[0]['assay_types'], ['Ki'])
        self.assertEqual(rows[0]['source'], 'bindingdb')

    def test_an_unusable_or_repeated_record_is_skipped_rather_than_guessed(self):
        source = self.binding([('CCO', 'Ki', 'not a number'), ('CCC', 'unknown_type', '5'),
                               ('CCN', 'IC50', '0')])
        source['rows'].append({'row_id': 'bindingdb:3', 'candidate_id': 'BDBM:3', 'smiles': 'CCCC',
                               'same_returned_representation_as_row': 0,
                               'raw': {'smile': 'CCCC', 'affinity_type': 'Ki', 'affinity': '10'}})
        self.assertEqual(training_rows({'rows': []}, extra_sources=[source]), [])

    def test_a_compound_in_both_sources_keeps_its_chembl_record(self):
        chembl = {'rows': [{'candidate_id': 'CHEMBL1', 'smiles': 'CCO',
                            'activities': [{'pchembl_value': 6.0, 'standard_type': 'Ki', 'standard_relation': '='}]}]}
        rows = training_rows(chembl, extra_sources=[self.binding([('CCO', 'Ki', '10')])])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source'], 'chembl')
        self.assertEqual(rows[0]['p_activity'], 6.0)

    def test_the_summary_reports_the_selected_endpoint_and_retained_other_measurements(self):
        learnable = retrieved(lambda index, step: 5 + 0.3 * step + (1.5 if 'N' in SCAFFOLDS[index] else 0))
        extra = self.binding([('c1ccc(Br)cc1CC(=O)NCC', 'IC50', '50'),
                              ('c1ccc(I)cc1CC(=O)NCC', 'Kd', '20')])
        result = fit(learnable, extra_sources=[extra])
        self.assertEqual(result['summary']['sources']['bindingdb'], 1)
        self.assertGreater(result['summary']['sources']['chembl'], 0)
        self.assertEqual(result['summary']['pooled_assay_types'], ['IC50'])
        self.assertEqual(result['input_review']['exclusion_counts']['different_endpoint'], 1)


class HoldoutTests(unittest.TestCase):
    def test_a_model_that_cannot_predict_unseen_scaffolds_refuses_to_score(self):
        import random
        random.seed(11)
        noise = retrieved(lambda index, step: random.uniform(4, 9))
        result = fit(noise)
        self.assertEqual(result['status'], 'fitted')
        self.assertIs(result['usable'], False)
        self.assertLess(result['summary']['held_out_spearman'], MINIMUM_HELD_OUT_SPEARMAN)
        self.assertIn('순서를 매길 수 없다', result['meaning'])
        proposals = [{'smiles': 'c1ccccc1CCC(=O)NCC'}]
        verdict = score(proposals, result)
        self.assertEqual(verdict['scored'], 0)
        self.assertNotIn('predicted_p_activity', proposals[0],
                         'a refused model must leave no number behind')

    def test_a_model_that_does_predict_unseen_scaffolds_scores_and_says_how_well(self):
        learnable = retrieved(lambda index, step: 5 + 0.3 * step + (1.5 if 'N' in SCAFFOLDS[index] else 0))
        result = fit(learnable)
        self.assertIs(result['usable'], True)
        self.assertGreaterEqual(result['summary']['held_out_spearman'], MINIMUM_HELD_OUT_SPEARMAN)
        self.assertTrue(result['summary']['beats_predicting_the_mean'])
        self.assertEqual(result['summary']['split'], 'murcko_scaffold_holdout')
        proposals = [{'smiles': 'c1ccccc1CCC(=O)NCC'}, {'smiles': 'C1CCNCC1CCCC(=O)NCC'}]
        verdict = score(proposals, result)
        self.assertEqual(verdict['scored'], 2)
        for row in proposals:
            self.assertIsInstance(row['predicted_p_activity'], float)
            self.assertIn('측정값이 아니며', row['predicted_p_activity_meaning'])
            self.assertIn(str(result['summary']['held_out_spearman']),
                          row['predicted_p_activity_meaning'])

    def test_the_held_out_compounds_share_no_scaffold_with_the_training_ones(self):
        from rdkit import Chem
        from rdkit.Chem.Scaffolds import MurckoScaffold
        from evida.activity_model import _scaffold
        learnable = retrieved(lambda index, step: 5 + 0.3 * step)
        rows = training_rows(learnable)
        groups = {}
        for row in rows:
            groups.setdefault(_scaffold(row['smiles'], Chem, MurckoScaffold), []).append(row)
        ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
        train, held = [], []
        for _, members in ordered:
            (train if len(train) < len(rows) * 0.75 else held).extend(members)
        train_keys = {_scaffold(r['smiles'], Chem, MurckoScaffold) for r in train}
        held_keys = {_scaffold(r['smiles'], Chem, MurckoScaffold) for r in held}
        self.assertTrue(held_keys, 'something must be held out')
        self.assertFalse(train_keys & held_keys, 'a shared scaffold makes the number circular')

    def test_too_few_records_is_reported_rather_than_fitted(self):
        thin = retrieved(lambda index, step: 6.0, scaffolds=SCAFFOLDS[:2], per=3)
        result = fit(thin)
        self.assertEqual(result['status'], 'not_enough_activity_records')
        self.assertIs(result['usable'], False)
        self.assertEqual(result['minimum_required'], MINIMUM_TRAINING_COMPOUNDS)
        self.assertIn('활성이 없다는 뜻이 아니라', result['meaning'])

    def test_one_series_only_cannot_be_tested_and_says_so(self):
        single = retrieved(lambda index, step: 5 + step * 0.4, scaffolds=SCAFFOLDS[:2], per=18)
        result = fit(single)
        self.assertEqual(result['status'], 'not_enough_distinct_scaffolds')
        self.assertIs(result['usable'], False)
        self.assertIn('같은 계열만으로 맞춘 모델', result['meaning'])

    def test_every_answer_carries_what_the_number_is_not(self):
        for result in (fit(retrieved(lambda i, s: 5 + 0.3 * s)),
                       fit(retrieved(lambda i, s: 6.0, scaffolds=SCAFFOLDS[:2], per=3))):
            self.assertEqual(result['limits'], LIMITS)
            self.assertTrue(any('측정 활성이 아니' in line for line in result['limits']))


class WiringTests(unittest.TestCase):
    def test_the_proposal_tool_fits_and_scores_in_the_same_run(self):
        from pathlib import Path
        source = Path(__file__).resolve().parents[1].joinpath('evida/science.py').read_text()
        self.assertIn('from .activity_model import fit, score', source)
        self.assertIn("result['activity_model']['scoring'] = score(", source)
        self.assertIn("if k not in ('model', 'fingerprint')", source,
                      'a fitted model object cannot be written into a stored artifact')


if __name__ == '__main__':
    unittest.main()
