# Threat model

This document describes the security assumptions and known limitations of
Engramkeep 0.5.2. It is intentionally conservative.

## Assets

- Memory cards, generated files, and the troubleshooting registry in the local store.
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
4. **MCP client and browser -> store.** The MCP stdio server and the
   loopback dashboard both exist in 0.5.2. MCP is read-only by default; the
   dashboard is read-only by default and requires a per-session token.

## Threats and mitigations

| Threat | Mitigation in 0.5.2 | Residual risk |
| --- | --- | --- |
| Path traversal through a project name | `normalize_project_id()` rejects separators, drive letters, control characters, and traversal; `safe_join()` proves containment | A bug in a future caller could bypass the helper |
| Symlink escape | `safe_join()` resolves symlinks; card scanning rejects symlinks; `append_text()` rejects symlinks | Junction behavior on some Windows versions is not exhaustively tested |
| Secret written to a card or registry entry | `redact_text()` covers common token formats (OpenAI, Anthropic, GitHub, GitLab, Stripe, npm, PyPI, HuggingFace, DigitalOcean, Google, SendGrid, AWS, Slack, Telegram, webhooks), PGP/OPENSSH/PEM key blocks, HTTP auth headers, URL credentials, credential assignments, and email | Encoded or novel secrets can pass through |
| Prompt injection in a card or registry entry | Documentation, skill, and templates state that memory is data, not instructions; the core never executes card or registry text | An agent can still choose to follow malicious text |
| Malicious Markdown | Cards are rendered as text by the CLI and the dashboard; the dashboard sends a strict CSP and never uses `innerHTML` | A browser bug or a future renderer could reintroduce HTML injection |
| Local attacker or malware | Files are created with private permissions where the OS supports it; there is no external network surface, and the dashboard is loopback-only | Same-user malware can read the files |
| Destructive action | `forget` requires `--yes`; cards move to trash instead of being deleted | Trash retains data until manually removed |
| Unsafe installer | Dry-run by default; `--apply` edits only inside `<!-- engramkeep:begin/end -->` managed blocks, refuses symlinks and unreadable JSON, and creates timestamped backups plus `manifest.json` | A user who deletes the backup directory loses the automatic snapshot |
| Supply-chain dependency | Zero runtime dependencies; dev dependencies are pinned by range and monitored by Dependabot | Build tooling is still a dependency |
| Denial of service via huge input | Decision text is capped at 4000 characters (and rejected above 256 KiB before scanning); `_PRIVATE_KEY` scanning is bounded; path components are bounded | Very large hand-written files are not size-limited |
| Malformed card crashes a command | Parse errors are reported; `doctor` surfaces them | A malformed card is skipped by search/list |
| Audit log tampering | Append-only by convention; no cryptographic sealing | A local user can edit the file |
| Store schema confusion | `meta.json` schema version is validated; newer/older versions are rejected | No migration exists yet |
| MCP write tool misuse | `engramkeep_remember` and `engramkeep_record_fix` are not listed or callable unless the server starts with `--allow-write`; there is no MCP forget tool | A user who enables `--allow-write` gives the client permission to add cards |
| MCP network exposure | stdio transport only; the server never opens a socket | A client can still send arbitrary JSON-RPC |
| MCP denial of service | Request lines are capped at 1 MiB; queries, tags, and limits are bounded | A client can send many requests |
| MCP malformed input | Invalid JSON, UTF-8, batches, and arguments produce JSON-RPC errors without crashing the loop | Error text can reveal local paths |
| MCP prompt injection | Initialization instructions and docs say card content is untrusted; tools return content as data | A client can still choose to follow card text |
| Dashboard token leakage | The token is delivered in the URL fragment, never embedded in HTML, kept in `sessionStorage`, and sent only in the `X-Engramkeep-Token` header; responses use `Cache-Control: no-store` and `Referrer-Policy: no-referrer` | A browser extension or local process can still read the token |
| Dashboard DNS rebinding | The server validates the `Host` header against `127.0.0.1` and `localhost` with the bound port and exposes no CORS headers | A local proxy or hosts-file change can still reach loopback |
| Dashboard CSRF | Writes require the token header, `Content-Type: application/json`, a same-origin `Origin` when present, POST, and `confirm: true`; no cookies are used | A compromised same-origin page or browser extension is outside the model |
| Dashboard XSS | Card content is rendered with `textContent`, the shell loads only `/app.js` and `/style.css`, and CSP is `default-src 'none'` | A browser bug or a compromised local asset could still execute code |
| Dashboard path traversal | Every card read goes through `Store.get_card()` and `safe_join()`; traversal attempts return an error and are tested | A bug in a future route could bypass the store |
| Dashboard denial of service | Request bodies are capped at 64 KiB, queries at 2000 characters, limits at 50, and tags at 20 | A local process can still open many connections |

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

### Dashboard (implemented in 0.3.0)

- [x] bind to `127.0.0.1` only (with `SO_EXCLUSIVEADDRUSE` on Windows).
- [x] require a per-session token and reject missing/invalid tokens.
- [x] enforce a path jail for every read and write.
- [x] use a strict Content-Security-Policy.
- [x] render card content as text, never with `innerHTML`.
- [x] mutations use POST with CSRF protection and explicit confirmation.
- [x] no GET request may mutate state.

Residual risk: the token is only as safe as the browser session, and a local
process running as the same user can still read the store directly.

### Installer (implemented in 0.5.0)

- [x] preview changes by default.
- [x] back up every file before modification and record changes in `manifest.json`.
- [x] update a marked managed block; never overwrite unrelated content.
- [x] reject symlinked targets and unreadable JSON configs.
- [x] do not create junctions, services, scheduled tasks, or auto-start entries.

## Reporting

Report vulnerabilities through the process in [SECURITY.md](../SECURITY.md).
Do not include real memory data, credentials, or personal information in a
report. Use synthetic reproduction steps.
