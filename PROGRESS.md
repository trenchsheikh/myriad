# Myriad — Build Progress

Living notes. Updated as work happens.

---

## Day 11 — Thursday 6 August

**Goal:** walk-forward backtest harness with hard leakage assertions.

| Step | What | State |
|------|------|-------|
| 1 | `backtest/walkforward.py` | Done |
| 2 | `backtest/leakage.py` (assertions, not comments) | Done |
| 3 | Smoke-run (5 matchdays, 2024-08) | Done — 17 preds written |

### Leakage checklist

| Guard | Status |
|-------|--------|
| No training match on/after prediction timestamp | Asserts (verified fires) |
| Closing odds never a feature | Asserts (verified fires) |
| xG not later revisions | Asserts (blocks `*revis*xg*`) |
| No end-of-season aggregates | Asserts (forbidden names) |
| Observed weather blocked | Asserts (forbidden names) |
| LLM inputs timestamped | Asserts when records passed |

### Smoke results

- 5 matchdays, 17 predictions, `model_variant='backtest'`, append-only
- Mean p_home ≈ 0.46
- Warm-start across matchdays for faster refits

```powershell
.\tasks.ps1 backtest
# full season later:
# uv run python -m backtest.walkforward --start 2015-08-01 --end 2026-05-31
```

### Schedule

PRD Day 11 = 6 Aug; ran 29 Jul — **ahead of schedule**. Audit still PASSED.

---

## Days 9–10

Dixon-Coles (γ=1.20 / γ_empty=1.03) + score matrix.

---

## Day 8

Data audit PASSED. M1 complete.

---

## Days 1–7

Logger → DuckDB → results → teams → xG → stadiums/fixtures.
