"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from engramkeep.store import Store


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """An isolated memory home."""
    return tmp_path / "brain"


@pytest.fixture
def store(home: Path) -> Store:
    """An initialized store rooted in a temporary directory."""
    instance = Store(home)
    instance.init()
    return instance


@pytest.fixture
def cli_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> Path:
    """Point the CLI at the temporary home through the environment."""
    monkeypatch.setenv("ENGRAMKEEP_HOME", str(home))
    return home
