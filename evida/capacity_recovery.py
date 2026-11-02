"""Same-route recovery of positively identified transient model capacity failures."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import time
from pathlib import Path

from .gateway import GatewayError
from .store import dump, Conflict


class RecoveryCancelled(Exception):
    """A terminal job must stay terminal when a waiting worker wakes."""


def check_current(runner, job):
    with runner.store.connect() as db:
        current = db.execute('SELECT status FROM jobs WHERE id=?', (job['id'],)).fetchone()
        workspace = runner.store.workspace(db, job['workspace'])
    if current is None or current['status'] not in ('queued', 'running'):
        raise RecoveryCancelled()
    if workspace['rev'] != job['based_rev']:
        raise Conflict('연구 조건이 바뀌어 이전 모델 요청의 재시도를 멈췄습니다. 저장된 결과는 보존됩니다.')


def is_capacity(exc):
    receipt = exc.receipt or {}
    failure = receipt.get('provider_failure') or {}
    evidence = failure.get('failure_evidence') or {}
    return (exc.status == 'provider_capacity' and receipt.get('status') == 'FAILED'
            and receipt.get('route', '').startswith('subscription:')
            and failure.get('retryable') is True
            and evidence.get('provider_capacity') is True
            and evidence.get('source') == 'plaintext_stderr')


def request_with_recovery(runner, job, payload, model, protocol_id, *, sleep=time.sleep):
    """Keep all attempts; wait without imposing a total-call or response-time cap."""
    attempt = 0
    while True:
        check_current(runner, job)
        try:
            if attempt:
                with runner.store.connect(True) as db:
                    runner.store.event(db, job['workspace'], 'model_retry_resumed',
                                       {'job_id': job['id'], 'failed_attempts': attempt, 'model': model})
            result = runner.gateway.request(payload, model=model)
            try:
                check_current(runner, job)
            except (RecoveryCancelled, Conflict):
                runner.store.add_artifact(job['workspace'], '중단 후 도착한 모델 응답 기록',
                    'model_receipt', dump(result[1]).encode(),
                    {'based_rev': job['based_rev'], 'job_id': job['id'],
                     'protocol_id': protocol_id, 'model_route': model,
                     'dispatch_suppressed': True}, bump=False)
                runner.store.add_artifact(job['workspace'], '중단 후 도착한 제안 · 실행하지 않음',
                    'decision_proposal', dump({'output': [x for x in result[0].get('output', [])
                        if x.get('type') != 'reasoning'], 'dispatch_suppressed': True}).encode(),
                    {'based_rev': job['based_rev'], 'job_id': job['id']}, bump=False)
                raise
            return result
        except GatewayError as exc:
            if not is_capacity(exc):
                raise
            attempt += 1
            delay = (30, 60, 120, 300)[min(attempt - 1, 3)]
            receipt_id = runner.store.add_artifact(job['workspace'], '모델 혼잡 · 재개 대기 기록',
                'model_receipt', dump(exc.receipt).encode(),
                {'based_rev': job['based_rev'], 'job_id': job['id'], 'protocol_id': protocol_id,
                 'model_route': model, 'transient_retry_attempt': attempt}, bump=False)
            with runner.store.connect(True) as db:
                runner.store.event(db, job['workspace'], 'model_retry_waiting', {
                    'job_id': job['id'], 'model': model, 'attempt': attempt,
                    'receipt_id': receipt_id, 'delay_seconds': delay,
                    'retry_at': (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(),
                    'message': '모델이 혼잡해 같은 모델의 응답을 기다리고 있습니다. 연구 기록을 보존하고 이어서 실행합니다.'})
            remaining = delay
            while remaining:
                check_current(runner, job)
                interval = min(5, remaining)
                sleep(interval)
                remaining -= interval


def recovery_view(state):
    jobs = {j['id']: j for j in state.get('jobs', [])}
    for event in reversed(state.get('events', [])):
        if event['kind'] not in ('model_retry_waiting', 'model_retry_resumed'):
            continue
        body = event['body']
        if event['kind'] == 'model_retry_waiting' and jobs.get(body.get('job_id'), {}).get('status') == 'running':
            return body
        return None
    return None


def prepare_subscription_resume(runner, wid, rev, source_id):
    """Read only server-owned immutable records; clients supply an ID, never a path."""
    state = runner.store.snapshot(wid)
    planners = [j for j in state['jobs'] if j['kind'] == 'planner']
    source = next((j for j in planners if j['id'] == source_id), None)
    if (not source or planners[-1]['id'] != source_id
            or source['status'] not in ('failed', 'interrupted', 'provider_capacity')
            or state['rev'] != rev or source['based_rev'] != rev):
        raise ValueError('현재 연구 조건에서 중단된 마지막 판단만 이어갈 수 있습니다.')
    model = source['request'].get('model')
    if not isinstance(model, str) or not model.startswith('subscription:'):
        raise ValueError('원래 구독 모델 경로가 확인돼야 합니다.')
    route = runner.gateway.route(model)
    if route is None:
        raise ValueError('원래 구독 모델을 사용할 수 없습니다.')
    records = [json.loads(runner.store.artifact(wid, a['id'])['content'])
               for a in state['artifacts'] if a['kind'] == 'model_receipt'
               and a['meta'].get('job_id') == source_id]
    if not records:
        raise ValueError('실패 영수증이 없습니다.')
    receipt = max(records, key=lambda r: r.get('started_at', ''))
    if (receipt.get('status') != 'FAILED' or receipt.get('route') != model
            or receipt.get('requested_model') != route.model
            or receipt.get('requested_effort') != route.effort):
        raise ValueError('동일 모델과 설정의 실패 기록이 필요합니다.')
    name = Path(receipt.get('provider_record', '')).name
    if not re.fullmatch(r'call-\d{4,}', name):
        raise ValueError('호출 기록 이름을 확인해야 합니다.')
    root = Path(route.dispatch.root).resolve(strict=True)
    directory = (root / name).resolve(strict=True)
    if directory.parent != root:
        raise ValueError('호출 기록은 검수된 저장소 안에 있어야 합니다.')
    disk = json.loads((directory / 'receipt.json').read_text())
    payload = json.loads((directory / 'input.json').read_text())
    digest = hashlib.sha256(dump(payload).encode()).hexdigest()
    if disk != receipt or digest != receipt.get('request_sha256'):
        raise ValueError('원 요청과 실패 기록의 해시가 다릅니다.')
    terminal = json.loads((directory / 'provider/terminal.json').read_text())
    last = directory / 'provider/last-message.bin'
    stderr = directory / 'provider/stderr.bin'
    if (terminal.get('returncode') != 1 or (last.exists() and last.stat().st_size)
            or stderr.stat().st_size > 16 * 1024 * 1024
            or not re.search(r'(?m)^ERROR: Selected model is at capacity\. Please try a different model\.$',
                             stderr.read_text(errors='replace'))):
        raise ValueError('응답 없는 일시적 모델 혼잡인지 확인해야 합니다.')
    from .planner_recovery import completed_rounds
    rounds = completed_rounds(runner.store, state, source_id)
    arguments = {'model': model, 'resume_from_job': source_id,
                 'resume_request_sha256': digest, 'resume_completed_rounds': rounds,
                 'manual_subscription_continuation': True,
                 'synthesis_only': source['request'].get('synthesis_only', False)}
    for key in ('decision_preservation', 'requested_check_operations', 'reasoning_excluded_cases'):
        if key in source['request']:
            arguments[key] = source['request'][key]
    return {'request': payload, 'completed_rounds': rounds, 'arguments': arguments}
