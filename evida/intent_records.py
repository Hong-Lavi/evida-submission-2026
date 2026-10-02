"""Preserve intent provenance when an editor changes only some fields."""
import copy


def override_ids(edit):
    if not edit:
        return set(), set()
    protected = edit.get('protected_ids', [r['id'] for r in edit['records']])
    return set(protected), set(edit.get('deleted_ids', []))


def field_edit(baseline, records, previous_edit, message_id):
    """The caller first checks that baseline is the current authoritative view."""
    old = {r['id']: r for r in baseline}
    seen, changed, normalized = set(), set(), []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('의도 항목 형식이 올바르지 않습니다.')
        rid, label, text = (record.get(k) for k in ('id', 'label', 'text'))
        if (not isinstance(rid, str) or not rid or rid in seen
                or not isinstance(label, str) or not label.strip()
                or not isinstance(text, str) or not text.strip()):
            raise ValueError('의도 항목의 고유 ID, 이름과 내용을 확인해 주세요.')
        seen.add(rid)
        prior = old.get(rid)
        if prior and prior['label'] == label and prior['text'] == text:
            normalized.append(copy.deepcopy(prior))
        else:
            changed.add(rid)
            normalized.append({'id': rid, 'label': label, 'text': text,
                               'origin': 'researcher', 'source_refs': [message_id]})
    removed = set(old) - seen
    protected, deleted = override_ids(previous_edit)
    protected.update(changed)
    protected.difference_update(removed)
    deleted.update(removed)
    deleted.difference_update(changed)
    return normalized, {'changed_ids': sorted(changed), 'removed_ids': sorted(removed),
                        'protected_ids': sorted(protected), 'deleted_ids': sorted(deleted)}
