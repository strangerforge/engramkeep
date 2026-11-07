# Privacy

Engramkeep is local-first by design. The core does not create an account,
collect telemetry, contact a server, or upload memory.

## What is stored

When you run `engramkeep remember`, the store writes:

- the project id and title,
- the decision text you provided,
- tags you provided,
- created and updated timestamps,
- metadata-only audit entries (action, project, tags, timestamps).

The store does not write the decision text into the audit log.

## Where it is stored

| Platform | Default location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Engramkeep` |
| macOS | `~/Library/Application Support/Engramkeep` |
| Linux | `$XDG_DATA_HOME/engramkeep` or `~/.local/share/engramkeep` |

Override it with `--home` or `ENGRAMKEEP_HOME`. Run `engramkeep path` to see
the active location.

## Redaction

Before storing user text, Engramkeep replaces common secret formats with
`[REDACTED]` and email addresses with `[REDACTED_EMAIL]`. Covered formats
include common provider API keys, GitHub tokens, Google API keys, AWS access
key ids, Slack tokens, JWTs, private-key blocks, bearer tokens, and
credential-like `key=value` assignments.

Redaction is **best-effort**. It cannot reliably catch:

- encoded, split, or encrypted secrets,
- secrets in images, archives, or binaries,
- novel token formats,
- secrets in project names or tags that are transformed before storage,
- personal data other than email addresses.

Do not use Engramkeep as a secret manager. If a credential may have been
stored, rotate it and remove the card.

## What Engramkeep does not do

- No telemetry, analytics, crash reporting, or update check.
- No cloud sync, Git push, or remote backup.
- No automatic transcript scraping.
- No background daemon or auto-start entry.
- No third-party runtime dependencies.

## Sharing and backups

If you copy or back up the memory directory, you are responsible for the
contents. The `trash/` directory can retain cards you asked to forget. Review
the directory before sharing it, and do not commit it to a public repository.

The repository `.gitignore` excludes common runtime data, archives, logs, and
secret file types, but it is not a substitute for reviewing what you commit.

## Data removal

- `engramkeep forget <project> --yes` moves a card to `trash/`.
- To remove it permanently, delete the matching file in `trash/`.
- To remove everything, delete the memory home directory.

There is no remote copy to delete.

## Children and regulated data

Engramkeep is a developer tool, not a system of record. Do not use it for
regulated personal data, health data, financial data, or information about
children.

## Contact

Privacy questions can be opened as a GitHub issue that contains no personal
data. Security issues should follow [SECURITY.md](../SECURITY.md).
