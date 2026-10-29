"""A proposed structure has to be drawn the same way a retrieved one is.

Stage 3 shows retrieved compounds with a 2D drawing of the stored SMILES, which is how a reader
tells one candidate from another at a glance. The proposals sat in the same screen as bare SMILES
strings: the interface asked for row.depiction and the backend never attached it, because
DEPICTED_KINDS listed the retrieval tools and not the proposal tool.

That made the generated half of stage 3 unreadable next to the retrieved half, which is exactly
the comparison the stage exists to support.

A depiction is a drawing of the stored string. It is not a measurement and not sample identity,
and a string RDKit cannot parse stays reported as unparsed rather than replaced by a guess - so
these check that the proposal rows are offered for drawing, not that any particular picture is
correct.
"""
from __future__ import annotations

import unittest

from evida.structure_depiction import DEPICTED_KINDS, attach, row_smiles

# What analogue_proposal actually stores: the proposed structure, the seed it came from, and the
# declared comparators. The kind the runner files it under is the tool name itself.
PROPOSAL_KIND = 'analogue_proposal'
PROPOSAL_ROWS = [
    {'candidate_id': 'proposal-1', 'smiles': 'CC(CCCc1ccccc1)OC(=O)c1ncc(C#N)o1',
     'seed': 'CCOC(=O)c1ncc(C#N)o1', 'nearest_training_similarity': 0.604},
    {'candidate_id': 'proposal-2', 'smiles': 'O=C(NCCc1ccccc1)c1nc2ncccc2o1',
     'seed': 'CCOC(=O)c1ncc(C#N)o1', 'nearest_training_similarity': 0.646},
]


class KindTests(unittest.TestCase):
    def test_the_proposal_tool_is_among_the_drawn_kinds(self):
        self.assertIn(PROPOSAL_KIND, DEPICTED_KINDS,
                      'stage 3 draws retrieved compounds but not the structures it generated, so '
                      'the two halves of the same screen cannot be read side by side')

    def test_the_retrieval_kinds_are_still_drawn(self):
        for kind in ('compound_candidates', 'literature_compounds', 'compound_selection'):
            with self.subTest(kind=kind):
                self.assertIn(kind, DEPICTED_KINDS)


class RowTests(unittest.TestCase):
    def test_a_proposal_row_offers_its_structure_string(self):
        self.assertEqual(row_smiles(PROPOSAL_ROWS[0]), PROPOSAL_ROWS[0]['smiles'])

    def test_the_seed_is_not_mistaken_for_the_proposal(self):
        # Both fields hold a structure; the row's own structure is the proposed one.
        self.assertNotEqual(row_smiles(PROPOSAL_ROWS[0]), PROPOSAL_ROWS[0]['seed'])


class AttachTests(unittest.TestCase):
    def test_a_proposal_view_is_not_returned_untouched(self):
        # The drawing subprocess is not run here; what matters is that attach recognises the kind
        # and reports on it rather than passing the view straight through.
        value = {'rows': [dict(row) for row in PROPOSAL_ROWS]}
        attach(value, PROPOSAL_KIND, cache_dir='/nonexistent-cache',
               science_python='/nonexistent-python', root='/nonexistent-root')
        self.assertIn('depiction_status', value,
                      'attach ignored the proposal view entirely, so no drawing was ever requested')

    def test_an_unrelated_kind_is_still_passed_through(self):
        value = {'rows': [dict(row) for row in PROPOSAL_ROWS]}
        attach(value, 'literature', cache_dir='/nonexistent-cache',
               science_python='/nonexistent-python', root='/nonexistent-root')
        self.assertNotIn('depiction_status', value)


if __name__ == '__main__':
    unittest.main()
