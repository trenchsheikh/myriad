# Myriad — Day 2 Progress

Living notes. Updated as work happens.

**Goal:** wire Parquet snapshots into DuckDB, and prove whether the logger has big gaps.

---

## Status

| Step | What | State |
|------|------|-------|
| 0 | This progress file | Done |
| 1 | `db/schema.sql` | Done |
| 2 | `loaders/crowd_to_duck.py` | Done |
| 3 | Load real snapshots into `data/myriad.duckdb` | Done |
| 4 | `scripts/check_gaps.py` | Done |
| 5 | Run everything and confirm it works | Done (with a real finding — see below) |

**Day 2 code: complete.** Gap check is working, and it found real missing hours.

---

## What's happening now

Day 2 implementation finished. Waiting on your next instruction (Day 3, or commit, etc.).

---

## Plain-English: what we built

| File | Job |
|------|-----|
| `db/schema.sql` | Database blueprint (matches, crowd snapshots, predictions, teams) |
| `loaders/crowd_to_duck.py` | Reads hourly Parquet files → inserts new ones into DuckDB. Safe to run twice. |
| `scripts/check_gaps.py` | Fails if any two consecutive captures are more than 90 minutes apart |
| `data/myriad.duckdb` | Local database (gitignored) with everything loaded so far |

---

## How to run it yourself

```bash
# 1. Pull latest snapshots from the data branch (local only; not committed to main)
git fetch origin data
git checkout origin/data -- data/raw/crowd

# 2. Load into DuckDB
uv run python -m loaders.crowd_to_duck

# 3. Check for gaps
uv run python scripts/check_gaps.py
```

---

## Results from today's run

- **29** snapshot files loaded
- **16,330** player-rows in DuckDB (~563–564 players per hour)
- **Second load skipped all 29 files** (idempotent — no duplicates)
- **Gap check found 12 gaps** over 90 minutes (longest ~222 min)

### Why gaps exist

GitHub Actions sometimes delays or skips scheduled jobs. The `:00` / `:30` redundancy helps, but hours still go missing. Day 3's job is to **alert** when that happens (open a GitHub issue automatically).

This is exactly why the PRD starts with the logger: missed hours are gone forever.

---

## Bug fixed along the way

DuckDB was converting UTC timestamps to local UK time (BST) on insert, so a second load thought every hour was "new" and doubled the data. Fix: store **naive UTC** wall-clock times. Reloads now correctly skip.

---

## What's next (Day 3)

1. `.github/workflows/gap-alert.yml` — run `check_gaps.py` every 6h, open an issue on failure
2. Expand `README.md`
3. `Makefile` stubs (`ingest`, `backtest`, `simulate`, `publish`)
4. Deliberately break the logger once to prove the alert works
