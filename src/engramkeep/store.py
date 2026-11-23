"""Local Markdown store: cards, index, activity log, audit trail, trash."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .audit import AuditVerification, last_audit_hash, seal_audit_entry, verify_audit_log
from .config import SCHEMA_VERSION
from .crypto import is_encrypted_text
from .errors import CardParseError, PathSafetyError, StoreError, ValidationError
from .models import (
    Card,
    add_tags,
    append_decision,
    merge_cards,
    new_card,
    normalize_tags,
    parse_card,
    remove_decision,
    remove_tags,
    render_card,
    supersede_decision,
    utc_now_iso,
)
from .paths import (
    append_text,
    atomic_write_text,
    display_title,
    ensure_private_dir,
    file_lock,
    is_link_or_junction,
    is_private_path,
    normalize_project_id,
    replace_file,
    safe_join,
    strip_control_chars,
)
from .redact import CustomRedactionRule, contains_secret, load_redaction_rules, redact_text
from .search import SearchHit, search_cards
from .troubleshoot import (
    MAX_ERROR_CHARS,
    MAX_FIX_CHARS,
    MAX_PROJECT_CHARS,
    MAX_WORKSPACE_CHARS,
    TROUBLESHOOTING_NAME,
    FixHit,
    TroubleEntry,
    normalize_field,
    parse_registry,
    render_registry,
    search_entries,
)

PROJECTS_DIR = "projects"
TRASH_DIR = "trash"
META_NAME = "meta.json"
INDEX_NAME = "INDEX.md"
RECENT_NAME = "RECENT_ACTIVITY.md"
AUDIT_NAME = "audit.log"
_TRASH_NAME_RE = re.compile(
    r"^(?P<id>[a-z0-9]+(?:-[a-z0-9]+)*)-(?P<stamp>\d{8}T\d{6}Z)(?:-\d+)?\.md$"
)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RECENT_TS_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2})")


@dataclass
class InitResult:
    """Result of initializing a store."""

    home: Path
    created: list[Path]
    already_initialized: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "home": str(self.home),
            "created": [str(path) for path in self.created],
            "already_initialized": self.already_initialized,
        }


@dataclass
class RememberResult:
    """Result of recording a decision."""

    card: Card
    created: bool
    added: bool
    tags_added: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "card": self.card.to_dict(),
            "created": self.created,
            "added": self.added,
            "tags_added": list(self.tags_added),
        }


@dataclass
class ScanResult:
    """Valid cards plus per-file parse errors."""

    cards: list[Card] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TrashEntry:
    """One trashed card stored under ``trash/``."""

    filename: str
    project_id: str
    trashed_at: str
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "filename": self.filename,
            "project_id": self.project_id,
            "trashed_at": self.trashed_at,
            "size_bytes": self.size_bytes,
        }


@dataclass
class SupersedeResult:
    """Result of superseding a decision on a project card."""

    card: Card
    old_decision: str
    new_decision: str
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "card": self.card.to_dict(),
            "old_decision": self.old_decision,
            "new_decision": self.new_decision,
            "reason": self.reason,
        }


@dataclass
class UntagResult:
    """Result of removing tags from a project card."""

    card: Card
    removed_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "card": self.card.to_dict(),
            "removed_tags": list(self.removed_tags),
        }


@dataclass
class MergeResult:
    """Result of merging one project card into another."""

    source_id: str
    target: Card
    decisions_added: int
    superseded_added: int
    tags_added: list[str] = field(default_factory=list)
    source_trashed: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "source_id": self.source_id,
            "target": self.target.to_dict(),
            "decisions_added": self.decisions_added,
            "superseded_added": self.superseded_added,
            "tags_added": list(self.tags_added),
            "source_trashed": self.source_trashed,
        }


@dataclass
class DoctorReport:
    """Health report for a store."""

    ok: bool
    home: str
    initialized: bool
    schema_version: int | None
    cards: int
    malformed: list[str]
    unredacted: list[str]
    index_present: bool
    recent_present: bool
    audit_present: bool
    permissions_ok: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    audit_chain_status: str = "empty"
    audit_chain_ok: bool = True

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "ok": self.ok,
            "home": self.home,
            "initialized": self.initialized,
            "schema_version": self.schema_version,
            "cards": self.cards,
            "malformed": list(self.malformed),
            "unredacted": list(self.unredacted),
            "index_present": self.index_present,
            "recent_present": self.recent_present,
            "audit_present": self.audit_present,
            "permissions_ok": self.permissions_ok,
            "audit_chain_status": self.audit_chain_status,
            "audit_chain_ok": self.audit_chain_ok,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass
class DoctorFixResult:
    """Result of running ``engramkeep doctor --fix``."""

    actions: list[str]
    backup_dir: Path | None
    report: DoctorReport

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "actions": list(self.actions),
            "backup_dir": str(self.backup_dir) if self.backup_dir else None,
            "report": self.report.to_dict(),
        }


class Store:
    """A local-first Markdown memory store."""

    def __init__(self, home: Path | str):
        self.home = Path(home).expanduser().resolve()
        if self.home == Path(self.home.anchor):
            raise StoreError("memory home must not be a filesystem root")
        self.projects_dir = self.home / PROJECTS_DIR
        self.trash_dir = self.home / TRASH_DIR
        self.meta_path = self.home / META_NAME
        self.index_path = self.home / INDEX_NAME
        self.recent_path = self.home / RECENT_NAME
        self.audit_path = self.home / AUDIT_NAME
        self.troubleshooting_path = self.home / TROUBLESHOOTING_NAME
        self.lock_path = self.home / ".engramkeep.lock"

    @contextlib.contextmanager
    def _write_lock(self) -> Iterator[None]:
        ensure_private_dir(self.home)
        with file_lock(self.lock_path):
            yield

    def _read_meta(self) -> dict[str, object]:
        if is_link_or_junction(self.meta_path):
            raise StoreError("refusing to read meta.json through a symlink")
        if self.meta_path.exists() and not self.meta_path.is_file():
            raise StoreError("refusing to read non-regular meta.json")
        try:
            raw = self.meta_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except FileNotFoundError as exc:
            raise StoreError(f"store is not initialized: {self.home}") from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StoreError(f"cannot read {self.meta_path.name}: {exc}") from exc

        if not isinstance(data, dict):
            raise StoreError("meta.json must contain an object")
        version = data.get("schema_version")
        if not isinstance(version, int) or version < 1:
            raise StoreError("meta.json has an invalid schema_version")
        if version > SCHEMA_VERSION:
            raise StoreError(
                f"store schema {version} is newer than supported schema {SCHEMA_VERSION}"
            )
        if version < SCHEMA_VERSION:
            raise StoreError(
                f"store schema {version} is older than supported schema {SCHEMA_VERSION}; "
                "run 'engramkeep migrate --apply' to upgrade"
            )
        return data

    def is_initialized(self) -> bool:
        """Return True when a valid meta.json exists."""
        if not self.meta_path.exists():
            return False
        self._read_meta()
        return True

    def require_initialized(self) -> None:
        """Raise a helpful error when the store is missing or invalid."""
        if not self.is_initialized():
            raise StoreError(f"no Engramkeep store at {self.home}; run 'engramkeep init' first")

    def is_encrypted(self) -> bool:
        """Return True when ``meta.json`` marks the store encrypted or encrypted files exist."""
        if not self.is_initialized():
            return False
        try:
            meta = self._read_meta()
            if meta.get("encrypted") is True:
                return True
        except StoreError:
            pass
        if self.troubleshooting_path.is_file() and not is_link_or_junction(
            self.troubleshooting_path
        ):
            try:
                if is_encrypted_text(self.troubleshooting_path.read_text(encoding="utf-8")[:128]):
                    return True
            except (OSError, UnicodeDecodeError):
                pass
        if self.projects_dir.is_dir() and not is_link_or_junction(self.projects_dir):
            for path in sorted(self.projects_dir.glob("*.md")):
                if path.is_file() and not is_link_or_junction(path):
                    try:
                        if is_encrypted_text(path.read_text(encoding="utf-8")[:128]):
                            return True
                    except (OSError, UnicodeDecodeError):
                        pass
        return False

    def require_unencrypted(self) -> None:
        """Refuse normal read/write operations on an encrypted store to prevent data loss."""
        if self.is_encrypted():
            raise StoreError(
                "store is encrypted; run 'engramkeep decrypt --apply' before reading or writing"
            )

    def init(self) -> InitResult:
        """Create the store layout. Safe to call repeatedly."""
        with self._write_lock():
            return self._init_locked()

    def _init_locked(self) -> InitResult:
        created: list[Path] = []
        home_existed = self.home.exists()
        projects_existed = self.projects_dir.exists()
        trash_existed = self.trash_dir.exists()

        try:
            ensure_private_dir(self.home)
            if is_link_or_junction(self.projects_dir):
                raise StoreError("refusing to use symlinked projects directory")
            if is_link_or_junction(self.trash_dir):
                raise StoreError("refusing to use symlinked trash directory")
            ensure_private_dir(self.projects_dir)
            ensure_private_dir(self.trash_dir)
        except OSError as exc:
            raise StoreError(f"cannot create store directories under {self.home}: {exc}") from exc

        if not home_existed:
            created.append(self.home)
        if not projects_existed:
            created.append(self.projects_dir)
        if not trash_existed:
            created.append(self.trash_dir)

        already_initialized = self.meta_path.exists()
        if already_initialized:
            self._read_meta()
        else:
            meta = {
                "schema_version": SCHEMA_VERSION,
                "created": utc_now_iso(),
            }
            atomic_write_text(
                self.meta_path, json.dumps(meta, indent=2) + "\n", private_parent=True
            )
            created.append(self.meta_path)

        starter_files = (
            (self.index_path, self._render_index([])),
            (self.recent_path, "# Recent Activity\n\n"),
            (self.audit_path, ""),
            (self.troubleshooting_path, render_registry([])),
        )
        for path, content in starter_files:
            if path.exists():
                if is_link_or_junction(path):
                    raise StoreError(f"refusing to use symlinked store file: {path}")
                continue
            atomic_write_text(path, content, private_parent=True)
            created.append(path)

        if created:
            self._append_recent("initialized the store", project=None, tags=[])
            self._audit("init", None, {"schema_version": SCHEMA_VERSION})
        return InitResult(self.home, created, already_initialized)

    def _project_path(self, project: str) -> tuple[Path, str]:
        if is_link_or_junction(self.projects_dir):
            raise StoreError("refusing to use symlinked projects directory")
        project_id = normalize_project_id(project)
        return safe_join(self.projects_dir, f"{project_id}.md"), project_id

    def save_card(self, card: Card) -> Path:
        """Render and atomically write one card."""
        path, project_id = self._project_path(card.id)
        if project_id != card.id:
            raise StoreError("card id does not match its normalized form")
        atomic_write_text(path, render_card(card), private_parent=True)
        return path

    def get_card(self, project: str) -> Card | None:
        """Load one card, or return None when it does not exist."""
        self.require_initialized()
        self.require_unencrypted()
        path, project_id = self._project_path(project)
        if not path.exists():
            return None
        if is_link_or_junction(path) or not path.is_file():
            raise StoreError(f"refusing to read non-regular card: {path.name}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise StoreError(f"cannot read {path.name}: {exc}") from exc
        try:
            return parse_card(text, fallback_id=project_id)
        except CardParseError as exc:
            raise StoreError(f"cannot parse {path.name}: {exc}") from exc

    def scan_cards(self) -> ScanResult:
        """Read every regular card and collect per-file errors."""
        self.require_initialized()
        self.require_unencrypted()
        result = ScanResult()
        if is_link_or_junction(self.projects_dir) or not self.projects_dir.is_dir():
            result.errors.append("projects directory is missing or invalid")
            return result

        for path in sorted(self.projects_dir.glob("*.md")):
            if is_link_or_junction(path) or not path.is_file():
                result.errors.append(f"{path.name}: not a regular file")
                continue
            try:
                safe_path = safe_join(self.projects_dir, path.name)
                text = safe_path.read_text(encoding="utf-8")
                result.cards.append(parse_card(text, fallback_id=path.stem))
            except (OSError, UnicodeDecodeError, PathSafetyError, CardParseError) as exc:
                result.errors.append(f"{path.name}: {exc}")
        return result

    def list_cards(self) -> list[Card]:
        """Return valid cards sorted by most recently updated."""
        cards = self.scan_cards().cards
        cards.sort(key=lambda card: (card.updated, card.title.lower()), reverse=True)
        return cards

    def _redaction_rules(self) -> tuple[CustomRedactionRule, ...]:
        return load_redaction_rules(self.home)

    def remember(
        self,
        project: str,
        decision: str,
        *,
        tags: Iterable[str] = (),
    ) -> RememberResult:
        """Record a durable decision for a project."""
        self.require_initialized()
        self.require_unencrypted()
        project_id = normalize_project_id(project)
        raw_decision = str(decision)
        if len(raw_decision) > 262_144:
            raise ValidationError("decision exceeds maximum input size")
        sanitized = " ".join(strip_control_chars(raw_decision).split())
        cleaned = redact_text(sanitized, extra_rules=self._redaction_rules())
        normalized_tags = normalize_tags(tags)

        with self._write_lock():
            card = self.get_card(project_id)
            created = card is None
            if card is None:
                card = new_card(project_id)

            added = append_decision(card, cleaned)
            tags_added = add_tags(card, normalized_tags)
            if added or tags_added or created:
                self.save_card(card)
                self._write_index(self.scan_cards().cards)
                action = "remembered" if added else "updated tags for"
                self._append_recent(f"{action} **{card.title}** (`{card.id}`)", card.id, card.tags)
            self._audit(
                "remember",
                card.id,
                {"added": added, "created": created, "tags": list(card.tags)},
            )
            return RememberResult(card=card, created=created, added=added, tags_added=tags_added)

    def forget(self, project: str) -> bool:
        """Move a card to trash. Returns False when it does not exist."""
        self.require_initialized()
        self.require_unencrypted()
        with self._write_lock():
            if is_link_or_junction(self.trash_dir):
                raise StoreError("refusing to use symlinked trash directory")
            path, project_id = self._project_path(project)
            if not path.exists():
                return False
            if is_link_or_junction(path) or not path.is_file():
                raise StoreError(f"refusing to forget non-regular card: {path.name}")

            stamp = utc_now_iso().replace("-", "").replace(":", "")
            trash_path = safe_join(self.trash_dir, f"{project_id}-{stamp}.md")
            counter = 1
            while trash_path.exists():
                trash_path = safe_join(self.trash_dir, f"{project_id}-{stamp}-{counter}.md")
                counter += 1

            try:
                replace_file(path, trash_path)
            except OSError as exc:
                raise StoreError(f"cannot move {path.name} to trash: {exc}") from exc

            self._write_index(self.scan_cards().cards)
            self._append_recent(
                f"forgot **{display_title(project_id)}** (`{project_id}`)",
                project_id,
                [],
            )
            self._audit("forget", project_id, {"trashed_as": trash_path.name})
            return True

    def list_trash(self) -> list[TrashEntry]:
        """List recoverable cards currently in ``trash/``, newest first."""
        self.require_initialized()
        if is_link_or_junction(self.trash_dir):
            raise StoreError("refusing to read symlinked trash directory")
        if not self.trash_dir.is_dir():
            return []

        entries: list[TrashEntry] = []
        for path in sorted(self.trash_dir.glob("*.md")):
            if is_link_or_junction(path) or not path.is_file():
                continue
            try:
                safe_path = safe_join(self.trash_dir, path.name)
            except PathSafetyError:
                continue
            match = _TRASH_NAME_RE.match(safe_path.name)
            if match:
                project_id = match.group("id")
                raw_stamp = match.group("stamp")
                trashed_at = (
                    f"{raw_stamp[0:4]}-{raw_stamp[4:6]}-{raw_stamp[6:8]}T"
                    f"{raw_stamp[9:11]}:{raw_stamp[11:13]}:{raw_stamp[13:15]}Z"
                )
            else:
                project_id = safe_path.stem
                trashed_at = ""
            try:
                size = safe_path.stat().st_size
            except OSError:
                size = 0
            entries.append(
                TrashEntry(
                    filename=safe_path.name,
                    project_id=project_id,
                    trashed_at=trashed_at,
                    size_bytes=size,
                )
            )
        entries.sort(key=lambda item: (item.trashed_at, item.filename), reverse=True)
        return entries

    def restore(
        self,
        project: str,
        *,
        filename: str | None = None,
        force: bool = False,
    ) -> Card:
        """Restore a trashed card back to ``projects/``."""
        self.require_initialized()
        self.require_unencrypted()
        project_id = normalize_project_id(project)
        with self._write_lock():
            if is_link_or_junction(self.trash_dir):
                raise StoreError("refusing to use symlinked trash directory")
            if not self.trash_dir.is_dir():
                raise StoreError(f"no trashed card found for project: {project_id}")

            if filename is not None:
                trash_path = safe_join(self.trash_dir, filename)
                if not trash_path.exists() or is_link_or_junction(trash_path):
                    raise StoreError(f"trashed file not found: {filename}")
                if not (
                    trash_path.name == f"{project_id}.md"
                    or trash_path.name.startswith(f"{project_id}-")
                ):
                    raise StoreError(
                        f"trashed file {trash_path.name!r} does not belong to "
                        f"project {project_id!r}"
                    )
            else:
                candidates = [item for item in self.list_trash() if item.project_id == project_id]
                if not candidates:
                    raise StoreError(f"no trashed card found for project: {project_id}")
                trash_path = safe_join(self.trash_dir, candidates[0].filename)

            dest_path, _ = self._project_path(project_id)
            if dest_path.exists() and not force:
                raise StoreError(
                    f"project {project_id!r} already exists; pass --force to overwrite it"
                )
            try:
                text = trash_path.read_text(encoding="utf-8")
                card = parse_card(text, fallback_id=project_id)
            except (OSError, UnicodeDecodeError, CardParseError) as exc:
                raise StoreError(f"cannot restore {trash_path.name}: {exc}") from exc

            if dest_path.exists() and force:
                stamp = utc_now_iso().replace("-", "").replace(":", "")
                backup_name = f"{project_id}-pre-restore-{stamp}.md"
                backup_path = safe_join(self.trash_dir, backup_name)
                counter = 1
                while backup_path.exists():
                    backup_path = safe_join(
                        self.trash_dir, f"{project_id}-pre-restore-{stamp}-{counter}.md"
                    )
                    counter += 1
                replace_file(dest_path, backup_path)

            try:
                replace_file(trash_path, dest_path)
            except OSError as exc:
                raise StoreError(f"cannot restore {trash_path.name}: {exc}") from exc

            self._write_index(self.scan_cards().cards)
            self._append_recent(
                f"restored **{card.title}** (`{card.id}`)",
                card.id,
                card.tags,
            )
            self._audit("restore", card.id, {"from_trash": trash_path.name})
            return card

    def purge_trash(self, *, project: str | None = None) -> int:
        """Permanently delete files in ``trash/`` (optionally filtered by project)."""
        self.require_initialized()
        target_id = normalize_project_id(project) if project else None
        with self._write_lock():
            if is_link_or_junction(self.trash_dir):
                raise StoreError("refusing to use symlinked trash directory")
            if not self.trash_dir.is_dir():
                return 0
            removed = 0
            for item in self.list_trash():
                if target_id is not None and item.project_id != target_id:
                    continue
                trash_path = safe_join(self.trash_dir, item.filename)
                if is_link_or_junction(trash_path) or not trash_path.is_file():
                    continue
                try:
                    trash_path.unlink()
                except OSError as exc:
                    raise StoreError(f"cannot purge {item.filename}: {exc}") from exc
                removed += 1
            if removed:
                self._audit("purge_trash", target_id, {"removed": removed})
            return removed

    def supersede(
        self,
        project: str,
        old_decision: str,
        new_decision: str,
        *,
        reason: str | None = None,
    ) -> SupersedeResult:
        """Supersede an existing decision with a new one while preserving history."""
        self.require_initialized()
        project_id = normalize_project_id(project)
        raw_new = str(new_decision)
        if len(raw_new) > 262_144:
            raise ValidationError("decision exceeds maximum input size")
        rules = self._redaction_rules()
        clean_new = redact_text(" ".join(strip_control_chars(raw_new).split()), extra_rules=rules)
        clean_reason = (
            redact_text(" ".join(strip_control_chars(str(reason)).split()), extra_rules=rules)
            if reason is not None and str(reason).strip()
            else None
        )

        with self._write_lock():
            card = self.get_card(project_id)
            if card is None:
                raise StoreError(f"project not found: {project}")
            matched_old, recorded_new = supersede_decision(
                card,
                old_decision,
                clean_new,
                reason=clean_reason,
            )
            self.save_card(card)
            self._write_index(self.scan_cards().cards)
            self._append_recent(
                f"superseded a decision in **{card.title}** (`{card.id}`)",
                card.id,
                card.tags,
            )
            self._audit("supersede", card.id, {"has_reason": bool(clean_reason)})
            return SupersedeResult(
                card=card,
                old_decision=matched_old,
                new_decision=recorded_new,
                reason=clean_reason,
            )

    def untag(self, project: str, tags: Iterable[str]) -> UntagResult:
        """Remove one or more tags from an existing project card."""
        self.require_initialized()
        project_id = normalize_project_id(project)
        normalized = normalize_tags(tags)
        if not normalized:
            raise ValidationError("at least one tag is required")

        with self._write_lock():
            card = self.get_card(project_id)
            if card is None:
                raise StoreError(f"project not found: {project}")
            removed = remove_tags(card, normalized)
            if removed:
                self.save_card(card)
                self._write_index(self.scan_cards().cards)
                self._append_recent(
                    f"removed tags from **{card.title}** (`{card.id}`)",
                    card.id,
                    card.tags,
                )
            self._audit("untag", card.id, {"removed": removed, "tags": list(card.tags)})
            return UntagResult(card=card, removed_tags=removed)

    def remove_decision(self, project: str, decision: str) -> tuple[Card, str]:
        """Remove a single decision bullet from a project card without deleting the card."""
        self.require_initialized()
        project_id = normalize_project_id(project)
        with self._write_lock():
            card = self.get_card(project_id)
            if card is None:
                raise StoreError(f"project not found: {project}")
            removed_text = remove_decision(card, decision)
            self.save_card(card)
            self._write_index(self.scan_cards().cards)
            self._append_recent(
                f"removed a decision from **{card.title}** (`{card.id}`)",
                card.id,
                card.tags,
            )
            self._audit("remove_decision", card.id, {"removed": True})
            return card, removed_text

    def merge(
        self,
        source_project: str,
        target_project: str,
        *,
        delete_source: bool = False,
    ) -> MergeResult:
        """Merge decisions, superseded history, and tags from ``source`` into ``target``."""
        self.require_initialized()
        src_id = normalize_project_id(source_project)
        dst_id = normalize_project_id(target_project)
        if src_id == dst_id:
            raise ValidationError("source and target projects must be different")

        with self._write_lock():
            source_card = self.get_card(src_id)
            if source_card is None:
                raise StoreError(f"source project not found: {source_project}")
            target_card = self.get_card(dst_id)
            if target_card is None:
                target_card = new_card(dst_id)

            merged, dec_added, sup_added, tags_added = merge_cards(source_card, target_card)
            self.save_card(merged)
            source_trashed = False
            if delete_source:
                source_trashed = self.forget(src_id)
            self._write_index(self.scan_cards().cards)
            self._append_recent(
                f"merged **{source_card.title}** (`{src_id}`) into **{merged.title}** (`{dst_id}`)",
                dst_id,
                merged.tags,
            )
            self._audit(
                "merge",
                dst_id,
                {
                    "source": src_id,
                    "decisions_added": dec_added,
                    "superseded_added": sup_added,
                    "tags_added": tags_added,
                    "source_trashed": source_trashed,
                },
            )
            return MergeResult(
                source_id=src_id,
                target=merged,
                decisions_added=dec_added,
                superseded_added=sup_added,
                tags_added=tags_added,
                source_trashed=source_trashed,
            )

    def reindex(self) -> ScanResult:
        """Regenerate INDEX.md from the valid cards."""
        self.require_initialized()
        with self._write_lock():
            scan = self.scan_cards()
            self._write_index(scan.cards)
            self._audit("reindex", None, {"cards": len(scan.cards), "errors": len(scan.errors)})
            return scan

    def recent(self, limit: int = 10, *, since: str | None = None) -> list[str]:
        """Return recent activity bullets, newest first, optionally filtered by ``since``."""
        self.require_initialized()
        since_date: str | None = None
        if since is not None and since.strip():
            candidate = since.strip()
            if not _ISO_DATE_RE.match(candidate):
                raise ValidationError(f"invalid --since date {since!r}; expected YYYY-MM-DD")
            try:
                date.fromisoformat(candidate)
            except ValueError as exc:
                raise ValidationError(
                    f"invalid --since date {since!r}; expected a valid calendar date YYYY-MM-DD"
                ) from exc
            since_date = candidate
        if limit <= 0 or not self.recent_path.exists():
            return []
        if is_link_or_junction(self.recent_path):
            raise StoreError("refusing to read RECENT_ACTIVITY.md through a symlink")
        if not self.recent_path.is_file():
            raise StoreError("refusing to read non-regular RECENT_ACTIVITY.md")
        try:
            lines = self.recent_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise StoreError(f"cannot read {self.recent_path.name}: {exc}") from exc
        bullets = [line for line in lines if line.startswith("- ")]
        if since_date is not None:
            filtered: list[str] = []
            for bullet in bullets:
                match = _RECENT_TS_RE.match(bullet)
                if match and match.group(1) >= since_date:
                    filtered.append(bullet)
            bullets = filtered
        return list(reversed(bullets[-limit:]))

    def _read_troubleshooting(self) -> list[TroubleEntry]:
        self.require_unencrypted()
        if not self.troubleshooting_path.exists():
            return []
        if is_link_or_junction(self.troubleshooting_path):
            raise StoreError("refusing to read TROUBLESHOOTING.md through a symlink")
        if not self.troubleshooting_path.is_file():
            raise StoreError("TROUBLESHOOTING.md is not a regular file")
        try:
            text = self.troubleshooting_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise StoreError(f"cannot read {TROUBLESHOOTING_NAME}: {exc}") from exc
        return parse_registry(text)

    def _write_troubleshooting(self, entries: list[TroubleEntry]) -> None:
        atomic_write_text(self.troubleshooting_path, render_registry(entries), private_parent=True)

    def record_fix_result(
        self,
        error: str,
        fix: str,
        *,
        project: str | None = None,
        workspace: str | None = None,
    ) -> tuple[TroubleEntry, bool]:
        """Record a resolved problem if not already present.

        Returns ``(entry, added)`` where ``added`` is False when an equivalent
        ``(project, error, fix)`` entry already exists in ``TROUBLESHOOTING.md``.
        """
        self.require_initialized()
        rules = self._redaction_rules()
        try:
            clean_error = redact_text(
                normalize_field(error, max_chars=MAX_ERROR_CHARS, name="error"),
                extra_rules=rules,
            )
            clean_fix = redact_text(
                normalize_field(fix, max_chars=MAX_FIX_CHARS, name="fix"),
                extra_rules=rules,
            )
            clean_project = (
                redact_text(
                    normalize_field(project, max_chars=MAX_PROJECT_CHARS, name="project"),
                    extra_rules=rules,
                )
                if project is not None and str(project).strip()
                else "General"
            )
            clean_workspace = (
                redact_text(
                    normalize_field(workspace, max_chars=MAX_WORKSPACE_CHARS, name="workspace"),
                    extra_rules=rules,
                )
                if workspace is not None and str(workspace).strip()
                else None
            )
        except ValueError as exc:
            raise StoreError(str(exc)) from exc

        entry = TroubleEntry(
            project=clean_project,
            error=clean_error,
            fix=clean_fix,
            workspace=clean_workspace,
            date=utc_now_iso()[:10],
        )
        dedup_key = entry.dedup_key()
        with self._write_lock():
            entries = self._read_troubleshooting()
            for existing in entries:
                if existing.dedup_key() == dedup_key:
                    self._audit(
                        "record_fix",
                        existing.project,
                        {
                            "error": existing.error[:120],
                            "workspace": existing.workspace or "General",
                            "duplicate": True,
                        },
                    )
                    return existing, False

            entries.append(entry)
            self._write_troubleshooting(entries)
            self._append_recent(
                f"recorded a fix for **{entry.project}**: {entry.error[:80]}",
                None,
                [],
            )
            self._audit(
                "record_fix",
                entry.project,
                {
                    "error": entry.error[:120],
                    "workspace": entry.workspace or "General",
                    "duplicate": False,
                },
            )
            return entry, True

    def record_fix(
        self,
        error: str,
        fix: str,
        *,
        project: str | None = None,
        workspace: str | None = None,
    ) -> TroubleEntry:
        """Record one resolved problem and its verified fix (deduplicated)."""
        entry, _ = self.record_fix_result(error, fix, project=project, workspace=workspace)
        return entry

    def search_fixes(self, query: str | None, *, limit: int = 10) -> list[FixHit]:
        """Search the troubleshooting registry, or list the newest entries."""
        self.require_initialized()
        entries = self._read_troubleshooting()
        return search_entries(entries, query, limit=limit)

    def export_cards(self) -> dict[str, object]:
        """Return all valid cards as a JSON-serializable document."""
        self.require_initialized()
        scan = self.scan_cards()
        cards = sorted(scan.cards, key=lambda card: card.id)
        export_doc = {
            "schema_version": SCHEMA_VERSION,
            "exported_at": utc_now_iso(),
            "cards": [card.to_dict() for card in cards],
            "errors": list(scan.errors),
            "fixes": [entry.to_dict() for entry in self._read_troubleshooting()],
        }
        return export_doc

    def verify_audit(self) -> AuditVerification:
        """Verify the SHA-256 hash chain of ``audit.log``."""
        return verify_audit_log(self.audit_path)

    def doctor(self) -> DoctorReport:
        """Inspect the store without modifying it."""
        report = DoctorReport(
            ok=False,
            home=str(self.home),
            initialized=False,
            schema_version=None,
            cards=0,
            malformed=[],
            unredacted=[],
            index_present=self.index_path.is_file(),
            recent_present=self.recent_path.is_file(),
            audit_present=self.audit_path.is_file(),
            permissions_ok=is_private_path(self.home),
        )

        if not self.meta_path.exists():
            report.errors.append("store is not initialized")
            return report
        try:
            meta = self._read_meta()
        except StoreError as exc:
            report.errors.append(str(exc))
            return report

        report.initialized = True
        version = meta.get("schema_version")
        report.schema_version = version if isinstance(version, int) else None
        report.permissions_ok = is_private_path(self.home)

        if not report.index_present:
            report.warnings.append("INDEX.md is missing; run 'engramkeep reindex'")
        if not report.recent_present:
            report.warnings.append("RECENT_ACTIVITY.md is missing")
        if not report.audit_present:
            report.warnings.append("audit.log is missing")
        if not self.troubleshooting_path.is_file():
            report.warnings.append(
                "TROUBLESHOOTING.md is missing; run 'engramkeep init' to create it"
            )
        if not report.permissions_ok:
            report.warnings.append("store directory is accessible by group or others")

        audit_check = verify_audit_log(self.audit_path)
        report.audit_chain_status = audit_check.status
        report.audit_chain_ok = audit_check.ok
        if not audit_check.ok:
            report.errors.append(f"audit.log integrity check failed: {audit_check.message}")
        elif audit_check.status == "legacy":
            report.warnings.append(audit_check.message)

        try:
            rules = self._redaction_rules()
        except ValidationError as exc:
            report.errors.append(str(exc))
            rules = ()

        if self.is_encrypted():
            report.errors.append(
                "store is encrypted; run 'engramkeep decrypt --apply' before normal use"
            )
            report.ok = False
            return report

        scan = self.scan_cards()
        report.cards = len(scan.cards)
        report.malformed = list(scan.errors)
        titles_seen: dict[str, list[str]] = {}
        for card in scan.cards:
            if contains_secret(render_card(card), extra_rules=rules):
                report.unredacted.append(card.id)
            key = card.title.strip().lower()
            titles_seen.setdefault(key, []).append(card.id)
        for ids in titles_seen.values():
            if len(ids) > 1:
                report.warnings.append(
                    f"duplicate card title shared by projects: {', '.join(sorted(ids))}"
                )
        try:
            for entry in self._read_troubleshooting():
                if contains_secret(
                    f"{entry.error}\n{entry.fix}\n{entry.workspace or ''}",
                    extra_rules=rules,
                ):
                    report.unredacted.append(f"fix:{entry.project}")
        except StoreError as exc:
            report.errors.append(str(exc))

        if report.malformed:
            report.errors.append(f"{len(report.malformed)} malformed card(s)")
        if report.unredacted:
            report.errors.append(
                f"{len(report.unredacted)} memory entr(y/ies) contain unredacted secrets or PII"
            )

        report.ok = not report.errors
        return report

    def doctor_fix(self) -> DoctorFixResult:
        """Safely repair recoverable store issues with backups.

        Repairs missing directories/files, stale ``INDEX.md``, broad POSIX
        permissions, and leftover temporary ``.*.tmp`` files. Never deletes
        malformed cards or modifies unredacted content automatically.
        """
        self.require_initialized()
        actions: list[str] = []
        backup_dir: Path | None = None

        def _ensure_backup_dir() -> Path:
            nonlocal backup_dir
            if backup_dir is not None:
                return backup_dir
            stamp = utc_now_iso().replace("-", "").replace(":", "")
            candidate = self.home / "backups" / "doctor" / f"{stamp}-{os.getpid()}"
            counter = 1
            while candidate.exists():
                candidate = self.home / "backups" / "doctor" / f"{stamp}-{os.getpid()}-{counter}"
                counter += 1
            backup_dir = ensure_private_dir(candidate)
            return backup_dir

        def _backup_if_exists(path: Path) -> None:
            if path.is_file() and not is_link_or_junction(path):
                dst = _ensure_backup_dir() / path.name
                shutil.copy2(path, dst)

        with self._write_lock():
            if not is_private_path(self.home):
                ensure_private_dir(self.home)
                actions.append("tightened permissions on store directory")

            for directory, label in (
                (self.projects_dir, "projects/"),
                (self.trash_dir, "trash/"),
            ):
                if is_link_or_junction(directory):
                    raise StoreError(f"refusing to repair symlinked directory: {label}")
                if not directory.exists():
                    ensure_private_dir(directory)
                    actions.append(f"created missing directory {label}")
                elif not is_private_path(directory):
                    ensure_private_dir(directory)
                    actions.append(f"tightened permissions on {label}")

            if not self.recent_path.exists():
                atomic_write_text(self.recent_path, "# Recent Activity\n\n", private_parent=True)
                actions.append("created missing RECENT_ACTIVITY.md")
            if not self.audit_path.exists():
                atomic_write_text(self.audit_path, "", private_parent=True)
                actions.append("created missing audit.log")
            if not self.troubleshooting_path.exists():
                atomic_write_text(
                    self.troubleshooting_path, render_registry([]), private_parent=True
                )
                actions.append("created missing TROUBLESHOOTING.md")

            scan = self.scan_cards()
            expected_index = self._render_index(scan.cards)
            if not self.index_path.is_file():
                self._write_index(scan.cards)
                actions.append("regenerated missing INDEX.md")
            else:
                try:
                    current_index = self.index_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    current_index = ""
                if current_index != expected_index:
                    _backup_if_exists(self.index_path)
                    self._write_index(scan.cards)
                    actions.append("rebuilt out-of-sync INDEX.md")

            # Clean stale atomic-write temporary files in store root and projects/.
            for directory in (self.home, self.projects_dir):
                if not directory.is_dir() or is_link_or_junction(directory):
                    continue
                for tmp_file in sorted(directory.glob(".*.tmp")):
                    if is_link_or_junction(tmp_file) or not tmp_file.is_file():
                        continue
                    with contextlib.suppress(OSError):
                        tmp_file.unlink()
                        actions.append(f"removed stale temporary file {tmp_file.name}")

            if actions:
                self._audit("doctor_fix", None, {"actions": len(actions)})

        report = self.doctor()
        return DoctorFixResult(actions=actions, backup_dir=backup_dir, report=report)

    def _render_index(self, cards: Iterable[Card]) -> str:
        ordered = sorted(cards, key=lambda card: (card.updated, card.title.lower()), reverse=True)
        lines = [
            "# Engramkeep Index",
            "",
            "Generated by Engramkeep. Do not edit by hand.",
            "",
            "| Project | Tags | Updated |",
            "| --- | --- | --- |",
        ]
        for card in ordered:
            title = (
                card.title.replace("\\", "\\\\")
                .replace("|", "\\|")
                .replace("[", "\\[")
                .replace("]", "\\]")
            )
            tags = ", ".join(card.tags) if card.tags else "-"
            updated = card.updated[:10] if card.updated else "-"
            lines.append(f"| [{title}](projects/{card.id}.md) | {tags} | {updated} |")
        lines.append("")
        return "\n".join(lines)

    def _write_index(self, cards: Iterable[Card]) -> None:
        atomic_write_text(self.index_path, self._render_index(cards), private_parent=True)

    def _append_recent(self, message: str, project: str | None, tags: list[str]) -> None:
        if not self.recent_path.exists():
            atomic_write_text(self.recent_path, "# Recent Activity\n\n", private_parent=True)
        line = f"- {utc_now_iso()} - {message}"
        if tags:
            line += f"; tags: {', '.join(tags)}"
        append_text(self.recent_path, line + "\n")

    def _audit(self, action: str, project: str | None, details: dict[str, object]) -> None:
        entry: dict[str, object] = {"ts": utc_now_iso(), "action": action}
        if project:
            entry["project"] = project
        entry.update(details)
        prev = last_audit_hash(self.audit_path)
        sealed = seal_audit_entry(entry, prev)
        append_text(self.audit_path, json.dumps(sealed, ensure_ascii=False, sort_keys=True) + "\n")


class LayeredStore:
    """Read-overlay combining an optional project ``.engramkeep/`` store with global memory.

    When a project store is present, its cards take precedence over global cards
    with the same project id, while unique cards and fixes from both layers are
    returned together with explicit ``source`` attribution (``"project"`` or
    ``"global"``).
    """

    def __init__(self, global_store: Store, project_store: Store | None = None) -> None:
        self.global_store = global_store
        if project_store is not None and project_store.home == global_store.home:
            self.project_store: Store | None = None
        else:
            self.project_store = project_store

    @property
    def is_layered(self) -> bool:
        """Return True when both a project store and a global store are active."""
        return self.project_store is not None and self.project_store.is_initialized()

    def _active_layers(self) -> list[tuple[str, Store]]:
        layers: list[tuple[str, Store]] = []
        if self.project_store is not None and self.project_store.is_initialized():
            layers.append(("project", self.project_store))
        if self.global_store.is_initialized():
            layers.append(("global", self.global_store))
        if not layers:
            raise StoreError(
                f"no Engramkeep store at {self.global_store.home}; run 'engramkeep init' first"
            )
        return layers

    def get_card(self, project: str) -> tuple[Card, str] | None:
        """Return ``(card, source)`` from project layer first, then global."""
        for source, layer in self._active_layers():
            card = layer.get_card(project)
            if card is not None:
                return card, source
        return None

    def scan_cards(self) -> tuple[list[Card], dict[str, str], list[str]]:
        """Scan active layers, merging by card id with project precedence."""
        merged: dict[str, Card] = {}
        sources: dict[str, str] = {}
        errors: list[str] = []
        for source, layer in self._active_layers():
            scan = layer.scan_cards()
            errors.extend(f"[{source}] {err}" for err in scan.errors)
            for card in scan.cards:
                if card.id not in merged:
                    merged[card.id] = card
                    sources[card.id] = source
        return list(merged.values()), sources, errors

    def search(
        self,
        query: str,
        *,
        tag: str | None = None,
        tags: Iterable[str] | None = None,
        limit: int = 10,
    ) -> tuple[list[SearchHit], list[str]]:
        """Search cards across all active layers and annotate hits with ``source``."""
        cards, sources, errors = self.scan_cards()
        hits = search_cards(cards, query, tag=tag, tags=tags, limit=limit)
        if not self.is_layered:
            return hits, errors
        annotated = [
            SearchHit(
                id=hit.id,
                title=hit.title,
                score=hit.score,
                snippet=hit.snippet,
                tags=hit.tags,
                updated=hit.updated,
                source=sources.get(hit.id, "global"),
            )
            for hit in hits
        ]
        return annotated, errors

    def search_fixes(self, query: str | None, *, limit: int = 10) -> list[FixHit]:
        """Search troubleshooting registries across active layers, deduplicating entries."""
        entries: list[TroubleEntry] = []
        source_by_key: dict[tuple[str, str, str], str] = {}
        for source, layer in self._active_layers():
            for entry in layer._read_troubleshooting():
                key = entry.dedup_key()
                if key not in source_by_key:
                    source_by_key[key] = source
                    entries.append(entry)
        hits = search_entries(entries, query, limit=limit)
        if not self.is_layered:
            return hits
        return [
            FixHit(
                entry=hit.entry,
                score=hit.score,
                source=source_by_key.get(hit.entry.dedup_key(), "global"),
            )
            for hit in hits
        ]

    def merged_troubleshooting_markdown(self) -> str:
        """Render the deduplicated troubleshooting registry across active layers."""
        entries: list[TroubleEntry] = []
        seen: set[tuple[str, str, str]] = set()
        for _, layer in self._active_layers():
            for entry in layer._read_troubleshooting():
                key = entry.dedup_key()
                if key not in seen:
                    seen.add(key)
                    entries.append(entry)
        return render_registry(entries)
