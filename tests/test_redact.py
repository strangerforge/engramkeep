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


@pytest.mark.parametrize(
    "secret",
    [
        "sk_live_" + "a" * 24,
        "rk_test_" + "b" * 24,
        "glpat-" + "c" * 20,
        "npm_" + "d" * 36,
        "pypi-" + "e" * 36,
        "hf_" + "f" * 24,
        "dop_v1_" + "0" * 64,
        "GOCSPX-" + "g" * 24,
        "123456789:AA" + "h" * 33,
        "https://hooks.slack.com/services/T11111111/B22222222/" + "j" * 24,
        "https://discord.com/api/webhooks/123456789012345678/" + "k" * 32,
    ],
)
def test_extended_provider_tokens_and_webhooks_are_redacted(secret: str) -> None:
    result = redact_text(f"credential: {secret}")
    assert secret not in result
    assert REDACTED in result
    assert redact_text(result) == result


def test_quoted_spaces_azure_and_url_credentials_are_redacted() -> None:
    quoted = 'password = "correct horse battery staple"'
    quoted_out = redact_text(quoted)
    assert "correct horse" not in quoted_out
    assert 'password = "[REDACTED]"' == quoted_out
    assert redact_text(quoted_out) == quoted_out

    azure = "DefaultEndpointsProtocol=https;AccountName=demo;AccountKey=" + "A" * 44 + ";End=core"
    azure_out = redact_text(azure)
    assert "A" * 44 not in azure_out
    assert "AccountKey=[REDACTED];End=core" in azure_out

    db_url = "postgresql://appuser:supersecretpass@db.internal:5432/prod"
    url_out = redact_text(db_url)
    assert "supersecretpass" not in url_out
    assert "postgresql://appuser:[REDACTED]@db.internal:5432/prod" == url_out


@pytest.mark.parametrize(
    "secret_line",
    [
        "SECRET_KEY=django-insecure-1234567890",
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI123456",
        "ACCESS_KEY=customaccesskey123",
        "PRIVATE_KEY=supersecretvalue123",
        "DB_PASS=hunter2hunter2",
        "PASS=hunter2hunter2",
        "auth=supersecretvalue123",
        "credential=supersecretvalue123",
        "SharedAccessKey=supersecretvalue123",
        "Authorization: Basic dXNlcjpwYXNz",
        "redis://:sifre123@cache:6379",
        "ya29." + "a0AfH6SMBx" + "c" * 30,
        "SG." + "a" * 22 + "." + "b" * 43,
    ],
)
def test_audit_discovered_formats_are_redacted(secret_line: str) -> None:
    result = redact_text(secret_line)
    assert result != secret_line
    assert REDACTED in result
    assert redact_text(result) == result


@pytest.mark.parametrize("header", ["PGP PRIVATE KEY BLOCK", "OPENSSH PRIVATE KEY"])
def test_pgp_and_openssh_private_key_blocks_are_redacted(header: str) -> None:
    block = f"-----BEGIN {header}-----\nMIIEexample\n-----END {header}-----"
    result = redact_text(block)
    assert "MIIEexample" not in result
    assert result == REDACTED_PRIVATE_KEY


def test_benign_partial_words_are_not_redacted() -> None:
    text = "compass=12345678 bypass=12345678 author=someone"
    assert redact_text(text) == text


def test_private_key_redaction_resists_redos() -> None:
    import time

    payload = "-----BEGIN " + "PRIVATE KEY" + "-----" + "A" * 60_000
    started = time.perf_counter()
    assert redact_text(payload) == payload
    assert time.perf_counter() - started < 0.5
