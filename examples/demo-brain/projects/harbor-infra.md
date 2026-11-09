---
id: harbor-infra
title: Harbor Infra
created: 2026-10-06T08:25:00Z
updated: 2026-10-24T09:30:00Z
tags: infra, docker, terraform
---

# Harbor Infra

Synthetic deployment notes for the Engramkeep demo store.

## Decisions

- Build multi-architecture images in CI with `docker buildx`.
- Keep Terraform state in a remote backend with locking enabled.
- Pin every image tag to a digest in production.
- Run one deployment at a time; the pipeline holds the lock.

## Gotchas

- An `exec format error` on an ARM machine usually means the image was built for the wrong platform.
- Terraform state locks outlive crashed CI runs; confirm no apply is active before forcing an unlock.
- `latest` tags make rollbacks ambiguous; deploy digests instead.

## Next steps

- Add a smoke test after deploy.
- Document the rollback procedure.
