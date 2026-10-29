"""The quote-support check is advisory, cached, and must never alter or reject a record.

The model itself is exercised only when the GPU environment is present; the contract around it is
tested either way, because the important guarantees are that a missing environment changes nothing
and that an unverified quote is not sent for checking.
"""
import json
import os
from unittest.mock import patch
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evida.entailment_support import (DEFAULT_PYTHON, annotate, check, pair_key,
                                      verified_clause_indexes)
from evida.research_loop import verify_basis
from evida.store import Store

DOCUMENT = ('In the FIBRONEER-IPF trial, nerandomilast 18 mg twice daily slowed the decline in '
            'forced vital capacity at week 52 compared with placebo (-114.65 mL versus -183.48 mL).')
HAVE_ENVIRONMENT = (Path(DEFAULT_PYTHON).is_file()
                    and bool(os.environ.get('EVIDA_ENTAIL_GPU', '').strip())
                    and os.environ.get('CUDA_VISIBLE_DEVICES') != '')


# The anchor result is not written into the basis: `verify_basis` returns it separately, keyed by
# clause_index. `entry` builds the pair the way the caller assembles it, and the store test below
# proves that shape is the one `verify_basis` actually emits.
def clause(text, quote):
    return {'text': text, 'anchor': {'quote': quote}}


def entry(*clauses, verified=(0,)):
    return {'basis': {'clauses': list(clauses)},
            'check': {'clauses': [{'clause_index': i,
                                   'status': 'verified' if i in verified else 'rejected'}
                                  for i in range(len(clauses))]}}


CONTEXT = {'disease': 'IPF', 'species': 'human', 'tissue': 'lung'}


class ContractTests(unittest.TestCase):
    def test_cached_pair_contract_without_loading_any_model(self):
        claim = 'Synthetic cached claim only'
        with tempfile.TemporaryDirectory() as cache:
            path = Path(cache) / f'{pair_key(DOCUMENT, claim)}.json'
            path.write_text(json.dumps({'status': 'from_cache'}))
            with patch('evida.entailment_support.subprocess.run') as worker:
                result = check([{'document': DOCUMENT, 'claim': claim}], cache, ROOT)
            worker.assert_not_called()
            self.assertEqual(result[pair_key(DOCUMENT, claim)]['status'], 'from_cache')

    def test_the_same_pair_keys_the_same_and_a_changed_sentence_does_not(self):
        self.assertEqual(pair_key(DOCUMENT, '가'), pair_key(DOCUMENT, '가'))
        self.assertNotEqual(pair_key(DOCUMENT, '가'), pair_key(DOCUMENT, '가.'))
        self.assertNotEqual(pair_key(DOCUMENT, '가'), pair_key(DOCUMENT + ' ', '가'))

    def test_a_quote_that_did_not_verify_is_never_sent_for_checking(self):
        value = entry(clause('주장', DOCUMENT), verified=())
        with tempfile.TemporaryDirectory() as cache:
            annotate([value], cache, ROOT, python='/nonexistent/python')
        self.assertNotIn('quote_supports_clause', value['basis']['clauses'][0],
                         'an unverified quote is already reported; do not check it further')

    def test_only_the_verified_clause_of_a_mixed_basis_is_checked(self):
        value = entry(clause('첫째', DOCUMENT), clause('둘째', DOCUMENT + ' Second.'), verified=(1,))
        with tempfile.TemporaryDirectory() as cache:
            annotate([value], cache, ROOT, python='/nonexistent/python')
        first, second = value['basis']['clauses']
        self.assertNotIn('quote_supports_clause', first)
        self.assertIn('quote_supports_clause', second, 'the index must follow the clause, not the order')

    def test_a_missing_environment_reports_itself_and_changes_nothing_else(self):
        value = entry(clause('주장', DOCUMENT))
        basis = value['basis']
        with tempfile.TemporaryDirectory() as cache:
            annotate([value], cache, ROOT, python='/nonexistent/python')
        verdict = basis['clauses'][0]['quote_supports_clause']
        self.assertEqual(verdict['status'], 'unavailable')
        self.assertEqual(basis['clauses'][0]['text'], '주장', 'the record is untouched')
        self.assertEqual(basis['clauses'][0]['anchor']['quote'], DOCUMENT)

    def test_empty_and_blank_pairs_are_skipped_rather_than_sent(self):
        with tempfile.TemporaryDirectory() as cache:
            self.assertEqual(check([], cache, ROOT), {})
            self.assertEqual(check([{'document': '  ', 'claim': '가'}], cache, ROOT), {})
            self.assertEqual(check([{'document': DOCUMENT, 'claim': ''}], cache, ROOT), {})

    def test_a_basis_without_clauses_is_left_alone(self):
        values = [{'basis': {'grade': 'established'}, 'check': None}, {'basis': {'clauses': []}, 'check': None}]
        with tempfile.TemporaryDirectory() as cache:
            self.assertEqual(annotate(values, cache, ROOT, python='/nonexistent/python'), values)


class WiringTests(unittest.TestCase):
    """The check reads `verify_basis` output. Hand-built shapes let a wrong reading pass, so this
    builds the verification the way the product does and asserts the pair is actually found."""

    def verification(self):
        store = Store(Path(tempfile.mkdtemp()) / 'wiring.sqlite3')
        wid = store.create('wiring')['id']
        article = store.add_artifact(wid, 'source', 'article', json.dumps(
            {'rows': [{'text': 'Prelude. ' + DOCUMENT + ' Coda.'}], 'pmc_id': 'PMC1234567'}).encode(), {})
        review = {'assessments': [{'option_id': 'mechanism:a', 'aspects': {}, 'basis': {
            'grade': 'established', 'hypothesis_id': None, 'missing_in_target_disease': [],
            'clauses': [{'text': '네란도밀라스트가 폐활량 감소를 늦췄다.', 'disease_match': 'target_disease',
                         'context': CONTEXT,
                         'anchor': {'artifact_id': article, 'row_index': 0, 'quote': DOCUMENT}}]}}]}
        return review, verify_basis(store, wid, review)

    def test_the_verification_reports_the_clause_as_verified(self):
        _, checks = self.verification()
        self.assertEqual(checks[0]['clauses'][0]['status'], 'verified')
        self.assertEqual(verified_clause_indexes(checks[0]), {0},
                         'reading the verification must find the verified clause by index')

    def test_a_real_verification_reaches_the_check(self):
        review, checks = self.verification()
        basis = review['assessments'][0]['basis']
        with tempfile.TemporaryDirectory() as cache:
            annotate([{'basis': basis, 'check': checks[0]}], cache, ROOT, python='/nonexistent/python')
        self.assertIn('quote_supports_clause', basis['clauses'][0],
                      'the pair the product assembles must actually be sent for checking')


@unittest.skipUnless(HAVE_ENVIRONMENT, 'requires explicit EVIDA_ENTAIL_GPU plus runtime and visible GPU; CPU contract tests remain active')
class VerdictTests(unittest.TestCase):
    """Korean clauses against English sources: the pairing this product actually produces."""

    @classmethod
    def setUpClass(cls):
        cls.cache = tempfile.TemporaryDirectory()
        cls.cases = {
            'supported': '네란도밀라스트가 위약보다 폐활량 감소를 늦췄다.',
            'not_carried': '이 시험은 전자간증 환자를 등록했다.',
            'contradicted': '네란도밀라스트는 위약보다 폐활량 감소를 빠르게 했다.',
        }
        cls.result = check([{'document': DOCUMENT, 'claim': c} for c in cls.cases.values()],
                           cls.cache.name, ROOT)

    @classmethod
    def tearDownClass(cls):
        cls.cache.cleanup()

    def test_each_kind_of_pair_gets_the_verdict_it_should(self):
        for expected, claim in self.cases.items():
            with self.subTest(expected):
                self.assertEqual(self.result[pair_key(DOCUMENT, claim)]['status'], expected)

    def test_an_overclaim_is_not_reported_as_supported(self):
        with tempfile.TemporaryDirectory() as cache:
            value = check([{'document': DOCUMENT, 'claim': 'PDE4B 억제제가 섬유화를 완치한다.'}],
                          cache, ROOT)
        self.assertNotEqual(next(iter(value.values()))['status'], 'supported')

    def test_a_cached_pair_is_reused_without_running_the_model(self):
        claim = self.cases['supported']
        path = Path(self.cache.name) / f'{pair_key(DOCUMENT, claim)}.json'
        self.assertTrue(path.is_file())
        path.write_text(json.dumps({'status': 'from_cache'}))
        again = check([{'document': DOCUMENT, 'claim': claim}], self.cache.name, ROOT)
        self.assertEqual(again[pair_key(DOCUMENT, claim)]['status'], 'from_cache')


if __name__ == '__main__':
    unittest.main()
