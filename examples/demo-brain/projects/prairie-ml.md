---
id: prairie-ml
title: Prairie ML
created: 2026-10-07T13:10:00Z
updated: 2026-10-20T12:05:00Z
tags: ml, python, reproducibility
---

# Prairie ML

Synthetic experiment-tracking notes for the Engramkeep demo store.

## Decisions

- Record the dataset hash, git commit, and random seed with every run.
- Store metrics in SQLite for local runs and export CSV for sharing.
- Keep training scripts in the repository; keep datasets and checkpoints outside it.
- Compare runs with the same seed before drawing conclusions.

## Gotchas

- Parallel workers writing metrics to one SQLite file trigger `database is locked`; batch writes in the parent process.
- Sorting a dict of floats for a report hides ties; sort by metric and name.
- A notebook is not a reproducible experiment until it runs top-to-bottom in a clean environment.

## Next steps

- Add a `--dry-run` mode that validates paths and config only.
- Publish a small synthetic dataset with the examples.
