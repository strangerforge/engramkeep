# Good first issues

These are small, self-contained tasks with a clear definition of done. Each
one can be finished without a design discussion. Open an issue with the label
`good first issue` and the matching area label before starting, or claim an
existing one.

Read [CONTRIBUTING.md](../CONTRIBUTING.md) and [AGENTS.md](../AGENTS.md) first.
Every change needs a test and a passing `python -m pytest`.

## 1. Show a transparent Windows permissions note in `engramkeep doctor`

**Area:** store · **Difficulty:** small

On POSIX systems, `engramkeep doctor` verifies `0o700` / `0o600` file
permissions via `is_private_path()`. On Windows, NTFS ACLs are not represented
by POSIX mode bits, so `is_private_path()` treats the check as satisfied. Add
an informational line to the human `doctor` output on Windows noting that POSIX
permission checks are skipped (without marking the store unhealthy).

- Files: `src/engramkeep/cli.py`, `tests/test_cli.py`
- Done when: Windows `doctor` output includes a clear informational note, exit
  code stays `0` on healthy stores, and tests cover both POSIX and Windows
  output paths.

## 2. Add a malformed Codex TOML config test for `engramkeep install`

**Area:** installer · **Difficulty:** small

`tests/test_installer.py` already covers malformed JSON MCP configs, symlinks,
and unreadable encodings, but Codex MCP registration uses a TOML managed block
in `config.toml`. Add regression tests for an existing `config.toml` containing
broken or mismatched managed-block markers.

- Files: `src/engramkeep/installer.py`, `tests/test_installer.py`
- Done when: broken/mismatched TOML markers are refused safely without
  modifying the user's file, and tests cover dry-run and apply modes.

## 3. Add property-based regression tests for redaction and frontmatter parsing

**Area:** testing · **Difficulty:** medium

Add optional `hypothesis` property-based tests (under `[project.optional-dependencies]`
`dev` only — zero runtime dependencies) exercising `redact_text()`,
`parse_card()`, and `safe_join()` against arbitrary Unicode, control
characters, and deeply nested inputs.

- Files: `pyproject.toml`, new `tests/test_properties.py`
- Done when: tests run quickly in CI, never fail on arbitrary UTF-8 inputs, and
  verify `safe_join()` containment and redaction invariants.

## 4. Add a Turkish translation for `docs/EXIT_CODES.md`

**Area:** docs · **Difficulty:** small

`docs/COMPATIBILITY.md` and `docs/PRIVACY.md` now have Turkish counterparts
(`COMPATIBILITY.tr.md` and `PRIVACY.tr.md`), while `docs/EXIT_CODES.md` is
English-only. Translate it without changing the meaning and link both versions
at the top.

- Files: `docs/EXIT_CODES.tr.md`, `docs/EXIT_CODES.md`
- Done when: both files link to each other, keep identical tables and exit
  codes, and `python scripts/check_repo_hygiene.py` passes.

## 5. Add an additional language concept pack (opt-in, zero dependencies)

**Area:** search · **Difficulty:** medium

`src/engramkeep/concepts.py` provides a small deterministic English/Turkish
concept map for cross-language recall without embeddings or network calls. Add
a focused, synthetic benchmark-backed concept pack for one more language
(for example German or Spanish) while keeping search deterministic and fast.

- Files: `src/engramkeep/concepts.py`, `tests/test_concepts.py`
- Done when: zero new runtime dependencies, no project-specific terms, and
  cross-language recall tests pass without regressing the existing EN/TR
  benchmark.

---

If you want to work on something else, open an issue first. Small, focused
pull requests with tests are merged fastest.
