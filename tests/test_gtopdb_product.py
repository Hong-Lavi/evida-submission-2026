"""Synthetic schema/behavior replay; fixture numbers and names are not measurements."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from evida.discovery import catalog, choice_command
from evida.gtopdb import retrieve
from evida.service_credentials import CredentialError
from evida.store import Store, dump

SOURCE = Path(__file__).resolve().parent / "fixtures/gtopdb"


class GtoPdbProductTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rows = json.loads((SOURCE / "human-interactions-response.json").read_text())
        self.targets = json.loads((SOURCE / "resolve-avpr2-response.json").read_text())
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, service, spec, secret):
        self.calls.append(spec)
        return {"status": "JSON_RECEIVED", "request": spec}, copy.deepcopy(
            self.targets if spec["name"] == "resolve-target" else self.rows)

    def run_lookup(self, request=None, reader=None):
        return retrieve({"gene_symbol": "SYNTHETICGENE", "species": "Human"}, Path(self.tmp.name) / "receipts",
            request=request or self.request, secret_reader=reader or (lambda _: "fixture-only-secret"))

    def test_all_returned_observations_and_unassessed_ligands_retained(self):
        result = self.run_lookup()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual([r["raw_record"] for r in result["rows"]], self.rows)
        binding_fixture = next(r for r in result["rows"] if r["interaction_id"] == 900011)
        self.assertEqual(binding_fixture["curated_action"]["action"], "Antagonist")
        self.assertEqual(binding_fixture["measurement"]["kind"], "binding_affinity")
        self.assertEqual(binding_fixture["missing_condition_fields"], ["assayDescription", "assayConditions"])
        self.assertFalse(result["automatic_ranking"])
        # Three interactions over two ligands exercise merging without losing evidence.
        self.assertEqual(len(result["rows"]), 3)
        self.assertEqual(len({r["ligand_id"] for r in result["rows"]}), 2)
        self.assertEqual(result["rows"][1]["measurement"]["kind"], "potency_or_antagonism_assay_context_required")
        self.assertEqual(result["rows"][1]["curated_action"]["status"], "unresolved")
        self.assertEqual(result["rows"][2]["measurement"]["kind"], "unclassified")
        self.assertEqual(result["rows"][0]["reference_ids"], [900201])
        store = Store(Path(self.tmp.name) / "db"); wid = store.create("source replay")["id"]
        store.add_artifact(wid, "source replay", "gtopdb_pharmacology", dump(result).encode(), {}, bump=False)
        pool = catalog(store, wid)
        self.assertEqual(pool["total"], len({r["ligandId"] for r in self.rows}))
        self.assertEqual(sum(len(x["sources"]) for x in pool["options"]), len(self.rows))
        self.assertEqual(pool["reviewed"], 0)
        item = next(x for x in pool["options"] if x["entity_id"] == "900101")
        choice_command(store, wid, {"expected_rev": 1, "command_id": "choose",
            "option_id": item["option_id"], "text": "Review this alternative"})
        self.assertEqual(catalog(store, wid)["selected"]["option_id"], item["option_id"])

    def test_access_and_ambiguity_are_not_zero_evidence(self):
        def absent(_):
            raise CredentialError("fixture")
        missing = self.run_lookup(reader=absent)
        self.assertIsNone(missing["summary"]["record_count"]); self.assertEqual(self.calls, [])
        failed = self.run_lookup(request=lambda *args: ({"status": "AUTHENTICATION_FAILED"}, None))
        self.assertEqual(failed["access_status"], "AUTHENTICATION_FAILED")
        self.assertIsNone(failed["summary"]["record_count"])
        self.targets += copy.deepcopy(self.targets)
        ambiguous = self.run_lookup()
        self.assertEqual(ambiguous["status"], "partial")
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(ambiguous["summary"]["record_count"])

    def test_wrong_target_or_species_never_normalized_as_success(self):
        for key, value in (("targetId", 54), ("targetSpecies", "Mouse")):
            saved = copy.deepcopy(self.rows)
            self.rows[0][key] = value
            result = self.run_lookup()
            self.assertEqual(result["access_status"], "RESPONSE_SCHEMA_UNVERIFIED")
            self.assertIsNone(result["summary"]["record_count"])
            self.rows = saved

    def test_successful_empty_scope_distinct_from_failure(self):
        self.rows = []
        result = self.run_lookup()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["summary"]["record_count"], 0)
        self.assertIn("GtoPdb", " ".join(result["limits"]))


if __name__ == "__main__":
    unittest.main()
