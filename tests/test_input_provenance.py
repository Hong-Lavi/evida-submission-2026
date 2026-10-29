"""Correct input provenance without replacing an observation or its earlier judgment."""
from pathlib import Path
import tempfile
import unittest

from evida.runner import Runner
from evida.store import Store, dump
from test_integrity import proposal


class InputProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "provenance.db")
        self.wid = self.store.create("Synthetic feedback provenance regression")["id"]
        self.original_body = {"kind": "observation", "synthetic": False,
            "text": "흡착군 sFlt-1 중앙값 42% 감소; 등록~분만 11.5일 대 12.1일, 95% CI −3.2~2.0."}
        self.original = self.store.command(self.wid, 1, "original-observation", self.original_body)
        self.mid = self.original["message_id"]
        self.runner = Runner.__new__(Runner)
        self.runner.root = Path(__file__).resolve().parents[1]
        self.runner.store = self.store

    def tearDown(self):
        self.temp.cleanup()

    def correction(self, synthetic=True):
        return {"kind": "correction", "synthetic": False,
            "text": "원 관측의 출처 정정: 연구자가 ‘가상 시연 입력이다’라고 확인했습니다.",
            "provenance_correction": {"target_message_id": self.mid,
                "corrected_synthetic": synthetic, "reason": "연구자 확인에 따른 출처 분류 정정",
                "researcher_reply": "가상 시연 입력이다"}}

    def stored_inputs(self):
        with self.store.connect() as db:
            return [tuple(row) for row in db.execute(
                "SELECT seq,kind,body FROM events WHERE workspace=? ORDER BY seq", (self.wid,))]

    def test_correction_changes_effective_model_input_and_invalidates_old_judgment(self):
        old = proposal(2)
        old["recommendation"] = "판단 당시에는 연구자 관측으로 해석한 이전 결과"
        aid = self.store.add_artifact(self.wid, "Previous judgment", "decision_proposal",
                                      dump(old).encode(), {"based_rev": 2}, bump=False)
        self.assertTrue(self.store.publish_decision(self.wid, 2, old, aid))
        raw_before = self.stored_inputs()
        old_content = self.store.artifact(self.wid, aid)["content"]
        correction = self.store.command(self.wid, 2, "provenance-correction", self.correction())
        self.assertEqual(self.stored_inputs()[:len(raw_before)], raw_before)
        self.assertEqual(self.store.artifact(self.wid, aid)["content"], old_content)
        context = self.runner.model_context(self.wid, 3, False)
        observation = next(e for e in context["ORIGINAL_MESSAGES"] if e["body"]["message_id"] == self.mid)
        self.assertEqual(observation["body"]["origin"], "researcher_report")
        self.assertFalse(observation["body"]["synthetic"])
        effective = observation.get("effective_provenance", {})
        self.assertEqual(effective.get("origin"), "synthetic")
        self.assertTrue(effective["synthetic"])
        self.assertEqual(effective["empirical_status"], "not_empirical_observation")
        self.assertEqual(effective["corrected_by"]["message_id"], correction["message_id"])
        self.assertEqual(effective["corrected_by"]["researcher_reply"], "가상 시연 입력이다")
        self.assertEqual(context["INPUT_CHANGES"]["provenance_corrections"][0]["target_message_id"], self.mid)
        state = self.store.snapshot(self.wid)
        self.assertEqual((state["rev"], state["decision_rev"], state["review_status"]), (3, 2, "needs_review"))
        self.assertEqual(state["decision"], old)
        self.assertEqual(context["PREVIOUS_DECISION"], old)
        latest = next(e for e in state["events"] if e["body"].get("message_id") == correction["message_id"])
        self.assertFalse(latest["effective_provenance"]["synthetic"], "The classification correction itself is factual researcher input.")

    def test_effective_labels_are_idempotent_and_latest_correction_retains_history(self):
        first = self.store.command(self.wid, 2, "first-correction", self.correction())
        self.assertEqual(self.store.command(self.wid, 2, "first-correction", self.correction()), first)
        state = self.store.snapshot(self.wid)
        self.assertEqual(state["rev"], 3)
        original = next(e for e in state["events"] if e["body"].get("message_id") == self.mid)
        self.assertEqual(original.get("effective_provenance", {}).get("origin"), "synthetic")
        # A later explicit classification correction also remains an unverified report,
        # never automatic validation of clinical efficacy.
        second_body = self.correction(False)
        second_body["provenance_correction"]["researcher_reply"] = "후속 분류 확인이라는 테스트 입력"
        second = self.store.command(self.wid, 3, "second-correction", second_body)
        state = self.store.snapshot(self.wid)
        original = next(e for e in state["events"] if e["body"].get("message_id") == self.mid)
        effective = original["effective_provenance"]
        self.assertFalse(effective["synthetic"])
        self.assertEqual(effective["empirical_status"], "researcher_report_unverified")
        self.assertEqual([c["message_id"] for c in effective["corrections"]], [first["message_id"], second["message_id"]])
        self.assertFalse(original["body"]["synthetic"])

    def test_invalid_and_cross_workspace_corrections_do_not_change_state(self):
        other = self.store.create("Other workspace")["id"]
        foreign = self.store.command(other, 1, "foreign", {"kind": "observation", "text": "Other observation"})
        cases = []
        for key, value in (("target_message_id", foreign["message_id"]), ("target_message_id", "missing"),
                           ("corrected_synthetic", "true"), ("reason", ""), ("researcher_reply", "")):
            body = self.correction()
            body["provenance_correction"][key] = value
            cases.append(body)
        for changes in ({"kind": "observation"}, {"kind": "intent_edit", "records": []}, {"synthetic": True}, {"synthetic": "false"},
                        {"provenance_correction": None}, {"provenance_correction": []}):
            cases.append({**self.correction(), **changes})
        before = self.stored_inputs()
        for i, body in enumerate(cases):
            with self.subTest(i=i), self.assertRaises(ValueError):
                self.store.command(self.wid, 2, "invalid-" + str(i), body)
        self.assertEqual(self.stored_inputs(), before)
        self.assertEqual(self.store.snapshot(self.wid)["rev"], 2)

    def test_originally_synthetic_input_and_ordinary_correction_keep_their_own_labels(self):
        original = self.store.command(self.wid, 2, "synthetic-input", {
            "kind": "observation", "text": "Explicitly synthetic test", "synthetic": True})
        ordinary = self.store.command(self.wid, 3, "ordinary-correction", {
            "kind": "correction", "text": "Revise tissue context", "synthetic": False})
        state = self.store.snapshot(self.wid)
        indexed = {e["body"].get("message_id"): e for e in state["events"]}
        self.assertTrue(indexed[original["message_id"]].get("effective_provenance", {}).get("synthetic"))
        self.assertFalse(indexed[ordinary["message_id"]]["effective_provenance"]["synthetic"])
        self.assertEqual(state["input_changes"]["provenance_corrections"], [])


if __name__ == "__main__":
    unittest.main()
