# CLI Exit Codes

Engramkeep returns deterministic process exit codes so shell scripts, CI
pipelines, and coding agents can branch safely without parsing human-readable
output.

## Summary table

| Exit code | Meaning |
| --- | --- |
| `0` | Success (including no-op dry runs and empty search/list results) |
| `1` | Operational error, validation failure, missing resource, safety refusal, or unhealthy check |
| `2` | CLI argument / syntax error from `argparse` (unknown command, missing required flag, invalid choice) |
| `130` | Interrupted by user (`Ctrl+C` / `KeyboardInterrupt`) |

## Command-specific notes

| Command | Returns `0` when | Returns `1` when |
| --- | --- | --- |
| `engramkeep show <project>` | Card exists and is readable | Card does not exist or project id is invalid |
| `engramkeep forget <project> --yes` | Card or decision removed (moved to `trash/`) | Card missing or decision not found (`2` if `--yes` omitted) |
| `engramkeep trash --purge --yes` | Trash emptied | Operational error (`2` if `--yes` omitted) |
| `engramkeep restore <project>` | Card restored from `trash/` | Trashed card missing, or active card exists without `--force` |
| `engramkeep merge <src> <dst>` | Decisions and tags merged into `<dst>` | Source or target missing, or `<src> == <dst>` |
| `engramkeep search` / `fixes` / `list` / `context` | Query runs cleanly (even with 0 hits) | Invalid argument (e.g., invalid `--since` on `recent`, invalid store path) |
| `engramkeep doctor` | Store exists, no malformed cards, no leaked secrets, valid audit chain | Store missing, malformed card, secret detected, symlink/junction error, or broken audit chain |
| `engramkeep sync --status` / `--commit` | Repo clean or allowlisted commit succeeds | Doctor check fails, `git` missing, or commit fails |
| `engramkeep migrate` | Dry run succeeds, `--apply` upgrades cleanly, or `--rollback` restores cleanly | Invalid rollback directory (outside `<home>/backups/migrations/` or symlink) or migration error |
| `engramkeep import` | `--discover` succeeds, or file parsed (dry-run / `--apply` / `--interactive`) | File missing, unreadable, symlink traversal, or unknown `--format` (exit `2` if neither `--file` nor `--discover` is given) |
| `engramkeep install` | Dry run, `--apply`, `--uninstall`, or `--restore` succeeds cleanly | Unknown agent, invalid backup run id, symlink target, or unparseable config file (exit `2` if `--agent`, `--list`, and `--restore` are all omitted) |
| `engramkeep encrypt` / `decrypt` | Dry run or `--apply` succeeds | Optional `engramkeep[crypto]` dependency missing, wrong passphrase, or tampered envelope |
| `engramkeep mcp` / `dashboard` | `--status` succeeds, or server exits cleanly on EOF/`SIGINT` | Store error, invalid port, or port already in use |

## Machine-readable output

Pass `--json` to commands that support structured output (`search`, `show`,
`list`, `recent`, `fixes`, `context`, `doctor`, `import`, `install`, `mcp --status`,
`dashboard --status`). Even when `--interactive` is combined with `--json` on
`engramkeep import`, interactive prompts are written to `stderr` so `stdout`
remains valid JSON.
