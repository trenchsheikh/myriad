# Myriad — Build Progress

Living notes. Updated as work happens.

---

## Day 7 — Sunday 2 August

**Goal:** stadium lat/lon + 2026-27 fixture list with canonical team IDs.

| Step | What | State |
|------|------|-------|
| 1 | `ref/stadiums.csv` | Done (42 clubs, incl. historical + Coventry) |
| 2 | `collectors/fixtures.py` | Done |

### Results

- **2026-27 FPL squad** includes newly promoted **Coventry** (+ Hull, Ipswich, Leeds, Sunderland)
- Added `coventry` to `ref/teams.csv` + FPL aliases
- **380 fixtures** loaded into `fixtures` (GW1–38, all unfinished; GW1 kicks off 2026-08-21)
- All **20** current PL clubs have stadium coordinates
- Stadium coords also filled for every club appearing since 2010

```bash
make fixtures
```

### Due diligence

- Fixtures: 0 null team_ids
- Prior pipelines still green (resolve-teams, understat re-join)

---

## Day 6 — Saturday 1 August

Understat xG for 2014-15 → 2025-26. Exact join 99.43%; ±1-day rescue → **100%** (4,560/4,560).

```bash
make understat
```

---

## Day 5 — Friday 31 July

Canonical team IDs. 6,080 matches, 0 null team_ids.

---

## Day 4 — Thursday 30 July

16 seasons of football-data results → `matches_staging`.

---

## Day 3 — Wednesday 29 July

Gap-alert workflow. [Issue #1](https://github.com/trenchsheikh/myrid/issues/1).

---

## Day 2 — Tuesday 28 July

DuckDB schema, crowd loader, gap checker.

---

## Day 1 — Monday 27 July

Crowd snapshot logger.
