"""Schema migration framework with automatic backups and rollback.

Migrations are dry-run by default. When ``apply=True``, the store snapshot is
copied into ``<home>/backups/migrations/<timestamp>-<pid>/`` before any file is
modified. If any step raises an error, the backup is restored automatically.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .audit import seal_audit_sequence, verify_audit_log
from .config import SCHEMA_VERSION
from .errors import StoreError
from .models import utc_now_iso
from .paths import atomic_write_text, ensure_private_dir, file_lock, is_link_or_junction, safe_join
from .store import AUDIT_NAME, INDEX_NAME, META_NAME, PROJECTS_DIR, RECENT_NAME, TRASH_DIR, Store
from .troubleshoot import TROUBLESHOOTING_NAME, render_registry

_MANAGED_TOP_FILES = (
    META_NAME,
    INDEX_NAME,
    RECENT_NAME,
    AUDIT_NAME,
    TROUBLESHOOTING_NAME,
)


@dataclass(frozen=True)
class MigrationStep:
    """One deterministic schema upgrade step."""

    from_version: int
    to_version: int
    description: str
    apply_fn: Callable[[Path], list[str]]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "description": self.description,
        }


@dataclass(frozen=True)
class MigrationPlan:
    """Planned migration actions for a store."""

    current_version: int
    target_version: int
    steps: tuple[MigrationStep, ...]
    audit_needs_seal: bool

    @property
    def has_work(self) -> bool:
        """Return True when at least one migration or audit-seal action is needed."""
        return bool(self.steps) or self.audit_needs_seal

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "current_version": self.current_version,
            "target_version": self.target_version,
            "steps": [step.to_dict() for step in self.steps],
            "audit_needs_seal": self.audit_needs_seal,
            "has_work": self.has_work,
        }


@dataclass
class MigrationResult:
    """Outcome of running ``migrate_store``."""

    mode: str
    from_version: int
    to_version: int
    steps_applied: list[str] = field(default_factory=list)
    audit_sealed: bool = False
    backup_dir: Path | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "mode": self.mode,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "steps_applied": list(self.steps_applied),
            "audit_sealed": self.audit_sealed,
            "backup_dir": str(self.backup_dir) if self.backup_dir else None,
        }


@dataclass
class RollbackResult:
    """Outcome of restoring a store from a migration backup."""

    backup_dir: Path
    restored_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "backup_dir": str(self.backup_dir),
            "restored_files": list(self.restored_files),
        }


def _migrate_v0_to_v1(home: Path) -> list[str]:
    """Upgrade a legacy pre-meta or schema 0 store to schema version 1."""
    actions: list[str] = []
    ensure_private_dir(home / PROJECTS_DIR)
    ensure_private_dir(home / TRASH_DIR)

    meta_path = home / META_NAME
    created = utc_now_iso()
    if meta_path.is_file() and not is_link_or_junction(meta_path):
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("created"), str):
                created = existing["created"]
        except (OSError, json.JSONDecodeError):
            pass

    atomic_write_text(
        meta_path,
        json.dumps({"schema_version": 1, "created": created}, indent=2) + "\n",
        private_parent=True,
    )
    actions.append("wrote meta.json with schema_version=1")

    for filename, default_content in (
        (RECENT_NAME, "# Recent Activity\n\n"),
        (AUDIT_NAME, ""),
        (TROUBLESHOOTING_NAME, render_registry([])),
    ):
        target = home / filename
        if not target.exists():
            atomic_write_text(target, default_content, private_parent=True)
            actions.append(f"created {filename}")

    store = Store(home)
    scan = store.scan_cards()
    store._write_index(scan.cards)
    actions.append(f"rebuilt INDEX.md for {len(scan.cards)} card(s)")
    return actions


BUILTIN_MIGRATIONS: tuple[MigrationStep, ...] = (
    MigrationStep(
        from_version=0,
        to_version=1,
        description="Initialize schema v1 metadata, starter files, and index",
        apply_fn=_migrate_v0_to_v1,
    ),
)


def _detect_schema_version(home: Path) -> int:
    meta_path = home / META_NAME
    if not meta_path.exists():
        if (home / PROJECTS_DIR).is_dir():
            return 0
        raise StoreError(f"no Engramkeep store at {home}; run 'engramkeep init' first")
    if is_link_or_junction(meta_path) or not meta_path.is_file():
        raise StoreError("refusing to read symlinked or non-regular meta.json")
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StoreError(f"cannot read meta.json: {exc}") from exc
    if not isinstance(data, dict):
        raise StoreError("meta.json must contain an object")
    version = data.get("schema_version", 0)
    if not isinstance(version, int) or version < 0:
        raise StoreError("meta.json has an invalid schema_version")
    return version


def plan_migrations(
    home: Path | str,
    *,
    target_version: int = SCHEMA_VERSION,
    migrations: Sequence[MigrationStep] = BUILTIN_MIGRATIONS,
) -> MigrationPlan:
    """Compute the ordered chain of migration steps to reach ``target_version``."""
    resolved = Path(home).expanduser().resolve()
    current = _detect_schema_version(resolved)
    if current > target_version:
        raise StoreError(
            f"store schema {current} is newer than target schema {target_version}; "
            "downgrades are not supported"
        )

    steps: list[MigrationStep] = []
    version = current
    by_from = {step.from_version: step for step in migrations}
    while version < target_version:
        step = by_from.get(version)
        if step is None:
            raise StoreError(f"no migration path from schema {version} to {target_version}")
        steps.append(step)
        version = step.to_version

    audit_check = verify_audit_log(resolved / AUDIT_NAME)
    audit_needs_seal = audit_check.status == "legacy"
    return MigrationPlan(
        current_version=current,
        target_version=target_version,
        steps=tuple(steps),
        audit_needs_seal=audit_needs_seal,
    )


def _create_snapshot(home: Path) -> Path:
    stamp = utc_now_iso().replace("-", "").replace(":", "")
    backup_root = home / "backups" / "migrations"
    candidate = backup_root / f"{stamp}-{os.getpid()}"
    counter = 1
    while candidate.exists():
        candidate = backup_root / f"{stamp}-{os.getpid()}-{counter}"
        counter += 1
    snapshot = ensure_private_dir(candidate)

    manifest_files: list[str] = []
    for name in _MANAGED_TOP_FILES:
        src = home / name
        if src.is_file() and not is_link_or_junction(src):
            shutil.copy2(src, snapshot / name)
            manifest_files.append(name)

    projects_src = home / PROJECTS_DIR
    if projects_src.is_dir() and not is_link_or_junction(projects_src):
        projects_dst = ensure_private_dir(snapshot / PROJECTS_DIR)
        for card_file in sorted(projects_src.glob("*.md")):
            if card_file.is_file() and not is_link_or_junction(card_file):
                shutil.copy2(card_file, projects_dst / card_file.name)
                manifest_files.append(f"{PROJECTS_DIR}/{card_file.name}")

    atomic_write_text(
        snapshot / "manifest.json",
        json.dumps(
            {
                "version": 1,
                "created": utc_now_iso(),
                "files": manifest_files,
            },
            indent=2,
        )
        + "\n",
        private_parent=True,
    )
    return snapshot


def _restore_snapshot(home: Path, snapshot: Path) -> list[str]:
    manifest_path = snapshot / "manifest.json"
    if not manifest_path.is_file() or is_link_or_junction(manifest_path):
        raise StoreError(f"invalid migration backup (missing manifest.json): {snapshot}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreError(f"cannot read backup manifest: {exc}") from exc
    files = manifest.get("files")
    if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
        raise StoreError("backup manifest has invalid file list")

    restored: list[str] = []
    for rel in files:
        parts = Path(rel).parts
        src = safe_join(snapshot, *parts)
        dst = safe_join(home, *parts)
        if not src.is_file() or is_link_or_junction(src):
            continue
        atomic_write_text(dst, src.read_text(encoding="utf-8"), private_parent=True)
        restored.append(rel)
    return restored


def _seal_legacy_audit(home: Path) -> bool:
    audit_path = home / AUDIT_NAME
    check = verify_audit_log(audit_path)
    if check.status != "legacy":
        return False
    raw_lines = [
        line.strip() for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    parsed: list[dict[str, object]] = [json.loads(line) for line in raw_lines]
    sealed = seal_audit_sequence(parsed)
    rendered = "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in sealed)
    atomic_write_text(audit_path, rendered + "\n", private_parent=True)
    return True


def migrate_store(
    home: Path | str,
    *,
    apply: bool = False,
    target_version: int = SCHEMA_VERSION,
    migrations: Sequence[MigrationStep] = BUILTIN_MIGRATIONS,
) -> MigrationResult:
    """Plan or apply schema migrations and audit-log sealing with automatic rollback."""
    resolved = Path(home).expanduser().resolve()
    plan = plan_migrations(resolved, target_version=target_version, migrations=migrations)

    if not plan.has_work:
        return MigrationResult(
            mode="up-to-date",
            from_version=plan.current_version,
            to_version=plan.current_version,
        )

    if not apply:
        return MigrationResult(
            mode="dry-run",
            from_version=plan.current_version,
            to_version=plan.target_version,
            steps_applied=[
                f"v{step.from_version}->v{step.to_version}: {step.description}"
                for step in plan.steps
            ],
            audit_sealed=plan.audit_needs_seal,
        )

    with file_lock(resolved / ".engramkeep.lock"):
        snapshot = _create_snapshot(resolved)
        applied_descriptions: list[str] = []
        audit_sealed = False
        try:
            for step in plan.steps:
                step.apply_fn(resolved)
                applied_descriptions.append(
                    f"v{step.from_version}->v{step.to_version}: {step.description}"
                )
                # Ensure meta.json reflects the step's target version.
                meta_path = resolved / META_NAME
                meta: dict[str, object] = {}
                if meta_path.is_file():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["schema_version"] = step.to_version
                meta["migrated_at"] = utc_now_iso()
                atomic_write_text(meta_path, json.dumps(meta, indent=2) + "\n", private_parent=True)

            if plan.audit_needs_seal:
                audit_sealed = _seal_legacy_audit(resolved)
                if audit_sealed:
                    applied_descriptions.append("sealed legacy audit.log with SHA-256 hash chain")
        except Exception as exc:
            _restore_snapshot(resolved, snapshot)
            raise StoreError(
                f"migration failed and was rolled back from {snapshot}: {exc}"
            ) from exc

        return MigrationResult(
            mode="applied",
            from_version=plan.current_version,
            to_version=plan.target_version,
            steps_applied=applied_descriptions,
            audit_sealed=audit_sealed,
            backup_dir=snapshot,
        )


def rollback_migration(home: Path | str, backup_dir: Path | str) -> RollbackResult:
    """Restore a store from a previously created migration backup directory."""
    resolved_home = Path(home).expanduser().resolve()
    resolved_backup = Path(backup_dir).expanduser().resolve()
    if not resolved_backup.is_dir() or is_link_or_junction(resolved_backup):
        raise StoreError(f"backup directory not found: {resolved_backup}")
    with file_lock(resolved_home / ".engramkeep.lock"):
        restored = _restore_snapshot(resolved_home, resolved_backup)
    return RollbackResult(backup_dir=resolved_backup, restored_files=restored)
