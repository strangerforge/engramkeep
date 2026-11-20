"""Deterministic bilingual (EN/TR) concept expansion for keyword search.

Engramkeep stores decisions in plain Markdown. People write memory cards in
the language they think in: a card saved as "Capacitor Android keystore
sorunu" must still surface for the query "mobile" or "keystore". This module
maps common engineering concepts to their EN and TR spellings so a search in
one language finds cards written in the other.

The map is deliberately small, generic, and free of project-specific terms.
It is a scoring aid, not an ontology: matched expanded terms carry a lower
weight than the literal query tokens.
"""

from __future__ import annotations

import re
import unicodedata

SEMANTIC_CONCEPTS: dict[str, tuple[str, ...]] = {
    "mobile": (
        "mobil",
        "android",
        "ios",
        "iphone",
        "apk",
        "capacitor",
        "react-native",
        "flutter",
        "keystore",
        "hybrid",
    ),
    "database": (
        "veritabanı",
        "sqlite",
        "postgres",
        "postgresql",
        "mysql",
        "mariadb",
        "mongodb",
        "redis",
        "prisma",
        "sql",
        "db",
        "storage",
    ),
    "frontend": (
        "ön yüz",
        "arayüz",
        "react",
        "next.js",
        "nextjs",
        "vue",
        "svelte",
        "pwa",
        "tailwind",
        "css",
        "component",
        "ui",
        "ux",
    ),
    "backend": (
        "api",
        "rest",
        "graphql",
        "fastapi",
        "flask",
        "django",
        "express",
        "node",
        "microservice",
        "endpoint",
        "arka yüz",
    ),
    "auth": (
        "authentication",
        "authorization",
        "jwt",
        "oauth",
        "session",
        "login",
        "token",
        "kimlik",
        "yetki",
        "şifre",
    ),
    "devops": (
        "docker",
        "kubernetes",
        "k8s",
        "ci/cd",
        "github actions",
        "vercel",
        "aws",
        "cloudflare",
        "nginx",
        "deploy",
        "dağıtım",
    ),
    "automation": (
        "otomasyon",
        "webhook",
        "workflow",
        "cron",
        "schedule",
        "bot",
        "scraper",
        "pipeline",
    ),
    "testing": (
        "test",
        "sınama",
        "pytest",
        "unittest",
        "e2e",
        "integration",
        "mock",
        "fixture",
    ),
    "security": (
        "güvenlik",
        "vulnerability",
        "xss",
        "csrf",
        "injection",
        "redact",
        "secret",
        "encrypt",
        "şifreleme",
    ),
    "search": (
        "arama",
        "query",
        "index",
        "indeks",
        "full-text",
        "fts",
        "rank",
        "snippet",
    ),
    "sync": (
        "senkronizasyon",
        "senkron",
        "backup",
        "yedek",
        "restore",
        "cloud",
        "drive",
        "sync",
    ),
    "performance": (
        "performans",
        "latency",
        "cache",
        "önbellek",
        "profiling",
        "optimizasyon",
        "memory",
        "bellek",
    ),
    "media": (
        "görsel",
        "image",
        "video",
        "audio",
        "ffmpeg",
        "logo",
        "svg",
        "banner",
        "thumbnail",
    ),
}

_TOKEN_SPLIT = re.compile(r"[^\w/.@-]+", re.UNICODE)
_MIN_PREFIX_LEN = 4
_MIN_SUBSTRING_LEN = 3
_SOFTENING_MAP = {
    "k": "kğ",
    "p": "pb",
    "ç": "çc",
    "t": "td",
}


def tr_lower(text: str) -> str:
    """Lowercase text cleanly for English and Turkish without combining dots.

    Python's ``"İstanbul".lower()`` produces ``"i\\u0307stanbul"`` (with a
    combining dot above), which breaks exact matching against ``"istanbul"``.
    Mapping ``İ`` before lowercasing and stripping stray combining dots keeps
    both Turkish and English identifiers consistent.
    """
    if not text:
        return ""
    folded = text.replace("İ", "i").lower().replace("i\u0307", "i")
    return unicodedata.normalize("NFC", folded)


def prefix_pattern(term: str) -> re.Pattern[str] | None:
    """Return a bounded suffix-tolerant regex for Turkish/agglutinative terms.

    Returns ``None`` for short terms (fewer than 4 characters) or multi-word
    phrases so short English tokens such as ``git`` or ``api`` never match
    inside unrelated words.
    """
    if len(term) < _MIN_PREFIX_LEN or not term.isalpha():
        return None
    last = term[-1]
    if last in _SOFTENING_MAP:
        stem = re.escape(term[:-1]) + f"[{_SOFTENING_MAP[last]}]"
    else:
        stem = re.escape(term)
    return re.compile(r"(?<![\w])" + stem + r"[\w]{1,6}(?![\w])")


def _matches_prefix(token: str, term: str) -> bool:
    if len(term) < _MIN_PREFIX_LEN or len(token) <= len(term):
        return False
    if token.startswith(term):
        return True
    last = term[-1]
    if last in _SOFTENING_MAP and token.startswith(term[:-1]):
        return token[len(term) - 1] in _SOFTENING_MAP[last]
    return False


def expand_query_terms(query: str) -> set[str]:
    """Return the normalized query terms plus matching EN/TR concept terms."""
    normalized = " ".join(tr_lower(query).split())
    if not normalized:
        return set()

    tokens = {token for token in _TOKEN_SPLIT.split(normalized) if token}
    expanded = set(tokens)
    if not tokens:
        expanded.add(normalized)

    for primary, related in SEMANTIC_CONCEPTS.items():
        family = (primary, *related)
        if any(_term_matches(term, normalized, tokens) for term in family):
            expanded.update(family)
    return expanded


def _term_matches(term: str, normalized: str, tokens: set[str]) -> bool:
    if term in tokens:
        return True
    # Multi-word concept terms (e.g. "github actions", "ön yüz") match on
    # word boundaries inside the normalized query.
    if " " in term:
        return re.search(r"(?<![\w])" + re.escape(term) + r"(?![\w])", normalized) is not None
    # Agglutinative / inflected queries (e.g. "veritabanında", "önbelleği")
    # match concept stems of length >= 4.
    if any(_matches_prefix(token, term) for token in tokens):
        return True
    # Short queries (e.g. "io", "in", "ar") must not trigger unrelated
    # families via loose substring containment.
    if len(normalized) < _MIN_SUBSTRING_LEN:
        return False
    return any(
        len(token) >= _MIN_PREFIX_LEN and len(term) >= _MIN_PREFIX_LEN and term.startswith(token)
        for token in tokens
    )
