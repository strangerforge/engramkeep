# Roadmap

This roadmap tracks Engramkeep's release milestones and security gates.

## 0.1.0 - Alpha (released)

- Local Markdown store, CLI, path jail, atomic writes, redaction, hygiene check.

## 0.2.0 - MCP (released)

- MCP stdio server with read-only tools and opt-in `--allow-write`.

## 0.3.0 - Dashboard (released)

- Hardened loopback-only web dashboard with per-session token and strict CSP.

## 0.4.0 - Troubleshooting registry and bilingual search (released)

- `TROUBLESHOOTING.md` registry (`fix` / `fixes`) and bilingual EN/TR concept expansion.

## 0.5.0 - Installer, demo, and benchmark (released)

- Managed-block installer for 10 agents, synthetic demo brain, and fix-recall benchmark.

## 0.6.0 - BM25 search and transcript import (released)

- Field-weighted BM25 + quoted phrase search and consent-based transcript import.

## 0.7.0 - Daily agent experience (included in 1.0.0)

- [x] Fix deduplication, `trash` / `restore` commands, Turkish-safe case folding & agglutinative prefix matching, `py.typed`, and `doctor --fix`.
- [x] Layered project (`.engramkeep/`) + global memory search and read overlay.
- [x] Decision lifecycle: `supersede` (ADR history), `untag`, and single-decision `forget --decision`.
- [x] MCP multi-version negotiation (`2024-11-05` through `2025-11-25`), MCP Resources (`engramkeep://...`), MCP Prompts, and `engramkeep_supersede`.
- [x] Expanded installer: MCP support across 9 agents, `--mcp-allow-write`, portable command selection, and `--skill`.
- [x] Modular dashboard assets, `POST /api/fixes`, `GET /api/export`, clickable tag filters, structured text-only Markdown rendering, copy/export buttons, and `--open`.

## 1.0.0 - Stable (current)

- [x] Schema migration framework (`engramkeep migrate`) with automatic backups and rollback.
- [x] Tamper-evident SHA-256 hash-chained `audit.log` verified by `engramkeep doctor`.
- [x] Safe allowlist local Git sync (`engramkeep sync`, doctor-gated, never auto-pushes or runs `git add -A`).
- [x] Modular multi-agent transcript adapters (`claude-jsonl`, `cursor`, `opencode`, `codex`, `gemini`, `text`) with natural-language extraction and `import --interactive`.
- [x] Shell completion scripts (`bash`, `zsh`, `fish`, `powershell`).
- [x] Synchronized English and Turkish documentation, threat model, and architecture docs.

## Future considerations

- Optional encryption at rest with a user-supplied key.
- Signed release provenance / SBOM artifacts.

## Non-goals

- A hosted service, vector database, or chat application.
- Automatic transcript scraping or silent background sync / auto-push.
- Storing secrets or regulated personal data.
