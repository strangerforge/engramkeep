"""Tests for path safety and file helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from engramkeep.errors import PathSafetyError, ValidationError
from engramkeep.paths import (
    append_text,
    atomic_write_text,
    display_title,
    ensure_private_dir,
    is_private_path,
    normalize_project_id,
    safe_join,
)


@pytest.mark.parametrize(
    "part",
    [
        "",
        ".",
        "..",
        "../escape",
        "a/b",
        "a\\b",
        "/absolute",
        "C:drive",
        "CON",
        "con.txt",
        "a\x00b",
        " leading",
        "trailing ",
        "trailing.",
        "a" * 256,
    ],
)
def test_safe_join_rejects_unsafe_components(tmp_path: Path, part: str) -> None:
    with pytest.raises(PathSafetyError):
        safe_join(tmp_path, part)


def test_safe_join_allows_nested_components(tmp_path: Path) -> None:
    result = safe_join(tmp_path, "projects", "example.md")
    assert result == (tmp_path / "projects" / "example.md").resolve()


def test_safe_join_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "link"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this environment")
    with pytest.raises(PathSafetyError):
        safe_join(root, "link", "file.md")


def test_normalize_project_id() -> None:
    assert normalize_project_id("My Project") == "my-project"
    assert normalize_project_id("Demo_Project") == "demo-project"
    assert normalize_project_id("v1.2") == "v1-2"
    assert normalize_project_id("  Example  ") == "example"


@pytest.mark.parametrize("value", ["", "..", "a/b", "a\\b", "C:name", "CON", "a" * 65])
def test_normalize_project_id_rejects_invalid(value: str) -> None:
    with pytest.raises(ValidationError):
        normalize_project_id(value)


def test_display_title() -> None:
    assert display_title("example-project") == "Example Project"


def test_atomic_write_text_replaces_without_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "card.md"
    atomic_write_text(target, "first\n")
    assert target.read_text(encoding="utf-8") == "first\n"
    atomic_write_text(target, "second\n")
    assert target.read_text(encoding="utf-8") == "second\n"
    assert list(target.parent.glob("*.tmp")) == []
    assert list(target.parent.glob(".*.tmp")) == []


def test_append_text_and_symlink_rejection(tmp_path: Path) -> None:
    target = tmp_path / "log.txt"
    append_text(target, "one\n")
    append_text(target, "two\n")
    assert target.read_text(encoding="utf-8") == "one\ntwo\n"

    link = tmp_path / "link.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this environment")
    with pytest.raises(PathSafetyError):
        append_text(link, "three\n")


def test_ensure_private_dir_and_permissions(tmp_path: Path) -> None:
    target = tmp_path / "private" / "nested"
    assert ensure_private_dir(target) == target
    assert target.is_dir()
    assert is_private_path(target) is True
