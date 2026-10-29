"""Synthetic Store only: original budget evidence governs exact continuation."""
import unittest
import test_planner_resume as legacy
from evida.store import dump

class RecordedResumePolicy(unittest.TestCase):
    setUp=legacy.PlannerResume.setUp
    tearDown=legacy.PlannerResume.tearDown

    def protocol(self,budget,job=None,mode=None,omit_budget=False):
        value={}if omit_budget else {'response_budget':budget}
        if mode is not None:value['response_limit_mode']=mode
        return self.store.add_artifact(self.wid,'Synthetic recorded policy','protocol_snapshot',dump(value).encode(),
            {'based_rev':1,'job_id':job or self.source},bump=False)

    def rounds(self,n,job=None):
        for i in range(n):
            self.store.add_artifact(self.wid,f'Synthetic returned receipt {i}','model_receipt',dump({
                'status':'RETURNED','response_status':'completed'}).encode(),{'job_id':job or self.source},bump=False)

    def resume(self,count=None):
        value={'request':self.request}
        if count is not None:value['completed_rounds']=count
        self.assertEqual(self.runner.planner_resume_input(self.job,value),self.request['input'])
        return value

    def reject(self,count=None):
        with self.assertRaisesRegex(ValueError,'응답 예산'):
            self.resume(count)

    def test_original_unbounded_crosses_16(self):
        self.runner._response_limit_setting=None;self.protocol(None,mode='unbounded');self.rounds(20)
        self.assertEqual(self.resume(20)['completed_rounds'],20)

    def test_original_unbounded_resumes_at_96(self):
        self.runner._response_limit_setting=None;self.protocol(None,mode='unbounded');self.rounds(96)
        self.assertEqual(self.resume(96)['completed_rounds'],96)

    def test_unbounded_does_not_require_a_completed_response(self):
        self.runner._response_limit_setting=None;self.protocol(None,mode='unbounded');self.resume(0)

    def test_finite16_boundary_preserved(self):
        self.protocol(16,mode='finite');self.rounds(15);self.resume(15);self.rounds(1);self.reject(16)

    def test_smaller_original_finite_budget_preserved(self):
        self.runner._response_limit_setting=4;self.protocol(4,mode='finite');self.rounds(3);self.resume(3)
        self.rounds(1);self.reject(4)

    def test_recorded_larger_finite_budget_remains_finite(self):
        self.runner._response_limit_setting=32;self.protocol(32,mode='finite');self.rounds(20);self.resume(20)
        self.rounds(12);self.reject(32)

    def test_current_none_cannot_expand_original_finite(self):
        self.runner._response_limit_setting=None;self.protocol(16,mode='finite');self.reject(0)

    def test_current_larger_finite_cannot_expand_original(self):
        self.runner._response_limit_setting=32;self.protocol(16,mode='finite');self.reject(0)

    def test_current_finite_cannot_replace_original_none(self):
        self.protocol(None,mode='unbounded');self.reject(0)

    def test_missing_protocol_legacy16_is_not_unbounded_authorization(self):
        self.runner._response_limit_setting=None;self.reject(0)

    def test_missing_protocol_legacy_finite16_still_resumes(self):
        self.rounds(15);self.resume(15);self.rounds(1);self.reject(16)

    def test_mode_without_explicit_null_budget_is_not_proof(self):
        self.runner._response_limit_setting=None;self.protocol(None,mode='unbounded',omit_budget=True);self.reject(0)

    def test_null_without_unbounded_mode_is_not_proof(self):
        self.runner._response_limit_setting=None;self.protocol(None);self.reject(0)

    def test_conflicting_protocols_rejected(self):
        self.runner._response_limit_setting=None;self.protocol(None,mode='unbounded');self.protocol(16,mode='finite');self.reject(0)

    def test_malformed_boolean_budget_rejected(self):
        self.protocol(True,mode='finite');self.reject(0)

    def test_resume_count_must_still_match_original_receipts(self):
        self.runner._response_limit_setting=None;self.protocol(None,mode='unbounded');self.rounds(20);self.reject(19)

    def chain(self,budget):
        child=self.jid  # Existing queued resume is already bound to the original source.
        self.store.start_job(child);self.store.finish_job(child,'failed',error='Synthetic interruption')
        self.protocol(budget,job=child,mode='unbounded'if budget is None else'finite')
        self.store.add_artifact(self.wid,'Synthetic failed child request','model_receipt',dump({
            'request_sha256':self.digest,'requested_model':self.runner.gateway.model,
            'requested_effort':self.runner.gateway.effort}).encode(),{'job_id':child},bump=False)
        self.jid=self.store.enqueue(self.wid,1,'planner',{'resume_from_job':child,'resume_request_sha256':self.digest})
        self.job=next(j for j in self.store.snapshot(self.wid)['jobs']if j['id']==self.jid)

    def test_resume_chain_cannot_launder_finite_into_none(self):
        self.runner._response_limit_setting=None;self.protocol(16,mode='finite');self.chain(None);self.reject(0)

    def test_consistent_unbounded_chain_preserves_count(self):
        self.runner._response_limit_setting=None;self.protocol(None,mode='unbounded');self.rounds(20);self.chain(None);self.resume(20)

if __name__=='__main__':unittest.main()
