"""When 2D similarity stops discriminating, the number must not read as a verified result.

Measured on the IPF run once the filters were corrected: all 40 returned proposals came back with
tanimoto_to_nearest = 1.0 against different SMILES, different molecular weights and different
logP. The Morgan fingerprint saturates on long aliphatic chains - an LPA analogue with two extra
methylenes sets the same bits - so for this chemistry the similarity is not measuring closeness,
it is measuring that the descriptor has run out of resolution.

That matters twice. The applicability-domain check passes trivially at 1.0, and a reader sees
"1.0" and concludes the proposal was checked against the training set. Neither is true here.

So saturation is detected and said. The similarity is still reported, because it is what was
computed; what changes is that the record stops implying it discriminated.
"""
from __future__ import annotations

import unittest

from evida.analogue_proposal import similarity_saturation


def rows(values):
    return [{'tanimoto_to_nearest': v} for v in values]


class SaturationTests(unittest.TestCase):
    def test_every_proposal_at_one_is_saturated(self):
        found = similarity_saturation(rows([1.0] * 40))
        self.assertTrue(found['saturated'])
        self.assertEqual(found['at_or_near_one'], 40)

    def test_a_spread_of_values_is_not_saturated(self):
        found = similarity_saturation(rows([0.31, 0.44, 0.58, 0.62, 0.77, 0.91]))
        self.assertFalse(found['saturated'])

    def test_a_few_identical_matches_are_not_saturation(self):
        # Two of twenty at 1.0 is an ordinary near-duplicate, not a broken descriptor.
        found = similarity_saturation(rows([1.0, 1.0] + [0.3 + i * 0.03 for i in range(18)]))
        self.assertFalse(found['saturated'])

    def test_no_rows_is_not_saturation(self):
        self.assertFalse(similarity_saturation([])['saturated'])

    def test_it_reports_the_spread_it_measured(self):
        found = similarity_saturation(rows([0.4, 0.6, 0.8]))
        self.assertAlmostEqual(found['lowest'], 0.4)
        self.assertAlmostEqual(found['highest'], 0.8)
        self.assertEqual(found['proposals'], 3)


class MeaningTests(unittest.TestCase):
    def test_the_saturated_message_says_the_measure_stopped_discriminating(self):
        meaning = similarity_saturation(rows([1.0] * 12))['meaning']
        self.assertTrue(meaning)
        self.assertIn('적용 범위', meaning)

    def test_an_unsaturated_run_carries_no_warning(self):
        self.assertIsNone(similarity_saturation(rows([0.3, 0.5, 0.7]))['meaning'])

    def test_a_row_without_the_field_is_skipped_not_fatal(self):
        found = similarity_saturation([{'tanimoto_to_nearest': 1.0}, {}, {'x': 1}])
        self.assertEqual(found['proposals'], 1)


if __name__ == '__main__':
    unittest.main()
