"""An alert every known active for this target carries is not a finding about a proposal.

Measured on the IPF run, 2026-10-01. After the property window was anchored to the retrieved
chemistry, structural alerts became the wall instead: 5,087 of 5,259 enumerated structures were
rejected by PAINS/BRENK/NIH, and the run still returned nothing.

The same test as before settles it. Of the 25 retrieved LPAR1 ligands, 25 trip an alert and 0 pass.
The three commonest are Aliphatic_long_chain (25/25), phosphor (25/25) and isolated_alkene (24/25)
- which is to say, the alerts are firing on the fact that these are lysophosphatidic acid
analogues. The long chain and the phosphate are the pharmacophore. BRENK was assembled for generic
oral screening libraries and reads a lipid as a liability.

So an alert carried by the retrieved compounds themselves stops being a rejection and becomes a
note: the proposal shares a feature with the target's own known ligands. Every other alert still
rejects, because a liability the known compounds do NOT have is exactly the thing worth catching.
"""
from __future__ import annotations

import unittest

from evida.analogue_proposal import alerts_shared_with_retrieved, split_alert_names


class SplitTests(unittest.TestCase):
    def test_an_alert_the_retrieved_set_carries_is_not_a_rejection(self):
        rejecting, shared = split_alert_names({'Aliphatic_long_chain', 'phosphor'},
                                              {'Aliphatic_long_chain', 'phosphor',
                                               'isolated_alkene'})
        self.assertEqual(shared, {'Aliphatic_long_chain', 'phosphor'})
        self.assertEqual(rejecting, {'isolated_alkene'})

    def test_an_alert_the_retrieved_set_does_not_carry_still_rejects(self):
        rejecting, shared = split_alert_names(set(), {'michael_acceptor'})
        self.assertEqual(rejecting, {'michael_acceptor'})
        self.assertFalse(shared)

    def test_nothing_retrieved_means_every_alert_rejects(self):
        rejecting, _ = split_alert_names(set(), {'a', 'b'})
        self.assertEqual(rejecting, {'a', 'b'})

    def test_a_proposal_with_no_alerts_is_unaffected(self):
        rejecting, shared = split_alert_names({'Aliphatic_long_chain'}, set())
        self.assertFalse(rejecting)
        self.assertFalse(shared)


class RetrievedAlertTests(unittest.TestCase):
    def test_a_lipid_like_set_reports_its_own_alerts(self):
        # Long chain plus a phosphate: what an LPA analogue looks like to BRENK.
        found = alerts_shared_with_retrieved([
            {'smiles': 'CCCCCCCCCCCCCCCCCCOP(=O)(O)OCC(O)CO'},
            {'smiles': 'CCCCCCCCCCCCCCCCOP(=O)(O)OCC(O)CO'},
        ])
        self.assertTrue(found['names'], 'the retrieved ligands tripped nothing, so this set '
                                        'cannot demonstrate the behaviour')
        self.assertEqual(found['compounds'], 2)
        self.assertTrue(any('chain' in n.lower() or 'phosphor' in n.lower() for n in found['names']))

    def test_a_clean_set_shares_nothing(self):
        found = alerts_shared_with_retrieved([{'smiles': 'CCO'}, {'smiles': 'c1ccccc1'}])
        self.assertEqual(found['names'], set())

    def test_an_unreadable_structure_is_skipped(self):
        found = alerts_shared_with_retrieved([{'smiles': 'CCO'}, {'smiles': 'nonsense!!'}])
        self.assertEqual(found['unreadable'], 1)
        self.assertEqual(found['compounds'], 1)

    def test_an_empty_set_carries_no_alerts(self):
        found = alerts_shared_with_retrieved([])
        self.assertEqual(found['names'], set())
        self.assertEqual(found['compounds'], 0)


class MeaningTests(unittest.TestCase):
    def test_the_record_does_not_call_a_shared_alert_safe(self):
        found = alerts_shared_with_retrieved([
            {'smiles': 'CCCCCCCCCCCCCCCCCCOP(=O)(O)OCC(O)CO'}])
        self.assertIn('안전', found['meaning'])
        self.assertIn('아닙니다', found['meaning'])


if __name__ == '__main__':
    unittest.main()
