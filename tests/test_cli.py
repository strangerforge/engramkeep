"""Tests for the command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engramkeep.cli import main


def test_init_remember_search_show(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init"]) == 0
    assert main(["remember", "demo", "Use SQLite for local storage", "--tag", "database"]) == 0
    capsys.readouterr()
    assert main(["search", "sqlite", "--json"]) == 0
    hits = json.loads(capsys.readouterr().out)
    assert hits[0]["id"] == "demo"
    assert main(["show", "demo"]) == 0
    assert "Use SQLite for local storage" in capsys.readouterr().out


def test_remember_auto_initializes(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["remember", "demo", "First decision"]) == 0
    assert (cli_home / "projects" / "demo.md").is_file()
    assert "Remembered" in capsys.readouterr().out


def test_search_without_store_returns_error(
    cli_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["search", "anything"]) == 1
    assert "engramkeep init" in capsys.readouterr().err


def test_forget_requires_confirmation(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["remember", "demo", "Temporary"]) == 0
    assert main(["forget", "demo"]) == 2
    assert "without --yes" in capsys.readouterr().err
    assert (cli_home / "projects" / "demo.md").is_file()
    assert main(["forget", "demo", "--yes"]) == 0
    assert not (cli_home / "projects" / "demo.md").exists()


def test_export_to_file_and_overwrite_guard(
    cli_home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["init"]) == 0
    assert main(["remember", "demo", "Export me"]) == 0
    target = tmp_path / "export.json"
    assert main(["export", "--output", str(target)]) == 0
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["cards"][0]["id"] == "demo"
    assert main(["export", "--output", str(target)]) == 1
    assert "pass --force" in capsys.readouterr().err
    assert main(["export", "--output", str(target), "--force"]) == 0


def test_export_to_stdout(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init"]) == 0
    assert main(["remember", "demo", "Export me"]) == 0
    capsys.readouterr()
    assert main(["export"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["cards"][0]["id"] == "demo"


def test_doctor_json(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["doctor", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert report["initialized"] is True


def test_list_empty(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["list"]) == 0
    assert "No projects yet." in capsys.readouterr().out


def test_recent_json(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init"]) == 0
    assert main(["remember", "demo", "A decision"]) == 0
    capsys.readouterr()
    assert main(["recent", "--json"]) == 0
    lines = json.loads(capsys.readouterr().out)
    assert any("remembered" in line for line in lines)


def test_path_prints_home(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["path"]) == 0
    assert str(cli_home.resolve()) in capsys.readouterr().out


def test_home_flag_overrides_environment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "flag-home"
    assert main(["--home", str(target), "init"]) == 0
    assert (target / "meta.json").is_file()
    assert str(target.resolve()) in capsys.readouterr().out


def test_install_plan_and_unknown_agent(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["install", "--agent", "opencode"]) == 0
    output = capsys.readouterr().out
    assert "dry run" in output
    assert "~/.config/opencode/AGENTS.md" in output

    assert main(["install", "--agent", "unknown"]) == 1
    assert "unknown agent" in capsys.readouterr().err


def test_mcp_status(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["mcp", "--status"]) == 0
    output = capsys.readouterr().out
    assert "MCP: available" in output
    assert "Transport: stdio" in output
    assert "Protocol: 2025-11-25" in output
    assert "--allow-write" in output


def test_mcp_command_serves_with_resolved_home(
    cli_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, object] = {}

    def fake_serve(home: Path, *, allow_write: bool = False) -> int:
        calls["home"] = home
        calls["allow_write"] = allow_write
        return 0

    monkeypatch.setattr("engramkeep.mcp_server.serve", fake_serve)
    assert main(["mcp", "--allow-write"]) == 0
    assert calls["home"] == cli_home.resolve()
    assert calls["allow_write"] is True


def test_dashboard_status(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["dashboard", "--status"]) == 0
    output = capsys.readouterr().out
    assert "Dashboard: available" in output
    assert "Bind: 127.0.0.1" in output
    assert "Auth: per-session token" in output
    assert "--allow-write" in output
    assert "CSP: strict" in output


def test_dashboard_command_serves_with_resolved_home(
    cli_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, object] = {}

    def fake_serve(
        home: Path,
        *,
        port: int = 8765,
        allow_write: bool = False,
    ) -> int:
        calls["home"] = home
        calls["port"] = port
        calls["allow_write"] = allow_write
        return 0

    monkeypatch.setattr("engramkeep.dashboard.serve", fake_serve)
    assert main(["dashboard", "--port", "9000", "--allow-write"]) == 0
    assert calls["home"] == cli_home.resolve()
    assert calls["port"] == 9000
    assert calls["allow_write"] is True


def test_project_traversal_is_rejected(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["remember", "../escape", "Bad"]) == 1
    assert "invalid project name" in capsys.readouterr().err
    assert not (cli_home.parent / "escape.md").exists()


def test_show_missing_project(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init"]) == 0
    assert main(["show", "missing"]) == 1
    assert "project not found" in capsys.readouterr().err


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "0.3.0" in capsys.readouterr().out
