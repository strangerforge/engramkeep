"""Tests for card parsing, rendering, and mutation."""

from __future__ import annotations

import pytest

from engramkeep.errors import CardParseError, ValidationError
from engramkeep.models import (
    add_tags,
    append_decision,
    new_card,
    normalize_tag,
    parse_card,
    render_card,
)


def test_new_card_defaults() -> None:
    card = new_card("example-project", now="2026-01-01T00:00:00Z")
    assert card.id == "example-project"
    assert card.title == "Example Project"
    assert card.created == "2026-01-01T00:00:00Z"
    assert "## Decisions" in card.body


def test_render_parse_roundtrip() -> None:
    card = new_card("example-project", now="2026-01-01T00:00:00Z")
    append_decision(card, "Use SQLite for local storage", now="2026-01-02T00:00:00Z")
    add_tags(card, ["database", "storage"], now="2026-01-02T00:00:00Z")
    rendered = render_card(card)
    parsed = parse_card(rendered, fallback_id="example-project")
    assert parsed.id == card.id
    assert parsed.title == card.title
    assert parsed.tags == ["database", "storage"]
    assert "Use SQLite for local storage" in parsed.body


def test_append_decision_adds_blank_line_and_deduplicates() -> None:
    card = new_card("demo", now="2026-01-01T00:00:00Z")
    assert append_decision(card, "Keep it simple", now="2026-01-02T00:00:00Z") is True
    assert "## Decisions\n\n- Keep it simple" in card.body
    assert append_decision(card, "Keep it simple", now="2026-01-03T00:00:00Z") is False
    assert card.body.count("- Keep it simple") == 1


def test_append_decision_inserts_before_next_section() -> None:
    card = new_card("demo")
    card.body = "# Demo\n\n## Decisions\n\n- One\n\n## Notes\n\nText\n"
    assert append_decision(card, "Two") is True
    assert card.body.index("- One") < card.body.index("- Two") < card.body.index("## Notes")


def test_append_decision_rejects_empty_and_long_values() -> None:
    card = new_card("demo")
    with pytest.raises(ValidationError):
        append_decision(card, "   ")
    with pytest.raises(ValidationError):
        append_decision(card, "x" * 4001)


def test_add_tags_normalizes_and_deduplicates() -> None:
    card = new_card("demo")
    added = add_tags(card, ["Database", "database", "my tag"])
    assert added == ["database", "my-tag"]
    assert card.tags == ["database", "my-tag"]


def test_normalize_tag_rejects_invalid() -> None:
    assert normalize_tag(" My Tag ") == "my-tag"
    with pytest.raises(ValidationError):
        normalize_tag("!!!")


def test_parse_card_without_frontmatter_uses_fallback() -> None:
    card = parse_card("# Notes\n\nSome text\n", fallback_id="notes")
    assert card.id == "notes"
    assert card.title == "Notes"
    assert "Some text" in card.body


def test_parse_card_requires_id() -> None:
    with pytest.raises(CardParseError):
        parse_card("plain text")


def test_parse_card_rejects_unterminated_frontmatter() -> None:
    with pytest.raises(CardParseError):
        parse_card("---\nid: demo\n", fallback_id="demo")


def test_parse_card_uses_filename_identity() -> None:
    card = parse_card("---\nid: other\ntitle: Other\n---\n\nBody\n", fallback_id="demo")
    assert card.id == "demo"


def test_parse_card_skips_invalid_tags() -> None:
    card = parse_card(
        "---\nid: demo\ntags: good, !!!\n---\n\n# Demo\n",
        fallback_id="demo",
    )
    assert card.tags == ["good"]


def test_parse_card_generates_body_when_empty() -> None:
    card = parse_card("---\nid: demo\ntitle: Demo\n---\n", fallback_id="demo")
    assert "## Decisions" in card.body
