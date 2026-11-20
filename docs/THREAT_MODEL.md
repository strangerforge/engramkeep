# Threat model

This document describes the security assumptions and known limitations of
Engramkeep 1.0.0. It is intentionally conservative.

## Assets

- Memory cards, generated files, backups, and the troubleshooting registry in
  the local (and optional project `.engramkeep/`) store.
- The user's filesystem, Git working tree, and agent configuration.
- The integrity of the agent's behavior when it reads memory.
- The user's credentials and personal data that might appear in text.

## Trust boundaries

1. **User and agent input -> store.** Project names, decisions, tags, fixes,
   and imported transcripts are untrusted.
2. **Store -> agent context.** Card content, fixes, and MCP resources are
   untrusted data even after storage.
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

| Threat | Mitigation in 1.0.0 | Residual risk |
| --- | --- | --- |
| Path traversal through a project name or URI | `normalize_project_id()` rejects separators, drive letters, control characters, and traversal; `safe_join()` proves containment across CLI, MCP tools/resources, dashboard, trash/restore, and migrations | A bug in a future caller could bypass the helper |
| Symlink / NTFS junction escape | `safe_join()` resolves symlinks; `is_link_or_junction()` checks symlinks and Windows reparse points across store, trash, project discovery, importer, installer, migrations, and sync | OS-specific edge cases on exotic filesystems |
| Secret written to card, fix, or imported transcript | `redact_text()` runs before preview or persistence on cards, superseded decisions, fixes, and all transcript adapters; `doctor` scans cards and fixes | Encoded or novel secrets can pass through |
| Prompt injection in cards, fixes, or MCP resources | Documentation, skill, MCP initialization instructions, `_untrusted_data_notice`, and MCP resource headers state memory is untrusted data; core never executes card text | An agent can still choose to follow malicious text |
| Malicious Markdown / Dashboard XSS | Modular dashboard assets use pure `createElement` + `textContent` (zero `innerHTML`), strict CSP (`default-src 'none'`), and `X-Content-Type-Options: nosniff` | A browser bug could still bypass isolation |
| Untrusted transcript import (`importer.py` & `adapters/`) | Dry-run by default (`--apply` or `--interactive` required); 10 MiB hard file cap; symlinks/junctions refused; control/bidi chars stripped; secrets redacted before display or write; fixes deduplicated | Large crafted regex backtracking or noisy natural-language false positives (mitigated by bounded match lengths and `--limit`) |
| Audit log tampering (`audit.py`) | Zero-dep SHA-256 hash chain (`prev_hash` + `hash`) verified by `engramkeep doctor`; any modified, deleted, or injected line fails doctor | An attacker with local write access can rewrite the entire chain from genesis |
| Destructive deletion or failed migration | `forget` moves to `trash/` (recoverable via `restore`); `trash --purge` requires `--yes`; `doctor --fix` and `migrate --apply` create timestamped backups and auto-rollback failed migrations | Deleting backup directories removes rollback snapshots |
| Accidental secret leak or force-push in Git sync (`sync.py`) | Explicit allowlist only (`meta.json`, `INDEX.md`, `TROUBLESHOOTING.md`, `projects/*.md`); never runs `git add -A` or `git push`; `store.doctor()` must pass before commit; `shell=False` with resolved `git` binary | User can still manually stage excluded files or push sensitive non-redacted text |
| Unsafe installer | Dry-run by default; managed blocks only; refuses symlinks and unreadable JSON; timestamped backups + `manifest.json`; `--mcp` is read-only unless `--mcp-allow-write` is passed | Deleting the installer backup directory removes automatic snapshots |
| Supply-chain dependency | Zero runtime dependencies (Python stdlib only); pinned GitHub Actions commit SHAs | Dev/build tooling remains an optional dev dependency |
| MCP abuse or network exposure | stdio transport only; no network listener; multi-version negotiation (`2024-11-05`..`2025-11-25`); read-only by default; no forget tool; 1 MiB line cap and 32-item batch cap | A client started with `--allow-write` can add/supersede decisions and fixes |
| Dashboard CSRF / DNS rebinding / token leakage | `127.0.0.1` exclusive bind; per-session token in URL fragment -> `sessionStorage` -> `X-Engramkeep-Token`; strict Host + Origin checks; POST-only mutations (`remember` & `fixes`) with `confirm: true` | Same-user local processes or browser extensions are outside the model |

## Out of scope

- A hostile multi-user host or shared account.
- Malware running as the same user.
- Physical access to an unlocked machine.
- Encrypted-at-rest storage.
- Cloud sync or automatic remote Git push.
- Guaranteed secret detection.

## Reporting

Report vulnerabilities through the process in [SECURITY.md](../SECURITY.md).
Do not include real memory data, credentials, or personal information in a
report. Use synthetic reproduction steps.
