"""Tamper-evident SHA-256 hash chain helpers for ``audit.log``.

Each new audit entry carries ``prev_hash`` (the SHA-256 hex digest of the
preceding chained entry, or 64 zeroes for the genesis entry) and ``hash``
(the SHA-256 hex digest of the canonical JSON entry without ``hash``).

Legacy stores created before hash chaining remain readable: unchained entries
at the start of the log are reported as ``legacy``, whereas any broken link,
modified field, malformed JSON line, or unchained line after chaining begins
is flagged as ``tampered``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import StoreError
from .paths import is_link_or_junction

GENESIS_HASH = "0" * 64
AuditStatus = Literal["empty", "valid", "legacy", "tampered"]


@dataclass(frozen=True)
class AuditVerification:
    """Result of verifying an ``audit.log`` hash chain."""

    ok: bool
    status: AuditStatus
    entries: int
    chained_entries: int
    legacy_entries: int
    broken_line: int | None = None
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "ok": self.ok,
            "status": self.status,
            "entries": self.entries,
            "chained_entries": self.chained_entries,
            "legacy_entries": self.legacy_entries,
            "broken_line": self.broken_line,
            "message": self.message,
        }


def compute_entry_hash(entry: dict[str, object]) -> str:
    """Return the canonical SHA-256 hex digest for an audit entry without ``hash``."""
    payload = {key: value for key, value in entry.items() if key != "hash"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def seal_audit_entry(entry: dict[str, object], prev_hash: str) -> dict[str, object]:
    """Return a copy of ``entry`` linked to ``prev_hash`` and sealed with ``hash``."""
    sealed = dict(entry)
    sealed["prev_hash"] = prev_hash
    sealed["hash"] = compute_entry_hash(sealed)
    return sealed


def seal_audit_sequence(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build a fresh hash chain over ``entries`` from ``GENESIS_HASH``."""
    prev = GENESIS_HASH
    chained: list[dict[str, object]] = []
    for raw in entries:
        clean = {k: v for k, v in raw.items() if k not in {"prev_hash", "hash"}}
        sealed = seal_audit_entry(clean, prev)
        prev = str(sealed["hash"])
        chained.append(sealed)
    return chained


def last_audit_hash(path: Path) -> str:
    """Return the latest ``hash`` in ``path``, or ``GENESIS_HASH`` if unchained/empty."""
    if not path.exists():
        return GENESIS_HASH
    if is_link_or_junction(path) or not path.is_file():
        raise StoreError("refusing to read audit.log through a symlink or non-regular file")
    try:
        raw_text = path.read_text(encoding="utf-8")
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError) as exc:
        raise StoreError(f"cannot read {path.name}: {exc}") from exc
    if not lines:
        return GENESIS_HASH
    try:
        last = json.loads(lines[-1])
    except json.JSONDecodeError:
        return GENESIS_HASH
    if isinstance(last, dict):
        digest = last.get("hash")
        if isinstance(digest, str) and len(digest) == 64:
            return digest
    return GENESIS_HASH


def verify_audit_log(path: Path) -> AuditVerification:
    """Verify the structural and cryptographic integrity of ``audit.log``."""
    if not path.exists():
        return AuditVerification(
            ok=True,
            status="empty",
            entries=0,
            chained_entries=0,
            legacy_entries=0,
            message="audit.log does not exist",
        )
    if is_link_or_junction(path) or not path.is_file():
        return AuditVerification(
            ok=False,
            status="tampered",
            entries=0,
            chained_entries=0,
            legacy_entries=0,
            broken_line=1,
            message="audit.log is a symlink or non-regular file",
        )

    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return AuditVerification(
            ok=False,
            status="tampered",
            entries=0,
            chained_entries=0,
            legacy_entries=0,
            broken_line=1,
            message=f"cannot read audit.log: {exc}",
        )

    entries = 0
    chained = 0
    legacy = 0
    expected_prev = GENESIS_HASH

    for line_no, raw_line in enumerate(raw_lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        entries += 1
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            return AuditVerification(
                ok=False,
                status="tampered",
                entries=entries,
                chained_entries=chained,
                legacy_entries=legacy,
                broken_line=line_no,
                message=f"malformed JSON at line {line_no}",
            )
        if not isinstance(obj, dict):
            return AuditVerification(
                ok=False,
                status="tampered",
                entries=entries,
                chained_entries=chained,
                legacy_entries=legacy,
                broken_line=line_no,
                message=f"non-object audit entry at line {line_no}",
            )

        has_hash = "hash" in obj or "prev_hash" in obj
        if not has_hash:
            if chained > 0:
                return AuditVerification(
                    ok=False,
                    status="tampered",
                    entries=entries,
                    chained_entries=chained,
                    legacy_entries=legacy,
                    broken_line=line_no,
                    message=f"unchained entry after hash chain started at line {line_no}",
                )
            legacy += 1
            continue

        prev_hash = obj.get("prev_hash")
        entry_hash = obj.get("hash")
        if not isinstance(prev_hash, str) or not isinstance(entry_hash, str):
            return AuditVerification(
                ok=False,
                status="tampered",
                entries=entries,
                chained_entries=chained,
                legacy_entries=legacy,
                broken_line=line_no,
                message=f"invalid hash fields at line {line_no}",
            )
        if prev_hash != expected_prev:
            return AuditVerification(
                ok=False,
                status="tampered",
                entries=entries,
                chained_entries=chained,
                legacy_entries=legacy,
                broken_line=line_no,
                message=f"broken hash chain at line {line_no}",
            )
        computed = compute_entry_hash(obj)
        if entry_hash != computed:
            return AuditVerification(
                ok=False,
                status="tampered",
                entries=entries,
                chained_entries=chained,
                legacy_entries=legacy,
                broken_line=line_no,
                message=f"hash mismatch at line {line_no}",
            )
        expected_prev = entry_hash
        chained += 1

    if entries == 0:
        return AuditVerification(
            ok=True,
            status="empty",
            entries=0,
            chained_entries=0,
            legacy_entries=0,
            message="audit.log is empty",
        )
    if chained == 0:
        return AuditVerification(
            ok=True,
            status="legacy",
            entries=entries,
            chained_entries=0,
            legacy_entries=legacy,
            message=(
                "audit.log uses legacy unchained format; run 'engramkeep migrate --apply' to seal"
            ),
        )
    return AuditVerification(
        ok=True,
        status="valid",
        entries=entries,
        chained_entries=chained,
        legacy_entries=legacy,
        message=f"verified {chained} chained audit entr(y/ies)",
    )
