"""Compare binding across sizes by the residual from a size regression, not by dividing.

Three corrections were on the table and each says something different about the same 32 poses.

Raw Vina score tracks heavy-atom count at r = -0.809 here, so it ranks size.

Ligand efficiency divides by heavy-atom count, and the medicinal-chemistry literature is explicit
that this does not remove the bias: LE falls monotonically with size because binding sites are
finite and fit degrades as a ligand grows, so small molecules score high by construction. CReM's
molecules have a median of 22 heavy atoms against the control's 32, which is exactly the regime
where LE flatters.

GNINA's CNN score carries no size correlation (+0.014 measured), but it is a 0-1 pose confidence
rather than an affinity, and its training overlap with this target was never excluded.

Hajduk's review of the metrics rejects the scaled variants (FQ, SILE) for depending on an
arbitrary reference and proposes reading the residual from a direct regression of affinity on
size. That is what this computes: fit score against heavy atoms on the set in hand, and report
how far each molecule sits from what its size predicts. A molecule with a positive residual binds
better than its size explains, which is the question the comparison was always asking.
"""
from __future__ import annotations

import unittest

from evida.proposal_docking import size_residuals


def rows(pairs):
    return [{'candidate_id': f'c{i}', 'vina_score_kcal_mol': s, 'heavy_atoms': h}
            for i, (s, h) in enumerate(pairs)]


class FitTests(unittest.TestCase):
    def test_a_perfectly_size_driven_set_leaves_no_residual(self):
        # score = -0.1 * heavy exactly: nothing binds better than its size explains.
        found = size_residuals(rows([(-0.1 * h, h) for h in range(20, 40)]))
        self.assertTrue(all(abs(r['size_residual']) < 1e-6 for r in found['rows']))

    def test_the_slope_is_reported_with_its_correlation(self):
        found = size_residuals(rows([(-0.1 * h, h) for h in range(20, 40)]))
        self.assertAlmostEqual(found['slope_kcal_per_heavy_atom'], -0.1, places=4)
        self.assertLess(found['pearson_r'], -0.99)

    def test_a_molecule_below_the_line_has_a_positive_residual(self):
        # One molecule binds 2 kcal/mol better than its size predicts.
        pairs = [(-0.1 * h, h) for h in range(20, 40)]
        pairs.append((-0.1 * 30 - 2.0, 30))
        found = size_residuals(rows(pairs))
        best = max(found['rows'], key=lambda r: r['size_residual'])
        self.assertGreater(best['size_residual'], 1.5)

    def test_a_molecule_above_the_line_has_a_negative_residual(self):
        pairs = [(-0.1 * h, h) for h in range(20, 40)]
        pairs.append((-0.1 * 30 + 2.0, 30))
        found = size_residuals(rows(pairs))
        worst = min(found['rows'], key=lambda r: r['size_residual'])
        self.assertLess(worst['size_residual'], -1.5)


class RefusalTests(unittest.TestCase):
    def test_too_few_molecules_to_fit_a_line_refuses(self):
        found = size_residuals(rows([(-8.0, 20), (-9.0, 30)]))
        self.assertFalse(found['usable'])
        self.assertIn('rows', found)
        self.assertFalse(found['rows'])

    def test_one_size_only_cannot_separate_size_from_binding(self):
        # Every molecule the same size: the regression has no leverage and must say so.
        found = size_residuals(rows([(-8.0, 25), (-9.0, 25), (-10.0, 25), (-8.5, 25)]))
        self.assertFalse(found['usable'])
        self.assertIn('같은 크기', found['meaning'])

    def test_a_row_without_a_score_is_skipped(self):
        pairs = rows([(-0.1 * h, h) for h in range(20, 40)])
        pairs.append({'candidate_id': 'missing', 'vina_score_kcal_mol': None, 'heavy_atoms': 30})
        found = size_residuals(pairs)
        self.assertTrue(found['usable'])
        self.assertEqual(len(found['rows']), 20)

    def test_no_rows_at_all(self):
        self.assertFalse(size_residuals([])['usable'])


class MeaningTests(unittest.TestCase):
    def test_it_says_the_residual_is_relative_to_this_set(self):
        found = size_residuals(rows([(-0.1 * h, h) for h in range(20, 40)]))
        self.assertIn('이 집합', found['meaning'])

    def test_it_does_not_call_the_residual_an_affinity(self):
        found = size_residuals(rows([(-0.1 * h, h) for h in range(20, 40)]))
        self.assertIn('친화도', found['meaning'])
        self.assertIn('아닙니다', found['meaning'])


if __name__ == '__main__':
    unittest.main()
