"""Naming a stored structure.

A screen that shows only CHEMBL103 tells a chemist nothing. But a name invented here would be
worse than none, so the name comes from PubChem's record for that exact structure and keeps the
CID that proves it. A structure PubChem does not hold stays unnamed.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evida.chemical_names import name_structures

ASPIRIN = 'CC(=O)Oc1ccccc1C(=O)O'


def reply(**properties):
    # The shape science.fetch actually returns: (body, receipt). A body-only fake passed every
    # test here while every real lookup failed with TypeError.
    body = json.dumps({'PropertyTable': {'Properties': [properties]}}).encode()
    return body, {'http_status': 200}


class NamingTests(unittest.TestCase):
    def test_a_structure_pubchem_holds_gets_its_systematic_name_and_the_record_behind_it(self):
        rows = [{'candidate_id': 'CHEMBL25', 'smiles': ASPIRIN}]
        report = name_structures(rows, lambda url: reply(
            CID=2244, IUPACName='2-acetyloxybenzoic acid', Title='Aspirin',
            MolecularFormula='C9H8O4', InChIKey='BSYNRYMUTXBXSQ-UHFFFAOYSA-N',
            CanonicalSMILES=ASPIRIN))
        self.assertEqual(rows[0]['iupac_name'], '2-acetyloxybenzoic acid')
        self.assertEqual(rows[0]['pubchem_title'], 'Aspirin', 'the name people actually say')
        self.assertEqual(rows[0]['pubchem_cid'], 2244, 'a reader can open the record')
        self.assertEqual(report['named'], 1)

    def test_a_structure_pubchem_does_not_hold_stays_unnamed(self):
        rows = [{'candidate_id': 'X', 'smiles': 'CC(C)(C)N1CCC1'}]
        report = name_structures(rows, lambda url: (json.dumps({'PropertyTable': {}}).encode(), {}))
        self.assertNotIn('iupac_name', rows[0])
        self.assertEqual(report['named'], 0)
        self.assertIn('이 구조가 없다는 뜻', report['limits'][2])

    def test_a_different_skeleton_coming_back_is_refused_rather_than_named(self):
        # A redirect to a salt or another compound would put the wrong name on this row.
        rows = [{'candidate_id': 'Y', 'smiles': ASPIRIN, 'inchikey': 'BSYNRYMUTXBXSQ-UHFFFAOYSA-N'}]
        name_structures(rows, lambda url: reply(
            CID=999, IUPACName='something else', InChIKey='AAAAAAAAAAAAAA-UHFFFAOYSA-N',
            CanonicalSMILES='CCO'))
        self.assertNotIn('iupac_name', rows[0])
        self.assertIn('pubchem_structure_differs', rows[0])

    def test_a_failed_lookup_is_recorded_and_the_other_rows_still_run(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if len(calls) == 1:
                raise TimeoutError('slow')
            return reply(CID=1, IUPACName='ethanol', CanonicalSMILES='CCO')

        rows = [{'candidate_id': 'A', 'smiles': ASPIRIN}, {'candidate_id': 'B', 'smiles': 'CCO'}]
        report = name_structures(rows, fetch)
        self.assertNotIn('iupac_name', rows[0])
        self.assertEqual(rows[1]['iupac_name'], 'ethanol')
        self.assertEqual(report['lookup_failures'][0]['reason'], 'TimeoutError')

    def test_the_same_structure_is_looked_up_once(self):
        calls = []
        rows = [{'candidate_id': 'A', 'smiles': ASPIRIN}, {'candidate_id': 'B', 'smiles': ASPIRIN}]
        name_structures(rows, lambda url: calls.append(url) or reply(
            CID=2244, IUPACName='2-acetyloxybenzoic acid', CanonicalSMILES=ASPIRIN))
        self.assertEqual(len(calls), 1)
        self.assertEqual(rows[0]['iupac_name'], rows[1]['iupac_name'])

    def test_a_row_that_already_has_a_name_or_no_structure_is_left_alone(self):
        rows = [{'candidate_id': 'A', 'smiles': ASPIRIN, 'iupac_name': 'kept'},
                {'candidate_id': 'B', 'name': 'no structure string'}]
        report = name_structures(rows, lambda url: self.fail('no lookup should happen'))
        self.assertEqual(rows[0]['iupac_name'], 'kept')
        self.assertEqual(report['looked_up'], 0)

    def test_the_number_of_lookups_is_capped(self):
        rows = [{'candidate_id': str(i), 'smiles': 'C' * (i + 1)} for i in range(10)]
        report = name_structures(rows, lambda url: reply(CID=1, IUPACName='x'), limit=3)
        self.assertEqual(report['looked_up'], 3)
        self.assertEqual(report['lookup_limit'], 3)


if __name__ == '__main__':
    unittest.main()
