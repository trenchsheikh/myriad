# Feature / model-structure log

Method (prd.md M2/M3): add one change -> walk-forward -> keep only if held-out RPS
improves. Failed ideas are logged here on purpose.

| Date | Change | Window | RPS | vs baseline | Keep? | Notes |
|------|--------|--------|----:|------------:|:-----:|-------|
| 2026-07-29 | Global γ Dixon-Coles, hl=182.5d | tune 2015-08->2019-05 stride2 | 0.1922 | — | yes | Day 9-13 baseline; best of {60,90,182.5,365} |
| 2026-07-29 | Team-specific γ + partial pooling | — | — | — | deferred | Expected small/no gain; after full baseline scores |
| 2026-07-29 | Separate home/away attack & defence | — | — | — | deferred | High overfitting risk |
| 2026-07-29 | Travel distance × away interaction | — | — | — | blocked | Needs features/context.py (Day 16) |

## Decision rule

Keep a variant only if it beats the current best on **held-out** seasons
(2019-20 onward), not on the xi-tune window.
