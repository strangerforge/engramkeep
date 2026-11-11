# Good first issues

These are small, self-contained tasks with a clear definition of done. Each
one can be finished without a design discussion. Open an issue with the label
`good first issue` and the matching area label before starting, or claim an
existing one.

Read [CONTRIBUTING.md](../CONTRIBUTING.md) and [AGENTS.md](../AGENTS.md) first.
Every change needs a test and a passing `python -m pytest`.

## 1. Add an explicit `--dry-run` flag to `engramkeep install`

**Area:** installer · **Difficulty:** small

The installer is already a dry run by default, but scripts and muscle memory
expect `--dry-run`. Add the flag as an explicit alias that cannot be combined
with `--apply` or `--uninstall`.

- Files: `src/engramkeep/cli.py`, `tests/test_cli.py`
- Done when: `engramkeep install --agent opencode --dry-run` prints the plan,
  `--dry-run --apply` exits with a usage error, and tests cover both.

## 2. Show the active store path in `engramkeep dashboard`

**Area:** dashboard · **Difficulty:** small

The dashboard header says "Local-first project memory" but not which store it
serves. Print the resolved home in the header or the status line so a user with
several stores can tell them apart.

- Files: `src/engramkeep/dashboard.py`, `tests/test_dashboard.py`
- Done when: the page exposes the store path as text, the token and CSP rules
  are unchanged, and a test asserts the rendered path.

## 3. Add a `--limit` test matrix for search and fixes

**Area:** CLI · **Difficulty:** small

`--limit` accepts any integer. Cover `0`, `1`, a value larger than the number of
entries, and a negative value, and make the behavior explicit in help text.

- Files: `src/engramkeep/cli.py`, `tests/test_cli.py`, `tests/test_fix_cli.py`
- Done when: every case has a documented and tested result, and the help text
  states the valid range.

## 4. Add `engramkeep install --restore` for backups

**Area:** installer · **Difficulty:** medium

`engramkeep install --apply` writes timestamped backups and a `manifest.json`
under `<home>/backups/installer/<run>/`, and `--uninstall` removes managed
blocks cleanly. Add a `--restore <run>` option (dry-run by default) to copy
backed-up files back to their original targets safely.

- Files: `src/engramkeep/installer.py`, `src/engramkeep/cli.py`, `tests/test_installer.py`
- Done when: `--restore` previews changes by default, `--apply` restores the
  recorded backups after symlink/path checks, and tests cover both.

## 5. Document exit codes

**Area:** docs · **Difficulty:** small

Users script around `engramkeep`. Write a short table of exit codes for
`doctor`, `search`, `show`, `fixes`, `install`, and argument errors, and link
it from the README.

- Files: new `docs/EXIT_CODES.md`, `README.md`, `README.tr.md`
- Done when: the table matches the code and every row is verified by a test or
  a manual command.

## 6. Add Turkish translations for the short docs

**Area:** docs · **Difficulty:** medium

`README.tr.md` exists, but `docs/COMPATIBILITY.md` and `docs/PRIVACY.md` are
English-only. Translate them without changing the meaning, and add a language
link at the top.

- Files: `docs/COMPATIBILITY.tr.md`, `docs/PRIVACY.tr.md`
- Done when: both files exist, link to the English originals, and use the same
  headings and tables.

## 7. Add a `doctor` check for duplicate card titles

**Area:** store · **Difficulty:** medium

Two cards can share a title. `doctor` should warn when that happens so the user
can rename or merge them, without treating it as a hard error.

- Files: `src/engramkeep/store.py`, `tests/test_store.py`
- Done when: duplicates produce a warning naming both project ids, the store
  stays healthy, and a test covers the warning.

## 8. Add a `--since` filter to `recent`

**Area:** CLI · **Difficulty:** medium

`recent` always shows the newest entries. Add `--since YYYY-MM-DD` so a user can
see what changed in a sprint.

- Files: `src/engramkeep/cli.py`, `tests/test_cli.py`
- Done when: the filter uses the timestamp prefix in `RECENT_ACTIVITY.md`,
  invalid dates produce a clear error, and help text includes an example.

## 9. Add an installer fixture for a file with no trailing newline

**Area:** installer · **Difficulty:** small

The managed-block writer must behave correctly when the existing file ends
without a newline. Add the fixture and the assertion; fix the writer if the
test exposes a missing separator.

- Files: `src/engramkeep/installer.py`, `tests/test_installer.py`
- Done when: apply and uninstall round-trip byte-for-byte on a file without a
  trailing newline.

## 10. Add a no-match benchmark entry that should stay clean

**Area:** benchmark · **Difficulty:** small

The current no-match control reports two clean results out of three. Add one
clearly unrelated query that must return nothing, and keep the existing
honest reporting for the ambiguous one.

- Files: `examples/fix-registry/fixes.json`, `docs/BENCHMARK.md`
- Done when: the new query is unrelated to every entry, the benchmark still
  passes its floor, and the report does not hide the ambiguous case.

## 11. Improve the MCP status output with the store path

**Area:** MCP · **Difficulty:** small

`engramkeep mcp --status` prints transport, protocol, and write mode, but not
which store the server will read.

- Files: `src/engramkeep/cli.py`, `tests/test_cli.py`
- Done when: the status includes the resolved home, JSON output includes it
  too, and a test covers both.

## 12. Add a screenshot check to the docs build

**Area:** docs · **Difficulty:** medium

`assets/dashboard.png` and `assets/demo.gif` can drift from the current UI. Add
a small script that fails when a referenced asset is missing or larger than a
documented budget.

- Files: new `scripts/check_docs_assets.py`, `tests/test_examples.py`
- Done when: missing files fail, oversized files fail with the actual size, and
  the check runs in CI.

---

If you want to work on something else, open an issue first. Small, focused
pull requests with tests are merged fastest.
