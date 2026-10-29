"""Physical coordinate controls and reference identity boundaries, no efficacy claim."""
import hashlib
import unittest
import gemmi
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign

from evida.binding_pose import fixed_geometry, comparable_reference, deposited_references


CCD = '''data_ABC
_chem_comp.id ABC
loop_
_chem_comp_atom.atom_id
_chem_comp_atom.type_symbol
_chem_comp_atom.charge
C1 C 0
C2 C 0
O1 O 0
O2 O 0
loop_
_chem_comp_bond.atom_id_1
_chem_comp_bond.atom_id_2
_chem_comp_bond.value_order
C1 C2 SING
C2 O1 DOUB
C2 O2 SING
'''


def molecule(smiles='CC(=O)O'):
    value = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3(); params.randomSeed = 42
    if AllChem.EmbedMolecule(value, params) != 0:
        raise ValueError('Fixture embedding failed')
    return value


def structure(omit_b_oxygen=False):
    value = gemmi.Structure(); model = gemmi.Model('1'); chain = gemmi.Chain('A')
    residue = gemmi.Residue(); residue.name = 'ABC'; residue.seqid = gemmi.SeqId(1, ' '); residue.het_flag = 'H'
    for name, xyz, alt in [('C1',(0,0,0),''),('C2',(1.4,0,0),''),
                           ('O1',(2,1,0),'A'),('O2',(2,-1,0),'A'),
                           ('O1',(2.1,1,.2),'B'),('O2',(2.1,-1,.2),'B')]:
        if omit_b_oxygen and name == 'O2' and alt == 'B':
            continue
        atom = gemmi.Atom(); atom.name = name; atom.element = gemmi.Element(name[0]); atom.pos = gemmi.Position(*xyz)
        atom.altloc = alt or '\x00'; atom.occ = .5 if alt else 1
        residue.add_atom(atom)
    chain.add_residue(residue); model.add_chain(chain); value.add_model(model)
    raw = value.make_mmcif_document().as_string()
    return {'original_cif': raw, 'source': {'sha256': hashlib.sha256(raw.encode()).hexdigest()}}


class PoseEvidenceBoundaries(unittest.TestCase):
    def test_atom_reindexing_does_not_hide_coordinate_motion(self):
        original = molecule()
        reordered = Chem.RenumberAtoms(original, list(reversed(range(original.GetNumAtoms()))))
        self.assertTrue(fixed_geometry(reordered, original)['atom_order_changed'])
        conf = reordered.GetConformer()
        for i in range(reordered.GetNumAtoms()):
            p = conf.GetAtomPosition(i); p.x += 5; conf.SetAtomPosition(i, p)
        with self.assertRaisesRegex(ValueError, '좌표'):
            fixed_geometry(reordered, original)

    def test_different_compound_cannot_receive_same_compound_rmsd(self):
        self.assertIsNone(comparable_reference(molecule('CCO'), molecule('CC(=O)O')))

    def test_protonation_normalization_is_only_a_declared_geometric_match(self):
        neutral, charged = molecule('CC(=O)O'), molecule('CC(=O)[O-]')
        result = comparable_reference(charged, neutral)
        self.assertIsNotNone(result)
        self.assertEqual(result[2], 'charge_normalized_for_geometry_only_not_native_protonation')
        self.assertEqual(Chem.GetFormalCharge(charged), -1)
        self.assertEqual(Chem.GetFormalCharge(neutral), 0)

    def test_shared_atoms_are_joined_with_each_altloc_not_averaged(self):
        refs, gaps = deposited_references(structure(), 'A:1:ABC', CCD)
        self.assertFalse(gaps); self.assertEqual(len(refs), 2)
        self.assertEqual([meta['altloc'] for _, meta in refs], ['A','B'])
        self.assertGreater(rdMolAlign.CalcRMS(refs[0][0], refs[1][0]), .1)
        self.assertNotEqual(refs[0][1]['coordinate_sha256'], refs[1][1]['coordinate_sha256'])

    def test_incomplete_altloc_is_retained_as_gap_not_mixed_with_other_altloc(self):
        refs, gaps = deposited_references(structure(True), 'A:1:ABC', CCD)
        self.assertEqual(len(refs), 1); self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]['altloc'], 'B'); self.assertEqual(gaps[0]['missing'], ['O2'])

    def test_wrong_component_or_changed_original_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '성분'):
            deposited_references(structure(), 'A:1:DEF', CCD)
        data = structure(); data['original_cif'] += '\n'
        with self.assertRaisesRegex(ValueError, '해시'):
            deposited_references(data, 'A:1:ABC', CCD)


if __name__ == '__main__':
    unittest.main()
