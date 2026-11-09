---
id: ledger-cli
title: Ledger CLI
created: 2026-10-04T14:30:00Z
updated: 2026-10-22T08:10:00Z
tags: cli, python, packaging
---

# Ledger CLI

Synthetic command-line bookkeeping tool for the Engramkeep demo store.

## Decisions

- Keep the package dependency-free at runtime.
- Represent amounts with `decimal.Decimal`, never binary floats.
- Publish wheels through GitHub Actions and verify them with `twine check`.
- Keep the CLI deterministic: no network access, no background jobs.

## Gotchas

- `pip install` from a source checkout can pick up a stale build directory; use an isolated virtual environment.
- Editable installs hide missing package data; test the built wheel in a clean environment.
- CI tokens need explicit `permissions:` when the default token is read-only.

## Next steps

- Add import from CSV with a dry-run preview.
- Document the exit codes.
