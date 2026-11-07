"""Project card model and Markdown frontmatter helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .errors import CardParseError, ValidationError
from .paths import display_title, normalize_project_id

_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
_DECISION_LIMIT = 4000
_TITLE_LIMIT = 120


def utc_now_iso() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_title(title: str) -> str:
    """Collapse whitespace and bound a title to one safe line."""
    cleaned = " ".join(str(title).split())
    if not cleaned:
        raise ValidationError("title must not be empty")
    if len(cleaned) > _TITLE_LIMIT:
        cleaned = cleaned[:_TITLE_LIMIT].rstrip()
    return cleaned


def normalize_tag(tag: str) -> str:
    """Normalize one tag to lowercase ASCII slug form."""
    value = str(tag).strip().lower()
    if not value:
        raise ValidationError("tag must not be empty")
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^a-z0-9._-]", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-._")
    if not value or not _TAG_RE.match(value):
        raise ValidationError(f"invalid tag: {tag!r}")
    return value


def normalize_tags(tags: Iterable[str]) -> list[str]:
    """Normalize tags, preserving order and removing duplicates."""
    result: list[str] = []
    for tag in tags:
        normalized = normalize_tag(tag)
        if normalized not in result:
            result.append(normalized)
    return result


@dataclass
class Card:
    """A single project memory card."""

    id: str
    title: str
    created: str
    updated: str
    tags: list[str] = field(default_factory=list)
    body: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "id": self.id,
            "title": self.title,
            "created": self.created,
            "updated": self.updated,
            "tags": list(self.tags),
            "body": self.body,
        }


def new_card(project_id: str, *, title: str | None = None, now: str | None = None) -> Card:
    """Create a blank card for ``project_id``."""
    project_id = normalize_project_id(project_id)
    resolved_title = sanitize_title(title or display_title(project_id))
    timestamp = now or utc_now_iso()
    body = f"# {resolved_title}\n\n## Decisions\n"
    return Card(
        id=project_id,
        title=resolved_title,
        created=timestamp,
        updated=timestamp,
        tags=[],
        body=body,
    )


def _parse_frontmatter(lines: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            raise CardParseError(f"invalid frontmatter line: {line!r}")
        key, value = line.split(":", 1)
        data[key.strip().lower()] = value.strip()
    return data


def parse_card(
    text: str,
    *,
    fallback_id: str | None = None,
    now: str | None = None,
) -> Card:
    """Parse a card from Markdown.

    ``fallback_id`` is authoritative when supplied, because the filename is the
    identity used by the store. A mismatch in frontmatter is ignored rather
    than trusted.
    """
    text = text.lstrip("\ufeff")
    lines = text.splitlines()
    frontmatter: list[str] = []
    body = text

    if lines and lines[0].strip() == "---":
        closing = next(
            (index for index in range(1, len(lines)) if lines[index].strip() == "---"),
            None,
        )
        if closing is None:
            raise CardParseError("unterminated frontmatter")
        frontmatter = lines[1:closing]
        body = "\n".join(lines[closing + 1 :]).lstrip("\n")

    data = _parse_frontmatter(frontmatter)
    raw_id = fallback_id or data.get("id")
    if not raw_id:
        raise CardParseError("card has no id")
    try:
        project_id = normalize_project_id(raw_id)
    except ValidationError as exc:
        raise CardParseError(f"invalid card id: {raw_id!r}") from exc

    raw_title = data.get("title") or display_title(project_id)
    try:
        title = sanitize_title(raw_title)
    except ValidationError as exc:
        raise CardParseError("card title is empty") from exc

    tags: list[str] = []
    for raw_tag in data.get("tags", "").split(","):
        if not raw_tag.strip():
            continue
        try:
            normalized = normalize_tag(raw_tag)
        except ValidationError:
            continue
        if normalized not in tags:
            tags.append(normalized)

    if not body.strip():
        body = f"# {title}\n\n## Decisions\n"

    return Card(
        id=project_id,
        title=title,
        created=data.get("created", ""),
        updated=data.get("updated", ""),
        tags=tags,
        body=body.rstrip() + "\n",
    )


def render_card(card: Card) -> str:
    """Render a card as Markdown with frontmatter."""
    title = sanitize_title(card.title)
    tags = normalize_tags(card.tags)
    body = card.body.strip("\n")
    if not body:
        body = f"# {title}\n\n## Decisions"

    lines = [
        "---",
        f"id: {card.id}",
        f"title: {title}",
        f"created: {card.created}",
        f"updated: {card.updated}",
        f"tags: {', '.join(tags)}",
        "---",
        "",
        body,
        "",
    ]
    return "\n".join(lines)


def _find_heading(lines: list[str], name: str) -> int | None:
    target = f"## {name}".lower()
    return next((index for index, line in enumerate(lines) if line.strip().lower() == target), None)


def append_decision(card: Card, decision: str, *, now: str | None = None) -> bool:
    """Append a decision bullet to ``card``.

    Returns True when a new bullet was added and False when the exact decision
    already exists. The card is modified in place.
    """
    cleaned = " ".join(str(decision).split())
    if not cleaned:
        raise ValidationError("decision must not be empty")
    if len(cleaned) > _DECISION_LIMIT:
        raise ValidationError(f"decision is longer than {_DECISION_LIMIT} characters")

    bullet = f"- {cleaned}"
    lines = card.body.splitlines()
    if bullet in lines:
        return False

    heading_index = _find_heading(lines, "Decisions")
    if heading_index is None:
        base = card.body.rstrip()
        card.body = (base + "\n\n" if base else "") + f"## Decisions\n\n{bullet}\n"
    else:
        next_heading = next(
            (
                index
                for index in range(heading_index + 1, len(lines))
                if lines[index].startswith("## ")
            ),
            len(lines),
        )
        insert_at = next_heading
        while insert_at > heading_index + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, bullet)
        if insert_at > 0 and lines[insert_at - 1].strip().lower() == "## decisions":
            lines.insert(insert_at, "")
            insert_at += 1
        if (
            next_heading < len(lines)
            and insert_at + 1 < len(lines)
            and lines[insert_at + 1].strip()
        ):
            lines.insert(insert_at + 1, "")
        card.body = "\n".join(lines).rstrip() + "\n"

    card.updated = now or utc_now_iso()
    return True


def add_tags(card: Card, tags: Iterable[str], *, now: str | None = None) -> list[str]:
    """Add normalized tags to ``card`` and return the newly added ones."""
    added: list[str] = []
    for tag in normalize_tags(tags):
        if tag not in card.tags:
            card.tags.append(tag)
            added.append(tag)
    if added:
        card.updated = now or utc_now_iso()
    return added
