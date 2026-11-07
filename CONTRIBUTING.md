# Contributing to Engramkeep

Thanks for helping. Engramkeep is small on purpose: keep changes focused,
auditable, and safe by default.

## Before you start

- Read [AGENTS.md](AGENTS.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
  and [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
- Follow the [Code of Conduct](CODE_OF_CONDUCT.md).
- Report security issues through [SECURITY.md](SECURITY.md), not a public issue.
- Do not include real project names, personal paths, credentials, or memory
  data in issues, pull requests, tests, or examples.

## Development setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -e ".[dev]"
```

Run the checks:

```bash
python -m pytest
python scripts/check_repo_hygiene.py
ruff check .
ruff format --check .
```

If `ruff` is not installed, install the `dev` extra first.

## What to work on

Good first contributions:

- documentation fixes and clearer examples,
- tests for edge cases,
- agent rule templates,
- search quality improvements that do not add dependencies,
- portability fixes for Windows, macOS, and Linux.

Open an issue before starting a large feature. Discuss security-sensitive
changes before writing code.

## Code style

- Python 3.10+ with type hints on public functions.
- Standard library only for runtime code. Ask before adding a dependency.
- Keep lines at 100 characters or less.
- Prefer small pure functions in `models.py` and `search.py`; keep I/O in
  `store.py`.
- Use `safe_join()` for user-controlled paths and `atomic_write_text()` for
  files that can be regenerated or updated.
- Never use `eval`, `exec`, `pickle`, `shell=True`, or `os.system`.
- Do not add network calls, telemetry, auto-push, junctions, daemons, or
  auto-start entries.

## Tests

- Add or update tests for every behavior change.
- Use `tmp_path` and `ENGRAMKEEP_HOME`; never touch the real user home.
- Add regression tests for path traversal, symlinks, malformed frontmatter,
  redaction, and destructive operations.
- Security-sensitive changes need a test that demonstrates the mitigation.

## Commit messages

Use a short imperative subject, then explain the why in the body if needed.

```text
Add path jail regression test

Explain why the case matters and what behavior is now guaranteed.
```

## Pull requests

- Keep the diff focused.
- Describe the user-visible change and any security impact.
- Update `CHANGELOG.md` and relevant docs.
- Confirm the checklist:

- [ ] Tests added or updated.
- [ ] `python -m pytest` passes.
- [ ] `ruff check .` passes.
- [ ] `python scripts/check_repo_hygiene.py` passes.
- [ ] No secrets, personal data, or real project names.
- [ ] Security impact considered.

## License

By contributing, you agree that your contribution is licensed under the MIT
License in [LICENSE](LICENSE). There is no CLA.
