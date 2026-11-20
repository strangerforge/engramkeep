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
from .context import DEFAULT_MAX_CHARS, pack_context
from .crypto import decrypt_store, encrypt_store, resolve_passphrase
from .errors import EngramkeepError, InstallerError, StoreError
from .importer import discover_transcripts, import_transcript
from .installer import (
    available_agents,
    format_plan,
    install_agents,
    plan_installation,
    restore_installer_backup,
)
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
    "merge",
    "context",
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
    "encrypt",
    "decrypt",
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


def _resolve_project_home(args: argparse.Namespace, global_home: Path) -> Path | None:
    explicit_project = getattr(args, "project_store", None)
    no_local = getattr(args, "no_local", False)
    if explicit_project:
        resolved = Path(explicit_project).expanduser().resolve()
        return None if resolved == global_home else resolved
    if not no_local and args.home is None and not os.environ.get(ENV_HOME):
        discovered = find_project_store()
        if discovered is not None and discovered != global_home:
            return discovered
    return None


def _open_store(args: argparse.Namespace, *, create: bool = False) -> Store:
    store = Store(_resolve_target_home(args))
    if create and not store.is_initialized():
        store.init()
    if not store.is_initialized():
        raise StoreError(f"no Engramkeep store at {store.home}; run 'engramkeep init' first")
    return store


def _open_layered(args: argparse.Namespace) -> LayeredStore:
    global_home = resolve_home(args.home)
    global_store = Store(global_home)
    project_home = _resolve_project_home(args, global_home)
    project_store = Store(project_home) if project_home is not None else None
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


def _cmd_merge(args: argparse.Namespace) -> int:
    store = _open_store(args)
    result = store.merge(args.source, args.target, delete_source=args.delete_source)
    if args.json:
        _print_json(result.to_dict())
    else:
        print(
            f"Merged {result.source_id} into {result.target.id}: "
            f"+{result.decisions_added} decision(s), +{result.superseded_added} superseded, "
            f"+{len(result.tags_added)} tag(s)."
        )
        if result.source_trashed:
            print(f"Moved source card {result.source_id} to trash.")
    return 0


def _cmd_context(args: argparse.Namespace) -> int:
    layered = _open_layered(args)
    source: Store | LayeredStore = layered if layered.is_layered else _open_store(args)
    bundle = pack_context(
        source,
        args.query,
        project=args.project,
        tags=args.tag or None,
        max_chars=args.max_chars,
        max_cards=args.max_cards,
        max_fixes=args.max_fixes,
    )
    if args.json:
        _print_json(bundle.to_dict())
    else:
        print(bundle.markdown, end="")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    tags: list[str] = [item for item in (args.tag or []) if item]
    layered = _open_layered(args)
    if layered.is_layered:
        hits, errors = layered.search(args.query, tags=tags or None, limit=args.limit)
    else:
        store = _open_store(args)
        scan = store.scan_cards()
        errors = list(scan.errors)
        hits = search_cards(scan.cards, args.query, tags=tags or None, limit=args.limit)
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
    lines = store.recent(args.limit, since=args.since)
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
    store = Store(_resolve_target_home(args))
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
    home = _resolve_target_home(args)
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


def _cmd_crypto(args: argparse.Namespace, *, operation: str) -> int:
    home = _resolve_target_home(args)
    passphrase = (
        resolve_passphrase(prompt=True, confirm=(operation == "encrypt")) if args.apply else ""
    )
    result = (
        encrypt_store(home, passphrase, apply=args.apply)
        if operation == "encrypt"
        else decrypt_store(home, passphrase, apply=args.apply)
    )
    if args.json:
        _print_json(result.to_dict())
        return 0
    print(
        f"{operation.capitalize()} ({result.mode}): {len(result.files_processed)} file(s), "
        f"{len(result.files_skipped)} skipped"
    )
    for rel in result.files_processed:
        print(f"  - {rel}")
    if result.mode == "dry-run":
        print("Dry run: no files were modified. Pass --apply to execute.")
    elif result.backup_dir:
        print(f"Backup: {result.backup_dir}")
        if operation == "encrypt":
            print("Note: Prune the unencrypted backup directory once you verify decryption.")
    if operation == "encrypt":
        print(
            "Scope: encrypts projects/*.md and TROUBLESHOOTING.md only; "
            "INDEX.md, RECENT_ACTIVITY.md, audit.log, and meta.json remain plaintext."
        )
    return 0


def _cmd_encrypt(args: argparse.Namespace) -> int:
    return _cmd_crypto(args, operation="encrypt")


def _cmd_decrypt(args: argparse.Namespace) -> int:
    return _cmd_crypto(args, operation="decrypt")


def _cmd_path(args: argparse.Namespace) -> int:
    print(_resolve_target_home(args))
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    project_home = _resolve_project_home(args, home)
    if args.status:
        info = mcp_server.status(home, project_home=project_home)
        if args.json:
            _print_json(info)
            return 0
        print(f"MCP: {info['status']}")
        print(f"Home: {info['home']}")
        if "project_home" in info:
            print(f"Project home: {info['project_home']}")
        print(f"Transport: {info['transport']}")
        print(f"Protocol: {info['protocol_version']} (supported: {info['supported_versions']})")
        print(f"Capabilities: {info['capabilities']}")
        print(f"Writes: {info['writes']}")
        return 0
    if project_home is not None:
        return mcp_server.serve(home, allow_write=args.allow_write, project_home=project_home)
    return mcp_server.serve(home, allow_write=args.allow_write)


def _cmd_dashboard(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    project_home = _resolve_project_home(args, home)
    if args.status:
        info = dashboard.status(home, project_home=project_home)
        if args.json:
            _print_json(info)
            return 0
        print(f"Dashboard: {info['status']}")
        print(f"Home: {info['home']}")
        if "project_home" in info:
            print(f"Project home: {info['project_home']}")
        print(f"Bind: {info['bind']}")
        print(f"Auth: {info['auth']}")
        print(f"Writes: {info['writes']}")
        print(f"CSP: {info['csp']}")
        return 0
    kwargs: dict[str, object] = {"port": args.port, "allow_write": args.allow_write}
    if args.open_browser:
        kwargs["open_browser"] = True
    if project_home is not None:
        kwargs["project_home"] = project_home
    return dashboard.serve(home, **kwargs)  # type: ignore[arg-type]


def _cmd_install(args: argparse.Namespace) -> int:
    if args.list_agents:
        for name in available_agents():
            print(format_plan(plan_installation(name)))
            print()
        return 0

    backup_root = resolve_home(args.home) / "backups" / "installer"
    if args.restore:
        try:
            result = restore_installer_backup(backup_root, args.restore, dry_run=not args.apply)
        except InstallerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.json:
            _print_json(result.to_dict())
            return 0
        for op in result.operations:
            print(f"{op.action}: {op.target} (from: {op.backup})")
        if result.mode == "dry-run":
            print("Dry run: no files were modified. Pass --apply to restore.")
        return 0

    if not args.agent:
        print("error: --agent is required (or use --list / --restore)", file=sys.stderr)
        return 2

    project_dir = Path(args.project_dir).expanduser().resolve() if args.project_dir else Path.cwd()
    try:
        result = install_agents(
            args.agent,
            user_home=Path.home(),
            project_dir=project_dir,
            backup_root=backup_root,
            scope=args.scope,
            mcp=args.mcp or args.mcp_allow_write,
            mcp_allow_write=args.mcp_allow_write,
            mcp_command=args.mcp_command,
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
    if args.discover:
        found = discover_transcripts(limit=args.limit)
        if args.json:
            _print_json([item.to_dict() for item in found])
            return 0
        if not found:
            print("No agent transcripts discovered in standard directories.")
            return 0
        print(f"Discovered {len(found)} transcript(s) (read-only metadata; nothing read yet):")
        for item in found:
            print(f"  [{item.agent}] {item.modified} ({item.size_bytes} B) {item.path}")
        print("Run `engramkeep import --file <PATH>` to preview candidates.")
        return 0

    if not args.file:
        print("error: --file is required (or use --discover)", file=sys.stderr)
        return 2

    store = Store(_resolve_target_home(args))
    source_path = Path(args.file).expanduser()
    # Keep stdout clean JSON when --interactive and --json are combined.
    prompt_out = (lambda msg: print(msg, file=sys.stderr)) if args.json else print
    result = import_transcript(
        store,
        source_path,
        fmt=args.fmt,
        project=args.project,
        limit=args.limit,
        apply=args.apply,
        interactive=args.interactive,
        output_fn=prompt_out if args.interactive else None,
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


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer value: {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def _add_local_arg(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--local",
        action="store_true",
        help="target project-scoped .engramkeep/ store in the current directory",
    )


def _add_layer_args(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--project-store", metavar="DIR", help="explicit project .engramkeep/ dir"
    )
    subparser.add_argument(
        "--no-local", action="store_true", help="ignore project .engramkeep/ layer"
    )


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
    _add_local_arg(init_parser)
    init_parser.set_defaults(handler=_cmd_init)

    remember = subparsers.add_parser("remember", help="record a durable decision")
    remember.add_argument("project", help="project name or id")
    remember.add_argument("decision", help="decision text")
    remember.add_argument("--tag", action="append", default=[], help="tag to add (repeatable)")
    _add_local_arg(remember)
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
    _add_local_arg(supersede)
    supersede.add_argument("--json", action="store_true", help="print JSON")
    supersede.set_defaults(handler=_cmd_supersede)

    untag = subparsers.add_parser("untag", help="remove tag(s) from a project card")
    untag.add_argument("project", help="project name or id")
    untag.add_argument("--tag", action="append", required=True, help="tag to remove (repeatable)")
    _add_local_arg(untag)
    untag.add_argument("--json", action="store_true", help="print JSON")
    untag.set_defaults(handler=_cmd_untag)

    merge = subparsers.add_parser("merge", help="merge one project card into another")
    merge.add_argument("source", help="source project id")
    merge.add_argument("target", help="target project id")
    merge.add_argument(
        "--delete-source",
        action="store_true",
        help="move the source card to trash after merging",
    )
    _add_local_arg(merge)
    merge.add_argument("--json", action="store_true", help="print JSON")
    merge.set_defaults(handler=_cmd_merge)

    context = subparsers.add_parser(
        "context", help="pack relevant cards and fixes into a character-budgeted Markdown block"
    )
    context.add_argument(
        "query", nargs="?", default="", help="topic, keywords, or project id (optional)"
    )
    context.add_argument("--project", help="optional priority project id")
    context.add_argument("--tag", action="append", default=[], help="tag filter (repeatable, AND)")
    context.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help=f"maximum character budget (default: {DEFAULT_MAX_CHARS})",
    )
    context.add_argument("--max-cards", type=int, default=5, help="maximum cards (default: 5)")
    context.add_argument("--max-fixes", type=int, default=5, help="maximum fixes (default: 5)")
    _add_layer_args(context)
    context.add_argument("--json", action="store_true", help="print JSON")
    context.set_defaults(handler=_cmd_context)

    search = subparsers.add_parser("search", help="search cards")
    search.add_argument("query", help="search terms")
    search.add_argument(
        "--tag", action="append", default=[], help="filter by tag (repeatable, AND)"
    )
    search.add_argument(
        "--limit",
        type=_non_negative_int,
        default=10,
        help="maximum results (integer >= 0, default: 10)",
    )
    _add_layer_args(search)
    search.add_argument("--json", action="store_true", help="print JSON")
    search.set_defaults(handler=_cmd_search)

    show = subparsers.add_parser("show", help="print one card")
    show.add_argument("project", help="project name or id")
    _add_layer_args(show)
    show.add_argument("--json", action="store_true", help="print JSON")
    show.set_defaults(handler=_cmd_show)

    list_parser = subparsers.add_parser("list", help="list projects")
    _add_layer_args(list_parser)
    list_parser.add_argument("--json", action="store_true", help="print JSON")
    list_parser.set_defaults(handler=_cmd_list)

    recent = subparsers.add_parser("recent", help="show recent activity")
    recent.add_argument("--limit", type=int, default=10, help="maximum entries (default: 10)")
    recent.add_argument("--since", metavar="YYYY-MM-DD", help="only entries on or after date")
    _add_local_arg(recent)
    recent.add_argument("--json", action="store_true", help="print JSON")
    recent.set_defaults(handler=_cmd_recent)

    forget = subparsers.add_parser("forget", help="move a card to trash or remove one decision")
    forget.add_argument("project", help="project name or id")
    forget.add_argument(
        "--decision",
        help="remove only one matching decision bullet instead of trashing the entire card",
    )
    forget.add_argument("--yes", action="store_true", help="confirm the action")
    _add_local_arg(forget)
    forget.set_defaults(handler=_cmd_forget)

    trash = subparsers.add_parser("trash", help="list or purge trashed cards")
    trash.add_argument("--project", help="filter by project id")
    trash.add_argument("--purge", action="store_true", help="permanently delete trashed cards")
    trash.add_argument("--yes", action="store_true", help="confirm --purge")
    _add_local_arg(trash)
    trash.add_argument("--json", action="store_true", help="print JSON")
    trash.set_defaults(handler=_cmd_trash)

    restore = subparsers.add_parser("restore", help="restore a card from trash")
    restore.add_argument("project", help="project name or id")
    restore.add_argument("--file", metavar="NAME", help="specific trash filename to restore")
    restore.add_argument("--force", action="store_true", help="overwrite an existing active card")
    _add_local_arg(restore)
    restore.add_argument("--json", action="store_true", help="print JSON")
    restore.set_defaults(handler=_cmd_restore)

    fix = subparsers.add_parser("fix", help="record a resolved error and its verified fix")
    fix.add_argument("error", help="the error or problem that was resolved")
    fix.add_argument("--solution", required=True, help="the verified fix that worked")
    fix.add_argument("--project", help="project name (default: General)")
    fix.add_argument("--workspace", help="workspace path or label")
    _add_local_arg(fix)
    fix.add_argument("--json", action="store_true", help="print JSON")
    fix.set_defaults(handler=_cmd_fix)

    fixes = subparsers.add_parser("fixes", help="search the troubleshooting registry")
    fixes.add_argument(
        "query",
        nargs="?",
        default=None,
        help="search terms (run without it to list the newest fixes)",
    )
    fixes.add_argument(
        "--limit",
        type=_non_negative_int,
        default=10,
        help="maximum results (integer >= 0, default: 10)",
    )
    _add_layer_args(fixes)
    fixes.add_argument("--json", action="store_true", help="print JSON")
    fixes.set_defaults(handler=_cmd_fixes)

    export = subparsers.add_parser("export", help="export all cards as JSON")
    export.add_argument("--output", metavar="FILE", help="write to FILE instead of stdout")
    export.add_argument("--force", action="store_true", help="overwrite an existing output file")
    _add_local_arg(export)
    export.set_defaults(handler=_cmd_export)

    reindex = subparsers.add_parser("reindex", help="regenerate INDEX.md")
    _add_local_arg(reindex)
    reindex.set_defaults(handler=_cmd_reindex)

    doctor = subparsers.add_parser("doctor", help="check or repair the local store")
    doctor.add_argument(
        "--fix",
        action="store_true",
        help="safely repair missing files, stale INDEX.md, permissions, and stale temp files",
    )
    _add_local_arg(doctor)
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
    _add_local_arg(migrate)
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
    _add_local_arg(sync)
    sync.add_argument("--json", action="store_true", help="print JSON")
    sync.set_defaults(handler=_cmd_sync)

    enc = subparsers.add_parser(
        "encrypt",
        help="encrypt store cards & fixes at rest (requires engramkeep[crypto]; dry run default)",
    )
    enc.add_argument("--apply", action="store_true", help="encrypt files with backup")
    _add_local_arg(enc)
    enc.add_argument("--json", action="store_true", help="print JSON")
    enc.set_defaults(handler=_cmd_encrypt)

    dec = subparsers.add_parser(
        "decrypt",
        help="decrypt encrypted store files back to Markdown (dry run default)",
    )
    dec.add_argument("--apply", action="store_true", help="decrypt files with backup")
    _add_local_arg(dec)
    dec.add_argument("--json", action="store_true", help="print JSON")
    dec.set_defaults(handler=_cmd_decrypt)

    path_parser = subparsers.add_parser("path", help="print the memory directory")
    _add_local_arg(path_parser)
    path_parser.set_defaults(handler=_cmd_path)

    mcp = subparsers.add_parser("mcp", help="run the MCP stdio server")
    mcp.add_argument("--status", action="store_true", help="print server status and exit")
    mcp.add_argument(
        "--allow-write",
        action="store_true",
        help="enable write tools (remember, record_fix, supersede)",
    )
    _add_layer_args(mcp)
    mcp.add_argument("--json", action="store_true", help="print JSON (with --status)")
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
        help="enable remember, supersede, restore, and fix forms",
    )
    dashboard_parser.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="open the dashboard URL in the default browser",
    )
    _add_layer_args(dashboard_parser)
    dashboard_parser.add_argument("--json", action="store_true", help="print JSON (with --status)")
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
        "--restore",
        metavar="RUN_ID",
        help="restore files from a backup run under <home>/backups/installer/<RUN_ID>",
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
        "--dry-run",
        action="store_true",
        help="preview changes without writing (default)",
    )
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
        help="also register the MCP server in the agent config",
    )
    install.add_argument(
        "--mcp-allow-write",
        action="store_true",
        help="register MCP with --allow-write (implies --mcp)",
    )
    install.add_argument(
        "--mcp-command",
        metavar="CMD",
        help="override the MCP command executable (default: portable engramkeep or sys.executable)",
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
        help="discover or extract redacted candidates from transcripts (dry run by default)",
    )
    imp.add_argument("--file", metavar="FILE", help="path to transcript file")
    imp.add_argument(
        "--discover",
        action="store_true",
        help="list recent agent transcripts in standard directories without reading contents",
    )
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
    _add_local_arg(imp)
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
