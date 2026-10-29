"""Synthetic design/transaction tests; no scientific or model-quality evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import jsonschema

from evida.contracts import model_final_decision, model_functions
from evida.finalization import finalize
from evida.reasoning_core import context, predictions_differ, validate_design, view
from evida.research_loop import decision_id
from evida.store import Store, dump
from planner_fixtures import current_final, current_frame
from test_integrity import proposal

ROOT = Path(__file__).resolve().parents[1]


def design(card_id='RC01'):
    return {
        'version': 'reasoning-design-v1', 'H1': '가상 조건: X 감소가 Y를 감소시킨다.',
        'H0': '가상 조건: X 감소 후에도 Y는 변하지 않는다.', 'hypothesis_level': 'target',
        'specimen': '합성 인터페이스 시험 · 실제 생물학적 제안 아님',
        'factors': [{'id': 'sequence', 'name': '처리 서열'}, {'id': 'dose', 'name': '농도'},
                    {'id': 'cells', 'name': '세포 조건'}],
        'changed_variable_id': 'sequence',
        'arms': [{'id': 'a', 'role': 'intervention', 'levels': [
            {'factor_id': 'sequence', 'value': 'X 표적'}, {'factor_id': 'dose', 'value': '동일 농도'},
            {'factor_id': 'cells', 'value': '같은 배치'}]},
            {'id': 'b', 'role': 'reference', 'levels': [
                {'factor_id': 'sequence', 'value': '비표적'}, {'factor_id': 'dose', 'value': '동일 농도'},
                {'factor_id': 'cells', 'value': '같은 배치'}]}],
        'controls': [{'id': 'ref', 'role': 'reference', 'description': '같은 전달체의 비표적 서열',
                      'validity_criterion': '전달량과 세포 생존 조건 일치'},
                     {'id': 'eng', 'role': 'engagement', 'description': 'X 억제 확인',
                      'validity_criterion': '사전 설정한 유효 억제 기준 충족'}],
        'readout': {'name': 'Y 변화', 'contrast': '개입군 − 기준군', 'unit': '상대량', 'timepoint': '48시간'},
        'predictions': {'H1': {'kind': 'direction', 'value': 'decrease'},
                        'H0': {'kind': 'direction', 'value': 'no_change'}},
        'prediction_basis': {'origin': 'proposed', 'source_ids': [], 'rationale': '합성 테스트 가정'},
        'refuting_result': {'prediction': 'H0', 'description': 'X가 충분히 감소해도 Y는 변하지 않음',
                            'valid_control_ids': ['ref', 'eng']},
        'experiment_failure': {'invalid_control_ids': ['ref', 'eng'],
                               'description': 'X 감소 또는 측정 유효성 기준을 충족하지 못함'},
        'next_actions': {'supports': '독립 반복에서 확인', 'refutes': 'X에서 Y로의 연결 재검토',
                         'inconclusive': '추정 불확실성 보존 후 정보량 보완',
                         'experiment_failure': '전달·측정 문제부터 수정'},
        'unresolved_requirements': ['실제 연구에서는 오차·효과 크기·반복 수 기준을 먼저 정해야 함'],
        'interpretation_limits': ['구조 검사이며 실제 효능·안전성 판단이 아님'],
        'cards_used': [{'id': card_id, 'application': '생산 억제와 결과 지표의 연결을 하나씩 시험'}],
    }


def hypothesis(d):
    return {'id': 'h1', 'statement': d['H1'], 'expected_observation': 'Y 감소',
            'alternatives': [d['H0']], 'assessment': 'proposed', 'rationale': '합성 시험',
            'evidence': [], 'reasoning_design': d}


class DesignChecks(unittest.TestCase):
    def test_declared_contrast_pass_keeps_unresolved_readiness(self):
        result = validate_design(design(), allowed_cards={'RC01'}, cards_required=True, source_ids=set())
        self.assertEqual(result['status'], 'declared_contrast_pass')
        self.assertEqual(result['prediction_resolution'], 'qualitative')
        self.assertTrue(result['unresolved_requirements'])

    def test_rejects_nondiscrimination_two_factors_missing_controls_and_empty_refuter(self):
        invalid = []
        d = design(); d['predictions']['H0'] = deepcopy(d['predictions']['H1']); invalid.append(d)
        d = design(); d['arms'][1]['levels'][1]['value'] = '다른 농도'; invalid.append(d)
        d = design(); d['controls'] = []; invalid.append(d)
        d = design(); d['refuting_result']['description'] = '   '; invalid.append(d)
        d = design(); d['refuting_result']['valid_control_ids'] = ['ref']; invalid.append(d)
        d = design(); d['experiment_failure']['description'] = d['refuting_result']['description']; invalid.append(d)
        d = design(); d['experiment_failure']['invalid_control_ids'] = ['eng']; invalid.append(d)
        for index, d in enumerate(invalid):
            with self.subTest(index=index), self.assertRaises((ValueError, jsonschema.ValidationError)):
                validate_design(d)

    def test_numeric_overlap_and_boundary_inclusion(self):
        a = {'kind': 'interval', 'lower': 0, 'upper': 1, 'lower_inclusive': True, 'upper_inclusive': True}
        b = {**a, 'lower': 1, 'upper': 2}
        self.assertFalse(predictions_differ(a, b))
        self.assertTrue(predictions_differ(a, {**b, 'lower_inclusive': False}))
        self.assertFalse(predictions_differ(a, {**b, 'lower': 0.5}))
        with self.assertRaises(ValueError): predictions_differ(a, {**b, 'lower': 3})

    def test_source_and_card_identity_cannot_be_fabricated(self):
        with self.assertRaises(ValueError): validate_design(design(), allowed_cards=set())
        d=design(); d['prediction_basis'].update(origin='source_reported', source_ids=['foreign'])
        with self.assertRaises(ValueError): validate_design(d, source_ids=set())

    def test_current_contract_requires_design_legacy_contract_does_not(self):
        for enabled in (False, True):
            schema = model_final_decision(reasoning_core=enabled)
            jsonschema.Draft202012Validator.check_schema(schema)
            variants=schema['properties']['decision']['properties']['research_loop']['properties']['hypotheses']['items']['anyOf']
            self.assertTrue(all(('reasoning_design' in v['required']) == enabled for v in variants))
            frame=next(f for f in model_functions(reasoning_core=enabled) if f['name']=='frame_work')
            self.assertEqual('reasoning_design' in frame['parameters']['properties']['hypotheses']['items']['anyOf'][0]['required'], enabled)

    def test_bounded_source_context_does_not_deliver_historical_examples(self):
        c=context('KRAS G12C preclinical cancer hypothesis', evidence_scope={
            'mode':'supplied_only', 'as_of':'2012-01-01', 'note':'synthetic bound'})
        self.assertTrue(c['historical_examples_suppressed'])
        self.assertTrue(c['cards'])
        self.assertTrue(all(not card['worked_examples'] for card in c['cards']))
        heldout={'zilebesiran','olpasiran','imatinib','ivacaftor','darapladib'}
        from evida.reasoning_core import load_cards
        self.assertFalse(heldout & {e['case_id'] for card in load_cards() for e in card['worked_examples']})

    def test_initial_frame_can_defer_hypotheses_but_final_decision_cannot(self):
        from evida.reasoning_core import validate_hypothesis_designs
        frame = next(f for f in model_functions(reasoning_core=True) if f['name'] == 'frame_work')
        initial = frame['parameters']['properties']['hypotheses']
        final = model_final_decision(reasoning_core=True)['properties']['decision']['properties']['research_loop']['properties']['hypotheses']
        jsonschema.validate([], initial)
        self.assertEqual(validate_hypothesis_designs([], required=True, allow_empty=True), {})
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate([], final)
        with self.assertRaises(ValueError):
            validate_hypothesis_designs([], required=True)
        incomplete = hypothesis(design())
        del incomplete['reasoning_design']
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate([incomplete], initial)
        with self.assertRaises(ValueError):
            validate_hypothesis_designs([incomplete], required=True, allow_empty=True)

    def test_exact_resume_recovers_packed_card_snapshot_and_explicit_exclusions(self):
        from evida.model_context import model_json
        from evida.reasoning_core import preserved_context
        c=context('triglyceride hepatic siRNA',excluded_cases=['plozasiran'])
        self.assertFalse(any(e['case_id']=='plozasiran' for card in c['cards'] for e in card['worked_examples']))
        self.assertEqual(preserved_context({'input':[{'role':'user','content':model_json({'CURRENT_CALL':{'reasoning_core':c}})}]}),c)


class ReasoningPublication(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.tmp.name)/'db')
        self.wid=self.store.create('합성 실험 설계 · 기능 시험')['id']
        self.context=context('siRNA hepatic production')
        self.p=proposal(1)
        self.p['research_loop']['hypotheses']=[hypothesis(design(self.context['cards'][0]['id']))]

    def tearDown(self): self.tmp.cleanup()

    def test_invalid_draft_never_publishes_then_valid_replacement_preserves_exact_cards(self):
        bad=deepcopy(self.p); bad['research_loop']['hypotheses'][0]['reasoning_design']['controls']=[]
        before=self.store.snapshot(self.wid)
        with self.assertRaises((ValueError,jsonschema.ValidationError)):
            finalize(self.store,self.wid,1,'j',current_final(self.store,self.wid,bad),True,[],None,
                     reasoning_context=self.context)
        self.assertEqual(self.store.snapshot(self.wid)['artifacts'],before['artifacts'])
        aid,published=finalize(self.store,self.wid,1,'j',current_final(self.store,self.wid,self.p),True,[],None,
                              reasoning_context=self.context)
        self.assertTrue(published)
        state=self.store.snapshot(self.wid); state['decision_id']=decision_id(state)
        shown=view(self.store,self.wid,state)
        self.assertEqual(shown['context'],self.context)
        self.assertEqual(shown['checks']['h1']['status'],'declared_contrast_pass')

    def test_new_mode_cannot_publish_legacy_omission(self):
        del self.p['research_loop']['hypotheses'][0]['reasoning_design']
        with self.assertRaisesRegex(ValueError,'reasoning_design'):
            finalize(self.store,self.wid,1,'j',current_final(self.store,self.wid,self.p),True,[],None,
                     reasoning_context=self.context)

    def test_runner_regenerates_invalid_design_in_same_bounded_job(self):
        from evida.runner import Runner
        from evida.gateway import Gateway
        policy=json.loads((ROOT/'configs/api_policy.json').read_text())
        policy['min_request_interval_seconds']=0
        gateway=Gateway(policy, True, model='gpt-6-sol', effort='medium')
        runner=Runner(ROOT,self.store,gateway,Path(self.tmp.name)/'runs')
        calls=[]
        def transport(request):
            calls.append(request)
            from evida.model_context import unpack
            core=unpack(json.loads(request['input'][-1]['content']))['CURRENT_CALL']['reasoning_core']
            p=deepcopy(self.p); p['research_loop']['hypotheses'][0]['reasoning_design']['cards_used'][0]['id']=core['perspectives'][0]['id']
            self.assertEqual(core['stage'], ['frame', 'research', 'decision_correction'][len(calls)-1])
            if len(calls)==1:
                frame=current_frame(self.store,self.wid,{'intent_records':[],'current_question':'합성 설계 기능 시험',
                    'task_brief':[],'questions':[],'hypotheses':[]})
                output=[{'type':'function_call','name':'frame_work','arguments':dump(frame),'call_id':'frame'}]
            else:
                if len(calls)==2:
                    p['research_loop']['hypotheses'][0]['reasoning_design']['predictions']['H0']['value']='decrease'
                output=[{'type':'message','role':'assistant','content':[{'type':'output_text',
                    'text':dump(current_final(self.store,self.wid,p))}]}]
            return {'id':f'synthetic-{len(calls)}','model':gateway.model,'status':'completed','usage':{},'output':output},{}
        gateway.transport=transport
        jid=self.store.enqueue(self.wid,1,'planner',{},'reasoning-test')
        try:
            with patch.object(gateway,'status',return_value={'available':True}), patch('evida.runner.RESEARCH_ROUNDS',32):
                runner.run_planner(jid)
            state=self.store.snapshot(self.wid)
            self.assertEqual(state['jobs'][0]['status'],'succeeded',state['jobs'][0].get('error'))
            self.assertEqual(len(calls),3)
            from evida.model_context import unpack
            self.assertEqual(unpack(json.loads(calls[0]['input'][-1]['content']))['CURRENT_CALL']['maximum_responses_remaining_including_current'],34)
            protocol=next(a for a in state['artifacts'] if a['kind']=='protocol_snapshot')
            self.assertEqual(json.loads(self.store.artifact(self.wid,protocol['id'])['content'])['response_budget'],32)
            self.assertEqual(len([a for a in state['artifacts'] if a['kind']=='decision_validation_error']),1)
            self.assertTrue(any(a['kind']=='decision_proposal' and a['meta'].get('published') is False for a in state['artifacts']))
            review=next(a for a in state['artifacts'] if a['kind']=='reasoning_design_review')
            saved=json.loads(self.store.artifact(self.wid,review['id'])['content'])
            self.assertEqual(saved['context']['stage'],'decision_correction')
            perspective=saved['context']['perspectives'][0]
            self.assertEqual(perspective['detail_function'],'read_reasoning_principle')
            self.assertEqual(perspective['worked_examples'],[])
            detail=runner.read_view(self.wid,'read_reasoning_principle',
                {'principle_id':perspective['id'],'section':'sources','offset':0,'limit':1})['result']
            self.assertEqual(detail['principle_id'],perspective['id'])
            self.assertEqual(len(detail['rows']),1)
            self.assertTrue(detail['catalog_sha256'])
            self.assertFalse(detail['historical_examples_suppressed'])
        finally:
            runner.pool.shutdown(wait=True); runner.explanation_pool.shutdown(wait=True)


if __name__ == '__main__': unittest.main()
