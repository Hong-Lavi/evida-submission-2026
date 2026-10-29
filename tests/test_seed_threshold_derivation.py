"""The seed threshold must be derived from the measurement, not equal to a range that resembles it.

The gate that decides whether a proposal beat its parent was 0.793 kcal/mol, and the comment said
it was "the measured median" - the median of each molecule's highest score minus its lowest, over
eight seeds. The external review on 2026-10-01 was right that this is a category error. A
max-minus-min grows with the number of repeats, so the same molecules run with sixteen seeds would
have produced a larger threshold from the same underlying noise, and it is neither a standard
deviation nor the standard error of the quantity the gate actually tests.

What the gate tests is a difference between two molecules, each scored once. If a single score
carries seed standard deviation sigma, that difference carries sigma * sqrt(2), and a 95% criterion
is 1.96 times it. The recorded measurement gives a per-molecule sigma with a median of 0.2867, so:

    1.96 * sqrt(2) * 0.2867 = 0.7948

which is where 0.793 was all along. The number survives; its derivation did not, and a number whose
stated derivation is wrong is a number nobody can check or update.

So the constant is computed here and the test pins it to the recorded sigma. Changing the
measurement without changing the threshold, or the threshold without the measurement, now fails.

The looseness that remains is stated rather than hidden: sigma comes from six molecules on one
receptor, the per-molecule sigma reaches 0.5246 so half the molecules are under-protected by a
median-derived gate, the two scores are assumed independent, and this interface feeds one seed to
both the initial conformer and the search, so the measurement covers their combined effect.
"""
from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from evida.proposal_docking import (SEED_NOISE_KCAL, SEED_SIGMA_KCAL, SEED_CONFIDENCE_Z,
                                    LIMITS, seed_threshold)

HERE = Path(__file__).resolve().parent
RECORD = HERE.parents[4] / 'docs/verification/seed-noise-20261001.json'


class DerivationTests(unittest.TestCase):
    def test_the_threshold_is_the_standard_error_of_a_difference(self):
        self.assertAlmostEqual(seed_threshold(SEED_SIGMA_KCAL),
                               SEED_CONFIDENCE_Z * math.sqrt(2) * SEED_SIGMA_KCAL, places=10)
        self.assertAlmostEqual(SEED_NOISE_KCAL, seed_threshold(SEED_SIGMA_KCAL), places=10)

    def test_it_is_not_the_range(self):
        """0.793 is also the median range over eight seeds. That coincidence is not the reason."""
        self.assertNotAlmostEqual(SEED_NOISE_KCAL, 0.793, places=10)
        self.assertAlmostEqual(SEED_NOISE_KCAL, 0.7948, places=3)

    def test_doubling_the_noise_doubles_the_threshold(self):
        self.assertAlmostEqual(seed_threshold(2 * SEED_SIGMA_KCAL),
                               2 * seed_threshold(SEED_SIGMA_KCAL), places=10)

    def test_no_noise_means_no_gate(self):
        self.assertEqual(seed_threshold(0.0), 0.0)


class RecordTests(unittest.TestCase):
    def test_sigma_matches_the_recorded_measurement(self):
        if not RECORD.is_file():
            raise unittest.SkipTest(f'{RECORD} 가 없습니다.')
        recorded = json.loads(RECORD.read_text())
        self.assertAlmostEqual(SEED_SIGMA_KCAL, recorded['stdev_across_seeds']['median'],
                               places=4)

    def test_the_worst_molecule_is_noisier_than_the_gate_assumes(self):
        """Stated as a limit, not smoothed over: a median-derived gate under-protects half of them."""
        if not RECORD.is_file():
            raise unittest.SkipTest(f'{RECORD} 가 없습니다.')
        recorded = json.loads(RECORD.read_text())
        highest = recorded['stdev_across_seeds']['highest']
        self.assertGreater(seed_threshold(highest), SEED_NOISE_KCAL)


class LimitsTests(unittest.TestCase):
    def test_the_limits_say_what_the_threshold_is(self):
        text = '\n'.join(LIMITS)
        self.assertIn('표준편차', text)
        self.assertIn('0.2867', text)

    def test_the_limits_no_longer_call_it_a_measured_range(self):
        text = '\n'.join(LIMITS)
        self.assertNotIn('중앙값 0.793', text)

    def test_the_limits_admit_the_worst_case(self):
        text = '\n'.join(LIMITS)
        self.assertIn('0.5246', text)


if __name__ == '__main__':
    unittest.main()
