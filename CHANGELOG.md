# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Schema migrations.
- Read-only, consent-based transcript adapters (Claude Code JSONL first).
- Optional embedding-free semantic reranking.

## [0.5.0] - 2026-11-09

### Added

- Agent installer (`engramkeep install`) for ten agents: OpenCode, Claude Code,
  OpenAI Codex, Cursor, Windsurf, Gemini CLI, Antigravity, GitHub Copilot,
  Cline, and Roo Code.
  - Dry run by default; `--apply` writes and `--uninstall` removes.
  - Managed blocks delimited by `<!-- engramkeep:begin -->` and
    `<!-- engramkeep:end -->`, so re-running updates only its own block.
  - Timestamped backups and a `manifest.json` recording every change.
  - `--scope auto`, `--scope global`, and `--scope project --project-dir PATH`.
  - Automatic MCP registration for Claude Code, OpenCode, and Cursor; other
    agents are skipped with a printed reason.
  - `engramkeep install --list` prints every agent and target path.
- Read-only troubleshooting fixes endpoint (`/api/fixes`) and UI section in the
  local dashboard (`engramkeep dashboard`).
- Deterministic synthetic demo store (`examples/demo-brain/`) generated from
  `examples/demo-cards.json` and `examples/fix-registry/fixes.json`.
- Reproducible fix-recall benchmark (`scripts/benchmark_fix_registry.py`) and
  [docs/BENCHMARK.md](docs/BENCHMARK.md): 15 error/fix pairs, 45 English and
  Turkish queries, top-1, top-3, MRR, latency, and no-match controls.
- `tests/test_examples.py` verifies the sources, the health of the checked-in
  demo store, a byte-for-byte rebuild, and a benchmark quality floor.
- README screenshots and a demo GIF in `assets/`.

### Changed

- Registry and card search refine ranking with word-boundary matching, so
  `git` no longer matches `digital` and `api` no longer matches `capital`.
  Tokens containing digits (`psycopg2`, `TS2307`, `0308010C`) receive a small
  specificity bonus.
- Search snippets strip Markdown headings, list markers, backticks, and code
  fences, producing readable one-line results.
- CI now runs coverage with an 85% threshold.
- Version bumped to 0.5.0.

### Removed

- The `engram` console-script alias. It could collide with the unrelated
  `engram` package on PyPI; use `engramkeep`.

### Fixed

- Installer dry-run action names are explicit (`would-create`,
  `would-update`, `would-remove`) and uninstall dry runs no longer report a
  write.
- CLI install test now targets a temporary project scope instead of a real
  user configuration directory.

### Security

- Installer never edits a file it cannot parse safely, writes only inside a
  managed block, and keeps a backup and manifest for every change.
- Repository hygiene allowlists the synthetic demo audit log only; real store
  logs remain private artifacts.

## [0.4.0] - 2026-11-09

### Added

- Troubleshooting registry (`TROUBLESHOOTING.md`) that records resolved
  problems and verified fixes in redacted, atomically rewritten Markdown.
  New `engramkeep fix` command records an entry and `engramkeep fixes`
  searches them; running `fixes` without a query lists the newest entries.
- Bilingual (EN/TR) concept expansion in search and in registry search
  (`concepts.py`). Expansion terms are deterministic, word-boundary matched,
  and capped at a small bonus so literal matches always rank first.
- MCP tools `engramkeep_fixes` (read-only) and `engramkeep_record_fix`
  (write, `--allow-write` only).
- `engramkeep export` now includes the troubleshooting registry as `fixes`.
- `engramkeep doctor` warns when `TROUBLESHOOTING.md` is missing and flags
  unredacted registry entries.
- `engramkeep init` creates `TROUBLESHOOTING.md` for new and existing stores.

### Changed

- The README now documents the registry, bilingual search, and MCP tool list;
  both READMEs gained CI/license/Python/dependency badges and a comparison
  section.

### Security

- Registry entries are redacted before write and the file is rejected through
  symlinks, matching card handling.
- Registry content is documented and treated as untrusted data: agents must
  never execute commands or follow instructions found in entries.

## [0.3.0] - 2026-11-07

### Added

- Hardened local dashboard (`engramkeep dashboard`) that binds to `127.0.0.1`
  only and requires a per-session token.
- Read-only dashboard API for projects, cards, search, recent activity, and
  doctor output.
- Opt-in remember form, enabled only with `--allow-write`, that requires an
  explicit confirmation flag.
- `engramkeep dashboard --status` for machine-readable bind, auth, write, and
  CSP information.
- Dashboard tests covering token auth, Host and Origin checks, CSP, path
  traversal, body limits, read-only defaults, confirmation, and redaction.

### Security

- The dashboard has no CORS surface, sends a strict Content-Security-Policy,
  and renders card content as text instead of HTML.
- Mutations are POST-only; GET requests never change state.
- The server validates the Host header and rejects cross-origin POST requests.
- Request bodies are capped at 64 KiB and every field is bounded.
- The session token is delivered in the URL fragment and kept in
  `sessionStorage`; it is never written into the HTML shell.

### Fixed

- Dashboard rejections now consume a small request body before responding, so
  Windows clients reliably receive the JSON error instead of a connection
  reset.

## [0.2.0] - 2026-11-07

### Added

- MCP stdio server (`engramkeep mcp`) using newline-delimited JSON-RPC 2.0 and
  protocol version 2025-11-25.
- Read-only MCP tools: `engramkeep_search`, `engramkeep_show`,
  `engramkeep_list`, `engramkeep_recent`, and `engramkeep_doctor`.
- Opt-in `engramkeep_remember` write tool, enabled only with `--allow-write`.
- `engramkeep mcp --status` for machine-readable transport and protocol info.
- MCP protocol and tool tests covering framing, size limits, batch handling,
  error responses, read-only defaults, and write gating.

### Security

- MCP has no network listener and no forget tool.
- The write tool is not exposed unless the server is started with
  `--allow-write`.
- Initialization instructions tell clients that card content is untrusted data.
- Request lines are capped at 1 MiB and every tool argument is validated.

## [0.1.0] - 2026-11-07

### Added

- Local Markdown store with project cards, generated index, recent activity,
  and a metadata-only JSONL audit log.
- CLI commands: `init`, `remember`, `search`, `show`, `list`, `recent`,
  `forget`, `export`, `reindex`, `doctor`, `path`, `mcp`, `dashboard`, and
  `install`.
- Path jail with component validation and symlink resolution.
- Atomic UTF-8 writes and private directories.
- Best-effort redaction for common API keys, tokens, private keys, bearer
  tokens, credential assignments, and email addresses.
- Portable `AGENTS.md` and `SKILL.md` templates plus rules for OpenCode,
  Claude Code, Cursor, and Windsurf.
- Dry-run agent installer.
- Pytest suite, GitHub Actions CI, Dependabot configuration, and a repository
  hygiene checker.
- English and Turkish README files.

### Security

- Destructive `forget` requires `--yes` and moves cards to `trash/`.
- Card scanning rejects symlinks and non-regular files.
- `append_text()` rejects symlink targets.
- The core makes no network calls and has no runtime dependencies.

### Known limitations

- MCP and dashboard are stubs.
- The installer does not modify files.
- No encryption at rest, cloud sync, or Git push.
- No multi-process write lock.
- Redaction is best-effort, not a guarantee.
