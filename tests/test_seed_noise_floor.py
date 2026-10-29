"""The noise floor has to be the one that was measured on this setup.

proposal_docking carried SEED_NOISE_KCAL = 0.1 with a comment citing "a measured seed-induced
spread of about 0.06 kcal/mol (median)". No record of that measurement exists anywhere in the
repository, so the threshold that decides whether one molecule beats another rested on a number
nobody could check.

Measured on 2026-10-01: six retrieved ligands, receptor 1RO6 site A:601:ROL, exhaustiveness 16,
eight seeds each, nothing else changed. The spread across seeds was 0.646 to 1.669 kcal/mol per
molecule, median 0.793, and the standard deviation per molecule ran 0.230 to 0.525.

That is eight times the threshold in use. Differences the product was treating as real
improvements are inside what the search returns for the same molecule twice.

It also retires a claim in the documents: TL beat prior by 0.80 kcal/mol on raw score, which was
described as "far above the noise floor". It is the noise floor.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from evida.proposal_docking import SEED_NOISE_KCAL

def _record():
    """The measurement, wherever this checkout keeps it."""
    here = Path(__file__).resolve()
    for candidate in (here.parents[1] / 'docs/verification/seed-noise-20261001.json',
                      here.parents[5] / 'docs/verification/seed-noise-20261001.json',
                      here.parents[3] / 'gpu-research-20260930/seed-noise.json'):
        if candidate.is_file():
            return candidate
    return None


RECORD = _record()


class ThresholdTests(unittest.TestCase):
    def test_the_threshold_covers_the_measured_spread(self):
        self.assertGreaterEqual(
            SEED_NOISE_KCAL, 0.79,
            'the threshold is below the median seed-to-seed spread measured on this setup, so '
            'differences smaller than re-running the same molecule count as improvements')

    def test_the_threshold_is_not_so_wide_it_hides_everything(self):
        # Above the largest single-molecule spread there is nothing left to compare.
        self.assertLessEqual(SEED_NOISE_KCAL, 1.7)


class RecordTests(unittest.TestCase):
    """The threshold has to be traceable to a measurement, which is what went wrong before."""

    def setUp(self):
        if RECORD is None:
            self.skipTest('seed-noise measurement not present in this checkout')
        self.record = json.loads(RECORD.read_text())

    def test_the_record_says_what_was_held_fixed(self):
        for key in ('receptor', 'site', 'exhaustiveness', 'seeds', 'molecules'):
            self.assertIn(key, self.record)

    def test_the_threshold_matches_the_measured_median(self):
        measured = self.record['range_across_seeds']['median']
        self.assertGreaterEqual(SEED_NOISE_KCAL, measured,
                                f'measured median spread {measured}, threshold {SEED_NOISE_KCAL}')

    def test_every_molecule_was_scored_more_than_once(self):
        for name, row in self.record['per_molecule'].items():
            with self.subTest(molecule=name):
                self.assertGreaterEqual(row['n'], 2)


if __name__ == '__main__':
    unittest.main()
