import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error

import jsonschema

from evida.contracts import model_functions, PUBLIC_LOOKUP_BUNDLE
from evida.public_lookup_bundle import execute, retain_sources
from evida.runner import Runner
from evida.store import Store, dump


class PublicLookupBundleTests(unittest.TestCase):
    def item(self, name='search_literature', value='ADPKD'):
        arguments={'query':value,'cursor':''} if name=='search_literature' else {'drug_name':value,'page':1}
        return {'name':name,'arguments':arguments,'purpose':'Compare conditions from already known public terms'}

    def request(self,items):
        return {'known_inputs_basis':'Source disease and public labels already identified; no sibling dependencies','lookups':items}

    def native(self,name,args):
        return {'status':'succeeded','source':{'url':'https://public.example/fixture','sha256':'preserved-original'},
                'summary':{'returned':1},'response':{'rows':[{'value':0,'unknown':None,'name':name}]},
                'rows':[{'value':0,'unknown':None,'name':name}],'original_response_base64':'Zml4dHVyZQ=='}

    def test_per_provider_serialization_independent_provider_progress_and_no_duplicate_fetch(self):
        guard=threading.Lock(); active={}; peaks={}; global_active=0; global_peak=0; calls=[]
        def get(name,args):
            nonlocal global_active,global_peak
            with guard:
                active[name]=active.get(name,0)+1;peaks[name]=max(peaks.get(name,0),active[name]);global_active+=1;global_peak=max(global_peak,global_active);calls.append((name,args))
            time.sleep(.03)
            with guard:active[name]-=1;global_active-=1
            return self.native(name,args)
        items=[self.item(value='A'),self.item(value='B'),self.item('search_drug_labels','C'),self.item(value='A')]
        with patch('evida.public_lookup_bundle.lookup',side_effect=get):r=execute(self.request(items))
        self.assertEqual(len(calls),3);self.assertEqual(peaks['search_literature'],1);self.assertGreater(global_peak,1)
        self.assertEqual(r['rows'][3]['status'],'same_response');self.assertEqual(r['rows'][3]['same_response_as'],0)

    def test_429_and_empty_results_are_separate_and_completed_source_is_retained(self):
        def get(name,args):
            if name=='search_drug_labels':raise urllib.error.HTTPError('https://public.example/limited',429,'rate',{'Retry-After':'60'},None)
            r=self.native(name,args);r['rows']=[];r['summary']={'returned':0};return r
        with tempfile.TemporaryDirectory() as tmp,patch('evida.public_lookup_bundle.lookup',side_effect=get) as call:
            d=Path(tmp)/'individual';r=execute(self.request([self.item(),self.item('search_drug_labels','B')]),d)
            self.assertEqual(call.call_count,2);self.assertEqual(r['status'],'partial')
            self.assertEqual(r['rows'][0]['status'],'succeeded');self.assertEqual(r['rows'][0]['value']['rows'],[])
            self.assertEqual(r['rows'][1]['status'],'rate_limited');self.assertEqual(r['rows'][1]['retry_after'],'60')
            for item in r['rows']:
                raw=(d/item['retained_file']).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),item['retained_file_sha256'])

    def test_real_store_preserves_source_and_only_delivers_bounded_views(self):
        with tempfile.TemporaryDirectory() as tmp,patch('evida.public_lookup_bundle.lookup',side_effect=self.native):
            store=Store(Path(tmp)/'db');wid=store.create('Public lookup test')['id'];runner=Runner.__new__(Runner);runner.store=store
            native=execute(self.request([self.item(),self.item()]))
            result=retain_sources(runner,wid,{'based_rev':1,'id':'fixture_job','attempt':'fixture_attempt'},native)
            row=result['rows'][0];artifact=store.artifact(wid,row['source_artifact_id'])
            self.assertEqual(json.loads(artifact['content']),native['rows'][0]['value'])
            self.assertEqual(artifact['sha256'],row['source_artifact_sha256']);self.assertNotIn('value',row)
            self.assertNotIn('original_response_base64',row['initial_view']['result'])
            self.assertEqual(row['initial_view']['result']['rows'][0]['value'],0)
            self.assertIsNone(row['initial_view']['result']['rows'][0]['unknown'])
            self.assertEqual(result['rows'][1]['source_artifact_id'],row['source_artifact_id'])
            self.assertEqual(len(store.snapshot(wid)['artifacts']),1);self.assertEqual(store.snapshot(wid)['rev'],1)

    def test_wire_contract_matches_local_and_cannot_execute_arbitrary_tools(self):
        wire=next(f for f in model_functions() if f['name']=='collect_public_evidence')
        local=self.request([self.item()]);out={**local,'research_notes':{'findings':[],'open_questions':[],'next_goal':'Compare sources'}}
        jsonschema.validate(out,wire['parameters']);jsonschema.validate(local,PUBLIC_LOOKUP_BUNDLE)
        with patch('evida.public_lookup_bundle.lookup',side_effect=self.native):self.assertEqual(execute(local)['status'],'succeeded')
        bad=self.request([{'name':'dock_molecules','arguments':{},'purpose':'Not a public lookup'}])
        with self.assertRaises(jsonschema.ValidationError):execute(bad)


if __name__=='__main__':unittest.main()
