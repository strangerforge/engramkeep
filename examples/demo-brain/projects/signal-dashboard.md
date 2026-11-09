---
id: signal-dashboard
title: Signal Dashboard
created: 2026-10-05T10:00:00Z
updated: 2026-10-23T17:45:00Z
tags: frontend, typescript, accessibility
---

# Signal Dashboard

Synthetic React dashboard for the Engramkeep demo store.

## Decisions

- Use React with TypeScript and Vite for the build.
- Keep chart colours in design tokens; never hard-code hex values in components.
- Every interactive control needs a visible focus state and a keyboard path.
- Prefer server-side filtering over shipping the whole dataset to the browser.

## Gotchas

- Vite and `tsconfig` must agree on path aliases, or imports work in the editor and fail at build time.
- A `useEffect` that sets state from a derived value causes an update loop.
- Chart libraries often ignore `prefers-reduced-motion`; disable animation explicitly.

## Next steps

- Add a table view for screen readers.
- Profile the first render with 5k points.
