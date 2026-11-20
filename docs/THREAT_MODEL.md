# Threat model

This document describes the security assumptions and known limitations of
Engramkeep 1.2.1. It is intentionally conservative.

## Assets

- Memory cards, generated files, backups, custom `redact.json` rules, and the
  troubleshooting registry in the local (and optional project `.engramkeep/`) store.
- The user's filesystem, Git working tree, and agent configuration.
- The integrity of the agent's behavior when it reads memory.
- The user's credentials and personal data that might appear in text.

## Trust boundaries

1. **User and agent input -> store.** Project names, decisions, tags, fixes,
   and imported transcripts are untrusted.
2. **Store -> agent context.** Card content, context bundles, fixes, and MCP
   resources are untrusted data even after storage.
3. **Local process -> filesystem.** The process runs with the user's
   privileges. A local attacker or malware with the same privileges is outside
   the model.
4. **MCP client and browser -> store.** MCP stdio server and loopback dashboard
   are read-only by default; writes require `--allow-write` (plus per-session
   token and explicit `confirm: true` in the dashboard).
5. **Agent A -> Store -> Agent B (cross-agent & layered `.engramkeep/`).**
   A repository's `.engramkeep/` store may come from another contributor; cards
   are treated as untrusted data and read-only unless the user explicitly writes
   with `--local`.

## Threats and mitigations

| Threat | Mitigation in 1.2.1 | Residual risk |
| --- | --- | --- |
| Path traversal through a project name, URI, or backup run id | `normalize_project_id()` rejects separators, drive letters, control characters, and traversal; `safe_join()` proves containment across CLI, MCP tools/resources, dashboard, trash/restore, `install --restore`, and `migrate --rollback` (confined strictly to `<home>/backups/migrations/`) | A bug in a future caller could bypass the helper |
| Symlink / NTFS junction escape | `safe_join()` resolves symlinks; `is_link_or_junction()` checks symlinks and Windows reparse points across store, trash, project discovery, MCP `resources/read`, importer & `--discover`, installer & `--restore`, migrations, crypto, and sync | OS-specific edge cases on exotic filesystems |
| Secret or username PII written to card, fix, or imported transcript | `redact_text()` runs before preview or persistence on cards, superseded decisions, fixes, and all transcript adapters; covers modern AI/SaaS keys (`sbp_`, `gsk_`, `xai-`, `pplx-`, `re_`, `lin_api_`, `dapi`), emails, and personal home paths (`[REDACTED_USER]`); optional `<home>/redact.json` custom rules validated against ReDoS nested quantifiers and empty matches; `doctor` scans cards and fixes | Encoded or novel secrets can pass through |
| Prompt injection in cards, context bundles, fixes, or MCP resources | Documentation, skill, managed rule blocks, MCP initialization instructions, `_untrusted_data_notice`, `UNTRUSTED_CONTEXT_BANNER`, and MCP resource headers state memory is untrusted data; core never executes card text | An agent can still choose to follow malicious text |
| Malicious Markdown / Dashboard XSS | Modular dashboard assets use pure `createElement` + `textContent` (zero `innerHTML`), strict CSP (`default-src 'none'`), and `X-Content-Type-Options: nosniff` | A browser bug could still bypass isolation |
| Untrusted transcript import (`importer.py` & `adapters/`) | `--discover` inspects metadata only and skips symlinks; `--file` is dry-run by default (`--apply` or `--interactive` required); 10 MiB hard file cap; symlinks/junctions refused; control/bidi chars stripped; questions filtered from natural-language decisions; secrets redacted before display or write; fixes deduplicated | Noisy natural-language false positives (mitigated by question filtering, bounded match lengths, and `--limit`) |
| Audit log tampering (`audit.py`) | Zero-dep SHA-256 hash chain (`prev_hash` + `hash`) verified by `engramkeep doctor`; any modified, deleted, or injected line fails doctor | An attacker with local write access can rewrite the entire chain from genesis |
| Destructive deletion or failed migration | `forget` moves to `trash/` (recoverable via `restore`); `trash --purge` requires `--yes`; `doctor --fix` and `migrate --apply` create timestamped backups, auto-rollback failed migrations, and clean up stray files created mid-migration | Deleting backup directories removes rollback snapshots |
| Accidental secret leak, ghost files, or force-push in Git sync (`sync.py`) | Explicit allowlist only (`meta.json`, `INDEX.md`, `TROUBLESHOOTING.md`, `projects/*.md`) plus allowlisted tracked deletions (`git rm --cached`); never runs `git add -A` or `git push`; `store.doctor()` must pass before commit; `shell=False` with resolved `git` binary | User can still manually stage excluded files or push sensitive non-redacted text |
| Unsafe installer or broken ephemeral `.venv` MCP path | Dry-run by default; managed blocks only (Markdown HTML comments + Codex TOML comments); shared targets deduplicated; refuses symlinks and unreadable JSON; ignores ephemeral `.venv` binary when resolving portable MCP command; timestamped backups + `manifest.json` + `--restore`; `--mcp` is read-only unless `--mcp-allow-write` is passed | Deleting the installer backup directory removes automatic snapshots |
| Passphrase leakage or silent corruption in optional encryption (`crypto.py`) | `cryptography` extra is strictly optional; passphrases read via `ENGRAMKEEP_PASSPHRASE` or `getpass` (never CLI args); AES-256-GCM with AAD `engramkeep-enc-v1` + Scrypt KDF (with bounded `kdf_params` stored in envelope) detects wrong keys and tampering; dry-run by default with timestamped backups under `backups/crypto/` | Partial scope: `INDEX.md`, `RECENT_ACTIVITY.md`, `audit.log`, and `meta.json` stay plaintext; forgotten passphrases cannot be recovered; unencrypted backup directories must be pruned by the user |
| Supply-chain dependency & release integrity | Zero required runtime dependencies (Python stdlib only); pinned GitHub Actions commit SHAs; `SHA256SUMS.txt` checksums and SLSA build provenance attestation (`actions/attest-build-provenance`) on releases | Dev/build tooling and optional `engramkeep[crypto]` remain external packages |
| MCP abuse or network exposure | stdio transport only; no network listener; multi-version negotiation (`2024-11-05`..`2025-11-25`); read-only by default; no forget tool; 1 MiB line cap and 32-item batch cap | A client started with `--allow-write` can add/supersede decisions and fixes |
| Dashboard CSRF / DNS rebinding / token leakage | `127.0.0.1` exclusive bind; per-session token in URL fragment -> `sessionStorage` -> `X-Engramkeep-Token`; strict Host + Origin checks; POST-only mutations (`remember`, `fixes`, `supersede`, `restore`) with `confirm: true`; no forget endpoint | Same-user local processes or browser extensions are outside the model |

## Out of scope

- A hostile multi-user host or shared account.
- Malware running as the same user.
- Physical access to an unlocked machine.
- Encrypted search indexing (optional `encrypt` protects whole files at rest;
  use full-disk encryption for transparent encrypted search).
- Cloud sync or automatic remote Git push.
- Guaranteed secret detection.

## Reporting

Report vulnerabilities through the process in [SECURITY.md](../SECURITY.md).
Do not include real memory data, credentials, or personal information in a
report. Use synthetic reproduction steps.
