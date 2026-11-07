# Threat model

This document describes the security assumptions and known limitations of
Engramkeep 0.2.0. It is intentionally conservative.

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
4. **MCP client -> store.** The MCP stdio server exists in 0.2.0 and is
   read-only by default. The dashboard does not exist yet; its planned
   security requirements are listed below.

## Threats and mitigations

| Threat | Mitigation in 0.2.0 | Residual risk |
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
| Store schema confusion | `meta.json` schema version is validated; newer/older versions are rejected | No migration exists in 0.2.0 |
| MCP write tool misuse | `engramkeep_remember` is not listed or callable unless the server starts with `--allow-write`; there is no MCP forget tool | A user who enables `--allow-write` gives the client permission to add cards |
| MCP network exposure | stdio transport only; the server never opens a socket | A client can still send arbitrary JSON-RPC |
| MCP denial of service | Request lines are capped at 1 MiB; queries, tags, and limits are bounded | A client can send many requests |
| MCP malformed input | Invalid JSON, UTF-8, batches, and arguments produce JSON-RPC errors without crashing the loop | Error text can reveal local paths |
| MCP prompt injection | Initialization instructions and docs say card content is untrusted; tools return content as data | A client can still choose to follow card text |

## Out of scope

- A hostile multi-user host or shared account.
- Malware running as the same user.
- Physical access to an unlocked machine.
- Encrypted-at-rest storage (not implemented).
- Cloud sync, remote backups, and multi-device conflict resolution.
- Guaranteed secret detection.
- Perfect isolation of agent behavior from stored text.

## Security requirements for integrations

### MCP server (implemented in 0.2.0)

- [x] stdio transport only; no TCP listener.
- [x] newline-delimited JSON-RPC 2.0, protocol version 2025-11-25.
- [x] read-only tools by default.
- [x] writes require the explicit `--allow-write` server flag.
- [x] validate every path through the same store helpers.
- [x] return card content as data; initialization instructions call it
  untrusted.
- [x] no forget tool.
- [x] cap request lines and tool arguments.

Residual risk: a client started with `--allow-write` can add cards, and a
client can ignore the instruction to treat card text as data.

### Dashboard (0.3.0)

- bind to `127.0.0.1` only.
- require a per-session token and reject missing/invalid tokens.
- enforce a path jail for every read and write.
- use a strict Content-Security-Policy.
- render card content as text, never with `innerHTML`.
- mutations use POST with CSRF protection and explicit confirmation.
- no GET request may mutate state.

### Installer (0.3.0)

- preview changes by default.
- back up every file before modification.
- update a marked managed block; never overwrite unrelated content.
- reject symlinked targets.
- do not create junctions, services, scheduled tasks, or auto-start entries.

## Reporting

Report vulnerabilities through the process in [SECURITY.md](../SECURITY.md).
Do not include real memory data, credentials, or personal information in a
report. Use synthetic reproduction steps.
