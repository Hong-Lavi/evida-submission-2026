"""Explicit continuation of a recorded HTTP429, preserving the original budget."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

from .contracts import DECISION, model_functions
from .store import dump

SYNTHESIS_SUFFIX = "\n지금까지의 근거로 현재 판단을 정리하라. 미확인 내용을 성공으로 채우지 말고 남은 확인으로 연결하라. 이번 응답은 추가 조회 없이 최종 JSON을 반환한다."


def completed_rounds(store, state, source_id):
    jobs = {j['id']: j for j in state['jobs']}
    chain = set()
    while source_id:
        if source_id in chain or source_id not in jobs:
            raise ValueError('원 실행의 연결 기록을 확인해야 합니다.')
        chain.add(source_id)
        source_id = jobs[source_id]['request'].get('resume_from_job')
    receipts = [json.loads(store.artifact(state['id'], a['id'])['content'])
                for a in state['artifacts'] if a['kind'] == 'model_receipt'
                and a['meta'].get('job_id') in chain]
    return sum(r.get('status') in ('RETURNED', 'COMPLETED') and r.get('response_status') == 'completed'
               for r in receipts)


def prepare_quota_resume(runner, wid, rev, source_id):
    """No dispatch. Trust the server's receipt directory, never a client path."""
    if getattr(runner.gateway, 'transport_mode', None) != 'competition_gateway':
        raise ValueError('이전 대회 요청은 해당 경로에 보존돼 있습니다. 현재 구독 모델의 새 검토는 별도로 시작해 주세요.')
    state = runner.store.snapshot(wid)
    planners = [j for j in state['jobs'] if j['kind'] == 'planner']
    source = next((j for j in planners if j['id'] == source_id), None)
    if not source or source['status'] != 'quota_or_rate_limit':
        raise ValueError('HTTP429로 중단된 판단만 이 경로로 이어갈 수 있습니다.')
    if state['rev'] != rev or source['based_rev'] != rev:
        raise ValueError('중단 후 연구 조건이 바뀌었습니다. 현재 조건으로 새 판단이 필요합니다.')
    if planners[-1]['id'] != source_id:
        raise ValueError('이후 실행 기록이 있습니다. 가장 최근 작업을 확인해 주세요.')
    receipts = [json.loads(runner.store.artifact(wid, a['id'])['content'])
                for a in state['artifacts'] if a['kind'] == 'model_receipt'
                and a['meta'].get('job_id') == source_id]
    if not receipts:
        raise ValueError('실패 영수증이 없습니다.')
    receipt = max(receipts, key=lambda r: r.get('started_at', ''))
    if (receipt.get('status') != 'quota_or_rate_limit' or receipt.get('http_status') != 429
            or receipt.get('response_id') or receipt.get('usage') or receipt.get('provider_error_code')):
        raise ValueError('응답 없는 HTTP429인지 확인되지 않아 이어서 호출하지 않습니다.')
    record = receipt.get('request_record', '')
    if not re.fullmatch(r'request_[a-f0-9]{16}', record) or not runner.gateway.requests_dir:
        raise ValueError('실패 요청의 저장 위치를 확인해야 합니다.')
    directory = runner.gateway.requests_dir / record
    disk_receipt = json.loads((directory / 'receipt.json').read_text())
    raw = (directory / 'request.json').read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if disk_receipt != receipt or digest != receipt.get('request_sha256'):
        raise ValueError('원 요청·영수증의 해시가 다릅니다.')
    if (directory / 'response.json').exists() or (directory / 'stream.sse').exists():
        raise ValueError('일부 응답이 남아 있어 먼저 수동 검토해야 합니다.')
    request = json.loads(raw)
    gateway = runner.gateway
    if (receipt.get('requested_model') != gateway.model or receipt.get('requested_effort') != gateway.effort
            or request.get('model') != gateway.model or request.get('reasoning') != {'effort': gateway.effort}
            or request.get('max_output_tokens') != gateway.max_output_tokens
            or request.get('stream', False) != bool(gateway.policy.get('stream_responses'))
            or request.get('store') is not False or request.get('include') != ['reasoning.encrypted_content']):
        raise ValueError('동일 모델·설정으로만 이어갈 수 있습니다.')
    if (request.get('instructions') not in (runner.prompt, runner.prompt + SYNTHESIS_SUFFIX)
            or request.get('tools') != model_functions()
            or request.get('parallel_tool_calls') is not False
            or request.get('text') != {'format': {'type': 'json_schema', 'name': 'evida_decision',
                                                'strict': True, 'schema': DECISION}}):
        raise ValueError('판단 지시·도구 계약이 바뀌었습니다. 새 검토가 필요합니다.')
    rounds = completed_rounds(runner.store, state, source_id)
    if not 0 < rounds < 16:
        raise ValueError('이어갈 작업 또는 원래 응답 예산이 없습니다.')
    expected_terminal = rounds == 15 or source['request'].get('synthesis_only', False)
    if request.get('tool_choice') != ('none' if expected_terminal else 'auto'):
        raise ValueError('원래 작업 단계와 실패 요청이 일치하지 않습니다.')
    retry_after = receipt.get('diagnostic_headers', {}).get('retry-after')
    if not isinstance(retry_after, str) or not retry_after.isdigit():
        raise ValueError('재개 가능 시각을 수동 확인해야 합니다.')
    earliest = datetime.fromisoformat(receipt['started_at']) + timedelta(
        seconds=float(receipt.get('elapsed_seconds', 0)) + int(retry_after))
    if datetime.now(timezone.utc) < earliest:
        raise ValueError('서비스가 안내한 대기 시간이 남았습니다. 잠시 후 이어가 주세요.')
    return {'request': request, 'completed_rounds': rounds,
            'arguments': {'resume_from_job': source_id, 'resume_request_sha256': digest,
                          'resume_completed_rounds': rounds, 'manual_quota_continuation': True,
                          'synthesis_only': source['request'].get('synthesis_only', False),
                          **({'decision_preservation': source['request']['decision_preservation']}
                             if 'decision_preservation' in source['request'] else {})}}
