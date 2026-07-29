# Myriad — Build Progress

Living notes. Updated as work happens.

---

## Day 6 — Saturday 1 August

**Goal:** pull Understat team xG (2014-15 onward) and join onto `matches`.

| Step | What | State |
|------|------|-------|
| 1 | Research `soccerdata` Understat API + add dep | Done (soccerdata 1.9.1) |
| 2 | `collectors/understat.py` | Done |
| 3 | Join to `matches` on (date, home, away) | Done |
| 4 | Report join rate; investigate if &lt;98% | Done — **100%** |

### Results

- **4,560** Understat matches (12 seasons: 2014-15 → 2025-26)
- Exact date join: **99.43%** (4,534 / 4,560)
- **26** mismatches were postponed / date-boundary fixtures (football-data date vs Understat kickoff date off by 1 day)
- ±1-day fuzzy rescue → **100%** join rate
- `matches.home_xg` / `away_xg` populated; kickoff_utc filled from Understat where available

### How to run

```bash
make understat
# or reuse parquet: uv run python -m collectors.understat --from-parquet data/raw/understat/team_match_xg.parquet
```

### Note

Understat moved to AJAX JSON endpoints; soccerdata &lt;1.9 breaks. We pin `soccerdata>=1.9.1`.

### Due diligence (regression)

- `resolve_team --check-only` — all football-data names still resolve
- `crowd_to_duck` — idempotent skip of existing snapshots
- `check_gaps` — still correctly flags real CI gaps

---

## Day 5 — Friday 31 July

Canonical team IDs. 6,080 matches, 0 null team_ids, 0 duplicate `match_id`s.

---

## Day 4 — Thursday 30 July

16 seasons of football-data results → `matches_staging`.

---

## Day 3 — Wednesday 29 July

Gap-alert workflow. [Issue #1](https://github.com/trenchsheikh/myrid/issues/1) opened on gaps.

---

## Day 2 — Tuesday 28 July

DuckDB schema, idempotent crowd loader, gap checker.

---

## Day 1 — Monday 27 July

Crowd snapshot logger.
