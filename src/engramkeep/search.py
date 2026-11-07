"""Keyword search over project cards."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .models import Card, normalize_tag


@dataclass(frozen=True)
class SearchHit:
    """One ranked search result."""

    id: str
    title: str
    score: int
    snippet: str
    tags: tuple[str, ...]
    updated: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "id": self.id,
            "title": self.title,
            "score": self.score,
            "snippet": self.snippet,
            "tags": list(self.tags),
            "updated": self.updated,
        }


def make_snippet(body: str, tokens: list[str], *, width: int = 160) -> str:
    """Build a single-line snippet around the first matching token."""
    flat = re.sub(r"\s+", " ", body).strip()
    if not flat:
        return ""

    lowered = flat.lower()
    positions = [lowered.find(token) for token in tokens if token and lowered.find(token) >= 0]
    if positions:
        index = min(positions)
        start = max(0, index - 60)
        end = min(len(flat), index + width - 60)
        snippet = flat[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(flat):
            snippet += "..."
        return snippet

    if len(flat) > width:
        return flat[:width].rstrip() + "..."
    return flat


def search_cards(
    cards: Iterable[Card],
    query: str,
    *,
    tag: str | None = None,
    limit: int = 10,
) -> list[SearchHit]:
    """Search titles, ids, tags, and bodies, ranked by field weight."""
    limit = max(0, limit)
    tag_filter = normalize_tag(tag) if tag else None
    tokens = [token for token in re.split(r"\s+", query.lower()) if token]
    hits: list[SearchHit] = []

    for card in cards:
        card_tags = [item.lower() for item in card.tags]
        if tag_filter and tag_filter not in card_tags:
            continue

        title = card.title.lower()
        body = card.body.lower()
        project_id = card.id.lower()
        score = 0
        matched_tokens = 0

        for token in tokens:
            token_score = 0
            if token in title:
                token_score += 10
            if token in project_id:
                token_score += 5
            if any(token in item for item in card_tags):
                token_score += 6
            occurrences = body.count(token)
            if occurrences:
                token_score += min(occurrences, 5)
            if token_score:
                matched_tokens += 1
                score += token_score

        if tokens and matched_tokens == 0:
            continue
        if matched_tokens:
            score += matched_tokens * 2

        hits.append(
            SearchHit(
                id=card.id,
                title=card.title,
                score=score,
                snippet=make_snippet(card.body, tokens),
                tags=tuple(card.tags),
                updated=card.updated,
            )
        )

    hits.sort(key=lambda hit: (hit.updated, hit.title.lower()), reverse=True)
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]
