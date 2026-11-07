"""Tests for the MCP stdio server."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from engramkeep import __version__, mcp_server
from engramkeep.store import Store

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": mcp_server.MCP_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1.0"},
    },
}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}


def run_server(
    messages: list[object],
    *,
    home: Path,
    allow_write: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """Run one server session over in-memory streams."""
    payload = b"".join(
        json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n" for message in messages
    )
    return run_raw(payload, home=home, allow_write=allow_write)


def run_raw(
    payload: bytes,
    *,
    home: Path,
    allow_write: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """Run one server session from raw bytes."""
    stdout = io.BytesIO()
    stderr = io.StringIO()
    exit_code = mcp_server.serve(
        home,
        allow_write=allow_write,
        stdin=io.BytesIO(payload),
        stdout=stdout,
        stderr=stderr,
    )
    assert exit_code == 0
    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    return responses, stderr.getvalue()


def call_tool(name: str, arguments: dict[str, Any], *, request_id: int = 2) -> dict[str, Any]:
    """Build a tools/call request."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def tool_payload(response: dict[str, Any]) -> dict[str, Any]:
    """Decode the JSON text content of a tool result."""
    content = response["result"]["content"]
    assert content[0]["type"] == "text"
    return json.loads(content[0]["text"])


def test_initialize_and_tools_list(home: Path) -> None:
    responses, _ = run_server(
        [
            INITIALIZE,
            INITIALIZED,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ],
        home=home,
    )

    assert len(responses) == 2
    initialized = responses[0]["result"]
    assert initialized["protocolVersion"] == mcp_server.MCP_PROTOCOL_VERSION
    assert initialized["serverInfo"] == {
        "name": "engramkeep",
        "version": __version__,
    }
    assert initialized["capabilities"] == {"tools": {"listChanged": False}}
    assert "untrusted" in initialized["instructions"]

    tools = {tool["name"]: tool for tool in responses[1]["result"]["tools"]}
    assert set(tools) == {
        "engramkeep_search",
        "engramkeep_show",
        "engramkeep_list",
        "engramkeep_recent",
        "engramkeep_doctor",
    }
    assert "engramkeep_remember" not in tools
    for tool in tools.values():
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["destructiveHint"] is False
        assert tool["inputSchema"]["type"] == "object"


def test_initialize_negotiates_protocol_version(home: Path) -> None:
    request = {
        **INITIALIZE,
        "params": {**INITIALIZE["params"], "protocolVersion": "2024-11-05"},
    }
    responses, _ = run_server([request], home=home)
    assert responses[0]["result"]["protocolVersion"] == mcp_server.MCP_PROTOCOL_VERSION


def test_write_tool_requires_explicit_opt_in(home: Path) -> None:
    responses, _ = run_server(
        [INITIALIZE, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}],
        home=home,
        allow_write=True,
    )
    tools = {tool["name"]: tool for tool in responses[1]["result"]["tools"]}
    assert "engramkeep_remember" in tools
    annotations = tools["engramkeep_remember"]["annotations"]
    assert annotations["readOnlyHint"] is False
    assert annotations["destructiveHint"] is False


def test_read_tools(store: Store, home: Path) -> None:
    store.remember("demo", "Use SQLite for local storage", tags=["database"])

    responses, _ = run_server(
        [
            INITIALIZE,
            call_tool("engramkeep_search", {"query": "sqlite"}, request_id=2),
            call_tool("engramkeep_show", {"project": "demo"}, request_id=3),
            call_tool("engramkeep_list", {"tag": "database"}, request_id=4),
            call_tool("engramkeep_recent", {"limit": 5}, request_id=5),
            call_tool("engramkeep_doctor", {}, request_id=6),
        ],
        home=home,
    )

    search = tool_payload(responses[1])
    assert search["hits"][0]["id"] == "demo"
    assert search["errors"] == []

    show = tool_payload(responses[2])
    assert show["id"] == "demo"
    assert "Use SQLite for local storage" in show["body"]

    listed = tool_payload(responses[3])
    assert [project["id"] for project in listed["projects"]] == ["demo"]

    recent = tool_payload(responses[4])
    assert any("remembered" in line for line in recent["entries"])

    doctor = tool_payload(responses[5])
    assert doctor["ok"] is True
    assert doctor["initialized"] is True


def test_remember_is_hidden_and_rejected_without_allow_write(store: Store, home: Path) -> None:
    responses, _ = run_server(
        [
            INITIALIZE,
            call_tool("engramkeep_remember", {"project": "demo", "decision": "No writes"}),
        ],
        home=home,
    )
    assert responses[1]["error"]["code"] == -32602
    assert "--allow-write" in responses[1]["error"]["message"]
    assert store.get_card("demo") is None


def test_remember_with_allow_write_redacts_secrets(store: Store, home: Path) -> None:
    secret = "sk-proj-" + "a" * 30
    responses, _ = run_server(
        [
            INITIALIZE,
            call_tool(
                "engramkeep_remember",
                {
                    "project": "demo",
                    "decision": f"Use the token {secret} for tests",
                    "tags": ["security"],
                },
            ),
        ],
        home=home,
        allow_write=True,
    )

    result = tool_payload(responses[1])
    assert responses[1]["result"]["isError"] is False
    assert result["created"] is True
    card = store.get_card("demo")
    assert card is not None
    assert secret not in card.body
    assert "[REDACTED]" in card.body
    assert card.tags == ["security"]


def test_missing_store_returns_tool_error(home: Path) -> None:
    responses, _ = run_server(
        [INITIALIZE, call_tool("engramkeep_search", {"query": "anything"})],
        home=home,
    )
    assert responses[1]["result"]["isError"] is True
    assert "engramkeep init" in responses[1]["result"]["content"][0]["text"]


def test_missing_project_returns_tool_error(store: Store, home: Path) -> None:
    responses, _ = run_server(
        [INITIALIZE, call_tool("engramkeep_show", {"project": "missing"})],
        home=home,
    )
    assert responses[1]["result"]["isError"] is True
    assert "project not found" in responses[1]["result"]["content"][0]["text"]


def test_project_traversal_is_a_tool_error(store: Store, home: Path) -> None:
    responses, _ = run_server(
        [INITIALIZE, call_tool("engramkeep_show", {"project": "../escape"})],
        home=home,
    )
    assert responses[1]["result"]["isError"] is True
    assert "invalid project name" in responses[1]["result"]["content"][0]["text"]
    assert not (home.parent / "escape.md").exists()


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({}, "missing required argument"),
        ({"query": 1}, "must be a string"),
        ({"query": "   "}, "must not be empty"),
        ({"query": "ok", "limit": 0}, "between 1 and 50"),
        ({"query": "ok", "limit": True}, "must be an integer"),
        ({"query": "ok", "tag": 5}, "must be a string"),
        ({"query": "ok", "extra": 1}, "unknown argument"),
    ],
)
def test_invalid_tool_arguments(
    store: Store,
    home: Path,
    arguments: dict[str, Any],
    expected: str,
) -> None:
    responses, _ = run_server(
        [INITIALIZE, call_tool("engramkeep_search", arguments)],
        home=home,
    )
    assert responses[1]["result"]["isError"] is True
    assert expected in responses[1]["result"]["content"][0]["text"]


def test_unknown_tool_is_a_jsonrpc_error(home: Path) -> None:
    responses, _ = run_server([INITIALIZE, call_tool("engramkeep_forget", {})], home=home)
    assert responses[1]["error"]["code"] == -32602
    assert "unknown tool" in responses[1]["error"]["message"]


def test_protocol_errors(home: Path) -> None:
    payload = b"".join(
        [
            b"{not json}\n",
            b'{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}\n',
            b'{"jsonrpc": "2.0", "id": 2, "method": "missing/method"}\n',
            b'{"jsonrpc": "1.0", "id": 3, "method": "ping"}\n',
            b'{"jsonrpc": "2.0", "id": 4, "method": "ping"}\n',
        ]
    )
    responses, _ = run_raw(payload, home=home)

    assert responses[0]["error"]["code"] == -32700
    assert responses[1]["error"]["code"] == -32002
    assert responses[2]["error"]["code"] == -32002
    assert responses[3]["error"]["code"] == -32600
    assert responses[4]["result"] == {}


def test_invalid_utf8_and_empty_batch(home: Path) -> None:
    payload = b"\xff\xfe\n[]\n"
    responses, _ = run_raw(payload, home=home)
    assert responses[0]["error"]["code"] == -32700
    assert responses[1]["error"]["code"] == -32600


def test_batch_requests_and_notifications(home: Path) -> None:
    batch = [
        INITIALIZE,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "method": "notifications/cancelled"},
    ]
    responses, _ = run_server([batch], home=home)
    assert len(responses) == 1
    assert len(responses[0]) == 2
    assert responses[0][0]["id"] == 1
    assert responses[0][1] == {"jsonrpc": "2.0", "id": 2, "result": {}}


def test_exit_notification_stops_the_server(home: Path) -> None:
    responses, _ = run_server(
        [
            INITIALIZE,
            {"jsonrpc": "2.0", "method": "exit"},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        ],
        home=home,
    )
    assert len(responses) == 1


def test_oversized_request_is_rejected(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "MAX_LINE_BYTES", 64)
    oversized = b'{"jsonrpc": "2.0", "id": 9, "method": "ping", "params": {"x": "' + b"a" * 100
    payload = oversized + b'"}}\n' + b'{"jsonrpc": "2.0", "id": 2, "method": "ping"}\n'
    responses, _ = run_raw(payload, home=home)
    assert responses[0]["error"]["code"] == -32600
    assert "maximum size" in responses[0]["error"]["message"]
    assert responses[1] == {"jsonrpc": "2.0", "id": 2, "result": {}}


def test_output_is_newline_delimited(home: Path) -> None:
    payload = json.dumps(INITIALIZE).encode("utf-8") + b"\n"
    stdout = io.BytesIO()
    exit_code = mcp_server.serve(
        home,
        stdin=io.BytesIO(payload),
        stdout=stdout,
        stderr=io.StringIO(),
    )
    assert exit_code == 0
    data = stdout.getvalue()
    assert data.endswith(b"\n")
    assert data.count(b"\n") == 1
    assert json.loads(data)["result"]["serverInfo"]["name"] == "engramkeep"


def test_status_reports_transport_and_writes() -> None:
    info = mcp_server.status()
    assert info["status"] == "available"
    assert info["transport"] == "stdio"
    assert info["protocol_version"] == mcp_server.MCP_PROTOCOL_VERSION
    assert "--allow-write" in info["writes"]
