"""Synthetic model transport + actual RDKit tests. No live model-quality claim."""
import json
import tempfile
import unittest
from pathlib import Path

from evida.gateway import Gateway
from evida.runner import Runner
from evida.store import Store
from test_integrity import proposal
from planner_fixtures import current_frame, current_final

ROOT = Path(__file__).resolve().parents[1]


class OrchestrationTests(unittest.TestCase):
    def exercise(self, correct_during_final=False):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "state.db")
            state = store.create("Synthetic transport test")
            wid = state["id"]
            aid = store.add_artifact(wid, "synthetic fixture", "molecule_csv", b"cid,smiles\nfixture,CCO\n",
                                     {"context": "synthetic protocol fixture"}, "text/csv", bump=False)
            calls = []
            def transport(request):
                calls.append(request)
                if len(calls) == 1:
                    args = {"intent_records": [], "current_question": "synthetic transport test", "task_brief": [], "questions": [], "hypotheses": []}
                    args = current_frame(store, wid, args)
                    output = [{"type": "function_call", "name": "frame_work", "arguments": json.dumps(args), "call_id": "call-frame", "id": "fixture-frame"}]
                elif len(calls) == 2:
                    self.assertTrue(any(i.get("type") == "function_call_output" for i in request["input"]))
                    output = [{"type": "function_call", "name": "compute_properties", "arguments": json.dumps({"artifact_id": aid, "research_notes": {"findings": [], "open_questions": [], "next_goal": "synthetic transport"}}), "call_id": "call-properties", "id": "fixture-properties"}]
                else:
                    tool_output = json.loads([i for i in request["input"] if i.get("call_id") == "call-properties" and i.get("type") == "function_call_output"][-1]["output"])
                    self.assertEqual(tool_output["result"]["summary"]["calculated"], 1)
                    p = proposal(1)
                    p["evidence_refs"] = [tool_output["artifact_id"]]
                    bundle = current_final(store, wid, p)
                    if correct_during_final:
                        store.command(wid, 1, "concurrent-correction", {"kind": "correction", "text": "new condition", "synthetic": True})
                    output = [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(bundle)}]}]
                return {"id": f"fixture-{len(calls)}", "model": "gpt-5.6-terra", "status": "completed", "usage": {"input_tokens": 0, "output_tokens": 0}, "output": output}, {}
            gateway = Gateway(json.loads((ROOT / "configs/api_policy.json").read_text()), True, transport=transport)
            runner = Runner(ROOT, store, gateway, Path(temp) / "attempts")
            try:
                jid = store.enqueue(wid, 1, "planner", {})
                runner.run_planner(jid)
                state = store.snapshot(wid)
                job = next(j for j in state["jobs"] if j["id"] == jid)
                self.assertEqual(len(calls), 3, job.get("error"))
                self.assertEqual(job["status"], "stale" if correct_during_final else "succeeded", job.get("error"))
                receipts = [store.artifact(wid, a["id"]) for a in state["artifacts"] if a["kind"] == "model_receipt"]
                protocols = [store.artifact(wid, a["id"]) for a in state["artifacts"] if a["kind"] == "protocol_snapshot"]
                self.assertEqual(len(protocols), 1)
                captured = json.loads(protocols[0]["content"])
                self.assertEqual(captured["prompt"], runner.prompt)
                self.assertFalse(captured["independent_semantic_verification"])
                self.assertEqual(captured["requested_model"], "gpt-5.6-terra")
                self.assertTrue(all(r["meta"]["protocol_id"] == protocols[0]["id"] for r in receipts))
                context = runner.model_context(wid, state["rev"], True)
                self.assertNotIn(protocols[0]["id"], json.dumps(context))
                self.assertEqual(len(receipts), 3)
                self.assertTrue(all(json.loads(a["content"])["transport_mode"] == "test_fixture" for a in receipts))
                self.assertEqual(state["decision"] is None, correct_during_final)
                self.assertTrue(any(e["kind"] == "work_framed" for e in state["events"]))
            finally:
                runner.pool.shutdown(wait=True)

    def test_frame_real_tool_and_final_decision_transport(self):
        self.exercise()

    def test_concurrent_correction_retains_tool_but_rejects_stale_decision(self):
        self.exercise(correct_during_final=True)


if __name__ == "__main__":
    unittest.main()
