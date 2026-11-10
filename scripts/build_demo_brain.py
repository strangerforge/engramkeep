"""Build the synthetic demo store from the checked-in JSON sources.

The demo store is ordinary Engramkeep data: six project cards and a handful of
resolved fixes. It exists so the README screenshots, the dashboard, and the
benchmark can be reproduced without touching real memory.

The build is deterministic: every timestamp comes from the source files, so
running the script twice produces byte-identical output. The script refuses to
replace any directory outside ``examples/``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from engramkeep.models import Card  # noqa: E402
from engramkeep.paths import atomic_write_text  # noqa: E402
from engramkeep.store import Store  # noqa: E402
from engramkeep.troubleshoot import TroubleEntry, render_registry  # noqa: E402

DEFAULT_OUTPUT = ROOT / "examples" / "demo-brain"
DEFAULT_CARDS = ROOT / "examples" / "demo-cards.json"
DEFAULT_FIXES = ROOT / "examples" / "fix-registry" / "fixes.json"
STORE_CREATED = "2026-10-01T08:00:00Z"

README = """# Synthetic demo brain

Six project cards and six resolved fixes, generated from
`examples/demo-cards.json` and `examples/fix-registry/fixes.json`. All data is
synthetic; it contains no real project names, people, paths, or secrets.

Explore it without touching your own memory:

```bash
engramkeep --home examples/demo-brain dashboard
engramkeep --home examples/demo-brain search "docker arm64"
engramkeep --home examples/demo-brain fixes "database is locked"
engramkeep --home examples/demo-brain doctor
```

Rebuild it after editing the source files:

```bash
python scripts/build_demo_brain.py
```

Do not copy real memory into this directory.
"""


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object with a clear error message."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return payload


def _require_list(payload: dict[str, Any], key: str, source: Path) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SystemExit(f"{source}: {key!r} must be a list of objects")
    return value


def _text(item: dict[str, Any], key: str, source: Path) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{source}: missing non-empty {key!r}")
    return value


def _activity_lines(cards: list[dict[str, Any]], fixes: list[dict[str, Any]]) -> list[str]:
    events: list[tuple[str, str]] = [
        (
            card["created"],
            f"remembered **{card['title']}** (`{card['id']}`); tags: {', '.join(card['tags'])}",
        )
        for card in cards
    ]
    events.extend(
        (f"{fix['date']}T12:00:00Z", f"recorded a fix for **{fix['project']}**") for fix in fixes
    )
    events.sort(key=lambda item: item[0])
    return [f"- {stamp} - {message}" for stamp, message in events]


def _audit_lines(cards: list[dict[str, Any]], fixes: list[dict[str, Any]]) -> list[str]:
    events: list[dict[str, Any]] = [{"ts": STORE_CREATED, "action": "init", "schema_version": 1}]
    events.extend(
        {
            "ts": card["created"],
            "action": "remember",
            "project": card["id"],
            "added": True,
            "created": True,
            "tags": list(card["tags"]),
        }
        for card in cards
    )
    events.extend(
        {
            "ts": f"{fix['date']}T12:00:00Z",
            "action": "record_fix",
            "project": fix["project"],
            "error": fix["error"][:120],
            "workspace": fix["workspace"],
        }
        for fix in fixes
    )
    events.extend(
        {"ts": card["updated"], "action": "reindex", "cards": len(cards), "errors": 0}
        for card in cards
        if card["updated"] > card["created"]
    )
    events.sort(key=lambda event: str(event["ts"]))
    return [json.dumps(event, ensure_ascii=False, sort_keys=True) for event in events]


def build(
    output: Path,
    cards_path: Path,
    fixes_path: Path,
    *,
    allowed_root: Path | None = None,
) -> Path:
    """Generate the demo store at ``output`` and return the path."""
    output = output.resolve()
    examples_root = (allowed_root or (ROOT / "examples")).resolve()
    if examples_root not in output.parents:
        raise SystemExit(f"refusing to write outside {examples_root}: {output}")

    cards_doc = load_json(cards_path)
    fixes_doc = load_json(fixes_path)
    cards = _require_list(cards_doc, "cards", cards_path)
    all_fixes = _require_list(fixes_doc, "entries", fixes_path)
    demo_fixes = [fix for fix in all_fixes if fix.get("demo") is True]

    if not cards:
        raise SystemExit(f"{cards_path}: no cards to build")
    if not demo_fixes:
        raise SystemExit(f"{fixes_path}: no entries marked demo")

    with tempfile.TemporaryDirectory(prefix="engramkeep-demo-") as tmp:
        store = Store(Path(tmp) / "brain")
        store.init()

        for raw in cards:
            card = Card(
                id=_text(raw, "id", cards_path),
                title=_text(raw, "title", cards_path),
                created=_text(raw, "created", cards_path),
                updated=_text(raw, "updated", cards_path),
                tags=[str(tag) for tag in raw.get("tags", [])],
                body=_text(raw, "body", cards_path),
            )
            store.save_card(card)

        entries = [
            TroubleEntry(
                project=_text(fix, "project", fixes_path),
                error=_text(fix, "error", fixes_path),
                fix=_text(fix, "fix", fixes_path),
                workspace=_text(fix, "workspace", fixes_path),
                date=_text(fix, "date", fixes_path),
            )
            for fix in demo_fixes
        ]
        entries.sort(key=lambda entry: entry.date)
        atomic_write_text(store.troubleshooting_path, render_registry(entries))

        # Reindex before writing the deterministic activity files: reindex
        # appends an audit event with the current clock.
        store.reindex()

        atomic_write_text(
            store.meta_path,
            json.dumps({"schema_version": 1, "created": STORE_CREATED}, indent=2) + "\n",
        )
        atomic_write_text(
            store.recent_path,
            "# Recent Activity\n\n" + "\n".join(_activity_lines(cards, demo_fixes)) + "\n",
        )
        atomic_write_text(
            store.audit_path,
            "\n".join(_audit_lines(cards, demo_fixes)) + "\n",
        )
        atomic_write_text(store.home / "README.md", README)

        report = store.doctor()
        if not report.ok:
            raise SystemExit("generated store is unhealthy: " + "; ".join(report.errors))
        if report.cards != len(cards):
            raise SystemExit(f"expected {len(cards)} cards, found {report.cards}")

        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(
            store.home,
            output,
            ignore=shutil.ignore_patterns("trash", "__pycache__", ".engramkeep.lock"),
        )

    return output


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cards", type=Path, default=DEFAULT_CARDS)
    parser.add_argument("--fixes", type=Path, default=DEFAULT_FIXES)
    args = parser.parse_args(argv)

    output = build(args.output, args.cards, args.fixes)
    print(f"built {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
