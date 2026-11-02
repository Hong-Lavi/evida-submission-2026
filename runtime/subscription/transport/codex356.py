from __future__ import annotations

import re
import json
from dataclasses import asdict
import subprocess
import threading
from pathlib import Path
from typing import Any, Mapping

from lavi_research_os.io import atomic_write_json
from lavi_research_os.models import FailureReason
from lavi_research_os.policy import (
    ProviderAudit,
    SubscriptionPolicyError,
    audit_codex,
    subscription_environment,
)
from lavi_research_os.runtime_contract import PROVIDER_CLI_VERSION_POLICY
from lavi_research_os.providers.base import (
    ProviderError,
    ProviderResponse,
    classify_provider_failure,
    reason_is_retryable,
    requested_model_matches,
    task_prompt,
)

from lavi_research_os.providers.content import recover_content
from failure_evidence358 import inspect_failure
from recording356 import (
    RecordedProcess,
    attempt_directory,
    bounded_text,
    record_no_call,
    run_recorded,
)


class CodexSubscriptionAdapter:
    provider_id = "openai-codex"
    adapter_contract_id = "codex-subscription-exec-v3"

    def __init__(
        self,
        binary: str = "codex",
        model: str | None = None,
        reasoning_effort: str = "high",
        timeout_seconds: int | None = None,
        allow_web_search: bool = False,
    ) -> None:
        if timeout_seconds is not None and not 60 <= timeout_seconds <= 7200:
            raise ValueError(
                "Codex attempt timeout must be between 60 and 7200 seconds"
            )
        self.binary = binary
        self.model = model
        self.requested_model = model or "chatgpt-subscription-default"
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.allow_web_search = allow_web_search
        self._audit: ProviderAudit | None = None
        self._audit_lock = threading.Lock()

    def _audited(self) -> ProviderAudit:
        with self._audit_lock:
            if self._audit is None:
                self._audit = audit_codex(self.binary)
            return self._audit

    def _audited_binary(self) -> str:
        return self._audited().binary

    def contract_identity(self) -> Mapping[str, Any]:
        audit = self._audited()
        return {
            "adapter_contract_id": self.adapter_contract_id,
            "provider_id": self.provider_id,
            "provider_cli_version": audit.version,
            "provider_cli_version_policy": PROVIDER_CLI_VERSION_POLICY,
            "requested_model": self.requested_model,
            "reasoning_effort": self.reasoning_effort,
            "attempt_timeout_seconds": self.timeout_seconds,
            "recording_contract": "private-cli-attempt-v1",
            "login_method": "chatgpt",
            "ephemeral": True,
            "sandbox": "read-only",
            "user_configuration": "ignored",
            "web_search": "live" if self.allow_web_search else "disabled",
            "identity_evidence": "bounded-recorded-stderr-header-v1",
        }

    def build_command(
        self, workspace: Path, schema_path: Path, output_path: Path
    ) -> list[str]:
        command = [self._audited_binary()]
        if self.allow_web_search:
            command.append("--search")
        command.extend(
            [
                "exec",
                "--ignore-user-config",
                "-c",
                'forced_login_method="chatgpt"',
                "-c",
                f'model_reasoning_effort="{self.reasoning_effort}"',
                "--ignore-rules",
                "--skip-git-repo-check",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "--color",
                "never",
                "-C",
                str(workspace),
            ]
        )
        if self.model:
            command.extend(["--model", self.model])
        command.append("-")
        return command

    def complete_json(
        self,
        *,
        task: str,
        payload: Mapping[str, Any],
        schema: Mapping[str, Any],
        workspace: Path,
    ) -> ProviderResponse:
        workspace.mkdir(parents=True, exist_ok=True)
        schema_path = workspace / "output-schema.json"
        output_path = workspace / "last-message.json"
        atomic_write_json(schema_path, schema)
        try:
            safe_env = subscription_environment()
            command = self.build_command(workspace, schema_path, output_path)
        except SubscriptionPolicyError as exc:
            record_no_call(
                workspace,
                reason="SUBSCRIPTION_PREFLIGHT",
                profile={
                    "provider": self.provider_id,
                    "requested_model": self.requested_model,
                },
            )
            reason = classify_provider_failure(str(exc))
            if reason is FailureReason.UNKNOWN:
                reason = FailureReason.SUBSCRIPTION_UNAVAILABLE
            raise ProviderError(
                "Codex subscription policy preflight failed",
                reason=reason,
                actual_provider=self.provider_id,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                "Codex subscription auth preflight timed out",
                reason=FailureReason.TIMEOUT,
                retryable=True,
                actual_provider=self.provider_id,
            ) from exc
        except OSError as exc:
            raise ProviderError(
                "Codex subscription CLI could not be started",
                reason=FailureReason.TOOL_FAILURE,
                retryable=True,
                actual_provider=self.provider_id,
            ) from exc
        try:
            result = run_recorded(
                command,
                input=task_prompt(task, payload),
                timeout=self.timeout_seconds,
                cwd=workspace,
                env=safe_env,
                profile=self.contract_identity(),
                extra_output=output_path,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                "Codex subscription CLI timed out",
                reason=FailureReason.TIMEOUT,
                retryable=True,
                actual_provider=self.provider_id,
            ) from exc
        except OSError as exc:
            raise ProviderError(
                "Codex subscription CLI could not be started",
                reason=FailureReason.TOOL_FAILURE,
                actual_provider=self.provider_id,
            ) from exc
        execution = dict(
            getattr(result, "report", {})
            or {
                "execution_status": "EXITED",
                "returncode": result.returncode,
            }
        )
        events = []
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, Mapping) and event.get("type") in (
                "error",
                "turn.failed",
            ):
                events.append(event)
        evidence = inspect_failure(
            events, stderr=result.stderr, returncode=result.returncode
        )
        reason = evidence.reason
        if execution["execution_status"] == "TIMEOUT":
            reason = FailureReason.TIMEOUT
        elif execution["execution_status"] == "CANCELLED":
            reason = FailureReason.USER_CANCELLED
        elif execution.get("limit_kind") == "ARGV_LIMIT":
            reason = FailureReason.LIMIT_EXCEEDED
        # Only the CLI diagnostic header can attest identity, never model-shaped
        # lines inside stdout scientific prose or the requested --model value.
        actual_model = _codex_model(_runtime_header(result))
        output = (
            bounded_text(result.directory / "last-message.bin")
            if isinstance(result, RecordedProcess)
            else bounded_text(output_path)
        )
        structured, flags = recover_content(output, schema, payload)
        observation = {
            "adapter_contract_id": self.adapter_contract_id,
            "provider_cli_version": self._audited().version,
            "trusted_identity_path": "stderr.runtime_header.model",
            "actual_model": actual_model,
        }
        content_status = (
            "RECOVERED" if flags else "STRUCTURED" if structured is not None else "NONE"
        )
        identity_ok = bool(
            actual_model and requested_model_matches(self.requested_model, actual_model)
        )
        atomic_write_json(
            attempt_directory(workspace) / "assessment.json",
            {
                "execution": execution,
                "failure_evidence": asdict(evidence),
                "operational_reason": reason,
                "identity_observation": observation,
                "content_status": content_status,
                "quality_flags": flags,
                "identity_accepted": identity_ok,
            },
        )
        error_fields: dict[str, Any] = dict(
            actual_provider=self.provider_id,
            actual_model=actual_model,
            identity_source="codex-runtime-metadata" if identity_ok else None,
            identity_observation=observation,
            execution=execution,
            failure_evidence=asdict(evidence),
            content_status=content_status,
        )
        if not identity_ok:
            failure_reason = (
                reason
                if structured is None and reason is not FailureReason.UNKNOWN
                else FailureReason.IDENTITY_UNVERIFIED
            )
            raise ProviderError(
                "Codex runtime identity is unverified",
                reason=failure_reason,
                retryable=reason_is_retryable(failure_reason),
                **error_fields,
            )
        if execution["execution_status"] in {
            "RECORDER_UNOBSERVABLE",
            "LAUNCH_UNCONFIRMED",
            "RECORDING_INCOMPLETE",
        }:
            raise ProviderError(
                "Codex attempt completion is unobservable",
                reason=FailureReason.UNKNOWN,
                **error_fields,
            )
        if structured is None or reason is FailureReason.USER_CANCELLED:
            if reason is FailureReason.UNKNOWN and not result.returncode:
                reason = FailureReason.INVALID_OUTPUT
            raise ProviderError(
                "Codex returned no recoverable accepted result",
                reason=reason,
                retryable=reason_is_retryable(reason) or evidence.provider_capacity,
                **error_fields,
            )
        if result.returncode or reason is not FailureReason.UNKNOWN:
            flags += ("PROVIDER_EXECUTION_DEGRADED",)
        return ProviderResponse(
            payload=structured,
            actual_provider=self.provider_id,
            actual_model=actual_model or "",
            identity_source="codex-runtime-metadata",
            identity_observation=observation,
            execution=execution,
            failure_evidence=asdict(evidence),
            content_status=content_status,
            quality_flags=flags,
        )


def _runtime_header(result: subprocess.CompletedProcess[str] | RecordedProcess) -> str:
    """Read complete diagnostic header lines independently of the full-stream cap.

    A retained multi-megabyte stderr can exceed the generic parse limit while
    its small, original runtime header remains intact. Never substitute stdout,
    requested argv, an incomplete line or scientific prose for this evidence.
    """
    if not isinstance(result, RecordedProcess):
        return result.stderr
    path = result.directory / "stderr.bin"
    if not path.is_file():
        return ""
    lines = []
    with path.open("rb") as handle:
        for _ in range(100):
            raw = handle.readline(4096)
            if not raw:
                break
            if not raw.endswith(b"\n"):
                return ""  # incomplete or oversized header, not an attested model
            line = raw.decode("utf-8", errors="replace")
            lines.append(line)
            if line.strip().lower() in {"user", "codex", "assistant", "thinking", "prompt:"}:
                break
    return "".join(lines)


def _codex_model(output: str) -> str | None:
    candidates = set()
    for line in output.splitlines()[:100]:
        if line.strip().lower() in {
            "user",
            "codex",
            "assistant",
            "thinking",
            "prompt:",
        }:
            break
        match = re.fullmatch(
            r"\s*model\s*:\s*([a-zA-Z0-9][a-zA-Z0-9._-]{1,95})\s*", line
        )
        if match and not match.group(1).lower().startswith(
            ("sk-", "token-", "secret-")
        ):
            candidates.add(match.group(1))
    return next(iter(candidates)) if len(candidates) == 1 else None
