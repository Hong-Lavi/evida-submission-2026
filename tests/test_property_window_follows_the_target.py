"""A proposal must not be rejected for looking like the target's own known compounds.

Measured on the first real research run, 2026-10-01. The IPF case retrieved 25 official structures
of human LPAR1 ligands and enumerated 3,762 recombinations from them. Every one of the 3,762 was
dropped, all of them by the property window, none by a structural alert or a synthetic
accessibility cutoff.

The reason is that the window was a fixed drug-like box, and this target's chemistry does not live
in that box: 0 of the 25 retrieved actives pass it either. All 25 exceed the rotatable-bond limit
and 17 of 25 exceed the logP ceiling, with a median logP of 7.10 against a ceiling of 6.

So the filter was not selecting good proposals out of bad ones. It was rejecting the entire
chemical space the target occupies, and the run reported zero proposals as though the chemistry
had nothing to offer.

The window now takes the union of the generic envelope and the range the retrieved compounds
actually occupy. The generic bound still holds where the retrieved set is narrower, both bounds
are reported, and a run with no retrieved compounds keeps the generic box exactly as before.
"""
from __future__ import annotations

import unittest

from evida.analogue_proposal import PROPERTY_WINDOW, effective_property_window

# Roughly where the retrieved LPAR1 ligands sit: heavier and more lipophilic than the generic box.
LIPOPHILIC = [
    {'smiles': 'CCCCCCCCc1ccc(cc1)C(=O)Nc1ccc(cc1)C(=O)NCCCCCCC(=O)O'},
    {'smiles': 'CCCCCCCCCCc1ccc(cc1)C(=O)NCCCCCCCCC(=O)O'},
]
SMALL = [{'smiles': 'CCO'}, {'smiles': 'c1ccccc1O'}]


class NoCompoundTests(unittest.TestCase):
    def test_with_nothing_retrieved_the_generic_box_is_unchanged(self):
        found = effective_property_window([])
        for key in ('mw', 'logp'):
            self.assertEqual(found['window'][key], PROPERTY_WINDOW[key])
        for key in ('donors', 'acceptors', 'rotatable', 'tpsa'):
            self.assertEqual(found['window'][key], PROPERTY_WINDOW[key])

    def test_it_says_the_bound_came_from_the_generic_box(self):
        self.assertEqual(effective_property_window([])['basis'], 'generic_only')


class WideningTests(unittest.TestCase):
    def setUp(self):
        self.found = effective_property_window(LIPOPHILIC)

    def test_the_retrieved_compounds_pass_their_own_window(self):
        # The property the whole change exists for.
        self.assertTrue(self.found['retrieved_all_inside'],
                        'the target\'s own known compounds still fail the filter: '
                        f"{self.found['observed']}")

    def test_the_window_never_narrows_below_the_generic_box(self):
        window = self.found['window']
        self.assertLessEqual(window['mw'][0], PROPERTY_WINDOW['mw'][0])
        self.assertGreaterEqual(window['mw'][1], PROPERTY_WINDOW['mw'][1])
        self.assertGreaterEqual(window['rotatable'], PROPERTY_WINDOW['rotatable'])
        self.assertGreaterEqual(window['tpsa'], PROPERTY_WINDOW['tpsa'])

    def test_both_bounds_are_reported(self):
        self.assertIn('generic', self.found)
        self.assertIn('observed', self.found)
        self.assertEqual(self.found['basis'], 'generic_union_retrieved')

    def test_a_narrower_retrieved_set_does_not_tighten_the_box(self):
        # Small molecules must not shrink the ceiling and exclude ordinary drug-like proposals.
        window = effective_property_window(SMALL)['window']
        self.assertEqual(window['mw'][1], PROPERTY_WINDOW['mw'][1])
        self.assertEqual(window['rotatable'], PROPERTY_WINDOW['rotatable'])

    def test_an_unreadable_structure_is_skipped_not_fatal(self):
        found = effective_property_window(LIPOPHILIC + [{'smiles': 'not a structure'}])
        self.assertTrue(found['retrieved_all_inside'])
        self.assertEqual(found['unreadable'], 1)


class MeaningTests(unittest.TestCase):
    def test_the_record_says_why_the_window_is_what_it_is(self):
        meaning = effective_property_window(LIPOPHILIC)['meaning']
        self.assertTrue(meaning and len(meaning) > 30)

    def test_the_record_denies_being_a_safety_or_activity_claim(self):
        # Passing a property window says the numbers are in range and nothing else. A reader who
        # takes it for a safety signal is the failure this sentence exists to prevent.
        meaning = effective_property_window(LIPOPHILIC)['meaning']
        self.assertIn('아닙니다', meaning)
        self.assertTrue('안전' in meaning and '활성' in meaning)


if __name__ == '__main__':
    unittest.main()
