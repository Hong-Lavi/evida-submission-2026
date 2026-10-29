from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from evida.interaction import claim_followthrough, enqueue_explanation, request_followthrough, run_explanation, saved_context
from evida.runner import Runner
from evida.store import Conflict, Store, dump


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'state.sqlite3')
        self.wid = self.store.create('Interaction fixture')['id']
        self.runner = Runner.__new__(Runner)
        self.runner.store = self.store
        self.source = self.store.add_artifact(self.wid,'Original fixture','literature',dump({'rows':[{'condition':'A','value':0}]}).encode(),{},bump=False)
        self.notes = self.store.add_artifact(self.wid,'Working conclusion','research_notes',dump({'findings':[{'text':'Fixture reading is pending','source_ids':[self.source]}],'next_goal':'Read original','open_questions':[]}).encode(),{'based_rev':1},bump=False)

    def tearDown(self): self.tmp.cleanup()

    def gateway(self, outputs):
        history = []
        def request(value):
            history.append(value)
            return {'output':outputs.pop(0)}, {'status':'fixture','actual_model':'synthetic_no_model_call'}
        self.runner.gateway = SimpleNamespace(request=request)
        return history

    def final(self, evidence=None, suggested=''):
        value = {'answer':'Fixture explanation, not a scientific claim','evidence_refs':evidence or [],
                 'event_refs':[],'not_established':['Understanding not tested'],'suggested_condition_change':suggested}
        return [{'type':'message','content':[{'type':'output_text','text':dump(value)}]}]

    def test_explanation_dedupe_does_not_change_revision_or_active_planner(self):
        planner = self.store.enqueue(self.wid,1,'planner',{})
        self.store.start_job(planner)
        first, created = enqueue_explanation(self.store,self.wid,1,'ex1','Why this direction?')
        again, repeated = enqueue_explanation(self.store,self.wid,1,'ex1','Why this direction?')
        self.assertTrue(created); self.assertFalse(repeated); self.assertEqual(first,again)
        with self.assertRaises(Conflict): enqueue_explanation(self.store,self.wid,1,'ex1','Different')
        with self.assertRaises(Conflict): enqueue_explanation(self.store,self.wid,1,'ex2','More')
        self.gateway([self.final([self.notes])])
        run_explanation(self.runner,first['job_id'])
        state=self.store.snapshot(self.wid)
        self.assertEqual(state['rev'],1);self.assertIsNone(state['decision_rev'])
        self.assertEqual(next(j['status'] for j in state['jobs'] if j['id']==planner),'running')
        self.assertEqual(enqueue_explanation(self.store,self.wid,1,'ex1','Why this direction?')[0],first)

    def test_exact_original_read_and_later_condition_are_separate(self):
        request, _ = enqueue_explanation(self.store,self.wid,1,'ex1','Explain condition A')
        self.store.command(self.wid,1,'edit1',{'kind':'correction','text':'Use condition B'})
        outputs = [[{'type':'function_call','name':'inspect_artifact','call_id':'read1',
                    'arguments':dump({'artifact_id':self.source,'offset':0,'limit':4})}],self.final([self.source])]
        history=self.gateway(outputs)
        run_explanation(self.runner,request['job_id'])
        state=self.store.snapshot(self.wid);job=next(j for j in state['jobs'] if j['id']==request['job_id'])
        answer=json.loads(self.store.artifact(self.wid,job['output_id'])['content'])
        self.assertEqual(state['rev'],2);self.assertEqual(answer['based_rev'],1)
        self.assertFalse(answer['condition_applied']); self.assertEqual(len(history),2)
        self.assertEqual(json.loads(history[1]['input'][-1]['output'])['result']['rows'],[{'condition':'A','value':0}])

    def test_source_added_after_snapshot_cannot_be_claimed_read(self):
        request, _ = enqueue_explanation(self.store,self.wid,1,'ex1','Why?')
        other=self.store.add_artifact(self.wid,'Later','literature',b'{}',{},bump=False)
        self.gateway([self.final([other])]);run_explanation(self.runner,request['job_id'])
        state=self.store.snapshot(self.wid);job=next(j for j in state['jobs'] if j['id']==request['job_id'])
        self.assertEqual(job['status'],'failed');self.assertEqual(state['rev'],1)
        self.assertTrue(any(a['kind']=='explanation_model_output' for a in state['artifacts']))

    def test_suggested_change_is_not_applied(self):
        request, _=enqueue_explanation(self.store,self.wid,1,'ex1','Would B change things?')
        self.gateway([self.final(suggested='Consider B')]);run_explanation(self.runner,request['job_id'])
        state=self.store.snapshot(self.wid)
        self.assertEqual(state['rev'],1)
        self.assertFalse(any(e['kind']=='correction' for e in state['events']))
        self.assertFalse(state['followthrough_requests'])

    def test_saved_note_citations_are_indirect_and_catalog_alone_is_not_support(self):
        # Explain an already recorded finding without compelling a full reread.
        request,_=enqueue_explanation(self.store,self.wid,1,'indirect','Explain the saved note')
        self.gateway([self.final([self.notes,self.source])]);run_explanation(self.runner,request['job_id'])
        job=next(j for j in self.store.snapshot(self.wid)['jobs'] if j['id']==request['job_id'])
        self.assertEqual(job['status'],'succeeded')
        answer=json.loads(self.store.artifact(self.wid,job['output_id'])['content'])
        detail=next(d for d in answer['citation_provenance'] if d['artifact_id']==self.source)
        self.assertEqual(detail['delivery'],'cited_in_saved_snapshot_not_reread')
        self.assertIn(self.notes,detail['snapshot_parents'])
        self.assertFalse(detail['scientific_claim_verified'])
        unrelated=self.store.add_artifact(self.wid,'Listed only','literature',b'{}',{},bump=False)
        request,_=enqueue_explanation(self.store,self.wid,1,'catalog','Explain unrelated source')
        self.gateway([self.final([unrelated])]);run_explanation(self.runner,request['job_id'])
        job=next(j for j in self.store.snapshot(self.wid)['jobs'] if j['id']==request['job_id'])
        self.assertEqual(job['status'],'failed')

    def test_working_notes_are_actual_artifacts_and_not_an_empty_event_query(self):
        context=saved_context(self.store,self.wid)
        self.assertEqual(context['CURRENT_RESEARCH_NOTES'][0]['artifact_id'],self.notes)
        self.assertEqual(context['CURRENT_RESEARCH_NOTES'][0]['body']['next_goal'],'Read original')

    def test_changed_condition_request_waits_and_enqueues_only_once(self):
        parent=self.store.enqueue(self.wid,1,'planner',{});self.store.start_job(parent)
        body={'kind':'correction','text':'Use B','review_requested':True}
        receipt=self.store.command(self.wid,1,'change1',body)
        self.assertIn('review_request_id',receipt);self.assertIsNone(claim_followthrough(self.store,self.wid))
        self.assertEqual(self.store.command(self.wid,1,'change1',body),receipt)
        self.store.finish_job(parent,'stale')
        with ThreadPoolExecutor(max_workers=4) as pool:
            claimed=list(pool.map(lambda _:claim_followthrough(self.store,self.wid),range(4)))
        self.assertEqual(len([j for j in claimed if j]),1)
        state=self.store.snapshot(self.wid)
        self.assertEqual(len(state['jobs']),2)
        self.assertEqual(state['followthrough_requests'][0]['job_id'],next(j for j in claimed if j))
        self.assertEqual(self.store.artifact(self.wid,self.source)['content'],dump({'rows':[{'condition':'A','value':0}]}).encode())

    def test_multiple_reviewed_corrections_merge_into_latest_review_not_duplicate_calls(self):
        parent=self.store.enqueue(self.wid,1,'planner',{});self.store.start_job(parent)
        a=self.store.command(self.wid,1,'c1',{'kind':'correction','text':'B','review_requested':True})
        b=self.store.command(self.wid,2,'c2',{'kind':'correction','text':'C','review_requested':True})
        self.store.finish_job(parent,'stale');jid=claim_followthrough(self.store,self.wid)
        state=self.store.snapshot(self.wid)
        self.assertEqual([r['status'] for r in state['followthrough_requests']],['superseded','dispatched'])
        self.assertEqual(state['followthrough_requests'][0]['superseded_by'],b['review_request_id'])
        self.assertEqual(next(j['based_rev'] for j in state['jobs'] if j['id']==jid),3)
        self.assertEqual([e['body']['text'] for e in state['events'] if e['kind']=='correction'],['B','C'])

    def test_later_record_only_edit_needs_explicit_new_review_choice(self):
        self.store.command(self.wid,1,'c1',{'kind':'correction','text':'B','review_requested':True})
        self.store.command(self.wid,2,'c2',{'kind':'correction','text':'C, record only'})
        self.assertIsNone(claim_followthrough(self.store,self.wid))
        state=self.store.snapshot(self.wid)
        self.assertEqual(state['followthrough_requests'][0]['status'],'needs_confirmation')
        request_followthrough(self.store,self.wid,3,'review3')
        self.assertIsNotNone(claim_followthrough(self.store,self.wid))

    def test_completed_science_result_can_be_included_at_new_revision(self):
        parent=self.store.enqueue(self.wid,1,'planner',{});self.store.start_job(parent)
        self.store.command(self.wid,1,'c1',{'kind':'correction','text':'B','review_requested':True})
        self.store.add_artifact(self.wid,'Completed tool','rdkit',b'{}',{'attempt_id':'fixture'},bump=True)
        self.store.finish_job(parent,'stale')
        jid=claim_followthrough(self.store,self.wid)
        self.assertEqual(next(j['based_rev'] for j in self.store.snapshot(self.wid)['jobs'] if j['id']==jid),3)

    def test_parent_quota_failure_or_restart_never_automatically_retries(self):
        parent=self.store.enqueue(self.wid,1,'planner',{});self.store.start_job(parent)
        self.store.command(self.wid,1,'c1',{'kind':'correction','text':'B','review_requested':True})
        self.store.finish_job(parent,'quota_or_rate_limit')
        self.assertIsNone(claim_followthrough(self.store,self.wid))
        self.assertEqual(len(self.store.snapshot(self.wid)['jobs']),1)
        request_followthrough(self.store,self.wid,2,'manual-next')
        self.store.recover()
        self.assertIsNone(claim_followthrough(self.store,self.wid))
        self.assertFalse(any(r['status']=='pending' for r in self.store.snapshot(self.wid)['followthrough_requests']))


if __name__ == '__main__': unittest.main()
