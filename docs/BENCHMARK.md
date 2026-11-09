# Fix recall benchmark

Synthetic corpus: 15 error/fix pairs and 45 human-written queries (English and Turkish). Scoring is lexical with a small bilingual concept
bonus; there are no embeddings and no network calls.

| Metric | Result |
| --- | --- |
| Top-1 accuracy | 43/45 (95.6%) |
| Top-3 recall | 45/45 (100.0%) |
| Mean reciprocal rank | 0.978 |
| Turkish query, English entry, top-1 | 15/15 (100.0%) |
| Turkish query, English entry, top-3 | 15/15 (100.0%) |
| Query latency p50 | 3.427 ms |
| Query latency p95 | 8.962 ms |
| No-match queries returning nothing | 2/3 |

## Per entry

| Entry | Project | Queries | Top-1 | Top-3 | Worst rank |
| --- | --- | --- | --- | --- | --- |
| `python-psycopg2-missing` | Ledger CLI | 3 | 3 | 3 | 1 |
| `docker-exec-format-arm64` | Harbor Infra | 3 | 3 | 3 | 1 |
| `sqlite-database-locked` | Prairie ML | 3 | 3 | 3 | 1 |
| `postgres-password-auth` | Atlas API | 3 | 3 | 3 | 1 |
| `android-keystore-tampered` | Orbit Mobile | 3 | 3 | 3 | 1 |
| `react-max-update-depth` | Signal Dashboard | 3 | 3 | 3 | 1 |
| `node-openssl-legacy-provider` | Signal Dashboard | 3 | 3 | 3 | 1 |
| `git-unrelated-histories` | Ledger CLI | 3 | 3 | 3 | 1 |
| `typescript-ts2307-alias` | Signal Dashboard | 3 | 2 | 3 | 2 |
| `terraform-state-lock` | Harbor Infra | 3 | 3 | 3 | 1 |
| `vite-failed-resolve-import` | Signal Dashboard | 3 | 2 | 3 | 2 |
| `python-recursion-repr` | Atlas API | 3 | 3 | 3 | 1 |
| `github-actions-resource-not-accessible` | Ledger CLI | 3 | 3 | 3 | 1 |
| `cors-missing-allow-origin` | Atlas API | 3 | 3 | 3 | 1 |
| `gradle-jdk-mismatch` | Orbit Mobile | 3 | 3 | 3 | 1 |

No-match queries that still returned a result:

- `kubernetes ingress certificate renewal` matched Harbor Infra

## Method

Each corpus entry has two or three queries written independently of the
stored error text. The expected fix counts as correct only when it appears
in the first result (top-1) or anywhere in the first three results (top-3).
Latency is measured over repeated in-process searches and is indicative,
not a cross-machine benchmark.

Reproduce:

```bash
python scripts/benchmark_fix_registry.py --output docs/BENCHMARK.md
```
