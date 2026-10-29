"""Explicit chemistry transfer and preserved source identity, without mock science."""
import copy
import unittest

from evida.rna_author_mod import prepare_rows


def fixture():
    anti='GACCAUCAGAGGACACUUG';sense=anti.translate(str.maketrans('ACGU','UGCA'))[::-1]
    parent={'status':'succeeded','semantic_type':'conditional_full_author_ensirna_prediction',
            'structures':[{'candidate_id':'new-candidate','pdb_sha256':'fixture-only'}]}
    original={'rows':[{'candidate_id':'new-candidate','sense seq':sense,'anti seq':anti,'source_chemistry':'unknown'}]}
    args={'candidate_id':'new-candidate','designs':[{'id':'../display-only','modifications':[
        {'strand':'guide','position_1_based':2,'chemistry':'2-O-Methyl'},
        {'strand':'passenger','position_1_based':7,'chemistry':'2-Fluoro'},
        {'strand':'guide','position_1_based':5,'chemistry':'2-O-Methyl'}]}]}
    return parent,original,args


class ModifiedAuthorTransferTests(unittest.TestCase):
    def test_strand_roles_positions_and_safe_internal_ids(self):
        p,original,args=fixture();before=copy.deepcopy(original)
        rows,_,_=prepare_rows(p,original,args);row=rows[0]['author_input']
        self.assertEqual(row['ID'],'design_1')
        self.assertEqual(row['anti mod'],'2-O-Methyl');self.assertEqual(row['anti pos'],'2,5')
        self.assertEqual(row['sense mod'],'2-Fluoro');self.assertEqual(row['sense pos'],'7')
        self.assertEqual(rows[0]['design_id'],'../display-only');self.assertEqual(original,before)
        self.assertEqual(rows[0]['source_chemistry'],'unknown');self.assertIsNone(rows[0]['actual_efficacy'])

    def test_explicit_no_modification_preserves_author_zero_sentinel(self):
        p,original,args=fixture();args['designs'][0]['modifications']=[]
        row=prepare_rows(p,original,args)[0][0]['author_input']
        self.assertEqual((row['sense mod'],row['sense pos'],row['anti mod'],row['anti pos']),(0,0,0,0))

    def test_different_chemistries_do_not_overwrite_one_position(self):
        p,original,args=fixture()
        args['designs'][0]['modifications'].append({'strand':'guide','position_1_based':2,'chemistry':'2-Fluoro'})
        with self.assertRaisesRegex(ValueError,'중복'):prepare_rows(p,original,args)

    def test_unknown_chemistry_and_out_of_range_are_not_guessed(self):
        for field,value in [('chemistry','unspecified'),('position_1_based',20),('position_1_based',0),('position_1_based',True)]:
            p,original,args=fixture();args['designs'][0]['modifications'][0][field]=value
            with self.assertRaisesRegex(ValueError,'수식'):prepare_rows(p,original,args)

    def test_no_automatic_overhang_truncation_or_wrong_parent(self):
        p,original,args=fixture();original['rows'][0]['anti seq']+='UU'
        with self.assertRaisesRegex(ValueError,'19nt'):prepare_rows(p,original,args)
        p,original,args=fixture();args['candidate_id']='another-candidate'
        with self.assertRaisesRegex(ValueError,'유일한'):prepare_rows(p,original,args)
