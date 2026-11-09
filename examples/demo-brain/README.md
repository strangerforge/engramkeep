# Synthetic demo brain

Six project cards and six resolved fixes, generated from
`examples/demo-cards.json` and `examples/fix-registry/fixes.json`. All data is
synthetic; it contains no real project names, people, paths, or secrets.

Explore it without touching your own memory:

```bash
engramkeep --home examples/demo-brain dashboard
engramkeep --home examples/demo-brain search "docker arm64"
engramkeep --home examples/demo-brain fixes "database is locked"
engramkeep --home examples/demo-brain doctor
```

Rebuild it after editing the source files:

```bash
python scripts/build_demo_brain.py
```

Do not copy real memory into this directory.
