"""Offline regression for exact, delivered message aliases in explanations.

Synthetic Store and explicit transport fixture only. Message citations remain
research history; neither resolving an ID nor publishing an explanation verifies
scientific claims. The original model response and stored message are retained.
"""
from copy import deepcopy
import json

import pytest

import test_live_interaction as live
from evida.interaction import enqueue_explanation, resolve_snapshot_citations, run_explanation, saved_context


@pytest.fixture
def case():
    fixture = live.InteractionTests()
    fixture.setUp()
    try:
        fixture.store.command(fixture.wid, 1, 'synthetic-message', {
            'kind': 'message', 'text': 'Synthetic researcher note; not an experimental result.',
            'synthetic': True})
        yield fixture
    finally:
        fixture.tearDown()


def message(context):
    return context['ORIGINAL_MESSAGES'][-1]


def response(case, evidence):
    return json.loads(case.final(evidence)[0]['content'][0]['text'])


def test_delivered_message_resolves_exactly_without_rewriting_model_or_source(case):
    context = saved_context(case.store, case.wid)
    event = message(context)
    mid = event['body']['message_id']
    original = response(case, [mid, case.notes, case.source])
    original['event_refs'] = [event['seq']]
    frozen_context, frozen_output = deepcopy(context), deepcopy(original)
    resolved = resolve_snapshot_citations(context, original, {case.notes},
                                          {case.source: [case.notes]}, case.wid)
    assert resolved['evidence_refs'] == [case.notes, case.source]
    assert resolved['event_refs'] == [event['seq']]
    assert resolved['model_evidence_refs'] == [mid, case.notes, case.source]
    assert resolved['model_event_refs'] == [event['seq']]
    assert resolved['event_citations'] == [event]
    assert resolved['reference_resolution'] == [{
        'original_reference': mid, 'original_field': 'evidence_refs', 'event_seq': event['seq'],
        'delivery': 'supplied_in_this_explanation', 'scientific_claim_verified': False}]
    assert context == frozen_context and original == frozen_output
    resolved['event_citations'][0]['body']['text'] = 'Mutating a result must not rewrite the source.'
    assert context == frozen_context


def test_message_alias_does_not_authorize_a_catalog_only_artifact(case):
    unread = case.store.add_artifact(case.wid, 'Synthetic unread source', 'literature', b'{}', {}, bump=False)
    context = saved_context(case.store, case.wid)
    assert unread in {row['artifact_id'] for row in context['SOURCE_CATALOG']}
    output = response(case, [message(context)['body']['message_id'], unread])
    with pytest.raises(ValueError, match='실제 제공하지 않은'):
        resolve_snapshot_citations(context, output, {case.notes}, {case.source: [case.notes]}, case.wid)


def test_later_and_other_workspace_messages_are_not_snapshot_evidence(case):
    original = saved_context(case.store, case.wid)
    case.store.command(case.wid, 2, 'later-message', {
        'kind': 'message', 'text': 'Synthetic later condition.', 'synthetic': True})
    later = message(saved_context(case.store, case.wid))
    foreign_wid = case.store.create('Other synthetic study')['id']
    case.store.command(foreign_wid, 1, 'foreign-message', {
        'kind': 'message', 'text': 'Synthetic other-study condition.', 'synthetic': True})
    foreign = message(saved_context(case.store, foreign_wid))
    for event in (later, foreign):
        context = deepcopy(original)
        context['ORIGINAL_MESSAGES'].append(event)
        if event is foreign:
            # Isolate workspace identity from the independent future-cursor gate.
            context['SNAPSHOT_EVENT_CURSOR'] = foreign['seq']
        for refs, seqs in (([event['body']['message_id']], []), ([], [event['seq']])):
            output = response(case, refs)
            output['event_refs'] = seqs
            with pytest.raises(ValueError, match='실제 제공하지 않은'):
                resolve_snapshot_citations(context, output, set(), {}, case.wid)
    assert saved_context(case.store, case.wid)['ORIGINAL_MESSAGES'][0] == message(original)


def test_ambiguous_message_id_cannot_choose_an_event(case):
    context = saved_context(case.store, case.wid)
    event = message(context)
    duplicate = deepcopy(event)
    duplicate['seq'] += 1
    duplicate['body']['text'] = 'Synthetic conflicting record with the same message ID.'
    context['SNAPSHOT_EVENT_CURSOR'] = duplicate['seq']
    context['ORIGINAL_MESSAGES'].append(duplicate)
    output = response(case, [event['body']['message_id']])
    output['event_refs'] = [event['seq']]
    with pytest.raises(ValueError, match='실제 제공하지 않은'):
        resolve_snapshot_citations(context, output, set(), {}, case.wid)


def test_run_explanation_publishes_resolved_copy_and_retains_original_records(case):
    before = case.store.snapshot(case.wid)
    event = message(saved_context(case.store, case.wid))
    mid = event['body']['message_id']
    source_bytes = {aid: case.store.artifact(case.wid, aid)['content'] for aid in (case.source, case.notes)}
    original_output = case.final([mid, case.notes, case.source])
    raw_answer = json.loads(original_output[0]['content'][0]['text'])
    history = case.gateway([deepcopy(original_output)])
    request, created = enqueue_explanation(case.store, case.wid, before['rev'], 'explanation', 'Explain the saved note.')
    assert created
    run_explanation(case.runner, request['job_id'])
    after = case.store.snapshot(case.wid)
    job = next(job for job in after['jobs'] if job['id'] == request['job_id'])
    assert job['status'] == 'succeeded' and len(history) == 1
    answer = json.loads(case.store.artifact(case.wid, job['output_id'])['content'])
    assert answer['answer'] == raw_answer['answer']
    assert answer['model_evidence_refs'] == [mid, case.notes, case.source]
    assert answer['evidence_refs'] == [case.notes, case.source]
    assert answer['event_refs'] == [event['seq']] and answer['event_citations'] == [event]
    assert answer['condition_applied'] is False
    detail = next(item for item in answer['citation_provenance'] if item['artifact_id'] == case.source)
    assert detail['delivery'] == 'cited_in_saved_snapshot_not_reread'
    assert detail['snapshot_parents'] == [case.notes] and detail['scientific_claim_verified'] is False
    raw_outputs = [a for a in after['artifacts'] if a['kind'] == 'explanation_model_output']
    assert len(raw_outputs) == 1
    assert json.loads(case.store.artifact(case.wid, raw_outputs[0]['id'])['content']) == original_output
    assert after['events'][:len(before['events'])] == before['events']
    assert next(e for e in after['events'] if e['seq'] == event['seq']) == event
    assert {key: after[key] for key in ('rev', 'intent', 'decision', 'decision_rev', 'followthrough_requests')} == {
        key: before[key] for key in ('rev', 'intent', 'decision', 'decision_rev', 'followthrough_requests')}
    assert {aid: case.store.artifact(case.wid, aid)['content'] for aid in source_bytes} == source_bytes
