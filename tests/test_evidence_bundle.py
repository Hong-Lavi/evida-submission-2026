import hashlib
from pathlib import Path
import tempfile
import unittest

import jsonschema

from evida.evidence_bundle import execute
from evida.contracts import model_functions, FUNCTION_BY_NAME
from evida.runner import Runner
from evida.store import Store, dump


class EvidenceBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db')
        self.wid=self.store.create('Read bundle fixture')['id']
        self.raw=dump({'rows':[{'row_id':'a','value':0,'unit':'nM'},
                             {'row_id':'a','value':None,'unit':'uM'}],
                       'limits':['Not independent conditions']}).encode()
        self.aid=self.store.add_artifact(self.wid,'Fixture','literature',self.raw,{},bump=False)
        self.runner=Runner.__new__(Runner);self.runner.store=self.store

    def tearDown(self):self.tmp.cleanup()

    def request(self,aid=None,purpose='Compare original values'):
        return {'name':'inspect_artifact','arguments':{'artifact_id':aid or self.aid,'offset':0,'limit':2},'purpose':purpose}

    def test_exact_values_and_failure_do_not_erase_successful_sibling(self):
        result=execute(self.runner,self.wid,{'reads':[self.request(),self.request('absent')]})
        self.assertEqual(result['status'],'partial')
        good,bad=result['rows'];self.assertEqual(good['status'],'succeeded');self.assertEqual(bad['status'],'input_error')
        self.assertEqual(good['view']['result']['rows'],[{'row_id':'a','value':0,'unit':'nM'},{'row_id':'a','value':None,'unit':'uM'}])
        self.assertEqual(good['source_sha256'],hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(self.store.snapshot(self.wid)['rev'],1);self.assertEqual(self.store.snapshot(self.wid)['jobs'],[])

    def test_same_source_range_has_one_execution_but_distinct_purposes(self):
        result=execute(self.runner,self.wid,{'reads':[self.request(),self.request(purpose='Recheck unit difference')]})
        self.assertEqual(result['summary']['unique_reads_executed'],1)
        self.assertEqual(result['rows'][1]['status'],'same_immutable_view')
        self.assertEqual(result['rows'][1]['same_view_as_read'],0)
        self.assertNotIn('view',result['rows'][1])
        self.assertEqual(result['rows'][1]['purpose'],'Recheck unit difference')

    def test_not_a_general_tool_executor_or_cross_workspace_reader(self):
        with self.assertRaises(jsonschema.ValidationError):
            execute(self.runner,self.wid,{'reads':[{'name':'compute_properties','arguments':{'artifact_id':self.aid},'purpose':'Not a read'}]})
        other=self.store.create('Other')['id'];foreign=self.store.add_artifact(other,'Other','literature',self.raw,{},bump=False)
        result=execute(self.runner,self.wid,{'reads':[self.request(foreign)]})
        self.assertEqual(result['rows'][0]['status'],'input_error')

    def test_oversized_view_is_not_silently_delivered_or_removed(self):
        raw=dump({'rows':[{'text':'preserved '*10000}]}).encode()
        aid=self.store.add_artifact(self.wid,'Large','literature',raw,{},bump=False)
        result=execute(self.runner,self.wid,{'reads':[self.request(aid),self.request()]})
        self.assertEqual(result['rows'][0]['status'],'needs_narrower_read')
        self.assertIsNone(result['rows'][0]['view'])
        self.assertEqual(result['rows'][1]['status'],'succeeded')
        self.assertEqual(self.store.artifact(self.wid,aid)['content'],raw)
        self.assertEqual(result['status'],'partial')

    def test_exported_model_request_is_accepted_by_actual_local_reader(self):
        # Reproduces the real model following an exported, aliased nested schema
        # that used to disagree with the local reader. No fake model is needed.
        functions={f['name']:f for f in model_functions()}
        request={'reads':[self.request()], 'research_notes':{
            'findings':[],'next_goal':'Read the existing exact values','open_questions':[]}}
        jsonschema.validate(request,functions['read_evidence_bundle']['parameters'])
        local={k:v for k,v in request.items() if k!='research_notes'}
        jsonschema.validate(local,FUNCTION_BY_NAME['read_evidence_bundle']['parameters'])
        result=execute(self.runner,self.wid,local)
        self.assertEqual(result['rows'][0]['view']['result']['rows'][0]['value'],0)
        self.assertEqual(result['rows'][0]['view']['result']['rows'][1]['value'],None)
        nested=functions['read_evidence_bundle']['parameters']['properties']['reads']['items']['anyOf']
        for option in nested:
            self.assertNotIn('research_notes',option['properties']['arguments']['properties'])
        # A second export cannot progressively mutate the base contracts.
        self.assertEqual(model_functions(),list(functions.values()))
        self.assertNotIn('research_notes',FUNCTION_BY_NAME['inspect_artifact']['parameters']['properties'])

    def test_budget_deferral_is_distinct_and_independent_of_request_order(self):
        requests=[]
        for i in range(5):
            raw=dump({'rows':[{'text':str(i)*55000}]}).encode()
            aid=self.store.add_artifact(self.wid,'Budget view','literature',raw,{},bump=False)
            requests.append(self.request(aid))
        requests.append(self.request())
        forward=execute(self.runner,self.wid,{'reads':requests})
        reverse=execute(self.runner,self.wid,{'reads':list(reversed(requests))})
        def identities(result):
            return {r['source_artifact_id']:(r['status'],r['view_sha256']) for r in result['rows']}
        self.assertEqual(identities(forward),identities(reverse))
        self.assertEqual(forward['rows'][0]['status'],'bundle_budget_deferred')
        self.assertEqual(forward['rows'][-1]['status'],'succeeded')
        self.assertEqual(forward['status'],'partial')


if __name__=='__main__':unittest.main()
