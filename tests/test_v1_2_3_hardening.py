"""Regression tests for Engramkeep v1.2.3 P0/P1 security and data-safety fixes."""

from __future__ import annotations

import hashlib
import io
import json
import time
from pathlib import Path

import pytest

from engramkeep.adapters.base import clean_candidate
from engramkeep.audit import last_audit_hash
from engramkeep.crypto import (
    ENVELOPE_HEADER,
    decrypt_store,
    decrypt_text,
    encrypt_store,
    encrypt_text,
    resolve_passphrase,
)
from engramkeep.errors import CryptoError, InstallerError, StoreError, ValidationError
from engramkeep.installer import (
    BEGIN_MARKER,
    END_MARKER,
    install_agents,
    restore_installer_backup,
)
from engramkeep.mcp_server import McpServer
from engramkeep.migrations import _create_snapshot, rollback_migration
from engramkeep.models import normalize_tag
from engramkeep.redact import (
    MAX_CUSTOM_SCAN_CHARS,
    REDACTED_EMAIL,
    REDACTED_USER,
    compile_custom_rule,
    redact_text,
    redact_user_paths,
)
from engramkeep.store import Store
from engramkeep.sync import is_allowlisted_path


class _FakeScrypt:
    def __init__(self, *, salt: bytes, length: int, n: int, r: int, p: int) -> None:
        self._salt = salt
        self._length = length

    def derive(self, key_material: bytes) -> bytes:
        return hashlib.sha256(key_material + self._salt).digest()[: self._length]


class _FakeAESGCM:
    def __init__(self, key: bytes) -> None:
        self._key = key

    def encrypt(self, nonce: bytes, data: bytes, aad: bytes) -> bytes:
        stream = hashlib.sha256(self._key + nonce + aad).digest()
        ct = bytes(b ^ stream[i % len(stream)] for i, b in enumerate(data))
        tag = hashlib.sha256(self._key + nonce + aad + ct).digest()[:16]
        return ct + tag

    def decrypt(self, nonce: bytes, data: bytes, aad: bytes) -> bytes:
        ct, tag = data[:-16], data[-16:]
        expected = hashlib.sha256(self._key + nonce + aad + ct).digest()[:16]
        if tag != expected:
            raise ValueError("bad tag")
        stream = hashlib.sha256(self._key + nonce + aad).digest()
        return bytes(b ^ stream[i % len(stream)] for i, b in enumerate(ct))


def test_encrypted_store_locks_reads_writes_and_doctor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("engramkeep.crypto._require_crypto", lambda: (_FakeAESGCM, _FakeScrypt))
    store = Store(tmp_path / "brain")
    store.init()
    store.remember("alpha", "Original architectural decision")
    store.record_fix("Disk full", "Rotate logs", project="alpha")

    res = encrypt_store(store.home, "pass-123", apply=True)
    assert res.mode == "applied"
    assert store.is_encrypted() is True

    # Normal read/write operations must refuse rather than corrupt encrypted files
    with pytest.raises(StoreError, match="decrypt --apply"):
        store.get_card("alpha")
    with pytest.raises(StoreError, match="decrypt --apply"):
        store.scan_cards()
    with pytest.raises(StoreError, match="decrypt --apply"):
        store.remember("alpha", "Second decision")
    with pytest.raises(StoreError, match="decrypt --apply"):
        store.record_fix("Other err", "Other fix", project="alpha")

    report = store.doctor()
    assert report.ok is False
    assert any("encrypted" in err.lower() for err in report.errors)

    # Decrypting restores full access without data loss
    decrypt_store(store.home, "pass-123", apply=True)
    assert store.is_encrypted() is False
    card = store.get_card("alpha")
    assert card is not None
    assert "Original architectural decision" in card.body
    assert store.doctor().ok is True


def test_resolve_passphrase_fails_fast_without_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENGRAMKEEP_PASSPHRASE", raising=False)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with pytest.raises(CryptoError, match="non-interactive"):
        resolve_passphrase(prompt=True)


def test_scrypt_kdf_memory_cap_rejects_huge_nr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engramkeep.crypto._require_crypto", lambda: (_FakeAESGCM, _FakeScrypt))
    env = encrypt_text("hello", "pass")
    body = json.loads(env.split("\n", 1)[1])
    # n=2**20, r=32 => 128 * n * r = 4 GiB (> 256 MiB cap)
    body["kdf_params"] = {"n": 2**20, "r": 32, "p": 1}
    with pytest.raises(CryptoError, match="memory cap"):
        decrypt_text(f"{ENVELOPE_HEADER}\n{json.dumps(body)}\n", "pass")


def test_sync_allowlist_handles_gitignore_and_rejects_dot_prefix_bypass() -> None:
    assert is_allowlisted_path(".gitignore") is True
    assert is_allowlisted_path("./.gitignore") is True
    assert is_allowlisted_path("./projects/alpha.md") is True
    assert is_allowlisted_path(".projects/evil.md") is False
    assert is_allowlisted_path("..projects/evil.md") is False


def test_redact_email_linear_time_and_spaced_windows_paths() -> None:
    # Quadratic backtracking regression check (60K chars without '@')
    t0 = time.perf_counter()
    long_dots = "a." * 30_000
    assert redact_text(long_dots) == long_dots
    assert time.perf_counter() - t0 < 0.5

    win_prefix = "C:\\" + "Users\\"
    mac_prefix = "/" + "Users/"
    assert redact_text("contact alice@example.com now") == f"contact {REDACTED_EMAIL} now"
    assert (
        redact_user_paths(f"{win_prefix}Sample Person\\work\\repo.py")
        == f"{win_prefix}{REDACTED_USER}\\work\\repo.py"
    )
    assert (
        redact_user_paths(f"{win_prefix}alice and {mac_prefix}bob")
        == f"{win_prefix}{REDACTED_USER} and {mac_prefix}{REDACTED_USER}"
    )

    # Importer clean_candidate stays fast on huge lines
    t1 = time.perf_counter()
    cleaned = clean_candidate("a." * 100_000)
    assert len(cleaned) <= 240
    assert time.perf_counter() - t1 < 0.5


def test_redact_custom_rules_brace_comma_n_literal_replacement_and_large_text() -> None:
    # Python >=3.11 {,n} nested quantifier must be rejected
    with pytest.raises(ValidationError, match="ReDoS"):
        compile_custom_rule("brace-bypass", r"(a{,2})+b")

    # Replacement containing \1 must not crash with re.error
    rule = compile_custom_rule("corp-id", r"CORP-[0-9]{4}", replacement=r"[\1_REDACTED]")
    assert redact_text("id=CORP-1234", extra_rules=(rule,)) == r"id=[\1_REDACTED]"

    # >256 KiB text must still be scanned by custom rules (fail-closed)
    huge = ("x" * (MAX_CUSTOM_SCAN_CHARS + 1000)) + " CORP-9999"
    redacted = redact_text(huge, extra_rules=(rule,))
    assert "CORP-9999" not in redacted
    assert r"[\1_REDACTED]" in redacted


def test_mcp_server_survives_deep_json_huge_int_and_lone_surrogate(tmp_path: Path) -> None:
    store = Store(tmp_path / "brain")
    store.init()
    out = io.BytesIO()
    err = io.StringIO()
    server = McpServer(store, allow_write=False, stdout=out, stderr=err)

    deep_json = ("[" * 10_000 + "]" * 10_000).encode("utf-8") + b"\n"
    huge_int = b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":' + b"9" * 5000 + b"}}\n"
    surrogate = b'{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}\n'
    valid_ping = b'{"jsonrpc":"2.0","id":42,"method":"ping"}\n'

    assert server.run(io.BytesIO(deep_json + huge_int + surrogate + valid_ping)) == 0
    lines = [json.loads(line) for line in out.getvalue().decode("utf-8").splitlines()]
    assert len(lines) == 4
    assert lines[0]["error"]["code"] == -32700
    assert lines[1]["error"]["code"] == -32700
    assert lines[3] == {"jsonrpc": "2.0", "id": 42, "result": {}}


def test_migration_rollback_moves_stray_cards_to_trash(tmp_path: Path) -> None:
    store = Store(tmp_path / "brain")
    store.init()
    store.remember("kept", "Before snapshot")
    snapshot = _create_snapshot(store.home)

    store.remember("stray", "Created after snapshot")
    assert (store.home / "projects" / "stray.md").is_file()

    rollback_migration(store.home, snapshot)
    assert not (store.home / "projects" / "stray.md").exists()
    trashed = list((store.home / "trash").glob("stray-rollback-*.md"))
    assert len(trashed) == 1


def test_restore_file_ownership_and_force_backup(tmp_path: Path) -> None:
    store = Store(tmp_path / "brain")
    store.init()
    store.remember("alpha", "Alpha v1")
    store.remember("beta", "Beta v1")
    store.forget("beta")
    beta_trash = [item for item in store.list_trash() if item.project_id == "beta"][0].filename

    # Cross-project --file mismatch must be rejected
    with pytest.raises(StoreError, match="does not belong"):
        store.restore("alpha", filename=beta_trash, force=True)

    # Same-project --force must archive existing active card to trash first
    store.forget("alpha")
    store.remember("alpha", "Alpha v2 active")
    store.restore("alpha", force=True)
    card = store.get_card("alpha")
    assert card is not None and "Alpha v1" in card.body
    pre_restore = list((store.home / "trash").glob("alpha-pre-restore-*.md"))
    assert len(pre_restore) == 1
    assert "Alpha v2 active" in pre_restore[0].read_text(encoding="utf-8")


def test_recent_since_rejects_invalid_calendar_date(tmp_path: Path) -> None:
    store = Store(tmp_path / "brain")
    store.init()
    with pytest.raises(ValidationError, match="valid calendar date"):
        store.recent(since="2026-13-99")


def test_audit_last_hash_rejects_corrupted_tail(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.log"
    audit_path.write_text("{not valid json\n", encoding="utf-8")
    with pytest.raises(StoreError, match="corrupted"):
        last_audit_hash(audit_path)


def test_normalize_tag_turkish_transliteration() -> None:
    assert normalize_tag("güvenlik") == "guvenlik"
    assert normalize_tag("Çözüm") == "cozum"
    assert normalize_tag("Iğdır Şişli") == "igdir-sisli"


def test_installer_rejects_unbalanced_markers_and_verifies_backup_sha256(tmp_path: Path) -> None:
    user_home = tmp_path / "home"
    project_dir = tmp_path / "project"
    backup_root = tmp_path / "backups"
    user_home.mkdir()
    project_dir.mkdir()

    # Orphan BEGIN marker must be refused instead of eating surrounding content
    target = project_dir / "CLAUDE.md"
    target.write_text(f"# User rules\n{BEGIN_MARKER}\nImportant text\n", encoding="utf-8")
    with pytest.raises(InstallerError, match="unbalanced"):
        install_agents(
            "claude-code",
            scope="project",
            dry_run=False,
            user_home=user_home,
            project_dir=project_dir,
            backup_root=backup_root,
        )

    # Duplicate managed blocks must be refused
    target.write_text(
        f"{BEGIN_MARKER}\na\n{END_MARKER}\n\n{BEGIN_MARKER}\nb\n{END_MARKER}\n",
        encoding="utf-8",
    )
    with pytest.raises(InstallerError, match="multiple managed blocks"):
        install_agents(
            "claude-code",
            scope="project",
            dry_run=False,
            user_home=user_home,
            project_dir=project_dir,
            backup_root=backup_root,
        )

    # Clean file -> apply records real content SHA-256 -> tampering fails restore
    target.write_bytes(b"# Clean rules\n")
    res = install_agents(
        "claude-code",
        scope="project",
        dry_run=False,
        user_home=user_home,
        project_dir=project_dir,
        backup_root=backup_root,
    )
    assert res.backup_dir is not None
    manifest = json.loads((res.backup_dir / "manifest.json").read_text(encoding="utf-8"))
    op = manifest["operations"][0]
    assert op["backup_sha256"] == hashlib.sha256(b"# Clean rules\n").hexdigest()

    backup_file = res.backup_dir / op["backup"]
    backup_file.write_text("# Tampered backup\n", encoding="utf-8")
    with pytest.raises(InstallerError, match="SHA-256 mismatch"):
        restore_installer_backup(
            backup_root,
            res.backup_dir.name,
            dry_run=False,
            allowed_roots=(project_dir,),
        )
