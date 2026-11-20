"""Tests for Engramkeep v1.0.1–v1.2.0 reliability, ergonomics, security, and CLI coverage."""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from engramkeep import dashboard, mcp_server
from engramkeep.adapters import get_adapter
from engramkeep.adapters.formats import ClaudeJsonlAdapter
from engramkeep.cli import main
from engramkeep.context import UNTRUSTED_CONTEXT_BANNER, pack_context
from engramkeep.crypto import (
    ENV_PASSPHRASE,
    ENVELOPE_HEADER,
    decrypt_store,
    decrypt_text,
    encrypt_store,
    encrypt_text,
    is_encrypted_text,
    resolve_passphrase,
)
from engramkeep.errors import (
    CryptoError,
    InstallerError,
    PathSafetyError,
    StoreError,
    ValidationError,
)
from engramkeep.importer import discover_transcripts, import_transcript
from engramkeep.installer import (
    TOML_BEGIN_MARKER,
    TOML_END_MARKER,
    _is_inside_venv,
    install_agents,
    restore_installer_backup,
)
from engramkeep.migrations import migrate_store, rollback_migration
from engramkeep.redact import (
    REDACTED,
    REDACTED_USER,
    compile_custom_rule,
    contains_secret,
    load_redaction_rules,
    redact_text,
    redact_user_paths,
)
from engramkeep.store import Store
from engramkeep.sync import is_allowlisted_path, sync_commit, sync_status


def _git_available() -> bool:
    return shutil.which("git") is not None


@contextmanager
def _running_dashboard(
    home: Path,
    *,
    allow_write: bool = False,
    project_home: Path | None = None,
) -> Iterator[dashboard.DashboardServer]:
    server = dashboard.create_server(
        home,
        port=0,
        allow_write=allow_write,
        project_home=project_home,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _http_request(
    server: dashboard.DashboardServer,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    try:
        headers: dict[str, str] = {}
        if token is not None:
            headers["X-Engramkeep-Token"] = token
        payload: bytes | None = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read()
    finally:
        conn.close()


def _run_mcp(
    messages: list[dict[str, Any]],
    *,
    home: Path,
    allow_write: bool = False,
    project_home: Path | None = None,
) -> list[dict[str, Any]]:
    raw_in = "".join(json.dumps(m) + "\n" for m in messages).encode("utf-8")
    stream_in = io.BytesIO(raw_in)
    stream_out = io.BytesIO()
    stream_err = io.StringIO()
    mcp_server.serve(
        home,
        allow_write=allow_write,
        project_home=project_home,
        stdin=stream_in,
        stdout=stream_out,
        stderr=stream_err,
    )
    return [
        json.loads(line)
        for line in stream_out.getvalue().decode("utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Stage 1: Sync ghost-card deletion, --local, MCP/Dashboard layered, Installer,
# Adapters, Redaction, Migration rollback
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _git_available(), reason="git is not installed")
def test_sync_tracks_allowlisted_card_deletions_and_cli_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Engramkeep Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Engramkeep Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.invalid")

    store = Store(tmp_path / "brain")
    store.init()
    store.remember("alpha", "Use Postgres")
    store.remember("beta", "Use Redis")

    assert main(["--home", str(store.home), "sync", "--init"]) == 0
    assert "Initialized local Git sync" in capsys.readouterr().out

    assert main(["--home", str(store.home), "sync", "--status"]) == 0
    assert "Allowlisted files:" in capsys.readouterr().out

    assert main(["--home", str(store.home), "sync", "--commit", "-m", "initial cards"]) == 0
    assert "Sync (committed):" in capsys.readouterr().out

    store.forget("beta")
    assert is_allowlisted_path("projects/beta.md")
    assert not is_allowlisted_path("trash/beta.md")

    status = sync_status(store)
    assert "projects/beta.md" in status.changed_files

    second = sync_commit(store, message="forget beta", apply=True)
    assert second.mode == "committed"
    assert "projects/beta.md" in second.staged_files

    git_bin = shutil.which("git")
    assert git_bin is not None
    tracked = subprocess.run(  # noqa: S603
        [git_bin, "-C", str(store.home), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert "projects/beta.md" not in tracked
    assert "projects/alpha.md" in tracked

    # Dry-run sync commit via CLI
    assert main(["--home", str(store.home), "sync"]) == 0
    assert "Sync (" in capsys.readouterr().out


def test_cli_local_flag_and_layered_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    global_home = tmp_path / "global-brain"
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.setenv("ENGRAMKEEP_HOME", str(global_home))
    monkeypatch.chdir(repo_dir)

    assert main(["init"]) == 0
    assert main(["remember", "global-svc", "Global rule", "--tag", "shared"]) == 0
    assert main(["init", "--local"]) == 0
    assert (repo_dir / ".engramkeep" / "meta.json").is_file()
    capsys.readouterr()

    assert main(["path", "--local"]) == 0
    assert ".engramkeep" in capsys.readouterr().out

    assert main(["remember", "svc", "Use SQLite WAL", "--tag", "db", "--local"]) == 0
    assert main(["remember", "svc-old", "Legacy cache note", "--tag", "cache", "--local"]) == 0
    assert main(["merge", "svc-old", "svc", "--delete-source", "--local"]) == 0
    assert "Merged svc-old into svc" in capsys.readouterr().out

    assert main(["trash", "--local"]) == 0
    assert "svc-old" in capsys.readouterr().out

    assert main(["trash", "--local", "--json"]) == 0
    trash_items = json.loads(capsys.readouterr().out)
    assert len(trash_items) == 1

    assert main(["restore", "svc-old", "--local"]) == 0
    assert main(["untag", "svc", "--tag", "cache", "--local"]) == 0
    assert main(["untag", "svc", "--tag", "not-there", "--local"]) == 0
    assert (
        main(
            [
                "supersede",
                "svc",
                "--old",
                "WAL",
                "--new",
                "Use Postgres",
                "--reason",
                "Concurrency",
                "--local",
            ]
        )
        == 0
    )
    capsys.readouterr()

    # Layered read commands (search, show, list, context) see both global and .engramkeep/
    proj_store = str(repo_dir / ".engramkeep")
    assert main(["list", "--project-store", proj_store]) == 0
    list_out = capsys.readouterr().out
    assert "svc" in list_out and "global-svc" in list_out

    assert main(["list", "--project-store", proj_store, "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert {item["id"] for item in listed} >= {"svc", "global-svc"}

    assert main(["show", "svc", "--project-store", proj_store]) == 0
    assert "Use Postgres" in capsys.readouterr().out

    assert main(["show", "svc", "--project-store", proj_store, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["source"] == "project"

    assert main(["search", "Postgres", "--project-store", proj_store]) == 0
    assert "svc" in capsys.readouterr().out

    assert main(["search", "no-such-term-xyz", "--project-store", proj_store]) == 0
    assert "No matches." in capsys.readouterr().out

    assert main(["context", "Postgres", "--project-store", proj_store]) == 0
    assert UNTRUSTED_CONTEXT_BANNER in capsys.readouterr().out

    assert main(["recent", "--local", "--limit", "5"]) == 0
    assert main(["reindex", "--local"]) == 0
    assert main(["export", "--local"]) == 0
    assert main(["doctor", "--local"]) == 0
    assert main(["doctor", "--fix", "--local"]) == 0
    assert main(["migrate", "--local"]) == 0
    assert main(["forget", "svc-old", "--yes", "--local"]) == 0
    assert main(["trash", "--purge", "--yes", "--local"]) == 0


def test_mcp_layered_store_and_engramkeep_context(tmp_path: Path) -> None:
    global_store = Store(tmp_path / "global-brain")
    project_store = Store(tmp_path / "project-brain")
    global_store.init()
    project_store.init()

    global_store.remember("shared-api", "Global decision v1", tags=["api", "core"])
    global_store.record_fix("Port 8080 busy", "Kill stale daemon", project="shared-api")
    project_store.remember("shared-api", "Project override v2", tags=["api", "local"])
    project_store.record_fix("Missing .env", "Copy .env.example", project="shared-api")

    responses = _run_mcp(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "engramkeep_context",
                    "arguments": {"query": "shared-api", "max_chars": 2000},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "resources/read",
                "params": {"uri": "engramkeep://troubleshooting"},
            },
        ],
        home=global_store.home,
        project_home=project_store.home,
    )

    ctx_payload = json.loads(responses[1]["result"]["content"][0]["text"])
    assert "untrusted" in ctx_payload["_untrusted_data_notice"].lower()
    assert "Project override v2" in ctx_payload["markdown"]
    assert UNTRUSTED_CONTEXT_BANNER in ctx_payload["markdown"]
    assert ctx_payload["char_count"] <= 2000

    trouble_text = responses[2]["result"]["contents"][0]["text"]
    assert "Missing .env" in trouble_text
    assert "Port 8080 busy" in trouble_text

    st = mcp_server.status(global_store.home, project_home=project_store.home)
    assert st["home"] == str(global_store.home.resolve())
    assert st["project_home"] == str(project_store.home.resolve())


def test_dashboard_layered_trash_restore_and_supersede(tmp_path: Path) -> None:
    global_store = Store(tmp_path / "global-brain")
    project_store = Store(tmp_path / "project-brain")
    global_store.init()
    project_store.init()

    global_store.remember("api", "Use SQLite", tags=["db"])
    global_store.remember("archived-svc", "Old note")
    global_store.forget("archived-svc")
    project_store.remember("local-only", "Repo specific rule", tags=["repo"])
    project_store.record_fix("Local port clash", "Use port 8099", project="local-only")

    st = dashboard.status(global_store.home, project_home=project_store.home)
    assert st["home"] == str(global_store.home.resolve())
    assert st["project_home"] == str(project_store.home.resolve())

    # Read-only server must reject supersede and restore with 403
    with _running_dashboard(
        global_store.home,
        allow_write=False,
        project_home=project_store.home,
    ) as ro_server:
        code, _, _ = _http_request(
            ro_server,
            "POST",
            "/api/supersede",
            token=ro_server.token,
            body={
                "project": "api",
                "old_decision": "SQLite",
                "new_decision": "Postgres",
                "confirm": True,
            },
        )
        assert code == 403
        code, _, _ = _http_request(
            ro_server,
            "POST",
            "/api/restore",
            token=ro_server.token,
            body={"project": "archived-svc", "confirm": True},
        )
        assert code == 403

    with _running_dashboard(
        global_store.home,
        allow_write=True,
        project_home=project_store.home,
    ) as server:
        code, _, raw = _http_request(server, "GET", "/api/health", token=server.token)
        assert code == 200
        health = json.loads(raw)
        assert health["layered"] is True
        assert health["writes"] is True
        assert str(global_store.home) == health["home"]
        assert str(project_store.home) == health["project_home"]

        code, _, raw = _http_request(server, "GET", "/api/cards", token=server.token)
        assert code == 200
        cards = json.loads(raw)["projects"]
        sources = {c["id"]: c["source"] for c in cards}
        assert sources["api"] == "global"
        assert sources["local-only"] == "project"

        # Layered GET /api/cards/<id>, /api/search, /api/fixes
        code, _, raw = _http_request(server, "GET", "/api/cards/local-only", token=server.token)
        assert code == 200
        assert json.loads(raw)["card"]["source"] == "project"

        code, _, raw = _http_request(server, "GET", "/api/search?q=Repo", token=server.token)
        assert code == 200
        assert any(h["id"] == "local-only" for h in json.loads(raw)["hits"])

        code, _, raw = _http_request(server, "GET", "/api/fixes?q=port", token=server.token)
        assert code == 200
        assert any("8099" in f["fix"] for f in json.loads(raw)["fixes"])

        code, _, raw = _http_request(server, "GET", "/api/trash", token=server.token)
        assert code == 200
        trash_items = json.loads(raw)["trash"]
        assert any(item["project_id"] == "archived-svc" for item in trash_items)

        # POST /api/supersede requires confirm: true and non-empty fields
        code, _, _ = _http_request(
            server,
            "POST",
            "/api/supersede",
            token=server.token,
            body={"project": "api", "old_decision": "SQLite", "new_decision": "Use Postgres"},
        )
        assert code == 400

        code, _, raw = _http_request(
            server,
            "POST",
            "/api/supersede",
            token=server.token,
            body={
                "project": "api",
                "old_decision": "SQLite",
                "new_decision": "Use Postgres",
                "reason": "Need concurrent writes",
                "confirm": True,
            },
        )
        assert code == 200
        sup_resp = json.loads(raw)
        assert sup_resp["old_decision"] == "Use SQLite"
        assert "Postgres" in sup_resp["new_decision"]

        # POST /api/restore requires confirm: true, then recovers trashed card
        code, _, _ = _http_request(
            server,
            "POST",
            "/api/restore",
            token=server.token,
            body={"project": "archived-svc"},
        )
        assert code == 400

        code, _, raw = _http_request(
            server,
            "POST",
            "/api/restore",
            token=server.token,
            body={"project": "archived-svc", "confirm": True},
        )
        assert code == 200
        assert json.loads(raw)["card"]["id"] == "archived-svc"
        assert global_store.get_card("archived-svc") is not None


def test_installer_codex_toml_venv_guard_shared_dedup_and_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user_home = tmp_path / "home"
    project_dir = tmp_path / "project"
    backup_root = tmp_path / "backups"
    user_home.mkdir()
    project_dir.mkdir()

    # Pre-existing Codex TOML should be preserved alongside managed block
    codex_cfg = project_dir / ".codex" / "config.toml"
    codex_cfg.parent.mkdir(parents=True)
    original_toml = 'model = "o3"\n'
    codex_cfg.write_text(original_toml, encoding="utf-8")

    # Ephemeral .venv path should be detected as inside venv
    venv_dir = tmp_path / ".venv"
    (venv_dir / "pyvenv.cfg").parent.mkdir(parents=True)
    (venv_dir / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    fake_venv_bin = venv_dir / "bin" / "engramkeep"
    fake_venv_bin.parent.mkdir(parents=True)
    fake_venv_bin.write_text("", encoding="utf-8")
    assert _is_inside_venv(str(fake_venv_bin)) is True

    # Custom --mcp-command overrides auto-detection
    res = install_agents(
        "codex",
        user_home=user_home,
        project_dir=project_dir,
        backup_root=backup_root,
        scope="project",
        mcp=True,
        mcp_command="/opt/bin/engramkeep",
        dry_run=False,
    )
    updated_toml = codex_cfg.read_text(encoding="utf-8")
    assert original_toml.strip() in updated_toml
    assert TOML_BEGIN_MARKER in updated_toml
    assert TOML_END_MARKER in updated_toml
    assert 'command = "/opt/bin/engramkeep"' in updated_toml
    assert res.backup_dir is not None

    # Idempotent re-apply updates cleanly without duplicating blocks
    install_agents(
        "codex",
        user_home=user_home,
        project_dir=project_dir,
        backup_root=backup_root,
        scope="project",
        mcp=True,
        mcp_command="/opt/bin/engramkeep",
        dry_run=False,
    )
    assert codex_cfg.read_text(encoding="utf-8").count(TOML_BEGIN_MARKER) == 1

    # Uninstall removes only the TOML managed block while keeping user config
    install_agents(
        "codex",
        user_home=user_home,
        project_dir=project_dir,
        backup_root=backup_root,
        scope="project",
        mcp=True,
        dry_run=False,
        remove=True,
    )
    after_uninstall = codex_cfg.read_text(encoding="utf-8")
    assert original_toml.strip() in after_uninstall
    assert TOML_BEGIN_MARKER not in after_uninstall

    # Re-apply then test dry-run & applied restore via library and CLI
    res2 = install_agents(
        "codex",
        user_home=user_home,
        project_dir=project_dir,
        backup_root=backup_root,
        scope="project",
        mcp=True,
        mcp_command="/opt/bin/engramkeep",
        dry_run=False,
    )
    assert res2.backup_dir is not None
    run_id = res2.backup_dir.name

    dry_restore = restore_installer_backup(backup_root, run_id, dry_run=True)
    assert dry_restore.mode == "dry-run"
    assert any(op.action == "would-restore" for op in dry_restore.operations)
    assert TOML_BEGIN_MARKER in codex_cfg.read_text(encoding="utf-8")

    applied_restore = restore_installer_backup(backup_root, run_id, dry_run=False)
    assert applied_restore.mode == "restore"
    assert codex_cfg.read_text(encoding="utf-8") == original_toml

    # CLI install --restore dry-run and --json
    store_home = tmp_path / "cli-home"
    inst_backup = store_home / "backups" / "installer"
    shutil.copytree(backup_root / run_id, inst_backup / run_id)
    assert main(["--home", str(store_home), "install", "--restore", run_id]) == 0
    assert "Dry run:" in capsys.readouterr().out
    assert main(["--home", str(store_home), "install", "--restore", run_id, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "dry-run"

    # Traversal in run_id must be rejected
    with pytest.raises((InstallerError, PathSafetyError, ValidationError)):
        restore_installer_backup(backup_root, "../escape", dry_run=True)

    # --agent all deduplicates shared global target (~/.gemini/GEMINI.md)
    monkeypatch.setattr("engramkeep.installer.shutil.which", lambda _: None)
    all_res = install_agents(
        "all",
        user_home=user_home,
        project_dir=project_dir,
        backup_root=backup_root,
        scope="global",
        dry_run=False,
    )
    shared_ops = [op for op in all_res.operations if op.action == "shared"]
    assert len(shared_ops) >= 1
    gemini_file = user_home / ".gemini" / "GEMINI.md"
    assert gemini_file.read_text(encoding="utf-8").count("<!-- engramkeep:begin -->") == 1


def test_adapters_question_filter_strict_claude_and_discover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Unknown adapter raises KeyError
    with pytest.raises(KeyError):
        get_adapter("does-not-exist")

    # Arbitrary JSON must NOT be misclassified as claude-jsonl
    other_json = tmp_path / "package.json"
    other_json.write_text('{"name": "demo", "version": "1.0.0"}\n', encoding="utf-8")
    assert ClaudeJsonlAdapter().can_handle(other_json, other_json.read_text(encoding="utf-8")) is (
        False
    )

    # Question sentences must be ignored while real decisions + multi-line error/fix pair work
    transcript = tmp_path / "chat.jsonl"
    records = [
        {"type": "user", "message": {"role": "user", "content": "Bundan sonra ne yapalım?"}},
        {"type": "user", "message": {"role": "user", "content": "Should we use Redis?"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": "Decision: Use SQLite with WAL mode",
            },
        },
        {
            "type": "user",
            "message": {"role": "user", "content": "Error: ModuleNotFoundError for pkg_foo"},
        },
        {"type": "assistant", "message": {"role": "assistant", "content": "Checking venv..."}},
        {"type": "assistant", "message": {"role": "assistant", "content": "Checking paths..."}},
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": "Fix: Reinstall editable package"},
        },
    ]
    transcript.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )

    store = Store(tmp_path / "brain")
    res = import_transcript(store, transcript, project="demo", apply=False)
    assert res.format == "claude-jsonl"
    assert len(res.decisions) == 1
    assert "WAL mode" in res.decisions[0].text
    assert len(res.fixes) == 1
    assert "Reinstall editable package" in res.fixes[0].fix

    # --discover finds standard local transcript folders read-only
    fake_home = tmp_path / "fake-home"
    claude_dir = fake_home / ".claude" / "projects" / "demo"
    claude_dir.mkdir(parents=True)
    (claude_dir / "session.jsonl").write_text(
        json.dumps({"type": "user", "message": {"content": "hello"}}) + "\n",
        encoding="utf-8",
    )
    codex_dir = fake_home / ".codex" / "sessions"
    codex_dir.mkdir(parents=True)
    (codex_dir / "run.jsonl").write_text("{}\n", encoding="utf-8")

    found = discover_transcripts(user_home=fake_home, limit=10)
    assert len(found) == 2
    assert {item.agent for item in found} == {"claude-jsonl", "codex"}

    # CLI import --discover (plain and --json)
    monkeypatch.setattr("engramkeep.cli.discover_transcripts", lambda limit=20: found)
    assert main(["--home", str(store.home), "import", "--discover"]) == 0
    assert "Discovered 2 transcript(s)" in capsys.readouterr().out
    assert main(["--home", str(store.home), "import", "--discover", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2

    # CLI import plain dry-run & applied
    assert (
        main(["--home", str(store.home), "import", "--file", str(transcript), "--project", "demo"])
        == 0
    )
    assert "Dry run:" in capsys.readouterr().out

    # CLI --interactive --json sends prompts to stderr so stdout stays valid JSON
    monkeypatch.setattr("builtins.input", lambda _: "n")
    code = main(
        [
            "--home",
            str(store.home),
            "import",
            "--file",
            str(transcript),
            "--project",
            "demo",
            "--interactive",
            "--json",
        ]
    )
    assert code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["format"] == "claude-jsonl"
    assert "decision" in captured.err.lower()

    # Interactive 'a' approves remaining items cleanly
    answers = iter(["a"])
    interactive_res = import_transcript(
        store,
        transcript,
        project="demo",
        interactive=True,
        input_fn=lambda _: next(answers),
        output_fn=lambda _: None,
    )
    assert interactive_res.applied is True
    assert interactive_res.written_decisions == 1
    assert interactive_res.written_fixes == 1


def test_modern_redaction_user_paths_and_custom_rules(tmp_path: Path) -> None:
    tokens = [
        "sbp_" + "a" * 36,
        "gsk_" + "b" * 32,
        "xai-" + "c" * 32,
        "pplx-" + "d" * 32,
        "re_" + "e" * 28,
        "lin_api_" + "f" * 32,
        "dapi" + "0123456789abcdef" * 2,
    ]
    for tok in tokens:
        redacted = redact_text(f"token={tok}")
        assert tok not in redacted
        assert REDACTED in redacted
        assert contains_secret(tok)

    # Personal home paths are redacted while safe placeholders are preserved
    win_path = "C:\\" + "Users\\devperson\\workspace\\app"
    mac_path = "/" + "Users/devperson/code/app"
    lin_path = "/" + "home/devperson/src/app"
    safe_path = "/" + "Users/example/demo"
    assert REDACTED_USER in redact_user_paths(win_path)
    assert "devperson" not in redact_user_paths(win_path)
    assert REDACTED_USER in redact_user_paths(mac_path)
    assert REDACTED_USER in redact_user_paths(lin_path)
    assert redact_user_paths(safe_path) == safe_path

    # Custom redact.json rules + ReDoS protection
    with pytest.raises(ValidationError):
        compile_custom_rule("redos", "(a+)+$")
    with pytest.raises(ValidationError):
        compile_custom_rule("empty", "a*")

    store = Store(tmp_path / "brain")
    store.init()
    (store.home / "redact.json").write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "name": "corp-key",
                        "pattern": r"CORP_[A-Z0-9]{12,}",
                        "replacement": "[REDACTED_CORP]",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rules = load_redaction_rules(store.home)
    assert len(rules) == 1

    fake_corp = "CORP_" + "9X8Y7Z6W5V4U"
    store.remember("app", f"Use key {fake_corp} in dev")
    card = store.get_card("app")
    assert card is not None
    assert fake_corp not in card.body
    assert "[REDACTED_CORP]" in card.body

    # Doctor also detects custom secret written directly to disk
    card_path = store.home / "projects" / "app.md"
    card_path.write_text(card_path.read_text(encoding="utf-8") + f"\n- {fake_corp}\n", "utf-8")
    report = store.doctor()
    assert not report.ok
    assert any("secret" in err.lower() for err in report.errors)


def test_migration_rollback_jail_and_stray_file_cleanup(tmp_path: Path) -> None:
    store = Store(tmp_path / "brain")
    store.init()
    store.remember("alpha", "Original decision")

    # External backup path must be rejected
    outside = tmp_path / "outside-backup"
    outside.mkdir()
    with pytest.raises((StoreError, ValidationError)):
        rollback_migration(store.home, outside)

    # Simulate legacy v0 store -> migrate -> add stray card -> rollback cleans stray card
    (store.home / "meta.json").write_text(json.dumps({"schema_version": 0}), encoding="utf-8")
    applied = migrate_store(store.home, apply=True)
    assert applied.backup_dir is not None

    stray_card = store.home / "projects" / "stray.md"
    stray_card.write_text("# Stray\n", encoding="utf-8")
    rollback_migration(store.home, applied.backup_dir)
    assert not stray_card.exists()


# ---------------------------------------------------------------------------
# Stage 2: Context packer, merge, multi-tag AND, recent --since, dup titles
# ---------------------------------------------------------------------------


def test_context_packer_budget_merge_multitag_since_and_duplicate_titles(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = Store(tmp_path / "brain")
    store.init()
    store.remember("api-gateway", "Use SQLite WAL mode", tags=["backend", "db"])
    store.remember("api-gateway", "Keep response payloads compact " + "x" * 180, tags=["api"])
    store.remember("web-ui", "Use vanilla JS without innerHTML", tags=["frontend", "db"])
    store.record_fix("SQLite locked under load", "Enable busy_timeout=5000", project="api-gateway")

    # Multi-tag AND filter: only api-gateway has both backend AND db
    assert (
        main(
            [
                "--home",
                str(store.home),
                "search",
                "Use",
                "--tag",
                "backend",
                "--tag",
                "db",
                "--json",
            ]
        )
        == 0
    )
    hits = json.loads(capsys.readouterr().out)
    assert [h["id"] for h in hits] == ["api-gateway"]

    # Context packer honors tight budget, truncates gracefully, and promotes exact project id
    bundle = pack_context(store, "api-gateway", max_chars=380)
    assert UNTRUSTED_CONTEXT_BANNER in bundle.markdown
    assert len(bundle.markdown) <= 380
    assert "api-gateway" in bundle.card_ids
    assert bundle.truncated is True

    # Empty query match yields explicit no-match marker
    empty_bundle = pack_context(store, "zzzz-no-match-9999", max_chars=1000)
    assert "No matching cards or fixes" in empty_bundle.markdown

    # CLI context works with optional query + --project
    assert main(["--home", str(store.home), "context", "--project", "api-gateway", "--json"]) == 0
    ctx_json = json.loads(capsys.readouterr().out)
    assert "api-gateway" in ctx_json["card_ids"]

    # recent --since filters by YYYY-MM-DD and rejects bad dates
    assert main(["--home", str(store.home), "recent", "--since", "2099-01-01"]) == 0
    assert "No activity yet." in capsys.readouterr().out
    assert main(["--home", str(store.home), "recent", "--since", "bad-date"]) == 1
    capsys.readouterr()

    # Duplicate titles produce a doctor warning
    card_a = store.home / "projects" / "dup-one.md"
    card_b = store.home / "projects" / "dup-two.md"
    for cid, p in (("dup-one", card_a), ("dup-two", card_b)):
        p.write_text(
            f"---\nid: {cid}\ntitle: Shared Service\ncreated: 2026-01-01T00:00:00Z\n"
            f"updated: 2026-01-01T00:00:00Z\ntags: demo\n---\n\n# Shared Service\n\n"
            "## Decisions\n\n- Keep clean.\n",
            encoding="utf-8",
        )
    report = store.doctor()
    assert any("duplicate card title" in w.lower() for w in report.warnings)


# ---------------------------------------------------------------------------
# Stage 3: Optional at-rest encryption (crypto.py) & CLI coverage polish
# ---------------------------------------------------------------------------


class _FakeScrypt:
    def __init__(self, *, salt: bytes, length: int, n: int, r: int, p: int) -> None:
        self._salt = salt
        self._length = length

    def derive(self, key_material: bytes) -> bytes:
        return hashlib.sha256(key_material + self._salt).digest()[: self._length]


class _FakeAESGCM:
    def __init__(self, key: bytes) -> None:
        self._key = key

    def encrypt(self, nonce: bytes, data: bytes, aad: bytes) -> bytes:
        stream = hashlib.sha256(self._key + nonce + aad).digest()
        ct = bytes(b ^ stream[i % len(stream)] for i, b in enumerate(data))
        tag = hashlib.sha256(self._key + nonce + aad + ct).digest()[:16]
        return ct + tag

    def decrypt(self, nonce: bytes, data: bytes, aad: bytes) -> bytes:
        ct, tag = data[:-16], data[-16:]
        expected = hashlib.sha256(self._key + nonce + aad + ct).digest()[:16]
        if tag != expected:
            raise ValueError("bad tag")
        stream = hashlib.sha256(self._key + nonce + aad).digest()
        return bytes(b ^ stream[i % len(stream)] for i, b in enumerate(ct))


def test_crypto_missing_extra_and_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Missing optional dependency produces clear CryptoError
    monkeypatch.setattr("engramkeep.crypto.crypto_available", lambda: False)
    with pytest.raises(CryptoError, match="engramkeep\\[crypto\\]"):
        encrypt_text("hello", "passphrase")

    # Resolve passphrase from env and validate empty failure
    monkeypatch.setenv(ENV_PASSPHRASE, "top-secret-pass")
    assert resolve_passphrase() == "top-secret-pass"
    monkeypatch.delenv(ENV_PASSPHRASE, raising=False)
    with pytest.raises(CryptoError):
        resolve_passphrase()

    # Round-trip encrypt/decrypt + tamper & wrong-passphrase detection using fake AEAD
    monkeypatch.setattr("engramkeep.crypto._require_crypto", lambda: (_FakeAESGCM, _FakeScrypt))
    envelope = encrypt_text("Merhaba Engramkeep!", "pass-123")
    assert is_encrypted_text(envelope)
    assert envelope.startswith(ENVELOPE_HEADER)
    assert decrypt_text(envelope, "pass-123") == "Merhaba Engramkeep!"

    with pytest.raises(CryptoError):
        decrypt_text(envelope, "wrong-pass")
    with pytest.raises(CryptoError):
        decrypt_text("not encrypted", "pass-123")

    # Store-level dry-run + apply encrypt & decrypt via library and CLI
    store = Store(tmp_path / "brain")
    store.init()
    store.remember("alpha", "Secret architecture note")
    store.record_fix("Disk full", "Prune logs", project="alpha")

    dry = encrypt_store(store.home, "", apply=False)
    assert dry.mode == "dry-run"
    assert "projects/alpha.md" in dry.files_processed

    assert main(["--home", str(store.home), "encrypt", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "dry-run"

    monkeypatch.setenv(ENV_PASSPHRASE, "store-pass")
    assert main(["--home", str(store.home), "encrypt", "--apply"]) == 0
    assert "Encrypt (applied)" in capsys.readouterr().out
    assert is_encrypted_text((store.home / "projects" / "alpha.md").read_text(encoding="utf-8"))

    # Re-encrypting skips already-encrypted files
    again = encrypt_store(store.home, "store-pass", apply=True)
    assert "projects/alpha.md" in again.files_skipped

    assert main(["--home", str(store.home), "decrypt", "--apply"]) == 0
    assert "Decrypt (applied)" in capsys.readouterr().out
    assert "Secret architecture note" in (store.home / "projects" / "alpha.md").read_text(
        encoding="utf-8"
    )
    dec_dry = decrypt_store(store.home, "", apply=False)
    assert "projects/alpha.md" in dec_dry.files_skipped


def test_cli_status_json_module_entry_and_error_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = Store(tmp_path / "brain")
    store.init()

    # python -m engramkeep --version exercises __main__.py
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "engramkeep", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "engramkeep" in proc.stdout

    # mcp/dashboard --status --json and plain output
    assert main(["--home", str(store.home), "mcp", "--status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["transport"] == "stdio"

    assert main(["--home", str(store.home), "dashboard", "--status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["bind"] == "127.0.0.1"

    assert main(["--home", str(store.home), "mcp", "--status"]) == 0
    assert "Home:" in capsys.readouterr().out

    assert main(["--home", str(store.home), "dashboard", "--status"]) == 0
    assert "Home:" in capsys.readouterr().out

    # Missing required flags on import & install return exit code 2
    assert main(["--home", str(store.home), "import"]) == 2
    assert main(["--home", str(store.home), "install"]) == 2

    # install --restore missing run returns exit code 1
    assert main(["--home", str(store.home), "install", "--restore", "no-such-run"]) == 1

    # completion prints all shells including new commands
    for shell in ("bash", "zsh", "fish", "powershell"):
        assert main(["completion", shell]) == 0
        out = capsys.readouterr().out
        assert "context" in out and "merge" in out and "encrypt" in out
