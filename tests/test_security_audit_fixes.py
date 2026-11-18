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

    extra = (
        "ASIAIOSFODNN7EXAMPLE "
        "whsec_1234567890abcdef1234 "
        "xapp-1-A12345-67890-abcdef "
        "Authorization: ApiKey topsecretapikey99"
    )
    redacted_extra = redact_text(extra)
    assert "ASIAIOSFODNN7EXAMPLE" not in redacted_extra
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
