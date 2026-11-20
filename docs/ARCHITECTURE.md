# Architecture

Engramkeep is a small Python package with zero required runtime dependencies.
The core is deliberately boring: files, a path jail, atomic writes, a SHA-256
hash-chained audit log, deterministic BM25 + bilingual search, and a
budget-bounded context packer. The security properties come from what is *not*
in the core.

## Design principles

1. **Local-first.** No account, server, telemetry, or network call in the core.
2. **Files over a database.** Every card is readable, diffable Markdown.
3. **Small auditable surface.** Standard library only for required runtime code
   (at-rest encryption is strictly opt-in via `engramkeep[crypto]`).
4. **Safe by default.** Path jail, atomic writes, redaction, and explicit
   confirmation for destructive operations.
5. **Memory is data, not instructions.** Cards, context bundles, and
   troubleshooting entries are untrusted input to agents.
6. **No hidden automation.** No automatic Git push, cloud upload, junctions,
   daemons, or auto-start entries.

## Package layout

| Module | Responsibility |
| --- | --- |
| `config.py` | Resolve global home (CLI, `--local`, `ENGRAMKEEP_HOME`, platform default) and discover project-local `.engramkeep/` stores. |
| `paths.py` | Validate path components, enforce the path jail (`safe_join()`), atomic writes, advisory file locks, private directories, symlink/junction checks. |
| `redact.py` | Best-effort secret, modern SaaS/AI token, email, and user-path username redaction, plus ReDoS-guarded `<home>/redact.json` custom rules. |
| `audit.py` | Tamper-evident SHA-256 hash chain sealing and verification for `audit.log`. |
| `models.py` | Card dataclass, frontmatter parser/renderer, decision lifecycle (`append_decision`, `supersede_decision`, `remove_decision`, `merge_cards`, `add_tags`, `remove_tags`). |
| `concepts.py` | Turkish-safe case folding (`tr_lower`), agglutinative prefix matching, and deterministic bilingual EN/TR concept expansion. |
| `search.py` | Field-weighted BM25, quoted phrase matching, Turkish prefix/softening matching, multi-tag AND filtering, bilingual expansion bonus, snippets. |
| `context.py` | Budget-bounded context packer (`pack_context`) generating a single untrusted-data-framed Markdown block (`engramkeep context`, MCP `engramkeep_context`). |
| `store.py` | Store lifecycle, cards, merge, index, activity log (`recent --since`), hash-chained audit trail, trash/restore/purge, deduplicated fixes, `doctor --fix` (including duplicate title checks), and `LayeredStore`. |
| `troubleshoot.py` | Troubleshooting registry: parse/render `TROUBLESHOOTING.md`, BM25 + phrase + bilingual search, deduplication keys. |
| `adapters/` | Modular read-only transcript adapters (`claude-jsonl`, `cursor`, `opencode`, `codex`, `gemini`, `text`) with question filtering and sequence-based error-fix pairing. |
| `importer.py` | Consent-based transcript importer (`--discover` read-only metadata discovery, dry-run default, `--apply`, `--interactive` `[y/n/a/q]`). |
| `migrations.py` | Schema migration framework (`engramkeep migrate`) with automatic backups, legacy `audit.log` sealing, jail-checked rollback, and stray-file cleanup. |
| `sync.py` | Safe allowlist local Git sync (`engramkeep sync`): doctor-gated commits, tracked deletion staging (`git rm --cached`), never runs `git add -A` or `git push`. |
| `crypto.py` | Optional at-rest AEAD encryption (`AES-256-GCM` + `Scrypt`, lazy `cryptography` import via `engramkeep[crypto]`) with backup snapshots and dry-run default. |
| `cli.py` | argparse CLI with consistent `--local` support and shell completion (`bash`, `zsh`, `fish`, `powershell`). |
| `installer.py` | Backed-up, managed-block installer for ten agents with 9 MCP targets (including Codex TOML), shared-target dedup, `.venv`-safe command resolution, `--mcp-command`, `--skill`, and `--restore`. |
| `mcp_server.py` | MCP stdio server: multi-version protocol negotiation, `LayeredStore` resolution, read/write tools (incl. `engramkeep_context`), resources (`engramkeep://...`), and prompts. |
| `dashboard.py` & `dashboard_assets/` | Hardened loopback dashboard with modular HTML/JS/CSS/SVG assets, `LayeredStore` badges, active store path, Doctor/Audit status, Trash + Restore, Supersede, Remember, Fixes, export, and strict CSP. |
| `data/SKILL.md` | Bundled portable skill file installed by `engramkeep install --skill`. |
| `py.typed` | PEP 561 type information marker. |

## Data flow

```text
CLI arguments
    |
    v
config.resolve_home() [+ find_project_store()]  ->  Store / LayeredStore
    |
    v
normalize_project_id() -> safe_join(projects_dir, "<id>.md")
    |
    v
redact_text(extra_rules=redact.json) -> models.*() -> paths.atomic_write_text()
    |
    +--> INDEX.md regenerated from valid cards
    +--> RECENT_ACTIVITY.md appended
    +--> audit.log appended (metadata + SHA-256 hash chain)
```

## Storage layout

```text
<home>/   (or <repo>/.engramkeep/ for project-scoped layered memory)
├── meta.json              # schema version and creation/migration metadata
├── redact.json            # optional user-defined ReDoS-guarded redaction rules
├── INDEX.md               # generated project index
├── RECENT_ACTIVITY.md     # human-readable activity bullets
├── TROUBLESHOOTING.md     # deduplicated resolved errors and verified fixes
├── audit.log              # append-only SHA-256 hash-chained JSONL metadata
├── projects/
│   └── <project-id>.md    # Decisions + optional ADR Superseded history
├── trash/                 # recoverable cards moved by `forget`, restored by `restore`
└── backups/
    ├── installer/         # installer snapshots + manifest.json (`install --restore`)
    ├── doctor/            # backups created by `doctor --fix`
    ├── migrations/        # rollback snapshots created by `migrate --apply`
    └── crypto/            # pre-encryption/decryption backups
```

### Audit format

Each line is a JSON object linked to the previous line via `prev_hash` and
sealed with `hash` (SHA-256 over canonical JSON without `hash`). Decision text
is never copied into the audit log. `engramkeep doctor` verifies the full chain
and flags any modified, deleted, or injected line as `tampered`.

## Invariants

- Every user-controlled filename goes through `safe_join()`.
- Every card and generated file is written through `atomic_write_text()`.
- `append_text()` rejects symlinks and non-regular files.
- `scan_cards()` rejects symlinks and non-regular files.
- Cards, superseded decisions, fixes, and imported candidates are redacted
  (built-in + user-path + `<home>/redact.json`) before write.
- Destructive commands (`forget`, `trash --purge`) require `--yes`.
- `engramkeep sync` never runs `git push` or `git add -A`, stages only allowlisted
  paths and deletions, and refuses to commit unless `doctor` passes.
- `engramkeep migrate --rollback` only accepts backup directories inside
  `<home>/backups/migrations/` and removes stray files created mid-migration.
- MCP uses stdio only, negotiates supported protocol versions, uses `is_link_or_junction()`
  on resources, is read-only by default, and exposes no forget tool.
- The dashboard binds to `127.0.0.1`, requires a per-session token, validates
  `Host` and `Origin`, renders content via pure `textContent` DOM nodes (zero
  `innerHTML`), and mutates only via POST with `--allow-write` and `confirm: true`.
