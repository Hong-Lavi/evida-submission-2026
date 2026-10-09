"""Submitter-subscription routes for the public EVIDA release 10.

A visitor reaches these only by choosing them, after a caution that they run on the submitter's
personal Claude or ChatGPT subscription. They reuse the reviewed release-09 product bridge: the
request is frozen into an indexed input packet, the model answers with the small JSON action
envelope, and the product's own function and decision contracts validate it before anything runs.

Unlike that bridge, a failed or unverified call fails only its own job. It is recorded, never
accepted, and never sent to another provider. A route stops admitting calls only for reasons
that would fail every later call too: missing subscription login, spent call allowance, or a
provider usage limit (for a cooling-off period).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

BASE = Path(__file__).resolve().parent
RUNTIME = BASE.parent
ROOT = Path('/data/user_home/hsm927/projects/EVIDA_finals_research_2026')
BRIDGE = ROOT / 'audit/evida-final-ui-20261002/subscription-format-repair-05/transport'
if not os.environ.get('EVIDA_SUBSCRIPTION_PRODUCT'):
    raise RuntimeError('The launcher must name the exact product before loading the bridge')
sys.path.insert(0, str(BRIDGE))

import transport_contract as contract  # noqa: E402  reviewed bridge; also sets the runtime paths
from transport_contract import (  # noqa: E402
    ENVELOPE, logical_input, catalog_paths, required_paths, wire_output, restore_indexed_input,
    input_preflight, verify_preserved_runtime, subscription_environment, provider_workspace,
    to_primitive, usage_review, _safe, save, dump, now, GatewayError,
)
from bounded_subscription_dispatch import BoundedDispatch, DispatchPaused  # noqa: E402
from lavi_research_os.providers.base import ProviderError  # noqa: E402
from lavi_research_os.providers.claude import ClaudeSubscriptionAdapter  # noqa: E402
from lavi_research_os.providers.codex import CodexSubscriptionAdapter  # noqa: E402
from lavi_research_os.policy import audit_claude, audit_codex  # noqa: E402
from research_input_support import FileInputClaudeAdapter, digest  # noqa: E402

_indexer = contract._c25_indexer  # the product packet builder release 09 actually used
prepare_indexed_input = _indexer.prepare_indexed_input
IndexedInputCodexAdapter = _indexer.IndexedInputCodexAdapter

SUBSCRIPTION_PREFIX = 'subscription:'
API_ENVIRONMENT = ('EVIDA_COMPETITION_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY')
RATE_LIMIT_COOLDOWN_SECONDS = 1800
IDENTITY = {'claude': r'claude-opus-5(?:-\d{8}|-\d{4}-\d{2}-\d{2})?',
            'codex': r'gpt-6-sol(?:-\d{4}-\d{2}-\d{2})?'}

# The reviewed task names the model it was written for and the Read tool; each route says what
# is actually true for it. Every replaced passage must still be present exactly once.
_IDENTITY_LINE = ("This is the researcher's local development/validation workflow, using Claude Opus 5/high\n"
                  "through the existing Claude subscription.")
_READ_LINES = ("The input directory is read-only. Use the Read tool with selected line ranges;\n"
               "Bash, editing and arbitrary code execution are unavailable to the model.")
_READ_SCOPE = ("Use the Read tool only to read this frozen input directory, not the repository,\n"
               "other workspaces, internet, or runtime.")


class StrictReadClaudeAdapter(FileInputClaudeAdapter):
    """The release-09 Read scope, with no MCP server configuration loaded either."""

    def build_command(self, schema):
        command = super().build_command(schema)
        command.extend(['--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}'])
        return command


def route_task(kind, label, effort, provider_label):
    task = contract.TASK
    for passage in (_IDENTITY_LINE, _READ_LINES, _READ_SCOPE):
        if task.count(passage) != 1:
            raise RuntimeError('The reviewed bridge task changed; review the route task before use')
    task = task.replace(_IDENTITY_LINE,
                        f"This request comes from a visitor of the public EVIDA instance, using {label}/{effort}\n"
                        f"through the submitter's {provider_label} subscription.")
    if kind == 'codex':
        task = task.replace(_READ_LINES,
                            "The input directory is read-only. Read selected line ranges with read-only\n"
                            "shell commands such as sed -n or rg; editing, network and other execution are unavailable.")
        task = task.replace(_READ_SCOPE,
                            "Read only this frozen input directory, not the repository,\n"
                            "other workspaces, internet, or runtime.")
    return task


def load_authorization(path=RUNTIME / 'authorization.json'):
    raw = Path(path).read_bytes()
    value = json.loads(raw)
    if (value.get('status') != 'AUTHORIZED_BY_RESEARCHER'
            or value.get('default_route') != 'competition_api'
            or value.get('automatic_fallback') is not False
            or value.get('competition_credentials_in_subscription_calls') is not False
            or not value.get('researcher_verbatim')
            or {r.get('kind') for r in value.get('routes', [])} != {'claude', 'codex'}):
        raise ValueError('Subscription routes need the explicit researcher authorization record')
    return value, hashlib.sha256(raw).hexdigest()


class SubscriptionRouteGateway:
    kinds = ('claude', 'codex')

    def __init__(self, spec, authorization, authorization_sha256, calls_root):
        if spec['kind'] not in self.kinds:
            raise ValueError('Unknown subscription route kind')
        verify_preserved_runtime()
        subscription_environment()
        if any(os.environ.get(name) for name in API_ENVIRONMENT):
            raise ValueError('Competition/API credentials must be absent from subscription calls')
        self.kind, self.model, self.effort = spec['kind'], spec['model'], spec['effort']
        self.label, self.provider_label = spec['label'], spec['provider_label']
        self.route_id = SUBSCRIPTION_PREFIX + self.model
        self.maximum_calls = int(authorization['maximum_calls_per_route'])
        self.timeout_seconds = int(authorization['timeout_seconds'])
        self.authorization, self.authorization_sha256 = authorization, authorization_sha256
        self.audit = audit_claude() if self.kind == 'claude' else audit_codex()
        self.task = route_task(self.kind, self.label, self.effort, self.provider_label)
        root = Path(calls_root).resolve() / self.kind
        self.dispatch = BoundedDispatch(root, maximum=int(authorization['concurrency_per_route']))
        self.lock = threading.Lock()
        self.cooldown_until = 0.0
        self.last_failure = None
        self.last_live_success = None

    def _calls_made(self):
        return self.dispatch.next_index - 1

    def status(self):
        made = self._calls_made()
        signed_in = bool(self.audit.authenticated and self.audit.subscription_only)
        cooling = time.time() < self.cooldown_until
        available = signed_in and made < self.maximum_calls and not cooling
        if not signed_in:
            message = f'제출자 {self.provider_label} 구독 로그인 확인 필요'
        elif made >= self.maximum_calls:
            message = f'이 구독 경로에 허용된 호출 {self.maximum_calls}회를 모두 사용했습니다'
        elif cooling:
            message = f'제출자 {self.provider_label} 구독의 사용 한도로 잠시 쉬는 중입니다'
        else:
            message = '사용 가능'
        return {'id': self.route_id, 'provider': 'anthropic' if self.kind == 'claude' else 'openai',
                'label': self.label, 'model': self.model, 'effort': self.effort,
                'available': available, 'message': message,
                'caution': f'제출자(연구자) 개인 {self.provider_label} 구독으로 운용됩니다.',
                'requests_made': made, 'maximum_requests': self.maximum_calls,
                'requests_remaining': max(0, self.maximum_calls - made),
                'provider_cli_version': self.audit.version,
                'last_live_success': self.last_live_success, 'automatic_fallback': False}

    def request(self, request):
        status = self.status()
        if not status['available']:
            raise GatewayError('route_unavailable', status['message'])
        try:
            with self.dispatch.admit() as admission:
                if admission.index > self.maximum_calls:
                    raise GatewayError('route_unavailable', status['message'])
                return self._request_once(request, admission)
        except DispatchPaused:
            raise GatewayError('route_unavailable', '이 구독 경로는 지금 새 호출을 받지 않습니다.') from None

    def _adapter(self, directory, packet):
        if self.kind == 'claude':
            source = ClaudeSubscriptionAdapter(model=self.model, effort=self.effort,
                                               timeout_seconds=self.timeout_seconds,
                                               allow_web_tools=False, available_tools=())
            permission = {'status': 'APPROVED_BY_RESEARCHER', 'scope': 'FROZEN_C1_INPUT_FILES_ONLY',
                          'verbatim_response': self.authorization['researcher_verbatim'],
                          'approval_sha256': self.authorization_sha256,
                          'packet_sha256': digest(packet),
                          'requested_model': self.model, 'requested_effort': self.effort,
                          'purpose': 'Public visitor request on an explicitly chosen subscription route; '
                                     'exact frozen input Read only. No provider or paid fallback.'}
            return StrictReadClaudeAdapter(source, directory, permission), permission
        source = CodexSubscriptionAdapter(model=self.model, reasoning_effort=self.effort,
                                          timeout_seconds=self.timeout_seconds, allow_web_search=False)
        return IndexedInputCodexAdapter(source, directory), None

    def _request_once(self, request, admission):
        subscription_environment()
        if any(os.environ.get(name) for name in API_ENVIRONMENT):
            raise GatewayError('invalid_input', '구독 실행에 API 키를 전달하지 않습니다.')
        root = admission.root
        receipt = {'started_at': now(), 'route': self.route_id, 'requested_model': self.model,
                   'requested_effort': self.effort, 'transport_mode': 'subscription_route_' + self.kind,
                   'competition_api': False, 'automatic_retry': False, 'automatic_fallback': False,
                   'request_sha256': hashlib.sha256(dump(request).encode()).hexdigest(),
                   'bridge_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'authorization_sha256': self.authorization_sha256, 'provider_record': str(root),
                   'status': 'PREPARING', 'provider_dispatched': False,
                   'queue_seconds': round(admission.queue_seconds, 3)}
        save(root / 'receipt.json', receipt)
        started = time.monotonic()
        try:
            payload = logical_input(request)
            _safe(payload)
            save(root / 'input.json', request)
            save(root / 'provider-input.json', payload)
            save(root / 'schema.json', ENVELOPE)
            (root / 'task.txt').write_text(self.task)
            directory = (root / 'prepared-input').resolve()
            prepare_indexed_input(directory, self.task, payload,
                                  document_paths=catalog_paths(payload),
                                  required_paths=required_paths(payload),
                                  navigation=True, catalog_directory=True)
            if restore_indexed_input(directory) != payload:
                raise ValueError('Exact product context restoration failed')
            preflight = input_preflight(self.task, payload, ENVELOPE, directory)
            save(root / 'input-preflight.json', preflight)
            if preflight['status'] != 'READY':
                raise ValueError('This input needs review before dispatch')
            packet = json.loads((directory / 'input-packet.json').read_text())
            adapter, permission = self._adapter(directory, packet)
            if permission:
                save(root / 'read-permission.json', permission)
            receipt.update(status='RUNNING', provider_dispatched=True,
                           provider_input_sha256=preflight['payload_sha256'])
            save(root / 'receipt.json', receipt)
            with provider_workspace(root / 'provider') as workspace:
                response = adapter.complete_json(task=self.task, payload=payload,
                                                 schema=ENVELOPE, workspace=Path(workspace))
            save(root / 'provider-response.json', to_primitive(response))
            if not re.fullmatch(IDENTITY[self.kind], response.actual_model or ''):
                raise ValueError('The returned model differs from the chosen route; nothing was accepted')
            if 'PROVIDER_EXECUTION_DEGRADED' in response.quality_flags:
                raise ValueError('Degraded execution is recorded and not used for product actions')
            output = wire_output(response.payload, request, f'{self.kind}-route-{admission.index}',
                                 normalization_directory=root)
            try:
                report = usage_review(root / 'provider', adapter_kind=self.kind)
            except Exception as exc:  # usage accounting must not decide acceptance
                report = {'status': 'USAGE_REVIEW_UNAVAILABLE', 'error': type(exc).__name__}
            save(root / 'usage-review.json', report)
            receipt.update(status='COMPLETED', response_status='completed',
                           actual_model=response.actual_model, identity_source=response.identity_source,
                           identity_observation=response.identity_observation,
                           quality_flags=list(response.quality_flags),
                           elapsed_seconds=round(time.monotonic() - started, 3))
            save(root / 'receipt.json', receipt)
            save(root / 'wire-output.json', output)
            self.last_live_success = {'started_at': receipt['started_at'],
                                      'actual_model': response.actual_model}
            return {'model': response.actual_model, 'status': 'completed', 'output': output}, receipt
        except Exception as exc:
            status, message = 'failed', (f'{self.label} 구독 호출의 입력·원 응답·실패를 보존했습니다. '
                                         '자동 재호출이나 다른 모델 전환은 하지 않았습니다.')
            details = {}
            if isinstance(exc, ProviderError):
                details = {'reason': exc.reason.value, 'actual_model': exc.actual_model,
                           'identity_observation': exc.identity_observation,
                           'execution': exc.execution, 'content_status': exc.content_status,
                           'failure_evidence': exc.failure_evidence}
                save(root / 'provider-error.json', to_primitive(details))
                if exc.reason.value in ('RATE_LIMIT', 'QUOTA'):
                    with self.lock:
                        self.cooldown_until = time.time() + RATE_LIMIT_COOLDOWN_SECONDS
                    status = 'quota_or_rate_limit'
                    message = (f'제출자 {self.provider_label} 구독의 사용 한도로 응답하지 못했습니다. '
                               '자동 재시도하지 않습니다.')
            self.last_failure = type(exc).__name__
            receipt.update(status='FAILED', response_status=status, error_type=type(exc).__name__,
                           error=str(exc)[:500], provider_failure=to_primitive(details),
                           elapsed_seconds=round(time.monotonic() - started, 3))
            save(root / 'receipt.json', receipt)
            raise GatewayError(status, message, receipt) from None


def build_subscription_routes(runtime=RUNTIME):
    authorization, sha = load_authorization(Path(runtime) / 'authorization.json')
    calls = Path(authorization['provider_calls']).resolve()
    if not calls.is_relative_to(Path(runtime).resolve()):
        raise ValueError('Subscription call records must stay inside this runtime')
    return [SubscriptionRouteGateway(spec, authorization, sha, calls) for spec in authorization['routes']]
