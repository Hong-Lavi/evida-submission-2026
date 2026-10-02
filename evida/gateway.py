"""Competition-only Responses transport. Credentials never enter artifacts or workers."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.request

from .store import dump, now, uid
from .response_stream import read_response_stream, StreamProviderError

BASE_URL = "https://dacon-apim-hackathon-0903.azure-api.net/hackathon/openai/v1"


class GatewayError(RuntimeError):
    def __init__(self, status, message, receipt=None):
        super().__init__(message)
        self.status = status
        self.receipt = receipt or {}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise GatewayError("failed", "대회 게이트웨이의 리디렉션은 자동으로 따라가지 않습니다.")


class Gateway:
    transport_mode = "competition_gateway"

    def __init__(self, policy, enabled=False, model="gpt-5.6-terra", effort="high", transport=None,
                 max_output_tokens=24000, requests_dir=None, maximum_requests=None):
        if policy["base_url"].rstrip("/") != BASE_URL or model not in policy["allowed_models"]:
            raise ValueError("현재 대회 설정에 허용되지 않은 endpoint 또는 모델입니다.")
        if model not in policy.get("development_api_models", policy["allowed_models"]):
            raise ValueError("현재 실행 정책에 승인되지 않은 개발 모델입니다.")
        if type(max_output_tokens) is not int or not 128 <= max_output_tokens <= 24000:
            raise ValueError("모델 응답 범위는 128–24000 토큰이어야 합니다.")
        self.policy, self.enabled, self.model, self.effort = policy, enabled, model, effort
        self.max_output_tokens = max_output_tokens
        self.transport = transport  # Explicit test seam; never configured by the HTTP client.
        self.last_live_success = None
        self.requests_dir = Path(requests_dir) if requests_dir else None
        self.minimum_interval = float(policy.get('min_request_interval_seconds', 0))
        if not 0 <= self.minimum_interval <= 60:
            raise ValueError('요청 간격은 0–60초 범위에서 검토해야 합니다.')
        self._start_lock = threading.Lock()
        self._last_request_start = None
        # A public instance is handed to people who did not start it. Pacing bounds the rate,
        # not the total, so the total is bounded here or not at all.
        if maximum_requests is not None and (type(maximum_requests) is not int or maximum_requests < 1):
            raise ValueError('호출 상한은 1 이상의 정수여야 합니다.')
        self.maximum_requests = maximum_requests
        self.requests_made = 0
        self._budget_lock = threading.Lock()

    def pace(self):
        """Space starts in this product process; never retry an HTTP failure."""
        if self.transport is not None or not self.minimum_interval:
            return 0.0
        began = time.monotonic()
        with self._start_lock:
            if self._last_request_start is not None:
                delay = self.minimum_interval - (time.monotonic() - self._last_request_start)
                if delay > 0:
                    time.sleep(delay)
            self._last_request_start = time.monotonic()
        return round(time.monotonic() - began, 5)

    def status(self):
        configured = bool(os.environ.get(self.policy["secret_env"]))
        remaining = (None if self.maximum_requests is None
                     else max(0, self.maximum_requests - self.requests_made))
        return {"enabled": self.enabled, "credential_configured": configured,
                "maximum_requests": self.maximum_requests, "requests_made": self.requests_made,
                "requests_remaining": remaining,
                "available": self.enabled and configured,
                "requested_model": self.model, "requested_effort": self.effort,
                "approved_models": self.approved_models(),
                "transport_mode": "test_fixture" if self.transport else self.transport_mode,
                "live_verified": self.last_live_success is not None,
                "last_live_success": self.last_live_success,
                "message": ("대회 모델 연결 확인됨" if self.last_live_success else "대회 모델 연결 준비") if self.enabled and configured else
                           "대회 모델 연결 전 · 자료 검토와 계산 도구는 사용할 수 있습니다."}

    def approved_models(self):
        """The models a research may choose between: the competition allowlist, narrowed to the
        ones this run's policy approves. Offering anything else is a policy change, not a UI one."""
        approved = self.policy.get("development_api_models", self.policy["allowed_models"])
        return [model for model in self.policy["allowed_models"] if model in approved]

    def _chosen(self, model):
        """A per-research choice clears the same two checks the constructor applies."""
        if model is None:
            return self.model
        if model not in self.approved_models():
            raise GatewayError("invalid_input", "현재 실행 정책에 승인되지 않은 모델입니다.")
        return model

    def request(self, payload, model=None):
        if not self.enabled:
            raise GatewayError("input_missing", "제품 모델 실행이 아직 활성화되지 않았습니다.")
        # Before the key is read or anything is sent.
        chosen = self._chosen(model)
        if self.maximum_requests is not None:
            with self._budget_lock:
                if self.requests_made >= self.maximum_requests:
                    raise GatewayError("budget_exhausted",
                                       f"이 인스턴스에 허용된 모델 호출 {self.maximum_requests}회를 "
                                       "모두 사용했습니다. 자동으로 늘리지 않습니다. 이미 완료된 "
                                       "연구 결과는 그대로 열어볼 수 있습니다.")
                self.requests_made += 1
        key = os.environ.get(self.policy["secret_env"])
        if not key and self.transport is None:
            raise GatewayError("input_missing", "고라니 제품 프로세스에 대회 API 키 설정이 필요합니다.")
        if key and (len(key) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in key)):
            # HTTP libraries may include an invalid header value in exception text. Never pass it there.
            raise GatewayError("invalid_input", "대회 키의 형식을 확인해야 합니다. 키 내용은 출력하지 않았습니다.")
        body = {**payload, "model": chosen, "reasoning": {"effort": self.effort},
                "store": False, "include": ["reasoning.encrypted_content"], "max_output_tokens": self.max_output_tokens}
        if self.policy.get("stream_responses"):
            body["stream"] = True
        encoded = dump(body).encode()
        if key and key.encode() in encoded:
            raise GatewayError("invalid_input", "인증 자료가 입력에 포함되어 전송하지 않았습니다.")
        pacing_wait = self.pace()
        receipt = {"started_at": now(), "requested_model": chosen, "requested_effort": self.effort,
                   "request_sha256": hashlib.sha256(encoded).hexdigest(), "endpoint": BASE_URL + "/responses",
                   "input_json_bytes": len(dump(payload.get("input", [])).encode()),
                   "transport_mode": "test_fixture" if self.transport else "competition_gateway"}
        receipt['pacing_wait_seconds'] = pacing_wait
        directory = None
        if self.requests_dir:
            directory = self.requests_dir / uid("request")
            directory.mkdir(parents=True, exist_ok=False)
            (directory / "request.json").write_bytes(encoded)
            (directory / "started.json").write_text(dump(receipt))
            receipt["request_record"] = str(directory.name)
        started = time.monotonic()
        stream_raw = bytearray()
        try:
            if self.transport:
                result, headers = self.transport(body)
            else:
                req = urllib.request.Request(BASE_URL + "/responses", data=encoded,
                    headers={"api-key": key, "Content-Type": "application/json"}, method="POST")
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
                with opener.open(req, timeout=1200) as response:
                    headers = response.headers
                    receipt["quota_headers"] = {h: headers.get(h) for h in self.policy["usage_headers"] if headers.get(h) is not None}
                    if body.get("stream"):
                        receipt["transport"] = "SSE"
                        receipt["quota_header_timing"] = "HTTP headers received before final usage; not a final debit"
                        result, event_types = read_response_stream(response, stream_raw)
                        receipt["stream_event_types"] = event_types
                        raw = bytes(stream_raw)
                    else:
                        raw = response.read(16 * 1024 * 1024 + 1)
                        result = json.loads(raw)
                    if len(raw) > 16 * 1024 * 1024 or (key and key.encode() in raw):
                        raise GatewayError("outcome_unknown", "응답이 저장 범위를 초과했습니다. 자동 재호출하지 않습니다.")
                if directory:
                    (directory / "response.json").write_text(dump(result))
            receipt.update(actual_model=result.get("model"), response_id=result.get("id"),
                           usage=result.get("usage"), response_status=result.get("status"),
                           quota_headers={h: headers.get(h) for h in self.policy["usage_headers"] if headers.get(h) is not None},
                           elapsed_seconds=round(time.monotonic() - started, 5))
            receipt["status"] = "RETURNED"
            actual = result.get("model", "")
            if not re.fullmatch(re.escape(chosen) + r"(?:-\d{4}-\d{2}-\d{2})?", actual):
                raise GatewayError("identity_unverified", "실제 반환 모델이 요청 모델과 일치하는지 확인이 필요합니다.", receipt)
            if result.get("status") != "completed":
                raise GatewayError(result.get("status", "outcome_unknown"), "모델 응답이 완료되지 않았습니다. 원상태를 보존했습니다.", receipt)
            for item in result.get("output", []):
                for part in item.get("content", []):
                    if part.get("type") == "refusal":
                        raise GatewayError("refused", "서비스가 이 요청에 응답하지 않았습니다. 요청과 작업 상태를 보존했습니다.", receipt)
            if self.transport is None:
                self.last_live_success = {"started_at": receipt["started_at"], "actual_model": actual,
                                          "requested_effort": self.effort}
            return result, receipt
        except StreamProviderError as exc:
            receipt.update(provider_error_code=exc.code, provider_error_type=exc.error_type,
                           elapsed_seconds=round(time.monotonic() - started, 5))
            if exc.response:
                receipt.update(actual_model=exc.response.get('model'), usage=exc.response.get('usage'),
                               response_id=exc.response.get('id'), response_status=exc.response.get('status'))
            if exc.code in {'bio_policy', 'content_policy_violation', 'safety_violation'}:
                status = 'refused'
                message = '모델 제공자가 이 요청에 응답하지 않았습니다 (' + exc.code + '). 새 입력과 이전 판단을 보존했습니다. 자동 재시도·모델 대체는 하지 않았습니다.'
            elif exc.code in {'rate_limit_exceeded', 'insufficient_quota'}:
                status = 'quota_or_rate_limit'
                message = '모델 제공자의 사용 한도로 응답하지 못했습니다. 자동 재시도하지 않습니다.'
            else:
                status = 'failed'
                message = '모델 제공자가 오류를 반환했습니다. 원 요청과 결과를 보존했습니다.'
            receipt['status'] = status
            raise GatewayError(status, message, receipt) from None
        except GatewayError as exc:
            receipt.update(exc.receipt)
            receipt["status"] = exc.status
            exc.receipt = receipt
            raise
        except urllib.error.HTTPError as exc:
            receipt.update(http_status=exc.code, elapsed_seconds=round(time.monotonic() - started, 5))
            receipt["diagnostic_headers"] = {h: exc.headers.get(h) for h in
                ("x-request-id", "apim-request-id", "x-ms-request-id", "retry-after")
                if exc.headers and exc.headers.get(h) is not None}
            # Do not persist provider error text, request headers or credentials.
            status = "quota_or_rate_limit" if exc.code == 429 else "failed"
            receipt["status"] = status
            raise GatewayError(status, f"대회 게이트웨이가 HTTP {exc.code}를 반환했습니다. 자동 대체 호출은 하지 않았습니다.", receipt) from None
        except (OSError, ValueError, http.client.HTTPException):
            receipt["elapsed_seconds"] = round(time.monotonic() - started, 5)
            receipt["status"] = "outcome_unknown"
            raise GatewayError("outcome_unknown", "요청의 완료 여부를 확인하지 못했습니다. 중복 과금 방지를 위해 자동 재시도하지 않습니다.", receipt) from None
        finally:
            if directory:
                if stream_raw and not (key and key.encode() in stream_raw):
                    (directory / "stream.sse").write_bytes(stream_raw)
                    receipt["stream_sha256"] = hashlib.sha256(stream_raw).hexdigest()
                    receipt["stream_bytes"] = len(stream_raw)
                (directory / "receipt.json").write_text(dump(receipt))
