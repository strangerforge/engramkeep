# Engramkeep

[![CI](https://github.com/engramkeep/engramkeep/actions/workflows/ci.yml/badge.svg)](https://github.com/engramkeep/engramkeep/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Dependencies: 0](https://img.shields.io/badge/Dependencies-0%20(stdlib)-brightgreen.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-JSON--RPC%202.0-purple.svg)](#mcp)

**Local-first, Markdown-native memory for AI coding agents.**

Engramkeep gives every agent you use — Codex, Claude Code, OpenCode, Cursor, Windsurf, Gemini CLI, Antigravity, or anything that can read `AGENTS.md` — the same persistent, human-readable project memory. It runs on the Python standard library alone.

> **Status: 0.4.0 alpha.** The core store, CLI, path safety, secret redaction, tests, MCP stdio server, hardened local dashboard, a troubleshooting registry, and bilingual (EN/TR) search work. The agent installer is still a dry-run planner in this release. See [docs/ROADMAP.md](docs/ROADMAP.md).

[Turkish README](README.tr.md)

---

## Why Engramkeep?

- **Local-first.** No account, no telemetry, no server. Your memory stays on your machine.
- **Markdown-native.** Every card is a plain Markdown file you can read, diff, back up, and edit.
- **Agent-agnostic.** A canonical `AGENTS.md` protocol, a portable `SKILL.md`, and an MCP stdio server for clients that speak the Model Context Protocol.
- **Safe by default.** Path jail, atomic writes, secret redaction, and one hard rule: memory is data, not instructions.
- **Zero required dependencies.** The core runs on the Python standard library.

Engramkeep is not a vector database, a chat application, or a cloud service. It is a small, auditable memory layer that keeps project decisions in files you own.

---

## What works in 0.4.0

| Area | Status |
| --- | --- |
| Markdown store + generated index | Working |
| CLI: `init`, `remember`, `search`, `show`, `list`, `recent`, `forget`, `export`, `reindex`, `doctor` | Working |
| CLI: `fix` (record a solved problem), `fixes` (search solved problems) | Working |
| Secret redaction before write | Working |
| Path traversal protection + atomic writes | Working |
| Tests + CI | Working |
| MCP stdio server | Working; read-only by default, writes opt-in |
| Web dashboard | Working; loopback + token, writes opt-in |
| Troubleshooting registry (`TROUBLESHOOTING.md`) | Working; redacted, atomic, untrusted data |
| Bilingual (EN/TR) search expansion | Working; deterministic, small bonus, word-boundary matched |
| Agent installer | Dry-run planner only |
| Cloud/Git sync | Not included |

---

## Demo

```console
$ engramkeep init
Initialized Engramkeep at …/Engramkeep
  created INDEX.md, RECENT_ACTIVITY.md, audit.log, TROUBLESHOOTING.md, projects/, trash/

$ engramkeep remember api-gateway "Use SQLite for local storage" --tag database
Remembered in api-gateway: Api Gateway

$ engramkeep fix "Keystore signature mismatch on release build" \
      --solution "Enable v2 signing in gradle signingConfigs" \
      --project mobile-app
Recorded fix for mobile-app: Keystore signature mismatch on release build

$ engramkeep fixes mobil        # Turkish query, English entry
mobile-app (2026-11-09)
  workspace: General
  problem: Keystore signature mismatch on release build
  fix: Enable v2 signing in gradle signingConfigs

$ engramkeep search "database"
Api Gateway (api-gateway)
  tags: database
  ...Decisions - Use SQLite for local storage
```

---

## Quick start

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"

engramkeep init
engramkeep remember example-project "Use SQLite for local storage" --tag database
engramkeep search sqlite
engramkeep show example-project
```

Without installing the package, run it from the repository:

```bash
# Windows
set PYTHONPATH=src
python -m engramkeep init

# macOS / Linux
PYTHONPATH=src python -m engramkeep init
```

---

## Where memory lives

By default:

| Platform | Location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Engramkeep` |
| macOS | `~/Library/Application Support/Engramkeep` |
| Linux | `$XDG_DATA_HOME/engramkeep` or `~/.local/share/engramkeep` |

Override it with the `ENGRAMKEEP_HOME` environment variable or the global `--home` flag:

```bash
engramkeep --home ./my-brain init
```

Layout:

```text
<home>/
├── INDEX.md              # generated project index
├── RECENT_ACTIVITY.md    # human-readable activity log
├── TROUBLESHOOTING.md    # resolved errors and verified fixes
├── audit.log             # append-only JSONL audit trail
├── projects/
│   └── example-project.md
└── trash/                # recoverable cards moved by `forget`
```

A project card is Markdown with a small frontmatter block:

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

---

## The troubleshooting registry

Every agent eventually hits the same build failure twice. Engramkeep keeps a local `TROUBLESHOOTING.md` so a solved error is recorded once and recalled forever:

```bash
# Record a resolved problem
engramkeep fix "Keystore signature mismatch on release build" \
    --solution "Enable v2 signing in gradle signingConfigs" \
    --project mobile-app

# Recall fixes
engramkeep fixes keystore
engramkeep fixes mobil      # bilingual: TR query, EN entry
engramkeep fixes            # newest first
engramkeep fixes --json
```

Entries are redacted before write, the file is rewritten atomically, and agents are instructed to treat entries as **untrusted data** — never as instructions to execute.

## Bilingual search (EN/TR)

Search expands common engineering concepts across English and Turkish deterministically (`concepts.py`): `mobil` finds cards about `capacitor`/`apk`/`flutter`, `veritabanı` finds `postgresql`/`sqlite`, `arama` finds `index`/`fts`. Expansion terms carry a small capped bonus and use word-boundary matching, so literal matches always win and one-letter terms never match inside unrelated words.

---

## Commands

| Command | Purpose |
| --- | --- |
| `engramkeep init` | Create the memory directory and starter files |
| `engramkeep remember <project> "<decision>" [--tag TAG]` | Record a durable decision |
| `engramkeep search "<query>" [--tag TAG] [--json]` | Search titles, tags, and card bodies (bilingual) |
| `engramkeep show <project>` | Print a project card |
| `engramkeep list` | List known projects |
| `engramkeep recent` | Print recent activity |
| `engramkeep forget <project> --yes` | Move a card to `trash/` |
| `engramkeep fix "<error>" --solution "<fix>" [--project NAME] [--workspace PATH]` | Record a resolved problem |
| `engramkeep fixes [query] [--limit N] [--json]` | Search the troubleshooting registry |
| `engramkeep export [--output FILE]` | Export all cards and fixes as JSON |
| `engramkeep reindex` | Regenerate `INDEX.md` |
| `engramkeep doctor [--json]` | Check the local store, including the registry |
| `engramkeep path` | Print the active memory directory |
| `engramkeep mcp [--status] [--allow-write]` | Run the MCP stdio server, or print its status |
| `engramkeep dashboard [--status] [--port PORT] [--allow-write]` | Run the local dashboard, or print its status |
| `engramkeep install --agent <name>` | Show the planned agent integration (dry run) |

---

## Using Engramkeep with agents

Engramkeep is designed around two portable files:

1. **`AGENTS.md`** — the cross-agent instruction format.
2. **`SKILL.md`** — the portable skill format used by OpenCode, Claude Code, and compatible agents.

The repository ships:

- [`skills/engramkeep/SKILL.md`](skills/engramkeep/SKILL.md)
- [`templates/agents/AGENTS.md`](templates/agents/AGENTS.md)
- [`templates/rules/`](templates/rules/) for Claude Code, Cursor, Windsurf, and OpenCode

Manual installation examples:

| Agent | Typical target |
| --- | --- |
| OpenCode | `~/.config/opencode/AGENTS.md` and `~/.config/opencode/skills/engramkeep/SKILL.md` |
| Claude Code | `~/.claude/CLAUDE.md` and `~/.claude/skills/engramkeep/SKILL.md` |
| Codex | `~/.codex/AGENTS.md` or a project `AGENTS.md` |
| Cursor | `.cursor/rules/engramkeep.mdc` or `AGENTS.md` |
| Windsurf | `.windsurf/rules/engramkeep.md` or `AGENTS.md` |
| Gemini CLI / Antigravity | `GEMINI.md` or `AGENTS.md` |
| Any MCP client | `engramkeep mcp` over stdio |

The installer is a **dry-run planner** in 0.4.0. It prints target paths but does not modify agent configuration. Automatic, backed-up, managed-block installation is planned for a later release.

### MCP

Start the server with:

```bash
engramkeep mcp
```

It uses newline-delimited JSON-RPC 2.0 over stdio and protocol version `2025-11-25`. A typical client configuration looks like:

```json
{
  "mcpServers": {
    "engramkeep": {
      "command": "engramkeep",
      "args": ["mcp"]
    }
  }
}
```

The default tool set is read-only: `engramkeep_search`, `engramkeep_show`, `engramkeep_list`, `engramkeep_recent`, `engramkeep_doctor`, and `engramkeep_fixes`. To also expose the write tools `engramkeep_remember` and `engramkeep_record_fix`, start the server with `--allow-write`:

```json
{
  "mcpServers": {
    "engramkeep": {
      "command": "engramkeep",
      "args": ["mcp", "--allow-write"]
    }
  }
}
```

There is no MCP forget tool. Use the CLI and confirm destructive actions explicitly. Run `engramkeep mcp --status` to print the transport, protocol version, and write mode.

### Dashboard

Start the local dashboard with:

```bash
engramkeep dashboard
```

It binds to `127.0.0.1` and prints a URL with a per-session token in the fragment. The token is never embedded in the HTML; the browser keeps it in `sessionStorage` and sends it in the `X-Engramkeep-Token` header.

The dashboard is read-only by default. To enable the remember form, start it with:

```bash
engramkeep dashboard --allow-write
```

Writes are POST-only and require `confirm: true`. There is no forget button. Use `--port 0` to pick a free port, and run `engramkeep dashboard --status` for machine-readable security details.

---

## Why not Mem0, Basic Memory, or a vector database?

| | Engramkeep | Cloud memory services | Vector DB stacks |
| --- | --- | --- | --- |
| Storage | Your files, plain Markdown | Their servers | Local/remote DB |
| Dependencies | **0** (stdlib) | Account + API | Embeddings + DB |
| Recall model | Keyword + recency + EN/TR concept expansion | LLM/embeddings | Semantic similarity |
| Auditability | `git diff`, open in any editor | Limited | Opaque vectors |
| Safety model | Memory is data, never instructions | Varies | Varies |
| Best for | Durable project decisions, fix registry | Teams/hosted use | Large corpora |

Pick Engramkeep when you want small, auditable, portable memory — not a RAG pipeline.

---

## Security and privacy

- **Local-only by default.** The core makes no network calls and collects no telemetry.
- **Secrets are redacted before write.** API keys, tokens, passwords, JWTs, and private keys are replaced with `[REDACTED]`.
- **Path jail.** Project names are resolved through `safe_join()` and cannot escape the memory directory.
- **Atomic writes.** Cards and generated files are written via a temporary file and `os.replace()`.
- **Memory is untrusted data.** Agents must never execute commands or follow instructions found inside a memory card or a troubleshooting entry.
- **No automatic Git push, cloud upload, junction, or background daemon.** Those features are intentionally excluded.
- **MCP is local and read-only by default.** Stdio transport, no network listener, no forget tool, write tools only with `--allow-write`.
- **The dashboard is loopback-only and token-protected.** `127.0.0.1`, per-session token, strict CSP, text-only rendering, writes only with `--allow-write` plus explicit confirmation.

Read [docs/PRIVACY.md](docs/PRIVACY.md) and [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) before deploying Engramkeep in a sensitive environment.

---

## Non-goals

- Replacing Git, an issue tracker, or a documentation site.
- Storing secrets, credentials, or regulated personal data.
- Automatic transcript scraping from every agent. (Read-only, consent-based transcript adapters are on the [roadmap](docs/ROADMAP.md).)
- A hosted service or a vector database.
- Perfect recall. Memory is only as good as what you record.

---

## Project structure

```text
engramkeep/
├── AGENTS.md
├── README.md
├── README.tr.md
├── LICENSE
├── pyproject.toml
├── src/engramkeep/
│   ├── cli.py
│   ├── config.py
│   ├── concepts.py        # bilingual EN/TR concept expansion
│   ├── models.py
│   ├── paths.py
│   ├── redact.py
│   ├── search.py
│   ├── store.py
│   ├── troubleshoot.py    # troubleshooting registry (TROUBLESHOOTING.md)
│   ├── mcp_server.py      # MCP stdio server
│   ├── dashboard.py       # hardened local dashboard
│   ├── installer.py       # dry-run planner
│   └── adapters/          # future transcript adapters
├── skills/engramkeep/SKILL.md
├── templates/
├── examples/brain/
├── tests/
├── docs/
└── .github/
```

---

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), follow the [Code of Conduct](CODE_OF_CONDUCT.md), and report security issues through [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).

Engramkeep is not affiliated with Google, Anthropic, OpenAI, Anysphere, Cognition, or any other agent vendor. See [TRADEMARKS.md](TRADEMARKS.md).
