# Compatibility

> **English** | [Türkçe](COMPATIBILITY.tr.md)

Engramkeep 1.2.3 is portable by file format. The installer writes managed blocks,
MCP registrations, and skills into supported agent configs while backing up every
touched file with a timestamped manifest; manual template copying also works.

## Runtime

| Item | Support |
| --- | --- |
| Python | 3.10, 3.11, 3.12, 3.13, 3.14 |
| Windows | Supported |
| macOS | Supported |
| Linux | Supported |
| Required runtime dependencies | None (Python standard library only) |
| Optional extras | `engramkeep[crypto]` (`cryptography>=43.0` for `encrypt`/`decrypt`) |
| File encoding | UTF-8 |
| Generated line endings | LF |

CI runs tests on Windows, Linux, and macOS across Python 3.10–3.14.

## Agents

| Agent | Installer id | Portable file | Typical target | MCP (`--mcp`) | Skill (`--skill`) |
| --- | --- | --- | --- | --- | --- |
| OpenCode | `opencode` | `AGENTS.md`, `SKILL.md` | `~/.config/opencode/AGENTS.md` | `opencode.json` | Yes |
| Claude Code | `claude-code` | `CLAUDE.md`, `SKILL.md` | `~/.claude/CLAUDE.md` | `~/.claude.json` / `.mcp.json` | Yes |
| OpenAI Codex | `codex` | `AGENTS.md` | `~/.codex/AGENTS.md` | `~/.codex/config.toml` / `.codex/config.toml` (TOML) | Yes |
| Cursor | `cursor` | `.mdc` rule | `.cursor/rules/engramkeep.mdc` | `.cursor/mcp.json` | Yes |
| Windsurf | `windsurf` | Markdown rule | `.windsurf/rules/engramkeep.md` | `~/.codeium/windsurf/mcp_config.json` / `.windsurf/mcp.json` | Yes |
| Gemini CLI | `gemini-cli` | `GEMINI.md` | `~/.gemini/GEMINI.md` | `~/.gemini/settings.json` / `.gemini/settings.json` | Yes |
| Antigravity | `antigravity` | `GEMINI.md`, `AGENTS.md` | `~/.gemini/GEMINI.md` | `~/.gemini/antigravity/mcp_config.json` / `.gemini/mcp.json` | Yes |
| GitHub Copilot | `copilot` | repository instructions | `.github/copilot-instructions.md` | Skipped (not standardized) | Yes |
| Cline | `cline` | `.clinerules` | project root | `.cline/mcp_settings.json` | Yes |
| Roo Code | `roo` | `.roorules` | project root | `.roo/mcp.json` | Yes |
| Any MCP client | n/a | MCP stdio | `engramkeep mcp` | Native | n/a |

These paths are conventions, not guarantees. Agent vendors can change them.
`engramkeep install --list` prints the current assumptions, and a dry run
(default or `--dry-run`) shows every target before anything is written.

## Installer behavior

- Dry run by default; `--apply` writes, `--uninstall` removes managed blocks,
  and `--restore RUN_ID` restores exact pre-edit backups (`--apply` to commit).
- Managed Markdown blocks are delimited by `<!-- engramkeep:begin -->` and
  `<!-- engramkeep:end -->`; OpenAI Codex TOML MCP blocks use
  `# engramkeep:mcp:begin` and `# engramkeep:mcp:end`. Re-running updates only
  the managed block.
- When `--agent all` encounters two agents sharing the same rule file (for
  example `gemini-cli` and `antigravity` both targeting `~/.gemini/GEMINI.md`),
  the installer writes once and records the second agent as `shared`.
- Existing files are backed up with a timestamp and recorded in
  `manifest.json` under `<home>/backups/installer/`.
- `--scope auto` picks the global target when the agent documents one,
  otherwise the project target. `--scope project --project-dir PATH` forces a
  project scope.
- `--mcp` registers the MCP server across 9 agents (read-only by default; add
  `--mcp-allow-write` for opt-in writes). If `engramkeep` is on global PATH
  (outside an ephemeral virtual environment), the portable command is preferred;
  use `--mcp-command` to override explicitly.
- `--skill` installs the bundled `SKILL.md` into the agent's skills directory.
- Files that cannot be parsed safely are never edited.

## Layered memory

If an initialized `.engramkeep/` store exists in the current repository (or any
parent directory up to the repo root), read commands (`search`, `show`, `list`,
`fixes`, `context`, `mcp`, `dashboard`) automatically layer it over the global
store. Project cards take precedence over global cards with the same id. Pass
`--local` on write and maintenance commands to target `.engramkeep/` directly,
or `--no-local` / `--project-store DIR` on `mcp` and `dashboard`.

## What "portable" means

- The same Markdown cards are readable by every agent that can run a shell.
- The same `AGENTS.md` and `SKILL.md` text can be copied into different tools.
- No agent-specific database or binary format is used.
- Engramkeep does not claim to be natively integrated with every agent.

## MCP

The MCP stdio server supports:

- stdio transport,
- newline-delimited JSON-RPC 2.0 framing,
- protocol version negotiation across `2024-11-05`, `2025-03-26`,
  `2025-06-18`, and `2025-11-25`,
- read-only tools by default,
- layered project + global resolution (`--project-store DIR` / `--no-local`).

Read-only tools are `engramkeep_context`, `engramkeep_search`,
`engramkeep_show`, `engramkeep_list`, `engramkeep_recent`,
`engramkeep_doctor`, and `engramkeep_fixes`. Write tools (`engramkeep_remember`,
`engramkeep_record_fix`, `engramkeep_supersede`) are exposed only when the
server is started with `--allow-write`. There is no MCP forget tool.

MCP resources expose `engramkeep://projects/<id>`, `engramkeep://index`,
`engramkeep://troubleshooting`, and `engramkeep://recent`. MCP prompts expose
`session-start`, `post-mortem-fix`, and `decision-review`.

The server does not use the legacy `Content-Length` framing and does not open a
TCP listener. Start it with `engramkeep mcp`; print its status with
`engramkeep mcp --status [--json]`.

## Dashboard

The local dashboard uses:

- a loopback bind to `127.0.0.1`,
- a per-session token delivered in the URL fragment and sent in the
  `X-Engramkeep-Token` header,
- a strict Content-Security-Policy and text-only (`textContent`) card rendering,
- layered store awareness (showing active store path and project/global badges),
- Doctor health, SHA-256 audit chain verification, and Trash inspection,
- a read-only API by default.

Start it with `engramkeep dashboard` (or `--open` to launch the browser). The
remember, fix, supersede, and trash-restore actions require `--allow-write`, and
every write is POST-only with `confirm: true`. The dashboard sets no cookies and
exposes no CORS headers. There is no forget button.

## Sync, Audit, and Optional Encryption

- **Audit log:** `audit.log` uses a zero-dependency SHA-256 hash chain verified
  by `engramkeep doctor`.
- **Git sync:** `engramkeep sync` supports allowlisted local Git commits
  (`projects/*.md`, `INDEX.md`, `TROUBLESHOOTING.md`), including tracked card
  deletions, with a mandatory pre-commit secret check. It never runs
  `git add -A` or `git push`.
- **Optional encryption:** `engramkeep encrypt` / `engramkeep decrypt` provide
  opt-in AES-256-GCM + Scrypt at-rest encryption when `engramkeep[crypto]` is
  installed. Encrypted stores must be decrypted before normal search/read.

## Known limitations

- Project ids are ASCII slugs. Non-ASCII names are transliterated or rejected.
- Mutating store operations serialize across threads and processes via an
  advisory lock (`.engramkeep.lock`), with bounded timeout.
- Search is lexical (BM25 + phrase + EN/TR concepts + Turkish prefix matching);
  it is not semantic or vector search.
- Optional at-rest encryption encrypts `projects/*.md` and
  `TROUBLESHOOTING.md` as whole files (`INDEX.md`, `RECENT_ACTIVITY.md`,
  `audit.log`, and `meta.json` remain plaintext, and there is no encrypted
  search index); for transparent always-on encryption, prefer full-disk
  encryption.
- Malformed cards are skipped by search/list and reported by `doctor`.
