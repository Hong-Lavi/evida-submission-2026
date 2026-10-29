"""Explicitly unreviewed metadata for synthetic planner transport fixtures.

These helpers let transport tests exercise the current response contract. They
make no biological judgment or inferred intent link; dedicated review tests
exercise those semantics independently.
"""
import copy
import json

from evida.intent_dependencies import view as intent_view


def intent_review(store, wid, consumers, *, question_only=False):
    return {
        'uses': [{'consumer_kind': kind, 'consumer_id': cid, 'intent_ids': [],
                  'reason': 'Intent linkage is unknown in this synthetic transport fixture.'}
                 for kind, cid in consumers],
        'reassessments': [{
            'consumer_kind': row['consumer_kind'], 'consumer_id': row['consumer_id'],
            'outcome': 'unknown', 'reason': 'This fixture tests transport, not intent impact.'}
            for row in intent_view(store, wid)['required_reassessments']
            if not question_only or row['consumer_kind'] == 'question'],
    }



def _active_reasoning_core(store, wid):
    """Only adapt fresh synthetic runs; historical helpers stay unchanged."""
    protocols = [a for a in store.snapshot(wid)['artifacts'] if a['kind'] == 'protocol_snapshot']
    if not protocols:
        return None
    return json.loads(store.artifact(wid, protocols[-1]['id'])['content']).get('reasoning_core')


def synthetic_reasoning_design(core):
    """A proposed interface contrast, never a biological measurement/result."""
    used = ([{'id': core['cards'][0]['id'],
              'application': 'Synthetic transport fixture: exercise the declared comparison fields only.'}]
            if core['cards_enabled'] and core['cards'] else [])
    return {
        'version': 'reasoning-design-v1',
        'H1': 'Synthetic interface assumption: changing fixture input changes fixture readout.',
        'H0': 'Synthetic interface assumption: fixture readout remains unchanged.',
        'hypothesis_level': 'condition', 'specimen': 'Synthetic interface fixture; no biological specimen',
        'factors': [{'id': 'input', 'name': 'Synthetic input'}, {'id': 'batch', 'name': 'Fixture batch'}],
        'changed_variable_id': 'input',
        'arms': [{'id': 'a', 'role': 'intervention', 'levels': [
            {'factor_id': 'input', 'value': 'changed synthetic value'},
            {'factor_id': 'batch', 'value': 'same fixture'}]},
                 {'id': 'b', 'role': 'reference', 'levels': [
            {'factor_id': 'input', 'value': 'reference synthetic value'},
            {'factor_id': 'batch', 'value': 'same fixture'}]}],
        'controls': [{'id': 'reference', 'role': 'reference', 'description': 'Synthetic reference',
                      'validity_criterion': 'Fixture baseline available'},
                     {'id': 'assay', 'role': 'assay', 'description': 'Synthetic readout control',
                      'validity_criterion': 'Fixture readout available'}],
        'readout': {'name': 'Synthetic readout', 'contrast': 'changed minus reference',
                    'unit': 'fixture units', 'timepoint': 'synthetic fixed time'},
        'predictions': {'H1': {'kind': 'direction', 'value': 'increase'},
                        'H0': {'kind': 'direction', 'value': 'no_change'}},
        'prediction_basis': {'origin': 'proposed', 'source_ids': [],
                             'rationale': 'Synthetic schema assumption; not a measured result'},
        'refuting_result': {'prediction': 'H0', 'description': 'Synthetic readout unchanged with valid controls',
                            'valid_control_ids': ['reference', 'assay']},
        'experiment_failure': {'invalid_control_ids': ['reference', 'assay'],
                               'description': 'A synthetic fixture control is invalid'},
        'next_actions': {outcome: 'Inspect the synthetic fixture; no scientific action is inferred.'
                         for outcome in ('supports', 'refutes', 'inconclusive', 'experiment_failure')},
        'unresolved_requirements': ['No real experiment is specified; noise and effect-size criteria are unresolved.'],
        'interpretation_limits': ['Synthetic transport/schema test, not biological validation'],
        'cards_used': used,
    }


def _adapt_reasoning_hypotheses(hypotheses, core):
    if not hypotheses:
        hypotheses.append({'id': 'synthetic-reasoning-h1',
            'statement': 'Synthetic interface comparison only.',
            'expected_observation': 'Proposed synthetic contrast; no observed result.',
            'alternatives': ['Synthetic unchanged readout'], 'assessment': 'proposed',
            'rationale': 'Exercises the current planner transport schema.', 'evidence': []})
    for hypothesis in hypotheses:
        # Keep deliberately authored/invalid designs intact for rejection tests.
        hypothesis.setdefault('reasoning_design', synthetic_reasoning_design(core))


def current_frame(store, wid, value):
    frame = copy.deepcopy(value)
    core = _active_reasoning_core(store, wid)
    if core is not None:
        _adapt_reasoning_hypotheses(frame['hypotheses'], core)
    frame['intent_review'] = intent_review(
        store, wid, [('question', 'current_question')], question_only=True)
    return frame


def current_final(store, wid, decision, *, discovery_review=None, judgment_context=None):
    decision = copy.deepcopy(decision)
    loop = decision['research_loop']
    core = _active_reasoning_core(store, wid)
    if core is not None:
        _adapt_reasoning_hypotheses(loop['hypotheses'], core)
    for check in loop['next_checks']:
        check.setdefault('measurement_selection_id', None)
        if core is not None:
            check.setdefault('design_hypothesis_id', check['hypothesis_ids'][0]
                if check['operation']['kind'] == 'external_observation' and check['hypothesis_ids'] else None)
    consumers = [('question', 'current_question'), ('recommendation', 'recommendation')]
    consumers += [('hypothesis', h['id']) for h in loop['hypotheses']]
    consumers += [('check', c['id']) for c in loop['next_checks']]
    return {
        'decision': decision, 'discovery_review': discovery_review,
        'judgment_context': judgment_context,
        'intent_review': intent_review(store, wid, consumers),
        'reassessment_review_ids': [],
        'hypothesis_review': {
            'schema_version': '2', 'causal_steps': [], 'observations': [],
            'scope': {
                'hypotheses': [{'hypothesis_id': h['id'], 'status': 'not_reviewed',
                               'reason': 'Synthetic transport does not assess causality.'}
                              for h in loop['hypotheses']],
                'checks': [{'check_id': c['id'], 'status': 'not_reviewed',
                           'reason': 'Synthetic transport does not assess predictions.'}
                          for c in loop['next_checks']],
            },
        },
    }
