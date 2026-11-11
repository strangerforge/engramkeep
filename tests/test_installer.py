"""Tests for the agent installer and managed-block updates."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from engramkeep.errors import InstallerError
from engramkeep.installer import (
    BEGIN_MARKER,
    END_MARKER,
    available_agents,
    install_agents,
    plan_installation,
)


def run_install(
    agent: str,
    tmp_path: Path,
    *,
    scope: str = "project",
    mcp: bool = False,
    dry_run: bool = True,
    remove: bool = False,
):
    return install_agents(
        agent,
        user_home=tmp_path / "home",
        project_dir=tmp_path / "project",
        backup_root=tmp_path / "backups",
        scope=scope,  # type: ignore[arg-type]
        mcp=mcp,
        dry_run=dry_run,
        remove=remove,
    )


def test_unknown_agent_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        run_install("does-not-exist", tmp_path)


def test_available_agents_are_stable() -> None:
    agents = available_agents()
    assert agents[0] == "opencode"
    assert "claude-code" in agents
    assert len(agents) == len(set(agents))


def test_plan_lists_global_and_project_targets() -> None:
    plan = plan_installation("claude-code")
    assert plan.global_target == "~/.claude/CLAUDE.md"
    assert plan.project_target == "CLAUDE.md"
    assert plan.mcp_global == "~/.claude.json"


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    target = tmp_path / "project" / "CLAUDE.md"
    target.parent.mkdir(parents=True)
    target.write_text("# User rules\n\nKeep this.\n", encoding="utf-8")

    result = run_install("claude-code", tmp_path)

    assert result.mode == "dry-run"
    assert result.operations[0].action == "would-update"
    assert target.read_text(encoding="utf-8") == "# User rules\n\nKeep this.\n"
    assert not (tmp_path / "backups").exists()


def test_apply_preserves_content_and_backs_up(tmp_path: Path) -> None:
    target = tmp_path / "project" / "CLAUDE.md"
    original = "# User rules\n\nKeep this.\n"
    target.parent.mkdir(parents=True)
    target.write_text(original, encoding="utf-8")

    result = run_install("claude-code", tmp_path, dry_run=False)

    updated = target.read_text(encoding="utf-8")
    assert "Keep this." in updated
    assert BEGIN_MARKER in updated
    assert END_MARKER in updated
    assert result.operations[0].action == "updated"
    assert result.backup_dir is not None
    assert result.backup_dir.is_dir()

    manifest = json.loads((result.backup_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["operations"][0]["action"] == "updated"
    backup_name = result.operations[0].backup
    assert backup_name is not None
    assert (result.backup_dir / backup_name).read_text(encoding="utf-8") == original


def test_apply_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "project" / "CLAUDE.md"
    target.parent.mkdir(parents=True)
    target.write_text("# User rules\n", encoding="utf-8")

    run_install("claude-code", tmp_path, dry_run=False)
    first = target.read_text(encoding="utf-8")
    second_result = run_install("claude-code", tmp_path, dry_run=False)

    assert target.read_text(encoding="utf-8") == first
    assert first.count(BEGIN_MARKER) == 1
    assert second_result.operations[0].action == "unchanged"


def test_uninstall_removes_only_the_managed_block(tmp_path: Path) -> None:
    target = tmp_path / "project" / "CLAUDE.md"
    original = "# User rules\n\nKeep this.\n"
    target.parent.mkdir(parents=True)
    target.write_text(original, encoding="utf-8")

    run_install("claude-code", tmp_path, dry_run=False)
    result = run_install("claude-code", tmp_path, dry_run=False, remove=True)

    assert result.operations[0].action == "removed"
    assert target.read_text(encoding="utf-8") == original
    assert BEGIN_MARKER not in target.read_text(encoding="utf-8")


def test_cursor_project_scope_has_frontmatter(tmp_path: Path) -> None:
    result = run_install("cursor", tmp_path, dry_run=False)
    target = tmp_path / "project" / ".cursor" / "rules" / "engramkeep.mdc"
    assert result.operations[0].target == str(target.resolve())
    text = target.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "alwaysApply: true" in text
    assert text.count(BEGIN_MARKER) == 1


def test_global_scope_uses_user_home(tmp_path: Path) -> None:
    result = run_install("claude-code", tmp_path, scope="global", dry_run=False)
    target = tmp_path / "home" / ".claude" / "CLAUDE.md"
    assert target.is_file()
    assert result.operations[0].target == str(target.resolve())


def test_mcp_registration_merges_existing_json(tmp_path: Path) -> None:
    config = tmp_path / "home" / ".claude.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "other"}}}),
        encoding="utf-8",
    )

    result = run_install("claude-code", tmp_path, scope="global", mcp=True, dry_run=False)

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["mcpServers"]["other"] == {"command": "other"}
    assert "engramkeep" in data["mcpServers"]
    assert any(op.target == str(config.resolve()) for op in result.operations)


def test_mcp_uninstall_removes_only_engramkeep(tmp_path: Path) -> None:
    config = tmp_path / "home" / ".claude.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"mcpServers": {"other": {"command": "other"}}}),
        encoding="utf-8",
    )

    run_install("claude-code", tmp_path, scope="global", mcp=True, dry_run=False)
    run_install("claude-code", tmp_path, scope="global", mcp=True, dry_run=False, remove=True)

    data = json.loads(config.read_text(encoding="utf-8"))
    assert "engramkeep" not in data["mcpServers"]
    assert data["mcpServers"]["other"] == {"command": "other"}


def test_invalid_mcp_json_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "home" / ".claude.json"
    config.parent.mkdir(parents=True)
    config.write_text("{not json", encoding="utf-8")

    with pytest.raises(InstallerError):
        run_install("claude-code", tmp_path, scope="global", mcp=True, dry_run=False)
    assert config.read_text(encoding="utf-8") == "{not json"


def test_all_agents_project_scope(tmp_path: Path) -> None:
    result = run_install("all", tmp_path, dry_run=False)
    assert len(result.operations) == len(available_agents())
    assert (tmp_path / "project" / "AGENTS.md").is_file()
    assert (tmp_path / "project" / ".clinerules").is_file()
    assert (tmp_path / "project" / ".github" / "copilot-instructions.md").is_file()


def test_symlink_target_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    target = tmp_path / "project" / "CLAUDE.md"
    target.parent.mkdir(parents=True)
    try:
        os.symlink(outside, target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(InstallerError):
        run_install("claude-code", tmp_path, dry_run=False)
    assert outside.read_text(encoding="utf-8") == "# Outside\n"


def test_symlink_parent_dir_is_refused(tmp_path: Path) -> None:
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    try:
        os.symlink(outside_dir, project_dir / ".cursor")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(InstallerError):
        run_install("cursor", tmp_path, dry_run=False)
    assert not (outside_dir / "rules").exists()


def test_unreadable_utf16_target_raises_installer_error(tmp_path: Path) -> None:
    target = tmp_path / "project" / "CLAUDE.md"
    target.parent.mkdir(parents=True)
    target.write_bytes("# UTF-16 rules\n".encode("utf-16"))

    with pytest.raises(InstallerError, match="unreadable file"):
        run_install("claude-code", tmp_path, dry_run=False)


def test_uninstall_removes_file_when_only_managed_block_existed(tmp_path: Path) -> None:
    run_install("claude-code", tmp_path, dry_run=False)
    target = tmp_path / "project" / "CLAUDE.md"
    assert target.is_file()

    result = run_install("claude-code", tmp_path, dry_run=False, remove=True)
    assert result.operations[0].action == "removed"
    assert not target.exists()


def test_installer_preserves_parent_directory_permissions(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX directory mode bits do not apply on Windows")
    expected_mode = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP
    project_dir = tmp_path / "project"
    project_dir.mkdir(mode=expected_mode)
    os.chmod(project_dir, expected_mode)
    run_install("claude-code", tmp_path, dry_run=False)
    assert stat.S_IMODE(project_dir.stat().st_mode) == expected_mode


def test_uninstall_without_mcp_notes_remaining_mcp_entry(tmp_path: Path) -> None:
    run_install("claude-code", tmp_path, mcp=True, dry_run=False)
    mcp_path = tmp_path / "project" / ".mcp.json"
    assert mcp_path.is_file()

    result = run_install("claude-code", tmp_path, mcp=False, dry_run=False, remove=True)
    actions = {op.action: op.reason for op in result.operations}
    assert actions.get("kept") == "MCP entry remains; pass --uninstall --mcp to remove"
    assert "engramkeep" in json.loads(mcp_path.read_text(encoding="utf-8"))["mcpServers"]
