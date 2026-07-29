# Myriad — Build Progress

Living notes. Updated as work happens.

---

## Day 4 — Thursday 30 July

**Goal:** download historical Premier League results + odds into a staging table.

| Step | What | State |
|------|------|-------|
| 1 | `collectors/results.py` | Done |
| 2 | Parse Date, teams, goals, referee, odds | Done |
| 3 | Load raw into DuckDB `matches_staging` | Done |

### Results

- Downloaded **16 seasons** (2010-11 → 2025-26) from football-data.co.uk
- **6,080 matches** in `matches_staging` (380 per season)
- **41** distinct raw team names (normalisation is Day 5)
- Closing odds present on ~44% of rows (older seasons only have opening odds — expected)

### How to run

```bash
make results
# or: uv run python -m collectors.results
# reuse CSVs: uv run python -m collectors.results --skip-download
```

---

## Day 3 — Wednesday 29 July

**Goal:** alert on missing snapshots, project scaffolding.

| Step | What | State |
|------|------|-------|
| 1 | `.github/workflows/gap-alert.yml` | Done |
| 2 | Expand `README.md` | Done |
| 3 | `Makefile` stubs | Done |

### Acceptance verified

Triggered `gap-alert` via `workflow_dispatch`. It found 13 gaps and opened
[issue #1](https://github.com/trenchsheikh/myrid/issues/1) — Crowd snapshot gap detected.

---

## Day 2 — Tuesday 28 July

**Goal:** wire Parquet snapshots into DuckDB, prove the logger has no big gaps.

| File | Job |
|------|-----|
| `db/schema.sql` | Database blueprint (matches, crowd snapshots, predictions, teams) |
| `loaders/crowd_to_duck.py` | Reads hourly Parquet files, inserts new ones into DuckDB. Safe to run twice. |
| `scripts/check_gaps.py` | Fails if any two consecutive captures are more than 90 minutes apart |

### Results

- 29 snapshot files loaded, 16,330 player-rows in DuckDB
- Second load skipped all 29 files (idempotent)
- Gap check found 12 gaps > 90 min (longest ~222 min) — GitHub Actions delays

### Bug fixed

DuckDB converted UTC timestamps to local BST on insert, breaking idempotency. Fix: store naive UTC wall-clock times.

---

## Day 1 — Monday 27 July

Logger and nothing else. `collectors/crowd.py` + `.github/workflows/crowd-logger.yml`.
