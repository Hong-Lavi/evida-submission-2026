"""Resolve exact delivery aliases while retaining the authored scientific review."""
from __future__ import annotations

import copy
import json


def resolve(store, wid, authored, loop):
    """Return a copy and a ledger; never infer a scientific statement or fuzzy match."""
    from .hypothesis_review import check_anchor, _pointer

    value = copy.deepcopy(authored)
    ledger = []
    hypotheses = {h['id']: h for h in loop['hypotheses']}
    for step in value['causal_steps']:
        hypothesis = hypotheses.get(step['hypothesis_id'])
        parts = (hypothesis.get('assessment_scope') or {}).get('parts', []) if hypothesis else None
        if step['part_id'] == 'whole' and parts == []:
            step['part_id'] = ''
            ledger.append({'kind': 'whole_hypothesis_reference', 'step_id': step['id'],
                           'hypothesis_id': step['hypothesis_id'], 'submitted_part_id': 'whole',
                           'resolved_part_id': '', 'reason': 'Whole hypothesis has no named parts.'})
        for group in step['evidence_groups']:
            for index, anchor in enumerate(group['anchors']):
                path = anchor['path']
                if not path.startswith('/result/rows/'):
                    continue
                original = check_anchor(store, wid, anchor)
                if original.get('reason') != 'path_not_found':
                    continue
                try:
                    artifact = store.artifact(wid, anchor['artifact_id'])
                    document = json.loads(artifact['content'])
                except (KeyError, ValueError, UnicodeError):
                    continue
                # A real stored result member always wins over any delivery alias.
                if not isinstance(document, dict) or 'result' in document or not isinstance(document.get('rows'), list):
                    continue
                canonical = {**anchor, 'path': path[len('/result'):]}
                checked = check_anchor(store, wid, canonical)
                if checked['status'] != 'verified':
                    continue
                pieces = canonical['path'].split('/', 3)
                suffix = '/' + pieces[3] if len(pieces) == 4 else ''
                matching_rows = []
                for row_index in range(len(document['rows'])):
                    try:
                        text = _pointer(document, f'/rows/{row_index}' + suffix)
                    except ValueError:
                        continue
                    if isinstance(text, str) and anchor['quote'] in text:
                        matching_rows.append(row_index)
                # A paginated view may use relative row indexes. Repeated text
                # cannot establish which original row its index meant.
                if matching_rows != [int(pieces[2])]:
                    continue
                anchor['path'] = canonical['path']
                ledger.append({'kind': 'provided_view_anchor_reference', 'step_id': step['id'],
                               'group_id': group['id'], 'anchor_index': index,
                               'artifact_id': anchor['artifact_id'], 'source_sha256': checked['source_sha256'],
                               'submitted_path': path, 'resolved_path': canonical['path'],
                               'match': checked['match'], 'quote_unchanged': True,
                               'matching_rows_at_field': matching_rows,
                               'source_rows_checked': len(document['rows']),
                               'reason': 'The result/rows delivery wrapper points to the exact stored rows value.'})
    return value, ledger
