"""A cofactor touching the ligand must stop the preparation, not be measured from the box centre.

prepare_receptor removes everything that is not an amino acid, and guards that with a refusal: if
another component sits near the selected site, it will not silently simplify the structure. The guard
measures the distance from each component to the centre of the docking box.

That is the wrong reference point, and 1RO6 shows why. PDE4B's catalytic site holds two metals, and
in that entry they sit 9.12 A and 9.40 A from the box centre - past the 8 A guard - while sitting
3.26 A and 3.55 A from the nearest heavy atom of rolipram, the co-crystal ligand the site is defined
by. A 22 A box reaches 11 A from its centre, so both metals are inside the box the search runs in.
Both are removed, silently, and every score computed on that receptor is a score on a metal-stripped
metallohydrolase.

The guard should ask what it means to ask: is another component near the ligand that defines this
site, or inside the box the search will explore. Distance to the box centre answers neither.

Refusing is the right outcome rather than an inconvenience. Putting the metals back is a separate
scientific decision with its own parameterisation - AutoDock ships a distinct model for zinc
coordination and nothing licenses reusing it for manganese - and the product's job here is to say
that the structure needs that decision, not to make it by deletion.
"""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from evida.binding import prepare_receptor

HERE = Path(__file__).resolve().parent
# The deposited entry, as a fetch_structure call stored it. Kept out of the product tree because it
# is 1.5 MB of primary data; the test skips rather than inventing coordinates, since a synthetic
# structure could not show the arrangement that caused the defect.
STORED = HERE.parents[3] / 'gpu-research-20260930/docking/1RO6.json'


def stored_structure():
    if not STORED.is_file():
        raise unittest.SkipTest(f'1RO6 원문이 {STORED} 에 없습니다.')
    return json.loads(STORED.read_text())


class NearTheLigandTests(unittest.TestCase):
    def test_the_metals_are_inside_the_box_and_close_to_the_ligand(self):
        """The arrangement the guard has to catch, measured from the deposited coordinates."""
        import gemmi
        structure_data = stored_structure()
        block = gemmi.cif.read_string(structure_data['original_cif']).sole_block()
        structure = gemmi.make_structure_from_block(block)
        structure.setup_entities()
        ligand, metals = [], {}
        for chain in structure[0]:
            for residue in chain:
                if residue.name == 'ROL':
                    ligand += [a for a in residue if a.element.name != 'H']
                elif residue.name in ('ZN', 'MN'):
                    metals[residue.name] = [a for a in residue]
        self.assertTrue(ligand, '1RO6 에서 ROL 을 찾지 못했습니다.')
        self.assertEqual(sorted(metals), ['MN', 'ZN'])
        for name, atoms in metals.items():
            nearest = min(math.dist([a.pos.x, a.pos.y, a.pos.z], [l.pos.x, l.pos.y, l.pos.z])
                          for a in atoms for l in ligand)
            self.assertLess(nearest, 4.0, f'{name} 이 리간드에서 4 A 이상 떨어져 있습니다.')

    def test_preparing_this_site_is_refused(self):
        structure_data = stored_structure()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / 'work'
            work.mkdir()
            with self.assertRaises(ValueError) as raised:
                prepare_receptor(structure_data, 'A:601:ROL', work)
        message = str(raised.exception)
        self.assertIn('ZN', message.upper())
        self.assertIn('MN', message.upper())

    def test_the_refusal_says_how_close_to_the_ligand_they_are(self):
        """A refusal that only gives a distance to a box centre cannot be acted on."""
        structure_data = stored_structure()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / 'work'
            work.mkdir()
            with self.assertRaises(ValueError) as raised:
                prepare_receptor(structure_data, 'A:601:ROL', work)
        message = str(raised.exception)
        self.assertIn('minimum_distance_to_site_component_angstrom', message)
        found = json.loads(message[message.index('['):])
        by_name = {row['name']: row for row in found}
        self.assertLess(by_name['ZN']['minimum_distance_to_site_component_angstrom'], 4.0)
        self.assertTrue(by_name['ZN']['inside_docking_box'])

    def test_a_component_far_from_both_is_still_removed_without_refusing(self):
        """The arsenic at 24 A from the ligand is a crystallisation additive, not a cofactor."""
        structure_data = stored_structure()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / 'work'
            work.mkdir()
            with self.assertRaises(ValueError) as raised:
                prepare_receptor(structure_data, 'A:601:ROL', work)
        found = json.loads(str(raised.exception)[str(raised.exception).index('['):])
        self.assertNotIn('ARS', {row['name'] for row in found})


if __name__ == '__main__':
    unittest.main()
