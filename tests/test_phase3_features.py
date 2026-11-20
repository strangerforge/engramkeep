"""Tests for Phase 3 features: migrations, audit hash chain, allowlist git sync, adapters."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from engramkeep.audit import verify_audit_log
from engramkeep.cli import main
from engramkeep.errors import StoreError
from engramkeep.importer import import_transcript
from engramkeep.migrations import MigrationStep, migrate_store, rollback_migration
from engramkeep.store import Store
from engramkeep.sync import sync_commit, sync_init


def test_audit_hash_chain_valid_and_detects_tampering(store: Store) -> None:
    store.remember("alpha", "Use SHA-256 hash chain")
    store.record_fix("Log tampered", "Verify chain in doctor", project="alpha")

    check = store.verify_audit()
    assert check.ok is True
    assert check.status == "valid"
    assert check.chained_entries >= 3
    assert store.doctor().audit_chain_status == "valid"

    # Tamper with one character in the second audit line
    lines = store.audit_path.read_text(encoding="utf-8").splitlines()
    tampered_obj = json.loads(lines[1])
    tampered_obj["action"] = "forged"
    lines[1] = json.dumps(tampered_obj, sort_keys=True)
    store.audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    bad = verify_audit_log(store.audit_path)
    assert bad.ok is False
    assert bad.status == "tampered"
    assert bad.broken_line == 2

    report = store.doctor()
    assert report.ok is False
    assert report.audit_chain_ok is False
    assert any("audit.log" in err for err in report.errors)


def test_migration_v0_to_v1_audit_sealing_and_rollback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Build a legacy v0 store with unchained audit.log and no meta.json
    legacy_home = tmp_path / "legacy"
    (legacy_home / "projects").mkdir(parents=True)
    (legacy_home / "projects" / "demo.md").write_text(
        "---\nid: demo\ntitle: Demo\n---\n\n# Demo\n\n## Decisions\n\n- Legacy item\n",
        encoding="utf-8",
    )
    (legacy_home / "audit.log").write_text(
        json.dumps({"ts": "2025-01-01T00:00:00Z", "action": "init", "schema_version": 0}) + "\n",
        encoding="utf-8",
    )

    # Dry run does not write meta.json
    dry = migrate_store(legacy_home, apply=False)
    assert dry.mode == "dry-run"
    assert dry.from_version == 0
    assert dry.to_version == 1
    assert dry.audit_sealed is True
    assert not (legacy_home / "meta.json").exists()

    # Apply creates backup, upgrades to v1, and seals legacy audit.log
    applied = migrate_store(legacy_home, apply=True)
    assert applied.mode == "applied"
    assert applied.backup_dir is not None
    assert (legacy_home / "meta.json").is_file()
    store = Store(legacy_home)
    report = store.doctor()
    assert report.ok is True
    assert report.audit_chain_status == "valid"

    # Second run is up-to-date
    assert migrate_store(legacy_home, apply=True).mode == "up-to-date"

    # Failing custom migration triggers automatic rollback
    def failing_step(home: Path) -> list[str]:
        (home / "projects" / "demo.md").write_text("CORRUPTED", encoding="utf-8")
        raise RuntimeError("simulated crash")

    steps = (MigrationStep(1, 2, "Broken v2", failing_step),)
    with pytest.raises(StoreError, match="rolled back"):
        migrate_store(legacy_home, apply=True, target_version=2, migrations=steps)
    assert "Legacy item" in (legacy_home / "projects" / "demo.md").read_text(encoding="utf-8")

    # Manual rollback via CLI restores backup snapshot cleanly
    rb = rollback_migration(legacy_home, applied.backup_dir)
    assert "projects/demo.md" in rb.restored_files

    assert main(["--home", str(legacy_home), "migrate", "--json"]) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["mode"] in {"dry-run", "up-to-date"}


def test_allowlist_git_sync_never_adds_secrets_or_private_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git = shutil.which("git")
    if not git:
        pytest.skip("git executable is not available")

    home = tmp_path / "sync-store"
    store = Store(home)
    store.init()
    store.remember("atlas", "Use allowlist git sync", tags=["sync"])
    store.remember("temp-card", "Will be trashed")
    store.forget("temp-card")

    init_status = sync_init(store)
    assert init_status.is_git_repo is True
    assert (home / ".gitignore").is_file()

    # Configure local git identity for isolated test repo
    subprocess.run([git, "config", "user.email", "test@example.com"], cwd=str(home), check=True)  # noqa: S603
    subprocess.run([git, "config", "user.name", "Test User"], cwd=str(home), check=True)  # noqa: S603

    # Create a non-allowlisted file that must never be staged
    (home / "scratch-notes.txt").write_text("do not commit me\n", encoding="utf-8")

    # Dry run does not commit
    dry = sync_commit(store, apply=False)
    assert dry.mode == "dry-run"
    assert dry.committed is False
    assert "projects/atlas.md" in dry.staged_files
    assert "scratch-notes.txt" not in dry.staged_files
    assert "audit.log" not in dry.staged_files

    # Commit succeeds and only tracks allowlisted files
    res = sync_commit(store, message="test: initial sync", apply=True)
    assert res.committed is True
    assert res.commit_hash is not None

    ls_files = subprocess.run(  # noqa: S603
        [git, "ls-files"], cwd=str(home), capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert "projects/atlas.md" in ls_files
    assert "INDEX.md" in ls_files
    assert "TROUBLESHOOTING.md" in ls_files
    assert "scratch-notes.txt" not in ls_files
    assert "audit.log" not in ls_files
    assert not any(name.startswith("trash/") for name in ls_files)

    # Inject an unredacted secret into a card -> sync_commit MUST refuse
    (home / "projects" / "leaky.md").write_text(
        "---\nid: leaky\ntitle: Leaky\n---\n\n# Leaky\n\n## Decisions\n\n"
        "- password = supersecretvalue123\n",
        encoding="utf-8",
    )
    with pytest.raises(StoreError, match="doctor failed"):
        sync_commit(store, apply=True)

    # CLI sync --status reports doctor failure
    assert main(["--home", str(home), "sync", "--status", "--json"]) == 1
    st_json = json.loads(capsys.readouterr().out)
    assert st_json["doctor_ok"] is False


def test_multi_agent_adapters_natural_language_and_interactive_import(tmp_path: Path) -> None:
    store = Store(tmp_path / "store")

    # 1. Codex JSONL with natural-language decision
    codex_file = tmp_path / "codex.jsonl"
    codex_file.write_text(
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "We decided to use SQLite WAL mode for local persistence.",
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    res_codex = import_transcript(store, codex_file, project="codex-app")
    assert res_codex.format == "codex"
    assert len(res_codex.decisions) == 1
    assert "SQLite WAL mode" in res_codex.decisions[0].text

    # 2. OpenCode JSON
    opencode_file = tmp_path / "opencode.json"
    opencode_file.write_text(
        json.dumps(
            {
                "sessionID": "ses_123",
                "messages": [
                    {
                        "info": {"role": "assistant"},
                        "parts": [{"type": "text", "text": "Decision: Keep zero dependencies"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    res_oc = import_transcript(store, opencode_file, project="oc-app")
    assert res_oc.format == "opencode"
    assert res_oc.decisions[0].text == "Keep zero dependencies"

    # 3. Cursor JSON bubbles
    cursor_file = tmp_path / "cursor.json"
    cursor_file.write_text(
        json.dumps(
            {
                "bubbles": [
                    {"text": "Error: Port 8765 already in use"},
                    {"text": "Fix: Pass --port 0 to pick an ephemeral loopback port"},
                ]
            }
        ),
        encoding="utf-8",
    )
    res_cursor = import_transcript(store, cursor_file, project="cur-app")
    assert res_cursor.format == "cursor"
    assert len(res_cursor.fixes) == 1
    assert "Port 8765" in res_cursor.fixes[0].error

    # 4. Gemini CLI JSON
    gemini_file = tmp_path / "gemini.json"
    gemini_file.write_text(
        json.dumps(
            {
                "contents": [
                    {
                        "role": "model",
                        "parts": [{"text": "Karar: Tüm yanıtlar Türkçe olacak"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    res_gemini = import_transcript(store, gemini_file, project="gem-app")
    assert res_gemini.format == "gemini"
    assert "Türkçe" in res_gemini.decisions[0].text

    # 5. Interactive mode keeps only user-approved candidates
    notes = tmp_path / "interactive.txt"
    notes.write_text(
        "Decision: Keep first decision\n"
        "Decision: Skip second decision\n"
        "Error: Cache miss -> Fix: Warm up index\n",
        encoding="utf-8",
    )
    answers = iter(["y", "n", "y"])
    prompts: list[str] = []
    res_int = import_transcript(
        store,
        notes,
        project="int-app",
        interactive=True,
        input_fn=lambda _: next(answers),
        output_fn=prompts.append,
    )
    assert res_int.applied is True
    assert res_int.written_decisions == 1
    assert res_int.written_fixes == 1
    card = store.get_card("int-app")
    assert card is not None
    assert "Keep first decision" in card.body
    assert "Skip second decision" not in card.body


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish", "powershell"])
def test_shell_completion_outputs_script(shell: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["completion", shell]) == 0
    out = capsys.readouterr().out
    assert "engramkeep" in out
    assert "supersede" in out
    assert "migrate" in out
    assert "sync" in out
