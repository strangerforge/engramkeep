"""Command-line interface for Engramkeep."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, dashboard, mcp_server
from .adapters import available_formats
from .config import ENV_HOME, PROJECT_STORE_DIR, find_project_store, resolve_home
from .errors import EngramkeepError, InstallerError, StoreError
from .importer import import_transcript
from .installer import available_agents, format_plan, install_agents, plan_installation
from .migrations import migrate_store, rollback_migration
from .models import render_card
from .paths import atomic_write_text
from .search import SearchHit, search_cards
from .store import LayeredStore, Store
from .sync import sync_commit, sync_init, sync_status
from .troubleshoot import FixHit

_ALL_COMMANDS = (
    "init",
    "remember",
    "supersede",
    "untag",
    "search",
    "show",
    "list",
    "recent",
    "forget",
    "trash",
    "restore",
    "fix",
    "fixes",
    "export",
    "reindex",
    "doctor",
    "migrate",
    "sync",
    "path",
    "mcp",
    "dashboard",
    "install",
    "import",
    "completion",
)


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _resolve_target_home(args: argparse.Namespace) -> Path:
    if getattr(args, "local", False):
        return (Path.cwd() / PROJECT_STORE_DIR).resolve()
    return resolve_home(args.home)


def _open_store(args: argparse.Namespace, *, create: bool = False) -> Store:
    store = Store(_resolve_target_home(args))
    if create and not store.is_initialized():
        store.init()
    if not store.is_initialized():
        raise StoreError(f"no Engramkeep store at {store.home}; run 'engramkeep init' first")
    return store


def _open_layered(args: argparse.Namespace) -> LayeredStore:
    global_store = Store(resolve_home(args.home))
    project_store: Store | None = None
    explicit_project = getattr(args, "project_store", None)
    no_local = getattr(args, "no_local", False)

    if explicit_project:
        project_store = Store(Path(explicit_project).expanduser().resolve())
    elif not no_local and args.home is None and not os.environ.get(ENV_HOME):
        discovered = find_project_store()
        if discovered is not None and discovered != global_store.home:
            project_store = Store(discovered)

    return LayeredStore(global_store, project_store)


def _format_hit(hit: SearchHit) -> str:
    suffix = f" [{hit.source}]" if hit.source else ""
    lines = [f"{hit.title} ({hit.id}){suffix}"]
    if hit.tags:
        lines.append(f"  tags: {', '.join(hit.tags)}")
    if hit.snippet:
        lines.append(f"  {hit.snippet}")
    return "\n".join(lines)


def _cmd_init(args: argparse.Namespace) -> int:
    result = Store(_resolve_target_home(args)).init()
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


def _cmd_supersede(args: argparse.Namespace) -> int:
    store = _open_store(args)
    result = store.supersede(args.project, args.old, args.new, reason=args.reason)
    if args.json:
        _print_json(result.to_dict())
    else:
        print(f"Superseded decision in {result.card.id}:")
        print(f"  old: {result.old_decision}")
        print(f"  new: {result.new_decision}")
        if result.reason:
            print(f"  reason: {result.reason}")
    return 0


def _cmd_untag(args: argparse.Namespace) -> int:
    store = _open_store(args)
    result = store.untag(args.project, args.tag)
    if args.json:
        _print_json(result.to_dict())
    elif result.removed_tags:
        print(f"Removed tags from {result.card.id}: {', '.join(result.removed_tags)}")
    else:
        print(f"No matching tags found on {result.card.id}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    layered = _open_layered(args)
    if layered.is_layered:
        hits, errors = layered.search(args.query, tag=args.tag, limit=args.limit)
    else:
        store = _open_store(args)
        scan = store.scan_cards()
        errors = list(scan.errors)
        hits = search_cards(scan.cards, args.query, tag=args.tag, limit=args.limit)
    if errors:
        print(f"warning: skipped {len(errors)} malformed card(s)", file=sys.stderr)
    if args.json:
        _print_json([hit.to_dict() for hit in hits])
        return 0
    if not hits:
        print("No matches.")
        return 0
    print("\n\n".join(_format_hit(hit) for hit in hits))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    layered = _open_layered(args)
    if layered.is_layered:
        found = layered.get_card(args.project)
        if found is None:
            raise StoreError(f"project not found: {args.project}")
        layered_card, source = found
        if args.json:
            payload = layered_card.to_dict()
            payload["source"] = source
            _print_json(payload)
        else:
            print(render_card(layered_card), end="")
        return 0

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
    layered = _open_layered(args)
    if layered.is_layered:
        cards, sources, errors = layered.scan_cards()
    else:
        store = _open_store(args)
        scan = store.scan_cards()
        cards = scan.cards
        sources = {}
        errors = list(scan.errors)

    cards.sort(key=lambda card: (card.updated, card.title.lower()), reverse=True)
    if args.json:
        items = []
        for card in cards:
            entry = card.to_dict()
            if card.id in sources:
                entry["source"] = sources[card.id]
            items.append(entry)
        _print_json(items)
        return 0
    if not cards:
        print("No projects yet.")
        return 0
    for card in cards:
        tags = f" [{', '.join(card.tags)}]" if card.tags else ""
        updated = f" ({card.updated[:10]})" if card.updated else ""
        src = f" <{sources[card.id]}>" if card.id in sources else ""
        print(f"- {card.id}: {card.title}{tags}{updated}{src}")
    if errors:
        print(f"warning: skipped {len(errors)} malformed card(s)", file=sys.stderr)
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
    source_tag = f" [{hit.source}]" if hit.source else ""
    lines = [f"{payload.project} ({payload.date}){source_tag}"]
    lines.append(f"  workspace: {workspace}")
    lines.append(f"  problem: {payload.error}")
    lines.append(f"  fix: {payload.fix}")
    return "\n".join(lines)


def _cmd_fix(args: argparse.Namespace) -> int:
    store = _open_store(args, create=True)
    entry, added = store.record_fix_result(
        args.error,
        args.solution,
        project=args.project,
        workspace=args.workspace,
    )
    if args.json:
        _print_json(entry.to_dict())
    elif added:
        print(f"Recorded fix for {entry.project}: {entry.error[:80]}")
    else:
        print(f"Fix already recorded for {entry.project}: {entry.error[:80]}")
    return 0


def _cmd_fixes(args: argparse.Namespace) -> int:
    layered = _open_layered(args)
    if layered.is_layered:
        hits = layered.search_fixes(args.query, limit=args.limit)
    else:
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
    if args.decision:
        card, removed = store.remove_decision(args.project, args.decision)
        print(f"Removed decision from {card.id}: {removed}")
        return 0
    if not store.forget(args.project):
        raise StoreError(f"project not found: {args.project}")
    print(f"Moved {args.project} to trash.")
    return 0


def _cmd_trash(args: argparse.Namespace) -> int:
    store = _open_store(args)
    if args.purge:
        if not args.yes:
            print("refusing to purge trash without --yes", file=sys.stderr)
            return 2
        removed = store.purge_trash(project=args.project)
        if args.json:
            _print_json({"purged": removed, "project": args.project})
        else:
            print(f"Purged {removed} trashed card(s).")
        return 0

    items = store.list_trash()
    if args.project:
        from .paths import normalize_project_id

        target = normalize_project_id(args.project)
        items = [item for item in items if item.project_id == target]
    if args.json:
        _print_json([item.to_dict() for item in items])
        return 0
    if not items:
        print("Trash is empty.")
        return 0
    for item in items:
        when = f" ({item.trashed_at})" if item.trashed_at else ""
        print(f"- {item.project_id}: {item.filename}{when}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    store = _open_store(args)
    card = store.restore(args.project, filename=args.file, force=args.force)
    if args.json:
        _print_json(card.to_dict())
    else:
        print(f"Restored {card.id}: {card.title}")
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
    if (output.exists() or output.is_symlink()) and not args.force:
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
    store = Store(resolve_home(args.home))
    if args.fix:
        fix_result = store.doctor_fix()
        if args.json:
            _print_json(fix_result.to_dict())
            return 0 if fix_result.report.ok else 1
        print("Engramkeep doctor --fix")
        if fix_result.actions:
            for action in fix_result.actions:
                print(f"  fixed: {action}")
        else:
            print("  no repairs needed")
        if fix_result.backup_dir:
            print(f"  backups: {fix_result.backup_dir}")
        report = fix_result.report
    else:
        report = store.doctor()
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
    print(f"Audit chain: {report.audit_chain_status}")
    print(f"Permissions: {'ok' if report.permissions_ok else 'too broad'}")
    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}")
    print(f"Result: {'OK' if report.ok else 'FAILED'}")
    return 0 if report.ok else 1


def _cmd_migrate(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    if args.rollback:
        rb = rollback_migration(home, Path(args.rollback).expanduser())
        if args.json:
            _print_json(rb.to_dict())
        else:
            print(f"Rolled back {len(rb.restored_files)} file(s) from {rb.backup_dir}")
        return 0

    result = migrate_store(home, apply=args.apply)
    if args.json:
        _print_json(result.to_dict())
        return 0
    print(f"Migration ({result.mode}): v{result.from_version} -> v{result.to_version}")
    for step in result.steps_applied:
        print(f"  - {step}")
    if result.mode == "dry-run":
        if result.audit_sealed:
            print("  - seal legacy audit.log with SHA-256 hash chain")
        print("Dry run: no files were modified. Pass --apply to migrate.")
    elif result.mode == "up-to-date":
        print("Store is already up to date.")
    elif result.backup_dir:
        print(f"Backup: {result.backup_dir}")
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    store = _open_store(args)
    if args.init:
        status = sync_init(store)
        if args.json:
            _print_json(status.to_dict())
        else:
            print(f"Initialized local Git sync in {status.home} (allowlist mode; no auto-push).")
        return 0

    if args.status:
        status = sync_status(store)
        if args.json:
            _print_json(status.to_dict())
            return 0 if status.doctor_ok else 1
        print(f"Sync home: {status.home}")
        print(f"Git repo: {'yes' if status.is_git_repo else 'no'}")
        print(f"Doctor: {'ok' if status.doctor_ok else 'FAILED'}")
        print(f"Allowlisted files: {len(status.allowlisted_files)}")
        print(f"Changed allowlisted: {len(status.changed_files)}")
        for path in status.changed_files:
            print(f"  + {path}")
        if status.excluded_files:
            print(f"Excluded (ignored by allowlist): {len(status.excluded_files)}")
        for err in status.doctor_errors:
            print(f"error: {err}")
        return 0 if status.doctor_ok else 1

    result = sync_commit(store, message=args.message, apply=args.commit)
    if args.json:
        _print_json(result.to_dict())
        return 0
    print(f"Sync ({result.mode}): {result.message}")
    if result.commit_hash:
        print(f"Commit: {result.commit_hash}")
    for path in result.staged_files:
        print(f"  - {path}")
    return 0


def _cmd_path(args: argparse.Namespace) -> int:
    print(_resolve_target_home(args))
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    if args.status:
        info = mcp_server.status()
        print(f"MCP: {info['status']}")
        print(f"Transport: {info['transport']}")
        print(f"Protocol: {info['protocol_version']} (supported: {info['supported_versions']})")
        print(f"Capabilities: {info['capabilities']}")
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
    if args.open_browser:
        return dashboard.serve(
            resolve_home(args.home),
            port=args.port,
            allow_write=args.allow_write,
            open_browser=True,
        )
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
            mcp=args.mcp or args.mcp_allow_write,
            mcp_allow_write=args.mcp_allow_write,
            skill=args.skill,
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


def _cmd_import(args: argparse.Namespace) -> int:
    store = Store(resolve_home(args.home))
    source_path = Path(args.file).expanduser()
    result = import_transcript(
        store,
        source_path,
        fmt=args.fmt,
        project=args.project,
        limit=args.limit,
        apply=args.apply,
        interactive=args.interactive,
    )
    if args.json:
        _print_json(result.to_dict())
        return 0

    print(
        f"Transcript ({result.format}): {len(result.decisions)} decision(s), "
        f"{len(result.fixes)} fix(es) for project '{result.project}'"
    )
    for dec in result.decisions:
        print(f"  [decision L{dec.source_line}] {dec.text}")
    for fx in result.fixes:
        print(f"  [fix L{fx.source_line}] {fx.error} -> {fx.fix}")
    if result.applied:
        print(f"Applied: {result.written_decisions} decision(s), {result.written_fixes} fix(es).")
    else:
        print("Dry run: no files were modified. Pass --apply or --interactive to write.")
    return 0


def _completion_script(shell: str) -> str:
    cmds = " ".join(_ALL_COMMANDS)
    if shell == "bash":
        return (
            "_engramkeep_complete() {\n"
            '  local cur="${COMP_WORDS[COMP_CWORD]}"\n'
            "  if [[ $COMP_CWORD -eq 1 ]]; then\n"
            f'    COMPREPLY=( $(compgen -W "{cmds}" -- "$cur") )\n'
            "  fi\n"
            "}\n"
            "complete -F _engramkeep_complete engramkeep\n"
        )
    if shell == "zsh":
        return (
            "#compdef engramkeep\n"
            "_engramkeep() {\n"
            f"  local -a commands; commands=({cmds})\n"
            "  _describe 'command' commands\n"
            "}\n"
            "compdef _engramkeep engramkeep\n"
        )
    if shell == "fish":
        lines = [
            f"complete -c engramkeep -n '__fish_use_subcommand' -a '{cmd}'" for cmd in _ALL_COMMANDS
        ]
        return "\n".join(lines) + "\n"
    # PowerShell
    quoted = ", ".join(f"'{cmd}'" for cmd in _ALL_COMMANDS)
    ps_cls = "System.Management.Automation.CompletionResult"
    return (
        "Register-ArgumentCompleter -Native -CommandName engramkeep -ScriptBlock {\n"
        "  param($wordToComplete, $commandAst, $cursorPosition)\n"
        f'  @({quoted}) | Where-Object {{ $_ -like "$wordToComplete*" }} |\n'
        f"    ForEach-Object {{ [{ps_cls}]::new($_, $_, 'ParameterValue', $_) }}\n"
        "}\n"
    )


def _cmd_completion(args: argparse.Namespace) -> int:
    print(_completion_script(args.shell), end="")
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
    init_parser.add_argument(
        "--local",
        action="store_true",
        help="initialize a project-scoped .engramkeep/ store in the current directory",
    )
    init_parser.set_defaults(handler=_cmd_init)

    remember = subparsers.add_parser("remember", help="record a durable decision")
    remember.add_argument("project", help="project name or id")
    remember.add_argument("decision", help="decision text")
    remember.add_argument("--tag", action="append", default=[], help="tag to add (repeatable)")
    remember.add_argument("--local", action="store_true", help="write to project .engramkeep/")
    remember.add_argument("--json", action="store_true", help="print JSON")
    remember.set_defaults(handler=_cmd_remember)

    supersede = subparsers.add_parser(
        "supersede", help="replace a decision while keeping ADR history"
    )
    supersede.add_argument("project", help="project name or id")
    supersede.add_argument(
        "--old", required=True, help="existing decision text or unique substring"
    )
    supersede.add_argument("--new", required=True, help="replacement decision text")
    supersede.add_argument("--reason", help="optional reason for the change")
    supersede.add_argument("--local", action="store_true", help="target project .engramkeep/")
    supersede.add_argument("--json", action="store_true", help="print JSON")
    supersede.set_defaults(handler=_cmd_supersede)

    untag = subparsers.add_parser("untag", help="remove tag(s) from a project card")
    untag.add_argument("project", help="project name or id")
    untag.add_argument("--tag", action="append", required=True, help="tag to remove (repeatable)")
    untag.add_argument("--local", action="store_true", help="target project .engramkeep/")
    untag.add_argument("--json", action="store_true", help="print JSON")
    untag.set_defaults(handler=_cmd_untag)

    search = subparsers.add_parser("search", help="search cards")
    search.add_argument("query", help="search terms")
    search.add_argument("--tag", help="filter by tag")
    search.add_argument("--limit", type=int, default=10, help="maximum results (default: 10)")
    search.add_argument("--project-store", metavar="DIR", help="explicit project .engramkeep/ dir")
    search.add_argument("--no-local", action="store_true", help="ignore project .engramkeep/ layer")
    search.add_argument("--json", action="store_true", help="print JSON")
    search.set_defaults(handler=_cmd_search)

    show = subparsers.add_parser("show", help="print one card")
    show.add_argument("project", help="project name or id")
    show.add_argument("--project-store", metavar="DIR", help="explicit project .engramkeep/ dir")
    show.add_argument("--no-local", action="store_true", help="ignore project .engramkeep/ layer")
    show.add_argument("--json", action="store_true", help="print JSON")
    show.set_defaults(handler=_cmd_show)

    list_parser = subparsers.add_parser("list", help="list projects")
    list_parser.add_argument(
        "--project-store", metavar="DIR", help="explicit project .engramkeep/ dir"
    )
    list_parser.add_argument(
        "--no-local", action="store_true", help="ignore project .engramkeep/ layer"
    )
    list_parser.add_argument("--json", action="store_true", help="print JSON")
    list_parser.set_defaults(handler=_cmd_list)

    recent = subparsers.add_parser("recent", help="show recent activity")
    recent.add_argument("--limit", type=int, default=10, help="maximum entries (default: 10)")
    recent.add_argument("--json", action="store_true", help="print JSON")
    recent.set_defaults(handler=_cmd_recent)

    forget = subparsers.add_parser("forget", help="move a card to trash or remove one decision")
    forget.add_argument("project", help="project name or id")
    forget.add_argument(
        "--decision",
        help="remove only one matching decision bullet instead of trashing the entire card",
    )
    forget.add_argument("--yes", action="store_true", help="confirm the action")
    forget.set_defaults(handler=_cmd_forget)

    trash = subparsers.add_parser("trash", help="list or purge trashed cards")
    trash.add_argument("--project", help="filter by project id")
    trash.add_argument("--purge", action="store_true", help="permanently delete trashed cards")
    trash.add_argument("--yes", action="store_true", help="confirm --purge")
    trash.add_argument("--json", action="store_true", help="print JSON")
    trash.set_defaults(handler=_cmd_trash)

    restore = subparsers.add_parser("restore", help="restore a card from trash")
    restore.add_argument("project", help="project name or id")
    restore.add_argument("--file", metavar="NAME", help="specific trash filename to restore")
    restore.add_argument("--force", action="store_true", help="overwrite an existing active card")
    restore.add_argument("--json", action="store_true", help="print JSON")
    restore.set_defaults(handler=_cmd_restore)

    fix = subparsers.add_parser("fix", help="record a resolved error and its verified fix")
    fix.add_argument("error", help="the error or problem that was resolved")
    fix.add_argument("--solution", required=True, help="the verified fix that worked")
    fix.add_argument("--project", help="project name (default: General)")
    fix.add_argument("--workspace", help="workspace path or label")
    fix.add_argument("--local", action="store_true", help="write to project .engramkeep/")
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
    fixes.add_argument("--project-store", metavar="DIR", help="explicit project .engramkeep/ dir")
    fixes.add_argument("--no-local", action="store_true", help="ignore project .engramkeep/ layer")
    fixes.add_argument("--json", action="store_true", help="print JSON")
    fixes.set_defaults(handler=_cmd_fixes)

    export = subparsers.add_parser("export", help="export all cards as JSON")
    export.add_argument("--output", metavar="FILE", help="write to FILE instead of stdout")
    export.add_argument("--force", action="store_true", help="overwrite an existing output file")
    export.set_defaults(handler=_cmd_export)

    reindex = subparsers.add_parser("reindex", help="regenerate INDEX.md")
    reindex.set_defaults(handler=_cmd_reindex)

    doctor = subparsers.add_parser("doctor", help="check or repair the local store")
    doctor.add_argument(
        "--fix",
        action="store_true",
        help="safely repair missing files, stale INDEX.md, permissions, and stale temp files",
    )
    doctor.add_argument("--json", action="store_true", help="print JSON")
    doctor.set_defaults(handler=_cmd_doctor)

    migrate = subparsers.add_parser(
        "migrate", help="plan, apply, or roll back schema migrations (dry run by default)"
    )
    migrate_mode = migrate.add_mutually_exclusive_group()
    migrate_mode.add_argument("--apply", action="store_true", help="apply pending migrations")
    migrate_mode.add_argument(
        "--rollback",
        metavar="BACKUP_DIR",
        help="restore store files from a migration backup directory",
    )
    migrate.add_argument("--json", action="store_true", help="print JSON")
    migrate.set_defaults(handler=_cmd_migrate)

    sync = subparsers.add_parser(
        "sync",
        help="safe allowlist Git sync (dry run by default; never auto-pushes)",
    )
    sync_mode = sync.add_mutually_exclusive_group()
    sync_mode.add_argument(
        "--init", action="store_true", help="initialize local Git repo with allowlist .gitignore"
    )
    sync_mode.add_argument("--status", action="store_true", help="print sync and doctor status")
    sync_mode.add_argument(
        "--commit",
        action="store_true",
        help="stage allowlisted files after doctor check and create a local commit",
    )
    sync.add_argument(
        "-m",
        "--message",
        default="chore(engramkeep): sync allowlisted memory",
        help="local commit message",
    )
    sync.add_argument("--json", action="store_true", help="print JSON")
    sync.set_defaults(handler=_cmd_sync)

    path_parser = subparsers.add_parser("path", help="print the memory directory")
    path_parser.add_argument("--local", action="store_true", help="print project .engramkeep/ path")
    path_parser.set_defaults(handler=_cmd_path)

    mcp = subparsers.add_parser("mcp", help="run the MCP stdio server")
    mcp.add_argument("--status", action="store_true", help="print server status and exit")
    mcp.add_argument(
        "--allow-write",
        action="store_true",
        help="enable write tools (remember, record_fix, supersede)",
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
        help="enable the remember and fix forms",
    )
    dashboard_parser.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="open the dashboard URL in the default browser",
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
    install.add_argument(
        "--mcp-allow-write",
        action="store_true",
        help="register MCP with --allow-write (implies --mcp)",
    )
    install.add_argument(
        "--skill",
        action="store_true",
        help="also install (or uninstall) SKILL.md into the agent skills directory",
    )
    install.add_argument("--json", action="store_true", help="print JSON")
    install.set_defaults(handler=_cmd_install)

    imp = subparsers.add_parser(
        "import",
        help="extract redacted decisions and fixes from a transcript (dry run by default)",
    )
    imp.add_argument("--file", required=True, metavar="FILE", help="path to transcript file")
    imp.add_argument(
        "--format",
        dest="fmt",
        choices=["auto", *available_formats()],
        default="auto",
        help="transcript format (default: auto)",
    )
    imp.add_argument("--project", default="imported", help="target project (default: imported)")
    imp.add_argument("--limit", type=int, default=20, help="maximum candidates (default: 20)")
    imp_mode = imp.add_mutually_exclusive_group()
    imp_mode.add_argument(
        "--apply",
        action="store_true",
        help="write extracted decisions and fixes into the store",
    )
    imp_mode.add_argument(
        "--interactive",
        action="store_true",
        help="review and approve each candidate interactively [y/n/a/q]",
    )
    imp.add_argument("--json", action="store_true", help="print JSON")
    imp.set_defaults(handler=_cmd_import)

    comp = subparsers.add_parser("completion", help="print shell completion script")
    comp.add_argument("shell", choices=["bash", "zsh", "fish", "powershell"], help="target shell")
    comp.set_defaults(handler=_cmd_completion)

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
