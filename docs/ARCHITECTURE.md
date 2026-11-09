# Architecture

Engramkeep is a small Python package with zero required runtime dependencies.
The core is deliberately boring: files, a path jail, atomic writes, and a
keyword search. The security properties come from what is *not* in the core.

## Design principles

1. **Local-first.** No account, server, telemetry, or network call in the core.
2. **Files over a database.** Every card is readable, diffable Markdown.
3. **Small auditable surface.** Standard library only for runtime code.
4. **Safe by default.** Path jail, atomic writes, redaction, and explicit
   confirmation for destructive operations.
5. **Memory is data, not instructions.** Cards are untrusted input to agents.
6. **No hidden automation.** No Git push, cloud upload, junctions, daemons, or
   auto-start entries.

## Package layout

| Module | Responsibility |
| --- | --- |
| `config.py` | Resolve the memory home from CLI, environment, or platform default. |
| `paths.py` | Validate path components, enforce the path jail, write atomically, create private directories. |
| `redact.py` | Best-effort secret and email redaction before storage. |
| `models.py` | Card dataclass, frontmatter parser/renderer, decision and tag mutation. |
| `concepts.py` | Deterministic bilingual EN/TR concept expansion used by search and the registry. |
| `search.py` | Keyword scoring, tag filtering, bilingual expansion bonus, snippets. |
| `store.py` | Store lifecycle, cards, index, activity log, audit trail, trash, doctor, troubleshooting registry. |
| `troubleshoot.py` | Troubleshooting registry: parse/render `TROUBLESHOOTING.md`, scoring, untrusted-data handling. |
| `cli.py` | argparse command-line interface. |
| `installer.py` | Dry-run agent integration planner. |
| `mcp_server.py` | MCP stdio server: newline-delimited JSON-RPC, read-only tools, opt-in write tools. |
| `dashboard.py` | Hardened loopback dashboard: token auth, strict CSP, path jail, read-only API, opt-in POST remember. |
| `adapters/` | Reserved for future read-only transcript adapters. |

## Data flow

```text
CLI arguments
    |
    v
config.resolve_home()  ->  Store(home)
    |
    v
normalize_project_id() -> safe_join(projects_dir, "<id>.md")
    |
    v
redact_text() -> models.append_decision() -> paths.atomic_write_text()
    |
    +--> INDEX.md regenerated from valid cards
    +--> RECENT_ACTIVITY.md appended
    +--> audit.log appended (metadata only)
```

A read follows the same path in reverse. `scan_cards()` rejects symlinks,
validates each filename through `safe_join()`, and reports malformed files
instead of guessing.

## Storage layout

```text
<home>/
├── meta.json              # schema version and creation time
├── INDEX.md               # generated project index
├── RECENT_ACTIVITY.md     # human-readable activity bullets
├── TROUBLESHOOTING.md     # resolved errors and verified fixes
├── audit.log              # append-only JSON Lines metadata
├── projects/
│   └── <project-id>.md
└── trash/
    └── <project-id>-<timestamp>.md
```

### `meta.json`

```json
{
  "schema_version": 1,
  "created": "2026-01-01T00:00:00Z"
}
```

A newer schema is rejected. An older schema is rejected in 0.3.0 because no
migration is implemented yet.

### Card format

```markdown
---
id: example-project
title: Example Project
created: 2026-01-01T00:00:00Z
updated: 2026-01-02T12:00:00Z
tags: demo, docs
---

# Example Project

## Decisions

- Use SQLite for local storage.
```

The filename is authoritative. If frontmatter `id` disagrees with the file
stem, the file stem wins.

### Index format

`INDEX.md` is generated with three columns: project link, tags, updated date.
The table is intentionally simple so it can be read by humans and agents
without a YAML or database dependency.

### Audit format

Each line is a JSON object with a timestamp, action, optional project, and
metadata. Decision text is not copied into the audit log. Example:

```json
{"action": "remember", "added": true, "created": true, "project": "example-project", "tags": ["demo"], "ts": "2026-01-02T12:00:00Z"}
```

## Invariants

- Every user-controlled filename goes through `safe_join()`.
- Every card and generated file is written through `atomic_write_text()`.
- `append_text()` rejects symlinks.
- `scan_cards()` rejects symlinks and non-regular files.
- Cards are redacted before write.
- The store, CLI, and MCP modules import no networking or subprocess modules.
  Only `dashboard.py` binds a loopback listener.
- Destructive commands require `--yes`.
- The installer never writes files in 0.3.0.
- MCP uses stdio only, is read-only by default, and has no forget tool.
- The MCP write tool exists only when the server is started with
  `--allow-write`.
- The dashboard binds to `127.0.0.1`, requires a per-session token, and
  validates the Host header and any Origin on writes.
- The dashboard renders card content as text and never mutates on GET.
- Dashboard writes require `--allow-write` and `confirm: true`.

## Extension points

Future features must preserve the invariants above:

- **MCP server (0.2.0, implemented):** stdio, newline-delimited JSON,
  protocol version 2025-11-25, no network listener, read-only by default, and
  an explicit `--allow-write` opt-in for the remember tool.
- **Dashboard (0.3.0, implemented):** bind to `127.0.0.1`, require a
  per-session token, enforce a path jail, use strict CSP, render card content
  as text, and keep mutations POST-only behind `--allow-write`.
- **Installer (0.4.0):** preview by default, back up before changing agent
  configuration, update a managed block, never overwrite unrelated content.
- **Adapters (0.5.0):** explicit consent, documented source paths, read-only,
  no upload.

## Testing strategy

- Unit tests for config resolution, path validation, redaction, card parsing,
  and search.
- Store tests use `tmp_path` and never touch the real user home.
- CLI tests set `ENGRAMKEEP_HOME` and capture output.
- MCP tests drive `serve()` with in-memory byte streams and cover protocol
  negotiation, tool schemas, write gating, framing, size limits, and errors.
- Dashboard tests start a real server on an ephemeral loopback port and use
  `http.client` to cover token auth, Host and Origin checks, CSP, path
  traversal, body limits, read-only defaults, and confirmation.
- A repository hygiene test checks for personal paths, secrets, required
  files, and unsafe artifacts.
- CI runs on Windows, Linux, and macOS across supported Python versions.
