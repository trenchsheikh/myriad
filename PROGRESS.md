# Myriad — Build Progress

Living notes. Updated as work happens.

---

## Day 13 — Saturday 8 August

**Goal:** full walk-forward, tune ξ on early seasons, calibration plot.

| Step | What | State |
|------|------|-------|
| 1 | ξ grid search (early seasons only) | Done — best **182.5d** |
| 2 | Full backtest 2015-16 → 2025-26 | Done — **4,180** preds |
| 3 | Calibration plot + feature_log | Done |

### ξ tune (2015-08 → 2019-05, stride 2)

| half-life | RPS |
|----------:|----:|
| **182.5** | **0.1922** ← best |
| 365 | 0.1924 |
| 90 | 0.1942 |
| 60 | 0.1971 |

### Full backtest results (`dc-v0.1-hl182`)

| Source | RPS | n |
|--------|----:|--:|
| Model | **0.2007** | 4180 |
| Closing de-vig | 0.1968 | 2660 |
| Opening de-vig | 0.1955 | 4180 |
| Base rates | 0.2322 | 4180 |

Bootstrap RPS 95% CI: **[0.1950, 0.2064]** (11 seasons).

In the PRD ballpark (0.19–0.21). Slightly behind closing line — expected; if we beat it across ten seasons we'd hunt leakage.

```powershell
.\tasks.ps1 tune-xi
.\tasks.ps1 full-backtest
.\tasks.ps1 calibrate
uv run python scripts/score_backtest.py --model-version dc-v0.1-hl182 --report docs/eval_full.md
```

Artefacts: `docs/xi_tune.md`, `docs/eval_full.md`, `docs/calibration.png`, `docs/feature_log.md`.

### Prior commit note

Nothing pending before Day 13 — import-path fix already pushed; Day 8 audit still PASSED.

---

## Day 12

RPS metrics + de-vig benchmarks.

---

## Days 1–11

Logger → data spine → Dixon-Coles → walk-forward harness.
