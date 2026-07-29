# Myriad — Build Progress

Living notes. Updated as work happens.

---

## Day 5 — Friday 31 July

**Goal:** canonical team IDs so every source joins cleanly.

| Step | What | State |
|------|------|-------|
| 1 | `ref/teams.csv` | Done (41 clubs) |
| 2 | `ref/team_aliases.csv` | Done (161 aliases across football-data / understat / fpl / fbref / common) |
| 3 | `loaders/resolve_team.py` | Done — raises on unknown aliases |
| 4 | Promote staging → `matches` | Done |

### Acceptance

`SELECT COUNT(*) FROM matches WHERE home_team_id IS NULL OR away_team_id IS NULL` → **0**.
6,080 matches, 0 duplicate `match_id`s.

```bash
make resolve-teams
```

---

## Day 4 — Thursday 30 July

**Goal:** download historical Premier League results + odds into a staging table.

| Step | What | State |
|------|------|-------|
| 1 | `collectors/results.py` | Done |
| 2 | Parse Date, teams, goals, referee, odds | Done |
| 3 | Load raw into DuckDB `matches_staging` | Done |

### Results

- **16 seasons** (2010-11 → 2025-26), **6,080 matches**
- Closing odds on ~44% of rows (older seasons lack them — expected)

---

## Day 3 — Wednesday 29 July

Gap-alert workflow + Makefile + README. Acceptance verified:
[issue #1](https://github.com/trenchsheikh/myrid/issues/1) opened when gaps detected.

---

## Day 2 — Tuesday 28 July

DuckDB schema, idempotent crowd loader, gap checker.

---

## Day 1 — Monday 27 July

Crowd snapshot logger (`collectors/crowd.py` + GitHub Action).
