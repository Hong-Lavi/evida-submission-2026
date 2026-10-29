"""Routing regression with a real operation fragment and a tiny synthetic Store.

The operation fragment is copied from the preserved ALS04 model response. All
other decision content is explicitly synthetic test scaffolding. No biology,
network, model, full audit database, or installed science runtime is needed.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from evida.finalization import prepare
from evida.model_context import model_json
from evida.runner import Runner
from evida.store import Store, dump


FRAGMENT = json.loads((Path(__file__).parent / 'fixtures/als04_operation_fragment.json').read_text())
CHECK = FRAGMENT['check_id']
EXPECTED = {CHECK: 'external_observation'}


def synthetic_decision(rev):
    return {'based_on_state_rev': rev, 'intent_records': [], 'action': 'maintain',
        'recommendation': 'Synthetic routing-test decision; not scientific evidence.',
        'reason': 'Test whether the explicitly requested operation type is applied.',
        'evidence_refs': [], 'alternatives': [], 'changed': [], 'preserved': [],
        'unknowns': [], 'next_actions': [], 'questions': [],
        'research_loop': {
            'hypotheses': [{'id': 'synthetic-hypothesis', 'statement': 'Synthetic hypothesis fixture.',
                'expected_observation': 'Synthetic expected observation.', 'alternatives': [],
                'assessment': 'inconclusive', 'rationale': 'Fixture only.', 'evidence': []}],
            'next_checks': [{'id': CHECK, 'question': 'Synthetic check around an actual operation fragment.',
                'purpose': 'Exercise operation routing only.', 'hypothesis_ids': ['synthetic-hypothesis'],
                'possible_outcomes': [{'observation': 'Synthetic result.', 'implication': 'Synthetic follow-up.'}],
                'outcome_links': [], 'operation': deepcopy(FRAGMENT['operation'])}],
            'revision_rationale': 'Synthetic test scaffold; no empirical result.'}}


def synthetic_bundle(decision):
    """Current transport shape; this routing fixture authors no science review."""
    return {'decision': decision, 'discovery_review': None, 'judgment_context': None,
            'hypothesis_review': {'schema_version': '2', 'causal_steps': [], 'observations': [],
                'scope': {field: [{key: row['id'], 'status': 'not_reviewed',
                                  'reason': 'Synthetic routing fixture; this item is not scientifically assessed.'}
                                 for row in decision['research_loop'][items]]
                          for field, key, items in (('hypotheses', 'hypothesis_id', 'hypotheses'),
                                                    ('checks', 'check_id', 'next_checks'))}}}


@pytest.fixture
def case(tmp_path):
    store = Store(tmp_path / 'tiny-synthetic.sqlite3')
    state = store.create('Synthetic operation-correction regression')
    wid, rev = state['id'], state['rev']
    decision = synthetic_decision(rev)
    # Minimal test setup. This never publishes a model answer or starts a job.
    with store.connect(True) as db:
        db.execute('UPDATE workspaces SET decision=?,decision_rev=? WHERE id=?', (dump(decision), rev, wid))
    bundle = synthetic_bundle(decision)
    return store, wid, rev, bundle


def test_saved_actual_operation_conflicts_with_explicit_correction(case):
    store, wid, rev, bundle = case
    assert bundle['decision']['research_loop']['next_checks'][0]['operation']['kind'] == 'unconnected_method'
    with pytest.raises(ValueError, match=CHECK):
        prepare(store, wid, rev, bundle, True, expected_operations=EXPECTED)


def test_unrequested_existing_operation_remains_valid(case):
    store, wid, rev, bundle = case
    answer, _ = prepare(store, wid, rev, bundle, True)
    assert answer['research_loop']['next_checks'][0]['operation'] == FRAGMENT['operation']


def test_satisfying_requested_kind_preserves_scientific_fields(case):
    store, wid, rev, bundle = case
    old = deepcopy(bundle)
    check = bundle['decision']['research_loop']['next_checks'][0]
    check['operation'] = {'kind': 'external_observation', 'request': 'Synthetic future observation request.', 'grounded_in': []}
    frozen = deepcopy(bundle)
    answer, _ = prepare(store, wid, rev, bundle, True, expected_operations=EXPECTED)
    assert answer['research_loop']['hypotheses'] == old['decision']['research_loop']['hypotheses']
    assert bundle == frozen


def test_requested_check_cannot_silently_disappear(case):
    store, wid, rev, bundle = case
    bundle['decision']['research_loop']['next_checks'] = []
    with pytest.raises(ValueError, match=CHECK):
        prepare(store, wid, rev, bundle, True, expected_operations=EXPECTED)


def test_unknown_existing_check_is_rejected(case):
    store, wid, rev, bundle = case
    with pytest.raises(ValueError, match='존재'):
        prepare(store, wid, rev, bundle, True, expected_operations={'unknown-check': 'external_observation'})


def test_unknown_operation_kind_is_rejected(case):
    store, wid, rev, bundle = case
    with pytest.raises(ValueError, match='유형'):
        prepare(store, wid, rev, bundle, True, expected_operations={CHECK: 'invented-kind'})


def test_rejection_preserves_original_and_adds_no_artifact(case):
    store, wid, rev, bundle = case
    before = deepcopy(bundle)
    with pytest.raises(ValueError):
        prepare(store, wid, rev, bundle, True, expected_operations=EXPECTED)
    assert bundle == before
    assert store.snapshot(wid)['artifacts'] == []


def test_request_reaches_actual_model_context_projection(case, tmp_path):
    store, wid, rev, _ = case
    jid = store.enqueue(wid, rev, 'planner', {'requested_check_operations': EXPECTED})
    runner = Runner.__new__(Runner)
    runner.root = Path(__file__).resolve().parents[1]
    runner.store = store
    runner.context_recent_views = 4
    context = runner.model_context(wid, rev, True, current_job=jid, force_full=True)
    assert context['REQUESTED_CHECK_OPERATIONS']['by_check_id'] == EXPECTED
    assert 'REQUESTED_CHECK_OPERATIONS' in model_json(context)
    assert store.snapshot(wid)['jobs'][0]['status'] == 'queued'


class OfflineGateway:
    def status(self):
        return {'available': True, 'message': 'Offline mock; no request transport.'}
    def approved_models(self):
        return ['gpt-6-sol']


class RecordingPool:
    def __init__(self):
        self.submissions = []
    def submit(self, function, *arguments):
        self.submissions.append((function.__name__, arguments))
        # Deliberately do not execute the submitted planner; API calls stay zero.


def start_runner(store, tmp_path):
    runner = Runner.__new__(Runner)
    runner.root = tmp_path
    runner.store = store
    runner.gateway = OfflineGateway()
    runner.pool = RecordingPool()
    return runner


def test_real_start_accepts_and_preserves_explicit_correction(case, tmp_path):
    store, wid, rev, _ = case
    runner = start_runner(store, tmp_path)
    arguments = {'model': 'gpt-6-sol', 'synthesis_only': True, 'source_views': [],
                 'requested_check_operations': EXPECTED}
    jid = runner.start(wid, rev, 'planner', arguments)
    job = next(j for j in store.snapshot(wid)['jobs'] if j['id'] == jid)
    assert job['request'] == arguments
    assert job['status'] == 'queued'
    assert runner.pool.submissions == [('run_planner', (jid,))]


@pytest.mark.parametrize('requirement', [
    {'unknown-check': 'external_observation'}, {CHECK: 'invented-kind'}, ['invalid-shape']])
def test_real_start_rejects_invalid_contract_before_enqueue(case, tmp_path, requirement):
    store, wid, rev, _ = case
    runner = start_runner(store, tmp_path)
    with pytest.raises(ValueError):
        runner.start(wid, rev, 'planner', {'model': 'gpt-6-sol', 'synthesis_only': True,
                     'requested_check_operations': requirement})
    assert store.snapshot(wid)['jobs'] == []
    assert runner.pool.submissions == []
