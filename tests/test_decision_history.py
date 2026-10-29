"""Older explanations remain retrievable after they leave the current decision."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from evida.runner import Runner
from evida.store import Store, dump
from test_integrity import proposal


class DecisionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "history.db")
        self.wid = self.store.create("Synthetic discrepancy history")["id"]
        self.runner = Runner.__new__(Runner)
        self.runner.store = self.store  # Context/retrieval need no model or science process.
        self.runner.root = Path(__file__).resolve().parents[1]

    def tearDown(self):
        self.temp.cleanup()

    def save(self, wid, rev, hypotheses, publish=True):
        p = proposal(rev)
        p["research_loop"]["hypotheses"] = hypotheses
        aid = self.store.add_artifact(wid, "Synthetic judgment", "decision_proposal",
                                      dump(p).encode(), {"based_rev": rev}, bump=False)
        if publish:
            self.store.publish_decision(wid, rev, p, aid)
        return aid, p

    def claim(self, hid, statement, assessment="inconclusive"):
        return {"id": hid, "statement": statement, "expected_observation": "Synthetic expectation",
                "assessment": assessment, "alternatives": ["Endpoint mismatch, still untested"],
                "rationale": "Synthetic test only", "evidence": []}

    def test_omitted_explanation_is_discoverable_and_full_original_is_readable(self):
        original = [self.claim("H1", "Original ranking", "challenged"),
                    self.claim("H2", "Parked endpoint explanation")]
        old_id, old = self.save(self.wid, 1, original)
        old_bytes = self.store.artifact(self.wid, old_id)["content"]
        self.store.command(self.wid, 1, "new-context", {"kind": "observation",
            "text": "Synthetic new endpoint context", "synthetic": True})
        current = copy.deepcopy(original[:1])
        current[0]["statement"] = "Later differently scoped claim with same ID"
        new_id, new = self.save(self.wid, 2, current)
        context = self.runner.model_context(self.wid, 2, False)
        history = context["DECISION_HISTORY"]
        self.assertEqual([r["decision_id"] for r in history], [old_id, new_id])
        self.assertEqual([r["state_revision"] for r in history], [1, 2])
        self.assertEqual(history[0]["hypotheses"][1]["statement"], "Parked endpoint explanation")
        self.assertEqual(history[0]["hypotheses"][0]["statement"], "Original ranking")
        self.assertEqual(history[0]["hypotheses"][0]["assessment"], "challenged")
        self.assertEqual(history[1]["hypotheses"][0]["statement"], current[0]["statement"])
        self.assertEqual(self.runner.inspect(self.wid, old_id)["result"], old)
        self.assertEqual(context["PREVIOUS_DECISION"], new)
        self.assertEqual(self.store.artifact(self.wid, old_id)["content"], old_bytes)
        self.assertEqual(self.store.snapshot(self.wid)["decision"], new)

    def test_unpublished_stale_and_other_workspace_proposals_are_not_history(self):
        kept, _ = self.save(self.wid, 1, [self.claim("H1", "Published")])
        draft, _ = self.save(self.wid, 1, [self.claim("H9", "Draft")], publish=False)
        self.store.command(self.wid, 1, "correction", {"kind": "correction", "text": "Synthetic context correction"})
        stale, _ = self.save(self.wid, 1, [self.claim("H8", "Stale unaccepted proposal")])
        other_wid = self.store.create("Other workspace")["id"]
        foreign, _ = self.save(other_wid, 1, [self.claim("H1", "Unrelated workspace")])
        context = self.runner.model_context(self.wid, 2, False)
        self.assertEqual([r["decision_id"] for r in context["DECISION_HISTORY"]], [kept])
        self.assertNotIn(draft, json.dumps(context))
        self.assertNotIn(stale, json.dumps(context))
        self.assertNotIn(foreign, json.dumps(context))

    def test_corrupt_past_record_stays_visible_without_fabricated_claims(self):
        old_id, _ = self.save(self.wid, 1, [self.claim("H2", "Old explanation")])
        new_id, _ = self.save(self.wid, 1, [self.claim("H3", "Current explanation")])
        with self.store.connect(True) as db:
            db.execute("UPDATE artifacts SET content=? WHERE id=?", (b"corrupt fixture", old_id))
        history = self.runner.model_context(self.wid, 1, False)["DECISION_HISTORY"]
        self.assertEqual(history[0]["decision_id"], old_id)
        self.assertEqual(history[0]["content_status"], "unavailable_or_integrity_failure")
        self.assertEqual(history[0]["hypotheses"], [])
        self.assertEqual(history[1]["decision_id"], new_id)
        self.assertEqual(history[1]["content_status"], "available")


if __name__ == "__main__":
    unittest.main()
