"""Base types and candidate extraction for read-only transcript adapters.

All adapters are strictly read-only, never upload data, and redact secrets
before candidates are previewed or persisted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..paths import strip_control_chars
from ..redact import redact_text

MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MiB hard cap

_DECISION_PREFIX_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:decision|karar|chosen|architecture|mimari|remember|note|not)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_DECISION_NATURAL_RE = re.compile(
    r"(?:^|(?<=[.!?]\s))(?:"
    r"(?:we\s+decided\s+to|decided\s+to\s+use|let'?s\s+use|going\s+forward(?:,\s*|\s+)we\s+(?:will|use|keep)|"
    r"switching\s+from\s+.+?\s+to)"
    r"\s+[^.!?\n]{8,220}"
    r"|"
    r"[^.!?\n]{4,180}(?:kullanmaya\s+karar\s+verdik|tercih\s+ettik|seçmeye\s+karar\s+verdik)"
    r"|"
    r"bundan\s+sonra\s+[^.!?\n]{8,200}"
    r")",
    re.IGNORECASE,
)
_INLINE_FIX_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:error|failed|exception|hata|problem)\s*:\s*(.+?)\s*(?:->|\||;)\s*"
    r"(?:fix|solution|resolved|çözüm)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_ERROR_LINE_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:error|failed|exception|traceback|hata|problem)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_FIX_LINE_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:fix|fixed\s+by|solution|resolved(?:\s+by)?|root\s+cause|workaround|çözüm|kök\s+neden)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_NATURAL_FIX_RE = re.compile(
    r"^(?:[-*+]\s*)?(?:fixed\s+by|resolved\s+by|root\s+cause\s+was|çözüm\s+olarak)\s+(.{8,260})$",
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


class TranscriptAdapter:
    """Base interface for read-only transcript parsers."""

    name: str = "text"

    def can_handle(self, path: Path, raw_text: str) -> bool:
        """Return True when this adapter recognizes the transcript."""
        return False

    def extract_lines(self, raw_text: str) -> list[tuple[int, str]]:
        """Extract ``(source_line, text_line)`` tuples from ``raw_text``."""
        return [(idx, line) for idx, line in enumerate(raw_text.splitlines(), start=1)]


def clean_candidate(text: str, *, max_chars: int = 240) -> str:
    """Redact secrets, strip control chars, and normalize whitespace."""
    cleaned = redact_text(strip_control_chars(text))
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip()
    return cleaned


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
            err = clean_candidate(inline_match.group(1), max_chars=240)
            fx = clean_candidate(inline_match.group(2), max_chars=280)
            key = (err.lower(), fx.lower())
            if err and fx and key not in seen_fixes:
                seen_fixes.add(key)
                fixes.append(ImportedFix(error=err, fix=fx, source_line=line_no))
            recent_error = None
            continue

        err_match = _ERROR_LINE_RE.match(line)
        if err_match:
            err_txt = clean_candidate(err_match.group(1), max_chars=240)
            if err_txt:
                recent_error = (line_no, err_txt)
            continue

        fix_match = _FIX_LINE_RE.match(line) or _NATURAL_FIX_RE.match(line)
        if fix_match and recent_error is not None and (line_no - recent_error[0]) <= 8:
            err_txt = recent_error[1]
            fx_txt = clean_candidate(fix_match.group(1), max_chars=280)
            key = (err_txt.lower(), fx_txt.lower())
            if fx_txt and key not in seen_fixes:
                seen_fixes.add(key)
                fixes.append(ImportedFix(error=err_txt, fix=fx_txt, source_line=line_no))
            recent_error = None
            continue

        dec_match = _DECISION_PREFIX_RE.match(line)
        if dec_match:
            dec_txt = clean_candidate(dec_match.group(1), max_chars=240)
            if dec_txt and dec_txt.lower() not in seen_decisions:
                seen_decisions.add(dec_txt.lower())
                decisions.append(ImportedDecision(text=dec_txt, source_line=line_no))
            continue

        natural_match = _DECISION_NATURAL_RE.search(line)
        if natural_match:
            dec_txt = clean_candidate(natural_match.group(0).rstrip(".,;"), max_chars=240)
            if dec_txt and dec_txt.lower() not in seen_decisions:
                seen_decisions.add(dec_txt.lower())
                decisions.append(ImportedDecision(text=dec_txt, source_line=line_no))

    return decisions, fixes
