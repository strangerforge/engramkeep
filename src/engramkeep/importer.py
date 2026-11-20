"""Consent-based, read-only-by-default transcript importer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .adapters import (
    MAX_IMPORT_BYTES,
    ImportedDecision,
    ImportedFix,
    ImportResult,
    detect_adapter,
    extract_candidates,
)
from .errors import PathSafetyError, StoreError
from .paths import is_link_or_junction
from .store import Store

ImportFormat = Literal["auto", "claude-jsonl", "cursor", "opencode", "codex", "gemini", "text"]

_DISCOVERY_SOURCES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("claude-jsonl", ".claude/projects", ("*.jsonl",)),
    ("codex", ".codex/sessions", ("*.jsonl",)),
    ("opencode", ".local/share/opencode/storage/session", ("*.json", "*.jsonl")),
    ("gemini", ".gemini/tmp", ("*.json",)),
    ("cursor", ".cursor", ("*.json",)),
)


@dataclass(frozen=True)
class DiscoveredTranscript:
    """Metadata for a locally discovered agent transcript file (never read automatically)."""

    agent: str
    path: Path
    size_bytes: int
    modified: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "agent": self.agent,
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "modified": self.modified,
        }


def discover_transcripts(
    *,
    user_home: Path | None = None,
    limit: int = 20,
) -> list[DiscoveredTranscript]:
    """List recent transcript files in standard agent directories (read-only metadata only)."""
    limit = max(0, limit)
    if limit == 0:
        return []
    base = (user_home if user_home is not None else Path.home()).expanduser().resolve()
    found: list[tuple[float, DiscoveredTranscript]] = []

    for agent, rel_dir, patterns in _DISCOVERY_SOURCES:
        root = base / rel_dir
        if not root.exists() or is_link_or_junction(root) or not root.is_dir():
            continue
        for pattern in patterns:
            for candidate in root.rglob(pattern):
                if is_link_or_junction(candidate) or not candidate.is_file():
                    continue
                try:
                    st = candidate.stat()
                except OSError:
                    continue
                if st.st_size == 0 or st.st_size > MAX_IMPORT_BYTES:
                    continue
                modified = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                found.append(
                    (
                        st.st_mtime,
                        DiscoveredTranscript(
                            agent=agent,
                            path=candidate,
                            size_bytes=st.st_size,
                            modified=modified,
                        ),
                    )
                )

    found.sort(key=lambda item: (item[0], str(item[1].path)), reverse=True)
    return [entry for _, entry in found[:limit]]


def _prompt_items(
    decisions: list[ImportedDecision],
    fixes: list[ImportedFix],
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> tuple[list[ImportedDecision], list[ImportedFix]]:
    """Interactively ask the user to approve or skip each extracted candidate."""
    selected_decisions: list[ImportedDecision] = []
    selected_fixes: list[ImportedFix] = []
    approve_all = False

    items: list[tuple[str, ImportedDecision | ImportedFix]] = [
        ("decision", dec) for dec in decisions
    ] + [("fix", fx) for fx in fixes]

    for kind, item in items:
        if approve_all:
            if kind == "decision" and isinstance(item, ImportedDecision):
                selected_decisions.append(item)
            elif kind == "fix" and isinstance(item, ImportedFix):
                selected_fixes.append(item)
            continue

        if kind == "decision" and isinstance(item, ImportedDecision):
            output_fn(f"[decision L{item.source_line}] {item.text}")
        elif kind == "fix" and isinstance(item, ImportedFix):
            output_fn(f"[fix L{item.source_line}] {item.error} -> {item.fix}")

        try:
            answer = input_fn("Keep? [y]es / [n]o / [a]ll / [q]uit: ").strip().lower()
        except EOFError:
            break
        if answer in {"q", "quit"}:
            break
        if answer in {"a", "all"}:
            approve_all = True
            if kind == "decision" and isinstance(item, ImportedDecision):
                selected_decisions.append(item)
            elif kind == "fix" and isinstance(item, ImportedFix):
                selected_fixes.append(item)
        elif answer in {"y", "yes"}:
            if kind == "decision" and isinstance(item, ImportedDecision):
                selected_decisions.append(item)
            elif kind == "fix" and isinstance(item, ImportedFix):
                selected_fixes.append(item)

    return selected_decisions, selected_fixes


def import_transcript(
    store: Store,
    source_path: Path,
    *,
    fmt: ImportFormat = "auto",
    project: str = "imported",
    limit: int = 20,
    apply: bool = False,
    interactive: bool = False,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> ImportResult:
    """Inspect a transcript file and optionally persist redacted candidates to the store."""
    if is_link_or_junction(source_path) or source_path.is_symlink():
        raise PathSafetyError(f"refusing symlinked transcript file: {source_path}")
    if not source_path.exists() or not source_path.is_file():
        raise StoreError(f"transcript file not found: {source_path}")
    if source_path.stat().st_size > MAX_IMPORT_BYTES:
        raise StoreError(f"transcript file exceeds {MAX_IMPORT_BYTES // (1024 * 1024)} MiB limit")

    raw_text = source_path.read_text(encoding="utf-8", errors="replace")
    adapter = detect_adapter(source_path, raw_text, fmt)
    lines = adapter.extract_lines(raw_text)
    decisions, fixes = extract_candidates(lines, limit=limit)

    if interactive and (decisions or fixes):
        prompt_in = input_fn if input_fn is not None else input
        prompt_out = output_fn if output_fn is not None else print
        decisions, fixes = _prompt_items(decisions, fixes, input_fn=prompt_in, output_fn=prompt_out)
        apply = True

    written_decisions = 0
    written_fixes = 0
    if apply and (decisions or fixes):
        if not store.is_initialized():
            store.init()
        for dec in decisions:
            res = store.remember(project, dec.text)
            if res.added:
                written_decisions += 1
        for fx in fixes:
            _, added = store.record_fix_result(fx.error, fx.fix, project=project)
            if added:
                written_fixes += 1

    return ImportResult(
        source_path=source_path,
        format=adapter.name,
        project=project,
        applied=apply,
        decisions=tuple(decisions),
        fixes=tuple(fixes),
        written_decisions=written_decisions,
        written_fixes=written_fixes,
    )


__all__ = [
    "MAX_IMPORT_BYTES",
    "DiscoveredTranscript",
    "ImportFormat",
    "ImportResult",
    "ImportedDecision",
    "ImportedFix",
    "discover_transcripts",
    "extract_candidates",
    "import_transcript",
]
