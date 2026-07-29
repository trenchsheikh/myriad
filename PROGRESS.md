# Myriad — Build Progress

Living notes. Updated as work happens.

---

## Day 8 — Monday 3 August

**Goal:** full DuckDB load + data audit; fix anything the audit surfaces.

| Step | What | State |
|------|------|-------|
| 0 | Due diligence on Days 1–7 | Done |
| 1 | `scripts/full_load.py` | Done |
| 2 | `notebooks/01_data_audit.ipynb` + `scripts/data_audit.py` | Done |
| 3 | Fix audit findings | Done — none blocking |

### Acceptance — PASSED

| Check | Result |
|-------|--------|
| ≥15 seasons of results | **16** |
| ≥10 seasons with xG | **12** (100% of 2014-15+) |
| Unresolved team names | **0** |
| Duplicate `match_id`s | **0** |

### Audit notes (not failures)

- Missing closing odds: 56% — expected; Bet365 closing columns only from ~2019-20
- Opening odds: 100% coverage
- Crowd logger still has real CI gaps (tracked in [issue #1](https://github.com/trenchsheikh/myrid/issues/1))

### How to run (Windows)

```powershell
.\tasks.ps1 load    # full rebuild (reuses cached downloads)
.\tasks.ps1 audit   # acceptance checks + writes notebooks/01_data_audit_report.md
```

### Also this session

- Fixed `tasks.ps1` so Python logging on stderr no longer aborts PowerShell
- Added `load` / `audit` task targets

**M1 (Historical spine) complete.** Next is M2 Day 9 — Dixon-Coles baseline.

---

## Day 7 — Sunday 2 August

Stadiums (42 clubs) + 380 FPL fixtures for 2026-27. Coventry registered.

---

## Day 6 — Saturday 1 August

Understat xG join **100%** (4,560/4,560).

---

## Day 5 — Friday 31 July

Canonical team IDs. 6,080 matches, 0 null team_ids.

---

## Days 1–4

Logger → DuckDB/gaps → gap-alert → football-data staging.
