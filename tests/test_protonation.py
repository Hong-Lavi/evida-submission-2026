import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from evida.protonation import prepare, run, state_csv, configuration
from evida.contracts import FUNCTION_BY_NAME, CHECK_OPERATION, model_functions
from evida.runner import Runner
from evida.gateway import Gateway
from evida.store import Store

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures'


def source():
    provenance = json.loads((FIXTURE / 'protonation-source-provenance.json').read_text())
    return {**provenance, 'content': (FIXTURE / 'protonation-source.json').read_bytes()}


def arguments(aid=None):
    s = source(); rows = json.loads(s['content'])['rows']
    return {'artifact_id': aid or s['id'],
            'structures': [{'source_pointer': f'/rows/{i}/smiles', 'smiles': rows[i]['smiles']} for i in range(5)],
            'ph_min': 6.4, 'ph_max': 6.4, 'precision': 1.0, 'max_variants': 128}


class BindingTests(unittest.TestCase):
    def test_public_projection_is_bound_and_original_receipt_is_retained(self):
        s=source(); bound=prepare(s,arguments())
        self.assertEqual(bound['source_artifact_sha256'], 'f1a4bd2d9cb948f89a499869c17a26634c32e3b5e9c8dc02e3608ef1c2e28350')
        self.assertEqual(s['original_source_artifact_sha256'], '7407372b21964b3fb86db6887e817a452856b5e764060d023f42714baabcd661')
        self.assertEqual(s['public_projection_sha256'], bound['source_artifact_sha256'])
        self.assertEqual(len(bound['structures']),5)

    def test_tampering_and_invalid_named_parameters_rejected(self):
        for key,value in [('ph_min',float('nan')),('ph_max',15),('precision',0),('max_variants',True),('max_variants',129),('structures',[])]:
            with self.subTest(key=key,value=value):
                a=arguments();a[key]=value
                with self.assertRaises(ValueError):prepare(source(),a)
        s=source();s['content']+=b' '
        with self.assertRaises(ValueError):prepare(s,arguments())
        for edit in ['smiles','source_pointer','extra','duplicate','sha']:
            a=arguments()
            if edit=='smiles':a['structures'][0]['smiles']='CC'
            elif edit=='source_pointer':a['structures'][0]['source_pointer']='/rows/999/smiles'
            elif edit=='extra':a['structures'][0]['path']='/tmp/arbitrary'
            elif edit=='duplicate':a['structures'].append(a['structures'][0])
            else:a['source_artifact_sha256']='0'*64
            with self.subTest(edit=edit),self.assertRaises(ValueError):prepare(source(),a)

    def test_registered_function_and_check_operation_available(self):
        self.assertIn('enumerate_protonation_states',FUNCTION_BY_NAME)
        self.assertTrue(any(f['name']=='enumerate_protonation_states' for f in model_functions()))
        self.assertTrue(any(v.get('properties',{}).get('name',{}).get('enum')==['enumerate_protonation_states'] for v in CHECK_OPERATION['anyOf']))

    def test_csv_parsing_uses_mapped_exact_structure(self):
        raw=b'id,structure,smiles\np1,CCN,bogus\n'
        s={'id':'fixture','kind':'molecule_csv','sha256':hashlib.sha256(raw).hexdigest(),'content':raw,
           'meta':{'id_column':'id','smiles_column':'structure'}}
        a=arguments('fixture');a['structures']=[{'source_pointer':'/rows/0/smiles','smiles':'CCN'}]
        self.assertEqual(prepare(s,a)['structures'][0]['smiles'],'CCN')
        a['structures'][0]['smiles']='bogus'
        with self.assertRaises(ValueError):prepare(s,a)


class TransferTests(unittest.TestCase):
    def test_parseable_but_integrity_mismatched_or_unknown_states_stay_raw_only(self):
        import csv
        import io
        result={'rows':[{'source_row_index':0,'source_pointer':'/rows/0/smiles','candidate_id':'fixture',
            'states':[{'exact_author_smiles':'CCN','rdkit_parse_valid':True,'heavy_atom_element_counts_preserved':True},
                      {'exact_author_smiles':'CCO','rdkit_parse_valid':True,'heavy_atom_element_counts_preserved':False},
                      {'exact_author_smiles':'CCC','rdkit_parse_valid':True},
                      {'exact_author_smiles':'bogus','rdkit_parse_valid':False,'heavy_atom_element_counts_preserved':False}]}]}
        original=copy.deepcopy(result)
        text,bindings,excluded=state_csv(result)
        self.assertEqual(result,original)
        self.assertEqual(list(csv.reader(io.StringIO(text))),[['cid','smiles'],['parent_0_state_0','CCN']])
        self.assertEqual([b['state_index']for b in bindings],[0])
        self.assertEqual([e['state_index']for e in excluded],[1,2,3])
        self.assertEqual(excluded[0]['reasons'],['heavy_atom_element_counts_not_verified'])
        self.assertEqual(len(result['rows'][0]['states']),4)


class AuthorTests(unittest.TestCase):
    def test_real_author_preserves_all_42_states_at_three_ph_settings(self):
        prior=json.loads((FIXTURE/'protonation-author-reference.json').read_text())
        count=0
        with tempfile.TemporaryDirectory() as temp:
            for ph in (6.4,7.4,8.4):
                a=arguments();a.update(ph_min=ph,ph_max=ph)
                body=run(prepare(source(),a),Path(temp)/str(ph))
                self.assertEqual(body['status'],'succeeded')
                for row in body['rows']:
                    expected=next(r for r in prior['rows'] if r['source_pointer']==row['source_pointer'] and r['ph']==ph)
                    self.assertEqual([s['exact_author_smiles']for s in row['states']],
                                     [s['exact_author_output_smiles']for s in expected['states']])
                    count+=len(row['states'])
        self.assertEqual(count,42)

    def test_invalid_smiles_failure_retained(self):
        s=source(); value=json.loads(s['content']);value['rows'][0]['smiles']='not a molecule'
        s['content']=json.dumps(value).encode();s['sha256']=hashlib.sha256(s['content']).hexdigest()
        a=arguments();a['structures']=a['structures'][:1];a['structures'][0]['smiles']='not a molecule'
        with tempfile.TemporaryDirectory() as temp:
            body=run(prepare(s,a),Path(temp)/'invalid')
            self.assertEqual(body['status'],'failed');self.assertEqual(len(body['rows']),1)
            self.assertIn(body['rows'][0]['status'],('author_failure','no_states'))
            self.assertEqual(body['rows'][0]['states'],[])

    def test_runtime_timeout_retains_failure_receipt(self):
        cfg=configuration();cfg['timeout_seconds']=0.00001
        with tempfile.TemporaryDirectory() as temp,patch('evida.protonation.configuration',return_value=cfg):
            body=run(prepare(source(),arguments()),Path(temp)/'timeout')
            self.assertEqual(body['status'],'failed');self.assertEqual(body['error'],'timeout')

    def test_output_limit_fails_and_retains_uncompleted_rows(self):
        cfg=configuration();cfg['output_limit_bytes']=1
        with tempfile.TemporaryDirectory() as temp,patch('evida.protonation.configuration',return_value=cfg):
            body=run(prepare(source(),arguments()),Path(temp)/'limit')
            self.assertEqual(body['status'],'failed');self.assertEqual(body['error'],'output_limit')
            self.assertEqual(len(body['rows']),5)
            self.assertTrue(all(r['status']=='not_completed' for r in body['rows']))
            self.assertIn('retained_progress',body)

    def test_oversized_progress_is_stream_hashed_without_read_bytes(self):
        import subprocess
        import sys
        cfg=configuration();bundle=prepare(source(),arguments());actual_popen=subprocess.Popen
        old_read_bytes=Path.read_bytes
        size=9*1024*1024
        expected=hashlib.sha256(b'x'*size).hexdigest()
        # Publish the complete oversized fixture atomically: an interrupted write
        # may correctly retain fewer bytes than the writer originally intended.
        script="from pathlib import Path; import os; Path('oversized.tmp').write_bytes(b'x'*(9*1024*1024)); os.replace('oversized.tmp','progress.json')"
        def launch(command,**kwargs):
            return actual_popen([sys.executable,'-B','-c',script],**kwargs)
        def bounded_read(path):
            if path.name=='progress.json':raise AssertionError('Oversized progress cannot use read_bytes')
            return old_read_bytes(path)
        with tempfile.TemporaryDirectory() as temp, patch('evida.protonation.configuration',return_value=cfg), \
                patch('evida.protonation.subprocess.Popen',side_effect=launch),patch.object(Path,'read_bytes',bounded_read):
            body=run(bundle,Path(temp)/'oversized')
        self.assertEqual(body['error'],'output_limit')
        self.assertEqual(body['retained_progress']['bytes'],size)
        self.assertEqual(body['retained_progress']['sha256'],expected)
        self.assertEqual(len(body['rows']),5)

    def test_timeout_kills_descendant_after_parent_exits_with_pipe_open(self):
        import os
        import signal
        import subprocess
        import sys
        import time
        cfg=configuration();cfg['timeout_seconds']=0.5
        bundle=prepare(source(),arguments());actual_popen=subprocess.Popen;started=time.monotonic()
        launched=[]
        script="import subprocess,sys; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)']); Path('descendant.pid').write_text(str(p.pid))"
        def launch(command,**kwargs):
            process=actual_popen([sys.executable,'-B','-c',script],**kwargs)
            launched.append(process)
            return process
        with tempfile.TemporaryDirectory() as temp,patch('evida.protonation.configuration',return_value=cfg), \
                patch('evida.protonation.subprocess.Popen',side_effect=launch):
            work=Path(temp)/'descendant'
            try:
                body=run(bundle,work)
                self.assertEqual(body['error'],'timeout')
                self.assertEqual(launched[0].returncode,0)
                self.assertLess(time.monotonic()-started,3)
                child=int((work/'descendant.pid').read_text())
                for _ in range(100):
                    stat=Path(f'/proc/{child}/stat')
                    if not stat.exists() or stat.read_text().split()[2]=='Z':break
                    time.sleep(0.01)
                else:self.fail('Descendant survived process-group timeout')
            finally:
                for process in launched:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass

    def test_operator_cancel_terminates_real_process_and_retains_rows(self):
        import subprocess
        actual_popen=subprocess.Popen
        with tempfile.TemporaryDirectory() as temp:
            work=Path(temp)/'cancel'
            def launch(*args,**kwargs):
                process=actual_popen(*args,**kwargs)
                (work/'protonation.cancel').write_text('operator request')
                return process
            with patch('evida.protonation.subprocess.Popen',side_effect=launch):
                body=run(prepare(source(),arguments()),work)
            self.assertEqual(body['status'],'failed');self.assertEqual(body['error'],'cancelled')
            self.assertEqual(len(body['rows']),5)

    def test_real_registered_worker_reading_csv_and_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'fixture.sqlite3');wid=store.create('Author protonation software fixture')['id']
            s=source();aid=store.add_artifact(wid,'Exact preserved source',s['kind'],s['content'],s['meta'],bump=False)
            a=arguments(aid)
            runner=Runner(ROOT,store,Gateway(json.loads((ROOT/'configs/api_policy.json').read_text()),False),Path(temp)/'attempts')
            try:
                runner.validate_tool(wid,'protonation_states',a)
                key=runner.cache_key(wid,'protonation_states',a)
                jid=store.enqueue(wid,1,'protonation_states',a,cache_key=key)
                result_id=runner.run_tool_job(jid,False)
                if not result_id:self.fail(str(store.snapshot(wid)['jobs']))
                result=json.loads(store.artifact(wid,result_id)['content'])
                self.assertEqual(result['status'],'succeeded')
                self.assertEqual(result['source_artifact_sha256'],s['sha256'])
                self.assertEqual(len(result['rows']),5)
                view=runner.read_view(wid,'inspect_artifact',{'artifact_id':result_id,'offset':0,'limit':2})
                self.assertEqual(view['result']['total_rows'],5);self.assertTrue(view['result']['has_more'])
                csv=store.artifact(wid,result['molecule_csv_artifact_id'])
                self.assertEqual(len(csv['meta']['state_bindings']),32)
                runner.validate_tool(wid,'rdkit',{'artifact_id':csv['id']})
                again=store.enqueue(wid,1,'protonation_states',a,cache_key=key)
                self.assertEqual(runner.run_tool_job(again,False),result_id)
                self.assertEqual(len(list((Path(temp)/'attempts').glob('*/request.json'))),1)
            finally:
                runner.pool.shutdown(wait=True);runner.explanation_pool.shutdown(wait=True)


if __name__=='__main__':unittest.main()
