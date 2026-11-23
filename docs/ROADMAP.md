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

## 1.2.0 - Precision, Context Packing, and Release Integrity (released)

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
  - CLI exit codes reference (`docs/EXIT_CODES.md`) and bilingual README EN/TR sync.

## 1.2.1 - Maintenance, Security Parity, and Bilingual Docs (released)

- [x] Updated `SECURITY.md` supported versions (`1.2.x`), cleaned `docs/GOOD_FIRST_ISSUES.md`, and enforced `CHANGELOG.md` + `SECURITY.md` version parity in `scripts/check_repo_hygiene.py`.
- [x] Added Turkish translations for short docs (`docs/COMPATIBILITY.tr.md`, `docs/PRIVACY.tr.md`).
- [x] Stored Scrypt `kdf_params` in encrypted envelopes with bounded validation and backwards-compatible decryption, and clarified partial encryption + plaintext backup boundaries in CLI and docs.
- [x] Enforced non-negative `--limit` validation for `search` and `fixes`, expanded the no-match benchmark control (`3/4`), added no-trailing-newline installer coverage, sped up dashboard test teardown, and added Python 3.14 support.

## 1.2.2 - Audit Hardening (released)

- [x] Remediated F-01 through F-05 security audit findings across `sync.py`, `redact.py`, `installer.py`, and `crypto.py` (hook-disabled Git sync, ReDoS guard, restore target containment, per-file AEAD context AAD, and automatic plaintext crypto backup pruning with `--keep-plaintext-backup`).

## 1.2.3 - Crash/DoS Guards, Encrypted Store Lock, and Data-Safety Hardening (current)

- [x] Locked encrypted stores against accidental read/write corruption (`Store.is_encrypted()` / `require_unencrypted()`, `doctor` error reporting, non-interactive `isatty()` check, staged all-or-nothing crypto transforms, and 256 MiB Scrypt `n*r` memory cap).
- [x] Fixed `sync.py` `lstrip("./")` allowlist bypass / `.gitignore` handling and added `core.quotepath=false`.
- [x] Fixed `_EMAIL` $O(n^2)$ ReDoS, `{,n}` ReDoS guard bypass, literal custom replacement safety, chunked >256 KiB custom redaction, pre-redaction importer line cap, and spaced Windows username masking.
- [x] Guarded MCP stdio and dashboard JSON decoders against `RecursionError`, `ValueError`, and lone-surrogate `UnicodeEncodeError`.
- [x] Hardened data-safety paths: `migrate --rollback` moves stray cards to `trash/`, `restore --force` archives overwritten cards to `trash/`, `restore --file` verifies project ownership, `installer` records & verifies content `backup_sha256` with line-anchored marker validation, `recent --since` validates real calendar dates, `normalize_tag` transliterates Turkish characters, `store.py` uses `is_link_or_junction()` everywhere, `audit.py` refuses corrupted chain tails, and CI runs real `cryptography` tests on Python 3.12.

## Future considerations

- Additional community-requested transcript adapters and language concept packs (opt-in, zero runtime deps).
- Richer card export formats (ADR bundle / static HTML snapshot).

## Non-goals

- A hosted service, vector database, or chat application.
- Automatic transcript scraping or silent background sync / auto-push.
- Storing secrets or regulated personal data.
