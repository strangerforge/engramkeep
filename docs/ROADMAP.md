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

## 1.0.0 - Stable (released)

- Fix deduplication, `trash` / `restore`, Turkish-safe search & prefix matching, `py.typed`, and `doctor --fix`.
- Layered project (`.engramkeep/`) + global memory search and read overlay.
- Decision lifecycle (`supersede`, `untag`, `forget --decision`).
- MCP multi-version negotiation, resources (`engramkeep://...`), prompts, and `engramkeep_supersede`.
- Expanded installer (9 MCP agents, `--mcp-allow-write`, `--skill`) and modular dashboard.
- Schema migrations (`engramkeep migrate`), SHA-256 hash-chained `audit.log`, allowlist `engramkeep sync`, multi-agent transcript adapters (`import --interactive`), and shell completion.

## 1.2.0 - Precision, Context Packing, and Release Integrity (current)

- [x] **Reliability & security hardening:**
  - Tracked allowlist deletion handling in `engramkeep sync` (fixes ghost cards after `forget`).
  - Consistent `--local` flag across all store CLI commands; `LayeredStore` support in `mcp` and `dashboard`.
  - OpenAI Codex MCP registration in TOML (`config.toml` managed block), `.venv`-safe portable MCP resolution + `--mcp-command`, shared-target deduplication (`--agent all`), and `install --restore <run>`.
  - Strict rollback containment in `migrate --rollback` + stray-file cleanup on failed migrations; `is_link_or_junction()` in MCP `resources/read`.
  - Modern AI/SaaS token redaction (`sbp_`, `gsk_`, `xai-`, `pplx-`, `re_`, `lin_api_`, `dapi`), user-path username masking (`[REDACTED_USER]`), and ReDoS-guarded custom `<home>/redact.json` rules.
  - Sealed SHA-256 audit chain in `examples/brain/audit.log` and version/`SKILL.md`/asset-budget parity checks in `check_repo_hygiene.py`.
- [x] **Daily ergonomics & dashboard v1.1:**
  - Budget-bounded context packer (`engramkeep context` CLI + `engramkeep_context` MCP tool).
  - Card consolidation (`engramkeep merge <source> <target> [--delete-source]`), multi-tag AND filtering (`search --tag a --tag b`), `recent --since YYYY-MM-DD`, and `doctor` duplicate-title warnings.
  - Transcript discovery (`engramkeep import --discover`), question filtering, sequence-based error-fix pairing, stricter `claude-jsonl` detection, and stderr prompts for `--interactive --json`.
  - Dashboard store-path & layered badges, Doctor/Audit health panel, Trash view + `POST /api/restore`, and `POST /api/supersede`.
- [x] **Optional encryption & release supply chain:**
  - Opt-in at-rest AEAD encryption (`engramkeep encrypt` / `decrypt` via optional `engramkeep[crypto]` extra).
  - Release `SHA256SUMS.txt` checksums and SLSA build provenance attestation (`actions/attest-build-provenance`).
  - CLI exit codes reference (`docs/EXIT_CODES.md`) and full EN/TR doc sync.

## Future considerations

- Additional community-requested transcript adapters and language concept packs (opt-in, zero runtime deps).
- Richer card export formats (ADR bundle / static HTML snapshot).

## Non-goals

- A hosted service, vector database, or chat application.
- Automatic transcript scraping or silent background sync / auto-push.
- Storing secrets or regulated personal data.
