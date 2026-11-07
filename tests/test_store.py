"""Tests for the local store."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from engramkeep.errors import StoreError, ValidationError
from engramkeep.paths import atomic_write_text
from engramkeep.store import Store


def test_init_layout(store: Store) -> None:
    assert store.home.is_dir()
    assert store.projects_dir.is_dir()
    assert store.trash_dir.is_dir()
    assert store.meta_path.is_file()
    assert store.index_path.is_file()
    assert store.recent_path.is_file()
    assert store.audit_path.is_file()
    meta = json.loads(store.meta_path.read_text(encoding="utf-8"))
    assert meta["schema_version"] == 1


def test_init_is_idempotent(store: Store) -> None:
    store.remember("demo", "Keep it simple")
    result = store.init()
    assert result.already_initialized is True
    assert result.created == []
    assert store.get_card("demo") is not None


def test_remember_creates_card_index_and_logs(store: Store) -> None:
    result = store.remember("demo", "Use SQLite for local storage", tags=["database"])
    assert result.created is True
    assert result.added is True
    assert result.card.id == "demo"
    assert result.card.tags == ["database"]

    card_path = store.projects_dir / "demo.md"
    assert card_path.is_file()
    assert "Use SQLite for local storage" in card_path.read_text(encoding="utf-8")
    assert "Demo" in store.index_path.read_text(encoding="utf-8")
    assert "remembered" in store.recent_path.read_text(encoding="utf-8")

    audit_lines = store.audit_path.read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in audit_lines]
    assert any(entry["action"] == "remember" for entry in entries)
    assert all("Use SQLite" not in line for line in audit_lines)


def test_duplicate_decision_is_not_repeated(store: Store) -> None:
    first = store.remember("demo", "Keep it simple")
    second = store.remember("demo", "Keep it simple")
    assert first.added is True
    assert second.added is False
    card = store.get_card("demo")
    assert card is not None
    assert card.body.count("- Keep it simple") == 1


def test_new_tags_are_added_to_existing_card(store: Store) -> None:
    store.remember("demo", "Keep it simple", tags=["docs"])
    result = store.remember("demo", "Keep it simple", tags=["docs", "design"])
    assert result.added is False
    assert result.tags_added == ["design"]
    card = store.get_card("demo")
    assert card is not None
    assert card.tags == ["docs", "design"]


def test_remember_redacts_secrets_and_email(store: Store) -> None:
    credential_value = "hunter2hunter2"
    email = "user" + "@" + "example.com"
    store.remember("demo", "password = " + credential_value + " contact " + email)
    card = store.get_card("demo")
    assert card is not None
    assert credential_value not in card.body
    assert email not in card.body
    assert "[REDACTED]" in card.body
    assert "[REDACTED_EMAIL]" in card.body


def test_get_missing_card_returns_none(store: Store) -> None:
    assert store.get_card("missing") is None


def test_list_cards_returns_valid_cards(store: Store) -> None:
    store.remember("one", "First")
    store.remember("two", "Second")
    cards = store.list_cards()
    assert {card.id for card in cards} == {"one", "two"}


def test_forget_moves_card_to_trash(store: Store) -> None:
    store.remember("demo", "Temporary")
    assert store.forget("demo") is True
    assert store.get_card("demo") is None
    assert list(store.trash_dir.glob("demo-*.md"))
    assert "demo" not in store.index_path.read_text(encoding="utf-8")


def test_forget_missing_returns_false(store: Store) -> None:
    assert store.forget("missing") is False


def test_export_contains_cards(store: Store) -> None:
    store.remember("demo", "Use SQLite", tags=["database"])
    document = store.export_cards()
    assert document["schema_version"] == 1
    cards = document["cards"]
    assert isinstance(cards, list)
    assert cards[0]["id"] == "demo"


def test_reindex_includes_hand_written_card(store: Store) -> None:
    atomic_write_text(
        store.projects_dir / "manual.md",
        "---\nid: manual\ntitle: Manual\n---\n\n# Manual\n\n## Decisions\n\n- Hand written\n",
    )
    scan = store.reindex()
    assert [card.id for card in scan.cards] == ["manual"]
    assert "Manual" in store.index_path.read_text(encoding="utf-8")


def test_doctor_reports_healthy_store(store: Store) -> None:
    store.remember("demo", "Use SQLite")
    report = store.doctor()
    assert report.ok is True
    assert report.cards == 1
    assert report.malformed == []
    assert report.unredacted == []


def test_doctor_reports_malformed_card(store: Store) -> None:
    atomic_write_text(store.projects_dir / "broken.md", "---\nid: broken\n")
    report = store.doctor()
    assert report.ok is False
    assert report.malformed
    assert store.list_cards() == []


def test_doctor_reports_unredacted_secret(store: Store) -> None:
    atomic_write_text(
        store.projects_dir / "leaky.md",
        (
            "---\nid: leaky\ntitle: Leaky\n---\n\n# Leaky\n\n"
            "## Decisions\n\n- password = hunter2hunter2\n"
        ),
    )
    report = store.doctor()
    assert report.ok is False
    assert report.unredacted == ["leaky"]


def test_project_path_traversal_is_rejected(store: Store) -> None:
    with pytest.raises(ValidationError):
        store.get_card("../escape")


def test_newer_schema_is_rejected(store: Store) -> None:
    store.meta_path.write_text('{"schema_version": 999}\n', encoding="utf-8")
    with pytest.raises(StoreError):
        store.is_initialized()


def test_symlinked_card_is_reported(store: Store, tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("---\nid: outside\n---\n\n# Outside\n", encoding="utf-8")
    link = store.projects_dir / "outside.md"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this environment")
    scan = store.scan_cards()
    assert scan.cards == []
    assert scan.errors


def test_recent_activity_is_newest_first(store: Store) -> None:
    store.remember("one", "First")
    store.remember("two", "Second")
    recent = store.recent(2)
    assert "two" in recent[0]
    assert "one" in recent[1]
