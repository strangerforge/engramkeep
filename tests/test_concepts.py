"""Tests for bilingual EN/TR concept expansion."""

from __future__ import annotations

from engramkeep.concepts import SEMANTIC_CONCEPTS, expand_query_terms


def test_expands_mobile_family_from_english() -> None:
    expanded = expand_query_terms("mobile")
    assert "mobil" in expanded
    assert "capacitor" in expanded
    assert "apk" in expanded


def test_expands_mobile_family_from_turkish() -> None:
    expanded = expand_query_terms("mobil")
    assert "mobile" in expanded
    assert "flutter" in expanded


def test_expands_database_family_across_languages() -> None:
    assert "veritabanı" in expand_query_terms("database")
    assert "postgresql" in expand_query_terms("veritabanı")
    assert "sqlite" in expand_query_terms("SQL")


def test_multi_word_term_matches_normalized_query() -> None:
    expanded = expand_query_terms("github actions deploy")
    assert "devops" in expanded or "docker" in expanded


def test_unknown_query_returns_normalized_tokens() -> None:
    assert expand_query_terms("zz-notathing") == {"zz-notathing"}


def test_empty_query_returns_empty_set() -> None:
    assert expand_query_terms("   ") == set()


def test_concept_map_has_no_project_specific_terms() -> None:
    flattened = " ".join(
        term for primary, related in SEMANTIC_CONCEPTS.items() for term in (primary, *related)
    )
    for personal in ("uçak", "bilet", "n8n", "sahibinden", "dizifilmbul", "niyaz"):
        assert personal not in flattened


def test_expansion_is_deterministic() -> None:
    assert expand_query_terms("auth") == expand_query_terms("auth")
