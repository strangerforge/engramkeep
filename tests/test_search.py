"""Tests for keyword search."""

from __future__ import annotations

from engramkeep.models import Card, new_card
from engramkeep.search import make_snippet, search_cards


def _card(
    project_id: str,
    decision: str,
    *,
    tags: list[str] | None = None,
    updated: str = "",
) -> Card:
    card = new_card(project_id, now=updated or "2026-01-01T00:00:00Z")
    card.body += f"\n- {decision}\n"
    card.tags = tags or []
    card.updated = updated or card.updated
    return card


def test_search_ranks_title_above_body() -> None:
    title_match = _card("sqlite-project", "Unrelated body", updated="2026-01-01T00:00:00Z")
    body_match = _card("other-project", "We use SQLite", updated="2026-01-02T00:00:00Z")
    hits = search_cards([title_match, body_match], "sqlite")
    assert [hit.id for hit in hits] == ["sqlite-project", "other-project"]
    assert hits[0].score > hits[1].score


def test_search_filters_by_tag() -> None:
    first = _card("one", "Use SQLite", tags=["database"])
    second = _card("two", "Use SQLite", tags=["frontend"])
    hits = search_cards([first, second], "sqlite", tag="database")
    assert [hit.id for hit in hits] == ["one"]


def test_search_empty_query_returns_all() -> None:
    first = _card("one", "A")
    second = _card("two", "B")
    hits = search_cards([first, second], "")
    assert {hit.id for hit in hits} == {"one", "two"}


def test_search_limit() -> None:
    cards = [_card(f"project-{index}", "shared") for index in range(5)]
    hits = search_cards(cards, "shared", limit=2)
    assert len(hits) == 2


def test_make_snippet_marks_truncation() -> None:
    body = "x" * 200 + " needle " + "y" * 200
    snippet = make_snippet(body, ["needle"])
    assert "needle" in snippet
    assert snippet.startswith("...")
    assert snippet.endswith("...")


def test_make_snippet_short_body() -> None:
    assert make_snippet("short body", ["short"]) == "short body"


def test_make_snippet_strips_markdown() -> None:
    body = "# Title\n\n## Decisions\n\n- Use `SQLite` for storage.\n- Keep it local."
    snippet = make_snippet(body, ["sqlite"])
    assert "#" not in snippet
    assert "`" not in snippet
    assert "SQLite" in snippet
