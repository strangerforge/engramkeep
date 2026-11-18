"""Consent-based, read-only-by-default transcript importer."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import PathSafetyError, StoreError
from .paths import is_link_or_junction, strip_control_chars
from .redact import redact_text
from .store import Store

ImportFormat = Literal["auto", "claude-jsonl", "text"]

MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MiB hard cap

_DECISION_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:decision|karar|chosen|architecture|mimari|remember|note|not)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_INLINE_FIX_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:error|failed|exception|hata|problem)\s*:\s*(.+?)\s*(?:->|\||;)\s*"
    r"(?:fix|solution|resolved|çözüm)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_ERROR_LINE_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:error|failed|exception|hata|problem)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_FIX_LINE_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:fix|fixed by|solution|resolved|root cause|çözüm)\s*:\s*(.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ImportedDecision:
    """A candidate decision extracted from an untrusted transcript."""

    text: str
    source_line: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {"text": self.text, "source_line": self.source_line}


@dataclass(frozen=True)
class ImportedFix:
    """A candidate problem/fix pair extracted from an untrusted transcript."""

    error: str
    fix: str
    source_line: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {"error": self.error, "fix": self.fix, "source_line": self.source_line}


@dataclass(frozen=True)
class ImportResult:
    """Outcome of a transcript dry-run preview or applied import."""

    source_path: Path
    format: str
    project: str
    applied: bool
    decisions: tuple[ImportedDecision, ...]
    fixes: tuple[ImportedFix, ...]
    written_decisions: int = 0
    written_fixes: int = 0

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "source_path": str(self.source_path),
            "format": self.format,
            "project": self.project,
            "applied": self.applied,
            "decisions": [item.to_dict() for item in self.decisions],
            "fixes": [item.to_dict() for item in self.fixes],
            "written_decisions": self.written_decisions,
            "written_fixes": self.written_fixes,
        }


def _clean_candidate(text: str, *, max_chars: int = 240) -> str:
    cleaned = redact_text(strip_control_chars(text))
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip()
    return cleaned


def _extract_claude_text(content: object) -> list[str]:
    if isinstance(content, str):
        return content.splitlines()
    if isinstance(content, list):
        lines: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                txt = block.get("text")
                if isinstance(txt, str):
                    lines.extend(txt.splitlines())
        return lines
    return []


def _detect_format(path: Path, raw_text: str, fmt: ImportFormat) -> Literal["claude-jsonl", "text"]:
    if fmt == "claude-jsonl":
        return "claude-jsonl"
    if fmt == "text":
        return "text"
    if path.suffix.lower() == ".jsonl":
        return "claude-jsonl"
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return "text"
        return "claude-jsonl" if isinstance(parsed, dict) else "text"
    return "text"


def _iter_transcript_lines(
    raw_text: str,
    resolved_fmt: Literal["claude-jsonl", "text"],
) -> list[tuple[int, str]]:
    if resolved_fmt == "text":
        return [(idx, line) for idx, line in enumerate(raw_text.splitlines(), start=1)]

    extracted: list[tuple[int, str]] = []
    for idx, raw_line in enumerate(raw_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        rec_type = str(record.get("type") or "").lower()
        msg = record.get("message")
        if isinstance(msg, dict):
            role = str(msg.get("role") or rec_type).lower()
            content = msg.get("content")
        else:
            role = str(record.get("role") or rec_type).lower()
            content = record.get("content")
        if role not in {"user", "assistant"}:
            continue
        for text_line in _extract_claude_text(content):
            extracted.append((idx, text_line))
    return extracted


def extract_candidates(
    lines: list[tuple[int, str]],
    *,
    limit: int = 20,
) -> tuple[list[ImportedDecision], list[ImportedFix]]:
    """Extract redacted decision and fix candidates from transcript lines."""
    limit = max(0, limit)
    decisions: list[ImportedDecision] = []
    fixes: list[ImportedFix] = []
    seen_decisions: set[str] = set()
    seen_fixes: set[tuple[str, str]] = set()
    recent_error: tuple[int, str] | None = None

    for line_no, raw_line in lines:
        if len(decisions) + len(fixes) >= limit:
            break
        line = strip_control_chars(raw_line).strip()
        if not line:
            continue

        inline_match = _INLINE_FIX_RE.match(line)
        if inline_match:
            err = _clean_candidate(inline_match.group(1), max_chars=240)
            fx = _clean_candidate(inline_match.group(2), max_chars=280)
            key = (err.lower(), fx.lower())
            if err and fx and key not in seen_fixes:
                seen_fixes.add(key)
                fixes.append(ImportedFix(error=err, fix=fx, source_line=line_no))
            recent_error = None
            continue

        err_match = _ERROR_LINE_RE.match(line)
        if err_match:
            err_txt = _clean_candidate(err_match.group(1), max_chars=240)
            if err_txt:
                recent_error = (line_no, err_txt)
            continue

        fix_match = _FIX_LINE_RE.match(line)
        if fix_match and recent_error is not None and (line_no - recent_error[0]) <= 5:
            err_txt = recent_error[1]
            fx_txt = _clean_candidate(fix_match.group(1), max_chars=280)
            key = (err_txt.lower(), fx_txt.lower())
            if fx_txt and key not in seen_fixes:
                seen_fixes.add(key)
                fixes.append(ImportedFix(error=err_txt, fix=fx_txt, source_line=line_no))
            recent_error = None
            continue

        dec_match = _DECISION_RE.match(line)
        if dec_match:
            dec_txt = _clean_candidate(dec_match.group(1), max_chars=240)
            if dec_txt and dec_txt.lower() not in seen_decisions:
                seen_decisions.add(dec_txt.lower())
                decisions.append(ImportedDecision(text=dec_txt, source_line=line_no))

    return decisions, fixes


def import_transcript(
    store: Store,
    source_path: Path,
    *,
    fmt: ImportFormat = "auto",
    project: str = "imported",
    limit: int = 20,
    apply: bool = False,
) -> ImportResult:
    """Inspect a transcript file and optionally persist redacted candidates to the store."""
    if is_link_or_junction(source_path) or source_path.is_symlink():
        raise PathSafetyError(f"refusing symlinked transcript file: {source_path}")
    if not source_path.exists() or not source_path.is_file():
        raise StoreError(f"transcript file not found: {source_path}")
    if source_path.stat().st_size > MAX_IMPORT_BYTES:
        raise StoreError(f"transcript file exceeds {MAX_IMPORT_BYTES // (1024 * 1024)} MiB limit")

    raw_text = source_path.read_text(encoding="utf-8", errors="replace")
    resolved_fmt = _detect_format(source_path, raw_text, fmt)
    lines = _iter_transcript_lines(raw_text, resolved_fmt)
    decisions, fixes = extract_candidates(lines, limit=limit)

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
            store.record_fix(fx.error, fx.fix, project=project)
            written_fixes += 1

    return ImportResult(
        source_path=source_path,
        format=resolved_fmt,
        project=project,
        applied=apply,
        decisions=tuple(decisions),
        fixes=tuple(fixes),
        written_decisions=written_decisions,
        written_fixes=written_fixes,
    )
