"""Synthetic schema/behavior replay; fixture numbers and names are not measurements."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from evida.lens_sources import retrieve, search_query

SOURCE = Path(__file__).resolve().parent / "fixtures/lens"


class LensSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_fixture(self, mode, name):
        raw = json.loads((SOURCE / (name + "-response.json")).read_text())
        def request(service, spec, secret):
            self.calls.append(spec)
            return {"status": "JSON_RECEIVED"}, copy.deepcopy(raw)
        args = {"mode": mode, "query": "synthetic retrieval query" if mode == "search" else "",
            "lens_id": "" if mode == "search" else "999-999-999-999-990", "offset": 0, "limit": 50}
        result = retrieve(args, Path(self.tmp.name)/mode, request=request, secret_reader=lambda _: "fixture-only-secret")
        return raw, result

    def test_both_citation_directions_retain_all_original_fields(self):
        for mode, name, field in (("references", "backward-references", "referenced_by"),
                                  ("citing", "forward-citations", "reference.lens_id")):
            raw, result = self.run_fixture(mode, name)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["rows"], raw["data"])
            self.assertEqual(self.calls[-1]["body"]["query"], {"term": {field: "999-999-999-999-990"}})
            self.assertFalse(result["citation_relation"]["claim_support_checked"])
            self.assertTrue(result["frontier"]["other_depths_and_independent_search_remain_open"])

    def test_independent_keyword_page_keeps_unreturned_scope(self):
        raw, result = self.run_fixture("search", "independent-keyword")
        self.assertEqual(result["rows"], raw["data"])
        self.assertGreater(result["summary"]["source_total"], len(result["rows"]))
        self.assertTrue(result["summary"]["source_has_more"])
        self.assertIsNone(result["citation_relation"])
        self.assertFalse(result["frontier"]["full_text_read"])

    def test_auth_failure_never_claims_no_literature(self):
        args = {"mode": "search", "query": "condition", "lens_id": "", "offset": 0, "limit": 10}
        result = retrieve(args, self.tmp.name, secret_reader=lambda _: "fixture-only-secret",
            request=lambda *args: ({"status": "AUTHENTICATION_FAILED"}, None))
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["summary"]["source_total"])
        self.assertIsNone(result["summary"]["returned"])

    def test_malformed_identifiers_counts_and_ambiguous_query_do_not_dispatch(self):
        args = {"mode": "references", "query": "also keyword", "lens_id": "999-999-999-999-990", "offset": 0, "limit": 10}
        with self.assertRaises(ValueError):
            retrieve(args, self.tmp.name, request=lambda *args: self.fail("must not dispatch"))
        args.update(mode="search", query="condition", lens_id="")
        result = retrieve(args, self.tmp.name, secret_reader=lambda _: "fixture-only-secret",
            request=lambda *args: ({"status": "JSON_RECEIVED"}, {"total": 1, "data": [{"title": "missing id"}]}))
        self.assertEqual(result["access_status"], "RESPONSE_SCHEMA_UNVERIFIED")
        self.assertIsNone(result["summary"]["source_total"])

    def test_exact_doi_url_and_identifier_are_not_general_keyword_queries(self):
        for raw in ['10.2215/CJN.11260821','https://doi.org/10.2215/CJN.11260821','doi: 10.2215/CJN.11260821']:
            self.assertEqual(search_query(raw), ({'term':{'ids.doi':'10.2215/CJN.11260821'}},'exact_doi'))
        self.assertEqual(search_query('synthetic retrieval query'),('synthetic retrieval query','keyword'))
        self.assertEqual(search_query('999-999-999-999-99X'),({'term':{'lens_id':'999-999-999-999-99X'}},'exact_lens_id'))

    def test_synthetic_returned_x_identifier_can_continue_citation_search(self):
        raw=json.loads((SOURCE/'backward-references-response.json').read_text())
        row=next(r for r in raw['data'] if r['lens_id'].endswith('X'))
        calls=[]
        def request(service,spec,secret):
            calls.append(spec)
            return {'status':'JSON_RECEIVED'}, {'total':0,'data':[]}
        result=retrieve({'mode':'references','query':'','lens_id':row['lens_id'],'offset':0,'limit':10},
                        self.tmp.name,request=request,secret_reader=lambda _: 'fixture-only-secret')
        self.assertEqual(result['status'],'succeeded')
        self.assertEqual(calls[0]['body']['query'],{'term':{'referenced_by':row['lens_id']}})


if __name__ == "__main__":
    unittest.main()
