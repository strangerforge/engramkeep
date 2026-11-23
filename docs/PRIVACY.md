# Privacy

> **English** | [Türkçe](PRIVACY.tr.md)

Engramkeep is local-first by design. The core does not create an account,
collect telemetry, contact a server, or upload memory.

## What is stored

When you run `engramkeep remember` (or `supersede` / `merge`), the store writes:

- the project id and title,
- the decision text you provided (and superseded decision history),
- tags you provided,
- created and updated timestamps,
- metadata-only SHA-256 hash-chained audit entries (action, project, tags, timestamps).

The store does not write decision text into `audit.log`.

When you run `engramkeep fix`, the store writes a troubleshooting registry
(`TROUBLESHOOTING.md`) with the error text, the fix you provided, and optional
project label and workspace path. Registry entries pass through the same
redaction (including user-path username masking) as cards, are rewritten
atomically, and are treated as untrusted data by agents.

## Where it is stored

| Platform | Default global location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Engramkeep` |
| macOS | `~/Library/Application Support/Engramkeep` |
| Linux | `$XDG_DATA_HOME/engramkeep` or `~/.local/share/engramkeep` |

Override it with `--home`, `--local` (repository `.engramkeep/`), or
`ENGRAMKEEP_HOME`. Run `engramkeep path` to see the active location.

### Project-local `.engramkeep/` and `backups/`

- An optional `.engramkeep/` store inside a repository holds project-scoped
  decisions and fixes that can be shared with teammates or kept local. Review
  its contents carefully before committing it to any repository.
- Installer backups (`<home>/backups/installer/`), schema migration backups
  (`<home>/backups/migrations/`), and crypto backups (`<home>/backups/crypto/`)
  keep timestamped copies of files modified on disk so changes remain
  reversible. Remove old backup folders when you no longer need rollback.

## Redaction

Before storing user text, Engramkeep replaces common secret formats with
`[REDACTED]`, email addresses with `[REDACTED_EMAIL]`, and personal usernames in
home directory paths (`C:\Users\<name>`, `/Users/<name>`, `/home/<name>`) with
`[REDACTED_USER]`.

Built-in patterns cover OpenAI/Anthropic/Supabase/Groq/xAI/Perplexity/Resend/
Linear/Databricks keys, GitHub tokens, Google API keys, AWS access key ids,
Slack tokens, JWTs, private-key blocks, bearer tokens, and credential-like
`key=value` assignments.

You can add organization-specific patterns in `<home>/redact.json` (each rule
is validated against ReDoS-prone nested quantifiers and empty matches before
compiling). `engramkeep doctor` scans cards and `TROUBLESHOOTING.md` using both
built-in and custom rules.

Redaction is **best-effort**. It cannot reliably catch:

- encoded, split, or encrypted secrets,
- secrets in images, archives, or binaries,
- novel token formats not covered by built-in or `redact.json` rules,
- secrets in project names or tags that are transformed before storage,
- free-form personal data beyond emails and standard home paths.

Do not use Engramkeep as a secret manager. If a credential may have been
stored, rotate it and remove the card.

## Optional at-rest encryption

If you need encrypted files on disk beyond full-disk encryption, install the
optional extra `pip install 'engramkeep[crypto]'` and use `engramkeep encrypt`
/ `engramkeep decrypt`. Passphrases are read from `ENGRAMKEEP_PASSPHRASE` or an
interactive terminal prompt (`getpass`), never from CLI arguments (avoiding
shell history and process-list leaks).

**Scope and limitations:**

- Encryption covers `projects/*.md` and `TROUBLESHOOTING.md` only.
- `INDEX.md`, `RECENT_ACTIVITY.md`, `audit.log`, and `meta.json` remain
  plaintext (project ids, titles, tags, and activity timestamps are still
  visible in those files).
- `engramkeep encrypt --apply` verifies decryption round-trip before writing and
  automatically removes the temporary plaintext backup under `<home>/backups/crypto/`
  unless `--keep-plaintext-backup` is passed. While encrypted, normal read/write
  commands refuse to run until `engramkeep decrypt --apply` is executed.
- For transparent, whole-directory confidentiality, prefer OS full-disk
  encryption (BitLocker, FileVault, LUKS).

## Transcript discovery and import

- `engramkeep import --discover` only inspects file metadata (paths, sizes,
  modification times, detected format) in standard local agent session folders
  and skips symlinks. It never modifies or reads transcript content automatically.
- `engramkeep import --file <path>` is dry-run by default and never writes to
  the store until you pass `--apply` or approve items via `--interactive`.

## Local Git sync

`engramkeep sync` is opt-in and local-only:

- It stages only allowlisted files (`projects/*.md`, `INDEX.md`,
  `TROUBLESHOOTING.md`) and tracked allowlisted deletions.
- It never stages `trash/`, `audit.log`, `backups/`, or arbitrary files, and
  never runs `git add -A` or `git push`.
- Every `--commit` runs a secret scan first and aborts if a secret is detected.

## MCP

The MCP server communicates over stdio with the client process. It does not
open a network socket or send memory anywhere. Tool results and resources go
only to the connected client. Read-only tools are available by default; write
tools require `--allow-write`.

## Dashboard

The dashboard is a local HTTP server bound to `127.0.0.1`. It does not contact
the internet. The per-session token is delivered in the URL fragment, kept in
the browser's `sessionStorage`, and sent only to the loopback server in the
`X-Engramkeep-Token` header. The dashboard sets no cookies, sends no CORS
headers, and logs only the HTTP method and path, not query strings or headers.

The dashboard is read-only by default. Writes are enabled only with
`--allow-write` and still require explicit confirmation.

## What Engramkeep does not do

- No telemetry, analytics, crash reporting, or update check.
- No cloud sync, automatic Git push, or remote backup.
- No automatic background transcript scraping.
- No background daemon or auto-start entry.
- No required third-party runtime dependencies.

## Sharing and backups

If you copy or back up the memory directory, you are responsible for the
contents. Both `trash/` and `backups/` can retain cards you asked to forget or
earlier versions of files. Review the directory before sharing it, and do not
commit a personal memory home to a public repository.

The repository `.gitignore` excludes common runtime data, archives, logs, and
secret file types, but it is not a substitute for reviewing what you commit.

## Data removal

- `engramkeep forget <project> --yes` moves a card to `trash/` (recoverable via
  `engramkeep restore <project>`).
- `engramkeep trash --purge --yes` permanently deletes all cards in `trash/`.
- To remove everything, delete the memory home directory (and any repo
  `.engramkeep/` directory if created).

There is no remote copy to delete.

## Children and regulated data

Engramkeep is a developer tool, not a system of record. Do not use it for
regulated personal data, health data, financial data, or information about
children.

## Contact

Privacy questions can be opened as a GitHub issue that contains no personal
data. Security issues should follow [SECURITY.md](../SECURITY.md).
