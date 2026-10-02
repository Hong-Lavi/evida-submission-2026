"""Read published evidence relationships without promoting past claims to truth.

The current and historical decisions stay immutable. Literal differences are
navigation aids, not inferences about reading, retraction or claim equivalence.
"""
from copy import deepcopy
import json

from .research_loop import decision_id


MEANING = ('이전 판단에 기록된 주장·근거·조건입니다. 현재 목록에 없다는 사실만으로 '
           '반박·철회·미열람·미재평가를 판정하지 않습니다. 같은 ID나 문구도 적용 조건의 '
           '동일성을 보장하지 않습니다. 현재 근거로 자동 승계하지 않습니다.')


def lineage(state):
    published = {e['body']['receipt_id']: e for e in state['events']
                 if e['kind'] == 'decision_published'}
    comparisons = {e['body']['receipt_id']: e['body'] for e in state['events']
                   if e['kind'] == 'hypothesis_wording_compared'}
    cursor, rows, seen, gap = decision_id(state), [], set(), None
    while cursor:
        if cursor in seen or cursor not in published:
            gap = {'decision_id': cursor, 'reason': 'cycle_or_unpublished_reference'}
            break
        seen.add(cursor)
        event = published[cursor]
        rows.append({'decision_id': cursor, 'state_revision': event['body']['state_rev'],
                     'event_sequence': event['seq'], 'created': event['created']})
        comparison = comparisons.get(cursor)
        if comparison is None:
            gap = {'decision_id': cursor, 'reason': 'recorded_predecessor_unavailable'}
            break
        reference = comparison.get('reference', {})
        if reference.get('kind') != 'previous_published_decision':
            break
        previous = reference.get('decision_id')
        if not previous:
            gap = {'decision_id': cursor, 'reason': 'recorded_predecessor_unavailable'}
            break
        cursor = previous
    return rows, gap


def edges(hypothesis):
    if hypothesis is None:
        return []
    rows = [{'part_id': '', 'part_statement': None, 'edge': deepcopy(e)}
            for e in hypothesis.get('evidence', [])]
    for part in hypothesis.get('assessment_scope', {}).get('parts', []):
        rows.extend({'part_id': part['id'], 'part_statement': part['statement'],
                     'edge': deepcopy(e)} for e in part.get('evidence', []))
    for explanation in hypothesis.get('conditional_alternatives', []):
        rows.extend({'part_id': '', 'part_statement': None,
                     'explanation_id': explanation['id'], 'explanation_statement': explanation['statement'],
                     'explanation_conditions': deepcopy(explanation['conditions']),
                     'edge': deepcopy(e)} for e in explanation.get('evidence', []))
    return rows


def compare_edges(previous, current):
    """No scientific interpretation; duplicates and separate part bindings survive."""
    current_rows = edges(current)
    result = []
    for row in edges(previous):
        edge = row['edge']
        matches = [r for r in current_rows if r['part_id'] == row['part_id']
                   and r.get('explanation_id') == row.get('explanation_id')
                   and r['edge']['source_type'] == edge['source_type']
                   and r['edge']['source_id'] == edge['source_id']]
        exact = any(r == row for r in matches)
        result.append({**row, 'comparison': 'same_recorded_link' if exact else
                       'recorded_link_changed' if matches else 'not_in_current_list',
                       'current_links': matches,
                       'disposition': 'not_inferred', 'automatically_reasserted': False})
    return result


def view(store, wid, hypothesis_id, offset=0, limit=4):
    if not isinstance(hypothesis_id, str) or not hypothesis_id:
        raise ValueError('확인할 가설 ID를 지정해 주세요.')
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError('이력 조회 범위를 확인해 주세요.')
    state = store.snapshot(wid)
    ids, gap = lineage(state)
    current_id = decision_id(state)
    current_status, current = 'no_published_decision', None
    if current_id:
        try:
            proposal = json.loads(store.artifact(wid, current_id)['content'])
            current = next((h for h in proposal.get('research_loop', {}).get('hypotheses', [])
                            if h['id'] == hypothesis_id), None)
            current_status = 'available'
        except (KeyError, ValueError):
            current_status = 'unavailable_or_integrity_failure'
    rows = []
    for entry in ids[offset:offset + limit]:
        row = {**entry, 'is_current': entry['decision_id'] == current_id}
        try:
            artifact = store.artifact(wid, entry['decision_id'])
            proposal = json.loads(artifact['content'])
            hypothesis = next((h for h in proposal.get('research_loop', {}).get('hypotheses', [])
                               if h['id'] == hypothesis_id), None)
            comparison = ('no_current_hypothesis' if current is None else
                          'not_in_this_decision' if hypothesis is None else
                          'same_literal_claim' if all(current.get(k) == hypothesis.get(k)
                              for k in ('statement', 'expected_observation')) else 'literal_claim_changed')
            row.update(content_status='available', sha256=artifact['sha256'],
                       hypothesis=hypothesis, claim_comparison=comparison,
                       evidence_comparison=compare_edges(hypothesis, current),
                       context_artifact_id=artifact['meta'].get('finalization_records', {}).get('judgment_context'),
                       comparison_is_scientific_equivalence=False)
        except (KeyError, ValueError):
            row.update(content_status='unavailable_or_integrity_failure', hypothesis=None,
                       evidence_comparison=[], claim_comparison='unknown')
        rows.append(row)
    return {'semantic_type': 'published_evidence_relationship_history',
            'hypothesis_id': hypothesis_id, 'current_decision_id': current_id,
            'current_content_status': current_status, 'current_hypothesis': current,
            'total_rows': len(ids), 'offset': offset, 'has_more': offset + len(rows) < len(ids),
            'rows': rows, 'lineage_gap': gap, 'meaning': MEANING,
            'current_claim_or_assessment_modified': False,
            'source_body_reading': 'Exact links preserved; source bodies require separate original-artifact reading.'}
