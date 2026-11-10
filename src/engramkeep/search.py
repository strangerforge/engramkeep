"""Keyword search over project cards."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .concepts import expand_query_terms
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


def _plain_text(body: str) -> str:
    """Flatten Markdown into one readable line for search snippets."""
    text = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = text.replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def make_snippet(body: str, tokens: list[str], *, width: int = 160) -> str:
    """Build a single-line plain-text snippet around the first matching token."""
    flat = _plain_text(body)
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
    # Bilingual (EN/TR) concept expansion. Expanded terms are worth a small
    # bonus only, never replace literal tokens, and cap their total gain so
    # they can recall cross-language cards without drowning real matches.
    expanded_terms = expand_query_terms(query) - set(tokens)
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
            pattern = re.compile(r"(?<![\w])" + re.escape(token) + r"(?![\w])")
            token_score = 0
            if pattern.search(title):
                token_score += 10
            if pattern.search(project_id):
                token_score += 5
            if any(pattern.search(item) for item in card_tags):
                token_score += 6
            occurrences = len(pattern.findall(body))
            if occurrences:
                token_score += min(occurrences, 5)
            if token_score:
                matched_tokens += 1
                score += token_score

        haystack = f"{title}\n{body}\n{project_id}"
        bonus = _expansion_bonus(expanded_terms, haystack)

        if tokens and matched_tokens == 0:
            if bonus == 0:
                continue
            # Recall cards that match a related EN/TR concept even when no
            # literal query token appears (for example "mobil" -> "capacitor").
            score = bonus
        else:
            score += bonus
        if matched_tokens:
            score += matched_tokens * 2

        snippet_tokens = tokens or sorted(
            (term for term in expanded_terms if term in haystack),
            key=len,
            reverse=True,
        )
        hits.append(
            SearchHit(
                id=card.id,
                title=card.title,
                score=score,
                snippet=make_snippet(card.body, snippet_tokens),
                tags=tuple(card.tags),
                updated=card.updated,
            )
        )

    hits.sort(key=lambda hit: (hit.updated, hit.title.lower()), reverse=True)
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]


def _expansion_bonus(terms: set[str], haystack: str, *, cap: int = 6) -> int:
    """Score expanded EN/TR terms with word-boundary matching."""
    bonus = 0
    for term in terms:
        if not term:
            continue
        pattern = re.compile(r"(?<![\w])" + re.escape(term) + r"(?![\w])")
        occurrences = len(pattern.findall(haystack))
        if occurrences:
            bonus += min(occurrences, 2)
        if bonus >= cap:
            return cap
    return bonus
