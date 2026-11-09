"""Measure fix-recall quality and latency on the synthetic registry.

The corpus in ``examples/fix-registry/fixes.json`` contains realistic error
messages, human-written queries in English and Turkish, and three queries that
should not match anything. The benchmark reports:

- top-1 accuracy: the expected fix is the first result,
- top-3 recall: the expected fix is in the first three results,
- mean reciprocal rank (MRR),
- cross-language top-1 accuracy for Turkish queries over English entries,
- p50/p95 query latency,
- how many no-match queries correctly returned nothing.

It is a regression tool, not a claim of semantic search: scoring is lexical
with a small bilingual concept bonus. Run it after changing ranking weights or
the concept map.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from engramkeep.troubleshoot import TroubleEntry, search_entries  # noqa: E402

DEFAULT_CORPUS = ROOT / "examples" / "fix-registry" / "fixes.json"
DEFAULT_REPEATS = 20


def load_corpus(path: Path) -> dict[str, Any]:
    """Load and validate the benchmark corpus."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SystemExit(f"{path}: 'entries' must be a non-empty list")
    return payload


def build_entries(corpus: dict[str, Any]) -> list[TroubleEntry]:
    """Turn the corpus into registry entries."""
    entries: list[TroubleEntry] = []
    for item in corpus["entries"]:
        if not isinstance(item, dict):
            raise SystemExit("every corpus entry must be an object")
        try:
            entries.append(
                TroubleEntry(
                    project=str(item["project"]),
                    error=str(item["error"]),
                    fix=str(item["fix"]),
                    workspace=item.get("workspace"),
                    date=str(item["date"]),
                )
            )
        except KeyError as exc:
            raise SystemExit(f"corpus entry missing {exc.args[0]!r}") from exc
    return entries


def collect_queries(corpus: dict[str, Any]) -> list[tuple[dict[str, str], TroubleEntry]]:
    """Return ``(query, expected_entry)`` pairs in corpus order."""
    entries = build_entries(corpus)
    by_error = {entry.error: entry for entry in entries}
    cases: list[tuple[dict[str, str], TroubleEntry]] = []
    for item in corpus["entries"]:
        expected = by_error[str(item["error"])]
        queries = item.get("queries", [])
        if not isinstance(queries, list) or not queries:
            raise SystemExit(f"entry {item.get('id')!r} has no queries")
        for query in queries:
            if not isinstance(query, dict) or not str(query.get("q", "")).strip():
                raise SystemExit(f"entry {item.get('id')!r} has an invalid query")
            cases.append(
                (
                    {"q": str(query["q"]), "lang": str(query.get("lang", "en"))},
                    expected,
                )
            )
    return cases


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def run_benchmark(corpus: dict[str, Any], *, repeats: int = DEFAULT_REPEATS) -> dict[str, Any]:
    """Run every query and return metrics plus per-entry detail."""
    entries = build_entries(corpus)
    cases = collect_queries(corpus)

    ranks: list[int | None] = []
    latencies: list[float] = []
    per_entry: dict[str, dict[str, Any]] = {}
    for item in corpus["entries"]:
        per_entry[str(item["id"])] = {
            "project": item["project"],
            "queries": 0,
            "top1": 0,
            "top3": 0,
            "worst_rank": None,
        }

    by_error = {
        entry.error: str(item["id"]) for entry, item in zip(entries, corpus["entries"], strict=True)
    }
    for query, expected in cases:
        hits = search_entries(entries, query["q"], limit=3)
        rank = next(
            (index + 1 for index, hit in enumerate(hits) if hit.entry.error == expected.error),
            None,
        )
        ranks.append(rank)
        entry_id = by_error[expected.error]
        detail = per_entry[entry_id]
        detail["queries"] += 1
        if rank == 1:
            detail["top1"] += 1
        if rank is not None and rank <= 3:
            detail["top3"] += 1
        if rank is not None and (detail["worst_rank"] is None or rank > detail["worst_rank"]):
            detail["worst_rank"] = rank

    for _ in range(max(1, repeats)):
        for query, _ in cases:
            started = time.perf_counter()
            search_entries(entries, query["q"], limit=3)
            latencies.append((time.perf_counter() - started) * 1000)

    total = len(cases)
    top1 = sum(1 for rank in ranks if rank == 1)
    top3 = sum(1 for rank in ranks if rank is not None and rank <= 3)
    mrr = sum(1.0 / rank for rank in ranks if rank is not None) / total if total else 0.0

    turkish = [rank for rank, (query, _) in zip(ranks, cases, strict=True) if query["lang"] == "tr"]
    turkish_top1 = sum(1 for rank in turkish if rank == 1)
    turkish_top3 = sum(1 for rank in turkish if rank is not None and rank <= 3)

    no_match = corpus.get("no_match_queries", [])
    no_match_clean = 0
    no_match_all: list[dict[str, Any]] = []
    if isinstance(no_match, list):
        for query in no_match:
            hits = search_entries(entries, str(query), limit=3)
            if not hits:
                no_match_clean += 1
            else:
                no_match_all.append(
                    {
                        "query": str(query),
                        "hits": [hit.entry.project for hit in hits],
                    }
                )

    return {
        "entries": len(entries),
        "queries": total,
        "top1": top1,
        "top3": top3,
        "mrr": mrr,
        "turkish": {
            "queries": len(turkish),
            "top1": turkish_top1,
            "top3": turkish_top3,
        },
        "no_match": {
            "queries": len(no_match) if isinstance(no_match, list) else 0,
            "clean": no_match_clean,
            "false_hits": no_match_all,
        },
        "latency_ms": {
            "samples": len(latencies),
            "p50": round(_percentile(latencies, 0.50), 3),
            "p95": round(_percentile(latencies, 0.95), 3),
            "mean": round(statistics.fmean(latencies), 3) if latencies else 0.0,
        },
        "per_entry": per_entry,
    }


def render_markdown(result: dict[str, Any]) -> str:
    """Render a human-readable benchmark report."""
    total = result["queries"]
    top1_pct = 100.0 * result["top1"] / total
    top3_pct = 100.0 * result["top3"] / total
    turkish = result["turkish"]
    lat = result["latency_ms"]
    lines = [
        "# Fix recall benchmark",
        "",
        "Synthetic corpus: "
        f"{result['entries']} error/fix pairs and {total} human-written queries "
        "(English and Turkish). Scoring is lexical with a small bilingual concept",
        "bonus; there are no embeddings and no network calls.",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Top-1 accuracy | {result['top1']}/{total} ({top1_pct:.1f}%) |",
        f"| Top-3 recall | {result['top3']}/{total} ({top3_pct:.1f}%) |",
        f"| Mean reciprocal rank | {result['mrr']:.3f} |",
        (
            f"| Turkish query, English entry, top-1 | "
            f"{turkish['top1']}/{turkish['queries']} "
            f"({100.0 * turkish['top1'] / turkish['queries']:.1f}%) |"
        ),
        (
            f"| Turkish query, English entry, top-3 | "
            f"{turkish['top3']}/{turkish['queries']} "
            f"({100.0 * turkish['top3'] / turkish['queries']:.1f}%) |"
        ),
        f"| Query latency p50 | {lat['p50']:.3f} ms |",
        f"| Query latency p95 | {lat['p95']:.3f} ms |",
        (
            f"| No-match queries returning nothing | "
            f"{result['no_match']['clean']}/{result['no_match']['queries']} |"
        ),
        "",
        "## Per entry",
        "",
        "| Entry | Project | Queries | Top-1 | Top-3 | Worst rank |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry_id, detail in result["per_entry"].items():
        worst = "-" if detail["worst_rank"] is None else str(detail["worst_rank"])
        lines.append(
            f"| `{entry_id}` | {detail['project']} | {detail['queries']} | "
            f"{detail['top1']} | {detail['top3']} | {worst} |"
        )

    if result["no_match"]["false_hits"]:
        lines.extend(["", "No-match queries that still returned a result:", ""])
        for item in result["no_match"]["false_hits"]:
            lines.append(f"- `{item['query']}` matched {', '.join(item['hits'])}")

    lines.extend(
        [
            "",
            "## Method",
            "",
            "Each corpus entry has two or three queries written independently of the",
            "stored error text. The expected fix counts as correct only when it appears",
            "in the first result (top-1) or anywhere in the first three results (top-3).",
            "Latency is measured over repeated in-process searches and is indicative,",
            "not a cross-machine benchmark.",
            "",
            "Reproduce:",
            "",
            "```bash",
            "python scripts/benchmark_fix_registry.py --output docs/BENCHMARK.md",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, help="write the Markdown report to this path")
    parser.add_argument("--json", action="store_true", help="print metrics as JSON")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument(
        "--min-top1",
        type=float,
        default=0.0,
        help="exit nonzero when top-1 accuracy is below this percentage (0 disables)",
    )
    args = parser.parse_args(argv)

    result = run_benchmark(load_corpus(args.corpus), repeats=args.repeats)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report = render_markdown(result)
        if args.output:
            args.output.write_text(report, encoding="utf-8")
            print(f"wrote {args.output}")
        else:
            print(report)

    total = result["queries"]
    accuracy = 100.0 * result["top1"] / total if total else 0.0
    if args.min_top1 and accuracy < args.min_top1:
        print(
            f"top-1 accuracy {accuracy:.1f}% is below the required {args.min_top1:.1f}%",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
