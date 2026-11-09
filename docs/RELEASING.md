# Releasing Engramkeep

Releases are cut from `main` with a version bump commit and an annotated tag.
The `Release` workflow verifies the tree, builds the distributions, publishes
to PyPI through trusted publishing, and creates a GitHub release.

## One-time setup

1. Create the GitHub repository `strangervibe/engramkeep` and push `main`.
2. On PyPI, add a **pending trusted publisher** for the `engramkeep` project:
   - Owner: `strangervibe`
   - Repository: `engramkeep`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. In the GitHub repository, create an environment named `pypi`. Optionally
   require a reviewer so a release needs a manual approval.
4. Confirm that Actions has `id-token: write` permission for the publish job
   (already set in `.github/workflows/release.yml`).

No long-lived PyPI token is stored in the repository.

## Checklist

1. **Start from a clean `main`.**

   ```bash
   git switch main
   git pull --ff-only
   git status --short   # must be empty
   ```

2. **Run the full gate.**

   ```bash
   python -m pytest --cov=engramkeep --cov-report=term-missing --cov-fail-under=80
   ruff check .
   ruff format --check .
   mypy src
   python scripts/check_repo_hygiene.py
   python scripts/build_demo_brain.py
   git diff --exit-code examples/demo-brain
   python scripts/benchmark_fix_registry.py --output docs/BENCHMARK.md
   ```

3. **Update the version** in both places, keeping them identical:

   - `pyproject.toml` → `[project] version`
   - `src/engramkeep/__init__.py` → `__version__`

4. **Update `CHANGELOG.md`.** Move items out of `[Unreleased]` into a dated
   section. Use [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
   headings: Added, Changed, Deprecated, Removed, Fixed, Security.

5. **Check the docs** that mention the version or behavior: `README.md`,
   `README.tr.md`, `docs/ROADMAP.md`, `docs/COMPATIBILITY.md`, `AGENTS.md`,
   `skills/engramkeep/SKILL.md`.

6. **Build and inspect locally.**

   ```bash
   python -m build
   python -m twine check dist/*
   python -m venv /tmp/engramkeep-release-venv
   /tmp/engramkeep-release-venv/bin/pip install dist/*.whl
   /tmp/engramkeep-release-venv/bin/engramkeep --version
   ```

7. **Commit and tag.**

   ```bash
   git add -A
   git commit -m "Release 0.5.0"
   git tag -a v0.5.0 -m "Engramkeep 0.5.0"
   git push origin main
   git push origin v0.5.0
   ```

8. **Watch the workflow.** It fails if the tag does not match
   `__version__`, if tests or coverage fail, or if `twine check` rejects the
   artifacts.

9. **Verify the release.**

   ```bash
   python -m pip index versions engramkeep
   pipx install --force engramkeep
   engramkeep --version
   ```

10. **Announce.** Update the GitHub release notes if needed and follow
    [docs/LAUNCH.md](LAUNCH.md).

## What the workflow publishes

| Artifact | Purpose |
| --- | --- |
| `engramkeep-<version>-py3-none-any.whl` | Universal wheel |
| `engramkeep-<version>.tar.gz` | Source distribution |
| GitHub release | Tag notes plus both artifacts |

## If something goes wrong

- **A job failed before publish.** Fix the tree, delete the local tag
  (`git tag -d v0.5.0`), delete the remote tag
  (`git push origin :refs/tags/v0.5.0`), and retry.
- **PyPI accepted the upload but the release is wrong.** Do not reuse the
  version. Bump the patch version and release again. If the release is
  unusable, yank it on PyPI; yanking hides it from resolution but keeps it
  installable for pinned users.
- **The GitHub release failed after PyPI succeeded.** Re-run only the
  `github-release` job from the Actions UI; the PyPI version is already
  published and cannot be overwritten.
- **Trusted publishing is misconfigured.** The publish job fails with an
  OIDC error. Confirm the PyPI publisher matches owner, repository, workflow
  filename, and environment exactly; then re-run the job.

## Versioning policy

- `0.x` releases may change the CLI and the on-disk schema. Every schema
  change needs a migration before `1.0.0`.
- Patch releases fix bugs without changing the file format.
- Minor releases add features and may add fields, but keep existing stores
  readable.
- Security fixes are released as soon as they are verified, without waiting
  for a feature release.
