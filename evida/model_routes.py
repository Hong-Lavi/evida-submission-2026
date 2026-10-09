"""Per-research model routes: the competition API by default, the submitter's subscriptions by choice.

A visitor runs on the competition API unless they pick something else. When that API has spent
its token allowance (HTTP 403), nothing switches on its own: the visitor is told, and may choose
one of the submitter's personal subscriptions by hand after a caution. Each route keeps its own
requested and actual model in the receipt it returns.

Subscription routes live outside the product (they need the subscription CLIs and their reviewed
bridge); this module only needs an object with `route_id`, `status()` and `request(payload)`.
"""
from __future__ import annotations

import json
from pathlib import Path
import threading
import time

from .gateway import GatewayError, QUOTA_EXHAUSTED_MESSAGE
from .store import dump, now

SUBSCRIPTION_PREFIX = "subscription:"
# A spent allowance is not re-tried by every visitor, but it is not believed forever either:
# after this long the next request goes to the API again and finds out.
QUOTA_RECHECK_SECONDS = 3600
API_LABELS = {"gpt-6-sol": "GPT-6 Sol", "gpt-5.6-sol": "GPT-5.6 Sol",
              "gpt-5.6-terra": "GPT-5.6 Terra", "gpt-5.6-luna": "GPT-5.6 Luna"}


class QuotaState:
    """Process-wide memory that the competition API refused for quota, kept across restarts."""

    def __init__(self, path=None, recheck_seconds=QUOTA_RECHECK_SECONDS, clock=time.time):
        self.path = Path(path) if path else None
        self.recheck_seconds = recheck_seconds
        self.clock = clock
        self.lock = threading.Lock()
        self.value = None
        if self.path and self.path.is_file():
            try:
                value = json.loads(self.path.read_text())
                self.value = value if isinstance(value.get("epoch"), (int, float)) else None
            except (OSError, ValueError, AttributeError):
                self.value = None

    def mark(self, receipt=None):
        record = {"status": "quota_exhausted", "at": now(), "epoch": self.clock(),
                  "http_status": (receipt or {}).get("http_status"),
                  "provider_error_code": (receipt or {}).get("provider_error_code")}
        with self.lock:
            self.value = record
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(dump(record))
                temporary.replace(self.path)

    def snapshot(self):
        with self.lock:
            value = dict(self.value) if self.value else None
        if not value:
            return None
        left = self.recheck_seconds - (self.clock() - value["epoch"])
        if left <= 0:
            return None
        value["recheck_after_seconds"] = int(left)
        return value

    def active(self):
        return self.snapshot() is not None


class RouteGateway:
    """The gateway the runner sees. It forwards each call to the route the research chose."""

    transport_mode = "model_routes"

    def __init__(self, api, subscriptions=(), quota=None):
        self.api = api
        self.subscriptions = {}
        for route in subscriptions:
            if not route.route_id.startswith(SUBSCRIPTION_PREFIX) or route.route_id in self.subscriptions:
                raise ValueError("구독 경로 ID를 확인해야 합니다.")
            self.subscriptions[route.route_id] = route
        self.quota = quota or QuotaState()
        self.policy = api.policy
        self.requests_dir = None

    # The runner's quota-resume check compares receipts with the default route's model/effort.
    @property
    def model(self):
        return self.api.model

    @property
    def effort(self):
        return self.api.effort

    @property
    def enabled(self):
        return self.api.enabled

    @property
    def last_live_success(self):
        return self.api.last_live_success

    def approved_models(self):
        return [*self.api.approved_models(), *self.subscriptions]

    def route(self, model):
        """None for the competition API, otherwise the chosen subscription route."""
        if model is None or model in self.api.approved_models():
            return None
        route = self.subscriptions.get(model)
        if route is None:
            raise GatewayError("invalid_input", "현재 실행 정책에 승인되지 않은 모델입니다.")
        return route

    def check_model_available(self, model):
        """Refuse before a job is queued, so the visitor is asked instead of waiting for a failure."""
        route = self.route(model)
        if route is None:
            if self.quota.active():
                raise GatewayError("quota_exhausted", QUOTA_EXHAUSTED_MESSAGE)
            api = self.api.status()
            if not api["available"]:
                raise GatewayError("input_missing", api["message"])
            return
        status = route.status()
        if not status["available"]:
            raise GatewayError("route_unavailable", status["message"])

    def _api_routes(self, api, quota):
        available = api["available"] and quota is None
        message = ("대회 API 토큰 한도 소진" if quota else
                   "사용 가능" if api["available"] else api["message"])
        return [{"id": name, "kind": "competition", "provider": "competition_api",
                 "label": API_LABELS.get(name, name), "model": name,
                 "effort": api["requested_effort"], "default": name == api["requested_model"],
                 "available": available, "message": message, "caution": None}
                for name in api["approved_models"]]

    def status(self):
        api = self.api.status()
        quota = self.quota.snapshot()
        routes = self._api_routes(api, quota)
        for route in self.subscriptions.values():
            routes.append({**route.status(), "kind": "subscription", "default": False})
        api_available = api["available"] and quota is None
        subscription_available = any(r["available"] for r in routes if r["kind"] == "subscription")
        if api_available:
            message = api["message"]
        elif quota and subscription_available:
            message = "대회 API 토큰 한도 소진 · 제출자 구독 모델을 직접 선택할 수 있습니다"
        elif subscription_available:
            message = "대회 API 사용 불가 · 제출자 구독 모델을 직접 선택할 수 있습니다"
        else:
            message = api["message"] if not quota else QUOTA_EXHAUSTED_MESSAGE
        return {**api, "available": api_available or subscription_available,
                "competition_available": api_available, "competition_quota": quota,
                "competition_api": True, "approved_models": self.approved_models(),
                "routes": routes, "transport_mode": self.transport_mode,
                "automatic_fallback": False, "message": message}

    def request(self, payload, model=None):
        route = self.route(model)
        if route is not None:
            return route.request(payload)
        if self.quota.active():
            raise GatewayError("quota_exhausted", QUOTA_EXHAUSTED_MESSAGE)
        try:
            return self.api.request(payload, model=model)
        except GatewayError as exc:
            if exc.status == "quota_exhausted":
                self.quota.mark(exc.receipt)
            raise


def workspace_model(store, wid, gateway):
    """The model this research last chose explicitly, if any and still offered.

    Follow-up runs, check reviews and explanations do not carry a model of their own; they stay
    on the route the visitor picked for this research instead of silently returning to the default."""
    approved = set(gateway.approved_models())
    with store.connect() as db:
        rows = db.execute("SELECT request FROM jobs WHERE workspace=? ORDER BY created DESC",
                          (wid,)).fetchall()
    for row in rows:
        try:
            model = json.loads(row["request"]).get("model")
        except (ValueError, AttributeError):
            continue
        if isinstance(model, str) and model in approved:
            return model
    return None
