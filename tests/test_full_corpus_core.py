import json
import hashlib
from types import SimpleNamespace
from pathlib import Path
import unittest
from evida.reasoning_core import context
from evida.reasoning_perspectives import read_detail, for_stage
from evida.contracts import model_functions

class FullCorpusCore(unittest.TestCase):
    def test_complete_original_denominator_and_conditioned_detail(self):
        path=Path(__file__).parents[1]/'evida/reasoning_corpus_coverage.json'
        rows=json.loads(path.read_text())['cases']
        self.assertEqual(len(rows),500);self.assertEqual(len({r['pmcid']for r in rows}),500)
        core=context('Unfamiliar research objective')
        self.assertEqual(len(core['perspectives']),48)
        for p in core['perspectives']:
            detail=read_detail(p['id'],'principle')['rows'][0]
            self.assertEqual(set(detail['stage_use']),{'investigate','generate','compare','update'})
            self.assertTrue(detail['limits'])
            self.assertTrue(read_detail(p['id'],'sources')['rows'])
        amended=next(r for r in rows if r['pmcid']=='PMC6028240')
        self.assertIn('n204',amended['source_argument_amendment']['text'])
    def test_nonillustrative_construction_case_is_excluded_from_index_and_detail(self):
        path=Path(__file__).parents[1]/'evida/reasoning_perspectives.json'
        p=json.loads(path.read_text())['perspectives'][0]
        shown={s['id']for e in p['worked_examples']for s in e['source_refs']}
        other=next(c for c in p['construction_case_ids']if c not in shown)
        core=context('Goal',excluded_cases=[other])
        self.assertNotIn(p['id'],{r['id']for r in core['perspectives']})
        with self.assertRaises(ValueError):read_detail(p['id'],'principle',excluded_cases=[other])
    def test_bounded_sources_do_not_reveal_historical_example_details(self):
        self.assertEqual(read_detail('MECH-01','sources',restricted=True)['rows'],[])
        self.assertEqual(read_detail('MECH-01','cases',restricted=True)['rows'],[])
        self.assertEqual(read_detail('MECH-01','principle',restricted=True)['rows'][0]['worked_examples'],[])
    def test_same_core_is_available_at_all_decision_stages_and_off_arm_has_no_detail(self):
        c=context('Goal')
        for stage in ('frame','research','synthesis','decision_correction'):
            self.assertEqual(for_stage(c,stage)['perspectives'],c['perspectives'])
        self.assertNotIn('read_reasoning_principle',{f['name']for f in model_functions(reasoning_core=False)})
        self.assertIn('read_reasoning_principle',{f['name']for f in model_functions(reasoning_core=True)})

    def test_trace_identity_excludes_its_source_derived_principles(self):
        with self.assertRaises(ValueError):
            read_detail('MECH-10','cases',excluded_cases=['P139-PMC6028240'])

    def test_bounded_source_all_principles_deliver_only_general_stage_operations(self):
        for p in context('Goal')['perspectives']:
            row=read_detail(p['id'],'principle',restricted=True)['rows'][0]
            self.assertEqual(row['worked_examples'],[])
            self.assertNotIn('PMC',json.dumps(row))
            self.assertNotIn('limits',row)
            self.assertEqual(row['stage_use']['generate'],p['principle'])

    def test_runner_requires_delivered_protocol_and_exact_detail_version(self):
        from evida.runner import Runner
        root=Path(__file__).parents[1]
        hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
                ('evida/reasoning_principle_details.json','evida/reasoning_corpus_coverage.json')}
        protocol={'reasoning_core':context('Goal'),'code_sha256':hashes}
        state={'artifacts':[],'title':'Goal','jobs':[]}
        store=SimpleNamespace(snapshot=lambda wid:state,artifact=lambda wid,aid:{'content':json.dumps(protocol)})
        runner=SimpleNamespace(store=store,root=root)
        args={'principle_id':'MECH-01','section':'principle','offset':0,'limit':1}
        with self.assertRaises(ValueError):Runner.read_view(runner,'w', 'read_reasoning_principle',args)
        state['artifacts']=[{'kind':'protocol_snapshot','id':'p'}]
        self.assertEqual(Runner.read_view(runner,'w','read_reasoning_principle',args)['result']['total_rows'],1)
        protocol['code_sha256']['evida/reasoning_principle_details.json']='0'*64
        with self.assertRaises(ValueError):Runner.read_view(runner,'w','read_reasoning_principle',args)
