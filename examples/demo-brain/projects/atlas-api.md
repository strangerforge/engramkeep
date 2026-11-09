---
id: atlas-api
title: Atlas API
created: 2026-10-02T09:15:00Z
updated: 2026-10-21T16:40:00Z
tags: api, database, python
---

# Atlas API

Synthetic service notes for the Engramkeep demo store.

## Decisions

- Use FastAPI with Pydantic v2 models at the HTTP boundary.
- Store money as integer cents in PostgreSQL; never use floats.
- Keep authentication in one `auth` module; sessions are opaque tokens in a `sessions` table.
- Run Alembic migrations in CI before deploying.

## Gotchas

- PostgreSQL `password authentication failed` during local setup usually means the role does not exist yet, not that the password is wrong.
- `psycopg2` needs a binary wheel on Windows; prefer `psycopg[binary]` in development.
- Connections leak when a request raises before the dependency closes; keep the session in a context manager.

## Next steps

- Add request-id logging.
- Benchmark the `/search` endpoint with 10k rows.
