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
_ANTHROPIC = re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")
_OPENAI = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")
_GITHUB = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b")
_GOOGLE = re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")
_AWS = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_SLACK = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_BEARER = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9._~+/=-]{12,})")
_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z0-9_]*(?:api[_-]?key|secret|token|password|passwd|pwd))"
    r"(\s*[:=]\s*)(['\"]?)([^\s'\"]{6,})\3"
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def redact_text(text: str) -> str:
    """Return ``text`` with common secrets and email addresses replaced."""
    if not text:
        return text

    result = _PRIVATE_KEY.sub(REDACTED_PRIVATE_KEY, text)
    result = _ANTHROPIC.sub(REDACTED, result)
    result = _OPENAI.sub(REDACTED, result)
    result = _GITHUB.sub(REDACTED, result)
    result = _GOOGLE.sub(REDACTED, result)
    result = _AWS.sub(REDACTED, result)
    result = _SLACK.sub(REDACTED, result)
    result = _JWT.sub(REDACTED, result)
    result = _BEARER.sub(lambda match: f"{match.group(1)} {REDACTED}", result)
    result = _ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}{REDACTED}{match.group(3)}",
        result,
    )
    result = _EMAIL.sub(REDACTED_EMAIL, result)
    return result


def contains_secret(text: str) -> bool:
    """Return True when redaction would change ``text``."""
    return redact_text(text) != text
