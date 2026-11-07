# Compatibility

Engramkeep is portable by file format, not by automatic installation. The
repository ships templates that work with common agents; the 0.2.0 installer
only prints a plan.

## Runtime

| Item | Support |
| --- | --- |
| Python | 3.10, 3.11, 3.12, 3.13 |
| Windows | Supported |
| macOS | Supported |
| Linux | Supported |
| Runtime dependencies | None |
| File encoding | UTF-8 |
| Generated line endings | LF |

CI is configured to run tests on Windows, Linux, and macOS across the Python
versions above.

## Agents

| Agent | Portable file | Typical target | Notes |
| --- | --- | --- | --- |
| OpenCode | `AGENTS.md`, `SKILL.md` | `~/.config/opencode/AGENTS.md`, `~/.config/opencode/skills/engramkeep/SKILL.md` | Copy both templates. |
| Claude Code | `CLAUDE.md`, `SKILL.md` | `~/.claude/CLAUDE.md`, `~/.claude/skills/engramkeep/SKILL.md` | Append the managed block; do not overwrite user content. |
| OpenAI Codex | `AGENTS.md` | `~/.codex/AGENTS.md` or project `AGENTS.md` | Project-level instructions are usually preferable. |
| Cursor | `.mdc` rule, `AGENTS.md` | `.cursor/rules/engramkeep.mdc` | Copy from `templates/rules/cursor.mdc`. |
| Windsurf | Markdown rule, `AGENTS.md` | `.windsurf/rules/engramkeep.md` | Copy from `templates/rules/windsurf.md`. |
| Gemini CLI | `GEMINI.md`, `AGENTS.md` | `~/.gemini/GEMINI.md` or project `AGENTS.md` | Prefer `AGENTS.md` when supported. |
| Antigravity | `GEMINI.md`, `AGENTS.md` | `~/.gemini/GEMINI.md` or project `AGENTS.md` | Verify your installed version's behavior. |
| Any MCP client | MCP stdio | `engramkeep mcp` | Read-only tools by default; `--allow-write` enables the remember tool. |

These paths are conventions, not guarantees. Agent vendors can change them.
The dry-run planner in `engramkeep install --agent <name>` prints the current
assumptions without touching the filesystem.

## What "portable" means

- The same Markdown cards are readable by every agent that can run a shell.
- The same `AGENTS.md` and `SKILL.md` text can be copied into different tools.
- No agent-specific database or binary format is used.
- Engramkeep does not claim to be natively integrated with every agent.

## MCP

The MCP stdio server is available in 0.2.0. It uses:

- stdio transport,
- newline-delimited JSON-RPC 2.0 framing,
- protocol version 2025-11-25,
- read-only tools by default.

Read-only tools are `engramkeep_search`, `engramkeep_show`,
`engramkeep_list`, `engramkeep_recent`, and `engramkeep_doctor`. The
`engramkeep_remember` write tool is exposed only when the server is started
with `--allow-write`. There is no MCP forget tool.

The server does not use the legacy `Content-Length` framing and does not open a
TCP listener. Start it with `engramkeep mcp`; print its status with
`engramkeep mcp --status`.

## Dashboard

The web dashboard is still a stub in 0.2.0. The planned implementation will
bind to loopback, require a token, enforce a path jail, and require explicit
confirmation for writes.

## Known limitations

- Project ids are ASCII slugs. Non-ASCII names are transliterated or rejected.
- There is no multi-process write lock. Avoid concurrent writers on the same
  store.
- There is no encryption at rest. Use full-disk encryption if needed.
- There is no cloud or Git sync. Back up the directory yourself.
- Search is keyword-based; it is not semantic or vector search.
- The audit log is not cryptographically tamper-evident.
- Malformed cards are skipped by search/list and reported by `doctor`.
