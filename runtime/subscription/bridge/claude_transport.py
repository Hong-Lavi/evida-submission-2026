"""Explicit Claude subscription product bridge; no paid or Codex fallback.

Uses the established product request, scientific tool and decision contracts.
The original provider identity gate remains intact. An identity failure pauses
dispatch and preserves raw evidence for a separate human/coordinator review.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import time

from transport_contract import (
    TASK, ENVELOPE, logical_input, catalog_paths, required_paths, wire_output,
    prepare_indexed_input, restore_indexed_input, input_preflight,
    verify_preserved_runtime, subscription_environment, provider_workspace,
    to_primitive, usage_review, _safe, save, dump, now, GatewayError,
    BoundedDispatch, DispatchPaused,
)
from format_recovery_dispatch import FormatRecoveryDispatch as BoundedDispatch, DispatchPaused
from lavi_research_os.providers.claude import ClaudeSubscriptionAdapter
from lavi_research_os.providers.base import ProviderError
from lavi_research_os.policy import audit_claude
from research_input_support import FileInputClaudeAdapter, digest

import importlib.util

BASE = Path(__file__).resolve().parent
AUTHORITY_BASE = Path('/data/user_home/hsm927/projects/EVIDA_finals_research_2026/audit/evida-final-ui-20261002/subscription-input-repair-03')
CURRENT_AUTHORIZATION_SHA256 = 'b73c644713a142e5f82ef5ea45ffecaae79cc4dabb66339422a7deab0e726103'
CURRENT_INPUT_REVIEW_SHA256 = '9951be225e4e726b18a89cb57ce32207eaf591b4e224a67d40a9cdf7031322c3'
_catalog_spec = importlib.util.spec_from_file_location('candidate22_indexed_input', BASE / 'product_indexed_input82.py')
_catalog_module = importlib.util.module_from_spec(_catalog_spec)
_catalog_spec.loader.exec_module(_catalog_module)
prepare_indexed_input = _catalog_module.prepare_indexed_input


def authority():
    review_path = AUTHORITY_BASE / 'input-review.json'
    if hashlib.sha256(review_path.read_bytes()).hexdigest() != CURRENT_INPUT_REVIEW_SHA256:
        raise ValueError('Reviewed lossless input repair binding changed')
    review = json.loads(review_path.read_text())
    if (review.get('status') != 'ROOT_REVIEWED_LOSSLESS_INPUT_REPAIR'
            or review.get('scientific_corpus_or_instructions_removed') is not False
            or review.get('review_threshold_changed') is not False
            or review.get('automatic_resume') is not False):
        raise ValueError('Explicit reviewed input repair required')
    for name, expected in review['files'].items():
        if hashlib.sha256((AUTHORITY_BASE / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Reviewed input representation changed: ' + name)
    if hashlib.sha256(Path(review['original_hold_preserved']).read_bytes()).hexdigest() != review['original_hold_sha256']:
        raise ValueError('Preserved predecessor input hold changed')
    path = AUTHORITY_BASE / 'authorization.json'
    if hashlib.sha256(path.read_bytes()).hexdigest() != CURRENT_AUTHORIZATION_SHA256:
        raise ValueError('Current authorization changed; ROOT review required')
    value = json.loads(path.read_text())
    if hashlib.sha256((AUTHORITY_BASE / 'current-user-correction.json').read_bytes()).hexdigest() != value['correction_record_sha256']:
        raise ValueError('Current effort correction source changed')
    if (value.get('status') != 'AUTHORIZED_CONTINUATION_FROM_CURRENT_USER'
            or value.get('model') != 'claude-opus-5'
            or value.get('effort') != 'high'
            or value.get('route') != 'existing_claude_subscription'
            or value.get('competition_api') is not False
            or value.get('automatic_fallback') is not False
            or value.get('maximum_new_provider_calls') != 60
            or value.get('concurrency_limit') != 2
            or not value.get('latest_user_verbatim')):
        raise ValueError('Current Claude continuation scope is missing or changed')
    if hashlib.sha256(Path(value['decision']).read_bytes()).hexdigest() != value['decision_sha256']:
        raise ValueError('Current researcher decision binding changed')
    return value, hashlib.sha256(path.read_bytes()).hexdigest()


class ProductReadAdapter(FileInputClaudeAdapter):
    def build_command(self, schema):
        command = super().build_command(schema)
        command.extend(['--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}'])
        return command


class ClaudeProductGateway:
    model, effort = 'claude-opus-5', 'high'
    transport_mode = 'claude_subscription_indexed_json_action_bridge'

    def __init__(self, audit_root, *, recovery_review_path=None, recovery_review_sha256=None):
        verify_preserved_runtime()
        subscription_environment()
        if any(os.environ.get(k) for k in ("EVIDA_COMPETITION_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY")):
            raise ValueError("Competition/API credentials must be absent from subscription process")
        self.auth_audit = audit_claude()
        self.scope, self.scope_sha256 = authority()
        self.requests_dir = None
        self.policy = {'cross_route_resume': False, 'transport_mode': self.transport_mode}
        self.audit_root = Path(audit_root).resolve()
        if self.audit_root != Path(self.scope['provider_calls']).resolve():
            raise ValueError('Shared stage provider-calls directory required; budget cannot reset')
        self.audit_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Only ROOT writes this launch profile after reviewing the diagnosed repair.
        # No profile is created automatically; ordinary initialization remains paused.
        launch_profile = BASE.parent / 'format-review-launch.json'
        if recovery_review_path is None and recovery_review_sha256 is None and launch_profile.exists():
            profile = json.loads(launch_profile.read_text())
            recovery_review_path = profile.get('recovery_review_path')
            recovery_review_sha256 = profile.get('recovery_review_sha256')
        self.dispatch = BoundedDispatch(self.audit_root, maximum=2, hold_path=BASE.parent / "dispatch-hold-high.json", recovery_review_path=recovery_review_path, recovery_review_sha256=recovery_review_sha256)
        self.last_failure = None
        self.last_live_success = None
        self.hold_path = BASE.parent / 'dispatch-hold-high.json'
        if self.hold_path.exists():
            self.last_failure = 'PRESERVED_DISPATCH_HOLD'
            self.dispatch.pause(self.last_failure)

    def _pause(self, reason):
        # A process restart must not erase a reviewed scientific/usage stop.
        self.dispatch.pause(reason)
        try:
            with self.hold_path.open('x') as handle:
                json.dump({'at': now(), 'reason': str(reason), 'automatic_resume': False}, handle)
                handle.write('\n')
        except FileExistsError:
            pass

    def status(self):
        dispatch = self.dispatch.snapshot()
        available = (self.last_failure is None and not dispatch['paused']
                     and self.auth_audit.authenticated and self.auth_audit.subscription_only)
        return {'enabled': True, 'available': available,
                'credential_configured': self.auth_audit.authenticated, 'requested_model': self.model,
                'requested_effort': self.effort, 'transport_mode': self.transport_mode,
                'dispatch': dispatch, 'competition_api': False,
                'approved_models': self.approved_models(),
                'requests_made': self.dispatch.next_index - 1,
                'calls_admitted': self.dispatch.next_index - 1,
                'requests_count_basis': 'Shared persistent call directories across max/high profiles; cap checked before admission',
                'requests_remaining': max(0, 60 - (self.dispatch.next_index - 1)),
                'maximum_requests': 60, 'automatic_fallback': False,
                'same_request_quota_resume': False,
                'subscription_auth_verified': self.auth_audit.subscription_only,
                'provider_cli_version': self.auth_audit.version,
                'live_verified': self.last_live_success is not None,
                'last_live_success': self.last_live_success,
                'message': 'Claude Opus 5 구독 · 현재 연구 연결' if available
                           else 'Claude 응답 검토 필요 · 기존 연구 기록 보존'}

    def approved_models(self):
        return [self.model]

    def request(self, request, model=None):
        if model is not None and model != self.model:
            raise GatewayError("invalid_input", "현재 구독 연결은 Claude Opus 5를 사용합니다. 지원하지 않는 모델은 호출하지 않았습니다.")
        # An explicit effort correction must not overlap the interrupted legacy
        # transport, which did not participate in the new OS slot locks.
        correction = json.loads((AUTHORITY_BASE / 'current-user-correction.json').read_text())
        legacy = correction['legacy_max_call_ids']
        if (legacy != ['call-0001', 'call-0002']
                or correction['interrupted_new_study_max_call'] not in legacy):
            raise GatewayError('invalid_input', '동결된 이전 max 호출 범위 확인이 필요합니다.')
        for call_id in legacy:
            previous = self.audit_root / call_id / 'receipt.json'
            try:
                record = json.loads(previous.read_text())
            except (OSError, ValueError):
                raise GatewayError('paused', '이전 max 호출 종료 기록을 확인한 뒤 high 호출을 시작합니다.') from None
            if record.get('requested_effort') == 'max' and record.get('status') in {'PREPARING', 'PREPARED', 'RUNNING'}:
                raise GatewayError('paused', '이전 max 호출 종료 기록을 확인한 뒤 high 호출을 시작합니다.')
        try:
            with self.dispatch.admit() as admission:
                if admission.index > self.scope['maximum_new_provider_calls']:
                    self.last_failure = 'STAGE_CALL_REVIEW_REQUIRED'
                    self._pause(self.last_failure)
                    raise DispatchPaused(self.last_failure)
                return self._request_once(request, admission)
        except DispatchPaused:
            raise GatewayError('paused', '기존 응답을 보존하며 검토 전 새 호출을 시작하지 않습니다.') from None
        except Exception as exc:
            self.last_failure = type(exc).__name__
            self._pause(self.last_failure)
            raise

    def _request_once(self, request, admission):
        subscription_environment()
        if any(os.environ.get(k) for k in ('EVIDA_COMPETITION_API_KEY', 'CODEX_API_KEY', 'OPENAI_API_KEY')):
            raise GatewayError('invalid_input', '구독 실행에 API 키를 전달하지 않습니다.')
        root = admission.root
        receipt = {'started_at': now(), 'requested_model': self.model,
                   'requested_effort': self.effort, 'transport_mode': self.transport_mode,
                   'competition_api': False, 'automatic_retry': False,
                   'request_sha256': hashlib.sha256(dump(request).encode()).hexdigest(),
                   'bridge_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'scope_sha256': self.scope_sha256, 'provider_record': str(root),
                   'status': 'PREPARING', 'provider_dispatched': False,
                   'queue_seconds': round(admission.queue_seconds, 3), 'concurrency_limit': 2}
        save(root / 'receipt.json', receipt)
        started = time.monotonic()
        try:
            payload = logical_input(request)
            _safe(payload)
            save(root / 'input.json', request)
            save(root / 'provider-input.json', payload)
            save(root / 'schema.json', ENVELOPE)
            (root / 'task.txt').write_text(TASK)
            directory = (root / 'prepared-input').resolve()
            prepare_indexed_input(directory, TASK, payload,
                                  document_paths=catalog_paths(payload),
                                  required_paths=required_paths(payload),
                                  navigation=True, catalog_directory=True)
            if restore_indexed_input(directory) != payload:
                raise ValueError('Exact product context restoration failed')
            preflight = input_preflight(TASK, payload, ENVELOPE, directory)
            save(root / 'input-preflight.json', preflight)
            if preflight['status'] != 'READY':
                raise ValueError('New input requires review before dispatch')
            packet = json.loads((directory / 'input-packet.json').read_text())
            permission = {'status': 'APPROVED_BY_RESEARCHER',
                          'scope': 'FROZEN_C1_INPUT_FILES_ONLY',
                          'verbatim_response': self.scope['latest_user_verbatim'],
                          'approval_sha256': self.scope_sha256,
                          'packet_sha256': digest(packet),
                          'requested_model': self.model, 'requested_effort': self.effort,
                          'purpose': 'Current EVIDA product request; exact frozen input Read only. No provider or paid fallback.'}
            save(root / 'read-permission.json', permission)
            receipt.update(status='PREPARED', provider_input_sha256=preflight['payload_sha256'])
            save(root / 'receipt.json', receipt)
            self.dispatch.check_dispatch()
            source = ClaudeSubscriptionAdapter(model=self.model, effort=self.effort,
                                               timeout_seconds=5400,
                                               allow_web_tools=False, available_tools=())
            adapter = ProductReadAdapter(source, directory, permission)
            receipt.update(status='RUNNING', provider_dispatched=True)
            save(root / 'receipt.json', receipt)
            print(dump({'event': 'claude_product_started', 'call': admission.index,
                        'requested_model': self.model}), flush=True)
            with provider_workspace(root / 'provider') as workspace:
                response = adapter.complete_json(task=TASK, payload=payload,
                                                 schema=ENVELOPE, workspace=Path(workspace))
            save(root / 'provider-response.json', to_primitive(response))
            # Documented routed Opus5 is acceptable when the original identity
            # gate itself attests it. Mixed/unknown metadata is never bypassed.
            if not re.fullmatch(r'claude-opus-5(?:-\d{8}|-\d{4}-\d{2}-\d{2})?', response.actual_model or ''):
                raise ValueError('Returned model requires explicit content/routing review')
            if 'PROVIDER_EXECUTION_DEGRADED' in response.quality_flags:
                raise ValueError('Degraded execution requires review before product actions')
            output = wire_output(response.payload, request, f'claude-product22-{admission.index}', normalization_directory=root)
            report = usage_review(root / 'provider', adapter_kind='claude')
            # Decision 0039 (researcher's explicit approval): the observed-context threshold is the
            # researcher's own local review signal, not a provider limit, and it no longer holds
            # dispatch. The alert stays recorded. Every other alert still holds: an automatic
            # compaction drops evidence silently, a rejected rate limit means the account is out,
            # and repeated identical reads mean the call is wasting itself.
            if isinstance(report.get('alerts'), list):
                report['context_alert_holds_dispatch'] = False
                report['hold_next_dispatch'] = bool(
                    [a for a in report['alerts'] if a != 'OBSERVED_CONTEXT_EXCEEDS_LOCAL_REVIEW_THRESHOLD'])
            save(root / 'usage-review.json', report)
            receipt.update(status='COMPLETED', response_status='completed',
                           actual_model=response.actual_model, identity_source=response.identity_source,
                           identity_observation=response.identity_observation,
                           quality_flags=list(response.quality_flags),
                           usage={'reported_usage': report['reported_usage'],
                                  'reported_model_usage': report['reported_model_usage'],
                                  'basis': 'Subscription CLI counters; cache/thinking subsets are not added twice, not a competition debit'},
                           elapsed_seconds=round(time.monotonic() - started, 3))
            save(root / 'receipt.json', receipt)
            save(root / 'wire-output.json', output)
            self.last_live_success = {'started_at': receipt['started_at'], 'actual_model': response.actual_model}
            if report['hold_next_dispatch']:
                self.last_failure = 'USAGE_REVIEW_REQUIRED'
                self._pause(self.last_failure)
            return {'model': response.actual_model, 'status': 'completed', 'output': output}, receipt
        except Exception as exc:
            self.last_failure = type(exc).__name__
            self._pause(self.last_failure)
            # Failed identity/content calls still have real observed consumption.
            # Preserve this independently; never turn it into identity acceptance.
            if (root / 'provider/stdout.bin').exists():
                save(root / 'usage-review.json', usage_review(root / 'provider', adapter_kind='claude'))
            details = {}
            if isinstance(exc, ProviderError):
                details = {'reason': exc.reason.value, 'actual_model': exc.actual_model,
                           'identity_observation': exc.identity_observation,
                           'execution': exc.execution, 'content_status': exc.content_status,
                           'failure_evidence': exc.failure_evidence}
                save(root / 'provider-error.json', to_primitive(details))
            receipt.update(status='FAILED', response_status='failed', error_type=type(exc).__name__,
                           error=str(exc)[:500], provider_failure=to_primitive(details),
                           elapsed_seconds=round(time.monotonic() - started, 3))
            save(root / 'receipt.json', receipt)
            raise GatewayError('failed', 'Claude 입력·원 응답·실패를 보존했습니다. 자동 재호출이나 다른 제공자 전환은 없습니다.', receipt) from None

