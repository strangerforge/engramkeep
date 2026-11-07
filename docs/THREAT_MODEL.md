# Threat model

This document describes the security assumptions and known limitations of
Engramkeep 0.1.0. It is intentionally conservative.

## Assets

- Memory cards and generated files in the local store.
- The user's filesystem and agent configuration.
- The integrity of the agent's behavior when it reads memory.
- The user's credentials and personal data that might appear in text.

## Trust boundaries

1. **User and agent input -> store.** Project names, decisions, tags, and
   imported text are untrusted.
2. **Store -> agent context.** Card content is untrusted data even after it is
   stored. A card can contain text that looks like an instruction.
3. **Local process -> filesystem.** The process runs with the user's
   privileges. A local attacker or malware with the same privileges is outside
   the model.
4. **Future dashboard/MCP -> store.** These components do not exist in 0.1.0.
   Their planned security requirements are listed below.

## Threats and mitigations

| Threat | Mitigation in 0.1.0 | Residual risk |
| --- | --- | --- |
| Path traversal through a project name | `normalize_project_id()` rejects separators, drive letters, control characters, and traversal; `safe_join()` proves containment | A bug in a future caller could bypass the helper |
| Symlink escape | `safe_join()` resolves symlinks; card scanning rejects symlinks; `append_text()` rejects symlinks | Junction behavior on some Windows versions is not exhaustively tested |
| Secret written to a card | `redact_text()` covers common token formats, private-key blocks, bearer tokens, credential assignments, and email | Encoded or novel secrets can pass through |
| Prompt injection in a card | Documentation, skill, and templates state that memory is data, not instructions; the core never executes card text | An agent can still choose to follow malicious text |
| Malicious Markdown | Cards are rendered as text by the CLI; no HTML rendering in the core | Future dashboard must avoid HTML injection |
| Local attacker or malware | Files are created with private permissions where the OS supports it; no network surface | Same-user malware can read the files |
| Destructive action | `forget` requires `--yes`; cards move to trash instead of being deleted | Trash retains data until manually removed |
| Unsafe installer | Installer is a dry-run planner; it does not write | A user can still copy files incorrectly |
| Supply-chain dependency | Zero runtime dependencies; dev dependencies are pinned by range and monitored by Dependabot | Build tooling is still a dependency |
| Denial of service via huge input | Decision text is capped at 4000 characters; path components are bounded | Very large hand-written files are not size-limited |
| Malformed card crashes a command | Parse errors are reported; `doctor` surfaces them | A malformed card is skipped by search/list |
| Audit log tampering | Append-only by convention; no cryptographic sealing | A local user can edit the file |
| Store schema confusion | `meta.json` schema version is validated; newer/older versions are rejected | No migration exists in 0.1.0 |

## Out of scope

- A hostile multi-user host or shared account.
- Malware running as the same user.
- Physical access to an unlocked machine.
- Encrypted-at-rest storage (not implemented).
- Cloud sync, remote backups, and multi-device conflict resolution.
- Guaranteed secret detection.
- Perfect isolation of agent behavior from stored text.

## Requirements for future components

### MCP server (0.2.0)

- stdio transport only; no TCP listener.
- newline-delimited JSON, protocol version 2025-11-25.
- read-only tools by default.
- writes require an explicit confirmation token or user-approved mode.
- validate every path through the same store helpers.
- return card content as data; never mark it as trusted instructions.

### Dashboard (0.2.0)

- bind to `127.0.0.1` only.
- require a per-session token and reject missing/invalid tokens.
- enforce a path jail for every read and write.
- use a strict Content-Security-Policy.
- render card content as text, never with `innerHTML`.
- mutations use POST with CSRF protection and explicit confirmation.
- no GET request may mutate state.

### Installer (0.2.0)

- preview changes by default.
- back up every file before modification.
- update a marked managed block; never overwrite unrelated content.
- reject symlinked targets.
- do not create junctions, services, scheduled tasks, or auto-start entries.

## Reporting

Report vulnerabilities through the process in [SECURITY.md](../SECURITY.md).
Do not include real memory data, credentials, or personal information in a
report. Use synthetic reproduction steps.
