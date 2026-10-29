"""Anchored mechanism clauses are checked mechanically, and a failure is recorded not hidden."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from evida.discovery import catalog, record_review
from evida.research_loop import verify_basis
from evida.store import Store, dump

QUOTE = ('Placental sFLT1 silencing normalised blood pressure and proteinuria in pregnant mice, '
         'and no human interventional study has been reported.')


class MechanismBasisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'db')
        self.wid = self.store.create('basis fixture')['id']
        self.article = self.store.add_artifact(self.wid, 'source', 'article', dump({
            'status': 'succeeded', 'pmc_id': 'PMC9263991',
            'rows': [{'row_id': 'PMC9263991:0', 'section': 'Results', 'text': QUOTE}]}).encode(), {}, bump=False)
        self.search = self.store.add_artifact(self.wid, 'search', 'literature', dump({
            'status': 'succeeded', 'summary': {'returned': 0, 'hit_count': 0, 'next_cursor': None},
            'rows': []}).encode(), {}, bump=False)
        self.notes = self.store.add_artifact(self.wid, 'notes', 'research_notes', dump({}).encode(), {}, bump=False)

    def tearDown(self):
        self.temp.cleanup()

    def clause(self, quote=QUOTE, disease_match='animal_model'):
        return {'text': 'Placental sFLT1 excess raises blood pressure.', 'disease_match': disease_match,
                'context': {'disease': 'preeclampsia', 'species': 'mouse', 'tissue': 'placenta'},
                'anchor': {'artifact_id': self.article, 'row_index': 0, 'quote': quote}}

    def gap(self, count=0):
        return {'claim': 'No human interventional study of placental sFLT1 silencing.',
                'query_artifact_id': self.search, 'reported_count': count}

    def review(self, basis='default', aspects=None, priority=1):
        if basis == 'default':
            basis = {'grade': 'demonstrated', 'clauses': [self.clause()],
                     'missing_in_target_disease': [self.gap()], 'hypothesis_id': 'H1'}
        assessment = {'option_id': 'mechanism:sflt1-silencing', 'status': 'needs_evidence',
                      'priority': priority, 'comparison_group': 'preeclampsia mechanisms',
                      'reason': 'Animal interventional evidence only.',
                      'support_source_ids': [self.article], 'challenge_source_ids': [],
                      'uncertainties': ['No human data.'], 'next_action': 'Propose a discriminating measurement.'}
        if aspects is not False:
            assessment['aspects'] = aspects or {'disease_match': 0.4, 'clinical_precedent': None,
                                               'evidence_grade': 0.6, 'actionability': 0.5}
            assessment['basis'] = basis
            assessment['challenge_applies'] = None
        return {'question': 'Which mechanism should be examined first?',
                'new_options': [{'option_id': 'mechanism:sflt1-silencing', 'kind': 'mechanism',
                                 'label': 'Placental sFLT1 silencing', 'description': 'siRNA against placental sFLT1.',
                                 'source_ids': [self.article]}],
                'assessments': [assessment], 'unsearched_scope': ['Non-placental mediators unexamined.']}

    def loop(self, relation='challenges', kind='external_observation'):
        return {'hypotheses': [{'id': 'H1', 'statement': 'Placental sFLT1 excess drives the phenotype.',
                                'expected_observation': 'Circulating sFlt-1/PlGF falls with silencing.',
                                'alternatives': [], 'assessment': 'proposed', 'rationale': 'Animal evidence.',
                                'evidence': [{'source_type': 'artifact', 'source_id': self.article,
                                              'relation': 'supports', 'detail': 'Mouse result.',
                                              'applicability': 'Animal model only.'}]}],
                'next_checks': [{'id': 'NC1', 'question': 'Does circulating sFlt-1/PlGF change at that dose?',
                                 'purpose': 'Separate pharmacokinetics from mechanism.', 'hypothesis_ids': ['H1'],
                                 'possible_outcomes': [{'observation': 'sFlt-1/PlGF falls.', 'implication': 'Mechanism engaged.'},
                                                       {'observation': 'No change at that exposure.', 'implication': 'Failure is exposure, not mechanism.'}],
                                 'operation': ({'kind': 'external_observation', 'request': 'Measure circulating sFlt-1/PlGF.'}
                                               if kind == 'external_observation'
                                               else {'kind': 'researcher_input', 'request': 'Supply the cohort.'}),
                                 'outcome_links': [{'outcome_index': 1, 'followup_check_ids': [],
                                                    'effects': [{'hypothesis_id': 'H1', 'alternative_ids': [], 'part_ids': [],
                                                                 'relation': relation, 'rationale': 'Exposure-limited result.'}]}]}],
                'revision_rationale': 'Animal evidence retained; human translation still open.'}

    def check(self, review, loop=None):
        record_review(self.store, self.wid, 1, 'fixture', review)
        return verify_basis(self.store, self.wid, review, loop)

    def test_an_exact_quotation_and_recorded_count_pass(self):
        result = self.check(self.review(), self.loop())
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertEqual(row['status'], 'passed')
        self.assertEqual(row['issues'], [])
        self.assertEqual(row['clauses'][0]['status'], 'verified')
        self.assertEqual(row['clauses'][0]['match'], 'exact')
        self.assertEqual(row['clauses'][0]['links'], {'pmcid': 'PMC9263991'})
        self.assertEqual(row['gaps'][0], {'gap_index': 0, 'status': 'verified',
                                          'recorded_count': 0, 'kind': 'literature'})

    def test_a_substring_and_normalized_whitespace_still_match(self):
        review = self.review()
        review['assessments'][0]['basis']['clauses'] = [self.clause('normalised   blood\npressure and proteinuria')]
        row = self.check(review, self.loop())[0]
        self.assertEqual(row['clauses'][0]['match'], 'whitespace_or_inline_markup_normalized')
        self.assertEqual(row['status'], 'passed')

    def test_a_quotation_absent_from_the_row_is_rejected_and_recorded(self):
        review = self.review()
        review['assessments'][0]['basis']['clauses'] = [self.clause('normalised blood pressure in pregnant women')]
        row = self.check(review, self.loop())[0]
        self.assertEqual(row['clauses'][0]['status'], 'rejected')
        self.assertEqual(row['clauses'][0]['reason'], 'quote_not_in_row')
        self.assertEqual(row['issues'], ['clause_0_quote_not_in_row'])
        self.assertEqual(row['status'], 'issues_recorded')
        # The submitted record itself is stored unchanged next to the check.
        stored = json.loads(self.store.artifact(self.wid, catalog(self.store, self.wid)['options'][0]
                                                ['assessments'][0]['artifact_id'])['content'])
        self.assertEqual(stored['assessments'][0]['basis']['clauses'][0]['anchor']['quote'],
                         'normalised blood pressure in pregnant women')

    def test_a_non_source_or_unknown_anchor_is_rejected(self):
        for anchor, reason in ((self.notes, 'not_a_public_source_row'), ('art_missing', 'artifact_not_in_this_research')):
            review = self.review()
            clause = self.clause()
            clause['anchor'] = {'artifact_id': anchor, 'row_index': 0, 'quote': QUOTE}
            review['assessments'][0]['basis']['clauses'] = [clause]
            row = verify_basis(self.store, self.wid, review, self.loop())[0]
            self.assertEqual(row['clauses'][0]['reason'], reason)

    def test_a_row_beyond_the_stored_rows_is_rejected(self):
        review = self.review()
        clause = self.clause()
        clause['anchor']['row_index'] = 7
        review['assessments'][0]['basis']['clauses'] = [clause]
        self.assertEqual(verify_basis(self.store, self.wid, review, self.loop())[0]['clauses'][0]['reason'],
                         'row_not_found')

    def test_a_count_that_differs_from_the_record_is_rejected_with_the_recorded_value(self):
        review = self.review()
        review['assessments'][0]['basis']['missing_in_target_disease'] = [self.gap(count=3)]
        row = self.check(review, self.loop())[0]
        self.assertEqual(row['gaps'][0]['status'], 'rejected')
        self.assertEqual(row['gaps'][0]['reason'], 'count_differs_from_record')
        self.assertEqual(row['gaps'][0]['recorded_count'], 0)
        self.assertIn('gap_0_count_differs_from_record', row['issues'])

    def test_a_failed_search_supplies_no_count(self):
        failed = self.store.add_artifact(self.wid, 'failed', 'literature', dump({
            'status': 'failed', 'error': 'HTTP 503', 'rows': []}).encode(), {}, bump=False)
        review = self.review()
        review['assessments'][0]['basis']['missing_in_target_disease'] = [
            {'claim': 'Unknown.', 'query_artifact_id': failed, 'reported_count': None}]
        row = verify_basis(self.store, self.wid, review, self.loop())[0]
        self.assertEqual(row['gaps'][0]['reason'], 'search_has_no_recorded_total')

    def test_an_outside_target_grade_needs_a_stated_gap(self):
        review = self.review()
        review['assessments'][0]['basis']['missing_in_target_disease'] = []
        row = self.check(review, self.loop())[0]
        self.assertTrue(row['target_disease_gap_required'])
        self.assertIn('missing_in_target_disease_required', row['issues'])

    def test_an_established_target_disease_grade_needs_no_gap(self):
        review = self.review(basis={'grade': 'established', 'clauses': [self.clause(disease_match='target_disease')],
                                    'missing_in_target_disease': [], 'hypothesis_id': 'H1'})
        row = self.check(review, self.loop())[0]
        self.assertFalse(row['target_disease_gap_required'])
        self.assertEqual(row['issues'], [])

    def test_a_hypothesis_grade_needs_a_challenging_external_observation(self):
        basis = {'grade': 'hypothesis', 'clauses': [self.clause()],
                 'missing_in_target_disease': [self.gap()], 'hypothesis_id': 'H1'}
        self.assertEqual(verify_basis(self.store, self.wid, self.review(basis=basis), self.loop())[0]['issues'], [])
        for loop, expected in ((self.loop(relation='supports'), 'no_challenging_outcome'),
                               (self.loop(kind='researcher_input'), 'no_external_observation')):
            row = verify_basis(self.store, self.wid, self.review(basis=basis), loop)[0]
            self.assertEqual(row['challenge_check'], expected)
            self.assertIn('challenging_external_observation_' + expected, row['issues'])

    def test_an_unknown_hypothesis_id_is_reported_not_guessed(self):
        basis = {'grade': 'hypothesis', 'clauses': [self.clause()],
                 'missing_in_target_disease': [self.gap()], 'hypothesis_id': 'H9'}
        row = verify_basis(self.store, self.wid, self.review(basis=basis), self.loop())[0]
        self.assertEqual(row['challenge_check'], 'hypothesis_not_in_decision')

    def test_an_intermediate_review_defers_the_check_link_without_flagging_it(self):
        basis = {'grade': 'hypothesis', 'clauses': [self.clause()],
                 'missing_in_target_disease': [self.gap()], 'hypothesis_id': 'H1'}
        row = self.check(self.review(basis=basis))[0]
        self.assertEqual(row['challenge_check'], 'pending_final_decision')
        self.assertEqual(row['issues'], [])

    def test_a_legacy_assessment_without_axes_is_untouched_and_unchecked(self):
        review = self.review(aspects=False)
        self.assertEqual(self.check(review, self.loop()), [])
        option = catalog(self.store, self.wid)['options'][0]
        self.assertNotIn('basis_check', option['assessment'])
        self.assertEqual(option['assessment']['priority'], 1)

    def test_axes_without_a_basis_are_allowed_and_recorded_as_such(self):
        review = self.review(basis=None)
        row = self.check(review, self.loop())[0]
        self.assertIsNone(row['basis'])
        self.assertTrue(row['profile_kind_applicable'])

    def test_the_catalog_surfaces_the_check_beside_the_assessment(self):
        review = self.review()
        record_review(self.store, self.wid, 1, 'fixture', deepcopy(review))
        assessment = catalog(self.store, self.wid)['options'][0]['assessment']
        self.assertEqual(assessment['basis_check']['status'], 'passed')
        self.assertEqual(assessment['aspects']['clinical_precedent'], None)


if __name__ == '__main__':
    unittest.main()
