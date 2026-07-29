# Myriad — Build Progress

Living notes. Updated as work happens.

---

## Day 12 — Friday 7 August

**Goal:** evaluation metrics + benchmarks.

| Step | What | State |
|------|------|-------|
| 1 | `eval/metrics.py` (RPS, log loss, Brier, calibration, bootstrap) | Done |
| 2 | `eval/benchmarks.py` (de-vig + naive baselines) | Done |
| 3 | `scripts/score_backtest.py` smoke | Done |

### Smoke scores (34 backtest preds, Aug 2024 only — not meaningful yet)

| Source | RPS |
|--------|----:|
| Model (`dc-v0.1`) | 0.163 |
| Closing de-vig | 0.165 |
| Opening de-vig | 0.160 |
| Base rates (in-sample) | 0.246 |
| Home-always | 0.471 |

Tiny sample — Day 13 full backtest is the real test. Ballpark for a competent DC is RPS ~0.19–0.21 over many seasons.

```powershell
.\tasks.ps1 score
```

Shin de-vig noted as a later refinement (proportional used for now).

### Schedule / diligence

Day 8 audit still **PASSED**. Ahead of PRD calendar (Day 12 = 7 Aug).

---

## Day 11 — Thursday 6 August

Walk-forward harness + leakage assertions. Smoke: 5 matchdays.

---

## Days 9–10

Dixon-Coles + score matrix.

---

## Day 8

Data audit PASSED. M1 complete.

---

## Days 1–7

Logger → DuckDB → results → teams → xG → stadiums/fixtures.
