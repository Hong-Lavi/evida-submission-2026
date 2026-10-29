import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from evida.gateway import Gateway
from evida.runner import Runner
from evida.store import Store
from evida.provided_views import build, completed_check

ROOT=Path(__file__).resolve().parents[1]


class ExplicitSourceViewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'test.db')
        self.wid=self.store.create('Synthetic delivery fixture')['id']
        self.value={'conditions':['Synthetic fixed assay, not efficacy'],
            'rows':[{'ratio':.93,'is_measurement':False},{'ratio':1.01,'is_measurement':False}],
            'limits':['Do not infer clinical efficacy from arithmetic.']}
        self.raw=json.dumps(self.value).encode()
        self.aid=self.store.add_artifact(self.wid,'Actual fixture arithmetic','kinetic_conditions',self.raw,{},bump=False)
        self.runner=Runner(ROOT,self.store,Gateway(json.loads((ROOT/'configs/api_policy.json').read_text()),False),Path(self.temp.name)/'attempts')

    def tearDown(self):
        self.runner.pool.shutdown(wait=True);self.runner.explanation_pool.shutdown(wait=True);self.temp.cleanup()

    def test_exact_selected_result_survives_frame_transition_without_whole_archive(self):
        specs=[{'artifact_id':self.aid,'offset':0,'limit':1}]
        job=self.store.enqueue(self.wid,1,'planner',{'synthesis_only':True,'source_views':specs})
        for framed in [False,True]:
            context=self.runner.model_context(self.wid,1,framed,current_job=job,force_full=framed)
            item=context['EXPLICIT_SOURCE_VIEWS']['views'][0]
            self.assertEqual(item['source_sha256'],hashlib.sha256(self.raw).hexdigest())
            self.assertEqual(item['view']['result']['rows'],self.value['rows'][:1])
            self.assertEqual(item['view']['result']['conditions'],self.value['conditions'])
            self.assertTrue(item['view']['result']['has_more'])
            self.assertEqual(item['status'],'explicitly_supplied_not_claimed_model_reading')
        self.assertNotIn('EXPLICIT_SOURCE_VIEWS',self.runner.model_context(self.wid,1,False))

    def test_duplicates_invalid_ranges_and_oversize_are_not_silently_repaired(self):
        spec={'artifact_id':self.aid,'offset':0,'limit':1}
        with self.assertRaises(ValueError):build(self.runner,self.wid,[spec,spec])
        with self.assertRaises(ValueError):build(self.runner,self.wid,[{**spec,'limit':0}])
        large=self.store.add_artifact(self.wid,'Large fixture','research_evidence',json.dumps({'text':'x'*70000}).encode(),{},bump=False)
        with self.assertRaisesRegex(ValueError,'조용히 잘라내지 않습니다'):
            build(self.runner,self.wid,[{**spec,'artifact_id':large}])

    def test_completed_small_result_carries_all_stored_rows_and_conditions(self):
        arguments, delivery = completed_check(self.runner, self.wid, self.aid)
        result = build(self.runner, self.wid, arguments['source_views'])['views'][0]
        self.assertEqual(result['view']['result']['rows'], self.value['rows'])
        self.assertEqual(result['view']['result']['conditions'], self.value['conditions'])
        self.assertEqual(result['source_sha256'], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(delivery['status'], 'exact_completed_presentation_supplied')
        self.assertEqual(self.store.artifact(self.wid, self.aid)['content'], self.raw)

    def test_large_completed_result_stays_catalogued_without_silent_first_page(self):
        for value in ({'rows': [{'i': n} for n in range(101)]}, {'rows': [{'large': 'x'*70000}]}):
            raw = json.dumps(value).encode()
            aid = self.store.add_artifact(self.wid, 'Large completed source', 'research_evidence', raw, {}, bump=False)
            arguments, delivery = completed_check(self.runner, self.wid, aid)
            self.assertEqual(arguments, {})
            self.assertEqual(delivery['status'], 'catalog_only')
            self.assertTrue(delivery['reason'])
            self.assertEqual(self.store.artifact(self.wid, aid)['content'], raw)

    def test_binary_result_is_not_relabelled_as_text_or_model_reading(self):
        aid = self.store.add_artifact(self.wid, 'Preserved image fixture', 'image', b'fixture-not-a-real-image', {}, 'image/png', bump=False)
        arguments, delivery = completed_check(self.runner, self.wid, aid)
        self.assertEqual(arguments, {})
        self.assertEqual(delivery['status'], 'catalog_only')
        self.assertIn('binary', delivery['reason'])

    def test_completed_result_cannot_cross_workspace_boundary(self):
        other = self.store.create('Other fixture')['id']
        with self.assertRaises(KeyError):
            completed_check(self.runner, other, self.aid)
