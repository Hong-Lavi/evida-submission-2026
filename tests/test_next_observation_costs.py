"""Known and unquoted costs, including exact historical calculations; synthetic only."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import jsonschema

from evida.next_observation import schema_for, select, validate_problem
from evida.next_observation_binding import evaluate, prepare
from evida.measurement_report import guarded_calculation
from evida.check_subject_binding import guarded_calculation_v2
from evida.store import Store, dump
from tests.test_next_observation import problem_fixture, publish_fixture, result_fixture


def unknown_alternative(problem):
    other = copy.deepcopy(problem['actions'][1])
    other.update(check_id='unquoted_function', incremental_cost=None)
    problem['actions'].append(other)
    return problem


class NextObservationCostTests(unittest.TestCase):
    def test_known_selection_and_valid_stop_keep_original_summary_and_rows(self):
        p = problem_fixture()
        for result in (None, result_fixture(), result_fixture(outcome_index=1), result_fixture(outcome_index=None)):
            old = select(p, result=result, calculation_version='1')
            new = select(p, result=result)
            for key in ('summary', 'rows', 'unresolvable_pairs', 'conditional_exclusions'):
                self.assertEqual(old[key], new[key])
        stopped = select(p, result=result_fixture())
        self.assertEqual(stopped['summary']['cost'], 0)
        self.assertEqual(stopped['resource_assessment']['scope'], 'no_further_check')

    def test_known_useful_choice_survives_unknown_alternative_without_price_ranking(self):
        p = unknown_alternative(problem_fixture()); original = copy.deepcopy(p)
        out = select(p)
        self.assertEqual(out['summary']['selected_check_ids'], ['function'])
        self.assertEqual(out['summary']['cost'], 3)
        self.assertEqual(out['resource_assessment']['budget_status'], 'within_declared_budget')
        self.assertEqual([x['check_ids'] for x in out['pending_cost_options']], [['unquoted_function']])
        option = out['pending_cost_options'][0]
        self.assertIsNone(option['cost'])
        self.assertEqual(option['known_subtotal'], 1)  # only the shared setup
        self.assertEqual(option['unknown_component_ids'], ['action:unquoted_function'])
        self.assertEqual(option['resolution'], 'full')
        self.assertEqual(p, original)

    def test_unavailable_useful_check_is_unresolved_not_a_reached_decision(self):
        p = problem_fixture(); p['actions'][1]['available'] = False
        out = select(p)
        self.assertEqual(out['summary']['selection_status'], 'stop_specific_claim')
        self.assertEqual(out['summary']['cost'], 0)
        self.assertEqual(out['resource_assessment']['scope'], 'declared_plan')
        self.assertEqual(out['summary']['common_next_decisions'], [])

    def test_only_unknown_useful_check_asks_for_its_quote(self):
        p = problem_fixture(); p['actions'][1]['incremental_cost'] = None
        out = select(p)
        self.assertEqual(out['summary']['selection_status'], 'needs_cost_information')
        self.assertEqual(out['summary']['selected_check_ids'], [])
        self.assertIsNone(out['summary']['cost'])
        self.assertEqual(out['pending_cost_options'][0]['known_subtotal'], 1)
        self.assertEqual(out['resource_assessment']['budget_status'], 'unresolved')
        self.assertEqual(out['conditional_exclusions'], [])

    def test_shared_unknown_is_counted_once_and_known_lower_bound_can_exceed_budget(self):
        p = problem_fixture(); p['shared_controls'][0]['cost'] = None
        out = select(p)
        option = out['pending_cost_options'][0]
        self.assertEqual(option['known_subtotal'], 2)
        self.assertEqual(option['unknown_component_ids'], ['shared_control:paired'])
        p['budget'] = 1
        out = select(p)
        self.assertEqual(out['summary']['selection_status'], 'needs_budget_adjustment')
        self.assertEqual(out['resource_assessment']['scope'], 'declared_plan')
        self.assertEqual(out['resource_assessment']['budget_status'], 'over_declared_budget')
        self.assertEqual(out['pending_cost_options'][0]['budget_status'], 'over_declared_budget')
        self.assertIsNone(out['summary']['cost'])

    def test_uninformative_unknown_repeat_and_full_supersets_are_not_alternatives(self):
        p = problem_fixture(); p['actions'][0]['incremental_cost'] = None
        out = select(p)
        self.assertEqual(out['summary']['selected_check_ids'], ['function'])
        self.assertEqual(out['pending_cost_options'], [])
        self.assertEqual(out['pending_cost_filter'], {'evaluated': 2, 'full_supersets_excluded': 1,
            'partial_multicheck_excluded': 0, 'noninformative_excluded': 1})

    def test_partial_options_are_singletons_and_full_joint_plan_keeps_shared_cost_once(self):
        p = problem_fixture(); template = p['actions'][1]
        p['worlds'] = [{**copy.deepcopy(p['worlds'][0]), 'id': 'w'+str(i), 'adequate_decision_ids': ['d'+str(i)]} for i in range(4)]
        p['decisions'] = [{'id':'d'+str(i), 'label':'Decision '+str(i), 'adequacy_basis':'Synthetic'} for i in range(4)]
        p['actions'] = []
        for bit in (0, 1):
            a = copy.deepcopy(template); a.update(check_id='bit'+str(bit), incremental_cost=None)
            a['predictions'] = [{**copy.deepcopy(template['predictions'][0]), 'world_id':'w'+str(i),
                                 'outcome_indices':[(i >> bit) & 1]} for i in range(4)]
            p['actions'].append(a)
        repeat = copy.deepcopy(p['actions'][0]); repeat['check_id'] = 'repeat'
        for prediction in repeat['predictions']: prediction['outcome_indices'] = [0]
        p['actions'].append(repeat)
        out = select(p)
        options = out['pending_cost_options']
        self.assertEqual([x['check_ids'] for x in options], [['bit0'], ['bit0','bit1'], ['bit1']])
        self.assertEqual([x['resolution'] for x in options], ['partial','full','partial'])
        self.assertEqual(options[1]['known_subtotal'], 1)
        self.assertEqual(out['pending_cost_filter']['partial_multicheck_excluded'], 2)

    def test_maximum_combinations_have_complete_accounting_and_stable_ids(self):
        p = problem_fixture(); a = p['actions'][1]
        p['actions'] = [{**copy.deepcopy(a), 'check_id':f'check{i:02}', 'incremental_cost':None} for i in reversed(range(12))]
        out = select(p)
        self.assertEqual(out['pending_cost_filter']['evaluated'], 298)
        self.assertEqual(out['pending_cost_options_total'], 12)
        self.assertEqual(out['pending_cost_options_limit'], 298)
        self.assertEqual(out['pending_cost_options_omitted'], 0)
        self.assertEqual(out['pending_cost_filter']['full_supersets_excluded'], 286)
        self.assertEqual([p['check_ids'][0] for p in out['pending_cost_options']], [f'check{i:02}' for i in range(12)])

    def test_legacy_input_contract_rejects_null_and_latest_never_accepts_missing_or_invalid_cost(self):
        p = problem_fixture(); p['actions'][1]['incremental_cost'] = None
        args = {'mode':'plan', 'artifact_id':'d', 'source_artifact_ids':[], 'problem':p, 'result':None}
        jsonschema.validate(args, schema_for('2'))
        with self.assertRaises(jsonschema.ValidationError): jsonschema.validate(args, schema_for('1'))
        with self.assertRaises(ValueError): select(p, calculation_version='1')
        for bad in (True, -1, 0, 'unknown', float('inf'), float('nan')):
            value = problem_fixture(); value['actions'][1]['incremental_cost'] = bad
            with self.subTest(cost=bad), self.assertRaises(ValueError): select(value)
        for field in ('incremental_cost',):
            value = problem_fixture(); del value['actions'][1][field]
            with self.assertRaises(ValueError): validate_problem(value)
        value = problem_fixture(); value['budget'] = None
        with self.assertRaises(ValueError): select(value)
        with self.assertRaises(ValueError): select(problem_fixture(), calculation_version='3')

    def test_failed_readout_has_no_experiment_price_or_exclusion(self):
        p = unknown_alternative(problem_fixture())
        out = select(p, result=result_fixture(measurement_validity='failed'))
        self.assertEqual(out['summary']['selection_status'], 'repair_readout')
        self.assertIsNone(out['summary']['cost'])
        self.assertEqual(out['summary']['selected_check_ids'], [])
        self.assertEqual(out['summary']['retained_configuration_ids'], [w['id'] for w in p['worlds']])
        self.assertEqual(out['conditional_exclusions'], [])
        self.assertEqual(out['pending_cost_options'], [])
        self.assertEqual(out['resource_assessment']['scope'], 'repair')
        self.assertIsNone(out['resource_assessment']['known_subtotal'])
        self.assertEqual(out['resource_assessment']['unknown_component_ids'], ['readout_repair:function'])
        self.assertEqual(select(problem_fixture(), result=result_fixture(measurement_validity='failed'), calculation_version='1')['summary']['cost'], 0)

    def test_report_subject_precision_and_context_guards_clear_plan_resources(self):
        p = unknown_alternative(problem_fixture()); assessment = result_fixture()
        body = {'message_id':assessment['message_id'], 'measurement_report': {
            'measurement_validity':'failed', 'intervention_status':'validated', 'precision':'adequate', 'context_match':True}}
        report, guard = guarded_calculation(p, None, assessment, body, calculation_version='2')
        subject, _, subject_guard = guarded_calculation_v2(p, None, assessment, {}, {'status':'mismatch'}, calculation_version='2')
        outputs = [report, subject]
        for changes in ({'precision':'unknown'}, {'context_match':False}, {'intervention_status':'unknown'}):
            outputs.append(select(p, result=result_fixture(**changes)))
        self.assertTrue(guard['applied']); self.assertTrue(subject_guard['applied'])
        for out in outputs:
            self.assertIsNone(out['summary']['cost'])
            self.assertEqual(out['summary']['selected_check_ids'], [])
            self.assertEqual(out['pending_cost_options'], [])
            self.assertEqual(out['pending_cost_filter']['evaluated'], 0)
            self.assertEqual(out['resource_assessment']['scope'], 'declared_plan')
            self.assertEqual(out['resource_assessment']['budget_status'], 'unresolved')
            self.assertEqual(out['resource_assessment']['unknown_component_ids'], [])
            self.assertEqual(out['conditional_exclusions'], [])

    def test_v1_golden_calculations_remain_exact(self):
        golden = json.loads((Path(__file__).parent/'fixtures/next_observation_cost_v1.json').read_text())
        for row in golden['cases']:
            with self.subTest(name=row['name']):
                self.assertEqual(select(row['problem'], result=row['result'], calculation_version='1'), row['output'])

    def test_old_guard_chains_replay_exactly_then_create_v2_without_mutation(self):
        for guard_version in (None, '1', '2'):
            with self.subTest(guard_version=guard_version), tempfile.TemporaryDirectory() as temp:
                store = Store(Path(temp)/'store.sqlite'); wid = store.create('Synthetic legacy chain')['id']
                plan, _ = publish_fixture(store, wid)
                bundle = prepare(store, wid, plan); bundle.pop('calculation_version')
                old = evaluate(bundle)
                self.assertNotIn('calculation_version', old)
                def retain(value):
                    aid = store.add_artifact(wid, 'Synthetic historical result', 'next_observation_selection', dump(value).encode(), {}, bump=False)
                    jid = store.enqueue(wid, store.snapshot(wid)['rev'], 'next_observation_selection', {})
                    store.finish_job(jid, 'succeeded', aid)
                    return aid
                def observe():
                    return store.command(wid, store.snapshot(wid)['rev'], 'observation-'+str(store.snapshot(wid)['rev']), {
                        'kind':'observation','text':'Synthetic failed readout, not an experiment.','synthetic':True,
                        'measurement_report':{'measurement_validity':'failed','intervention_status':'validated','precision':'adequate','context_match':True},
                        'research_context':{'decision_id':plan['artifact_id'],'check_id':'function','hypothesis_ids':['h'],'comparison':'unclear'}})['message_id']
                def update(parent, mid):
                    return {'mode':'review_result','artifact_id':parent,'source_artifact_ids':[], 'problem':None,'result':result_fixture(message_id=mid)}
                parent = retain(old); mid = observe(); args = update(parent, mid)
                old_bundle = prepare(store,wid,args); old_bundle.pop('calculation_version')
                historical = evaluate(old_bundle)
                if guard_version is None:
                    historical.update(select(plan['problem'],result=args['result'],calculation_version='1'))
                    historical.pop('report_guard_version');historical.pop('report_guard');historical.pop('subject_guard')
                else:
                    historical['report_guard_version'] = guard_version
                    if guard_version == '1':historical.pop('subject_guard')
                aid = retain(historical); original = store.artifact(wid,aid)['content']
                latest_args = update(aid, observe()); current = prepare(store,wid,latest_args)
                latest = evaluate(current)
                self.assertEqual(latest['calculation_version'],'2')
                self.assertIsNone(latest['summary']['cost'])
                self.assertEqual(latest['summary']['retained_configuration_ids'],historical['summary']['retained_configuration_ids'])
                self.assertEqual(store.artifact(wid,aid)['content'], original)
                for change in ('summary', 'version'):
                    tampered=copy.deepcopy(current); record=tampered['artifacts'][aid]
                    value=json.loads(base64.b64decode(record['content_base64']))
                    if change=='summary':value['summary']['cost']=77
                    else:value['calculation_version']='unrecognized'
                    raw=dump(value).encode();record['content_base64']=base64.b64encode(raw).decode();record['sha256']=hashlib.sha256(raw).hexdigest()
                    with self.assertRaises(ValueError):evaluate(tampered)

    def test_v2_resource_metadata_cannot_be_forged_without_changing_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'store.sqlite');wid=store.create('Synthetic resource integrity')['id']
            args,_=publish_fixture(store,wid);value=evaluate(prepare(store,wid,args))
            value['resource_assessment']['known_subtotal']=0
            aid=store.add_artifact(wid,'Synthetic forged metadata','next_observation_selection',dump(value).encode(),{},bump=False)
            jid=store.enqueue(wid,store.snapshot(wid)['rev'],'next_observation_selection',{});store.finish_job(jid,'succeeded',aid)
            mid=store.command(wid,store.snapshot(wid)['rev'],'synthetic-observation',{'kind':'observation','text':'Synthetic only','synthetic':True,
                'research_context':{'decision_id':args['artifact_id'],'check_id':'function','hypothesis_ids':['h'],'comparison':'unclear'}})['message_id']
            with self.assertRaisesRegex(ValueError,'비용'):
                prepare(store,wid,{'mode':'review_result','artifact_id':aid,'source_artifact_ids':[], 'problem':None,'result':result_fixture(message_id=mid)})


if __name__ == '__main__':
    unittest.main()
