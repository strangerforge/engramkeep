# Roadmap

This roadmap is a direction, not a promise. Security gates apply to every
release.

## 0.1.0 - Alpha (current)

- Local Markdown store with cards, index, recent activity, and audit log.
- CLI: `init`, `remember`, `search`, `show`, `list`, `recent`, `forget`,
  `export`, `reindex`, `doctor`, `path`.
- Path jail, atomic writes, private directories, and symlink rejection.
- Best-effort secret and email redaction.
- Portable `AGENTS.md` and `SKILL.md` templates.
- Dry-run agent installer.
- Tests, CI skeleton, repository hygiene check.
- MCP and dashboard are stubs.

## 0.2.0 - Integrations

- MCP stdio server with newline-delimited JSON and protocol version
  2025-11-25.
- Read-only MCP tools first; write tools require explicit confirmation.
- Hardened dashboard: loopback bind, per-session token, CSP, path jail,
  text-only rendering, POST-only mutations.
- Installer that previews, backs up, and updates a managed block.
- Schema migration framework.
- More tests for the new surfaces.

Security gate: threat model updated, no network listener by default, no
unauthenticated writes, no HTML injection, no path escape.

## 0.3.0 - Import and encryption

- Read-only transcript adapters with explicit consent and documented paths.
- Optional encryption at rest with a user-supplied key.
- Better search: field weighting, phrase support, and deterministic snippets.
- Import dry-run that shows exactly what would be written.

Security gate: imported text is treated as untrusted, encrypted stores never
write plaintext to disk, and key handling is documented.

## 0.4.0 - Optional sync design

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
