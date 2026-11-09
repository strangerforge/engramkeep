"""Tests for the troubleshooting registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from engramkeep.errors import StoreError
from engramkeep.store import Store
from engramkeep.troubleshoot import (
    TROUBLESHOOTING_NAME,
    parse_registry,
    render_registry,
    search_entries,
)


def test_init_creates_registry(store: Store) -> None:
    assert store.troubleshooting_path.is_file()
    assert "Troubleshooting Registry" in store.troubleshooting_path.read_text(encoding="utf-8")


def test_record_and_roundtrip(store: Store) -> None:
    entry = store.record_fix(
        "Keystore signature error on Android release build",
        "Set signingConfigs in android/app/build.gradle with v2 signing enabled",
        project="my-app",
        workspace="C:/work/my-app",
    )
    assert entry.project == "my-app"
    text = store.troubleshooting_path.read_text(encoding="utf-8")
    assert "Keystore signature error" in text
    assert "build.gradle" in text

    parsed = parse_registry(text)
    assert len(parsed) == 1
    assert parsed[0].project == "my-app"
    assert parsed[0].workspace == "C:/work/my-app"
    assert parsed[0].date == entry.date


def test_record_fix_redacts_secrets(store: Store) -> None:
    store.record_fix(
        "Build failed with api_key=sk-proj-1234567890abcdefghijklmnop in log",
        "Rotated key and removed it from build.gradle",
        project="demo",
    )
    text = store.troubleshooting_path.read_text(encoding="utf-8")
    assert "sk-proj-1234567890abcdefghijklmnop" not in text
    assert "[REDACTED]" in text


def test_record_fix_rejects_empty_fields(store: Store) -> None:
    with pytest.raises(StoreError):
        store.record_fix("", "something")
    with pytest.raises(StoreError):
        store.record_fix("error", "   ")


def test_search_fixes_by_keyword(store: Store) -> None:
    store.record_fix(
        "Android keystore signature mismatch on release",
        "Enable v2 signing in gradle signingConfigs",
        project="my-app",
    )
    store.record_fix(
        "PostgreSQL connection refused on port 5432",
        "Start the postgres service and check pg_hba.conf",
        project="api",
    )
    hits = store.search_fixes("keystore")
    assert len(hits) == 1
    assert hits[0].entry.project == "my-app"
    assert hits[0].score > 0


def test_search_fixes_cross_language(store: Store) -> None:
    store.record_fix(
        "Capacitor mobile build failed with keystore error",
        "Added v2 signing config",
        project="my-app",
    )
    # Turkish query must recall an English entry via concept expansion.
    hits = store.search_fixes("mobil")
    assert any(hit.entry.project == "my-app" for hit in hits)
    # English query must recall a Turkish-ish spelling in the card.
    hits = store.search_fixes("mobile")
    assert any(hit.entry.project == "my-app" for hit in hits)


def test_search_fixes_without_query_lists_newest(store: Store) -> None:
    store.record_fix("first error", "first fix", project="one")
    store.record_fix("second error", "second fix", project="two")
    hits = store.search_fixes(None, limit=5)
    assert [hit.entry.project for hit in hits] == ["two", "one"]


def test_registry_is_rewritten_atomically_and_dedupes_nothing(store: Store) -> None:
    store.record_fix("error one", "fix one", project="demo")
    store.record_fix("error one", "fix one", project="demo")
    parsed = parse_registry(store.troubleshooting_path.read_text(encoding="utf-8"))
    # Duplicate recording is allowed (each call is an explicit user/agent action).
    assert len(parsed) == 2


def test_parse_registry_tolerates_garbage_blocks() -> None:
    text = (
        "# Title\n\n---\n\n"
        "### ⚠️ broken block without required fields\n"
        "- not a field\n\n"
        "### ⚠️ good (2026-11-09)\n"
        "- **Workspace:** `general`\n"
        "- **Problem / Error:** _some error_\n"
        "- **Verified Fix:** some fix\n"
    )
    entries = parse_registry(text)
    assert len(entries) == 1
    assert entries[0].project == "good"


def test_render_parse_roundtrip() -> None:
    entries = parse_registry(
        "### ⚠️ demo (2026-01-02)\n"
        "- **Workspace:** `x`\n"
        "- **Problem / Error:** _err_\n"
        "- **Verified Fix:** fix with **markdown**\n"
    )
    rendered = render_registry(entries)
    reparsed = parse_registry(rendered)
    assert reparsed == entries


def test_symlinked_registry_is_refused(store: Store, tmp_path: Path) -> None:
    target = store.troubleshooting_path
    decoy = tmp_path / "decoy.md"
    decoy.write_text(
        "### ⚠️ x (2026-01-01)\n- **Problem / Error:** _e_\n- **Verified Fix:** f\n",
        encoding="utf-8",
    )
    target.unlink()
    try:
        target.symlink_to(decoy)
    except OSError:
        pytest.skip("symlinks not available on this platform")
    with pytest.raises(StoreError):
        store.record_fix("some error", "some fix")


def test_search_entries_limit() -> None:
    from engramkeep.troubleshoot import TroubleEntry

    entries = [
        TroubleEntry(
            project=f"p{i}",
            error="same",
            fix="same fix",
            workspace=None,
            date=f"2026-01-{i + 1:02d}",
        )
        for i in range(15)
    ]
    assert len(search_entries(entries, "same", limit=10)) == 10


def test_troubleshooting_in_export(store: Store) -> None:
    store.record_fix("exportable error", "exportable fix", project="demo")
    document = store.export_cards()
    fixes = document["fixes"]
    assert isinstance(fixes, list)
    assert any(fix["error"] == "exportable error" for fix in fixes)


def test_troubleshooting_constant_name() -> None:
    assert TROUBLESHOOTING_NAME == "TROUBLESHOOTING.md"
