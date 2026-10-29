"""Normal Runner with deterministic synthetic responses; no provider/network calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from evida.gateway import Gateway
from evida.runner import Runner
from evida.store import Store, dump
from evida.private_supervision import ActionMonitor
from planner_fixtures import current_frame
from test_current_call_tools import current_call

ROOT=Path(__file__).resolve().parents[1]
class UnboundedSupervision(unittest.TestCase):
    def test_repeated_query_is_detected_despite_new_notes_and_argument_order(self):
        monitor=ActionMonitor()
        for i in range(3):
            arguments={'query':'same source query','limit':3,'research_notes':{'next_goal':str(i)}}
            if i%2:arguments=dict(reversed(list(arguments.items())))
            result=monitor.observe({'output':[{'type':'function_call','name':'search_literature','arguments':dump(arguments)}]})
        self.assertTrue(result['supervisor_attention'])
        self.assertEqual(result['identical_action_streak'],3)
        self.assertFalse(result['automatic_stop'])

    def test_normal_runner_crosses_old_limit_and_preserves_goal_revision(self):
        self.run_synthetic()

    def test_invalid_final_can_replan_without_a_correction_count_stop(self):
        self.run_synthetic(invalid_final=True)

    def test_invalid_transport_can_replan_without_a_correction_count_stop(self):
        self.run_synthetic(invalid_transport=True)

    def run_synthetic(self, invalid_final=False, invalid_transport=False):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'fixture.sqlite3');wid=store.create('Synthetic unbounded controller fixture')['id']
            source=store.add_artifact(wid,'Synthetic source','repository_document',dump({'rows':[{'observation':'fixture only'}]}).encode(),{},bump=False)
            requests=[]
            def transport(request):
                requests.append(request);number=len(requests)
                if number==1:
                    args=current_frame(store,wid,{'intent_records':[],'current_question':'Synthetic question','task_brief':[],'questions':[],'hypotheses':[]});name='frame_work'
                else:
                    name='inspect_artifact';args={'artifact_id':source,'offset':0,'limit':1,'research_notes':{'findings':[],'open_questions':['Synthetic observation'],'next_goal':'Read saved fixture'}}
                if 2<=number<=5 and invalid_final:
                    return {'id':f'fixture-{number}','model':gateway.model,'status':'completed','usage':{},'output':[{'type':'message','content':[{'type':'output_text','text':'{}'}]}]},{}
                if 2<=number<=5 and invalid_transport:
                    return {'id':f'fixture-{number}','model':gateway.model,'status':'completed','usage':{},'schema_rejection':{'errors':['synthetic invalid field'],'may_execute':False},'output':[{'type':'function_call','name':name,'arguments':dump(args),'call_id':f'c{number}'}]},{}
                if number==21:
                    store.command(wid,1,'synthetic-goal-revision',{'kind':'message','text':'Synthetic updated goal','review_requested':False})
                return {'id':f'fixture-{number}','model':gateway.model,'status':'completed','usage':{},'output':[{'type':'function_call','name':name,'arguments':dump(args),'call_id':f'c{number}'}]},{}
            policy=json.loads((ROOT/'configs/api_policy.json').read_text());policy['min_request_interval_seconds']=0;policy['secret_env']='EVIDA_UNUSED_SYNTHETIC_CREDENTIAL'
            gateway=Gateway(policy,True,model='gpt-6-sol',effort='medium',transport=transport)
            runner=object.__new__(Runner);runner.root=ROOT;runner.store=store;runner.gateway=gateway;runner.prompt=(ROOT/'configs/planner.md').read_text();runner.context_recent_views=2;runner._response_limit_setting=None
            jid=store.enqueue(wid,1,'planner',{})
            runner.run_planner(jid)
            state=store.snapshot(wid);job=next(j for j in state['jobs']if j['id']==jid)
            self.assertEqual(job['status'],'stale',job.get('error'))
            self.assertEqual(len(requests),21)
            for request in requests[1:]:
                self.assertEqual(request['tool_choice'],'auto')
                self.assertIsNone(current_call(request)['maximum_responses_remaining_including_current'])
                self.assertFalse(current_call(request)['unbounded_supervision']['count_forced_synthesis'])
            self.assertEqual(sum(a['kind']=='model_receipt'for a in state['artifacts']),21)
            self.assertEqual(sum(a['kind']=='supervision_progress'for a in state['artifacts']),21)
            self.assertEqual(sum(a['kind']=='tool_reading'for a in state['artifacts']),15 if invalid_final or invalid_transport else 19)
            self.assertIsNone(state['decision'])
            self.assertEqual(state['rev'],2)
            protocol=next(a for a in state['artifacts']if a['kind']=='protocol_snapshot')
            self.assertIsNone(json.loads(store.artifact(wid,protocol['id'])['content'])['response_budget'])
            self.assertTrue(any('ORCHESTRATION_PROGRESS' in str(r['input'])for r in requests))

    def test_legacy_default_observes_launcher_setting_at_execution(self):
        runner=object.__new__(Runner)
        with patch('evida.runner.RESEARCH_ROUNDS',32):self.assertEqual(runner.response_limit,32)
        runner._response_limit_setting=None
        with patch('evida.runner.RESEARCH_ROUNDS',32):self.assertIsNone(runner.response_limit)
