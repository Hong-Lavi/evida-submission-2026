"""RNA coordinates are checked against independent partition functions."""
import hashlib
import json
import math
import unittest
from unittest.mock import patch

import RNA

from evida import rna_sequence as rna


def reference(seq):
    return {'semantic_type': 'versioned_transcript_sequence', 'sequence_5to3': seq,
            'reference': {'transcript_id': 'synthetic-transcript', 'version': 1,
                          'sequence_sha256': hashlib.sha256(seq.encode()).hexdigest()},
            'sequence_source': {'fixture': 'synthetic, not biological evidence'}}


class RNASequenceTests(unittest.TestCase):
    def test_accessibility_matches_independent_constrained_partition_functions(self):
        # Full window removes sliding-window differences. Compute the same
        # physical event by imposing hard unpaired constraints, not indexing
        # the adapter's matrix again. A start/end swap fails by orders of magnitude.
        seq = 'GGGGAAAACCCCUUUUGGGGAAAACCCCAAAAUUUUGGGGAAAACCCCUUUUGGGGAAAACCCC'
        md = RNA.md(); md.compute_bpp = 0
        _, unrestricted = RNA.fold_compound(seq, md).pf()
        candidates = [{'id': str(i), 'guide_5to3': rna.reverse_complement(seq[i:i+19])}
                      for i in [0, 7, 29, len(seq)-19]]
        result = rna.evaluate(reference(seq), candidates, 'unmodified')
        for row in result['rows']:
            for site in row['perfect_complementary_sites']:
                constrained = RNA.fold_compound(seq, md)
                for pos in range(site['start_1_based'], site['end_1_based']+1):
                    constrained.hc_add_up(pos, RNA.CONSTRAINT_CONTEXT_ALL_LOOPS | RNA.CONSTRAINT_CONTEXT_ENFORCE)
                _, energy = constrained.pf()
                expected = math.exp(-(energy-unrestricted)/(0.00198720425864083*310.15))
                self.assertGreater(expected, 0)
                self.assertLess(abs(site['unpaired_probability']/expected-1), 0.002)
                self.assertAlmostEqual(site['opening_free_energy_kcal_mol'], energy-unrestricted, delta=0.002)

    def test_generation_orientation_edge_coordinates_and_chemical_limits(self):
        seq = 'AAGUCGAAACGUUUCCAGUGACGUACGUAA'
        result = rna.generate(reference(seq), {'start_1_based': 1, 'count': 2,
                'paired_length': 21, 'stride': len(seq)-21, 'chemistry': 'modified'})
        self.assertEqual(result['rows'][0]['guide_5to3'], 'UCACUGGAAACGUUUCGACUU')
        self.assertEqual(result['rows'][0]['perfect_complementary_sites'][0]['start_1_based'], 1)
        self.assertEqual(result['rows'][1]['perfect_complementary_sites'][0]['end_1_based'], len(seq))
        for row in result['rows']:
            self.assertEqual(row['calculation_scope'], 'unmodified_sequence_surrogate_only')
            self.assertIsNone(row['efficacy_prediction'])
            self.assertEqual(row['transcriptome_offtarget_assessment'], 'not_performed')
        self.assertIn('modification pattern', result['generation']['not_designed'])

    def test_reference_mutation_unknown_bases_and_version_disagreement_are_rejected(self):
        seq = 'ACGU'*12
        ref = reference(seq); ref['sequence_5to3'] = 'U'+seq[1:]
        with self.assertRaisesRegex(ValueError, '해시'):
            rna.evaluate(ref, [{'id': 'x', 'guide_5to3': seq[:21]}], 'unmodified')
        with self.assertRaisesRegex(ValueError, '미확인 염기'):
            rna.evaluate(reference('N'+seq[1:]), [{'id': 'x', 'guide_5to3': seq[:21]}], 'unmodified')
        accession = 'ENST00000237014'
        meta = {'id': accession, 'object_type': 'Transcript', 'version': 8}
        body = {'id': accession, 'version': 9, 'seq': seq}
        with patch.object(rna, 'fetch', side_effect=[(json.dumps(meta).encode(), {}), (json.dumps(body).encode(), {})]):
            with self.assertRaises(ValueError):
                rna.retrieve_reference({'ensembl_id': accession+'.8'})


if __name__ == '__main__':
    unittest.main()
