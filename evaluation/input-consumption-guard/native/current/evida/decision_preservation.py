"""Opt-in literal preservation for an explicitly bounded decision revision.

This is a publication gate, never an output merger or a scientific assessment.
The reference must be the workspace's current published decision. Both its
stored bytes and the selected JSON fields are checked again at publication.
"""
import hashlib
import json
import re

from .store import dump


class DecisionPreservationError(ValueError):
    def __init__(self, report):
        self.report = report
        self.artifact_id = None
        super().__init__('명시한 판단 보존 범위를 벗어나 게시하지 않았습니다. '
                         '원 제안과 이전 판단을 확인해 주세요: ' + report['status'])


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def pointer_value(value, pointer):
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise ValueError('보호할 필드는 /로 시작하는 JSON pointer여야 합니다.')
    for raw in pointer[1:].split('/'):
        if re.search(r'~(?![01])', raw):
            raise ValueError('JSON pointer의 ~ 이스케이프가 잘못됐습니다.')
        part = raw.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', part):
                raise ValueError('배열 위치는 음수가 아닌 정수여야 합니다.')
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise TypeError('JSON pointer가 필드가 없는 값에 도달했습니다.')
    return value


def reject(status, **details):
    raise DecisionPreservationError({
        'status': status, 'proposal_modified': False, 'automatic_retry': False,
        'scientific_validation': False, **details})


def bind(store, wid, requirement, db=None):
    """Resolve a caller-selected reference and fields; never infer them from prose."""
    if requirement is None:
        return None
    keys = {'reference_decision_id', 'reference_sha256', 'protected_fields'}
    if not isinstance(requirement, dict) or set(requirement) != keys:
        reject('invalid_contract', reason='Exact reference ID, SHA256 and protected_fields are required.')
    aid, sha, fields = (requirement[k] for k in ('reference_decision_id', 'reference_sha256', 'protected_fields'))
    if (not isinstance(aid, str) or not aid or not isinstance(sha, str)
            or not re.fullmatch(r'[0-9a-f]{64}', sha)
            or not isinstance(fields, list) or not fields
            or any(not isinstance(p, str) for p in fields) or len(set(fields)) != len(fields)):
        reject('invalid_contract', reason='Reference or explicit nonduplicated fields are invalid.')
    if db is None:
        with store.connect() as connection:
            return bind(store, wid, requirement, connection)
    reference = db.execute('SELECT kind,sha256,content FROM artifacts WHERE workspace=? AND id=?',
                           (wid, aid)).fetchone()
    published = db.execute("SELECT body FROM events WHERE workspace=? AND kind='decision_published' "
                           'ORDER BY seq DESC LIMIT 1', (wid,)).fetchone()
    if (not reference or reference['kind'] != 'decision_proposal' or not published
            or json.loads(published['body']).get('receipt_id') != aid):
        reject('invalid_reference', reason='Reference is not this workspace\'s current published decision.',
               reference_decision_id=aid)
    if reference['sha256'] != sha or hashlib.sha256(reference['content']).hexdigest() != sha:
        reject('reference_hash_mismatch', reference_decision_id=aid)
    decision = json.loads(reference['content'])
    current = store.workspace(db, wid)
    if not current['decision'] or json.loads(current['decision']) != decision:
        reject('reference_state_mismatch', reference_decision_id=aid)
    try:
        protected = [{'pointer': p, 'value_sha256': digest(pointer_value(decision, p))} for p in fields]
    except (KeyError, IndexError, TypeError, ValueError):
        reject('invalid_protected_field', reference_decision_id=aid)
    return {'schema_version': 1, 'reference_decision_id': aid, 'reference_sha256': sha,
            'protected_fields': protected,
            'meaning': 'Explicit literal preservation only; not scientific validation. '
                'Keep the named fields of PREVIOUS_DECISION unchanged. '
                'A difference retains the previous decision and rejected draft, without merge or automatic retry.'}


def check(store, wid, requirement, proposal, db=None):
    contract = bind(store, wid, requirement, db)
    if contract is None:
        return None
    differences = []
    for field in contract['protected_fields']:
        try:
            actual = digest(pointer_value(proposal, field['pointer']))
        except (KeyError, IndexError, TypeError, ValueError):
            actual = None
        if actual != field['value_sha256']:
            differences.append({'pointer': field['pointer'], 'reference_sha256': field['value_sha256'],
                                'proposal_sha256': actual,
                                'relation': 'missing' if actual is None else 'literal_change'})
    if differences:
        reject('protected_fields_changed', contract=contract, differences=differences)
    return contract


def preserve_rejection(store, wid, rev, jid, value, requirement, error, receipts, protocol_id):
    """Retain the entire rejected bundle without touching the current judgment."""
    error.artifact_id = store.add_artifact(wid, '보존 범위를 벗어나 게시하지 않은 판단',
        'decision_scope_rejection', dump({'proposal': value, 'requirement': requirement,
                                        'review': error.report}).encode(),
        {'based_rev': rev, 'job_id': jid, 'published': False, 'scientific_validation': False,
         'model_receipts': receipts, 'protocol_id': protocol_id, 'automatic_retry': False}, bump=False)


def hold_followthrough(store, wid):
    """Preserve queued research requests for explicit review after a scope failure."""
    reason = '명시한 판단 보존 범위를 벗어났습니다. 원 제안과 이전 판단을 확인한 뒤 검토를 선택해 주세요.'
    with store.connect(True) as db:
        requests = db.execute("SELECT id FROM followthrough_requests WHERE workspace=? AND status='pending'",
                              (wid,)).fetchall()
        for request in requests:
            db.execute("UPDATE followthrough_requests SET status='needs_confirmation',error=? WHERE id=?",
                       (reason, request['id']))
            store.event(db,wid,'followthrough_attention',{'request_id':request['id'],'reason':reason,
                                                        'automatic_retry':False})
