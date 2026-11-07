"""Local Markdown store: cards, index, activity log, audit trail, trash."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .config import SCHEMA_VERSION
from .errors import CardParseError, PathSafetyError, StoreError
from .models import (
    Card,
    add_tags,
    append_decision,
    new_card,
    normalize_tags,
    parse_card,
    render_card,
    utc_now_iso,
)
from .paths import (
    append_text,
    atomic_write_text,
    display_title,
    ensure_private_dir,
    is_private_path,
    normalize_project_id,
    safe_join,
)
from .redact import contains_secret, redact_text

PROJECTS_DIR = "projects"
TRASH_DIR = "trash"
META_NAME = "meta.json"
INDEX_NAME = "INDEX.md"
RECENT_NAME = "RECENT_ACTIVITY.md"
AUDIT_NAME = "audit.log"


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
            "warnings": list(self.warnings),
            "errors": list(self.errors),
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

    def _read_meta(self) -> dict[str, object]:
        if self.meta_path.is_symlink():
            raise StoreError("refusing to read meta.json through a symlink")
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
                "migration is not implemented in this release"
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

    def init(self) -> InitResult:
        """Create the store layout. Safe to call repeatedly."""
        created: list[Path] = []
        home_existed = self.home.exists()
        projects_existed = self.projects_dir.exists()
        trash_existed = self.trash_dir.exists()

        try:
            ensure_private_dir(self.home)
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
            atomic_write_text(self.meta_path, json.dumps(meta, indent=2) + "\n")
            created.append(self.meta_path)

        starter_files = (
            (self.index_path, self._render_index([])),
            (self.recent_path, "# Recent Activity\n\n"),
            (self.audit_path, ""),
        )
        for path, content in starter_files:
            if path.exists():
                if path.is_symlink():
                    raise StoreError(f"refusing to use symlinked store file: {path}")
                continue
            atomic_write_text(path, content)
            created.append(path)

        if created:
            self._append_recent("initialized the store", project=None, tags=[])
            self._audit("init", None, {"schema_version": SCHEMA_VERSION})
        return InitResult(self.home, created, already_initialized)

    def _project_path(self, project: str) -> tuple[Path, str]:
        project_id = normalize_project_id(project)
        return safe_join(self.projects_dir, f"{project_id}.md"), project_id

    def save_card(self, card: Card) -> Path:
        """Render and atomically write one card."""
        path, project_id = self._project_path(card.id)
        if project_id != card.id:
            raise StoreError("card id does not match its normalized form")
        atomic_write_text(path, render_card(card))
        return path

    def get_card(self, project: str) -> Card | None:
        """Load one card, or return None when it does not exist."""
        self.require_initialized()
        path, project_id = self._project_path(project)
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
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
        result = ScanResult()
        if not self.projects_dir.is_dir():
            result.errors.append("projects directory is missing")
            return result

        for path in sorted(self.projects_dir.glob("*.md")):
            if path.is_symlink() or not path.is_file():
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

    def remember(
        self,
        project: str,
        decision: str,
        *,
        tags: Iterable[str] = (),
    ) -> RememberResult:
        """Record a durable decision for a project."""
        self.require_initialized()
        project_id = normalize_project_id(project)
        cleaned = redact_text(str(decision))
        normalized_tags = normalize_tags(tags)

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
        path, project_id = self._project_path(project)
        if not path.exists():
            return False
        if path.is_symlink() or not path.is_file():
            raise StoreError(f"refusing to forget non-regular card: {path.name}")

        stamp = utc_now_iso().replace("-", "").replace(":", "")
        trash_path = safe_join(self.trash_dir, f"{project_id}-{stamp}.md")
        counter = 1
        while trash_path.exists():
            trash_path = safe_join(self.trash_dir, f"{project_id}-{stamp}-{counter}.md")
            counter += 1

        try:
            os.replace(path, trash_path)
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

    def reindex(self) -> ScanResult:
        """Regenerate INDEX.md from the valid cards."""
        self.require_initialized()
        scan = self.scan_cards()
        self._write_index(scan.cards)
        self._audit("reindex", None, {"cards": len(scan.cards), "errors": len(scan.errors)})
        return scan

    def recent(self, limit: int = 10) -> list[str]:
        """Return recent activity bullets, newest first."""
        self.require_initialized()
        if limit <= 0 or not self.recent_path.exists():
            return []
        if self.recent_path.is_symlink():
            raise StoreError("refusing to read RECENT_ACTIVITY.md through a symlink")
        try:
            lines = self.recent_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise StoreError(f"cannot read {self.recent_path.name}: {exc}") from exc
        bullets = [line for line in lines if line.startswith("- ")]
        return list(reversed(bullets[-limit:]))

    def export_cards(self) -> dict[str, object]:
        """Return all valid cards as a JSON-serializable document."""
        self.require_initialized()
        scan = self.scan_cards()
        cards = sorted(scan.cards, key=lambda card: card.id)
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": utc_now_iso(),
            "cards": [card.to_dict() for card in cards],
            "errors": list(scan.errors),
        }

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
        if not report.permissions_ok:
            report.warnings.append("store directory is accessible by group or others")

        scan = self.scan_cards()
        report.cards = len(scan.cards)
        report.malformed = list(scan.errors)
        for card in scan.cards:
            if contains_secret(render_card(card)):
                report.unredacted.append(card.id)

        if report.malformed:
            report.errors.append(f"{len(report.malformed)} malformed card(s)")
        if report.unredacted:
            report.errors.append(
                f"{len(report.unredacted)} card(s) contain unredacted secrets or PII"
            )

        report.ok = not report.errors
        return report

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
            title = card.title.replace("|", "\\|")
            tags = ", ".join(card.tags) if card.tags else "-"
            updated = card.updated[:10] if card.updated else "-"
            lines.append(f"| [{title}](projects/{card.id}.md) | {tags} | {updated} |")
        lines.append("")
        return "\n".join(lines)

    def _write_index(self, cards: Iterable[Card]) -> None:
        atomic_write_text(self.index_path, self._render_index(cards))

    def _append_recent(self, message: str, project: str | None, tags: list[str]) -> None:
        if not self.recent_path.exists():
            atomic_write_text(self.recent_path, "# Recent Activity\n\n")
        line = f"- {utc_now_iso()} - {message}"
        if tags:
            line += f"; tags: {', '.join(tags)}"
        append_text(self.recent_path, line + "\n")

    def _audit(self, action: str, project: str | None, details: dict[str, object]) -> None:
        entry: dict[str, object] = {"ts": utc_now_iso(), "action": action}
        if project:
            entry["project"] = project
        entry.update(details)
        append_text(self.audit_path, json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
