"""A mocked transport must receive all actual locator diagnostics, no model call."""
import json
from pathlib import Path
import tempfile
import unittest

from evida.gateway import Gateway
from evida.model_context import unpack
from evida.runner import Runner
from evida.store import Store
from test_integrity import proposal
from planner_fixtures import current_frame, current_final

ROOT=Path(__file__).resolve().parents[1]


class ExposureErrorDeliveryTests(unittest.TestCase):
    def test_invalid_source_diagnostics_survive_real_planner_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'fixture.db');wid=store.create('Synthetic locator error fixture')['id']
            text='Synthetic only: 2 uM, 5 ug/mL, molecular weight 500 g/mol.'
            aid=store.add_artifact(wid,'Synthetic source','research_evidence',json.dumps({'rows':[{'text':text}]}).encode(),{},bump=False)
            binding={'artifact_id':aid,'path':['result','rows',0,'text'],'quote':text}
            args={'source_artifact_ids':[aid],'context':'synthetic fixture',
                'assay_benchmark':{'value':2,'unit':'uM','metric':'fixture','context':'fixture','source':binding},
                'exposures':[{'id':'peak','label':'fixture','value':5,'unit':'ug/mL','statistic':'Cmax','interval_hours':None,'context':'fixture','source':binding}],
                'mass_bases':[{'id':'form','label':'fixture','molecular_weight_g_mol':500,'status':'sensitivity_only','source':{**binding,'path':['content','rows',0,'text']}}],
                'research_notes':{'findings':[],'open_questions':[],'next_goal':'Fix exact recorded locator; no automatic science conclusion.'}}
            requests=[]
            def transport(request):
                requests.append(request)
                if len(requests)==1:
                    frame={'intent_records':[],'current_question':'Synthetic diagnostic transport','task_brief':[],'questions':[],'hypotheses':[]}
                    frame=current_frame(store,wid,frame)
                    output=[{'type':'function_call','name':'frame_work','arguments':json.dumps(frame),'call_id':'frame','id':'fixture-frame'}]
                elif len(requests)==2:
                    output=[{'type':'function_call','name':'compare_exposure_requirements','arguments':json.dumps(args),'call_id':'compare','id':'fixture-compare'}]
                else:
                    response=next(i for i in request['input'] if i.get('type')=='function_call_output' and i.get('call_id')=='compare')
                    value=unpack(json.loads(response['output']))
                    self.assertEqual(value['status'],'invalid_input')
                    self.assertEqual(len(value['source_binding_errors']),2)
                    self.assertTrue(all(e['artifact_id']==aid for e in value['source_binding_errors']))
                    self.assertIn('keys=["rows"]',value['source_binding_errors'][1]['message'])
                    output=[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(current_final(store,wid,proposal(1)))}]}]
                return {'id':'synthetic-'+str(len(requests)),'model':'gpt-5.6-terra','status':'completed','usage':{'input_tokens':0,'output_tokens':0},'output':output},{}
            gateway=Gateway(json.loads((ROOT/'configs/api_policy.json').read_text()),True,transport=transport)
            runner=Runner(ROOT,store,gateway,Path(temp)/'attempts')
            try:
                jid=store.enqueue(wid,1,'planner',{});runner.run_planner(jid)
                state=store.snapshot(wid);job=next(j for j in state['jobs'] if j['id']==jid)
                self.assertEqual(job['status'],'succeeded',job.get('error'))
                self.assertEqual(len(requests),3)
                self.assertEqual([j for j in state['jobs'] if j['kind']=='exposure_requirements'],[])
                saved=[a for a in state['artifacts'] if a['kind']=='tool_reading' and a['meta'].get('function')=='compare_exposure_requirements']
                self.assertEqual(len(saved),1)
                self.assertEqual(len(json.loads(store.artifact(wid,saved[0]['id'])['content'])['source_binding_errors']),2)
            finally:
                runner.pool.shutdown(wait=True);runner.explanation_pool.shutdown(wait=True)
