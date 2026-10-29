"""Exact reference repair preserves authored judgments and unresolved references."""
import copy
from pathlib import Path
import tempfile
import unittest

from evida.hypothesis_reference_resolution import resolve
from evida.hypothesis_review import loop_sha256, prepare, validate
from evida.store import Store, dump
from test_hypothesis_review import loop_fixture, review_fixture


class ReferenceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'review.sqlite3')
        self.wid = self.store.create('Synthetic reference delivery')['id']
        self.document = {'rows': [{'result': 'Treatment X changed marker Y.'}],
                         'methods': 'Synthetic measurement protocol.'}
        self.source = self.store.add_artifact(self.wid, 'Synthetic source', 'article',
                                             dump(self.document).encode(), {}, bump=False)
        self.loop = loop_fixture()
        self.review = review_fixture(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def alias_review(self):
        review = copy.deepcopy(self.review)
        review['causal_steps'][0]['part_id'] = 'whole'
        review['causal_steps'][0]['evidence_groups'][0]['anchors'][0]['path'] = '/result/rows/0/result'
        return review

    def test_exact_aliases_preserve_every_scientific_field_input_and_store(self):
        authored = self.alias_review()
        frozen = copy.deepcopy(authored)
        state = self.store.snapshot(self.wid)
        resolved, ledger = resolve(self.store, self.wid, authored, self.loop)
        self.assertEqual(resolved, self.review)
        self.assertEqual(authored, frozen)
        self.assertEqual(self.store.snapshot(self.wid), state)
        self.assertEqual([r['kind'] for r in ledger],
                         ['whole_hypothesis_reference', 'provided_view_anchor_reference'])
        self.assertEqual(ledger[1]['source_sha256'], self.store.artifact(self.wid, self.source)['sha256'])
        self.assertTrue(ledger[1]['quote_unchanged'])
        again, second = resolve(self.store, self.wid, resolved, self.loop)
        self.assertEqual(again, resolved)
        self.assertEqual(second, [])

    def test_prepared_record_retains_authored_review_ledger_and_exact_loop_hash(self):
        authored = self.alias_review()
        frozen = copy.deepcopy(authored)
        record = prepare(self.store, self.wid, 1, authored, self.loop)['value']
        self.assertEqual(record['authored_review'], frozen)
        self.assertEqual(record['review'], self.review)
        self.assertEqual(record['loop_sha256'], loop_sha256(self.loop))
        self.assertEqual(record['summary']['verified_anchors'], 2)
        self.assertEqual(record['summary']['reference_resolutions'], 2)
        self.assertEqual(authored, frozen)

    def test_existing_result_member_never_gets_reinterpreted_as_a_wrapper(self):
        for result in (None, {'rows': [{'result': 'Different stored result.'}]}):
            with self.subTest(result=result):
                source = self.store.add_artifact(self.wid, 'Real result member', 'article',
                    dump({**self.document, 'result': result}).encode(), {}, bump=False)
                authored = review_fixture(source)
                authored['causal_steps'][0]['evidence_groups'][0]['anchors'][0]['path'] = '/result/rows/0/result'
                resolved, ledger = resolve(self.store, self.wid, authored, self.loop)
                self.assertEqual(resolved, authored)
                self.assertEqual(ledger, [])
                self.assertEqual(prepare(self.store, self.wid, 1, authored, self.loop)['value']['summary']['failed_anchors'], 1)

    def test_wrong_quote_missing_row_or_foreign_source_stays_unverified(self):
        for change in ({'quote': 'Treatment X cured disease.'}, {'path': '/result/rows/3/result'},
                       {'artifact_id': 'artifact-from-another-workspace'}):
            with self.subTest(change=change):
                authored = copy.deepcopy(self.review)
                anchor = authored['causal_steps'][0]['evidence_groups'][0]['anchors'][0]
                anchor['path'] = '/result/rows/0/result'
                anchor.update(change)
                resolved, ledger = resolve(self.store, self.wid, authored, self.loop)
                self.assertEqual(resolved, authored)
                self.assertEqual(ledger, [])
                self.assertEqual(prepare(self.store, self.wid, 1, authored, self.loop)['value']['summary']['failed_anchors'], 1)

    def test_named_parts_and_other_invalid_ids_are_never_widened_to_whole_hypothesis(self):
        for part, named in (('unknown-part', []), ('whole', [{'id': 'p1'}])):
            with self.subTest(part=part, named=named):
                authored = copy.deepcopy(self.review)
                authored['causal_steps'][0]['part_id'] = part
                loop = copy.deepcopy(self.loop)
                loop['hypotheses'][0]['assessment_scope'] = {'parts': named}
                resolved, ledger = resolve(self.store, self.wid, authored, loop)
                self.assertEqual(resolved, authored)
                self.assertEqual(ledger, [])
                with self.assertRaises(ValueError):
                    validate(resolved, {}, loop)

    def test_repeated_quote_cannot_resolve_a_potentially_relative_page_index(self):
        source = self.store.add_artifact(self.wid, 'Ambiguous row indexes', 'article', dump({
            'rows': [{'result': 'Treatment X changed marker Y.', 'time': '1h'},
                     {'result': 'Treatment X changed marker Y.', 'time': '24h'}],
            'methods': self.document['methods']}).encode(), {}, bump=False)
        authored = review_fixture(source)
        authored['causal_steps'][0]['evidence_groups'][0]['anchors'][0]['path'] = '/result/rows/0/result'
        resolved, ledger = resolve(self.store, self.wid, authored, self.loop)
        self.assertEqual(resolved, authored)
        self.assertEqual(ledger, [])
        self.assertEqual(prepare(self.store, self.wid, 1, authored, self.loop)['value']['summary']['failed_anchors'], 1)

    def test_a_declared_part_named_whole_keeps_its_identity(self):
        authored = copy.deepcopy(self.review)
        authored['causal_steps'][0]['part_id'] = 'whole'
        self.loop['hypotheses'][0]['assessment_scope'] = {'parts': [{'id': 'whole'}]}
        resolved, ledger = resolve(self.store, self.wid, authored, self.loop)
        self.assertEqual(resolved, authored)
        self.assertEqual(ledger, [])
        validate(resolved, {}, self.loop)


if __name__ == '__main__':
    unittest.main()
