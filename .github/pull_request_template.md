## Summary

Describe the change and why it is needed.

## Security impact

- [ ] No security-sensitive behavior changed.
- [ ] Security-sensitive change; threat model or tests updated.

## Checklist

- [ ] Tests added or updated.
- [ ] `python -m pytest` passes.
- [ ] `ruff check .` passes.
- [ ] `python scripts/check_repo_hygiene.py` passes.
- [ ] No secrets, personal data, or real project names.
- [ ] `CHANGELOG.md` and relevant docs updated.
- [ ] New paths go through `safe_join()`.
- [ ] New writes use `atomic_write_text()` or `append_text()`.
- [ ] No network calls, telemetry, auto-push, junctions, daemons, or auto-start entries.
