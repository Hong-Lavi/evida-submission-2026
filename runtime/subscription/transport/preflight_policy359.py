"""Researcher-authorized byte-review advisories for one indexed Codex route.

No preflight/verification execution or exception handling lives here. The caller
runs the unchanged integrity checks first and saves their original report before
applying this derived dispatch policy. No content or source selection changes.
"""
from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

POLICY = 'codex-indexed-byte-review-advisory-v1'
BYTE_REVIEW_ISSUES = frozenset(('INITIAL_INDEX_TOO_LARGE', 'MANDATORY_ENTRY_POINTS_TOO_LARGE'))


def apply_input_size_policy(report: Mapping[str, Any], *, route_kind: str,
                            authorization_entry: Mapping[str, Any],
                            authorization_reference: str | None) -> dict[str, Any]:
    """Return an auditable derivative; never mutate/rewrite the preflight report.

    Unknown, inline, corpus-instruction and integrity issues remain blocking.
    Mixed byte/nonbyte issues retain INPUT_REVIEW_REQUIRED. A byte threshold is
    advisory only under the named route's explicit authorization and exact
    indexed original-value equality. Exceptions from upstream remain exceptions.
    """
    if 'input_size_review_policy' in report:
        raise ValueError('INPUT_SIZE_POLICY_ALREADY_APPLIED')
    original = deepcopy(dict(report))
    result = deepcopy(original)
    issues = original.get('issues')
    valid_issues = isinstance(issues, list) and all(isinstance(i, str) for i in issues)
    authorized = (route_kind == 'codex' and authorization_entry.get('kind') == 'codex'
                  and authorization_entry.get('input_size_review_limits') == 'advisory'
                  and isinstance(authorization_reference, str) and bool(authorization_reference.strip()))
    integrity_error = any(original.get(key) for key in
                          ('integrity_error', 'integrity_errors', 'error', 'errors', 'exception'))
    verified_indexed = (original.get('transport') == 'indexed'
                        and original.get('whole_original_value_equality') is True
                        and original.get('limits_are_local_review_thresholds_not_token_or_cost_limits') is True
                        and not integrity_error)
    eligible = bool(authorized and verified_indexed and valid_issues
                    and original.get('status') == 'INPUT_REVIEW_REQUIRED')
    advisories = [issue for issue in issues if issue in BYTE_REVIEW_ISSUES] if eligible else []
    if advisories:
        result['issues'] = [issue for issue in issues if issue not in BYTE_REVIEW_ISSUES]
        if not result['issues']:
            result['status'] = 'READY'
    encoded = json.dumps(original, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode()
    result['input_size_review_policy'] = {
        'policy': POLICY, 'route_kind': route_kind,
        'authorization_reference': authorization_reference,
        'explicit_advisory_authorized': authorized,
        'verified_indexed_original_equality': verified_indexed,
        'applied': bool(advisories), 'advisory_issues': advisories,
        'original_status': original.get('status'), 'original_issues': deepcopy(issues),
        'original_report_sha256': hashlib.sha256(encoded).hexdigest(),
        'original_report': original,
        'remaining_blocking_issues': deepcopy(result.get('issues')),
        'meaning': 'Only named local input-byte review thresholds can be advisories under explicit route authorization. All original bytes, thresholds and issues remain recorded. This is not a token, call, provider-response-time or scientific sufficiency policy; no other preflight failure is waived.',
    }
    return result
