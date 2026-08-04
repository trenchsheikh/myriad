# Myriad

**A Premier League season simulator that re-plays the rest of the season ten
thousand times every week, and publishes every prediction — timestamped,
git-pinned, and publicly scored.**

Built in the open. Predictions are append-only: once published, they are never
edited, re-fit, or quietly withdrawn. The scoreboard includes the misses.

[![Status](https://img.shields.io/badge/status-Day%2013%20%C2%B7%20M2%20complete-blue)](PROGRESS.md)
[![Backtest RPS](https://img.shields.io/badge/backtest%20RPS-0.2007%20(n%3D4180)-green)](docs/eval_full.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Licence](https://img.shields.io/badge/licence-MIT-lightgrey)](#licence)

---

## Table of contents

- [Research context](#research-context)
- [What it does](#what-it-does)
- [Current results](#current-results)
- [Method](#method)
- [Guarding against leakage](#guarding-against-leakage)
- [Why a cron job before a model](#why-a-cron-job-before-a-model)
- [Quick start](#quick-start)
- [Task shortcuts](#task-shortcuts)
- [Repository layout](#repository-layout)
- [Roadmap](#roadmap)
- [References](#references)
- [Licence](#licence)

---

## Research context

Myriad is a research project, and its methodology is deliberately modelled on
**Google DeepMind's TacticAI** ([blog][tacticai-blog] · Wang et al.,
*Nature Communications*, March 2024) — the AI assistant for football tactics
built with Liverpool FC.

TacticAI narrows all of football to corner kicks and asks three questions of
them: **prediction** ("for a given corner kick tactical setup, what will
happen?"), **retrieval** ("once a setup has been played, can we understand what
happened?"), and **generation** ("how can we adjust the tactics to make a
particular outcome happen?"). Each player is a node in a graph, and the network
is a variant of a Group Equivariant Convolutional Network that generates all
four reflections of the pitch and forces identical predictions across them —
which "reduces the search space of possible functions our neural network can
represent to ones that respect the reflection symmetry — and yields more
generalizable models, with less training data." Liverpool FC experts, blind to
which corners were real and which were generated, favoured TacticAI's
suggestions over the original setups **90% of the time**.

It is the clearest recent demonstration that football modelling can be done as
*science* rather than as punditry. Three things are borrowed from how that work
is framed:

| TacticAI | How Myriad applies it |
|----------|-----------------------|
| A narrow, sharply-posed question — corners only, ~10 per match, rather than "model football" | One question: the 1X2 outcome distribution for a scheduled fixture, and the season table it implies |
| Inductive bias matched to the domain — group equivariance, because a corner is invariant to reflection of the pitch and to relabelling of players | Inductive bias matched to the domain — Dixon-Coles bivariate Poisson, because goals are low-count, low scorelines are correlated, and team strength drifts over time |
| Structure chosen partly *because data is scarce* — symmetry buys generalisation from ~10 corners a match | Same pressure, same response — 4,180 matches is not much, so the model stays at ~2n+3 parameters with time decay rather than reaching for capacity |
| Evaluated blind against expert practitioners, not against a weak internal baseline | Evaluated against de-vigged bookmaker odds — the strongest publicly available forecaster of match outcomes |

That last row is the one that matters most. It is trivially easy to build a
football model that beats "always predict the home win" and present that as a
result. Myriad reports its Ranked Probability Score next to the closing betting
line on every one of 4,180 held-out matches, and the model is currently
**behind** that line. The number is published anyway — see
[Current results](#current-results).

[tacticai-blog]: https://deepmind.google/blog/tacticai-ai-assistant-for-football-tactics/

### What this project is *not*

Stated explicitly, because the comparison could otherwise mislead:

- **This is not a reimplementation of TacticAI.** Different problem, different
  data, different model class.
- **There is no player tracking data here.** TacticAI represents every player
  as a graph node with position, velocity and height. Myriad works from match
  results, xG, fixtures, and a public crowd signal — no positional data at all.
- **There is no retrieval or generation task here.** Myriad does prediction
  only. It cannot tell you *why* a result happened or how to change it.
- **There is no graph neural network here — yet.** The current model is a
  hand-specified statistical model with roughly `2n + 3` parameters, chosen
  because it is the correct baseline to beat before any learned representation
  earns its complexity. A learned model over the team-interaction graph is a
  candidate for M3+, and it ships only if it beats the number below on held-out
  seasons.

The influence is one of **research standard**, not of architecture: pose the
task precisely, encode what you actually know about the domain, hold out data
honestly, benchmark against the strongest available forecaster, and publish the
result whichever way it falls.

---

## What it does

1. **Collects** an hourly crowd signal from the official FPL API — transfer
   activity, ownership, price movement, availability flags. These fields have
   no history endpoint and are overwritten every gameweek.
2. **Builds** a historical spine: 15+ seasons of results joined to Understat xG
   at 100% coverage, with team names normalised across four different naming
   conventions.
3. **Fits** a time-weighted Dixon-Coles bivariate Poisson model for scorelines.
4. **Overlays** the crowd signal to test one specific hypothesis — that
   aggregated fantasy-manager behaviour carries match-outcome information not
   already priced into the betting market. (M4; not yet evaluated.)
5. **Simulates** the remainder of the season 10,000 times and publishes the
   resulting table distribution with a timestamp and git SHA.

---

## Current results

Full walk-forward backtest, 2015-16 → 2025-26, model version `dc-v0.1-hl182`.
Lower Ranked Probability Score (RPS) is better.

| Forecaster | n | RPS | Log loss | Brier |
|------------|--:|----:|---------:|------:|
| Opening line (de-vigged) | 4180 | **0.1955** | 0.9602 | 0.5690 |
| Closing line (de-vigged) | 2660 | **0.1968** | 0.9640 | 0.5717 |
| **Myriad `dc-v0.1-hl182`** | 4180 | **0.2007** | 0.9852 | 0.5809 |
| Season base rates (in-sample) | 4180 | 0.2322 | 1.0664 | 0.6451 |
| Always predict home win | 4180 | 0.4383 | 19.2277 | 1.1134 |

Bootstrap 95% CI on model RPS, resampling by season: **[0.1950, 0.2064]**
(11 seasons, 1,000 resamples). Per-season RPS ranges from 0.1866 (2018-19) to
0.2160 (2020-21).

**Reading this honestly:** a plain Dixon-Coles model landing ~0.005 RPS behind
the closing line is the expected and correct outcome. The market aggregates
team news, lineups, and money; the model currently sees only historical goals
and xG. If a bare bivariate Poisson *beat* the closing line across eleven
seasons, the first response would be to hunt for leakage, not to publish. That
gap is the budget the M3 feature layers have to close.

Full report: [`docs/eval_full.md`](docs/eval_full.md) ·
Calibration: [`docs/calibration.png`](docs/calibration.png) ·
Tuning: [`docs/xi_tune.md`](docs/xi_tune.md)

---

## Method

### The model

Dixon-Coles bivariate Poisson (Dixon & Coles, 1997), fit by maximum likelihood:

```
λ_home = exp(α_home + β_away + γ)
λ_away = exp(α_away + β_home)
```

- `α_i` — attack strength of team *i*
- `β_i` — defence weakness of team *i* (higher = concedes more)
- `γ` — home advantage, with a separate `γ_e` for behind-closed-doors fixtures,
  so the COVID seasons are given their own parameter rather than discarded
- `τ` — the Dixon-Coles low-score dependence correction, which repairs the
  independence assumption that plain Poisson gets wrong for 0-0, 1-0, 0-1, 1-1
- `ξ` — exponential time decay, `weight = exp(-ξ · days_ago)`

Identifiability is enforced by `Σα = 0`, reconstructing the final attack
parameter rather than leaving the likelihood flat along a ridge.

### Choosing the decay rate

The half-life behind `ξ` was tuned on **early seasons only**
(2015-08 → 2019-05), with everything from 2019-20 onward held back:

| Half-life (days) | ξ | RPS |
|-----------------:|--:|----:|
| **182.5** | 0.00380 | **0.1922** |
| 365.0 | 0.00190 | 0.1924 |
| 90.0 | 0.00770 | 0.1942 |
| 60.0 | 0.01155 | 0.1971 |

Roughly six months — short enough to track a squad's form, long enough not to
overreact to a three-game slump.

### The walk-forward harness

For every matchday `D` in the test range:

1. Build the training set from matches with `asof_ts < D` — strictly before.
2. Run the leakage assertions (below). A violation raises; it does not warn.
3. Fit Dixon-Coles from scratch on that training set.
4. Predict every fixture scheduled on `D`.
5. Append-only insert into `predictions`, stamped with model version and git SHA.

No refitting on future data, no rolling a single fit across its own boundary.

### The feature decision rule

Every proposed feature is added one at a time, run through the full
walk-forward, and kept **only if it improves held-out RPS from 2019-20 onward** —
not on the tuning window. Rejected ideas stay in
[`docs/feature_log.md`](docs/feature_log.md) with their numbers, on purpose. A
log that records only the wins is a log that lies about the search.

---

## Guarding against leakage

`backtest/leakage.py` implements each rule as a runtime assertion inside the fit
loop, not as a comment in a design doc:

1. No training match on or after the prediction timestamp.
2. **Closing odds are never a feature.** They are benchmark-only, and the column
   names are hard-blocked from any feature matrix.
3. xG values are as-published, never later revisions.
4. No end-of-season aggregates (final position, season points, goal difference).
5. Weather uses forecasts at a fixed lead time, never observed conditions.
6. Any text fed to a language model must be timestamped before kickoff.

Benchmarking against the market while accidentally training on the market is the
most common way a football model produces a beautiful, meaningless backtest.
Rules 1 and 2 exist to make that failure loud.

---

## Why a cron job before a model

Day 1 of this project shipped an hourly logger and nothing else — no schema, no
model, no notebook.

The FPL crowd fields have no history endpoint. They overwrite themselves. An
hour that is not captured is permanently unrecoverable, and no amount of later
cleverness gets it back. Everything else in this repository can be rebuilt from
public sources at any time; the crowd signal cannot. So collection started
before anything that depends on it existed.

`scripts/check_gaps.py` fails CI if any capture gap exceeds 90 minutes.

---

## Quick start

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
# Install dependencies
uv sync

# Pull captured snapshots from the data branch
git fetch origin data
git checkout origin/data -- data/raw/crowd

# Load into DuckDB
uv run python -m loaders.crowd_to_duck

# Verify capture continuity (fails if any gap > 90 minutes)
uv run python scripts/check_gaps.py
```

Reproduce the headline number:

```bash
# 1. Grid-search the decay half-life on early seasons only
uv run python scripts/tune_xi.py

# 2. Full walk-forward, 2015-16 -> 2025-26
uv run python -m backtest.walkforward \
    --start 2015-08-01 --end 2026-05-31 --half-life 182.5

# 3. Score against the de-vigged odds benchmarks
uv run python scripts/score_backtest.py \
    --model-version dc-v0.1-hl182 --report docs/eval_full.md

# 4. Calibration plot
uv run python scripts/plot_calibration.py
```

---

## Task shortcuts

`make` is not installed on Windows by default — use `.\tasks.ps1`, or the
`uv run` commands directly.

| Task | Windows (PowerShell) | macOS / Linux |
|------|----------------------|---------------|
| Crowd ingest | `.\tasks.ps1 ingest` | `make ingest` |
| Results | `.\tasks.ps1 results` | `make results` |
| Resolve teams | `.\tasks.ps1 resolve-teams` | `make resolve-teams` |
| Understat xG | `.\tasks.ps1 understat` | `make understat` |
| Fixtures | `.\tasks.ps1 fixtures` | `make fixtures` |
| Gap check | `.\tasks.ps1 check-gaps` | `make check-gaps` |
| Data audit | `.\tasks.ps1 audit` | `make audit` |
| Full load | `.\tasks.ps1 load` | `make load` |
| Fit Dixon-Coles | `.\tasks.ps1 fit-dc` | `make fit-dc` |
| Backtest smoke (5 matchdays) | `.\tasks.ps1 backtest` | `make backtest` |
| ξ tune | `.\tasks.ps1 tune-xi` | `make tune-xi` |
| Full backtest (2015-26) | `.\tasks.ps1 full-backtest` | see Quick start |
| Calibration plot | `.\tasks.ps1 calibrate` | `make calibrate` |
| Score predictions | `.\tasks.ps1 score` | `make score` |

---

## Repository layout

```
collectors/    Data collection — crowd.py runs hourly in CI
  crowd.py       FPL crowd signal (ephemeral: capture it or lose it)
  results.py     Historical results and odds
  understat.py   Understat xG
  fixtures.py    Forward fixture list
loaders/       Parquet -> DuckDB ingestion, idempotent
  resolve_team.py  Name normalisation across four naming conventions
db/            DuckDB schema (matches, crowd_snapshots, predictions, fixtures)
models/        Dixon-Coles fit; score matrix -> 1X2 projection
backtest/      Walk-forward harness and the leakage assertions
eval/          RPS / log loss / Brier, and de-vigged odds benchmarks
scripts/       Checks, tuning, scoring, plots
ref/           Team aliases, canonical team list, stadium coordinates
docs/          Eval reports, tuning results, calibration, feature log
data/          Captured snapshots (on the `data` branch); local DuckDB gitignored
```

---

## Roadmap

| Milestone | Content | State |
|-----------|---------|-------|
| M0 | Hourly logger, schema, gap alerting | Done |
| M1 | Historical spine — results, xG, fixtures, name resolution | Done |
| M2 | Dixon-Coles baseline, walk-forward harness, RPS benchmarks | Done |
| M3 | Feature layers — availability, fixture context, weather, referee | Next |
| M4 | Monte Carlo season simulator and the crowd overlay test | Planned |
| M5 | Publication surface and launch | Planned |
| M6 | Weekly in-season operations | Planned |

Running notes: [`PROGRESS.md`](PROGRESS.md) · Full spec: [`prd.md`](prd.md)

---

## References

- Wang, Z., Veličković, P., Hennes, D. *et al.* (2024). **TacticAI: an AI
  assistant for football tactics.** *Nature Communications* 15, 1906. Google
  DeepMind & Liverpool FC.
  - Announcement: <https://deepmind.google/blog/tacticai-ai-assistant-for-football-tactics/>
  - Paper: <https://www.nature.com/articles/s41467-024-45965-x>
- Dixon, M. J. & Coles, S. G. (1997). **Modelling Association Football Scores
  and Inefficiencies in the Football Betting Market.** *Journal of the Royal
  Statistical Society: Series C*, 46(2), 265–280.
- Epstein, E. S. (1969). **A Scoring System for Probability Forecasts of Ranked
  Categories.** *Journal of Applied Meteorology*, 8(6) — the origin of RPS, the
  metric used throughout this repository.

---

## Licence

MIT
