"""Proposed structures must be traceable to the compounds this research retrieved.

Every other small-molecule path here retrieves; this one proposes, which is exactly where a
product can start inventing. So the rules that make a proposal inspectable are checked on real
molecules: both halves come from retrieved compounds and say which one, an input redrawn without
its stereochemistry is not a proposal, and the filters that were claimed actually drop things.

Uses the pinned science runtime's RDKit. Three real PDE4 inhibitors, about three seconds.
"""
import unittest

from evida.analogue_proposal import (LIMITS, PROPERTY_WINDOW, SYNTHETIC_ACCESSIBILITY_CUTOFF,
                                     propose, retrieved_smiles)

ROFLUMILAST = 'COc1ccc(cc1OCC1CC1)C(=O)Nc1c(Cl)cncc1Cl'
CILOMILAST = 'OC(=O)C1(CCC(CC1)c1ccc(OC)c(OCC2CC2)c1)C#N'
APREMILAST = 'CCOc1cc(ccc1OC)C(CS(C)(=O)=O)N1C(=O)c2ccccc2C1=O'
RETRIEVED = {'rows': [{'candidate_id': 'CHEMBL103', 'name': 'roflumilast', 'smiles': ROFLUMILAST},
                      {'candidate_id': 'CHEMBL1533', 'name': 'cilomilast', 'smiles': CILOMILAST},
                      {'candidate_id': 'CHEMBL12', 'name': 'apremilast', 'smiles': APREMILAST}]}


class AnalogueProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = propose(RETRIEVED, {'reason': '테스트', 'maximum_proposals': 8})

    def test_it_proposes_structures_that_are_not_the_inputs(self):
        self.assertEqual(self.result['status'], 'succeeded')
        self.assertTrue(self.result['rows'], 'three related inhibitors must recombine into rows')
        proposed = {row['smiles'] for row in self.result['rows']}
        self.assertFalse(proposed & {ROFLUMILAST, CILOMILAST, APREMILAST},
                         'an input returned as a proposal would be a fabricated novelty')

    def test_every_row_names_the_retrieved_compound_each_half_came_from(self):
        known = {'CHEMBL103', 'CHEMBL1533', 'CHEMBL12'}
        for row in self.result['rows']:
            self.assertIn(row['core_from'], known)
            self.assertIn(row['substituent_from'], known)
            self.assertIn(row['nearest_retrieved'], known)
            self.assertLessEqual(row['SA_score'], SYNTHETIC_ACCESSIBILITY_CUTOFF)
            self.assertLessEqual(row['MolWt'], PROPERTY_WINDOW['mw'][1])
            self.assertGreaterEqual(row['MolWt'], PROPERTY_WINDOW['mw'][0])

    def test_the_result_says_what_it_is_not(self):
        self.assertEqual(self.result['semantic_type'], 'proposed_structure')
        self.assertEqual(self.result['limits'], LIMITS)
        self.assertIn('활성 예측이 아니', self.result['meaning'])
        self.assertIn('rdkit', self.result['versions'])
        counted = self.result['summary']['dropped']
        self.assertTrue(sum(counted.values()), 'filters that never drop anything are not filters')

    def test_the_generator_that_ran_is_named_with_what_it_was_built_from(self):
        # Which generator produced a row changes what the row means, so the record says which one
        # ran, and for CReM what its fragment database was built from - nothing is shipped.
        detail = self.result['generator']
        self.assertEqual(self.result['method'], detail['method'])
        self.assertIn(detail['method'], ('crem_context_constrained_fragment_transformation',
                                         'single_cut_matched_molecular_pair_recombination'))
        if detail['method'].startswith('crem'):
            self.assertEqual(detail['fragment_database']['set_name'], 'retrieved')
            self.assertEqual(detail['fragment_database']['compounds'], 3)
            self.assertIn('this research retrieved', detail['fragment_database']['built_from'])
            for row in self.result['rows']:
                self.assertIn(row['transformed_from'], {'CHEMBL103', 'CHEMBL1533', 'CHEMBL12'})
                self.assertIn('>>', row['transformation'], 'the exact change has to be readable')
                self.assertIn(row['context_radius'], (1, 2, 3))

    def test_a_generator_that_cannot_run_says_so_instead_of_going_quiet(self):
        # An unavailable generator falls back, and the fallback is recorded rather than hidden.
        result = propose(RETRIEVED, {'maximum_proposals': 3, 'method': 'crem',
                                     'work_directory': '/proc/nonexistent-directory'})
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['method'], 'single_cut_matched_molecular_pair_recombination')
        self.assertTrue(result['generator_error'], 'the failure must be on the record')

    def test_nothing_is_proposed_when_the_stored_rows_carry_no_structures(self):
        empty = propose({'rows': [{'candidate_id': 'X', 'name': 'no structure'}]}, {})
        self.assertEqual(empty['status'], 'no_retrieved_structures')
        self.assertEqual(empty['rows'], [])
        self.assertIn('구조가 없다는 뜻', empty['meaning'])

    def test_only_the_stored_structure_strings_are_read(self):
        found = retrieved_smiles(RETRIEVED)
        self.assertEqual([x['candidate_id'] for x in found], ['CHEMBL103', 'CHEMBL1533', 'CHEMBL12'])
        self.assertEqual(retrieved_smiles({'rows': []}), [])

    def test_a_stereoisomer_of_an_input_is_not_offered_as_new(self):
        # The same molecule with its stereocentre drawn is the input, not a proposal.
        chiral = {'rows': [{'candidate_id': 'A', 'smiles': 'C[C@H](N)C(=O)Oc1ccccc1'},
                           {'candidate_id': 'B', 'smiles': 'C[C@@H](N)C(=O)Oc1ccccc1'}]}
        result = propose(chiral, {'maximum_proposals': 5})
        for row in result.get('rows', []):
            self.assertNotIn(row['smiles'].replace('@@', '@'), {'C[C@H](N)C(=O)Oc1ccccc1'})


if __name__ == '__main__':
    unittest.main()
