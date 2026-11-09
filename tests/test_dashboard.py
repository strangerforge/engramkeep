"""Tests for the hardened local dashboard."""

from __future__ import annotations

import http.client
import io
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from engramkeep import dashboard
from engramkeep.errors import StoreError
from engramkeep.store import Store


@contextmanager
def running_dashboard(
    home: Path,
    *,
    allow_write: bool = False,
) -> Iterator[dashboard.DashboardServer]:
    """Run a dashboard server on an ephemeral loopback port."""
    server = dashboard.create_server(
        home,
        port=0,
        allow_write=allow_write,
        stderr=io.StringIO(),
    )
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        daemon=True,
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(
    server: dashboard.DashboardServer,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: bytes | str | None = None,
    headers: dict[str, str] | None = None,
    host: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Send one HTTP request to a test dashboard."""
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    connection.putheader("Host", host or f"127.0.0.1:{server.port}")
    if token is not None:
        connection.putheader(dashboard.TOKEN_HEADER, token)
    for key, value in (headers or {}).items():
        connection.putheader(key, value)
    if body is not None:
        if isinstance(body, str):
            body = body.encode("utf-8")
        connection.putheader("Content-Length", str(len(body)))
    connection.endheaders(body)
    response = connection.getresponse()
    data = response.read()
    response_headers = {key.lower(): value for key, value in response.getheaders()}
    status = response.status
    connection.close()
    return status, response_headers, data


def json_body(data: bytes) -> dict[str, object]:
    """Decode a JSON response body."""
    return json.loads(data)


def test_status_reports_hardening() -> None:
    info = dashboard.status()
    assert info["status"] == "available"
    assert info["bind"] == "127.0.0.1"
    assert "token" in info["auth"]
    assert "--allow-write" in info["writes"]
    assert info["csp"] == "strict"


def test_shell_and_assets_are_safe(store: Store) -> None:
    with running_dashboard(store.home) as server:
        status, headers, body = request(server, "GET", "/")
        assert status == 200
        assert headers["content-type"].startswith("text/html")
        assert "default-src 'none'" in headers["content-security-policy"]
        assert headers["x-frame-options"] == "DENY"
        assert headers["cache-control"] == "no-store"
        assert b'<script src="/app.js"' in body
        assert b"<script>" not in body
        assert b"<style" not in body
        assert server.token.encode() not in body

        status, headers, body = request(server, "GET", "/app.js")
        assert status == 200
        assert headers["content-type"].startswith("text/javascript")
        assert b"innerHTML" not in body
        assert b"textContent" in body

        status, headers, _ = request(server, "GET", "/style.css")
        assert status == 200
        assert headers["content-type"].startswith("text/css")


def test_api_requires_the_session_token(store: Store) -> None:
    with running_dashboard(store.home) as server:
        status, headers, body = request(server, "GET", "/api/cards")
        assert status == 401
        assert headers["www-authenticate"] == "EngramkeepToken"
        assert "error" in json_body(body)

        invalid = "wrong"
        status, _, _ = request(server, "GET", "/api/cards", token=invalid)
        assert status == 401

        status, _, body = request(server, "GET", "/api/cards", token=server.token)
        assert status == 200
        assert json_body(body)["projects"] == []


def test_api_reads(store: Store) -> None:
    store.remember("demo", "Use SQLite for local storage", tags=["database"])

    with running_dashboard(store.home) as server:
        status, _, body = request(server, "GET", "/api/cards", token=server.token)
        assert status == 200
        projects = json_body(body)["projects"]
        assert projects[0]["id"] == "demo"
        assert projects[0]["tags"] == ["database"]

        status, _, body = request(server, "GET", "/api/cards/demo", token=server.token)
        assert status == 200
        assert "Use SQLite for local storage" in json_body(body)["card"]["body"]

        status, _, body = request(
            server,
            "GET",
            "/api/search?q=sqlite",
            token=server.token,
        )
        assert status == 200
        assert json_body(body)["hits"][0]["id"] == "demo"

        status, _, body = request(
            server,
            "GET",
            "/api/search?q=sqlite&tag=database",
            token=server.token,
        )
        assert status == 200
        assert len(json_body(body)["hits"]) == 1

        status, _, body = request(server, "GET", "/api/recent?limit=5", token=server.token)
        assert status == 200
        assert any("remembered" in line for line in json_body(body)["entries"])

        status, _, body = request(server, "GET", "/api/doctor", token=server.token)
        assert status == 200
        assert json_body(body)["report"]["ok"] is True


def test_api_rejects_bad_query_parameters(store: Store) -> None:
    with running_dashboard(store.home) as server:
        for path in (
            "/api/search",
            "/api/search?q=",
            "/api/search?q=x&limit=0",
            "/api/search?q=x&limit=abc",
            "/api/recent?limit=999",
        ):
            status, _, body = request(server, "GET", path, token=server.token)
            assert status == 400, path
            assert "error" in json_body(body)


def test_card_path_traversal_is_rejected(store: Store) -> None:
    with running_dashboard(store.home) as server:
        status, _, body = request(
            server,
            "GET",
            "/api/cards/%2e%2e%2fescape",
            token=server.token,
        )
        assert status == 400
        assert "invalid project name" in json_body(body)["error"]
        assert not (store.home.parent / "escape.md").exists()


def test_invalid_host_is_rejected(store: Store) -> None:
    with running_dashboard(store.home) as server:
        status, _, body = request(server, "GET", "/", host="evil.example")
        assert status == 403
        assert "Host" in json_body(body)["error"]

        status, _, _ = request(
            server,
            "GET",
            "/api/cards",
            token=server.token,
            host="evil.example",
        )
        assert status == 403


def test_writes_are_disabled_by_default(store: Store) -> None:
    with running_dashboard(store.home) as server:
        payload = json.dumps({"project": "demo", "decision": "No writes", "confirm": True})
        status, _, body = request(
            server,
            "POST",
            "/api/remember",
            token=server.token,
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        assert status == 403
        assert "--allow-write" in json_body(body)["error"]
        assert store.get_card("demo") is None


def test_remember_requires_explicit_confirmation(store: Store) -> None:
    with running_dashboard(store.home, allow_write=True) as server:
        status, _, body = request(
            server,
            "POST",
            "/api/remember",
            token=server.token,
            body=json.dumps({"project": "demo", "decision": "Use SQLite"}),
            headers={"Content-Type": "application/json"},
        )
        assert status == 400
        assert "confirmation" in json_body(body)["error"]
        assert store.get_card("demo") is None

        status, _, _ = request(
            server,
            "POST",
            "/api/remember",
            token=server.token,
            body=json.dumps({"project": "demo", "decision": "Use SQLite", "confirm": False}),
            headers={"Content-Type": "application/json"},
        )
        assert status == 400

        status, _, body = request(
            server,
            "POST",
            "/api/remember",
            token=server.token,
            body=json.dumps(
                {
                    "project": "demo",
                    "decision": "Use SQLite",
                    "tags": ["database"],
                    "confirm": True,
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        result = json_body(body)
        assert result["created"] is True
        card = store.get_card("demo")
        assert card is not None
        assert "Use SQLite" in card.body
        assert card.tags == ["database"]


def test_remember_redacts_secrets(store: Store) -> None:
    secret = "sk-proj-" + "a" * 30
    with running_dashboard(store.home, allow_write=True) as server:
        status, _, _ = request(
            server,
            "POST",
            "/api/remember",
            token=server.token,
            body=json.dumps(
                {
                    "project": "demo",
                    "decision": f"Use the token {secret} for tests",
                    "confirm": True,
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        card = store.get_card("demo")
        assert card is not None
        assert secret not in card.body
        assert "[REDACTED]" in card.body


def test_get_cannot_mutate(store: Store) -> None:
    with running_dashboard(store.home, allow_write=True) as server:
        status, headers, _ = request(
            server,
            "GET",
            "/api/remember",
            token=server.token,
        )
        assert status == 405
        assert headers["allow"] == "POST"
        assert store.get_card("demo") is None


def test_post_to_read_endpoint_is_rejected(store: Store) -> None:
    with running_dashboard(store.home) as server:
        status, headers, _ = request(
            server,
            "POST",
            "/api/cards",
            token=server.token,
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert status == 405
        assert headers["allow"] == "GET"


def test_cross_origin_post_is_rejected(store: Store) -> None:
    with running_dashboard(store.home, allow_write=True) as server:
        status, _, body = request(
            server,
            "POST",
            "/api/remember",
            token=server.token,
            body=json.dumps({"project": "demo", "decision": "Cross origin", "confirm": True}),
            headers={
                "Content-Type": "application/json",
                "Origin": "http://evil.example",
            },
        )
        assert status == 403
        assert "cross-origin" in json_body(body)["error"]
        assert store.get_card("demo") is None


def test_post_requires_json_content_type(store: Store) -> None:
    with running_dashboard(store.home, allow_write=True) as server:
        status, _, body = request(
            server,
            "POST",
            "/api/remember",
            token=server.token,
            body="project=demo",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert status == 415
        assert "application/json" in json_body(body)["error"]


def test_post_body_limits(store: Store) -> None:
    with running_dashboard(store.home, allow_write=True) as server:
        status, _, body = request(
            server,
            "POST",
            "/api/remember",
            token=server.token,
            headers={"Content-Type": "application/json"},
        )
        assert status == 411
        assert "Content-Length" in json_body(body)["error"]

        status, _, body = request(
            server,
            "POST",
            "/api/remember",
            token=server.token,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(dashboard.MAX_BODY_BYTES + 1),
            },
        )
        assert status == 413
        assert "too large" in json_body(body)["error"]


def test_unknown_paths_and_methods(store: Store) -> None:
    with running_dashboard(store.home) as server:
        status, _, _ = request(server, "GET", "/nope")
        assert status == 404

        status, _, _ = request(server, "GET", "/api/nope", token=server.token)
        assert status == 404

        status, headers, _ = request(server, "OPTIONS", "/api/cards", token=server.token)
        assert status == 405
        assert headers["allow"] == "GET, POST"


def test_cross_origin_get_has_no_cors_headers(store: Store) -> None:
    with running_dashboard(store.home) as server:
        status, headers, _ = request(
            server,
            "GET",
            "/api/cards",
            token=server.token,
            headers={"Origin": "http://evil.example"},
        )
        assert status == 200
        assert "access-control-allow-origin" not in headers


def test_create_server_rejects_an_uninitialized_store(home: Path) -> None:
    with pytest.raises(StoreError, match="engramkeep init"):
        dashboard.create_server(home, port=0)


def test_create_server_rejects_an_invalid_port(home: Path) -> None:
    with pytest.raises(StoreError, match="port must be between"):
        dashboard.create_server(home, port=70_000)
