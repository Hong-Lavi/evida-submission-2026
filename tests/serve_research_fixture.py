"""Opt-in browser fixture: synthetic model transport, actual RDKit, isolated database."""
import copy
import argparse
import json
import sys
from pathlib import Path
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evida.server import Application, handler_for
from evida.store import dump
from test_research_loop import seed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--scoped', action='store_true')
    options = parser.parse_args()
    with TemporaryDirectory(prefix="evida-browser-fixture-") as temp:
        app = Application(ROOT, Path(temp) / "state.db")
        app.runner.attempts_root = Path(temp) / "attempts"
        wid, aid, pid, initial = seed(app.store)
        if options.scoped:
            from test_assessment_scope import scoped
            initial = scoped(initial)
            initial['research_loop']['hypotheses'][0]['assessment'] = 'inconclusive'
            initial['research_loop']['next_checks'][0].pop('scope_targets')
            pid = app.store.add_artifact(wid, 'Synthetic scoped fixture', 'decision_proposal', dump(initial).encode(), {}, bump=False)
            app.store.publish_decision(wid, 1, initial, pid)
        calls = []
        def transport(request):
            calls.append(request)
            state = app.store.snapshot(wid)
            if len(calls) % 2:
                args = {"intent_records": [], "current_question": "가상 전송 시험", "task_brief": [], "questions": [],
                        "hypotheses": initial["research_loop"]["hypotheses"]}
                output = [{"type": "function_call", "name": "frame_work", "arguments": dump(args), "call_id": f"frame-{len(calls)}"}]
            else:
                p = copy.deepcopy(initial)
                p["based_on_state_rev"] = state["rev"]
                p["research_loop"]["next_checks"] = [{"id": "observe", "question": "후속 관측을 원래 예상과 연결하기", "purpose": "가상 전송 확인",
                    "hypothesis_ids": ["h1"], "possible_outcomes": [], "operation": {"kind": "external_observation", "request": "가상 관측임을 표시하고 기록하세요."}}]
                feedback = [e for e in state["events"] if e["kind"] == "observation"]
                p["recommendation"] = "가상 전송 확인: 새 관측을 검토했습니다." if feedback else "가상 전송 확인: 실제 물성 계산이 완료되었습니다."
                p["research_loop"]["hypotheses"][0]["assessment"] = "challenged" if feedback else "consistent_in_context"
                if options.scoped:
                    p['research_loop']['hypotheses'][0]['assessment'] = 'inconclusive'
                    p['research_loop']['next_checks'][0]['scope_targets'] = [{'hypothesis_id': 'h1', 'part_ids': ['stage']}]
                output = [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": dump(p)}]}]
            return {"id": f"fixture-{len(calls)}", "model": "gpt-5.6-terra", "status": "completed", "usage": {}, "output": output}, {}
        app.gateway.enabled = True
        app.gateway.transport = transport
        app.gateway.status = lambda: {"available": True, "enabled": True, "credential_configured": False,
            "requested_model": "SYNTHETIC TRANSPORT", "requested_effort": "fixture", "live_verified": False}
        server = ThreadingHTTPServer(("127.0.0.1", options.port), handler_for(app))
        print(dump({"port": options.port, "workspace": wid, "mode": "test_fixture_no_api_key"}), flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally:
            server.server_close()
            app.runner.pool.shutdown(wait=True)
            app.lock.close()


if __name__ == "__main__": main()
