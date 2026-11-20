"""Read-only, consent-based transcript adapters for AI coding agents."""

from __future__ import annotations

from pathlib import Path

from .base import (
    MAX_IMPORT_BYTES,
    ImportedDecision,
    ImportedFix,
    ImportResult,
    TranscriptAdapter,
    clean_candidate,
    extract_candidates,
)
from .formats import (
    ClaudeJsonlAdapter,
    CodexAdapter,
    CursorAdapter,
    GeminiAdapter,
    OpenCodeAdapter,
    PlainTextAdapter,
)

# Detection order matters: more specific JSON schemas are checked before
# the generic Claude JSONL / plain-text fallbacks.
_ORDERED_ADAPTERS: tuple[TranscriptAdapter, ...] = (
    CodexAdapter(),
    OpenCodeAdapter(),
    GeminiAdapter(),
    CursorAdapter(),
    ClaudeJsonlAdapter(),
    PlainTextAdapter(),
)

ADAPTERS: dict[str, TranscriptAdapter] = {adapter.name: adapter for adapter in _ORDERED_ADAPTERS}


def available_formats() -> list[str]:
    """Return supported transcript adapter format names."""
    return list(ADAPTERS)


def get_adapter(name: str) -> TranscriptAdapter:
    """Return the adapter registered under ``name``."""
    key = name.strip().lower()
    if key not in ADAPTERS:
        choices = ", ".join(available_formats())
        raise KeyError(f"unknown transcript format {name!r}; choose one of: {choices}")
    return ADAPTERS[key]


def detect_adapter(path: Path, raw_text: str, fmt: str = "auto") -> TranscriptAdapter:
    """Resolve an explicit format or auto-detect the matching adapter."""
    if fmt != "auto":
        return get_adapter(fmt)
    for adapter in _ORDERED_ADAPTERS:
        if adapter.can_handle(path, raw_text):
            return adapter
    return ADAPTERS["text"]


__all__ = [
    "ADAPTERS",
    "MAX_IMPORT_BYTES",
    "ImportedDecision",
    "ImportedFix",
    "ImportResult",
    "TranscriptAdapter",
    "available_formats",
    "clean_candidate",
    "detect_adapter",
    "extract_candidates",
    "get_adapter",
]
