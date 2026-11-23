"""Safe, allowlist-based local Git synchronization for Engramkeep stores.

Security invariants:
- Never runs ``git push`` automatically.
- Never runs ``git add -A`` or ``git add .``.
- Stages only allowlisted regular files (``meta.json``, ``INDEX.md``,
  ``TROUBLESHOOTING.md``, ``projects/*.md``).
- Refuses to commit unless ``store.doctor()`` passes with zero unredacted
  secrets, zero malformed cards, and a valid audit chain.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .errors import StoreError
from .paths import atomic_write_text, is_link_or_junction, safe_join
from .store import INDEX_NAME, META_NAME, PROJECTS_DIR, Store
from .troubleshoot import TROUBLESHOOTING_NAME

SYNC_ALLOWLIST_FILES = (
    META_NAME,
    INDEX_NAME,
    TROUBLESHOOTING_NAME,
)

SYNC_GITIGNORE = """\
# Engramkeep sync allowlist policy: keep private/transient files untracked.
trash/
backups/
.engramkeep.lock
*.tmp
audit.log
RECENT_ACTIVITY.md
"""


@dataclass
class SyncStatus:
    """Summary of the store's Git sync state."""

    home: str
    is_git_repo: bool
    doctor_ok: bool
    allowlisted_files: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    excluded_files: list[str] = field(default_factory=list)
    doctor_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "home": self.home,
            "is_git_repo": self.is_git_repo,
            "doctor_ok": self.doctor_ok,
            "allowlisted_files": list(self.allowlisted_files),
            "changed_files": list(self.changed_files),
            "excluded_files": list(self.excluded_files),
            "doctor_errors": list(self.doctor_errors),
        }


@dataclass
class SyncCommitResult:
    """Outcome of a dry-run or applied allowlist commit."""

    mode: str
    committed: bool
    commit_hash: str | None = None
    staged_files: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "mode": self.mode,
            "committed": self.committed,
            "commit_hash": self.commit_hash,
            "staged_files": list(self.staged_files),
            "message": self.message,
        }


def _git_executable() -> str:
    git = shutil.which("git")
    if not git:
        raise StoreError("git executable not found on PATH")
    return git


def _run_git(home: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    git = _git_executable()
    safe_prefix = [
        "-c",
        "core.hooksPath=",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.quotepath=false",
    ]
    try:
        return subprocess.run(  # noqa: S603 - explicit git binary and static arg list, shell=False
            [git, *safe_prefix, *args],
            cwd=str(home),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise StoreError(f"git command failed: {exc}") from exc


def is_allowlisted_path(rel: str) -> bool:
    """Return True when ``rel`` matches the strict sync allowlist (even if deleted)."""
    normalized = rel.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in SYNC_ALLOWLIST_FILES or normalized == ".gitignore":
        return True
    prefix = f"{PROJECTS_DIR}/"
    if normalized.startswith(prefix) and normalized.endswith(".md"):
        rest = normalized[len(prefix) :]
        return bool(rest) and "/" not in rest and ".." not in rest
    return False


def collect_allowlist(store: Store) -> list[str]:
    """Return relative POSIX paths of regular allowlisted files inside ``store``."""
    allowed: list[str] = []
    for name in SYNC_ALLOWLIST_FILES:
        path = safe_join(store.home, name)
        if path.is_file() and not is_link_or_junction(path):
            allowed.append(name)

    if store.projects_dir.is_dir() and not is_link_or_junction(store.projects_dir):
        for card_path in sorted(store.projects_dir.glob("*.md")):
            if card_path.is_file() and not is_link_or_junction(card_path):
                safe_card = safe_join(store.projects_dir, card_path.name)
                allowed.append(f"{PROJECTS_DIR}/{safe_card.name}")

    gitignore = store.home / ".gitignore"
    if gitignore.is_file() and not is_link_or_junction(gitignore):
        allowed.append(".gitignore")
    return allowed


def _is_git_repo(home: Path) -> bool:
    git_dir = home / ".git"
    return git_dir.exists() and not is_link_or_junction(git_dir)


def _git_porcelain_paths(home: Path) -> list[str]:
    proc = _run_git(home, ["status", "--porcelain", "-uall"])
    if proc.returncode != 0:
        raise StoreError(f"git status failed: {proc.stderr.strip()}")
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1].strip()
        raw = raw.strip('"')
        if raw:
            paths.append(raw.replace("\\", "/"))
    return paths


def sync_init(store: Store) -> SyncStatus:
    """Initialize a local Git repository in the store with a strict allowlist ``.gitignore``."""
    store.require_initialized()
    if is_link_or_junction(store.home):
        raise StoreError("refusing to initialize git inside a symlinked store")
    gitignore = store.home / ".gitignore"
    if not gitignore.exists():
        atomic_write_text(gitignore, SYNC_GITIGNORE, private_parent=True)
    if not _is_git_repo(store.home):
        proc = _run_git(store.home, ["init"])
        if proc.returncode != 0:
            raise StoreError(f"git init failed: {proc.stderr.strip()}")
    return sync_status(store)


def sync_status(store: Store) -> SyncStatus:
    """Inspect allowlisted files, Git dirty status, and pre-commit doctor health."""
    store.require_initialized()
    report = store.doctor()
    allowlisted = collect_allowlist(store)
    is_repo = _is_git_repo(store.home)

    changed: list[str] = []
    excluded: list[str] = []
    if is_repo:
        for rel in _git_porcelain_paths(store.home):
            if is_allowlisted_path(rel):
                target = store.home / Path(rel)
                if not target.exists() or (target.is_file() and not is_link_or_junction(target)):
                    changed.append(rel)
                else:
                    excluded.append(rel)
            else:
                excluded.append(rel)
    return SyncStatus(
        home=str(store.home),
        is_git_repo=is_repo,
        doctor_ok=report.ok,
        allowlisted_files=allowlisted,
        changed_files=changed,
        excluded_files=excluded,
        doctor_errors=list(report.errors),
    )


def sync_commit(
    store: Store,
    *,
    message: str = "chore(engramkeep): sync allowlisted memory",
    apply: bool = False,
) -> SyncCommitResult:
    """Stage allowlisted files (including deletions) and create a local Git commit.

    Always runs ``store.doctor()`` first and refuses to commit if secrets,
    malformed cards, or audit-log tampering are detected. Dry-run by default.
    Never runs ``git add -A`` or ``git push``.
    """
    with store._write_lock():
        status = sync_status(store)
        if not status.is_git_repo:
            raise StoreError(
                f"store is not a Git repository: {store.home}; run 'engramkeep sync --init' first"
            )
        if not status.doctor_ok:
            details = "; ".join(status.doctor_errors)
            raise StoreError(f"refusing to sync unhealthy store (doctor failed): {details}")

        staged_before = _run_git(store.home, ["diff", "--cached", "--name-only"])
        if staged_before.returncode == 0:
            non_allowlisted = [
                line.strip().replace("\\", "/")
                for line in staged_before.stdout.splitlines()
                if line.strip() and not is_allowlisted_path(line.strip())
            ]
            if non_allowlisted:
                raise StoreError(
                    "refusing to commit while non-allowlisted file(s) are staged in the Git "
                    f"index: {', '.join(non_allowlisted)}"
                )

        candidates = list(status.changed_files)
        if not candidates:
            return SyncCommitResult(
                mode="clean",
                committed=False,
                staged_files=[],
                message="no allowlisted changes to commit",
            )

        if not apply:
            return SyncCommitResult(
                mode="dry-run",
                committed=False,
                staged_files=candidates,
                message="dry run: pass --commit to stage allowlisted files and commit locally",
            )

        existing = [rel for rel in candidates if (store.home / Path(rel)).exists()]
        deleted = [rel for rel in candidates if not (store.home / Path(rel)).exists()]

        # Explicitly stage only allowlisted paths; never run git add -A.
        if existing:
            add_proc = _run_git(store.home, ["add", "--", *existing])
            if add_proc.returncode != 0:
                raise StoreError(f"git add failed: {add_proc.stderr.strip()}")
        if deleted:
            rm_proc = _run_git(store.home, ["rm", "--cached", "--ignore-unmatch", "--", *deleted])
            if rm_proc.returncode != 0:
                raise StoreError(f"git rm failed: {rm_proc.stderr.strip()}")

        diff_check = _run_git(store.home, ["diff", "--cached", "--quiet"])
        if diff_check.returncode == 0:
            return SyncCommitResult(
                mode="clean",
                committed=False,
                staged_files=[],
                message="nothing staged to commit",
            )

        commit_proc = _run_git(
            store.home,
            ["commit", "--no-verify", "--only", "-m", message, "--", *candidates],
        )
        if commit_proc.returncode != 0:
            detail = commit_proc.stderr.strip() or commit_proc.stdout.strip()
            raise StoreError(f"git commit failed: {detail}")

        rev = _run_git(store.home, ["rev-parse", "--short", "HEAD"])
        commit_hash = rev.stdout.strip() if rev.returncode == 0 else None
        store._audit(
            "sync_commit",
            None,
            {"files": len(candidates), "commit": commit_hash or ""},
        )
        return SyncCommitResult(
            mode="committed",
            committed=True,
            commit_hash=commit_hash,
            staged_files=candidates,
            message="committed locally; run 'git push' manually when ready",
        )
