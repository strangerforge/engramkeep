"""Tests for Phase 2 enhancements: layered memory, lifecycle, MCP, installer, dashboard."""

from __future__ import annotations

import http.client
import io
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from engramkeep import dashboard, mcp_server
from engramkeep.cli import main
from engramkeep.config import PROJECT_STORE_DIR, find_project_store
from engramkeep.errors import ValidationError
from engramkeep.installer import install_agents
from engramkeep.store import LayeredStore, Store

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


def run_server(
    messages: list[object],
    *,
    home: Path,
    allow_write: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    payload = b"".join(
        json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n" for message in messages
    )
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
    return [json.loads(line) for line in stdout.getvalue().splitlines()], stderr.getvalue()


def call_tool(name: str, arguments: dict[str, Any], *, request_id: int = 2) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def tool_payload(response: dict[str, Any]) -> dict[str, Any]:
    return json.loads(response["result"]["content"][0]["text"])


@contextmanager
def running_dashboard(
    home: Path,
    *,
    allow_write: bool = False,
) -> Iterator[dashboard.DashboardServer]:
    server = dashboard.create_server(home, port=0, allow_write=allow_write, stderr=io.StringIO())
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
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
) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    conn.putheader("Host", f"127.0.0.1:{server.port}")
    if token is not None:
        conn.putheader(dashboard.TOKEN_HEADER, token)
    for key, value in (headers or {}).items():
        conn.putheader(key, value)
    if body is not None:
        raw = body.encode("utf-8") if isinstance(body, str) else body
        conn.putheader("Content-Length", str(len(raw)))
    else:
        raw = None
    conn.endheaders(raw)
    resp = conn.getresponse()
    data = resp.read()
    resp_headers = {k.lower(): v for k, v in resp.getheaders()}
    status = resp.status
    conn.close()
    return status, resp_headers, data


def json_body(data: bytes) -> dict[str, Any]:
    return json.loads(data)


def test_layered_memory_project_overrides_global_and_merges_fixes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    global_home = tmp_path / "global"
    project_root = tmp_path / "repo"
    nested = project_root / "src" / "pkg"
    nested.mkdir(parents=True)
    local_home = project_root / PROJECT_STORE_DIR

    global_store = Store(global_home)
    global_store.init()
    global_store.remember("shared-api", "Global decision about REST")
    global_store.remember("global-only", "Use SQLite globally")
    global_store.record_fix("Global port error", "Bind 127.0.0.1", project="global-app")

    project_store = Store(local_home)
    project_store.init()
    project_store.remember("shared-api", "Project override decision about gRPC")
    project_store.remember("repo-only", "Use SQLite in this repo")
    project_store.record_fix("Repo build error", "Run clean build", project="repo-app")

    assert find_project_store(nested) == local_home.resolve()

    layered = LayeredStore(global_store, project_store)
    assert layered.is_layered is True

    found = layered.get_card("shared-api")
    assert found is not None
    card, source = found
    assert source == "project"
    assert "gRPC" in card.body

    hits, errors = layered.search("sqlite")
    assert errors == []
    by_id = {hit.id: hit.source for hit in hits}
    assert by_id == {"repo-only": "project", "global-only": "global"}

    fixes = layered.search_fixes(None, limit=10)
    assert {hit.entry.project for hit in fixes} == {"repo-app", "global-app"}

    # CLI integration with explicit --project-store
    code = main(
        [
            "--home",
            str(global_home),
            "search",
            "sqlite",
            "--project-store",
            str(local_home),
            "--json",
        ]
    )
    assert code == 0
    cli_hits = json.loads(capsys.readouterr().out)
    assert {item["id"]: item["source"] for item in cli_hits} == {
        "repo-only": "project",
        "global-only": "global",
    }


def test_decision_lifecycle_supersede_untag_and_remove_decision(
    cli_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "remember",
                "backend",
                "Use SQLite for primary database",
                "--tag",
                "database",
                "--tag",
                "draft",
            ]
        )
        == 0
    )
    assert main(["remember", "backend", "Keep endpoints stateless"]) == 0
    capsys.readouterr()

    # Supersede with reason preserves ADR history under ## Superseded
    code = main(
        [
            "supersede",
            "backend",
            "--old",
            "SQLite",
            "--new",
            "Use PostgreSQL for primary database",
            "--reason",
            "Need multi-writer concurrency",
            "--json",
        ]
    )
    assert code == 0
    sup = json.loads(capsys.readouterr().out)
    assert sup["old_decision"] == "Use SQLite for primary database"
    assert "PostgreSQL" in sup["card"]["body"]
    assert "## Superseded" in sup["card"]["body"]
    assert "~~Use SQLite for primary database~~" in sup["card"]["body"]
    assert "Need multi-writer concurrency" in sup["card"]["body"]

    # Untag removes only the selected tag
    code = main(["untag", "backend", "--tag", "draft", "--json"])
    assert code == 0
    untagged = json.loads(capsys.readouterr().out)
    assert untagged["removed_tags"] == ["draft"]
    assert untagged["card"]["tags"] == ["database"]

    # Remove a single decision without trashing the whole card
    code = main(["forget", "backend", "--decision", "stateless", "--yes"])
    assert code == 0
    store = Store(cli_home)
    card = store.get_card("backend")
    assert card is not None
    assert "stateless" not in card.body
    assert "PostgreSQL" in card.body

    # Ambiguous selector raises ValidationError
    store.remember("backend", "Enable strict CSP headers")
    store.remember("backend", "Enable strict CORS denial")
    with pytest.raises(ValidationError, match="ambiguous"):
        store.supersede("backend", "Enable strict", "New rule")


def test_mcp_resources_prompts_and_supersede(store: Store, home: Path) -> None:
    store.remember("atlas", "Use SQLite for caching", tags=["cache"])
    store.record_fix("Disk full", "Prune old artifacts", project="atlas")

    responses, _ = run_server(
        [
            INITIALIZE,
            {"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "resources/templates/list"},
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "resources/read",
                "params": {"uri": "engramkeep://projects/atlas"},
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "resources/read",
                "params": {"uri": "engramkeep://troubleshooting"},
            },
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "resources/read",
                "params": {"uri": "engramkeep://projects/../escape"},
            },
            {"jsonrpc": "2.0", "id": 7, "method": "prompts/list"},
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "prompts/get",
                "params": {"name": "session-start", "arguments": {"project": "atlas"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "prompts/get",
                "params": {
                    "name": "post-mortem-fix",
                    "arguments": {"error": "Disk full", "project": "atlas"},
                },
            },
            call_tool(
                "engramkeep_supersede",
                {
                    "project": "atlas",
                    "old_decision": "SQLite",
                    "new_decision": "Use Redis for caching",
                    "reason": "Need shared cache",
                },
                request_id=10,
            ),
        ],
        home=home,
        allow_write=True,
    )

    uris = {res["uri"] for res in responses[1]["result"]["resources"]}
    assert "engramkeep://projects/atlas" in uris
    assert "engramkeep://troubleshooting" in uris
    assert "engramkeep://index" in uris

    templates = responses[2]["result"]["resourceTemplates"]
    assert templates[0]["uriTemplate"] == "engramkeep://projects/{project}"

    card_res = responses[3]["result"]["contents"][0]
    assert "UNTRUSTED DATA" in card_res["text"]
    assert "Use SQLite for caching" in card_res["text"]

    fix_res = responses[4]["result"]["contents"][0]
    assert "Disk full" in fix_res["text"]

    # Path traversal over resource URI is rejected
    assert responses[5]["error"]["code"] == -32602

    prompts = {p["name"] for p in responses[6]["result"]["prompts"]}
    assert prompts == {"session-start", "post-mortem-fix", "decision-review"}

    session_prompt = responses[7]["result"]["messages"][0]["content"]["text"]
    assert "atlas" in session_prompt
    assert "untrusted data" in session_prompt

    postmortem = responses[8]["result"]["messages"][0]["content"]["text"]
    assert "Disk full" in postmortem

    sup_payload = tool_payload(responses[9])
    assert "Redis" in sup_payload["card"]["body"]
    assert "## Superseded" in sup_payload["card"]["body"]


def test_installer_extended_mcp_allow_write_portable_cmd_and_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("engramkeep.installer.shutil.which", lambda name: "/usr/bin/engramkeep")

    for agent, rel_mcp in (
        ("windsurf", ".windsurf/mcp.json"),
        ("gemini-cli", ".gemini/settings.json"),
        ("antigravity", ".gemini/mcp.json"),
        ("codex", ".codex/mcp.json"),
        ("cline", ".cline/mcp_settings.json"),
        ("roo", ".roo/mcp.json"),
    ):
        result = install_agents(
            agent,
            user_home=tmp_path / "home",
            project_dir=tmp_path / "project",
            backup_root=tmp_path / "backups",
            scope="project",
            mcp=True,
            mcp_allow_write=True,
            skill=True,
            dry_run=False,
        )
        mcp_file = tmp_path / "project" / rel_mcp
        assert mcp_file.is_file(), agent
        cfg = json.loads(mcp_file.read_text(encoding="utf-8"))
        entry = cfg["mcpServers"]["engramkeep"]
        assert entry["command"] == "engramkeep"
        assert entry["args"] == ["mcp", "--allow-write"]
        assert any("SKILL.md" in op.target for op in result.operations)

    # Uninstall with --skill removes SKILL.md cleanly
    skill_path = tmp_path / "project" / ".gemini" / "skills" / "engramkeep" / "SKILL.md"
    assert skill_path.is_file()
    install_agents(
        "gemini-cli",
        user_home=tmp_path / "home",
        project_dir=tmp_path / "project",
        backup_root=tmp_path / "backups",
        scope="project",
        mcp=True,
        skill=True,
        dry_run=False,
        remove=True,
    )
    assert not skill_path.exists()


def test_dashboard_post_fixes_export_and_open_browser(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.remember("demo", "Use SQLite", tags=["database"])

    with running_dashboard(store.home, allow_write=True) as server:
        # GET /api/export requires token and returns cards + fixes
        status, _, body = request(server, "GET", "/api/export", token=server.token)
        assert status == 200
        exported = json_body(body)
        assert exported["cards"][0]["id"] == "demo"  # type: ignore[index]

        # POST /api/fixes requires confirm: true
        status, _, _ = request(
            server,
            "POST",
            "/api/fixes",
            token=server.token,
            body=json.dumps({"error": "Boom", "solution": "Fix it"}),
            headers={"Content-Type": "application/json"},
        )
        assert status == 400

        # Valid POST /api/fixes redacts secrets and deduplicates repeats
        secret = "sk-proj-" + "z" * 28
        payload = json.dumps(
            {
                "error": f"Auth failed with {secret}",
                "solution": "Rotate key",
                "project": "demo",
                "confirm": True,
            }
        )
        status, _, body = request(
            server,
            "POST",
            "/api/fixes",
            token=server.token,
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        res1 = json_body(body)
        assert res1["added"] is True
        assert secret not in json.dumps(res1)

        status, _, body = request(
            server,
            "POST",
            "/api/fixes",
            token=server.token,
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        res2 = json_body(body)
        assert res2["added"] is False

        # Modular static assets still satisfy zero innerHTML invariant
        status, _, js_bytes = request(server, "GET", "/app.js")
        assert status == 200
        assert b"innerHTML" not in js_bytes
        assert b"renderStructuredMarkdown" in js_bytes
        assert b"/api/export" in js_bytes

    # Verify --open invokes webbrowser.open with server URL
    opened: list[str] = []
    monkeypatch.setattr("engramkeep.dashboard.webbrowser.open", lambda url: opened.append(url))

    def fake_serve_forever(self: Any) -> None:
        return None

    monkeypatch.setattr(dashboard.DashboardServer, "serve_forever", fake_serve_forever)
    rc = dashboard.serve(
        store.home,
        port=0,
        open_browser=True,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert rc == 0
    assert len(opened) == 1
    assert opened[0].startswith("http://127.0.0.1:")
    assert "#token=" in opened[0]


def test_dashboard_post_fixes_rejected_when_read_only(store: Store) -> None:
    with running_dashboard(store.home, allow_write=False) as server:
        status, _, body = request(
            server,
            "POST",
            "/api/fixes",
            token=server.token,
            body=json.dumps({"error": "Boom", "solution": "Fix", "confirm": True}),
            headers={"Content-Type": "application/json"},
        )
        assert status == 403
        assert "--allow-write" in str(json_body(body)["error"])


def test_dashboard_serve_thread_safety_smoke(store: Store) -> None:
    # Ensure modular assets load cleanly across concurrent requests.
    with running_dashboard(store.home) as server:
        results: list[int] = []

        def worker() -> None:
            st, _, _ = request(server, "GET", "/")
            results.append(st)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert results == [200, 200, 200, 200]
