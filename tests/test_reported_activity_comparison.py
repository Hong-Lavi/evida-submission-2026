"""Hand-calculated censoring, source identity and native binding controls; no fitting or network."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evida import reported_activity_comparison as c
from evida.store import Store, dump
from evida.runner import Runner, FUNCTION_TO_TOOL


def raw(target='T_A', value='10', relation='=', activity=1, **extra):
    return {'activity_id': activity, 'record_id': 5, 'document_chembl_id': 'D1', 'molecule_chembl_id': 'M1',
            'canonical_smiles': 'C[C@H](O)F', 'target_chembl_id': target, 'target_organism': 'Homo sapiens',
            'assay_chembl_id': 'ASSAY_' + target, 'standard_type': 'IC50', 'standard_value': value,
            'standard_relation': relation, 'standard_units': 'nM', 'pchembl_value': '0.00',
            'data_validity_comment': None, 'potential_duplicate': 0, 'standard_flag': 1, **extra}


def pair(a=None, b=None):
    return {side: {'raw_record': r, 'namespace': 'chembl', 'source_ref': {'artifact_id': side,
            'artifact_sha256': 'a'*64, 'json_pointer': '/rows/0', 'row_sha256': c.digest(r)},
            'source_record_ambiguous': False, 'official_smiles': None,
            'condition_context': r.get('assay_context'), 'assay_context_status': 'synthetic_control_declared_in_test'}
            for side, r in [('reference', a or raw()), ('comparator', b or raw('T_B', '100', activity=2))]}


def args():
    return {'reference_target_id': 'T_A', 'comparator_target_id': 'T_B', 'endpoint': 'IC50',
            'reason': 'Synthetic hand arithmetic', 'pairs': [{'reference': {'artifact_id': 'A', 'json_pointer': '/rows/0'},
                                                              'comparator': {'artifact_id': 'B', 'json_pointer': '/rows/0'}}]}


class ArithmeticTests(unittest.TestCase):
    def test_exact_original_values_and_units_not_rounded_pchembl(self):
        row = c.compare_pair(pair(b=raw('T_B', '.1', standard_units='uM', activity=2)), args())
        self.assertEqual(row['ratio']['point'], 10)
        self.assertEqual(row['log10_ratio']['point'], 1)
        self.assertEqual(row['direction'], 'reference_lower')
        self.assertEqual(row['condition_review']['status'], 'unknown_remaining')
        self.assertFalse(row['condition_review']['complete_protocol_verified'])
        self.assertEqual(row['reference']['raw_record']['pchembl_value'], '0.00')

    def test_open_and_closed_ratio_bounds(self):
        for ar, br, low, high, lc, hc in [
            ('<', '=', 10, None, False, False), ('<=', '>=', 10, None, True, False),
            ('>', '=', 0, 10, False, False), ('>=', '=', 0, 10, False, True),
            ('<', '<', 0, None, False, False), ('>', '>', 0, None, False, False),
            ('=', '<=', 0, 10, False, True), ('=', '>=', 10, None, True, False)]:
            with self.subTest(ar=ar, br=br):
                row = c.compare_pair(pair(raw(relation=ar), raw('T_B', '100', br, activity=2)), args())
                interval = row['ratio']
                self.assertEqual((interval['lower'], interval['upper'], interval['lower_closed'], interval['upper_closed']),
                                 (low, high, lc, hc))
                self.assertFalse(interval['lower_unbounded'])
                if low == 0:
                    self.assertIsNone(row['log10_ratio']['lower'])
                    self.assertTrue(row['log10_ratio']['lower_unbounded'])

    def test_strict_direction_at_one_depends_on_boundary(self):
        for ar, br, expected in [('<', '=', 'reference_lower'), ('<=', '=', 'unresolved'),
                                ('>', '=', 'comparator_lower'), ('>=', '=', 'unresolved'), ('=', '=', 'equal')]:
            row = c.compare_pair(pair(raw(relation=ar), raw('T_B', '10', br, activity=2)), args())
            self.assertEqual(row['direction'], expected)

    def test_missing_offtarget_and_bad_quantity_do_not_become_zero(self):
        changes = [{'standard_value': None}, {'standard_value': 0}, {'standard_value': True},
                   {'standard_value': 'NaN'}, {'standard_value': 'Infinity'}, {'standard_value': '1e900'},
                   {'standard_relation': '~'}, {'standard_relation': None}, {'standard_units': 'mg/mL'},
                   {'standard_type': 'Ki'}, {'data_validity_comment': 'Outside typical range'},
                   {'potential_duplicate': 1}, {'standard_upper_value': '200'}]
        for change in changes:
            with self.subTest(change=change):
                b = raw('T_B', '100', activity=2); b.update(change)
                row = c.compare_pair(pair(b=b), args())
                self.assertEqual(row['status'], 'unresolved'); self.assertIsNone(row['ratio'])
                self.assertEqual(row['comparator']['raw_record'], b)

    def test_source_record_stereo_and_official_structure_hold(self):
        for change in [{'document_chembl_id': 'D2'}, {'record_id': 6}, {'molecule_chembl_id': 'M2'},
                       {'canonical_smiles': 'C[C@@H](O)F'}, {'canonical_smiles': 'invalid'},
                       {'target_chembl_id': 'OTHER'}, {'record_id': None}, {'assay_chembl_id': None}]:
            b = raw('T_B', '100', activity=2); b.update(change)
            with self.subTest(change=change):
                self.assertEqual(c.compare_pair(pair(b=b), args())['status'], 'unresolved')
        bound = pair(); bound['reference']['official_smiles'] = 'CCO'
        self.assertIn('official_activity_structure_mismatch', c.compare_pair(bound, args())['reasons'])
        bound = pair(); bound['reference']['source_record_ambiguous'] = True
        self.assertIn('ambiguous_source_record_measurements', c.compare_pair(bound, args())['reasons'])

    def test_different_smiles_serialization_same_stereo_and_molar_scales(self):
        b = raw('T_B', '1e-7', activity=2, standard_units='M', canonical_smiles='F[C@@H](O)C')
        self.assertEqual(c.compare_pair(pair(b=b), args())['ratio']['point'], 10)
        for unit, value in [('pM', '100000'), ('nM', '100'), ('uM', '.1'), ('µM', '.1'), ('μM', '.1'), ('mM', '.0001')]:
            with self.subTest(unit=unit):
                self.assertEqual(c.compare_pair(pair(b=raw('T_B', value, activity=2, standard_units=unit)), args())['ratio']['point'], 10)

    def test_known_condition_conflict_and_unreported_distinct(self):
        for change in [{'target_organism': 'Mus musculus'}, {'assay_context': {'assay_cell_type': 'CHO'}}]:
            a = raw(assay_context={'assay_cell_type': 'HEK293'})
            b = raw('T_B', '100', activity=2); b.update(change)
            row = c.compare_pair(pair(a, b), args())
            self.assertEqual(row['condition_review']['status'], 'known_mismatch')
            self.assertIsNone(row['ratio'])
        row = c.compare_pair(pair(raw(assay_context={'assay_cell_type': 'HEK293'})), args())
        self.assertEqual(row['status'], 'computed_exact')
        self.assertIn('assay_cell_type', row['condition_review']['unknown_fields'])

    def test_precision_cannot_turn_a_reported_difference_into_equal(self):
        row = c.compare_pair(pair(raw(value='1'), raw('T_B', '1.0000000000000000000000000001', activity=2)), args())
        self.assertEqual(row['direction'], 'reference_lower')
        self.assertEqual(row['ratio']['point_decimal'], '1.0000000000000000000000000001')
        self.assertGreater(row['log10_ratio']['point'], 0)
        too_long = raw('T_B', '1.' + '0' * 50 + '1', activity=2)
        row = c.compare_pair(pair(b=too_long), args())
        self.assertEqual(row['status'], 'unresolved')
        self.assertIn('comparator_concentration_exceeds_50_significant_digits', row['reasons'])

    def test_repeated_activity_across_selected_pairs_retains_denominator_unresolved(self):
        a = args(); a['pairs'].append(copy.deepcopy(a['pairs'][0])); a['pairs'][1]['comparator']['artifact_id'] = 'C'
        p1 = pair(); p2 = pair(b=raw('T_B', '150', activity=3))
        result = c.evaluate({'arguments': a, 'pairs': [p1, p2], 'source_hashes': {}})
        self.assertEqual(result['summary'], {'requested_pairs': 2, 'computed_exact': 0, 'computed_interval': 0, 'unresolved': 2})
        json.dumps(result, allow_nan=False)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'source.db')
        self.wid = self.store.create('Synthetic concentration contrast')['id']
        self.a = args()
        for side, target, value, activity in [('reference', 'T_A', '10', 1), ('comparator', 'T_B', '100', 2)]:
            r = raw(target, value, activity=activity)
            source = {'source': {'url': 'https://www.ebi.ac.uk/chembl/api/data/activity.json'},
                      'rows': [{**r, 'assay_context': None}], 'response': {'activities': [r]}}
            aid = self.add('bioactivities', source)
            self.a['pairs'][0][side]['artifact_id'] = aid

    def add(self, kind, value):
        return self.store.add_artifact(self.wid, 'Synthetic source', kind, dump(value).encode(), {}, bump=False)

    def test_native_store_source_hashes_rows_and_no_mutation(self):
        before = copy.deepcopy(self.a); bundle = c.prepare(self.store, self.wid, self.a)
        out = c.evaluate(bundle)
        self.assertEqual(before, self.a)
        self.assertEqual(out['rows'][0]['ratio']['point'], 10)
        for side in ('reference', 'comparator'):
            ref = out['rows'][0][side]['source_ref']; source = self.store.artifact(self.wid, ref['artifact_id'])
            self.assertEqual(ref['artifact_sha256'], source['sha256'])
            self.assertEqual(ref['row_sha256'], c.digest(json.loads(source['content'])['rows'][0]))
        runner = Runner.__new__(Runner); runner.store = self.store
        runner.validate_tool(self.wid, c.TOOL, self.a)
        self.assertIsNone(runner.cache_key(self.wid, c.TOOL, self.a))
        self.assertEqual(FUNCTION_TO_TOOL['compare_reported_activity_pairs'], c.TOOL)

    def test_wrong_pointer_cross_workspace_and_duplicate_selection_rejected(self):
        for pointer in ['/rows/-1', '/rows/00', '/rows/1', '/response/activities/0', '/rows/0/standard_value']:
            bad = copy.deepcopy(self.a); bad['pairs'][0]['reference']['json_pointer'] = pointer
            with self.subTest(pointer=pointer), self.assertRaises(ValueError): c.prepare(self.store, self.wid, bad)
        other = self.store.create('Other workspace')['id']
        with self.assertRaises(KeyError): c.prepare(self.store, other, self.a)
        bad = copy.deepcopy(self.a); bad['pairs'] *= 2
        with self.assertRaises(ValueError): c.prepare(self.store, self.wid, bad)
        bad = copy.deepcopy(self.a); bad['pairs'] *= 61
        with self.assertRaises(ValueError): c.prepare(self.store, self.wid, bad)

    def test_modified_numeric_copy_rejected_against_original_response(self):
        source = json.loads(self.store.artifact(self.wid, self.a['pairs'][0]['reference']['artifact_id'])['content'])
        source['rows'][0]['standard_value'] = '1'
        self.a['pairs'][0]['reference']['artifact_id'] = self.add('bioactivities', source)
        with self.assertRaises(ValueError): c.prepare(self.store, self.wid, self.a)

    def test_assay_response_overrules_an_inconsistent_enriched_copy(self):
        aid = self.a['pairs'][0]['reference']['artifact_id']
        source = json.loads(self.store.artifact(self.wid, aid)['content'])
        context = {'assay_chembl_id': 'ASSAY_T_A', 'assay_cell_type': 'CHO'}
        source['assay_response'] = {'assays': [context]}
        source['rows'][0]['assay_context'] = {**context, 'assay_cell_type': 'HEK293'}
        self.a['pairs'][0]['reference']['artifact_id'] = self.add('bioactivities', source)
        with self.assertRaisesRegex(ValueError, '조건 사본'): c.prepare(self.store, self.wid, self.a)
        source['rows'][0]['assay_context'] = None
        self.a['pairs'][0]['reference']['artifact_id'] = self.add('bioactivities', source)
        with self.assertRaisesRegex(ValueError, '조건 사본'): c.prepare(self.store, self.wid, self.a)
        source['rows'][0]['assay_context'] = context
        self.a['pairs'][0]['reference']['artifact_id'] = self.add('bioactivities', source)
        bound = c.prepare(self.store, self.wid, self.a)['pairs'][0]['reference']
        self.assertEqual(bound['condition_context'], context)
        self.assertEqual(bound['assay_context_source_ref']['json_pointer'], '/assay_response/assays/0')

    def test_unbacked_assay_copy_retained_without_condition_authority(self):
        for side in ('reference', 'comparator'):
            aid = self.a['pairs'][0][side]['artifact_id']
            source = json.loads(self.store.artifact(self.wid, aid)['content'])
            source['rows'][0]['assay_context'] = {'assay_cell_type': 'HEK293'}
            self.a['pairs'][0][side]['artifact_id'] = self.add('bioactivities', source)
        row = c.evaluate(c.prepare(self.store, self.wid, self.a))['rows'][0]
        self.assertEqual(row['reference']['assay_context']['assay_cell_type'], 'HEK293')
        self.assertIsNone(row['reference']['condition_context'])
        self.assertEqual(row['reference']['assay_context_status'], 'unverified_copy')
        self.assertNotIn('assay_cell_type', row['condition_review']['matched_fields'])
        self.assertIn('assay_cell_type', row['condition_review']['unknown_fields'])

    def test_compound_measurement_and_qualification_follow_original_sha(self):
        r = raw(); enriched = {**r, 'assay_context': None}
        pool = {'source': {'url': 'https://www.ebi.ac.uk/chembl/api/data/activity.json'},
                'original_activity_response': {'activities': [r]}, 'rows': [{'smiles': r['canonical_smiles'], 'activities': [enriched]}]}
        aid = self.add('compound_candidates', pool); source = self.store.artifact(self.wid, aid)
        ref = {'artifact_id': aid, 'sha256': source['sha256'], 'json_pointer': '/rows/0/activities/0'}
        qualified = {'rows': [{'actual_parents': [{'reported_measurements': [{'source_ref': ref, 'original_measurement': enriched}]}]}]}
        qid = self.add('proposal_qualification', qualified)
        self.a['pairs'][0]['reference'] = {'artifact_id': qid, 'json_pointer': '/rows/0/actual_parents/0/reported_measurements/0'}
        bundle = c.prepare(self.store, self.wid, self.a); row = c.evaluate(bundle)['rows'][0]
        self.assertEqual(row['reference']['source_ref']['artifact_id'], aid)
        self.assertEqual(row['reference']['selected_via']['artifact_id'], qid)
        self.assertEqual(set(bundle['source_hashes']), {aid, qid, self.a['pairs'][0]['comparator']['artifact_id']})
        qualified['rows'][0]['actual_parents'][0]['reported_measurements'][0]['source_ref']['sha256'] = '0'*64
        self.a['pairs'][0]['reference']['artifact_id'] = self.add('proposal_qualification', qualified)
        with self.assertRaises(ValueError): c.prepare(self.store, self.wid, self.a)


if __name__ == '__main__': unittest.main()
