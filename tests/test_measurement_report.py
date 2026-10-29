"""Native event/source binding and conditional filtering, using synthetic reports only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from evida.store import Store, dump
from evida.runner import Runner
from evida.next_observation_binding import prepare, evaluate
from evida.measurement_report import guarded_calculation
from tests.test_next_observation import publish_fixture, problem_fixture, result_fixture

REPORT = {'measurement_validity': 'failed', 'intervention_status': 'validated',
          'precision': 'insufficient', 'context_match': None, 'assessment_basis': 'Synthetic failed readout; retain counterevidence.'}


class MeasurementReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'test.db'); self.wid = self.store.create('Synthetic report')['id']
        self.plan, _ = publish_fixture(self.store, self.wid)
        self.raw = self.store.add_artifact(self.wid, 'Synthetic raw', 'source_file', b'\xef\xbb\xbfraw\r\nfailed\r\n', {}, media='text/plain', bump=False)
        self.body = {'kind': 'observation', 'text': 'Synthetic measurement, not an experiment.', 'synthetic': True,
                     'research_context': {'decision_id': self.plan['artifact_id'], 'check_id': 'function', 'hypothesis_ids': ['h'], 'comparison': 'unclear'}}

    def save(self, **fields):
        return self.store.command(self.wid, self.store.snapshot(self.wid)['rev'], 'command-' + str(self.store.snapshot(self.wid)['rev']), {**self.body, **fields})['message_id']

    def keep_result(self, value):
        aid = self.store.add_artifact(self.wid, 'Synthetic conditional result', 'next_observation_selection', dump(value).encode(), {}, bump=False)
        jid = self.store.enqueue(self.wid, self.store.snapshot(self.wid)['rev'], 'next_observation_selection', {})
        self.store.finish_job(jid, 'succeeded', aid)
        return aid

    def update_args(self, mid, parent=None):
        return {'mode': 'review_result', 'artifact_id': parent or self.keep_result(evaluate(prepare(self.store, self.wid, self.plan))),
                'source_artifact_ids': [], 'problem': None, 'result': result_fixture(message_id=mid)}

    def test_report_sources_reach_native_planner_and_worker_without_relabeling(self):
        mid = self.save(measurement_report=REPORT, source_artifact_ids=[self.raw])
        stored = next(e['body'] for e in self.store.snapshot(self.wid)['events'] if e['body'].get('message_id') == mid)
        runner = object.__new__(Runner); runner.store = self.store; runner.root = Path(__file__).resolve().parents[1]
        context = runner.model_context(self.wid, self.store.snapshot(self.wid)['rev'], False)
        delivered = next(e['body'] for e in context['ORIGINAL_MESSAGES'] if e['body'].get('message_id') == mid)
        self.assertEqual(stored, delivered)
        self.assertEqual(stored['source_artifact_hashes'][self.raw], self.store.artifact(self.wid, self.raw)['sha256'])
        args = self.update_args(mid); bundle = prepare(self.store, self.wid, args); result = evaluate(bundle)
        self.assertIn(self.raw, bundle['artifacts'])
        self.assertEqual(result['observed_events'][0]['measurement_report'], REPORT)
        self.assertEqual(result['observed_events'][0]['source_artifact_refs'], stored['source_artifact_refs'])
        self.assertEqual(result['result_assessment'], args['result'])
        self.assertEqual(result['summary']['selection_status'], 'report_confirmation_required')
        self.assertEqual(len(result['summary']['retained_configuration_ids']), 3)
        self.assertEqual(result['conditional_exclusions'], [])
        self.assertEqual(len(result['measurement_report_comparison'][0]['differences']), 3)
        self.assertFalse(result['provenance']['scientific_validation'])
        tampered = copy.deepcopy(bundle); tampered['events'][-1]['body']['source_artifact_hashes'][self.raw] = '0' * 64
        with self.assertRaises(ValueError): evaluate(tampered)
        updated = self.keep_result(result)
        with self.assertRaisesRegex(ValueError, '반복'): prepare(self.store, self.wid, self.update_args(mid, updated))
        correction = self.save(kind='correction', measurement_report=REPORT, source_artifact_ids=[self.raw])
        with self.assertRaises(ValueError): prepare(self.store, self.wid, self.update_args(correction))

    def test_omitted_report_legacy_chain_and_explicit_unknown_are_distinct(self):
        legacy = evaluate(prepare(self.store, self.wid, self.plan))
        legacy.pop('report_guard_version'); legacy.pop('report_guard')
        parent = self.keep_result(legacy)
        mid = self.save(); args = self.update_args(mid, parent)
        out = evaluate(prepare(self.store, self.wid, args))
        self.assertNotIn('measurement_report', out['observed_events'][0])
        self.assertEqual(out['measurement_report_comparison'], [])
        self.assertEqual(len(out['summary']['retained_configuration_ids']), 2)
        self.assertIsNone(out['report_guard'])
        report = dict(measurement_validity='unknown', intervention_status='unknown', precision='unknown', context_match=None)
        mid = self.save(measurement_report=report)
        out = evaluate(prepare(self.store, self.wid, self.update_args(mid, parent)))
        self.assertEqual(len(out['summary']['retained_configuration_ids']), 3)
        self.assertTrue(out['report_guard']['applied'])

    def test_all_failure_unknown_guards_preserve_inputs_and_do_not_promote_positive_report(self):
        passed = {k: result_fixture()[k] for k in ('measurement_validity','intervention_status','precision','context_match')}
        for key, value in [('measurement_validity','failed'),('intervention_status','failed'),('precision','insufficient'),('context_match',False),('measurement_validity','unknown'),('intervention_status','unknown'),('precision','unknown'),('context_match',None)]:
            body = {'message_id':'synthetic_message','measurement_report':{**passed,key:value}}
            assessment=result_fixture(); original=copy.deepcopy(assessment)
            out, guard=guarded_calculation(problem_fixture(), None, assessment, body)
            self.assertTrue(guard['applied']); self.assertEqual(len(out['summary']['retained_configuration_ids']),3)
            self.assertEqual(assessment,original)
        out,guard=guarded_calculation(problem_fixture(),None,result_fixture(measurement_validity='failed'),{'message_id':'synthetic_message','measurement_report':passed})
        self.assertFalse(guard['applied']);self.assertEqual(out['summary']['selection_status'],'repair_readout')

    def test_stored_unguarded_history_replays_with_its_original_rule(self):
        from evida.next_observation import select
        mid = self.save(measurement_report=REPORT, synthetic=False)
        args = self.update_args(mid)
        guarded = evaluate(prepare(self.store, self.wid, args))
        original_rule = copy.deepcopy(guarded)
        original_rule.update(select(self.plan['problem'], result=args['result']))
        original_rule.pop('report_guard_version'); original_rule.pop('report_guard')
        parent = self.keep_result(original_rule)
        original_bytes = self.store.artifact(self.wid, parent)['content']
        later = self.save(text='Separate synthetic control observation, not a correction.', measurement_report=REPORT)
        result = evaluate(prepare(self.store, self.wid, self.update_args(later, parent)))
        self.assertEqual(result['summary']['retained_configuration_ids'], original_rule['summary']['retained_configuration_ids'])
        self.assertTrue(result['report_guard']['applied'])
        self.assertEqual(self.store.artifact(self.wid, parent)['content'], original_bytes)
        self.assertEqual(result['observed_events'][0]['origin'], 'researcher_report')

    def test_invalid_sources_forged_server_fields_and_reports_are_atomic(self):
        other = self.store.create('Other synthetic workspace')['id']
        cross = self.store.add_artifact(other,'Other raw','source_file',b'raw',{},bump=False)
        internal = self.store.add_artifact(self.wid,'Internal','model_receipt',b'{}',{},bump=False)
        bad = [dict(source_artifact_ids=[cross]),dict(source_artifact_ids=[internal]),dict(source_artifact_ids=['missing']),
               dict(source_artifact_ids=[self.raw,self.raw]),dict(source_artifact_hashes={}),dict(source_artifact_refs=[]),
               dict(measurement_report=None),dict(measurement_report={}),dict(measurement_report={**REPORT,'context_match':1}),
               dict(measurement_report={**REPORT,'certified':True})]
        before=self.store.snapshot(self.wid)
        for fields in bad:
            with self.subTest(fields=fields),self.assertRaises(ValueError):self.save(**fields)
            self.assertEqual(self.store.snapshot(self.wid),before)
        with self.store.connect(True) as db:db.execute('UPDATE artifacts SET content=? WHERE id=?',(b'tampered',self.raw))
        with self.assertRaisesRegex(ValueError,'해시'):self.save(source_artifact_ids=[self.raw])
