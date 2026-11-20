"""BM25, phrase, and bilingual keyword search over project cards."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

from .concepts import expand_query_terms, prefix_pattern, tr_lower
from .models import Card, normalize_tag

_BM25_K1 = 1.5
_BM25_B = 0.75
_TITLE_WEIGHT = 4.0
_TAG_WEIGHT = 2.5
_ID_WEIGHT = 2.0
_BODY_WEIGHT = 1.0
_PREFIX_WEIGHT = 0.55


@dataclass(frozen=True)
class SearchHit:
    """One ranked search result."""

    id: str
    title: str
    score: int
    snippet: str
    tags: tuple[str, ...]
    updated: str
    source: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        payload: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "score": self.score,
            "snippet": self.snippet,
            "tags": list(self.tags),
            "updated": self.updated,
        }
        if self.source is not None:
            payload["source"] = self.source
        return payload


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

    lowered = tr_lower(flat)
    positions: list[int] = []
    for token in tokens:
        if not token:
            continue
        pos = lowered.find(token)
        if pos >= 0:
            positions.append(pos)
            continue
        pref = prefix_pattern(token)
        if pref is not None:
            match = pref.search(lowered)
            if match is not None:
                positions.append(match.start())
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


def _parse_query(query: str) -> tuple[list[str], list[str]]:
    """Split query into exact quoted phrases and deduplicated unquoted tokens."""
    phrases = [
        " ".join(tr_lower(match).split())
        for match in re.findall(r'"([^"]+)"', query)
        if match.strip()
    ]
    phrases = list(dict.fromkeys(phrases))[:16]
    unquoted = re.sub(r'"[^"]*"', " ", query)
    tokens = list(dict.fromkeys(token for token in re.split(r"\s+", tr_lower(unquoted)) if token))[
        :64
    ]
    return phrases, tokens


def _word_pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w])" + re.escape(term) + r"(?![\w])")


def _weighted_doc_length(card: Card) -> float:
    title_len = len(re.findall(r"\w+", card.title))
    id_len = len(re.findall(r"\w+", card.id))
    tag_len = sum(len(re.findall(r"\w+", tag)) for tag in card.tags)
    body_len = len(re.findall(r"\w+", card.body))
    return max(
        1.0,
        _TITLE_WEIGHT * title_len
        + _ID_WEIGHT * id_len
        + _TAG_WEIGHT * tag_len
        + _BODY_WEIGHT * body_len,
    )


def search_cards(
    cards: Iterable[Card],
    query: str,
    *,
    tag: str | None = None,
    limit: int = 10,
) -> list[SearchHit]:
    """Search titles, ids, tags, and bodies using BM25, phrase match, and EN/TR expansion."""
    limit = max(0, limit)
    tag_filter = normalize_tag(tag) if tag else None
    candidates: list[Card] = []
    for card in cards:
        if tag_filter and tag_filter not in [item.lower() for item in card.tags]:
            continue
        candidates.append(card)

    if not candidates or limit == 0:
        return []

    phrases, tokens = _parse_query(query)
    if not phrases and not tokens:
        hits = [
            SearchHit(
                id=card.id,
                title=card.title,
                score=1,
                snippet=make_snippet(card.body, []),
                tags=tuple(card.tags),
                updated=card.updated,
            )
            for card in candidates
        ]
        hits.sort(key=lambda hit: (hit.updated, hit.title.lower()), reverse=True)
        return hits[:limit]

    token_patterns = [_word_pattern(token) for token in tokens]
    token_prefix_patterns = [prefix_pattern(token) for token in tokens]
    phrase_patterns = [_word_pattern(phrase) for phrase in phrases]

    # Bilingual (EN/TR) concept expansion. Expanded terms add a small capped
    # bonus so cross-language cards recall without drowning literal matches.
    literal_terms = set(tokens) | set(phrases)
    expanded_terms = expand_query_terms(query) - literal_terms
    expanded_patterns = [_word_pattern(term) for term in sorted(expanded_terms) if term]

    doc_lengths = [_weighted_doc_length(card) for card in candidates]
    avgdl = sum(doc_lengths) / len(doc_lengths)
    num_docs = len(candidates)

    doc_fields = [
        (
            tr_lower(card.title),
            tr_lower(card.id),
            [tr_lower(item) for item in card.tags],
            tr_lower(card.body),
        )
        for card in candidates
    ]

    # Compute document frequency (df) per literal token across candidate corpus.
    df_counts: list[int] = []
    for pattern, pref in zip(token_patterns, token_prefix_patterns, strict=True):
        df = 0
        for title, project_id, card_tags, body in doc_fields:
            matched = (
                pattern.search(title)
                or pattern.search(project_id)
                or any(pattern.search(t) for t in card_tags)
                or pattern.search(body)
            )
            if not matched and pref is not None:
                matched = (
                    pref.search(title)
                    or pref.search(project_id)
                    or any(pref.search(t) for t in card_tags)
                    or pref.search(body)
                )
            if matched:
                df += 1
        df_counts.append(df)

    idfs = [math.log(1.0 + (num_docs - df + 0.5) / (df + 0.5)) for df in df_counts]

    hits = []
    for idx, card in enumerate(candidates):
        title, project_id, card_tags, body = doc_fields[idx]
        dl = doc_lengths[idx]
        norm = 1.0 - _BM25_B + _BM25_B * (dl / avgdl)

        bm25_score = 0.0
        matched_tokens = 0
        for pattern, pref, idf in zip(token_patterns, token_prefix_patterns, idfs, strict=True):
            tf = (
                _TITLE_WEIGHT * len(pattern.findall(title))
                + _ID_WEIGHT * len(pattern.findall(project_id))
                + _TAG_WEIGHT * sum(len(pattern.findall(t)) for t in card_tags)
                + _BODY_WEIGHT * len(pattern.findall(body))
            )
            if pref is not None:
                tf += _PREFIX_WEIGHT * (
                    _TITLE_WEIGHT * len(pref.findall(title))
                    + _ID_WEIGHT * len(pref.findall(project_id))
                    + _TAG_WEIGHT * sum(len(pref.findall(t)) for t in card_tags)
                    + _BODY_WEIGHT * len(pref.findall(body))
                )
            if tf > 0.0:
                matched_tokens += 1
                bm25_score += idf * (tf * (_BM25_K1 + 1.0)) / (tf + _BM25_K1 * norm)

        phrase_score = 0.0
        matched_phrases = 0
        for p_pat in phrase_patterns:
            p_tf = (
                _TITLE_WEIGHT * len(p_pat.findall(title))
                + _TAG_WEIGHT * sum(len(p_pat.findall(t)) for t in card_tags)
                + _BODY_WEIGHT * len(p_pat.findall(body))
            )
            if p_tf > 0.0:
                matched_phrases += 1
                phrase_score += 4.0 + min(p_tf, 4.0)

        # If the user supplied quoted phrases only, require at least one phrase match.
        if phrase_patterns and not token_patterns and matched_phrases == 0:
            continue

        haystack = f"{title}\n{body}\n{project_id}"
        bonus = _expansion_bonus(expanded_patterns, haystack)

        if matched_tokens == 0 and matched_phrases == 0:
            if bonus == 0:
                continue
            total = float(bonus)
        else:
            # Multi-term coverage reward + expansion bonus on top of BM25 + phrase match.
            total = bm25_score * 10.0 + phrase_score * 10.0 + matched_tokens * 2.0 + bonus

        int_score = max(1, round(total * 10))
        snippet_tokens = phrases + tokens or sorted(
            (term for term in expanded_terms if term in haystack),
            key=len,
            reverse=True,
        )
        hits.append(
            SearchHit(
                id=card.id,
                title=card.title,
                score=int_score,
                snippet=make_snippet(card.body, snippet_tokens),
                tags=tuple(card.tags),
                updated=card.updated,
            )
        )

    hits.sort(key=lambda hit: (hit.updated, hit.title.lower()), reverse=True)
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]


def _expansion_bonus(patterns: list[re.Pattern[str]], haystack: str, *, cap: int = 6) -> int:
    """Score expanded EN/TR terms with word-boundary matching."""
    bonus = 0
    for pattern in patterns:
        occurrences = len(pattern.findall(haystack))
        if occurrences:
            bonus += min(occurrences, 2)
        if bonus >= cap:
            return cap
    return bonus
