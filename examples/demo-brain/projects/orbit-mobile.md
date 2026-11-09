---
id: orbit-mobile
title: Orbit Mobile
created: 2026-10-03T11:05:00Z
updated: 2026-10-18T10:20:00Z
tags: mobile, android, offline
---

# Orbit Mobile

Synthetic Capacitor app notes for the Engramkeep demo store.

## Decisions

- Ship a Capacitor hybrid app instead of two native codebases.
- Queue writes in SQLite and sync when the device is online; never block the UI on the network.
- Keep the Android keystore outside the repository and load secrets from CI variables.
- Pin the Gradle wrapper and use JDK 17 for every build.

## Gotchas

- A keystore error is usually a wrong alias or a stale password, not a corrupted file.
- SQLite writes from two isolates cause `database is locked`; keep one writer.
- Offline timestamps must be stored in UTC and reconciled on the server.

## Next steps

- Add a background sync retry with exponential backoff.
- Test the upgrade path from the previous app version.
