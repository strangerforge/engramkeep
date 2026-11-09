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


def expand_query_terms(query: str) -> set[str]:
    """Return the normalized query terms plus matching EN/TR concept terms."""
    normalized = " ".join(query.lower().split())
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
    # Substring match in both directions so "mobil" finds "mobile"-family
    # entries and multi-word terms like "github actions" still match.
    return term in normalized or normalized in term
