"""Current model contracts match stage-specific server consumers; no model calls."""
import copy
import json
from pathlib import Path
import unittest

import jsonschema

from evida.contracts import CURRENT_FINAL_DECISION, FRAME, model_final_decision, model_functions
from evida.intent_dependencies import SCHEMA, bind, consumers, digest


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/intent_review_contract_failures.json').read_text())


def wire(frame):
    schema = (next(f['parameters'] for f in model_functions() if f['name'] == 'frame_work')
              if frame else model_final_decision())
    return schema['properties']['intent_review']


def snapshot():
    value = {'state_revision': 1, 'intents': {}}
    for rid in ('I1', 'I2', 'I3', 'I4'):
        record = {'id': rid, 'text': 'Synthetic intent for a contract check.'}
        value['intents'][rid] = {'record': record, 'content_sha256': digest(record)}
    value['snapshot_sha256'] = digest(value)
    return value


def use(kind, cid):
    return {'consumer_kind': kind, 'consumer_id': cid, 'intent_ids': ['I1'],
            'reason': 'This input sets the synthetic question.'}


def reassessment(kind, cid, outcome='retained'):
    return {'consumer_kind': kind, 'consumer_id': cid, 'outcome': outcome,
            'reason': 'Reviewed this exact consumer under the current inputs.'}


class IntentReviewWireTests(unittest.TestCase):
    def test_original_call1_frame_hypothesis_consumers_rejected_by_current_wire(self):
        case = next(c for c in FIXTURE['cases'] if c['id'] == 'call-0001')
        review = case['intent_review']
        jsonschema.validate(review, SCHEMA)  # The original record shape remains readable.
        self.assertEqual([r['consumer_id'] for r in review['uses']], ['current_question', 'H1', 'H2'])
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(review, wire(True))
        with self.assertRaises(ValueError):
            bind(review, snapshot(), consumers({'current_question': 'Question'}), [])

    def test_original_call16_recommendation_id_rejected_by_current_wire(self):
        case = next(c for c in FIXTURE['cases'] if c['id'] == 'call-0016')
        review = case['intent_review']
        jsonschema.validate(review, SCHEMA)
        self.assertEqual(review['uses'][0]['consumer_id'], 'current_recommendation')
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(review, wire(False))
        with self.assertRaises(ValueError):
            bind(review, snapshot(), consumers({'current_question': 'Question'}, {}), [])

    def test_frame_question_pair_passes_schema_and_existing_server_binding(self):
        frame = {'current_question': 'Question', 'hypotheses': [{'id': 'H1'}]}
        review = {'uses': [use('question', 'current_question')],
                  'reassessments': [reassessment('question', 'current_question')]}
        required = [{'consumer_kind': 'question', 'consumer_id': 'current_question',
                     'content_sha256': digest('Question'), 'trigger': 'input_changed', 'changed_intent_ids': ['I1']}]
        jsonschema.validate(review, wire(True))
        result = bind(review, snapshot(), consumers(frame), required)
        self.assertEqual([(r['consumer_kind'], r['consumer_id']) for r in result['consumers']],
                         [('question', 'current_question')])

    def test_frame_rejects_wrong_pair_in_uses_and_reassessments(self):
        for field in ('uses', 'reassessments'):
            for kind, cid in [('question', 'recommendation'), ('hypothesis', 'H1'),
                              ('check', 'C1'), ('recommendation', 'recommendation')]:
                with self.subTest(field=field, kind=kind, cid=cid):
                    review = {'uses': [use('question', 'current_question')], 'reassessments': []}
                    review[field] = [use(kind, cid) if field == 'uses' else reassessment(kind, cid)]
                    with self.assertRaises(jsonschema.ValidationError):
                        jsonschema.validate(review, wire(True))

    def test_final_all_current_consumers_and_removed_prior_id_pass(self):
        frame = {'current_question': 'Question'}
        proposal = {'action': 'defer', 'recommendation': 'Read evidence', 'reason': 'Unresolved',
                    'research_loop': {'hypotheses': [{'id': 'H1'}], 'next_checks': [{'id': 'C1'}]}}
        review = {'uses': [use(kind, cid) for kind, cid in consumers(frame, proposal)],
                  'reassessments': [reassessment('hypothesis', 'old-H', 'removed')]}
        required = [{'consumer_kind': 'hypothesis', 'consumer_id': 'old-H',
                     'content_sha256': digest({'id': 'old-H'}),
                     'trigger': 'consumed_intent_changed', 'changed_intent_ids': ['I1']}]
        jsonschema.validate(review, wire(False))
        result = bind(review, snapshot(), consumers(frame, proposal), required)
        self.assertEqual(len(result['consumers']), 4)
        self.assertEqual(result['reassessments'][0]['outcome'], 'removed')

    def test_final_fixed_kind_and_id_pairs_apply_to_both_arrays(self):
        for field in ('uses', 'reassessments'):
            for kind, cid in [('question', 'current_question'), ('recommendation', 'recommendation'),
                              ('hypothesis', 'H1'), ('check', 'C1')]:
                with self.subTest(field=field, kind=kind):
                    item = use(kind, cid) if field == 'uses' else reassessment(kind, cid)
                    item_schema = wire(False)['properties'][field]['items']
                    jsonschema.validate(item, item_schema)
                    if kind in ('question', 'recommendation'):
                        for wrong in ('current_recommendation', 'H1', ''):
                            bad = {**item, 'consumer_id': wrong}
                            with self.assertRaises(jsonschema.ValidationError):
                                jsonschema.validate(bad, item_schema)

    def test_dynamic_id_coverage_and_duplicates_still_require_server_validation(self):
        frame, proposal = {'current_question': 'Question'}, {'research_loop': {'hypotheses': [{'id': 'H1'}]}}
        good = [use(kind, cid) for kind, cid in consumers(frame, proposal)]
        for variant in ('missing', 'foreign', 'duplicate'):
            with self.subTest(variant=variant):
                uses = copy.deepcopy(good)
                if variant == 'missing':
                    uses.pop()
                elif variant == 'foreign':
                    uses[-1]['consumer_id'] = 'foreign-H'
                else:
                    uses.append(copy.deepcopy(uses[-1]))
                review = {'uses': uses, 'reassessments': []}
                jsonschema.validate(review, wire(False))
                with self.assertRaises(ValueError):
                    bind(review, snapshot(), consumers(frame, proposal), [])

    def test_current_contract_is_strict_and_isolated_from_legacy_records(self):
        before = copy.deepcopy((SCHEMA, FRAME, CURRENT_FINAL_DECISION))
        for frame in (True, False):
            current = wire(frame)
            self.assertEqual(current, wire(frame))
            jsonschema.Draft202012Validator.check_schema(current)

            def check(node):
                if isinstance(node, dict):
                    self.assertNotIn('uniqueItems', node)
                    if node.get('type') == 'object':
                        self.assertFalse(node['additionalProperties'])
                        self.assertEqual(set(node['required']), set(node['properties']))
                    for child in node.values():
                        check(child)
                elif isinstance(node, list):
                    for child in node:
                        check(child)

            check(current)
            item = current['properties']['uses']['items']
            if not frame:
                item = item['anyOf'][0]
            item['properties']['consumer_id']['enum'][0] = 'mutated-local-copy'
            self.assertNotEqual(current, wire(frame))
        self.assertEqual(before, (SCHEMA, FRAME, CURRENT_FINAL_DECISION))
        self.assertNotIn('intent_review', FRAME['required'])
        self.assertNotIn('intent_review', CURRENT_FINAL_DECISION['required'])


if __name__ == '__main__':
    unittest.main()
