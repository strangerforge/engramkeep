"""Checks for the synthetic example data and the benchmark corpus."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
CARDS = EXAMPLES / "demo-cards.json"
FIXES = EXAMPLES / "fix-registry" / "fixes.json"
DEMO_BRAIN = EXAMPLES / "demo-brain"


def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_cards_are_unique_and_complete() -> None:
    payload = json.loads(CARDS.read_text(encoding="utf-8"))
    cards = payload["cards"]
    assert len(cards) == 6
    ids = [card["id"] for card in cards]
    assert len(ids) == len(set(ids))
    for card in cards:
        assert card["title"]
        assert card["body"].startswith("# ")
        assert card["created"] < card["updated"]


def test_fix_corpus_is_complete() -> None:
    payload = json.loads(FIXES.read_text(encoding="utf-8"))
    entries = payload["entries"]
    assert len(entries) == 15
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids))
    assert sum(1 for entry in entries if entry.get("demo")) == 6
    queries = [query for entry in entries for query in entry["queries"]]
    assert len(queries) == 45
    assert {query["lang"] for query in queries} == {"en", "tr"}


def test_checked_in_demo_brain_is_healthy() -> None:
    from engramkeep.store import Store

    store = Store(DEMO_BRAIN)
    report = store.doctor()
    assert report.ok is True, report.errors
    assert report.cards == 6
    assert report.unredacted == []
    fixes = store.search_fixes("database is locked")
    assert fixes
    assert fixes[0].entry.project == "Prairie ML"


def test_demo_brain_is_reproducible(tmp_path: Path) -> None:
    builder = _load_script("build_demo_brain", ROOT / "scripts" / "build_demo_brain.py")
    output = builder.build(
        tmp_path / "demo-brain",
        CARDS,
        FIXES,
        allowed_root=tmp_path,
    )

    generated = sorted(path.relative_to(output) for path in output.rglob("*") if path.is_file())
    checked_in = sorted(
        path.relative_to(DEMO_BRAIN) for path in DEMO_BRAIN.rglob("*") if path.is_file()
    )
    assert generated == checked_in
    for relative in generated:
        assert (output / relative).read_bytes() == (DEMO_BRAIN / relative).read_bytes(), relative


def test_benchmark_meets_the_documented_floor() -> None:
    benchmark = _load_script(
        "benchmark_fix_registry", ROOT / "scripts" / "benchmark_fix_registry.py"
    )
    corpus = benchmark.load_corpus(FIXES)
    result = benchmark.run_benchmark(corpus, repeats=1)

    assert result["queries"] == 45
    assert result["top1"] / result["queries"] >= 0.90
    assert result["top3"] == result["queries"]
    assert result["turkish"]["top1"] / result["turkish"]["queries"] >= 0.90
    assert result["no_match"]["clean"] >= 2
