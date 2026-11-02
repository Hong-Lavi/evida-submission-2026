"""Failure classification uses control fields, never successful scientific prose."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from lavi_research_os.models import FailureReason


@dataclass(frozen=True, slots=True)
class FailureEvidence:
    reason: FailureReason = FailureReason.UNKNOWN
    source: str = "none"
    locator: str | None = None
    confidence: str = "unknown"
    evidence_sha256: str | None = None
    reset_at: str | None = None
    retry_after_seconds: float | None = None
    quota_scope: str = "unknown"
    provider_capacity: bool = False


_CODES = {
    "authentication_error": FailureReason.AUTH,
    "unauthorized": FailureReason.AUTH,
    "permission_error": FailureReason.PERMISSION,
    "permission_denied": FailureReason.PERMISSION,
    "rate_limit_error": FailureReason.RATE_LIMIT,
    "rate_limit_exceeded": FailureReason.RATE_LIMIT,
    "insufficient_quota": FailureReason.QUOTA,
    "usage_limit_exceeded": FailureReason.QUOTA,
    "context_length_exceeded": FailureReason.LIMIT_EXCEEDED,
    "max_output_tokens": FailureReason.LIMIT_EXCEEDED,
    "error_max_output_tokens": FailureReason.LIMIT_EXCEEDED,
    "error_max_turns": FailureReason.LIMIT_EXCEEDED,
    "error_max_structured_output_retries": FailureReason.INVALID_OUTPUT,
    "model_not_found": FailureReason.MODEL_UNAVAILABLE,
}


def classify_error_message(text: str) -> FailureReason:
    """Conservative fallback for a diagnostic, with explicit exhaustion shapes."""
    value = " ".join(text.lower().split()).strip()
    if not value or value.startswith(('"', "'", "`", ">")):
        return FailureReason.UNKNOWN
    value = re.sub(r"^(?:error|fatal|api error)\s*:\s*", "", value)
    value = re.sub(r"^(?:claude(?: code)?|codex) (?:is )?", "", value)
    value = value.removeprefix("the ")
    if value in _CODES:
        return _CODES[value]
    # Require a diagnostic at the start, not a word somewhere in a paper.
    rules = (
        (
            r"(?:webfetch |websearch )?(?:permission denied|permission denial|tool use denied|tool_use_denied|not allowed to use tool|permission (?:has not been granted|was denied))",
            FailureReason.PERMISSION,
        ),
        (
            r"(?:safety refusal|content safety(?: policy)? (?:blocked|refusal)|blocked (?:for safety|by the safety)|i (?:can't|cannot) assist with|unable to comply with this request|cannot provide assistance with)",
            FailureReason.SAFETY,
        ),
        (
            r"(?:not logged in|authentication failed|unauthorized(?:\b|$)|invalid oauth|oauth expired|please log in|login required)",
            FailureReason.AUTH,
        ),
        (
            r"(?:subscription unavailable|subscription required|max plan required|not available on your plan)",
            FailureReason.SUBSCRIPTION_UNAVAILABLE,
        ),
        (
            r"(?:rate[ _-]limit(?:ed| exceeded| reached| error)?|too many requests|status 429)",
            FailureReason.RATE_LIMIT,
        ),
        (
            r"(?:(?:subscription )?quota(?:[ _-]+limit)?(?:[ _-]+(?:has|have|is|was|were|been))*[ _-]+(?:exceeded|exhausted|depleted|reached|hit)|usage[ _-]+limit(?:[ _-]+quota)?(?:[ _-]+(?:has|have|is|was|were|been))*[ _-]+(?:exceeded|exhausted|depleted|reached|hit)|you(?:'ve| have) (?:hit|reached|exceeded) your (?:(?:subscription|usage|session) )?limit|insufficient[ _-]+quota|out of (?:(?:subscription|usage) )?quota|no (?:(?:subscription|usage) )?quota (?:remaining|left)|quota (?:remaining|left)\s*[:=]?\s*0\b)",
            FailureReason.QUOTA,
        ),
        (
            r"(?:selected model is at capacity\.(?: please try a different model\.)?$|model unavailable|model_unavailable|unknown model|model is not available|invalid model)",
            FailureReason.MODEL_UNAVAILABLE,
        ),
        (
            r"(?:tool failed|tool_failure|websearch failed|webfetch failed)",
            FailureReason.TOOL_FAILURE,
        ),
        (r"(?:request )?(?:timed out|timeout)\b", FailureReason.TIMEOUT),
        (
            r"(?:cancelled by user|canceled by user|user cancelled)",
            FailureReason.USER_CANCELLED,
        ),
        (
            r"(?:context (?:length|window|size).*(?:exceed|limit)|prompt (?:is )?too (?:long|large)|input (?:is )?too (?:long|large)|output (?:token )?limit|maximum output tokens|argument list too long|claude's response exceeded the [0-9]+ output token maximum\.)",
            FailureReason.LIMIT_EXCEEDED,
        ),
    )
    for pattern, reason in rules:
        if re.match(pattern, value):
            return reason
    return FailureReason.UNKNOWN


def _evidence(value: Any, source: str, locator: str) -> FailureEvidence:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    reason = FailureReason.UNKNOWN
    reset = None
    retry = None
    scope = "unknown"
    if isinstance(value, Mapping):
        for key in ("code", "type", "subtype"):
            reason = _CODES.get(str(value.get(key)), FailureReason.UNKNOWN)
            if reason is not FailureReason.UNKNOWN:
                break
        if reason is FailureReason.UNKNOWN:
            reason = classify_error_message(
                str(value.get("message", value.get("result", "")))
            )
        # Only explicit, bounded machine-readable values. Never infer a reset.
        raw_reset = value.get("reset_at")
        if isinstance(raw_reset, str) and re.fullmatch(
            r"[0-9T:Z+. -]{8,40}", raw_reset
        ):
            reset = raw_reset
        raw_retry = value.get("retry_after_seconds")
        if (
            isinstance(raw_retry, (int, float))
            and not isinstance(raw_retry, bool)
            and 0 <= raw_retry <= 604800
        ):
            retry = float(raw_retry)
        if value.get("quota_scope") in ("session", "daily", "weekly"):
            scope = str(value["quota_scope"])
    else:
        reason = classify_error_message(str(value))
    return FailureEvidence(
        reason,
        source,
        locator,
        "high" if source == "structured" else "low",
        hashlib.sha256(text.encode()).hexdigest(),
        reset,
        retry,
        scope,
        reason is FailureReason.MODEL_UNAVAILABLE and bool(re.fullmatch(
            r"(?:error:\s*)?selected model is at capacity\.(?: please try a different model\.)?",
            " ".join((str(value.get("message", "")) if isinstance(value, Mapping) else str(value)).lower().split()),
        )),
    )


def inspect_failure(
    events: Iterable[Mapping[str, Any]],
    *,
    stderr: str = "",
    returncode: int = 0,
) -> FailureEvidence:
    fatal: list[FailureEvidence] = []
    denials: list[FailureEvidence] = []
    for index, event in enumerate(events):
        prefix = f"stdout.event[{index}]"
        kind = event.get("type")
        if kind in ("result", "error", "turn.failed") or kind is None:
            if kind in ("error", "turn.failed") or event.get("is_error") is True:
                value = event.get("error", event)
                evidence = _evidence(
                    value,
                    "structured",
                    prefix + (".error" if "error" in event else ".result"),
                )
                fatal.append(evidence)
            denied = event.get("permission_denials")
            if isinstance(denied, list) and denied:
                denials.append(
                    FailureEvidence(
                        FailureReason.PERMISSION,
                        "structured",
                        prefix + ".permission_denials",
                        "high",
                        hashlib.sha256(
                            json.dumps(denied, sort_keys=True).encode()
                        ).hexdigest(),
                    )
                )
    if fatal:
        # Terminal errors win over incidental denied tools. A recognized typed
        # cause wins over generic envelopes, irrespective of scientific content.
        return next(
            (x for x in reversed(fatal) if x.reason is not FailureReason.UNKNOWN),
            fatal[-1],
        )
    if denials:
        return denials[-1]
    if returncode:
        for index, line in enumerate(stderr.splitlines()):
            evidence = _evidence(line, "plaintext_stderr", f"stderr.line[{index + 1}]")
            if evidence.reason is not FailureReason.UNKNOWN:
                return evidence
    return FailureEvidence()


def classify_failure_text(text: str) -> FailureReason:
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return classify_error_message(text)
    if isinstance(value, Mapping):
        return inspect_failure((value,)).reason
    return FailureReason.UNKNOWN
