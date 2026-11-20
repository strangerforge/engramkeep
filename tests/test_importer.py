"""Tests for consent-based, read-only-by-default transcript import."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from engramkeep.cli import main
from engramkeep.errors import PathSafetyError, StoreError
from engramkeep.importer import MAX_IMPORT_BYTES, import_transcript
from engramkeep.redact import REDACTED
from engramkeep.store import Store


def test_import_claude_jsonl_dry_run_redacts_and_does_not_write(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    fake_secret = "sk-ant-" + "api03-" + "abcdefghijklmnopqrstuvwxyz123456"
    records = [
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": "Error: SQLite database is locked during parallel writes",
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Fix: Enable WAL mode and set busy_timeout=5000\n"
                            f"Decision: Use {fake_secret} only from env\n"
                        ),
                    }
                ],
            },
        },
        "not-valid-json-line",
    ]
    transcript.write_text(
        "\n".join(r if isinstance(r, str) else json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )

    store = Store(tmp_path / "store")
    result = import_transcript(store, transcript, project="mobile-app")
    assert result.format == "claude-jsonl"
    assert result.applied is False
    assert not store.is_initialized()
    assert len(result.decisions) == 1
    assert REDACTED in result.decisions[0].text
    assert "abcdefghijklmnopqrstuvwxyz" not in result.decisions[0].text
    assert len(result.fixes) == 1
    assert "SQLite database is locked" in result.fixes[0].error
    assert "WAL mode" in result.fixes[0].fix


def test_import_text_apply_persists_decisions_and_fixes(tmp_path: Path) -> None:
    log_file = tmp_path / "notes.txt"
    log_file.write_text(
        (
            "Karar: Yerel depolama için düz Markdown kullan\n"
            "Error: Missing keystore alias -> Fix: Set signingConfigs.release.storeFile\n"
        ),
        encoding="utf-8",
    )
    store = Store(tmp_path / "store")
    result = import_transcript(store, log_file, project="mobile-notes", apply=True)
    assert result.format == "text"
    assert result.applied is True
    assert result.written_decisions == 1
    assert result.written_fixes == 1

    card = store.get_card("mobile-notes")
    assert card is not None
    assert "Yerel depolama için düz Markdown kullan" in card.body
    fix_hits = store.search_fixes("keystore alias")
    assert len(fix_hits) == 1
    assert "signingConfigs.release.storeFile" in fix_hits[0].entry.fix


def test_import_rejects_missing_oversized_and_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(tmp_path / "store")
    with pytest.raises(StoreError):
        import_transcript(store, tmp_path / "missing.jsonl")

    real_file = tmp_path / "real.txt"
    real_file.write_text("Decision: Keep it simple\n", encoding="utf-8")

    monkeypatch.setattr("engramkeep.importer.MAX_IMPORT_BYTES", 5)
    with pytest.raises(StoreError, match="limit"):
        import_transcript(store, real_file)
    monkeypatch.setattr("engramkeep.importer.MAX_IMPORT_BYTES", MAX_IMPORT_BYTES)

    if sys.platform != "win32":
        sym = tmp_path / "link.txt"
        sym.symlink_to(real_file)
        with pytest.raises(PathSafetyError):
            import_transcript(store, sym)


def test_cli_import_dry_run_and_apply_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    transcript = tmp_path / "chat.txt"
    transcript.write_text("Decision: Use BM25 ranking in search\n", encoding="utf-8")
    home = tmp_path / "home"

    code = main(["--home", str(home), "import", "--file", str(transcript), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is False
    assert payload["written_decisions"] == 0
    assert len(payload["decisions"]) == 1
    assert not (home / "INDEX.md").exists()

    code = main(
        [
            "--home",
            str(home),
            "import",
            "--file",
            str(transcript),
            "--project",
            "search-core",
            "--apply",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is True
    assert payload["written_decisions"] == 1
    assert (home / "INDEX.md").exists()
