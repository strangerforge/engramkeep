"""Tests for memory-home resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from engramkeep.config import ENV_HOME, platform_default_home, resolve_home
from engramkeep.errors import ConfigError


def test_env_override(tmp_path: Path) -> None:
    target = tmp_path / "env-brain"
    assert resolve_home(env={ENV_HOME: str(target)}, system="Linux") == target.resolve()


def test_cli_value_wins(tmp_path: Path) -> None:
    cli_target = tmp_path / "cli-brain"
    env_target = tmp_path / "env-brain"
    resolved = resolve_home(
        str(cli_target),
        env={ENV_HOME: str(env_target)},
        system="Linux",
    )
    assert resolved == cli_target.resolve()


def test_empty_env_is_ignored(tmp_path: Path) -> None:
    default = platform_default_home(
        system="Linux",
        env={"XDG_DATA_HOME": str(tmp_path / "xdg")},
        user_home=tmp_path,
    )
    assert (
        resolve_home(
            env={ENV_HOME: "", "XDG_DATA_HOME": str(tmp_path / "xdg")},
            system="Linux",
            user_home=tmp_path,
        )
        == default
    )


def test_windows_default(tmp_path: Path) -> None:
    local = tmp_path / "Local"
    resolved = platform_default_home(
        system="Windows",
        env={"LOCALAPPDATA": str(local)},
        user_home=tmp_path,
    )
    assert resolved == (local / "Engramkeep").resolve()


def test_macos_default(tmp_path: Path) -> None:
    resolved = platform_default_home(system="Darwin", env={}, user_home=tmp_path)
    assert resolved == (tmp_path / "Library" / "Application Support" / "Engramkeep").resolve()


def test_linux_xdg_default(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    resolved = platform_default_home(
        system="Linux",
        env={"XDG_DATA_HOME": str(xdg)},
        user_home=tmp_path,
    )
    assert resolved == (xdg / "engramkeep").resolve()


def test_linux_fallback_default(tmp_path: Path) -> None:
    resolved = platform_default_home(system="Linux", env={}, user_home=tmp_path)
    assert resolved == (tmp_path / ".local" / "share" / "engramkeep").resolve()


def test_root_home_is_rejected() -> None:
    with pytest.raises(ConfigError):
        resolve_home(str(Path("/")), system="Linux")


def test_file_home_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "not-a-directory"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(ConfigError):
        resolve_home(str(target), system="Linux")
