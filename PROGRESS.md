# Myriad — Build Progress

Living notes. Updated as work happens.

---

## Day 10 — Wednesday 5 August

**Goal:** score matrix → 1X2 / BTTS / Over 2.5 probabilities.

| Step | What | State |
|------|------|-------|
| 1 | `models/score_matrix.py` | Done |
| 2 | Assert 1X2 sums to 1 within 1e-9 | Done |

Sample (fitted model): Liverpool vs Man United → p_home≈0.45, p_draw≈0.25, p_away≈0.31.

---

## Day 9 — Tuesday 4 August

**Goal:** Dixon-Coles baseline with empty-stadium home-advantage correction.

| Step | What | State |
|------|------|-------|
| 1 | `crowd_present` on matches | Done (False for 2020-06-17 → 2021-05-16) |
| 2 | `models/dixon_coles.py` | Done (vectorised NLL, L-BFGS-B) |
| 3 | Smoke-fit | Done |

### Fit sanity check (2014-15 → 2025-26, 4,560 matches)

| Param | Value | Notes |
|-------|-------|-------|
| γ (crowd) | **1.203** | normal home advantage |
| γ_empty | **1.029** | collapsed — COVID correction working |
| ρ | -0.119 | low-score dependence |
| ξ | ln2/182.5 | ~6-month half-life |

Top strengths: Arsenal, Man City, Liverpool. Empty-stadium γ near 1.0 confirms the PRD warning.

```powershell
.\tasks.ps1 fit-dc
```

---

## Day 8 — Monday 3 August

Data audit **PASSED**. M1 complete.
16 seasons, 12 with xG (100%), 0 null teams, 0 duplicate match_ids.

```powershell
.\tasks.ps1 load
.\tasks.ps1 audit
```

---

## Days 1–7

Logger → DuckDB/gaps → gap-alert → results → team IDs → Understat xG → stadiums/fixtures.
