"""Tests for Phase 1 enhancements: fix dedup, trash/restore, Turkish search, doctor --fix."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engramkeep.cli import main
from engramkeep.concepts import expand_query_terms, tr_lower
from engramkeep.errors import StoreError
from engramkeep.importer import import_transcript
from engramkeep.models import new_card
from engramkeep.paths import atomic_write_text
from engramkeep.search import search_cards
from engramkeep.store import Store


def test_import_apply_twice_does_not_duplicate_fixes(tmp_path: Path) -> None:
    transcript = tmp_path / "session.txt"
    transcript.write_text(
        "Error: SQLite database is locked -> Fix: Enable WAL mode\n",
        encoding="utf-8",
    )
    store = Store(tmp_path / "store")
    first = import_transcript(store, transcript, project="app", apply=True)
    second = import_transcript(store, transcript, project="app", apply=True)

    assert first.written_fixes == 1
    assert second.written_fixes == 0
    assert len(store.search_fixes(None, limit=20)) == 1


def test_trash_list_restore_and_purge_flow(
    cli_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["remember", "alpha", "Keep it simple", "--tag", "core"]) == 0
    assert main(["forget", "alpha", "--yes"]) == 0
    capsys.readouterr()

    assert main(["trash", "--json"]) == 0
    trashed = json.loads(capsys.readouterr().out)
    assert len(trashed) == 1
    assert trashed[0]["project_id"] == "alpha"

    assert main(["restore", "alpha", "--json"]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["id"] == "alpha"
    assert "Keep it simple" in restored["body"]

    # Conflict protection without --force
    assert main(["forget", "alpha", "--yes"]) == 0
    assert main(["remember", "alpha", "New active card"]) == 0
    capsys.readouterr()
    assert main(["restore", "alpha"]) == 1
    assert "--force" in capsys.readouterr().err

    # Purge requires --yes
    assert main(["trash", "--purge"]) == 2
    assert "without --yes" in capsys.readouterr().err
    assert main(["trash", "--purge", "--yes", "--json"]) == 0
    purged = json.loads(capsys.readouterr().out)
    assert purged["purged"] == 1


def test_restore_missing_raises_store_error(store: Store) -> None:
    with pytest.raises(StoreError, match="no trashed card"):
        store.restore("missing")


def test_turkish_case_folding_and_agglutinative_search() -> None:
    assert tr_lower("İstanbul") == "istanbul"
    assert tr_lower("İNDEX") == "index"

    card_db = new_card("db-notlari", now="2026-01-01T00:00:00Z")
    card_db.body += "\n- Veritabanında WAL modu aktif edilsin ve İstanbul bölgesi seçilsin.\n"
    card_cache = new_card("cache-notlari", now="2026-01-02T00:00:00Z")
    card_cache.body += "\n- Önbelleği 5 dakika TTL ile sınırla.\n"

    hits_db = search_cards([card_db, card_cache], "veritabanı")
    assert hits_db and hits_db[0].id == "db-notlari"

    hits_city = search_cards([card_db, card_cache], "İstanbul")
    assert hits_city and hits_city[0].id == "db-notlari"

    # Consonant softening: önbellek -> önbelleği
    hits_cache = search_cards([card_db, card_cache], "önbellek")
    assert hits_cache and hits_cache[0].id == "cache-notlari"


def test_concepts_short_queries_do_not_over_expand() -> None:
    for short in ("io", "in", "ar"):
        expanded = expand_query_terms(short)
        assert expanded == {short}, f"{short!r} unexpectedly expanded to {expanded}"

    # Exact short concept terms still expand properly.
    assert "database" in expand_query_terms("db")
    assert "frontend" in expand_query_terms("ui")
    # Inflected Turkish terms expand their concept family.
    assert "database" in expand_query_terms("veritabanında")
    assert "performance" in expand_query_terms("önbelleği")


def test_doctor_fix_repairs_recoverable_issues_with_backup(
    cli_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = Store(cli_home)
    store.init()
    store.remember("demo", "Keep it local")

    # Simulate recoverable problems: stale INDEX.md, missing TROUBLESHOOTING.md, stale .tmp file.
    store.index_path.write_text("# Stale index\n", encoding="utf-8")
    store.troubleshooting_path.unlink()
    stale_tmp = store.home / ".INDEX.md.stale.tmp"
    stale_tmp.write_text("leftover", encoding="utf-8")

    # Also add a malformed card to prove doctor --fix never deletes broken user files.
    atomic_write_text(store.projects_dir / "broken.md", "---\nid: broken\n")

    code = main(["doctor", "--fix", "--json"])
    assert code == 1  # Still fails because broken.md is intentionally untouched
    payload = json.loads(capsys.readouterr().out)
    assert any("INDEX.md" in action for action in payload["actions"])
    assert any("TROUBLESHOOTING.md" in action for action in payload["actions"])
    assert any("stale temporary file" in action for action in payload["actions"])
    assert payload["backup_dir"] is not None
    assert (Path(payload["backup_dir"]) / "INDEX.md").is_file()
    assert not stale_tmp.exists()
    assert store.troubleshooting_path.is_file()
    assert (store.projects_dir / "broken.md").is_file()
    assert "Demo" in store.index_path.read_text(encoding="utf-8")


def test_py_typed_marker_is_shipped() -> None:
    import engramkeep

    marker = Path(engramkeep.__file__).resolve().parent / "py.typed"
    assert marker.is_file()
