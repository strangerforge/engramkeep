"""Regression tests for security audit findings and hardening fixes."""

from __future__ import annotations

import http.client
import io
import json
import sys
import threading
from pathlib import Path

import pytest

from engramkeep import dashboard
from engramkeep.errors import PathSafetyError
from engramkeep.mcp_server import MAX_BATCH_SIZE, McpServer
from engramkeep.models import parse_card
from engramkeep.paths import ensure_private_dir, is_link_or_junction
from engramkeep.redact import REDACTED, REDACTED_EMAIL, REDACTED_PRIVATE_KEY, redact_text
from engramkeep.store import Store


def test_remember_redacts_secrets_obfuscated_with_control_or_zwsp_chars(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.init()
    sample_api_val = "sk-ant-\u200bapi03-abcdefghijklmnopqrstuvwxyz123456"
    pw = "pass\x00word=supersecret123"
    email = "alice@\u200bexample.com"
    store.remember("proj", f"Use {sample_api_val} and {pw} or {email}")
    card = store.get_card("proj")
    assert card is not None
    assert "abcdefghijklmnopqrstuvwxyz" not in card.body
    assert "supersecret123" not in card.body
    assert "alice@example.com" not in card.body
    assert REDACTED in card.body
    assert REDACTED_EMAIL in card.body


def test_redact_text_handles_json_unclosed_quotes_and_extra_tokens() -> None:
    json_payload = '{"password": "mysecretvalue", "api_key": "my_api_key_value_99"}'
    redacted_json = redact_text(json_payload)
    assert "mysecretvalue" not in redacted_json
    assert "my_api_key_value_99" not in redacted_json

    unclosed = 'password="unclosed_secret_123'
    assert "unclosed_secret_123" not in redact_text(unclosed)

    aws_dummy = "ASIA" + "IOSFODNN7EXAMPLE"
    extra = (
        f"{aws_dummy} "
        "whsec_1234567890abcdef1234 "
        "xapp-1-A12345-67890-abcdef "
        "Authorization: ApiKey topsecretapikey99"
    )
    redacted_extra = redact_text(extra)
    assert aws_dummy not in redacted_extra
    assert "whsec_1234567890abcdef1234" not in redacted_extra
    assert "xapp-1-A12345-67890-abcdef" not in redacted_extra
    assert "topsecretapikey99" not in redacted_extra


def test_redact_text_handles_large_private_key_block() -> None:
    big_body = "A" * 25_000
    begin = "-----BEGIN " + "PRIVATE KEY-----"
    end = "-----END " + "PRIVATE KEY-----"
    pem = f"{begin}\n{big_body}\n{end}"
    result = redact_text(pem)
    assert result == REDACTED_PRIVATE_KEY


def test_parse_card_strips_control_chars_from_created_and_updated() -> None:
    raw = (
        "---\n"
        "id: demo\n"
        "title: Demo\n"
        "created: 2026-01-01\x1b[31mT00:00:00Z\n"
        "updated: 2026-01-02\u202eT00:00:00Z\n"
        "---\n\n"
        "# Demo\n\n## Decisions\n"
    )
    card = parse_card(raw)
    assert "\x1b" not in card.created
    assert "\u202e" not in card.updated


def test_mcp_server_rejects_oversized_batch_and_frames_untrusted_reads(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.init()
    store.remember("demo", "Keep API responses small")
    server = McpServer(store, allow_write=False, stdout=io.StringIO(), stderr=io.StringIO())

    batch = [
        {"jsonrpc": "2.0", "id": idx, "method": "tools/list", "params": {}}
        for idx in range(MAX_BATCH_SIZE + 1)
    ]
    out: list[dict[str, object]] = []
    server._send = out.append  # type: ignore[method-assign]
    server._handle_message(batch)
    assert len(out) == 1
    assert out[0]["error"]["code"] == -32600  # type: ignore[index]

    out.clear()
    server._handle_message(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        }
    )
    server._handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    out.clear()
    server._handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "engramkeep_show", "arguments": {"project": "demo"}},
        }
    )
    payload = json.loads(out[0]["result"]["content"][0]["text"])  # type: ignore[index]
    assert "_untrusted_data_notice" in payload


def test_dashboard_handles_non_ascii_token_and_post_auth_order(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.init()
    server = dashboard.create_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # 1. Non-ASCII byte in X-Engramkeep-Token should return 401 cleanly, not crash
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/api/overview", headers={"X-Engramkeep-Token": "\xe9\xe9\xe9"})
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 401
        conn.close()

        # 2. Unauthenticated POST to another /api/* route should return 401, not 405
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request(
            "POST",
            "/api/overview",
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 401
        conn.close()

        # 3. Tag longer than 64 chars should return 400
        long_tag = "a" * 65
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request(
            "GET",
            f"/api/search?q=test&tag={long_tag}",
            headers={"X-Engramkeep-Token": server.token},
        )
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 400
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_is_link_or_junction_and_ensure_private_dir_rejects_links(tmp_path: Path) -> None:
    target = tmp_path / "real_dir"
    target.mkdir()
    link = tmp_path / "link_dir"
    if sys.platform == "win32":
        import _winapi

        try:
            _winapi.CreateJunction(str(target), str(link))
        except OSError:
            pytest.skip("Unable to create NTFS junction on this environment")
    else:
        link.symlink_to(target)

    assert is_link_or_junction(link) is True
    with pytest.raises(PathSafetyError):
        ensure_private_dir(link)


def test_redact_custom_rule_blocks_redos_variants() -> None:
    from engramkeep.errors import ValidationError
    from engramkeep.redact import compile_custom_rule

    for bad_pattern in (
        r"(a|aa)+$",
        r"([a-z]{1,10})+$",
        r"((a+)b)+$",
        r"(.+)\1+",
    ):
        with pytest.raises(ValidationError):
            compile_custom_rule("evil", bad_pattern)

    # Legitimate flat pattern still compiles
    ok = compile_custom_rule("custom-id", r"\bPROJ-[0-9]{4,8}\b")
    assert ok.pattern.search("PROJ-12345") is not None


def test_sync_commit_refuses_pre_staged_non_allowlisted_files(tmp_path: Path) -> None:
    import shutil
    import subprocess

    from engramkeep.errors import StoreError
    from engramkeep.sync import sync_commit, sync_init

    git = shutil.which("git")
    assert git is not None
    home = tmp_path / "store"
    store = Store(home)
    store.init()
    sync_init(store)
    subprocess.run(  # noqa: S603
        [git, "-C", str(home), "config", "user.email", "ci@example.com"],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(home), "config", "user.name", "CI"],
        check=True,
    )

    excluded = home / ".env"
    excluded.write_text("DUMMY=1\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "-C", str(home), "add", "-f", ".env"],
        check=True,
    )

    store.remember("demo", "Use SQLite")
    with pytest.raises(StoreError, match="non-allowlisted"):
        sync_commit(store, apply=True)


def test_installer_restore_rejects_arbitrary_manifest_target(tmp_path: Path) -> None:
    from engramkeep.errors import InstallerError
    from engramkeep.installer import restore_installer_backup

    backup_root = tmp_path / "backups"
    run_dir = backup_root / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "payload.txt").write_text("SHOULD_NOT_WRITE", encoding="utf-8")
    outside = tmp_path / "outside_file.txt"
    outside.write_text("ORIGINAL", encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "operations": [
                    {
                        "agent": "claude-code",
                        "backup": "payload.txt",
                        "target": str(outside),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(InstallerError, match="non-agent target"):
        restore_installer_backup(backup_root, "run-1", dry_run=False)
    assert outside.read_text(encoding="utf-8") == "ORIGINAL"


def test_installer_toml_quote_rejects_newlines() -> None:
    from engramkeep.errors import InstallerError
    from engramkeep.installer import _resolve_mcp_command, _toml_quote

    with pytest.raises(InstallerError, match="control characters"):
        _toml_quote('engramkeep"\n[mcp_servers.evil]\ncommand = "sh')
    with pytest.raises(InstallerError, match="control characters"):
        _resolve_mcp_command(mcp_command="engramkeep\nevil")


def test_crypto_prunes_plaintext_backup_and_binds_aad_context(tmp_path: Path) -> None:
    from engramkeep.crypto import (
        crypto_available,
        decrypt_store,
        decrypt_text,
        encrypt_store,
        encrypt_text,
    )
    from engramkeep.errors import CryptoError

    if not crypto_available():
        pytest.skip("optional cryptography extra not installed")

    # AAD context binding prevents cross-file ciphertext swapping
    enc_a = encrypt_text("card A secret", "pass-123", context="projects/a.md")
    assert decrypt_text(enc_a, "pass-123", expected_context="projects/a.md") == "card A secret"
    with pytest.raises(CryptoError, match="context mismatch"):
        decrypt_text(enc_a, "pass-123", expected_context="projects/b.md")

    # encrypt_store removes plaintext backup by default after round-trip verification
    store = Store(tmp_path / "brain")
    store.init()
    store.remember("alpha", "Durable decision")
    res = encrypt_store(store.home, "pass-123", apply=True)
    assert res.backup_dir is None
    crypto_backups = store.home / "backups" / "crypto"
    if crypto_backups.exists():
        assert list(crypto_backups.iterdir()) == []

    # Decrypt still succeeds with context verification
    dec = decrypt_store(store.home, "pass-123", apply=True)
    assert "projects/alpha.md" in dec.files_processed
