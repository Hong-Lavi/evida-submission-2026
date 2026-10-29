import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from evida.contracts import model_functions
from evida.runner import Runner
from evida.store import Store, dump


class PlannerResume(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.temp.name)/'db.sqlite3')
        self.wid=self.store.create('resume fixture')['id']
        self.runner=object.__new__(Runner);self.runner.store=self.store;self.runner.prompt='fixture prompt'
        self.runner.gateway=SimpleNamespace(model='gpt-5.6-sol',effort='max')
        self.request={'instructions':self.runner.prompt,'tools':model_functions(),
                      'input':[{'role':'user','content':'preserved fixture input'}]}
        self.source=self.store.enqueue(self.wid,1,'planner',{})
        self.store.start_job(self.source);self.store.finish_job(self.source,'failed',error='fixture input length')
        with self.store.connect(True) as db:self.store.event(db,self.wid,'work_framed',{'based_rev':1})
        self.digest=hashlib.sha256(dump(self.request).encode()).hexdigest()
        self.store.add_artifact(self.wid,'failed request receipt','model_receipt',dump({
            'request_sha256':self.digest,'requested_model':'gpt-5.6-sol','requested_effort':'max'}).encode(),
            {'job_id':self.source},bump=False)
        self.jid=self.store.enqueue(self.wid,1,'planner',{'resume_from_job':self.source,'resume_request_sha256':self.digest})
        self.job=next(j for j in self.store.snapshot(self.wid)['jobs'] if j['id']==self.jid)

    def tearDown(self):self.temp.cleanup()

    def test_exact_failed_input_resumes_without_another_frame(self):
        self.assertEqual(self.runner.planner_resume_input(self.job,{'request':self.request}),self.request['input'])
        self.assertEqual(next(j for j in self.store.snapshot(self.wid)['jobs'] if j['id']==self.source)['status'],'failed')

    def test_new_researcher_input_prevents_stale_continuation(self):
        self.store.command(self.wid,1,'new-input',{'kind':'message','text':'New fixture constraint','synthetic':True})
        with self.assertRaisesRegex(ValueError,'연구 조건이 바뀌'):
            self.runner.planner_resume_input(self.job,{'request':self.request})

    def test_modified_request_and_changed_provider_are_rejected(self):
        bad=json.loads(json.dumps(self.request));bad['input'][0]['content']='different'
        with self.assertRaisesRegex(ValueError,'해시가 다릅니다'):
            self.runner.planner_resume_input(self.job,{'request':bad})
        self.runner.gateway.model='different-fixture-model'
        with self.assertRaisesRegex(ValueError,'동일 모델'):
            self.runner.planner_resume_input(self.job,{'request':self.request})


if __name__ == '__main__':unittest.main()
