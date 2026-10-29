"""The real worker must deliver usable result status and safe cache reuse."""
import json
from pathlib import Path
import tempfile
import unittest
from evida.gateway import Gateway
from evida.runner import Runner
from evida.store import Store

ROOT=Path(__file__).resolve().parents[1]


class KineticWorkerTests(unittest.TestCase):
    def test_calculated_result_is_successful_and_reused_without_a_second_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'fixture.db')
            wid=store.create('Synthetic kinetics worker fixture')['id']
            text='Synthetic fixture: reference Km 86 and Vmax 61; comparator Km 69 and Vmax 56.'
            aid=store.add_artifact(wid,'Synthetic source','research_evidence',json.dumps({'text':text}).encode(),{},bump=False)
            source={'artifact_id':aid,'path':['text'],'quote':text}
            def model(name,km,vmax):
                return {'id':name,'label':name,'conditions':'Controlled arithmetic fixture',
                    'km':{'value':km,'unit':'uM','source':source},
                    'vmax':{'value':vmax,'unit':'nmol/min/mg','source':source}}
            args={'source_artifact_ids':[aid],'reference':model('reference',86,61),
                'comparators':[model('A',69,56)],'substrate_unit':'uM','substrate_values':[1000],
                'comparison_assumptions':['Compatible synthetic parameters; not measurements.']}
            gateway=Gateway(json.loads((ROOT/'configs/api_policy.json').read_text()),False)
            runner=Runner(ROOT,store,gateway,Path(temp)/'attempts')
            try:
                runner.validate_tool(wid,'kinetic_conditions',args)
                key=runner.cache_key(wid,'kinetic_conditions',args)
                first=store.enqueue(wid,1,'kinetic_conditions',args,cache_key=key)
                result_id=runner.run_tool_job(first,False)
                result=json.loads(store.artifact(wid,result_id)['content'])
                self.assertEqual(result['status'],'succeeded')
                self.assertEqual(result['semantic_type'],'conditional_parameter_calculation')
                self.assertAlmostEqual(result['rows'][0]['amount_multiplier_for_equal_rate'],65209/60816)
                second=store.enqueue(wid,1,'kinetic_conditions',args,cache_key=key)
                reused=runner.run_tool_job(second,False)
                self.assertEqual(reused,result_id)
                jobs={j['id']:j for j in store.snapshot(wid)['jobs']}
                self.assertEqual(jobs[first]['status'],'succeeded')
                self.assertEqual(jobs[second]['status'],'reused')
                self.assertEqual(len(list((Path(temp)/'attempts').glob('*/request.json'))),1)
            finally:
                runner.pool.shutdown(wait=True);runner.explanation_pool.shutdown(wait=True)
