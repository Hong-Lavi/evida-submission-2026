"""Expose saved public research notes, never hidden provider reasoning."""
import json

import jsonschema

from .contracts import RESEARCH_NOTES


def view(store, wid, state):
    planner = next((j for j in reversed(state['jobs'])
                    if j['kind'] == 'planner' and j['based_rev'] == state['rev']), None)
    if not planner or planner['status'] not in ('queued', 'running'):
        return None
    notes = [a for a in state['artifacts'] if a['kind'] == 'research_notes'
             and a['meta'].get('job_id') == planner['id']
             and a['meta'].get('based_rev') == state['rev']]
    if not notes:
        return None
    item = notes[-1]
    try:
        content = json.loads(store.artifact(wid, item['id'])['content'])
        jsonschema.validate(content, RESEARCH_NOTES)
    except (ValueError, KeyError, jsonschema.ValidationError):
        return {'status': 'unavailable', 'message': '현재 메모의 원자료 확인이 필요합니다.'}
    call_id = item['meta'].get('model_call_id')
    returned = [a for a in state['artifacts'] if call_id and a['kind'] == 'tool_reading'
                and a['meta'].get('job_id') == planner['id']
                and a['meta'].get('call_id') == call_id]
    return {'status': 'saved_public_notes', 'job_id': planner['id'],
            'based_rev': state['rev'], 'artifact_id': item['id'],
            'created': item['created'], 'notes': content,
            'following_operation_returned': bool(returned),
            'returned_artifact_ids': [a['id'] for a in returned],
            'meaning': 'Saved provisional findings and check direction before an operation; not final validation or a claim about current hidden reasoning.'}
