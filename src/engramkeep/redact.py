"""Best-effort secret and PII redaction for text written to memory.

Redaction is a safety net, not a guarantee. It catches common token formats,
credential assignments, private-key blocks, bearer tokens, and email
addresses. Encoded, split, or novel secret formats can still slip through.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"
REDACTED_PRIVATE_KEY = "[REDACTED_PRIVATE_KEY]"

_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bpypi-[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bdo[opr]_v1_[a-f0-9]{64}\b"),
    re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b[0-9]{8,11}:AA[A-Za-z0-9_-]{33}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"),
    re.compile(r"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+"),
)
_BEARER = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9._~+/=-]{12,})")
_KEY_NAMES = (
    r"[A-Za-z0-9_]*(?:api[_-]?key|account_?key|auth_?token|secret"
    r"|token|password|passphrase|passwd|pwd)"
)
_URL_CREDENTIALS = re.compile(r"\b([A-Za-z][A-Za-z0-9+.-]*://[^:/@\s]+:)([^@\s]+)(@)")
_QUOTED_ASSIGNMENT = re.compile(rf"(?i)\b({_KEY_NAMES})(\s*[:=]\s*)(['\"])([^'\"\r\n]{{6,}})\3")
_ASSIGNMENT = re.compile(rf"(?i)\b({_KEY_NAMES})(\s*[:=]\s*)([^\s'\";]{{6,}})")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def redact_text(text: str) -> str:
    """Return ``text`` with common secrets and email addresses replaced."""
    if not text:
        return text

    result = _PRIVATE_KEY.sub(REDACTED_PRIVATE_KEY, text)
    for pattern in _TOKEN_PATTERNS:
        result = pattern.sub(REDACTED, result)
    result = _URL_CREDENTIALS.sub(
        lambda match: f"{match.group(1)}{REDACTED}{match.group(3)}", result
    )
    result = _BEARER.sub(lambda match: f"{match.group(1)} {REDACTED}", result)
    result = _QUOTED_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}{REDACTED}{match.group(3)}",
        result,
    )
    result = _ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
        result,
    )
    result = _EMAIL.sub(REDACTED_EMAIL, result)
    return result


def contains_secret(text: str) -> bool:
    """Return True when redaction would change ``text``."""
    return redact_text(text) != text
