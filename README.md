# Engramkeep

[![CI](https://github.com/strangervibe/engramkeep/actions/workflows/ci.yml/badge.svg)](https://github.com/strangervibe/engramkeep/actions/workflows/ci.yml)
[![Coverage: 85%](https://img.shields.io/badge/Coverage-85%25-brightgreen.svg)](docs/BENCHMARK.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Dependencies: 0](https://img.shields.io/badge/Dependencies-0%20(stdlib)-brightgreen.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-JSON--RPC%202.0-purple.svg)](#mcp)

**Local-first, Markdown-native memory for AI coding agents.**

Engramkeep gives every agent you use — Codex, Claude Code, OpenCode, Cursor,
Windsurf, Gemini CLI, Antigravity, or anything that can read `AGENTS.md` — the
same persistent, human-readable project memory. It runs on the Python standard
library alone.

> **Status: 0.5.0 alpha.** The store, CLI, MCP server, dashboard,
> troubleshooting registry, bilingual search, and the backed-up agent
> installer work. Cloud sync, transcript adapters, and schema migrations are
> still ahead. See [docs/ROADMAP.md](docs/ROADMAP.md).

[Turkish README](README.tr.md)

---

![Engramkeep dashboard](https://raw.githubusercontent.com/strangervibe/engramkeep/main/assets/dashboard.png)

<p align="center">
  <img src="https://raw.githubusercontent.com/strangervibe/engramkeep/main/assets/demo.gif" alt="Engramkeep demo: projects, search, cards, activity, and doctor" width="720">
</p>

---

## Why Engramkeep?

- **Local-first.** No account, no telemetry, no server. Your memory stays on your machine.
- **Markdown-native.** Every card is a plain Markdown file you can read, diff, back up, and edit.
- **Agent-agnostic.** A canonical `AGENTS.md` protocol, a portable `SKILL.md`, and an MCP stdio server for clients that speak the Model Context Protocol.
- **One-command setup.** `engramkeep install --apply` wires the memory protocol into ten agents, with managed blocks, timestamped backups, and a clean uninstall.
- **Safe by default.** Path jail, atomic writes, secret redaction, and one hard rule: memory is data, not instructions.
- **Zero required dependencies.** The core runs on the Python standard library.

Engramkeep is not a vector database, a chat application, or a cloud service. It
is a small, auditable memory layer that keeps project decisions in files you
own.

---

## What works in 0.5.0

| Area | Status |
| --- | --- |
| Markdown store + generated index | Working |
| CLI: `init`, `remember`, `search`, `show`, `list`, `recent`, `forget`, `export`, `reindex`, `doctor` | Working |
| CLI: `fix` (record a solved problem), `fixes` (search solved problems) | Working |
| Secret redaction before write | Working |
| Path traversal protection + atomic writes | Working |
| Tests + CI on Linux, macOS, and Windows | 203 passing tests, 85% coverage |
| MCP stdio server | Working; read-only by default, writes opt-in |
| Web dashboard | Working; loopback + token, writes opt-in |
| Troubleshooting registry (`TROUBLESHOOTING.md`) | Working; redacted, atomic, untrusted data |
| Bilingual (EN/TR) search expansion | Working; deterministic, word-boundary matched |
| Agent installer | Working; managed blocks, backups, uninstall |
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

A complete synthetic store lives in [`examples/demo-brain/`](examples/demo-brain).
It is generated from checked-in JSON sources by
`python scripts/build_demo_brain.py`; no real project data is included.

---

## Quick start

```bash
pipx install engramkeep     # or: pip install engramkeep
engramkeep init
engramkeep remember example-project "Use SQLite for local storage" --tag database
engramkeep search sqlite
engramkeep show example-project
```

From a source checkout:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
engramkeep init
```

Without installing the package:

```bash
# Windows
set PYTHONPATH=src
python -m engramkeep init

# macOS / Linux
PYTHONPATH=src python -m engramkeep init
```

Try the demo store before touching your own memory:

```bash
engramkeep --home examples/demo-brain search "docker arm64"
engramkeep --home examples/demo-brain fixes "database is locked"
engramkeep --home examples/demo-brain dashboard
```

---

## Install the memory protocol into your agents

The installer writes a small managed block into your agent instruction files.
It is a **dry run by default**: nothing changes until you pass `--apply`.

```bash
engramkeep install --list                 # supported agents
engramkeep install --agent opencode       # show the plan (dry run)
engramkeep install --agent opencode --apply
engramkeep install --agent opencode --apply --mcp
engramkeep install --agent all --apply    # every supported agent
engramkeep install --agent opencode --uninstall
```

What it does:

| Behavior | Detail |
| --- | --- |
| Managed blocks | Text is wrapped in `<!-- engramkeep:begin -->` … `<!-- engramkeep:end -->`; re-running updates only that block |
| Backups | Every modified file is copied to a timestamped `.bak` next to it, and the path is recorded in `manifest.json` |
| Scopes | `--scope auto` (default; global when documented, otherwise project) or `--scope project --project-dir PATH` |
| MCP registration | Opt-in with `--mcp`; automatic for Claude Code, OpenCode, and Cursor, skipped with a printed reason elsewhere |
| Uninstall | `--uninstall` removes only the managed block and leaves the rest of the file intact |
| Dry run | Prints `would-create`, `would-update`, or `would-remove` for every target |
| No overwrites | Refuses to edit files it cannot parse safely; never deletes user content |

Supported agents: **OpenCode, Claude Code, OpenAI Codex, Cursor, Windsurf,
Gemini CLI, Antigravity, GitHub Copilot, Cline, and Roo Code.** `engramkeep
install --list` prints the exact target paths for the current platform.

---

## What gets remembered

By default:

| Platform | Location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Engramkeep` |
| macOS | `~/Library/Application Support/Engramkeep` |
| Linux | `$XDG_DATA_HOME/engramkeep` or `~/.local/share/engramkeep` |

Override it with the `ENGRAMKEEP_HOME` environment variable or the global
`--home` flag:

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

Every agent eventually hits the same build failure twice. Engramkeep keeps a
local `TROUBLESHOOTING.md` so a solved error is recorded once and recalled
forever:

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

Entries are redacted before write, the file is rewritten atomically, and agents
are instructed to treat entries as **untrusted data** — never as instructions
to execute.

### How well does recall work?

The repository includes a reproducible benchmark over a synthetic corpus of 15
error/fix pairs and 45 independently written queries (English and Turkish):

| Metric | Result |
| --- | --- |
| Top-1 accuracy | 43/45 (95.6%) |
| Top-3 recall | 45/45 (100%) |
| Turkish query → English entry, top-1 | 15/15 (100%) |
| Mean reciprocal rank | 0.978 |
| Query latency p50 / p95 | ~4 ms / ~9 ms |

Scoring is lexical with a small bilingual concept bonus: no embeddings, no
network calls, nothing to download. Two of the three no-match controls return
nothing; the third is reported honestly in [docs/BENCHMARK.md](docs/BENCHMARK.md)
rather than hidden.

Reproduce:

```bash
python scripts/benchmark_fix_registry.py --output docs/BENCHMARK.md
```

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
| `engramkeep install [--list] [--agent NAME] [--apply] [--uninstall] [--scope auto\|global\|project] [--mcp]` | Plan or apply agent integration |
| `engramkeep mcp [--status] [--allow-write]` | Run the MCP stdio server, or print its status |
| `engramkeep dashboard [--status] [--port PORT] [--allow-write]` | Run the local dashboard, or print its status |

---

## Using Engramkeep with agents

Engramkeep is designed around two portable files:

1. **`AGENTS.md`** — the cross-agent instruction format.
2. **`SKILL.md`** — the portable skill format used by OpenCode, Claude Code, and compatible agents.

The repository ships:

- [`skills/engramkeep/SKILL.md`](skills/engramkeep/SKILL.md)
- [`templates/agents/AGENTS.md`](templates/agents/AGENTS.md)
- [`templates/rules/`](templates/rules/) for Claude Code, Cursor, Windsurf, and OpenCode

`engramkeep install --agent <name> --apply` does this for you, or you can copy
the templates manually:

| Agent | Typical target |
| --- | --- |
| OpenCode | `~/.config/opencode/AGENTS.md` and `~/.config/opencode/skills/engramkeep/SKILL.md` |
| Claude Code | `~/.claude/CLAUDE.md` and `~/.claude/skills/engramkeep/SKILL.md` |
| Codex | `~/.codex/AGENTS.md` or a project `AGENTS.md` |
| Cursor | `.cursor/rules/engramkeep.mdc` or `AGENTS.md` |
| Windsurf | `.windsurf/rules/engramkeep.md` or `AGENTS.md` |
| Gemini CLI / Antigravity | `GEMINI.md` or `AGENTS.md` |
| Any MCP client | `engramkeep mcp` over stdio |

### MCP

Start the server with:

```bash
engramkeep mcp
```

It uses newline-delimited JSON-RPC 2.0 over stdio and protocol version
`2025-11-25`. A typical client configuration looks like:

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

The default tool set is read-only: `engramkeep_search`, `engramkeep_show`,
`engramkeep_list`, `engramkeep_recent`, `engramkeep_doctor`, and
`engramkeep_fixes`. To also expose the write tools `engramkeep_remember` and
`engramkeep_record_fix`, start the server with `--allow-write`:

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

There is no MCP forget tool. Use the CLI and confirm destructive actions
explicitly. Run `engramkeep mcp --status` to print the transport, protocol
version, and write mode.

### Dashboard

Start the local dashboard with:

```bash
engramkeep dashboard
```

It binds to `127.0.0.1` and prints a URL with a per-session token in the
fragment. The token is never embedded in the HTML; the browser keeps it in
`sessionStorage` and sends it in the `X-Engramkeep-Token` header.

The dashboard is read-only by default. To enable the remember form, start it
with:

```bash
engramkeep dashboard --allow-write
```

Writes are POST-only and require `confirm: true`. There is no forget button.
Use `--port 0` to pick a free port, and run `engramkeep dashboard --status` for
machine-readable security details.

---

## Comparison with alternatives: Why Engramkeep?

Different projects approach agent memory from different angles. Here is how Engramkeep compares to common patterns and alternatives:

| Dimension | **Engramkeep** | [basic-memory](https://github.com/basicbase/basic-memory) | [memsearch](https://github.com/zilliztech/memsearch) | [Mem0](https://github.com/mem0ai/mem0) | Manual files ([brain.md](https://gist.github.com/) / EverOS) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Storage format** | Plain Markdown files on local disk | JSON / SQLite via MCP | Vector store (Milvus / Chroma) | Managed cloud or local vector DB | Static prompt / notes files |
| **Runtime dependencies** | **0** (Python standard library only) | Minimal Node / Python | Embeddings, vector libraries, daemon | API keys or embedding pipeline | None (text editor) |
| **Search mechanism** | BM25-style lexical + recency + EN/TR stemmer | Basic key/value & entity lookup | Semantic dense vector embeddings | Vector / graph semantic recall | Agent grep or full context stuffing |
| **Audit & Versioning** | Native `git diff`, open in any editor | Opaque database or schema | Binary vector index | Hosted dashboard or DB rows | Full `git diff` |
| **Security & Redaction** | Built-in secret scrubber (`[REDACTED]`) & path jail | Application level | None built-in | Cloud provider policy | Manual diligence |
| **Fix Registry** | Built-in cross-agent troubleshooting catalog | No | No | No | Freeform notes |
| **Agent Installer** | Single command for 10 agents (`--apply` + backups) | Manual config | Custom integration scripts | Client SDK integration | Manual copy-pasting |
| **Primary focus** | Durable project memory & actionable fixes | Minimal MCP memory layer | Fuzzy semantic document search | Conversational user profile graphs | Simple single-agent rule prompt |

### Objective differences

- **vs. [basic-memory](https://github.com/basicbase/basic-memory):** `basic-memory` provides a clean, minimal MCP memory service. Engramkeep operates as both an MCP server and a full standalone CLI with zero dependencies, adding bilingual query expansion (EN/TR), a dedicated troubleshooting/fix registry, automated path-jail isolation, secret sanitization, and automated multi-agent configuration injection with backup rollbacks.
- **vs. [memsearch](https://github.com/zilliztech/memsearch) & Vector DBs:** `memsearch` excels at fuzzy semantic recall across large unstructured corpora using dense vector embeddings. However, vector databases require heavy embedding model runtimes, background services, and introduce non-deterministic retrieval. Engramkeep intentionally trades fuzzy semantic matching for zero dependencies, instant lexical queries, complete offline auditability, and deterministic `git diff` tracking.
- **vs. [Mem0](https://github.com/mem0ai/mem0):** Mem0 is tailored for dynamic, personalized user conversational memory and multi-tenant cloud applications. Engramkeep is explicitly local-first and project-centric: no cloud accounts, no API tokens sent to third-party endpoints, and every piece of memory remains a human-readable file in your repository.
- **vs. Manual single-file prompts ([brain.md](https://gist.github.com/) / EverOS-style rule files):** Plain Markdown rule files are portable and transparent. However, as projects grow, single files suffer from token context bloat, accidental API key commits, and conflicting manual edits across multiple AI tools. Engramkeep structures memory into organized topics, strips credentials before writing, provides fast CLI indexing, and keeps configurations synced across 10+ coding agents.

Pick Engramkeep when you want small, auditable, portable memory that lives with your code — not a complex RAG pipeline or hosted cloud service.

---

## Security and privacy

- **Local-only by default.** The core makes no network calls and collects no telemetry.
- **Secrets are redacted before write.** API keys, tokens, passwords, JWTs, and private keys are replaced with `[REDACTED]`.
- **Path jail.** Project names are resolved through `safe_join()` and cannot escape the memory directory.
- **Atomic writes.** Cards and generated files are written via a temporary file and `os.replace()`.
- **Memory is untrusted data.** Agents must never execute commands or follow instructions found inside a memory card or a troubleshooting entry.
- **Installer safety.** Dry run by default, managed blocks only, timestamped backups, `manifest.json`, and a reversible uninstall.
- **No automatic Git push, cloud upload, junction, or background daemon.** Those features are intentionally excluded.
- **MCP is local and read-only by default.** Stdio transport, no network listener, no forget tool, write tools only with `--allow-write`.
- **The dashboard is loopback-only and token-protected.** `127.0.0.1`, per-session token, strict CSP, text-only rendering, writes only with `--allow-write` plus explicit confirmation.

Read [docs/PRIVACY.md](docs/PRIVACY.md) and
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) before deploying Engramkeep in a
sensitive environment.

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
│   ├── installer.py       # backed-up, managed-block agent installer
│   └── adapters/          # future transcript adapters
├── assets/                # dashboard.png, demo.gif
├── examples/
│   ├── brain/             # minimal valid store
│   ├── demo-brain/        # generated synthetic store
│   ├── demo-cards.json
│   └── fix-registry/      # benchmark corpus
├── scripts/
│   ├── build_demo_brain.py
│   └── benchmark_fix_registry.py
├── skills/engramkeep/SKILL.md
├── templates/
├── tests/                 # 203 tests
├── docs/
└── .github/
```

---

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), follow
the [Code of Conduct](CODE_OF_CONDUCT.md), and report security issues through
[SECURITY.md](SECURITY.md). Good first tasks are listed in
[docs/GOOD_FIRST_ISSUES.md](docs/GOOD_FIRST_ISSUES.md).

## License

MIT. See [LICENSE](LICENSE).

Engramkeep is not affiliated with Google, Anthropic, OpenAI, Anysphere,
Cognition, or any other agent vendor. See [TRADEMARKS.md](TRADEMARKS.md).
