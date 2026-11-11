# Roadmap

This roadmap is a direction, not a promise. Security gates apply to every
release.

## 0.1.0 - Alpha (released)

- Local Markdown store with cards, index, recent activity, and audit log.
- CLI: `init`, `remember`, `search`, `show`, `list`, `recent`, `forget`,
  `export`, `reindex`, `doctor`, `path`.
- Path jail, atomic writes, private directories, and symlink rejection.
- Best-effort secret and email redaction.
- Portable `AGENTS.md` and `SKILL.md` templates.
- Dry-run agent installer.
- Tests, CI skeleton, repository hygiene check.
- MCP and dashboard were stubs.

## 0.2.0 - MCP (released)

- [x] MCP stdio server with newline-delimited JSON-RPC 2.0 and protocol
  version 2025-11-25.
- [x] Read-only tools: `engramkeep_search`, `engramkeep_show`,
  `engramkeep_list`, `engramkeep_recent`, and `engramkeep_doctor`.
- [x] Opt-in `engramkeep_remember` write tool behind `--allow-write`.
- [x] MCP protocol and tool tests, including framing, size limits, batch
  handling, error responses, and write gating.

Security gate: threat model updated, no network listener, no write tool by
default, no path escape, no command execution from card content.

## 0.3.0 - Dashboard (released)

- [x] Hardened dashboard: loopback bind, per-session token, strict CSP, path
  jail, text-only rendering, POST-only mutations.
- [x] Read-only dashboard API for projects, cards, search, recent activity,
  and doctor output.
- [x] Opt-in remember form behind `--allow-write` with explicit confirmation.
- [x] Dashboard tests for token auth, Host and Origin checks, CSP, path
  traversal, body limits, and write gating.

Security gate: no unauthenticated reads or writes, no HTML injection, no path
escape, and no mutation on GET.

## 0.4.0 - Troubleshooting registry and bilingual search (released)

- [x] `TROUBLESHOOTING.md` registry with redaction and atomic rewrite.
- [x] `engramkeep fix` / `engramkeep fixes` CLI commands.
- [x] MCP tools `engramkeep_fixes` (read) and `engramkeep_record_fix` (write,
  `--allow-write` only).
- [x] Bilingual EN/TR concept expansion in `search` and `fixes`.
- [x] `export` includes fixes; `doctor` audits the registry.

Security gate: registry entries are untrusted data, redacted before write, and
symlinked registry files are refused.

## 0.5.0 - Installer, demo, and benchmark (released; current 0.5.3)

- [x] Installer that previews, backs up, and updates a managed block for ten
  agents, with `--apply`, `--uninstall`, and `--scope project`.
- [x] Timestamped backups and `manifest.json` for every installer change.
- [x] Automatic MCP registration for Claude Code, OpenCode, and Cursor.
- [x] Dashboard surfacing for the troubleshooting registry (read-only).
- [x] Deterministic synthetic demo store and reproducible fix-recall benchmark.
- [x] CI coverage threshold and demo/benchmark regression tests.
- [ ] Schema migration framework. (Moved to 0.6.0.)

Security gate: every installer change is backed up and reversible; the
installer never edits a file it cannot parse safely.

## 0.6.0 - Import, search, and migrations

- Schema migration framework.
- Read-only transcript adapters with explicit consent and documented paths
  (Claude Code JSONL first). Imported text is treated as untrusted.
- Optional encryption at rest with a user-supplied key.
- Better search: field weighting, phrase support, and deterministic snippets.
- Import dry-run that shows exactly what would be written.

Security gate: imported text is treated as untrusted, encrypted stores never
write plaintext to disk, and key handling is documented.

## 0.7.0 - Optional sync design

- Design-only work for encrypted, user-controlled sync.
- Allowlist-based Git integration that never runs `git add -A`.
- Conflict handling with explicit user review.
- No automatic push and no cloud account requirement.

Security gate: independent review of the sync design before implementation.

## 1.0.0 - Stable

- Stable CLI and storage schema with migrations.
- Documented compatibility policy.
- Security audit and remediation.
- Reproducible builds and signed release artifacts where practical.
- Complete English and Turkish documentation.

## Non-goals

- A hosted service, vector database, or chat application.
- Automatic transcript scraping from every agent.
- Storing secrets or regulated personal data.
- Silent background sync.
- Claiming native integration that has not been tested.
