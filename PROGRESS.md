# Myriad — Build Progress

Living notes. Updated as work happens.

---

## Day 3 — Wednesday 29 July

**Goal:** alert on missing snapshots, project scaffolding.

| Step | What | State |
|------|------|-------|
| 1 | `.github/workflows/gap-alert.yml` | Done |
| 2 | Expand `README.md` | Done |
| 3 | `Makefile` stubs | Done |

### What we built

| File | Job |
|------|-----|
| `.github/workflows/gap-alert.yml` | Runs `check_gaps.py` every 6 hours. If gaps > 90 min, opens a GitHub issue (or comments on an existing one). |
| `README.md` | Now explains what Myriad is, how to run it, project layout. |
| `Makefile` | `make ingest`, `make check-gaps` work now; `backtest`, `simulate`, `publish` are stubs for later. |

### Acceptance

PRD says: "deliberately break the logger, confirm an issue is opened, fix it." This can be tested by pushing to `main` and triggering the workflow manually via `workflow_dispatch`. The gap-alert will fire because there are already 12 real gaps in the captured data.

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
