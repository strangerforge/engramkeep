"""Tests for secret and PII redaction."""

from __future__ import annotations

import pytest

from engramkeep.redact import (
    REDACTED,
    REDACTED_EMAIL,
    REDACTED_PRIVATE_KEY,
    contains_secret,
    redact_text,
)


def _openai_key() -> str:
    return "sk-" + "A" * 32


def _anthropic_key() -> str:
    return "sk-ant-" + "B" * 32


def _github_token() -> str:
    return "ghp_" + "C" * 36


def _google_key() -> str:
    return "AIza" + "D" * 35


def _aws_key() -> str:
    return "AKIA" + "E" * 16


def _slack_token() -> str:
    return "xoxb-" + "1" * 20


def _jwt() -> str:
    return "eyJ" + "a" * 20 + "." + "b" * 20 + "." + "c" * 20


def _private_key() -> str:
    begin = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"
    end = "-----END " + "RSA PRIVATE KEY" + "-----"
    return begin + "\nMIIEexample\n" + end


@pytest.mark.parametrize(
    ("secret", "label"),
    [
        (_openai_key(), REDACTED),
        (_anthropic_key(), REDACTED),
        (_github_token(), REDACTED),
        (_google_key(), REDACTED),
        (_aws_key(), REDACTED),
        (_slack_token(), REDACTED),
        (_jwt(), REDACTED),
        (_private_key(), REDACTED_PRIVATE_KEY),
    ],
)
def test_known_token_formats_are_redacted(secret: str, label: str) -> None:
    result = redact_text(f"value: {secret}")
    assert label in result
    assert secret not in result


def test_bearer_token_is_redacted() -> None:
    bearer_value = "abcdefghijklmnop"
    result = redact_text("Authorization: Bearer " + bearer_value)
    assert bearer_value not in result
    assert "Bearer " + REDACTED in result


def test_password_assignment_is_redacted() -> None:
    value = "hunter2hunter2"
    result = redact_text("password = " + value)
    assert value not in result
    assert REDACTED in result


def test_environment_style_key_is_redacted() -> None:
    key = "sk-" + "F" * 32
    result = redact_text("OPENAI_API_KEY=" + key)
    assert key not in result
    assert "OPENAI_API_KEY=" in result


def test_email_is_redacted() -> None:
    email = "user" + "@" + "example.com"
    result = redact_text("contact " + email)
    assert email not in result
    assert REDACTED_EMAIL in result


def test_redaction_is_idempotent() -> None:
    text = "key=" + _openai_key() + " contact " + "user" + "@" + "example.com"
    once = redact_text(text)
    assert redact_text(once) == once


def test_benign_text_is_unchanged() -> None:
    text = "The password policy is documented in docs/PRIVACY.md."
    assert redact_text(text) == text
    assert contains_secret(text) is False


def test_contains_secret_detects_known_value() -> None:
    assert contains_secret("token=" + _github_token()) is True
    assert contains_secret("plain project decision") is False
