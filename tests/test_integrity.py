"""State and failure tests, not a claim about scientific or model quality."""
import copy
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from evida.contracts import DECISION
from evida.gateway import Gateway, GatewayError
from evida.science import rdkit_properties, rna_observations
from evida.store import Conflict, Store, dump

ROOT = Path(__file__).resolve().parents[1]


def proposal(rev):
    return {"based_on_state_rev": rev, "intent_records": [], "action": "defer", "recommendation": "contract fixture",
            "reason": "synthetic transport test only", "evidence_refs": [], "alternatives": [], "changed": [],
            "preserved": [], "unknowns": [], "next_actions": [], "questions": [],
            "research_loop": {"hypotheses": [], "next_checks": [], "revision_rationale": "synthetic fixture"}}


class IntegrityTests(unittest.TestCase):
    def test_standalone_probe_preserves_development_model_policy(self):
        spec = importlib.util.spec_from_file_location('evida_api_probe', ROOT / 'scripts/api_probe.py')
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        policy = json.loads((ROOT / 'configs/api_policy.json').read_text())
        # Driven by the policy file rather than a fixed pair of names, so widening or narrowing
        # the approved list stays a policy edit and never silently loosens what may be billed.
        approved = policy.get('development_api_models', policy['allowed_models'])
        self.assertTrue(approved)
        for model in approved:
            with self.subTest(model=model):
                request = probe.build_request(policy, 'OFFLINE_TEST_VALUE', model)
                self.assertEqual(json.loads(request.data)['model'], model)
        for model in ('gpt-4o', 'gpt-5.6-nova', 'claude-opus-5'):
            with self.subTest(model=model), self.assertRaises(ValueError):
                probe.build_request(policy, 'OFFLINE_TEST_VALUE', model)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.db")
        self.state = self.store.create("Test workspace")
        self.wid = self.state["id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_retry_is_idempotent_and_conflicting_retry_rejected(self):
        body = {"kind": "intent_edit", "records": [{"label": "目標", "text": "Choose an approach; target undecided"}]}
        original = copy.deepcopy(body)
        first = self.store.command(self.wid, 1, "fixed-id", body)
        self.assertEqual(body, original)
        self.assertEqual(self.store.command(self.wid, 1, "fixed-id", body), first)
        self.assertEqual(self.store.snapshot(self.wid)["rev"], 2)
        with self.assertRaises(Conflict):
            self.store.command(self.wid, 1, "fixed-id", {"kind": "message", "text": "different"})

    def test_stale_decision_cannot_replace_current(self):
        self.store.command(self.wid, 1, "change", {"kind": "observation", "text": "new result", "synthetic": True})
        self.assertFalse(self.store.publish_decision(self.wid, 1, proposal(1), "receipt-old"))
        state = self.store.snapshot(self.wid)
        self.assertIsNone(state["decision"])
        self.assertEqual(state["events"][-1]["kind"], "decision_stale")
        self.assertEqual(state["events"][1]["body"]["origin"], "synthetic")

    def test_correction_retains_original_and_marks_old_decision(self):
        self.assertTrue(self.store.publish_decision(self.wid, 1, proposal(1), "receipt"))
        self.store.command(self.wid, 1, "c", {"kind": "correction", "text": "unit uncertain"})
        state = self.store.snapshot(self.wid)
        self.assertEqual(state["decision_rev"], 1)
        self.assertEqual(state["rev"], 2)
        self.assertEqual(state["review_status"], "needs_review")
        self.assertEqual(state["decision"]["recommendation"], "contract fixture")

    def test_user_intent_cannot_be_silently_overwritten(self):
        body = {"kind": "intent_edit", "records": [{"id": "r1", "label": "Boundary", "text": "Consider combinations"}]}
        self.store.command(self.wid, 1, "edit", body)
        p = proposal(2)
        p["intent_records"] = [{"id": "r1", "label": "Boundary", "text": "Only one modality", "origin": "inferred"}]
        self.store.publish_decision(self.wid, 2, p, "receipt")
        self.assertEqual(self.store.snapshot(self.wid)["intent"][0]["text"], "Consider combinations")

    def test_artifact_integrity_required_for_reuse(self):
        aid = self.store.add_artifact(self.wid, "result", "rdkit", b'{"status":"succeeded"}',
                                      {"result_status": "succeeded"}, bump=False)
        jid = self.store.enqueue(self.wid, 1, "rdkit", {}, "key")
        self.store.start_job(jid)
        self.store.finish_job(jid, "succeeded", aid)
        self.assertEqual(self.store.reusable(self.wid, "key")["id"], aid)
        with self.store.connect(True) as db:
            db.execute("UPDATE artifacts SET content=? WHERE id=?", (b"modified", aid))
        self.assertIsNone(self.store.reusable(self.wid, "key"))

    def test_model_paraphrase_is_not_frozen_as_a_human_edit(self):
        p = proposal(1)
        p["intent_records"] = [{"id": "i1", "label": "scope", "text": "provisional paraphrase", "origin": "researcher"}]
        self.store.publish_decision(self.wid, 1, p, "first")
        self.store.command(self.wid, 1, "clarification", {"kind": "correction", "text": "clarify requested scope"})
        p["based_on_state_rev"] = 2
        p["intent_records"][0]["text"] = "paraphrase incorporating new clarification"
        self.store.publish_decision(self.wid, 2, p, "second")
        self.assertEqual(self.store.snapshot(self.wid)["intent"][0]["text"], "paraphrase incorporating new clarification")

    def test_restart_retains_receipts_and_does_not_retry_model(self):
        jid = self.store.enqueue(self.wid, 1, "planner", {})
        self.store.start_job(jid)
        self.assertEqual(self.store.recover(), 1)
        state = Store(self.store.path).snapshot(self.wid)
        self.assertEqual(state["jobs"][0]["status"], "interrupted")
        self.assertEqual(state["events"][-1]["kind"], "job_interrupted")

    def test_two_simultaneous_planner_submissions_rejected(self):
        self.store.enqueue(self.wid, 1, "planner", {})
        with self.assertRaises(Conflict):
            self.store.enqueue(self.wid, 1, "planner", {})

    def test_cross_workspace_artifact_not_accessible(self):
        aid = self.store.add_artifact(self.wid, "source", "molecule_csv", b"input", {}, bump=False)
        other = self.store.create("Other")
        with self.assertRaises(KeyError):
            self.store.artifact(other["id"], aid)


class ScienceBoundaryTests(unittest.TestCase):
    def test_missing_invalid_and_duplicate_candidates_survive(self):
        content = b"cid,smiles\na,CCO\nb,\nc,not_smiles\nd,CCO\ne,CCO,wrong_width\n"
        result = rdkit_properties(content, {})
        self.assertEqual([r["candidate_id"] for r in result["rows"]], list("abcde"))
        self.assertEqual([r["status"] for r in result["rows"]],
                         ["succeeded", "input_missing", "invalid_input", "succeeded", "invalid_input"])
        self.assertEqual(result["rows"][0]["properties"], result["rows"][3]["properties"])
        self.assertNotEqual(result["rows"][0]["source_ref"], result["rows"][3]["source_ref"])

    def test_rna_missing_invalid_and_reported_zero_distinct(self):
        content = b"ensembl_gene_id\tbaseMean\tlog2FoldChange\tlfcSE\tstat\tpvalue\tpadj\tsymbol\ng1\t0\tNA\tbad\tNaN\t0\tNA\tGene\n"
        result = rna_observations(content, {"context": "synthetic numerical boundary test"})
        row = result["rows"][0]
        self.assertEqual(row["values"]["baseMean"], 0)
        self.assertIsNone(row["values"]["log2FoldChange"])
        self.assertEqual(row["value_states"]["lfcSE"], "invalid_numeric")
        self.assertEqual(row["reference_mapping"], "not_run")


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "configs/api_policy.json").read_text())

    def test_no_paid_fallback_or_implicit_enable(self):
        with self.assertRaises(ValueError):
            Gateway(self.policy, model="gpt-6-astra")
        with self.assertRaises(GatewayError) as context:
            Gateway(self.policy).request({"input": "test"})
        self.assertEqual(context.exception.status, "input_missing")

    def test_invalid_key_never_reaches_http_exception_text(self):
        with patch.dict("os.environ", {self.policy["secret_env"]: "synthetic-sensitive\ninvalid-header"}):
            with self.assertRaises(GatewayError) as context:
                Gateway(self.policy, True).request({"input": "contract fixture"})
            self.assertEqual(context.exception.status, "invalid_input")
            self.assertNotIn("synthetic-sensitive", str(context.exception))

    def test_actual_model_checked_and_usage_preserved(self):
        def transport(body):
            self.assertEqual(body["store"], False)
            self.assertEqual(body["model"], "gpt-5.6-terra")
            return {"id": "test-only", "model": "gpt-5.6-terra", "status": "completed", "output": [],
                    "usage": {"input_tokens": 5}}, {}
        _, receipt = Gateway(self.policy, True, transport=transport).request({"input": "contract fixture"})
        self.assertEqual(receipt["usage"]["input_tokens"], 5)
        self.assertNotIn("api-key", dump(receipt))

    def test_a_model_outside_the_approved_list_cannot_be_billed(self):
        # Decision 0041 opened the choice to every model the organizer supports, so the guard is
        # against names the policy does not carry rather than against two particular ones.
        for model in ("gpt-4o", "gpt-5.6-nova", "claude-opus-5", ""):
            with self.subTest(model=model), self.assertRaises(ValueError):
                Gateway(self.policy, enabled=True, model=model)

    def test_every_approved_model_can_actually_be_used(self):
        approved = self.policy.get("development_api_models", self.policy["allowed_models"])
        self.assertTrue(approved)
        for model in approved:
            with self.subTest(model=model):
                self.assertEqual(Gateway(self.policy, enabled=True, model=model).model, model)

    def test_http_error_records_only_diagnostic_headers(self):
        from email.message import Message
        from urllib.error import HTTPError
        headers = Message()
        headers['x-request-id'] = 'synthetic-request-id'
        headers['retry-after'] = '5'
        headers['api-key'] = 'synthetic-sensitive-value'
        def failure(_):
            raise HTTPError('https://example.invalid', 500, 'synthetic server failure', headers, None)
        with self.assertRaises(GatewayError) as context:
            Gateway(self.policy, True, transport=failure, max_output_tokens=1500).request({'input': 'fixture'})
        receipt = context.exception.receipt
        self.assertEqual(receipt['http_status'], 500)
        self.assertEqual(receipt['diagnostic_headers'], {'x-request-id': 'synthetic-request-id', 'retry-after': '5'})
        self.assertNotIn('synthetic-sensitive', dump(receipt))

    def test_substitution_and_incomplete_response_are_not_success(self):
        for actual, response_status, expected in [("gpt-5.6-luna", "completed", "identity_unverified"),
                                                   ("gpt-5.6-terra", "incomplete", "incomplete")]:
            with self.subTest(actual=actual, status=response_status):
                gateway = Gateway(self.policy, True, transport=lambda _: ({"model": actual, "status": response_status}, {}))
                with self.assertRaises(GatewayError) as context:
                    gateway.request({"input": "contract fixture"})
                self.assertEqual(context.exception.status, expected)


if __name__ == "__main__":
    unittest.main()
