# Compatibility

Engramkeep is portable by file format. The 0.5.0 installer can write the
managed block for you, but every agent file it touches is backed up and
reversible; manual template copying still works.

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

| Agent | Installer id | Portable file | Typical target |
| --- | --- | --- | --- |
| OpenCode | `opencode` | `AGENTS.md`, `SKILL.md` | `~/.config/opencode/AGENTS.md`, skills directory |
| Claude Code | `claude-code` | `CLAUDE.md`, `SKILL.md` | `~/.claude/CLAUDE.md`, skills directory |
| OpenAI Codex | `codex` | `AGENTS.md` | `~/.codex/AGENTS.md` or project `AGENTS.md` |
| Cursor | `cursor` | `.mdc` rule | `.cursor/rules/engramkeep.mdc` |
| Windsurf | `windsurf` | Markdown rule | `.windsurf/rules/engramkeep.md` |
| Gemini CLI | `gemini-cli` | `GEMINI.md` | `~/.gemini/GEMINI.md` |
| Antigravity | `antigravity` | `GEMINI.md`, `AGENTS.md` | `~/.gemini/GEMINI.md` |
| GitHub Copilot | `copilot` | repository instructions | `.github/copilot-instructions.md` |
| Cline | `cline` | `.clinerules` | project root |
| Roo Code | `roo` | `.roorules` | project root |
| Any MCP client | n/a | MCP stdio | `engramkeep mcp` |

These paths are conventions, not guarantees. Agent vendors can change them.
`engramkeep install --list` prints the current assumptions, and a dry run shows
every target before anything is written.

## Installer behavior

- Dry run by default; `--apply` writes and `--uninstall` removes.
- Managed blocks are delimited by `<!-- engramkeep:begin -->` and
  `<!-- engramkeep:end -->`; re-running updates only that block.
- Existing files are backed up with a timestamp and recorded in
  `manifest.json` under `<home>/backups/installer/`.
- `--scope auto` picks the global target when the agent documents one,
  otherwise the project target. `--scope project --project-dir PATH` forces a
  project scope.
- `--mcp` also registers the MCP server. It is supported for Claude Code,
  OpenCode, and Cursor; other agents are reported as skipped.
- Files that cannot be parsed safely are never edited.

## What "portable" means

- The same Markdown cards are readable by every agent that can run a shell.
- The same `AGENTS.md` and `SKILL.md` text can be copied into different tools.
- No agent-specific database or binary format is used.
- Engramkeep does not claim to be natively integrated with every agent.

## MCP

The MCP stdio server is available since 0.2.0 and gained the fixes tools in 0.4.0.
It uses:

- stdio transport,
- newline-delimited JSON-RPC 2.0 framing,
- protocol version 2025-11-25,
- read-only tools by default.

Read-only tools are `engramkeep_search`, `engramkeep_show`,
`engramkeep_list`, `engramkeep_recent`, `engramkeep_doctor`, and
`engramkeep_fixes`. The `engramkeep_remember` and `engramkeep_record_fix`
write tools are exposed only when the server is started with `--allow-write`.
There is no MCP forget tool.

The server does not use the legacy `Content-Length` framing and does not open a
TCP listener. Start it with `engramkeep mcp`; print its status with
`engramkeep mcp --status`.

## Dashboard

The local dashboard is available since 0.3.0. It uses:

- a loopback bind to `127.0.0.1`,
- a per-session token delivered in the URL fragment and sent in the
  `X-Engramkeep-Token` header,
- a strict Content-Security-Policy and text-only card rendering,
- a read-only API by default.

Start it with `engramkeep dashboard`. The remember form requires
`--allow-write`, and every write is POST-only with `confirm: true`. The
dashboard sets no cookies and exposes no CORS headers. There is no forget
button.

## Known limitations

- Project ids are ASCII slugs. Non-ASCII names are transliterated or rejected.
- There is no multi-process write lock. Avoid concurrent writers on the same
  store.
- There is no encryption at rest. Use full-disk encryption if needed.
- There is no cloud or Git sync. Back up the directory yourself.
- Search is keyword-based; it is not semantic or vector search.
- The audit log is not cryptographically tamper-evident.
- Malformed cards are skipped by search/list and reported by `doctor`.
