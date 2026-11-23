"""Best-effort secret, PII, and configurable custom redaction for stored text.

Redaction is a safety net, not a guarantee. It catches common provider token
formats, credential assignments, private-key blocks, bearer tokens, email
addresses, personal home-directory usernames, and optional store-defined
custom patterns in ``redact.json`` (with ReDoS guardrails).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .errors import ValidationError
from .paths import is_link_or_junction

REDACTED = "[REDACTED]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"
REDACTED_PRIVATE_KEY = "[REDACTED_PRIVATE_KEY]"
REDACTED_USER = "[REDACTED_USER]"
REDACT_CONFIG_NAME = "redact.json"

MAX_CUSTOM_RULES = 50
MAX_RULE_PATTERN_CHARS = 256
MAX_CUSTOM_SCAN_CHARS = 262_144

_BACKREFERENCE_RE = re.compile(r"(?<!\\)\\[1-9]|(?<!\\)\(\?P=")


def _has_redos_risk(pattern_text: str) -> bool:
    """Detect common catastrophic-backtracking constructs in user regexes.

    Flags backreferences, nested quantifiers (including bounded ``{m,n}`` and
    nested groups), and alternation ``|`` inside any quantified group.
    """
    if _BACKREFERENCE_RE.search(pattern_text):
        return True

    # Track per-group state: [has_quantifier_inside, has_alternation_inside].
    stack: list[list[bool]] = []
    in_char_class = False
    i = 0
    n = len(pattern_text)
    while i < n:
        ch = pattern_text[i]
        if ch == "\\":
            i += 2
            continue
        if in_char_class:
            if ch == "]":
                in_char_class = False
            i += 1
            continue
        if ch == "[":
            in_char_class = True
            i += 1
            continue
        if ch == "(":
            stack.append([False, False])
            i += 1
            continue
        if ch == "|":
            if stack:
                stack[-1][1] = True
            i += 1
            continue
        if ch in "+*":
            if stack:
                stack[-1][0] = True
            i += 1
            continue
        if ch == "{":
            close = pattern_text.find("}", i + 1)
            if close != -1 and re.fullmatch(r"(?:\d+(?:,\d*)?|,\d+)", pattern_text[i + 1 : close]):
                if stack:
                    stack[-1][0] = True
                i = close + 1
                continue
        if ch == ")" and stack:
            has_quant, has_alt = stack.pop()
            # Check if the closed group itself is immediately quantified.
            j = i + 1
            group_quantified = False
            if j < n and pattern_text[j] in "+*":
                group_quantified = True
            elif j < n and pattern_text[j] == "{":
                close = pattern_text.find("}", j + 1)
                if close != -1 and re.fullmatch(
                    r"(?:\d+(?:,\d*)?|,\d+)", pattern_text[j + 1 : close]
                ):
                    group_quantified = True
            if group_quantified and (has_quant or has_alt):
                return True
            if stack and (has_quant or group_quantified):
                stack[-1][0] = True
        i += 1
    return False


_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?|OPENSSH PRIVATE KEY)-----"
    r".*?"
    r"-----END (?:[A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?|OPENSSH PRIVATE KEY)-----",
    re.DOTALL,
)
_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bwhsec_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bpypi-[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bdo[opr]_v1_[a-f0-9]{64}\b"),
    re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b[0-9]{8,11}:AA[A-Za-z0-9_-]{33}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bx(?:ox[baprs]|app|oxe)-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    # Modern AI & SaaS developer tokens (v1.2.0)
    re.compile(r"\bsbp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxai-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bpplx-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bre_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\blin_api_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bdapi[a-f0-9]{32}\b"),
    re.compile(r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"),
    re.compile(r"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+"),
)
_AUTH_HEADER = re.compile(
    r"(?i)\b((?:authorization\s*:\s*(?:bearer|basic|digest|token|apikey)|bearer))\s+([A-Za-z0-9._~+/=-]{6,})"
)
_KEY_NAMES = (
    r"(?:[A-Za-z0-9_]*(?:api[_-]?key|access[_-]?key|account_?key|secret[_-]?key"
    r"|private[_-]?key|shared_?access_?key|auth_?(?:token|key|pass)|credentials?"
    r"|db_?pass|secret|token|password|passphrase|passwd|pwd)"
    r"|\b(?:pass|auth))"
)
_URL_CREDENTIALS = re.compile(r"\b([A-Za-z][A-Za-z0-9+.-]*://[^:/@\s]*:)([^@\s]+)(@)")
_QUOTED_ASSIGNMENT = re.compile(
    rf"(?i)\b({_KEY_NAMES})(['\"]?\s*[:=]\s*)(['\"])([^'\"\r\n]{{6,}})\3"
)
_ASSIGNMENT = re.compile(rf"(?i)\b({_KEY_NAMES})(['\"]?\s*[:=]\s*['\"]?)([^\s'\";\r\n]{{6,}})")
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}\b"
)

_SAFE_USERNAMES = {
    "example",
    "user",
    "test",
    "public",
    "shared",
    "runner",
    "username",
    "default",
}
_USER_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Windows profile paths with spaces (e.g. C:\Users\<username> ...)
    re.compile(
        r"(?i)(\b[A-Z]:[\\/]+Users[\\/]+)([A-Za-z0-9._-]+(?: [A-Za-z0-9._-]+){1,2})(?=[\\/])"
    ),
    re.compile(r"(?i)(\b[A-Z]:[\\/]+Users[\\/]+)([A-Za-z0-9._-]+)"),
    re.compile(r"(/Users/)([A-Za-z0-9._-]+)"),
    re.compile(r"(/home/)([A-Za-z0-9._-]+)"),
)


@dataclass(frozen=True)
class CustomRedactionRule:
    """One validated, ReDoS-guarded custom redaction rule."""

    name: str
    pattern: re.Pattern[str]
    replacement: str = REDACTED


def compile_custom_rule(
    name: str,
    pattern_text: str,
    *,
    replacement: str = REDACTED,
) -> CustomRedactionRule:
    """Validate and compile one custom regex rule with ReDoS guardrails."""
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 64:
        raise ValidationError("redaction rule name must be 1..64 characters")
    if not isinstance(pattern_text, str) or not pattern_text.strip():
        raise ValidationError(f"redaction rule {clean_name!r} pattern must not be empty")
    if len(pattern_text) > MAX_RULE_PATTERN_CHARS:
        raise ValidationError(
            f"redaction rule {clean_name!r} exceeds {MAX_RULE_PATTERN_CHARS} character limit"
        )
    if _has_redos_risk(pattern_text):
        raise ValidationError(
            f"redaction rule {clean_name!r} rejected due to nested quantifiers or unsafe "
            "repetition (ReDoS risk)"
        )
    try:
        compiled = re.compile(pattern_text)
    except re.error as exc:
        raise ValidationError(f"invalid regex in redaction rule {clean_name!r}: {exc}") from exc
    if compiled.search(""):
        raise ValidationError(f"redaction rule {clean_name!r} must not match empty strings")
    clean_replacement = replacement.strip() if isinstance(replacement, str) else REDACTED
    return CustomRedactionRule(
        name=clean_name,
        pattern=compiled,
        replacement=clean_replacement or REDACTED,
    )


def load_redaction_rules(home: Path) -> tuple[CustomRedactionRule, ...]:
    """Load optional custom redaction rules from ``<home>/redact.json``."""
    config_path = home / REDACT_CONFIG_NAME
    if not config_path.exists():
        return ()
    if is_link_or_junction(config_path) or not config_path.is_file():
        raise ValidationError("refusing to read symlinked or non-regular redact.json")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read {REDACT_CONFIG_NAME}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError(f"{REDACT_CONFIG_NAME} must contain a JSON object")
    raw_rules = payload.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValidationError(f"{REDACT_CONFIG_NAME} 'rules' must be a list")
    if len(raw_rules) > MAX_CUSTOM_RULES:
        raise ValidationError(f"{REDACT_CONFIG_NAME} supports at most {MAX_CUSTOM_RULES} rules")

    compiled: list[CustomRedactionRule] = []
    for idx, item in enumerate(raw_rules):
        if not isinstance(item, dict):
            raise ValidationError(f"{REDACT_CONFIG_NAME} rule #{idx + 1} must be an object")
        name = str(item.get("name") or f"rule-{idx + 1}")
        pattern = item.get("pattern")
        if not isinstance(pattern, str):
            raise ValidationError(f"{REDACT_CONFIG_NAME} rule {name!r} missing string 'pattern'")
        replacement = str(item.get("replacement") or REDACTED)
        compiled.append(compile_custom_rule(name, pattern, replacement=replacement))
    return tuple(compiled)


def redact_user_paths(text: str) -> str:
    """Replace personal OS home-directory usernames with ``[REDACTED_USER]``."""
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        prefix, username = match.group(1), match.group(2)
        if username.lower() in _SAFE_USERNAMES:
            return match.group(0)
        return f"{prefix}{REDACTED_USER}"

    result = text
    for pattern in _USER_PATH_PATTERNS:
        result = pattern.sub(_replace, result)
    return result


def _apply_custom_rules(text: str, rules: tuple[CustomRedactionRule, ...]) -> str:
    result = text
    for rule in rules:
        replacement = rule.replacement

        def _literal_replace(_match: re.Match[str], rep: str = replacement) -> str:
            return rep

        result = rule.pattern.sub(_literal_replace, result)
    return result


def redact_text(
    text: str,
    *,
    extra_rules: Iterable[CustomRedactionRule] = (),
) -> str:
    """Return ``text`` with secrets, emails, personal user paths, and custom rules redacted."""
    if not text:
        return text

    result = (
        _PRIVATE_KEY.sub(REDACTED_PRIVATE_KEY, text)
        if "PRIVATE KEY" in text and "-----BEGIN " in text
        else text
    )
    for pattern in _TOKEN_PATTERNS:
        result = pattern.sub(REDACTED, result)
    if "://" in result:
        result = _URL_CREDENTIALS.sub(
            lambda match: f"{match.group(1)}{REDACTED}{match.group(3)}", result
        )
    result = _AUTH_HEADER.sub(lambda match: f"{match.group(1)} {REDACTED}", result)
    if ":" in result or "=" in result:
        result = _QUOTED_ASSIGNMENT.sub(
            lambda match: (
                f"{match.group(1)}{match.group(2)}{match.group(3)}{REDACTED}{match.group(3)}"
            ),
            result,
        )
        result = _ASSIGNMENT.sub(
            lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
            result,
        )
    if "@" in result:
        result = _EMAIL.sub(REDACTED_EMAIL, result)
    result = redact_user_paths(result)
    rules_tuple = tuple(extra_rules)
    if rules_tuple:
        if len(result) <= MAX_CUSTOM_SCAN_CHARS:
            result = _apply_custom_rules(result, rules_tuple)
        else:
            # Fail-closed on large inputs: scan in bounded overlapping chunks so
            # custom rules are never silently skipped.
            overlap = min(512, MAX_RULE_PATTERN_CHARS * 2)
            step = MAX_CUSTOM_SCAN_CHARS - overlap
            chunks: list[str] = []
            pos = 0
            length = len(result)
            while pos < length:
                end = min(length, pos + MAX_CUSTOM_SCAN_CHARS)
                chunk = _apply_custom_rules(result[pos:end], rules_tuple)
                chunks.append(chunk if pos == 0 else chunk[overlap:])
                if end >= length:
                    break
                pos += step
            result = "".join(chunks)
    return result


def contains_secret(
    text: str,
    *,
    extra_rules: Iterable[CustomRedactionRule] = (),
) -> bool:
    """Return True when redaction would change ``text``."""
    return redact_text(text, extra_rules=extra_rules) != text
