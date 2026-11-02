"""Exact coordinator observations at a required entry; originals stay accessible.

This helper has no product/model imports, no source selection, no science verdict,
no execution, and no scheduler. Install after the returned_reading_entry25 wrapper.
"""
from copy import deepcopy

KEY = 'coordinator_supervision'


def add_coordinator_supervision(payload):
    entry = payload.get('entry') or {}
    if entry.get('current_request', {}).get('request_kind') != 'research':
        return deepcopy(payload)
    if KEY in payload:
        raise ValueError('Coordinator supervision view already exists')
    result = deepcopy(payload)
    contexts = result.get('contexts') or {}
    state_key, state = next(((k, v) for k, v in contexts.items()
                            if isinstance(v, dict) and 'STATE_REVISION' in v), (None, {}))
    document = {'meaning': 'Exact existing coordinator observations and retained link navigation, repeated here for required delivery. Original locations remain unchanged. Delivery is not reading, scientific support, or a command to stop or select a conclusion.',
                'original_locations': {}}
    for name in ('GOAL_SUPERVISION', 'ORCHESTRATION_PROGRESS'):
        if name in state:
            document[name] = deepcopy(state[name])
            document['original_locations'][name] = ['contexts', state_key, name]
    # CURRENT_CALL is a separate appended context, not necessarily the state object.
    for key, context in contexts.items():
        if isinstance(context, dict) and 'CURRENT_CALL' in context:
            document['CURRENT_CALL'] = deepcopy(context['CURRENT_CALL'])
            document['original_locations']['CURRENT_CALL'] = ['contexts', key, 'CURRENT_CALL']
    navigation = []
    # The bridge already lists the latest executed function-return addresses.
    # Inspect only their exact decoded result dictionaries, not arbitrary source text.
    decoded = result.get('decoded_tool_returns') or {}
    for handle in result['entry'].get('LAST_RETURNED_PRODUCT_TOOLS', []):
        path = handle.get('decoded_document_path')
        if not isinstance(path, list) or len(path) != 2 or path[0] != 'decoded_tool_returns':
            continue
        answer = decoded.get(path[1])
        body = answer.get('result') if isinstance(answer, dict) else None
        if isinstance(body, dict) and isinstance(body.get('source_navigation'), dict):
            navigation.append({'artifact_id': answer.get('artifact_id'), 'call_id': handle.get('call_id'),
                               'source_navigation': deepcopy(body['source_navigation']),
                               'original_location': [*path, 'result', 'source_navigation']})
    restored = state.get('RESTORED_READING') or {}
    content = restored.get('content') if isinstance(restored, dict) else None
    body = content.get('result') if isinstance(content, dict) else None
    if not navigation and isinstance(body, dict) and isinstance(body.get('source_navigation'), dict):
        navigation.append({'artifact_id': content.get('artifact_id'), 'reading_id': restored.get('reading_id'),
                           'source_navigation': deepcopy(body['source_navigation']),
                           'original_location': ['contexts', state_key, 'RESTORED_READING', 'content', 'result', 'source_navigation']})
    if navigation:
        document['latest_returned_source_navigation'] = navigation
    if len(document) == 2:
        return result
    result[KEY] = document
    result['entry']['coordinator_supervision_location'] = [KEY]
    result['entry']['coordinator_supervision_note'] = ('Read the required coordinator_supervision document before choosing this research action. It repeats existing supervision and latest retained link addresses exactly; it does not authorise a scientific conclusion or override current tool_choice.')
    return result


def required_paths_with_supervision(payload, original_required_paths):
    paths = list(original_required_paths(payload))
    if KEY in payload and [KEY] not in paths:
        paths.append([KEY])
    return paths


def catalog_paths_with_supervision(payload, original_catalog_paths):
    paths = list(original_catalog_paths(payload))
    if KEY in payload and [KEY] not in paths:
        paths.append([KEY])
    return paths
