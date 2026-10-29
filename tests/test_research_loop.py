"""Real workers and durable feedback; synthetic model responses are not quality evidence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema
from evida.contracts import DECISION
from evida.gateway import Gateway
from evida.public_evidence import parse_article
from evida.research_loop import decision_id, validate_loop
from evida.rna_analysis import review_genes
from evida.runner import Runner
from evida.store import Conflict, Store, dump
from test_integrity import proposal
from planner_fixtures import current_frame, current_final

ROOT = Path(__file__).resolve().parents[1]


def hypothesis(aid):
    return {"id": "h1", "statement": "가상 시험: 입력 구조의 물성을 계산할 수 있다.",
            "expected_observation": "유효한 구조이면 계산 값이 반환된다. 효능을 예상하지 않는다.",
            "alternatives": ["입력 구조 오류"], "assessment": "proposed", "rationale": "합성 전송 시험",
            "evidence": [{"source_type": "artifact", "source_id": aid, "relation": "context",
                          "detail": "합성 CSV 입력", "applicability": "이 입력에만 해당"}]}


def seed(store):
    wid = store.create("가상 전송 시험 · 실제 RDKit 계산")["id"]
    aid = store.add_artifact(wid, "합성 CSV", "molecule_csv", b"cid,smiles\nfixture,CCO\n", {}, "text/csv", bump=False)
    p = proposal(1)
    p["research_loop"]["hypotheses"] = [hypothesis(aid)]
    p["research_loop"]["next_checks"] = [{"id": "c1", "question": "입력 구조의 물성을 확인한다", "purpose": "입력 확인",
        "hypothesis_ids": ["h1"], "possible_outcomes": [{"observation": "유효하지 않은 구조", "implication": "입력 확인 필요"}],
        "operation": {"kind": "tool", "name": "compute_properties", "arguments": {"artifact_id": aid}}}]
    jsonschema.validate(p, DECISION)
    validate_loop(p["research_loop"], store.snapshot(wid))
    pid = store.add_artifact(wid, "합성 판단", "decision_proposal", dump(p).encode(), {}, bump=False)
    store.publish_decision(wid, 1, p, pid)
    return wid, aid, pid, p


class ResearchLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.db")
        self.wid, self.aid, self.pid, self.p = seed(self.store)
        self.gateway = Gateway(json.loads((ROOT / "configs/api_policy.json").read_text()), True)
        self.runner = Runner(ROOT, self.store, self.gateway, Path(self.temp.name) / "attempts")

    def tearDown(self):
        self.runner.pool.shutdown(wait=True)
        self.temp.cleanup()

    def claim(self):
        return self.store.claim_check(self.wid, 1, self.pid, "c1")[0]

    def test_real_next_check_automatic_review_and_linked_feedback(self):
        calls = []
        def transport(request):
            calls.append(request)
            current = self.store.snapshot(self.wid)
            if len(calls) == 1:
                from evida.model_context import unpack
                context = unpack(json.loads(request['input'][0]['content']))
                delivered = context['EXPLICIT_SOURCE_VIEWS']['views']
                self.assertEqual(len(delivered), 1)
                actual = next(a for a in current['artifacts'] if a['kind'] == 'rdkit')
                self.assertEqual(delivered[0]['specification']['artifact_id'], actual['id'])
                self.assertEqual(delivered[0]['source_sha256'], actual['sha256'])
                self.assertEqual(delivered[0]['view']['result']['summary']['calculated'], 1)
                self.assertEqual(delivered[0]['view']['result']['rows'][0]['candidate_id'], 'fixture')
                args = {"intent_records": [], "current_question": "計算結果の意味", "task_brief": [], "questions": [],
                        "hypotheses": self.p["research_loop"]["hypotheses"]}
                output = [{"type": "function_call", "name": "frame_work", "arguments": dump(current_frame(self.store, self.wid, args)), "call_id": "frame"}]
            else:
                result = next(a for a in current["artifacts"] if a["kind"] == "rdkit")
                measured = json.loads(self.store.artifact(self.wid, result["id"])["content"])
                self.assertEqual(measured["summary"]["calculated"], 1)
                p = copy.deepcopy(self.p)
                p["based_on_state_rev"] = current["rev"]
                p["research_loop"]["next_checks"] = []
                p["research_loop"]["hypotheses"][0]["assessment"] = "consistent_in_context"
                p["evidence_refs"] = [result["id"]]
                output = [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": dump(current_final(self.store, self.wid, p))}]}]
            return {"id": f"fixture-{len(calls)}", "model": "gpt-5.6-terra", "status": "completed", "usage": {}, "output": output}, {}
        self.gateway.transport = transport
        jid = self.claim()
        with patch.object(self.gateway, "status", return_value={"available": True}):
            self.runner.run_check(jid)
            self.runner.pool.shutdown(wait=True)
        state = self.store.snapshot(self.wid)
        self.assertEqual(len(calls), 2)
        self.assertEqual(state["decision_rev"], 2)
        self.assertEqual([j["status"] for j in state["jobs"]], ["succeeded"] * 3)
        self.assertIsNotNone(state["research_checks"][0]["review_job_id"])
        self.assertEqual(self.runner.start_check(self.wid, 1, self.pid, "c1"), jid)
        self.assertEqual(len(self.store.snapshot(self.wid)["jobs"]), 3)
        context = {"decision_id": self.pid, "check_id": "c1", "hypothesis_ids": ["h1"], "comparison": "different"}
        self.store.command(self.wid, 2, "feedback", {"kind": "observation", "text": "가상 후속 관측: 구조 식별을 정정해야 함",
            "synthetic": True, "research_context": context})
        after = self.store.snapshot(self.wid)
        self.assertEqual(after["review_status"], "needs_review")
        self.assertEqual(after["events"][-1]["body"]["research_context"], context)
        self.assertEqual(after["events"][-1]["body"]["origin"], "synthetic")
        self.assertEqual(json.loads(self.store.artifact(self.wid, self.pid)["content"]), self.p)
        self.assertEqual(len(calls), 2)  # Recording feedback alone does not start model work.

    def test_unpublished_or_cross_workspace_feedback_rejected(self):
        context = {"decision_id": self.pid, "check_id": "c1", "hypothesis_ids": ["h1"], "comparison": "different"}
        other = self.store.create("Other")["id"]
        with self.assertRaises(ValueError):
            self.store.command(other, 1, "bad", {"kind": "observation", "text": "x", "research_context": context})
        raw = self.store.add_artifact(self.wid, "unpublished", "decision_proposal", dump(self.p).encode(), {}, bump=False)
        context["decision_id"] = raw
        with self.assertRaises(ValueError):
            self.store.command(self.wid, 1, "bad", {"kind": "observation", "text": "x", "research_context": context})
        self.assertEqual(self.store.snapshot(self.wid)["rev"], 1)

    def test_csv_pages_reach_later_rows_and_preserve_preamble_and_original_bytes(self):
        raw = ("description,,unit unknown\nsmiles,cid,observation\n" + "".join(f"{'C' * 45},candidate-{i},NA\n" for i in range(200))).encode()
        aid = self.store.add_artifact(self.wid, "synthetic CSV", "molecule_csv", raw, {"header_record": 1}, "text/csv", bump=False)
        view = self.runner.inspect(self.wid, aid, 190, 10)
        self.assertEqual(view["result"]["total_rows"], 200)
        self.assertEqual(view["result"]["rows"][-1]["candidate_id"], "candidate-199")
        self.assertEqual(view["result"]["rows"][-1]["raw_values"][-1], "NA")
        self.assertEqual(view["result"]["preamble_records"], [["description", "", "unit unknown"]])
        self.assertFalse(view["result"]["has_more"])
        self.assertEqual(self.store.artifact(self.wid, aid)["content"], raw)

    def test_edit_before_execution_keeps_check_stale(self):
        jid = self.claim()
        with self.assertRaises(Conflict):
            self.store.enqueue(self.wid, 1, "planner", {})
        self.store.command(self.wid, 1, "changed", {"kind": "correction", "text": "different input"})
        self.runner.run_check(jid)
        state = self.store.snapshot(self.wid)
        self.assertEqual(state["jobs"][0]["status"], "stale")
        self.assertEqual(len(state["jobs"]), 1)

    def test_review_race_does_not_change_successful_tool_to_failed(self):
        jid = self.claim()
        with patch.object(self.gateway, "status", return_value={"available": True}), patch.object(self.runner, "start", side_effect=Conflict("newer context")):
            self.runner.run_check(jid)
        state = self.store.snapshot(self.wid)
        self.assertEqual(state["jobs"][0]["status"], "succeeded")
        self.assertEqual(state["events"][-1]["kind"], "research_check_review_pending")
        self.assertEqual(state["decision_rev"], 1)
        self.assertEqual(state["rev"], 2)

    def test_missing_evidence_and_unknown_hypothesis_not_published(self):
        loop = copy.deepcopy(self.p["research_loop"])
        loop["hypotheses"][0]["evidence"][0]["source_id"] = "not-in-this-workspace"
        with self.assertRaises(ValueError): validate_loop(loop, self.store.snapshot(self.wid))

        loop = copy.deepcopy(self.p["research_loop"])
        loop["next_checks"][0]["hypothesis_ids"] = ["unknown"]
        with self.assertRaises(ValueError): validate_loop(loop, self.store.snapshot(self.wid))

    def test_repeated_view_round_ends_with_a_judgment_and_preserves_delivery_records(self):
        calls = []
        def transport(request):
            calls.append(request)
            if len(calls) == 1:
                name = "frame_work"
                args = {"intent_records": [], "current_question": "synthetic boundary", "task_brief": [], "questions": [], "hypotheses": []}
            else:
                name = "inspect_artifact"
                args = {"artifact_id": self.aid, "offset": 0, "limit": 1, "research_notes": {
                    "findings": [{"text": "synthetic CSV preview", "source_ids": [self.aid]}],
                    "open_questions": ["not scientific validation"], "next_goal": "synthetic repeat"}}
            if request["tool_choice"] == "none":
                output = [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": dump(current_final(self.store, self.wid, proposal(1)))}]}]
            else:
                output = [{"type": "function_call", "name": name, "arguments": dump(current_frame(self.store, self.wid, args) if name == "frame_work" else args), "call_id": f"call-{len(calls)}"}]
            return {"id": f"fixture-{len(calls)}", "model": "gpt-5.6-terra", "status": "completed", "usage": {}, "output": output}, {}
        self.gateway.transport = transport
        jid = self.store.enqueue(self.wid, 1, "planner", {})
        self.runner.run_planner(jid)
        state = self.store.snapshot(self.wid)
        self.assertEqual(len(calls), 16)
        self.assertEqual(state["jobs"][-1]["status"], "succeeded", state["jobs"][-1]["error"])
        readings = [a for a in state["artifacts"] if a["kind"] == "tool_reading"]
        self.assertEqual(len(readings), 14)
        self.assertEqual(readings[-1]["meta"]["arguments"]["artifact_id"], self.aid)
        self.assertTrue(readings[-1]["meta"]["view_only"])
        self.assertEqual(json.loads(self.store.artifact(self.wid, readings[0]["id"])["content"])["artifact_id"], self.aid)
        self.assertEqual(len(self.runner.model_context(self.wid, 1, True)["PRIOR_NOTE_FINDINGS"]), 1)
        restored = self.runner.model_context(self.wid, 1, False, restore_reading=True)["RESTORED_READING"]
        self.assertEqual(restored["reading_id"], readings[-1]["id"])
        self.assertEqual(restored["content"], json.loads(self.store.artifact(self.wid, readings[-1]["id"])["content"]))


    def test_final_response_includes_context_without_a_late_separate_call(self):
        from test_judgment_context import fixture
        from evida.judgment_context import view
        context = fixture(self.aid)
        context['bindings'] = [b for b in context['bindings'] if b['hypothesis_id'] == 'h1']
        context['review_links'] = []
        calls = []
        notes = {'findings':[], 'open_questions':['synthetic integration check'], 'next_goal':'preserve context before final'}
        def transport(request):
            calls.append(request)
            if request['tool_choice'] == 'none':
                p = copy.deepcopy(self.p);p['research_loop']['next_checks'] = []
                output = [{'type':'message','role':'assistant','content':[{'type':'output_text','text':dump(current_final(self.store,self.wid,p,judgment_context=context))}]}]
            else:
                if len(calls) == 1:
                    name = 'frame_work'
                    args = {'intent_records':[], 'current_question':'fixture scientific conditions', 'task_brief':[],
                            'questions':[], 'hypotheses':[hypothesis(self.aid)]}
                elif isinstance(request['tool_choice'],dict):
                    name = request['tool_choice']['name']
                    args = {**context, 'research_notes':notes}
                else:
                    name = 'inspect_artifact'
                    args = {'artifact_id':self.aid,'offset':0,'limit':1,'research_notes':notes}
                output = [{'type':'function_call','name':name,'arguments':dump(current_frame(self.store,self.wid,args) if name=='frame_work' else args),'call_id':f'ctx-{len(calls)}'}]
            return {'id':f'fixture-ctx-{len(calls)}','model':'gpt-5.6-terra','status':'completed','usage':{},'output':output},{}
        self.gateway.transport = transport
        jid = self.store.enqueue(self.wid,1,'planner',{})
        self.runner.run_planner(jid)
        state = self.store.snapshot(self.wid)
        self.assertEqual(len(calls),16)
        self.assertEqual(calls[14]['tool_choice'],'auto')
        self.assertEqual(calls[15]['tool_choice'],'none')
        self.assertEqual(state['jobs'][-1]['status'],'succeeded',state['jobs'][-1]['error'])
        linked = view(self.store,self.wid,state)
        self.assertEqual(linked['context'],context)
        self.assertEqual(linked['published_decision_id'],state['jobs'][-1]['output_id'])
        self.assertEqual(len([a for a in state['artifacts'] if a['kind']=='judgment_context']),1)


    def test_first_final_response_publishes_discovery_context_and_decision_together(self):
        from test_judgment_context import fixture
        from evida.judgment_context import view
        context = fixture(self.aid)
        context['bindings'] = [b for b in context['bindings'] if b['hypothesis_id'] == 'h1']
        context['review_links'] = []
        pool={'disease':{'id':'D'},'rows':[{'target':{'id':'G','approvedSymbol':'Example'}}]}
        aid=self.store.add_artifact(self.wid,'fixture pool','disease_targets',dump(pool).encode(),{},bump=False)
        review={'question':'fixture','new_options':[],'assessments':[{'option_id':'target:D:G','status':'needs_evidence','priority':None,'comparison_group':'fixture','reason':'association is not intervention proof','support_source_ids':[aid],'challenge_source_ids':[],'uncertainties':['function unknown'],'next_action':'read functional evidence'}],'unsearched_scope':['other targets']}
        calls = []
        notes = {'findings':[], 'open_questions':['synthetic integration check'], 'next_goal':'preserve context before final'}
        def transport(request):
            calls.append(request)
            if len(calls)>1:
                p = copy.deepcopy(self.p);p['research_loop']['next_checks'] = []
                output = [{'type':'message','role':'assistant','content':[{'type':'output_text','text':dump(current_final(self.store,self.wid,p,discovery_review=review,judgment_context=context))}]}]
            else:
                if len(calls) == 1:
                    name = 'frame_work'
                    args = {'intent_records':[], 'current_question':'fixture scientific conditions', 'task_brief':[],
                            'questions':[], 'hypotheses':[hypothesis(self.aid)]}
                elif isinstance(request['tool_choice'],dict):
                    name = request['tool_choice']['name']
                    args = {**(review if name=='record_discovery_review' else context), 'research_notes':notes}
                else:
                    name = 'inspect_artifact'
                    args = {'artifact_id':self.aid,'offset':0,'limit':1,'research_notes':notes}
                output = [{'type':'function_call','name':name,'arguments':dump(current_frame(self.store,self.wid,args) if name=='frame_work' else args),'call_id':f'ctx-{len(calls)}'}]
            return {'id':f'fixture-ctx-{len(calls)}','model':'gpt-5.6-terra','status':'completed','usage':{},'output':output},{}
        self.gateway.transport = transport
        jid = self.store.enqueue(self.wid,1,'planner',{})
        self.runner.run_planner(jid)
        state = self.store.snapshot(self.wid)
        self.assertEqual(len(calls),2)
        self.assertEqual(len([a for a in state['artifacts'] if a['kind']=='discovery_review']),1)
        self.assertEqual(state['jobs'][-1]['status'],'succeeded',state['jobs'][-1]['error'])
        linked = view(self.store,self.wid,state)
        self.assertEqual(linked['context'],context)
        self.assertEqual(linked['published_decision_id'],state['jobs'][-1]['output_id'])
        self.assertEqual(len([a for a in state['artifacts'] if a['kind']=='judgment_context']),1)

    def test_explicit_synthesis_does_not_repeat_valid_answers_for_unavailable_tool(self):
        pool={'disease':{'id':'D'},'rows':[{'target':{'id':'G','approvedSymbol':'Example'}}]}
        aid=self.store.add_artifact(self.wid,'unassessed source option','disease_targets',dump(pool).encode(),{},bump=False)
        calls=[]
        def transport(request):
            calls.append(request)
            if len(calls)==1:
                args={'intent_records':[], 'current_question':'Synthesize supplied evidence', 'task_brief':[],
                      'questions':[], 'hypotheses':[hypothesis(self.aid)]}
                output=[{'type':'function_call','name':'frame_work','arguments':dump(current_frame(self.store,self.wid,args)),'call_id':'frame'}]
            else:
                self.assertEqual(request['tool_choice'],'none')
                p=copy.deepcopy(self.p);p['research_loop']['next_checks']=[]
                output=[{'type':'message','role':'assistant','content':[{'type':'output_text','text':dump(current_final(self.store,self.wid,p))}]}]
            return {'id':f'fixture-synthesis-{len(calls)}','model':'gpt-5.6-terra','status':'completed','usage':{},'output':output},{}
        self.gateway.transport=transport
        jid=self.store.enqueue(self.wid,1,'planner',{'synthesis_only':True})
        self.runner.run_planner(jid)
        state=self.store.snapshot(self.wid)
        self.assertEqual(state['jobs'][-1]['status'],'succeeded',state['jobs'][-1]['error'])
        self.assertEqual(len(calls),2)
        self.assertFalse(any(a['kind']=='discovery_review'for a in state['artifacts']))
        self.assertEqual(json.loads(self.store.artifact(self.wid,aid)['content']),pool)


class EvidenceBoundaryTests(unittest.TestCase):
    def test_rna_contrasts_missingness_duplicates_and_input_rows_preserved(self):
        one = {"semantic_type": "reported_observation", "contrast": {"control": ["shared-control"]}, "rows": [
            {"gene_id": "g1", "symbol": "Example", "values": {"padj": None, "log2FoldChange": 0}},
            {"gene_id": "g2", "symbol": "Example", "values": {"padj": 0.02, "log2FoldChange": -1}}]}
        two = {**one, "rows": [{"gene_id": "g1", "symbol": "Example", "values": {"padj": 0, "log2FoldChange": 2}}]}
        inputs = [{"artifact_id": "a", "sha256": "hash1", "result": one}, {"artifact_id": "b", "sha256": "hash2", "result": two}]
        untouched = copy.deepcopy(inputs)
        result = review_genes(inputs, ["Example", "absent", "example"])
        self.assertEqual(inputs, untouched)
        self.assertEqual(result["summary"]["unmatched_requests"], 4)
        self.assertEqual(result["rows"][0]["matching_rows"], 2)
        self.assertIsNone(result["rows"][0]["observation"]["values"]["padj"])
        self.assertEqual(result["rows"][0]["observation"]["values"]["log2FoldChange"], 0)
        self.assertEqual(result["sources"][1]["contrast"]["control"], ["shared-control"])

    def test_article_original_figures_permissions_and_identity(self):
        raw = b'<article><front><article-meta><article-id pub-id-type="pmc">123</article-id><title-group><article-title>Fixture</article-title></title-group><permissions>License terms</permissions><abstract><p>Abstract</p></abstract></article-meta></front><body><sec><title>Results</title><p>Text <inline-formula>Formula</inline-formula></p><table-wrap id="table1"><caption>Meaning requires table</caption><table><tr><td>Value</td></tr></table></table-wrap><fig id="fig1"><caption>Not an image interpretation</caption></fig></sec></body></article>'
        result = parse_article(raw, "PMC123", {"url": "public"})
        self.assertEqual(result["original_xml"].encode(), raw)
        self.assertEqual(result["permissions"], ["License terms"])
        self.assertEqual(result["summary"]["original_review_blocks"], 3)
        self.assertTrue(result["rows"][2]["source_url"].endswith("#table1"))
        with self.assertRaises(ValueError): parse_article(raw, "PMC999", {})


if __name__ == "__main__": unittest.main()
