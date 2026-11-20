"""Built-in read-only transcript adapters for multiple coding agents."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .base import TranscriptAdapter


def _extract_text_blocks(content: object) -> list[str]:
    if isinstance(content, str):
        return content.splitlines()
    if isinstance(content, list):
        lines: list[str] = []
        for block in content:
            if isinstance(block, str):
                lines.extend(block.splitlines())
            elif isinstance(block, dict):
                block_type = str(block.get("type") or "").lower()
                if block_type in {"", "text", "input_text", "output_text"}:
                    for key in ("text", "content", "value"):
                        val = block.get(key)
                        if isinstance(val, str):
                            lines.extend(val.splitlines())
                            break
        return lines
    return []


def _first_json_object(raw_text: str) -> dict[str, object] | None:
    stripped = raw_text.strip()
    if not stripped:
        return None
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    for line in raw_text.splitlines():
        item = line.strip()
        if not item:
            continue
        try:
            parsed = json.loads(item)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


class CodexAdapter(TranscriptAdapter):
    """Parse OpenAI Codex session JSONL logs (``payload`` / ``item`` records)."""

    name = "codex"

    def can_handle(self, path: Path, raw_text: str) -> bool:
        obj = _first_json_object(raw_text)
        if obj is None:
            return False
        if obj.get("type") in {"session_meta", "response_item", "event_msg"}:
            return True
        payload = obj.get("payload")
        return isinstance(payload, dict) and (
            "content" in payload or "message" in payload or payload.get("type") == "message"
        )

    def extract_lines(self, raw_text: str) -> list[tuple[int, str]]:
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
            payload = record.get("payload")
            source = payload if isinstance(payload, dict) else record
            role = str(source.get("role") or "").lower()
            if role and role not in {"user", "assistant"}:
                continue
            content = source.get("content") or source.get("message")
            for text_line in _extract_text_blocks(content):
                extracted.append((idx, text_line))
        return extracted


class OpenCodeAdapter(TranscriptAdapter):
    """Parse OpenCode session JSON/JSONL exports (``parts`` or ``info``+``parts``)."""

    name = "opencode"

    def can_handle(self, path: Path, raw_text: str) -> bool:
        obj = _first_json_object(raw_text)
        if obj is None:
            return False
        if "sessionID" in obj or "session_id" in obj:
            return "parts" in obj or "messages" in obj
        messages = obj.get("messages")
        if isinstance(messages, list):
            first = messages[0] if messages else None
            if isinstance(first, dict) and ("parts" in first or "info" in first):
                return True
        return isinstance(obj.get("parts"), list) and "info" in obj

    def extract_lines(self, raw_text: str) -> list[tuple[int, str]]:
        extracted: list[tuple[int, str]] = []
        stripped = raw_text.strip()
        records: list[tuple[int, dict[str, object]]] = []
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    if isinstance(parsed.get("messages"), list):
                        for i, msg in enumerate(parsed["messages"], start=1):
                            if isinstance(msg, dict):
                                records.append((i, msg))
                    else:
                        records.append((1, parsed))
            except json.JSONDecodeError:
                pass
        if not records:
            for idx, line in enumerate(raw_text.splitlines(), start=1):
                item = line.strip()
                if not item:
                    continue
                try:
                    parsed = json.loads(item)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    records.append((idx, parsed))

        for idx, rec in records:
            info = rec.get("info")
            role = ""
            if isinstance(info, dict):
                role = str(info.get("role") or "").lower()
            else:
                role = str(rec.get("role") or "").lower()
            if role and role not in {"user", "assistant"}:
                continue
            parts = rec.get("parts")
            content = parts if parts is not None else rec.get("content")
            for text_line in _extract_text_blocks(content):
                extracted.append((idx, text_line))
        return extracted


class CursorAdapter(TranscriptAdapter):
    """Parse Cursor chat exports (JSON ``bubbles``/``conversation`` or Markdown)."""

    name = "cursor"
    _MD_ROLE_RE = re.compile(r"^(?:##+\s*)?\*\*(?:User|Cursor|Assistant)\*\*\s*$", re.IGNORECASE)

    def can_handle(self, path: Path, raw_text: str) -> bool:
        obj = _first_json_object(raw_text)
        if obj is not None:
            if any(key in obj for key in ("bubbles", "conversation", "tabs")):
                return True
        return any(self._MD_ROLE_RE.match(line.strip()) for line in raw_text.splitlines()[:40])

    def extract_lines(self, raw_text: str) -> list[tuple[int, str]]:
        stripped = raw_text.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                items = (
                    parsed.get("bubbles")
                    or parsed.get("conversation")
                    or parsed.get("messages")
                    or []
                )
                if isinstance(items, list):
                    extracted: list[tuple[int, str]] = []
                    for idx, item in enumerate(items, start=1):
                        if not isinstance(item, dict):
                            continue
                        text = item.get("text") or item.get("rawText") or item.get("content")
                        for text_line in _extract_text_blocks(text):
                            extracted.append((idx, text_line))
                    return extracted
        return [
            (idx, line)
            for idx, line in enumerate(raw_text.splitlines(), start=1)
            if not self._MD_ROLE_RE.match(line.strip())
        ]


class GeminiAdapter(TranscriptAdapter):
    """Parse Gemini CLI session JSON exports (``contents`` / ``history``)."""

    name = "gemini"

    def can_handle(self, path: Path, raw_text: str) -> bool:
        obj = _first_json_object(raw_text)
        if obj is None:
            return False
        if isinstance(obj.get("contents"), list):
            return True
        history = obj.get("history")
        if isinstance(history, list):
            first = history[0] if history else None
            return isinstance(first, dict) and "parts" in first
        return False

    def extract_lines(self, raw_text: str) -> list[tuple[int, str]]:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, dict):
            return []
        items = parsed.get("contents") or parsed.get("history") or []
        if not isinstance(items, list):
            return []
        extracted: list[tuple[int, str]] = []
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").lower()
            if role and role not in {"user", "model", "assistant"}:
                continue
            parts = item.get("parts") or item.get("content")
            for text_line in _extract_text_blocks(parts):
                extracted.append((idx, text_line))
        return extracted


class ClaudeJsonlAdapter(TranscriptAdapter):
    """Parse Claude Code ``.jsonl`` session transcripts."""

    name = "claude-jsonl"

    def can_handle(self, path: Path, raw_text: str) -> bool:
        if path.suffix.lower() == ".jsonl":
            return True
        obj = _first_json_object(raw_text)
        if obj is None:
            return False
        if isinstance(obj.get("message"), dict):
            return True
        rec_type = str(obj.get("type") or "").lower()
        if rec_type in {"user", "assistant", "system", "summary"}:
            return True
        return "role" in obj and "content" in obj

    def extract_lines(self, raw_text: str) -> list[tuple[int, str]]:
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
            for text_line in _extract_text_blocks(content):
                extracted.append((idx, text_line))
        return extracted


class PlainTextAdapter(TranscriptAdapter):
    """Parse plain-text or Markdown notes."""

    name = "text"

    def can_handle(self, path: Path, raw_text: str) -> bool:
        return True
