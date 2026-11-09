"""Command-line interface for Engramkeep."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, dashboard, mcp_server
from .config import resolve_home
from .errors import EngramkeepError, InstallerError, StoreError
from .installer import available_agents, format_plan, install_agents, plan_installation
from .models import render_card
from .paths import atomic_write_text
from .search import SearchHit, search_cards
from .store import Store
from .troubleshoot import FixHit


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _open_store(args: argparse.Namespace, *, create: bool = False) -> Store:
    store = Store(resolve_home(args.home))
    if create and not store.is_initialized():
        store.init()
    if not store.is_initialized():
        raise StoreError(f"no Engramkeep store at {store.home}; run 'engramkeep init' first")
    return store


def _format_hit(hit: SearchHit) -> str:
    lines = [f"{hit.title} ({hit.id})"]
    if hit.tags:
        lines.append(f"  tags: {', '.join(hit.tags)}")
    if hit.snippet:
        lines.append(f"  {hit.snippet}")
    return "\n".join(lines)


def _cmd_init(args: argparse.Namespace) -> int:
    result = Store(resolve_home(args.home)).init()
    if result.created:
        action = "Repaired" if result.already_initialized else "Initialized"
        print(f"{action} Engramkeep at {result.home}")
        for path in result.created:
            if path == result.home:
                print(f"  created {path}")
                continue
            try:
                relative = path.relative_to(result.home)
            except ValueError:
                relative = path
            print(f"  created {relative}")
    else:
        print(f"Engramkeep is already initialized at {result.home}")
    return 0


def _cmd_remember(args: argparse.Namespace) -> int:
    store = _open_store(args, create=True)
    result = store.remember(args.project, args.decision, tags=args.tag)
    if args.json:
        _print_json(result.to_dict())
    elif result.added:
        print(f"Remembered in {result.card.id}: {result.card.title}")
    elif result.tags_added:
        print(f"Updated tags for {result.card.id}: {', '.join(result.tags_added)}")
    else:
        print(f"Decision already recorded in {result.card.id}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    store = _open_store(args)
    scan = store.scan_cards()
    if scan.errors:
        print(f"warning: skipped {len(scan.errors)} malformed card(s)", file=sys.stderr)
    hits = search_cards(scan.cards, args.query, tag=args.tag, limit=args.limit)
    if args.json:
        _print_json([hit.to_dict() for hit in hits])
        return 0
    if not hits:
        print("No matches.")
        return 0
    print("\n\n".join(_format_hit(hit) for hit in hits))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    store = _open_store(args)
    card = store.get_card(args.project)
    if card is None:
        raise StoreError(f"project not found: {args.project}")
    if args.json:
        _print_json(card.to_dict())
    else:
        print(render_card(card), end="")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    store = _open_store(args)
    scan = store.scan_cards()
    cards = sorted(scan.cards, key=lambda card: (card.updated, card.title.lower()), reverse=True)
    if args.json:
        _print_json([card.to_dict() for card in cards])
        return 0
    if not cards:
        print("No projects yet.")
        return 0
    for card in cards:
        tags = f" [{', '.join(card.tags)}]" if card.tags else ""
        updated = f" ({card.updated[:10]})" if card.updated else ""
        print(f"- {card.id}: {card.title}{tags}{updated}")
    if scan.errors:
        print(f"warning: skipped {len(scan.errors)} malformed card(s)", file=sys.stderr)
    return 0


def _cmd_recent(args: argparse.Namespace) -> int:
    store = _open_store(args)
    lines = store.recent(args.limit)
    if args.json:
        _print_json(lines)
        return 0
    if not lines:
        print("No activity yet.")
        return 0
    print("\n".join(lines))
    return 0


def _format_fix(hit: FixHit) -> str:
    payload = hit.entry
    workspace = payload.workspace or "General"
    lines = [f"{payload.project} ({payload.date})"]
    lines.append(f"  workspace: {workspace}")
    lines.append(f"  problem: {payload.error}")
    lines.append(f"  fix: {payload.fix}")
    return "\n".join(lines)


def _cmd_fix(args: argparse.Namespace) -> int:
    store = _open_store(args, create=True)
    entry = store.record_fix(
        args.error,
        args.solution,
        project=args.project,
        workspace=args.workspace,
    )
    if args.json:
        _print_json(entry.to_dict())
    else:
        print(f"Recorded fix for {entry.project}: {entry.error[:80]}")
    return 0


def _cmd_fixes(args: argparse.Namespace) -> int:
    store = _open_store(args)
    hits = store.search_fixes(args.query, limit=args.limit)
    if args.json:
        _print_json([hit.to_dict() for hit in hits])
        return 0
    if not hits:
        print("No fixes recorded yet." if not args.query else "No matching fixes.")
        return 0
    print("\n\n".join(_format_fix(hit) for hit in hits))
    return 0


def _cmd_forget(args: argparse.Namespace) -> int:
    if not args.yes:
        print("refusing to forget without --yes", file=sys.stderr)
        return 2
    store = _open_store(args)
    if not store.forget(args.project):
        raise StoreError(f"project not found: {args.project}")
    print(f"Moved {args.project} to trash.")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    store = _open_store(args)
    document = store.export_cards()
    cards = document.get("cards")
    if not isinstance(cards, list):
        raise StoreError("export document is missing its card list")
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if not args.output:
        print(payload, end="")
        return 0

    output = Path(args.output).expanduser().resolve()
    if output.exists() and not args.force:
        raise StoreError(f"refusing to overwrite {output}; pass --force to replace it")
    atomic_write_text(output, payload)
    print(f"Exported {len(cards)} card(s) to {output}")
    return 0


def _cmd_reindex(args: argparse.Namespace) -> int:
    store = _open_store(args)
    scan = store.reindex()
    print(f"Reindexed {len(scan.cards)} card(s).")
    if scan.errors:
        print(f"warning: skipped {len(scan.errors)} malformed card(s)", file=sys.stderr)
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    report = Store(resolve_home(args.home)).doctor()
    if args.json:
        _print_json(report.to_dict())
        return 0 if report.ok else 1

    print("Engramkeep doctor")
    print(f"Home: {report.home}")
    print(f"Initialized: {'yes' if report.initialized else 'no'}")
    print(f"Schema: {report.schema_version if report.schema_version is not None else 'unknown'}")
    print(f"Cards: {report.cards}")
    print(f"Index: {'ok' if report.index_present else 'missing'}")
    print(f"Recent activity: {'ok' if report.recent_present else 'missing'}")
    print(f"Audit log: {'ok' if report.audit_present else 'missing'}")
    print(f"Permissions: {'ok' if report.permissions_ok else 'too broad'}")
    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}")
    print(f"Result: {'OK' if report.ok else 'FAILED'}")
    return 0 if report.ok else 1


def _cmd_path(args: argparse.Namespace) -> int:
    print(resolve_home(args.home))
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    if args.status:
        info = mcp_server.status()
        print(f"MCP: {info['status']}")
        print(f"Transport: {info['transport']}")
        print(f"Protocol: {info['protocol_version']}")
        print(f"Writes: {info['writes']}")
        return 0
    return mcp_server.serve(resolve_home(args.home), allow_write=args.allow_write)


def _cmd_dashboard(args: argparse.Namespace) -> int:
    if args.status:
        info = dashboard.status()
        print(f"Dashboard: {info['status']}")
        print(f"Bind: {info['bind']}")
        print(f"Auth: {info['auth']}")
        print(f"Writes: {info['writes']}")
        print(f"CSP: {info['csp']}")
        return 0
    return dashboard.serve(
        resolve_home(args.home),
        port=args.port,
        allow_write=args.allow_write,
    )


def _cmd_install(args: argparse.Namespace) -> int:
    if args.list_agents:
        for name in available_agents():
            print(format_plan(plan_installation(name)))
            print()
        return 0
    if not args.agent:
        print("error: --agent is required (or use --list)", file=sys.stderr)
        return 2

    project_dir = Path(args.project_dir).expanduser().resolve() if args.project_dir else Path.cwd()
    backup_root = resolve_home(args.home) / "backups" / "installer"
    try:
        result = install_agents(
            args.agent,
            user_home=Path.home(),
            project_dir=project_dir,
            backup_root=backup_root,
            scope=args.scope,
            mcp=args.mcp,
            dry_run=not (args.apply or args.uninstall),
            remove=args.uninstall,
        )
    except KeyError as exc:
        print(f"error: {exc.args[0]}", file=sys.stderr)
        print(f"available agents: {', '.join(available_agents())}", file=sys.stderr)
        return 1
    except InstallerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        _print_json(result.to_dict())
        return 0

    for operation in result.operations:
        line = f"{operation.action}: {operation.target}"
        if operation.backup:
            line += f" (backup: {operation.backup})"
        if operation.reason:
            line += f" ({operation.reason})"
        print(line)
    if result.mode == "dry-run":
        print("Dry run: no files were modified. Pass --apply to write.")
    if result.backup_dir:
        print(f"Backups: {result.backup_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="engramkeep",
        description="Local-first, Markdown-native memory for AI coding agents.",
    )
    parser.add_argument(
        "--home",
        metavar="DIR",
        help="memory directory (default: ENGRAMKEEP_HOME or the platform data directory)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create the memory directory")
    init_parser.set_defaults(handler=_cmd_init)

    remember = subparsers.add_parser("remember", help="record a durable decision")
    remember.add_argument("project", help="project name or id")
    remember.add_argument("decision", help="decision text")
    remember.add_argument("--tag", action="append", default=[], help="tag to add (repeatable)")
    remember.add_argument("--json", action="store_true", help="print JSON")
    remember.set_defaults(handler=_cmd_remember)

    search = subparsers.add_parser("search", help="search cards")
    search.add_argument("query", help="search terms")
    search.add_argument("--tag", help="filter by tag")
    search.add_argument("--limit", type=int, default=10, help="maximum results (default: 10)")
    search.add_argument("--json", action="store_true", help="print JSON")
    search.set_defaults(handler=_cmd_search)

    show = subparsers.add_parser("show", help="print one card")
    show.add_argument("project", help="project name or id")
    show.add_argument("--json", action="store_true", help="print JSON")
    show.set_defaults(handler=_cmd_show)

    list_parser = subparsers.add_parser("list", help="list projects")
    list_parser.add_argument("--json", action="store_true", help="print JSON")
    list_parser.set_defaults(handler=_cmd_list)

    recent = subparsers.add_parser("recent", help="show recent activity")
    recent.add_argument("--limit", type=int, default=10, help="maximum entries (default: 10)")
    recent.add_argument("--json", action="store_true", help="print JSON")
    recent.set_defaults(handler=_cmd_recent)

    forget = subparsers.add_parser("forget", help="move a card to trash")
    forget.add_argument("project", help="project name or id")
    forget.add_argument("--yes", action="store_true", help="confirm the move")
    forget.set_defaults(handler=_cmd_forget)

    fix = subparsers.add_parser("fix", help="record a resolved error and its verified fix")
    fix.add_argument("error", help="the error or problem that was resolved")
    fix.add_argument("--solution", required=True, help="the verified fix that worked")
    fix.add_argument("--project", help="project name (default: General)")
    fix.add_argument("--workspace", help="workspace path or label")
    fix.add_argument("--json", action="store_true", help="print JSON")
    fix.set_defaults(handler=_cmd_fix)

    fixes = subparsers.add_parser("fixes", help="search the troubleshooting registry")
    fixes.add_argument(
        "query",
        nargs="?",
        default=None,
        help="search terms (run without it to list the newest fixes)",
    )
    fixes.add_argument("--limit", type=int, default=10, help="maximum results (default: 10)")
    fixes.add_argument("--json", action="store_true", help="print JSON")
    fixes.set_defaults(handler=_cmd_fixes)

    export = subparsers.add_parser("export", help="export all cards as JSON")
    export.add_argument("--output", metavar="FILE", help="write to FILE instead of stdout")
    export.add_argument("--force", action="store_true", help="overwrite an existing output file")
    export.set_defaults(handler=_cmd_export)

    reindex = subparsers.add_parser("reindex", help="regenerate INDEX.md")
    reindex.set_defaults(handler=_cmd_reindex)

    doctor = subparsers.add_parser("doctor", help="check the local store")
    doctor.add_argument("--json", action="store_true", help="print JSON")
    doctor.set_defaults(handler=_cmd_doctor)

    path_parser = subparsers.add_parser("path", help="print the memory directory")
    path_parser.set_defaults(handler=_cmd_path)

    mcp = subparsers.add_parser("mcp", help="run the MCP stdio server")
    mcp.add_argument("--status", action="store_true", help="print server status and exit")
    mcp.add_argument(
        "--allow-write",
        action="store_true",
        help="enable the engramkeep_remember and engramkeep_record_fix tools",
    )
    mcp.set_defaults(handler=_cmd_mcp)

    dashboard_parser = subparsers.add_parser("dashboard", help="run the local dashboard")
    dashboard_parser.add_argument("--status", action="store_true", help="print status and exit")
    dashboard_parser.add_argument(
        "--port",
        type=int,
        default=dashboard.DEFAULT_PORT,
        help=f"loopback port (default: {dashboard.DEFAULT_PORT}; 0 picks a free port)",
    )
    dashboard_parser.add_argument(
        "--allow-write",
        action="store_true",
        help="enable the remember form",
    )
    dashboard_parser.set_defaults(handler=_cmd_dashboard)

    install = subparsers.add_parser(
        "install",
        help="plan or apply agent integration (dry run by default)",
    )
    install.add_argument("--agent", help="agent identifier, or 'all'")
    install.add_argument(
        "--list",
        dest="list_agents",
        action="store_true",
        help="list supported agents and exit",
    )
    install.add_argument(
        "--scope",
        choices=["auto", "global", "project"],
        default="auto",
        help="target scope (default: global when documented, otherwise project)",
    )
    install.add_argument(
        "--project-dir",
        metavar="DIR",
        help="project root for project-scoped targets (default: current directory)",
    )
    mode = install.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="write the managed block and back up existing files",
    )
    mode.add_argument(
        "--uninstall",
        action="store_true",
        help="remove the Engramkeep managed block",
    )
    install.add_argument(
        "--mcp",
        action="store_true",
        help="also register the MCP server in the agent JSON config",
    )
    install.add_argument("--json", action="store_true", help="print JSON")
    install.set_defaults(handler=_cmd_install)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return an exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except EngramkeepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
