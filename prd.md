# Myriad — Build PRD

**Version:** 1.0
**Date:** 27 July 2026
**Hard deadline:** Friday 21 August 2026, 18:30 BST (Premier League GW1 kickoff)
**Days available:** 26

---

## 1. What Myriad is

A Premier League season simulator that plays out the remainder of the season ten thousand times every week and publishes every prediction publicly scored — built live, in the open, on a crowd signal nobody else is collecting.

### Goals

1. **Research with publicity value.** Test a specific, pre-registered hypothesis: does aggregated fantasy-manager transfer behaviour contain match-outcome information not already priced into betting markets?
2. **Reach.** Build a football-fan audience through bold, falsifiable, publicly-scored predictions.
3. **Funnel to Ora.** Every public artefact shows the machine being built, not just its output.

### Non-goals

- Not a betting product. Odds are a benchmark, never a call to action.
- Not FPL-branded. FPL is an input; the letters never appear in fan-facing content.
- Not a paid product before November. Track record first.

### The one design rule

**Every football post shows the build, not just the number.** A prediction without visible machinery builds an audience that will never convert. If a week's content contains no visible engineering, that week failed regardless of its metrics.

---

## 2. Success criteria

| Horizon | Criterion |
|---|---|
| 21 Aug | Full predicted table + all GW1 fixture probabilities published and timestamped before 18:30 BST |
| 21 Aug | Pre-registration document committed to git before first kickoff |
| 21 Aug | ≥8 seasons of walk-forward backtest published with confidence intervals |
| Ongoing | Zero missed hours in the crowd snapshot log |
| Dec | Calibration within 3pp across probability bins |
| Dec | Base vs crowd-overlay comparison reported honestly, including if the overlay fails |

**Explicitly not a success criterion:** beating the closing line. You probably won't overall. The finding is *where* you diverge and who's right there.

---

## 3. Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 | Ecosystem |
| Deps | `uv` | Fast, lockfile-based |
| Storage | DuckDB + Parquet | Single file, columnar, no server, fits 16GB |
| Modelling | `scipy`, `numpy`, `pandas` | Dixon-Coles is an optimisation problem, not deep learning |
| Scraping | `soccerdata` | Wraps FBref, Understat, football-data |
| Scheduling | GitHub Actions | Runs when your PC doesn't |
| Site | Next.js on Vercel | Static gen from JSON export |
| LLM | Ollama, 8B at 4-bit | Post-launch, not critical path |

**Hardware note:** GTX 1660 Ti with 6GB VRAM. Nothing in the critical path needs a GPU — Dixon-Coles fits on CPU in seconds, and 10,000 season simulations is vectorised numpy. The LLM layer is the only GPU consumer and it is deliberately post-launch so VRAM constraints cannot block the 21 August deadline.

---

## 4. Data sources

| Source | Access | Cadence | Purpose |
|---|---|---|---|
| football-data.co.uk | `E0.csv` per season | Weekly | Results, opening + closing odds, 1993→ |
| Understat | `soccerdata` | Post-match | Team xG per match, 2014-15→ |
| FBref | `soccerdata` | Post-match | Shot-level data, squad stats |
| FPL API | `bootstrap-static/`, `fixtures/` | **Hourly** | Crowd signal, availability flags |
| Open-Meteo Previous Runs | REST, no key | On demand | Historical forecasts at fixed lead time |

### Critical: the ephemerality problem

`transfers_in_event` and `transfers_out_event` reset every gameweek. `selected_by_percent` is a current snapshot only. **There is no history endpoint.** An hour not captured is an hour that never existed and can never be recovered.

This is why M0 Day 1 is the logger and nothing else.

---

## 5. Schema

```sql
CREATE TABLE matches (
  match_id      VARCHAR PRIMARY KEY,
  season        VARCHAR,
  match_date    DATE,
  kickoff_utc   TIMESTAMP,
  home_team_id  VARCHAR,
  away_team_id  VARCHAR,
  home_goals    INTEGER,
  away_goals    INTEGER,
  home_xg       DOUBLE,
  away_xg       DOUBLE,
  referee       VARCHAR,
  odds_open_h   DOUBLE, odds_open_d DOUBLE, odds_open_a DOUBLE,
  odds_close_h  DOUBLE, odds_close_d DOUBLE, odds_close_a DOUBLE
);

CREATE TABLE crowd_snapshots (   -- APPEND ONLY
  captured_at        TIMESTAMP,
  player_id          INTEGER,
  team_id            VARCHAR,
  position           VARCHAR,
  price              INTEGER,
  ownership_pct      DOUBLE,
  transfers_in_ev    INTEGER,
  transfers_out_ev   INTEGER,
  play_chance_pct    INTEGER,
  news               VARCHAR,
  news_added         TIMESTAMP
);

CREATE TABLE predictions (       -- APPEND ONLY, NEVER UPDATED
  prediction_id   VARCHAR PRIMARY KEY,
  created_at      TIMESTAMP,
  model_version   VARCHAR,
  model_variant   VARCHAR,       -- 'base' | 'crowd' | 'live'
  match_id        VARCHAR,
  p_home          DOUBLE, p_draw DOUBLE, p_away DOUBLE,
  p_btts          DOUBLE, p_over25 DOUBLE,
  is_locked       BOOLEAN,
  git_sha         VARCHAR
);

CREATE TABLE teams (
  team_id VARCHAR PRIMARY KEY,
  canonical_name VARCHAR,
  stadium_lat DOUBLE,
  stadium_lon DOUBLE
);

CREATE TABLE team_aliases (
  alias VARCHAR, source VARCHAR, team_id VARCHAR
);
```

**Two tables are append-only and must never be updated in place:** `crowd_snapshots` and `predictions`. The immutability of `predictions` is the entire basis of the public scorecard's credibility. Enforce it in code, not by discipline.

---

## 6. Season output specification

Each simulator iteration produces a complete final table. Aggregating across 10,000 iterations turns every column of that table into a distribution.

### Per-team outputs

| Field | Type | Notes |
|---|---|---|
| `points_mean` / `points_median` / `points_mode` | Distribution | Median is the headline |
| `points_p05` / `points_p95` | Interval | 90% credible interval |
| `gf_mean` / `ga_mean` / `gd_mean` | Distribution | Accumulated from sampled scorelines |
| `wins` / `draws` / `losses` | Distribution | Counted per iteration |
| `position_histogram` | 20-element array | P(finishing 1st…20th) |
| `p_title` / `p_top4` / `p_top6` / `p_relegation` | Probability | Slices of the position histogram |
| `clean_sheets_mean` | Distribution | Iterations where opponent scored zero |

### The headline table

Publish the **median** table, not the mean table.

A mean table is not a real table: two clubs can both average 4.3rd, which is not a ranking, and the averaged table corresponds to no single simulated season. Means are a diagnostic only.

Every published row carries its interval. The headline unit is:

> Arsenal — 78 pts (90% CI: 64–89), most likely finish 2nd, title 22%

### Storage

```sql
CREATE TABLE sim_runs (
  run_id VARCHAR PRIMARY KEY, run_at TIMESTAMP,
  model_variant VARCHAR, gameweek INTEGER,
  n_iterations INTEGER, git_sha VARCHAR
);

CREATE TABLE sim_fixture_results (   -- rolling 4-week retention
  run_id VARCHAR, iteration INTEGER, match_id VARCHAR,
  home_goals INTEGER, away_goals INTEGER
);

CREATE TABLE sim_final_tables (      -- retained permanently
  run_id VARCHAR, iteration INTEGER, team_id VARCHAR,
  points INTEGER, gf INTEGER, ga INTEGER, position INTEGER
);
```

`sim_fixture_results` is 10,000 × ~370 rows per run — a few million rows, trivial for DuckDB, but it grows weekly. Keep four weeks rolling. `sim_final_tables` at 10,000 × 20 rows per run is small enough to keep forever, and it's what powers the what-if engine.

### Player-level outputs (post-launch)

The simulator allocates goals to **teams**, not players. Golden boot and assist races need a separate allocation layer:

`models/goal_allocation.py`
- Each player's historical share of team goals, shrunk toward positional means
- Weighted by projected minutes from the availability model
- For each iteration, distribute that team's sampled goals across the squad via a multinomial draw

Scheduled for late September, after the availability model is stable. High engagement value — the golden boot race is one of the most-argued questions in football — but strictly not critical path.

---

## 7. Weekly update mechanics

Three separate things change after each gameweek. Keeping them distinct is essential, both for correctness and because their *difference* is the best content the system produces.

### 7.1 The starting state (mechanical)

Before GW1, every club sits on zero and all 380 fixtures are unplayed. After GW1, ten results are **facts**. The simulator now starts from the real table and simulates only the remaining 370 fixtures. Played matches are no longer sampled.

This is pure bookkeeping and accounts for most of the visible movement in the projected table early on.

### 7.2 The ratings (belief update)

`models/dixon_coles.py` refits on Tuesday including the new matches, weighted by recency via the time-decay half-life ξ.

**Ratings move far less than people expect.** A single match is one observation among several hundred weighted ones. A 4-0 win might shift a team's attack rating by 1–3%.

This produces the system's sharpest early-season insight: **the table moves enormously while the model's beliefs barely move at all.** A club top after two games has banked real points but is, in the model's view, almost exactly the team it was in July.

Team strength estimates typically stabilise around 8–12 matches. Before that, the prior should dominate — and ξ is what controls how fast current-season evidence overrides it. Tuned too fast, the model declares a GW1 winner a title contender. Tuned too slow, it misses genuine change from a new manager or major transfers.

### 7.3 The remaining schedule (composition effect)

As fixtures are consumed, the *remaining* fixture list changes shape in two ways.

**Opponent quality.** A club that has already played its three hardest away trips has an easier run left than its points total suggests — so its projection can rise beyond what it banked.

**Home/away balance.** A team with 12 of its remaining 18 fixtures at home is in materially better shape than one with 6, independent of opponent quality. Expose `remaining_home` and `remaining_away` counts per team in the output — fans feel this intuitively but never see it quantified, which makes it a reliable weekly content beat.

### 7.4 Movement decomposition

Every week, diff the new projected table against last week's and attribute the change across the three causes above:

```
models/attribution.py
  Δ p_top4 = Δ from points banked vs expected
           + Δ from rating change
           + Δ from remaining schedule
```

Output format:

> Newcastle's top-four chance rose 6.1pp this week: +4.4 from banking three points against the odds, +0.9 because the model raised their defensive rating, +0.8 because two rivals' remaining fixtures got harder.

Nobody in fan-facing football content does this, and it directly satisfies the "show the machine" rule — the explanation *is* the model working.

---

## 8. What-if engine

Because per-iteration results are stored, conditional questions become queries rather than new simulations.

### 8.1 Two modes — and they are not the same thing

**Filtering (conditioning).** Select the subset of iterations where the specified result occurred, re-aggregate over that subset. Instant.

**Forcing (intervention).** Fix the specified result, resimulate every other fixture fresh. Slower — seconds — but causally clean.

The distinction matters. Filtering to iterations where Liverpool beat Arsenal also selects iterations where the random draws happened to favour Liverpool *everywhere else*, so the conditional table mildly overstates Liverpool. For a single fixture the contamination is small. For compound scenarios ("Arsenal win their next five") it is large and will produce visibly wrong answers.

**Rule:** filter for one or two conditions and fast interactive queries; force for anything compound or anything published as a headline.

**Sample-size guard:** if filtering leaves fewer than 200 matching iterations, fall back to forcing automatically. Conditioning on three specific results can easily reduce 10,000 iterations to a handful, and a table built from 12 samples is noise.

### 8.2 Match leverage

The genuinely novel output. For any fixture, compute:

```
leverage = P(outcome | home win) − P(outcome | away win)
```

…for each of title, top four, relegation. Rank the weekend's fixtures by leverage.

That produces "the most important match this weekend isn't the one you think" — a repeatable, data-backed, argument-generating format available every single week for free.

### 8.3 API surface

```
GET /api/whatif?fixture={match_id}&result={H|D|A}
  → conditional table, deltas vs baseline, mode used

GET /api/leverage?gameweek={n}
  → fixtures ranked by title / top-four / relegation swing
```

### 8.4 Content formats this unlocks

- **Pre-match:** "here's exactly what this fixture is worth to both clubs"
- **Post-match:** "that result just moved four teams — here's the decomposition"
- **Milestone:** "your club needs X points from the remaining fixtures for a 50% top-four chance"

---

## M0 — Foundations
**27–29 July (3 days)**

### Day 1 — Monday 27 July: the logger, and nothing else

Everything else can wait. This cannot.

1. Create repo `myriad`. Python 3.11, `uv init`.
2. Write `collectors/crowd.py`:
   - `GET https://fantasy.premierleague.com/api/bootstrap-static/`
   - Extract per player: `id`, `team`, `element_type`, `now_cost`, `selected_by_percent`, `transfers_in_event`, `transfers_out_event`, `chance_of_playing_next_round`, `news`, `news_added`
   - Stamp with UTC capture time
   - Write to `data/raw/crowd/{YYYY-MM-DD}/{HH}.parquet` (~150–250KB/hour, ~2GB/year — acceptable in-repo)
3. Write `.github/workflows/crowd-logger.yml`:
   - `schedule: cron: '0 * * * *'` **and** a second job at `'30 * * * *'` as redundancy
   - Commits Parquet to a `data` branch
4. Push. Wait. **Verify two consecutive hourly snapshots landed, produced by Actions and not by your machine.**

> **Warning:** GitHub Actions scheduled workflows are delayed under platform load and are auto-disabled after 60 days of repository inactivity. The `:30` redundancy job covers delays. Set a calendar reminder to push a commit at least monthly, or move the logger to a £4/month VPS by October.

**Acceptance:** two timestamped Parquet files in the repo, both written by CI.

### Day 2 — Tuesday 28 July

1. `db/schema.sql` — the DDL above.
2. `loaders/crowd_to_duck.py` — idempotent Parquet → `crowd_snapshots` load. Must be safe to re-run.
3. Create `data/myriad.duckdb`, load everything captured so far.
4. Write `scripts/check_gaps.py` — asserts no gap >90 minutes in `captured_at`.

**Acceptance:** `check_gaps.py` passes on real captured data.

### Day 3 — Wednesday 29 July

1. `.github/workflows/gap-alert.yml` — runs `check_gaps.py` every 6h, opens a GitHub issue on failure.
2. `README.md`: what Myriad is, how to run it, MIT licence.
3. `Makefile`: `make ingest`, `make backtest`, `make simulate`, `make publish`.

**Acceptance:** deliberately break the logger, confirm an issue is opened, fix it.

**Content this milestone:** the pitch, and "why I started with a cron job instead of a model" — a genuinely good hook because it's the opposite of what everyone expects.

---

## M1 — Historical spine
**30 July – 3 August (5 days)**

### Day 4 — Thursday 30 July

1. `collectors/results.py` — download `E0.csv` for 2010-11 through 2025-26 from football-data.co.uk.
2. Parse: `Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, `Referee`, `B365H/D/A` (opening), `B365CH/CD/CA` (closing).
3. Load raw into a staging table. Do not normalise yet.

### Day 5 — Friday 31 July: team name normalisation

**Budget a full day. Everyone underestimates this and it silently corrupts every downstream join.**

The same club appears as "Man United" (football-data), "Manchester United" (Understat), "Man Utd" (FPL), "Manchester Utd" (FBref).

1. Build `ref/teams.csv` — canonical `team_id` + display name for every club appearing in any source since 2010.
2. Build `ref/team_aliases.csv` — every observed spelling mapped to a `team_id`.
3. Write `loaders/resolve_team.py` that **raises on an unknown alias** rather than silently dropping the row.
4. Run every source through it until zero exceptions.

**Acceptance:** a query returning any match row with a null `team_id` returns zero rows.

### Day 6 — Saturday 1 August

1. `collectors/understat.py` via `soccerdata` — team xG per match, 2014-15 onward.
2. Join to `matches` on (date, home_team_id, away_team_id).
3. Report join rate. Investigate anything below 98% — usually postponements and rescheduled fixtures.

### Day 7 — Sunday 2 August

1. `ref/stadiums.csv` — lat/lon for all 20 current PL grounds plus any ground used since 2010 (needed for weather and travel distance).
2. `collectors/fixtures.py` — pull the 2026-27 fixture list from the FPL fixtures endpoint, map to canonical `team_id`s.

### Day 8 — Monday 3 August

1. Full load into DuckDB.
2. `notebooks/01_data_audit.ipynb` — matches per season, xG coverage, missing odds, duplicate fixtures.
3. Fix everything the audit surfaces.

**Acceptance:** ≥15 seasons of results, ≥10 seasons with xG, zero unresolved team names, zero duplicate `match_id`s.

**Content:** the team-name problem is unexpectedly relatable — "I spent a full day on the fact that Manchester United has four names."

---

## M2 — Baseline model and backtest harness
**4–9 August (6 days)**

This milestone produces the thing you'll be judged on. The backtest harness matters more than the model.

### Day 9 — Tuesday 4 August

`models/dixon_coles.py`:

- Parameters: attack strength α and defence strength β per team, global home advantage γ, low-score correction τ, time-decay half-life ξ
- `λ_home = α_home × β_away × γ`, `λ_away = α_away × β_home`
- Negative log-likelihood over historical matches, weighted `exp(-ξ · days_ago)`
- Fit via `scipy.optimize.minimize` (L-BFGS-B), with sum-to-zero constraint on α to fix identifiability
- Start with ξ tuned to roughly a 6-month half-life; tune properly on Day 12

**Empty-stadium correction — do this on day one, not later.** Matches played behind closed doors (most of 2020-21, part of 2019-20) show a measurably collapsed home advantage. Add a `crowd_present` boolean to `matches` and fit γ separately for those fixtures. Without it, those seasons drag the global home advantage estimate down and silently distort every rating fitted across them.

Also check for a secular decline in home advantage across the full history. Time decay partially absorbs it, but verify rather than assume.

### Day 10 — Wednesday 5 August

`models/score_matrix.py`:

- Given λ_home, λ_away, produce an 11×11 Poisson score matrix with the Dixon-Coles low-score adjustment applied to the 0-0, 1-0, 0-1, 1-1 cells
- Collapse to `p_home`, `p_draw`, `p_away`, `p_btts`, `p_over25`
- Assert every probability set sums to 1.0 within 1e-9

### Day 11 — Thursday 6 August: the walk-forward harness

**This is the single most important file in the repo.**

`backtest/walkforward.py`:

- For each matchday D in the test range: fit using only matches with `kickoff_utc < D`, predict D's fixtures, store to `predictions` with `model_variant='backtest'`
- **Never** pass future data into the fit. Assert it: the harness should raise if any training row has `kickoff_utc >= D`.

**Leakage checklist — implement each as an assertion, not a comment:**

- [ ] No training match on or after the prediction timestamp
- [ ] Closing odds never used as a feature (opening odds only; closing odds are benchmark-only)
- [ ] xG values are as-published, not later revisions
- [ ] No end-of-season aggregates as features
- [ ] Weather uses forecasts at fixed lead time, never observed values
- [ ] Any text fed to an LLM is timestamped before kickoff

### Day 12 — Friday 7 August

`eval/metrics.py`:

- **Ranked Probability Score** (the standard metric for 1X2 forecasting) — this is your headline number
- Log loss, Brier score
- Calibration: bin predictions in 5pp buckets, plot predicted vs realised frequency
- Bootstrap confidence intervals over seasons (1,000 resamples)

`eval/benchmarks.py`:

- De-vig closing odds to true probabilities (start with proportional normalisation; note Shin's method as a later refinement)
- Naive baselines: fixed home/draw/away base rates, and home-team-always

### Day 13 — Saturday 8 August

- Run the full backtest, 2015-16 → 2025-26
- Tune ξ by grid search **on early seasons only**, evaluate on later ones
- Produce the calibration plot

**Home/away structure variants.** Test these in order, each against the walk-forward backtest, keeping only what improves held-out RPS:

1. **Global γ** (baseline, as specced)
2. **Team-specific γ with partial pooling** — shrink each club's home advantage hard toward the league mean. Twenty extra parameters on 19 home matches per club per season will learn noise unless heavily regularised. Expect small or no gain; team-level home advantage is largely non-persistent season to season.
3. **Separate home and away attack/defence ratings** — four parameters per team rather than two, capturing sides that play expansively at home and conservatively away. Real but modest effect, high overfitting risk.
4. **Travel distance × away interaction** — long away trips plausibly cost more than short ones. Cheap to test once `features/context.py` exists on Day 16.

Log all four outcomes in `docs/feature_log.md` whether they survive or not. "Team-specific home advantage turned out to be noise" is a legitimate finding and a good video.

**Ballpark for orientation:** a competent Dixon-Coles on xG typically lands around RPS 0.19–0.21; de-vigged closing lines sit a little below that. If you're materially better than the closing line across ten seasons, you have a bug, not an edge. Go looking for leakage.

### Day 14 — Sunday 9 August

- `docs/backtest_v1.md` — methodology, results table, calibration plot, confidence intervals
- Commit it. This is your first real research artefact.

**Acceptance:** RPS reported with CIs across ≥8 seasons vs. de-vigged closing odds, with a published calibration curve.

**Content:** "my model lost to the bookies and that's the point" — counter-programming against every account claiming a hot streak.

---

## M3 — Feature layers
**10–14 August (5 days)**

**Method for every feature in this milestone:** add it alone → rerun the walk-forward backtest → keep only if RPS improves on held-out seasons → log the result either way in `docs/feature_log.md`.

That log is the research output. Failed features are content, not waste.

### Day 15 — Monday 10 August: availability (highest value)

`models/player_value.py`:

- For each player, compute team xG-difference per 90 with and without them on the pitch
- Regularise heavily — ridge, or shrink toward the squad mean. Small samples will produce absurd values otherwise.
- Output: contribution in goals per 90, per player

`features/availability.py`:

- Join `crowd_snapshots.play_chance_pct` and `news` to the squad
- Team availability adjustment = Σ (contribution × (1 − play_chance))
- Apply as an offset to λ

### Day 16 — Tuesday 11 August: fixture context

`features/context.py`:

- Rest days since last fixture, per team
- Rest differential (home minus away) — often stronger than either alone
- European midweek involvement flag
- Travel distance: haversine between the two stadiums
- Kickoff hour bucket (early / standard / evening / Monday)

### Day 17 — Wednesday 12 August: weather

`features/weather.py`:

- Open-Meteo **Previous Runs API** at a fixed 48-hour lead time
- Query per stadium lat/lon at kickoff hour
- Variables: `precipitation`, `wind_speed_10m`, `temperature_2m`
- Forecast archive coverage begins around 2022 — restrict weather backtests to seasons within coverage and say so

> Never use the Historical Weather (ERA5 reanalysis) endpoint for features. It contains what actually happened, not what was forecast. Using it will inflate your backtest and quietly break live performance.

Expect a small effect, concentrated in goal totals rather than match result. Report the effect size honestly.

### Day 18 — Thursday 13 August: referee and shot profile

`features/referee.py` — historical cards and penalties per game by official, shrunk toward the league mean.

`features/shot_profile.py` — distribution of shot locations rather than aggregate xG. Two teams with equal xG can have very different chance profiles, and this is where the modelling edge actually lives.

### Day 19 — Friday 14 August

- Rerun the full backtest with all surviving features
- Write `docs/feature_log.md` — every feature tried, effect size, kept or dropped, and why
- Expect roughly half to fail. Momentum and form streaks in particular are well documented as overrated; test them so you can say so with data.

**Acceptance:** feature log published with at least three honest negative results.

---

## M4 — Simulator and crowd overlay
**15–18 August (4 days)**

### Day 20 — Saturday 15 August: Monte Carlo

`sim/monte_carlo.py`:

- Input: current table + all remaining fixtures + fitted ratings
- For each of 10,000 iterations, sample a scoreline per fixture from its score matrix, accumulate points and goal difference
- Fully vectorised numpy — 380 fixtures × 10,000 iterations should run in seconds, not minutes
- Outputs per team: P(title), P(top 4), P(top 6), P(relegation), expected points, full finish-position distribution
- **Persist per-iteration results** to `sim_fixture_results` and `sim_final_tables` (section 6). Aggregating and discarding the raw iterations is the one irreversible mistake in this milestone — the what-if engine is impossible without them.
- Assert the median table is published, not the mean table

### Day 21 — Sunday 16 August: promoted teams

The three promoted sides have no Premier League history and are the largest single error source in a pre-season table.

`models/promoted_prior.py`:

- Fit a prior from historical promoted-team first-season performance
- Optionally adjust by Championship finishing position and points
- Widen the uncertainty on these teams explicitly

This is a great video — everyone has an opinion about promoted teams and yours will be quantified.

### Day 22 — Monday 17 August: crowd overlay

`features/crowd.py`:

- Aggregate net transfers by team × position group
- Normalise by ownership base and hours-to-deadline (raw counts are meaningless — a 5% owned player and a 50% owned player move differently)
- Defender/keeper net flow → implied clean-sheet conviction
- Attacker net flow → implied scoring conviction
- Apply as an adjustment to λ

`features/news_leak.py`:

- Rolling z-score of transfer-out velocity per player
- Flag spikes with no corresponding `news_added` timestamp — the candidate early team-news signal

**Register `base` and `crowd` as separate model variants and run both, every week, all season.** This is the experiment. If the overlay loses, you report that.

### Day 23 — Tuesday 18 August

- Full pipeline dry run end to end
- Generate the 2026-27 predicted table
- Sanity check it against bookmaker outright odds — you're looking for *explainable* divergence, not agreement. Unexplainable divergence means a bug.

---

## M5 — Publication and launch
**19–21 August (3 days)**

### Day 24 — Wednesday 19 August

- Next.js app on Vercel, static generation from a DuckDB → JSON export
- Pages: predicted table, fixture predictions, scorecard (empty for now), methodology
- Brand: Myriad. Confirm handle availability across TikTok, Instagram, YouTube and the domain **before** publishing anything.

### Day 25 — Thursday 20 August

`docs/preregistration.md` — commit before a ball is kicked:

1. The hypotheses being tested, stated specifically
2. The metrics that will judge them (RPS, calibration, base vs crowd)
3. What would count as a null result
4. Commitment that predictions are append-only and never revised

Commit it. The git SHA and timestamp are the proof.

### Day 26 — Friday 21 August — **hard deadline 18:30 BST**

Work backwards from the deadline, not forwards from the morning.

- **09:00** — final refit on all data through 20 August
- **10:00** — generate GW1 predictions, all fixtures, both model variants
- **11:00** — run the season simulation, produce the predicted table
- **12:00** — write to `predictions` with `is_locked=true` and the git SHA
- **14:00** — publish to the site; verify the timestamp renders publicly
- **16:00** — post the launch content: full predicted table, contrarian calls flagged explicitly
- **18:30** — kickoff. Nothing changes after this point, ever.

**Acceptance:** a publicly visible, timestamped, immutable prediction set that predates the first kickoff of the season.

---

## M6 — Season operations
**From 22 August**

### Weekly cycle

| When | Job | Output |
|---|---|---|
| Hourly | Crowd logger | Snapshot |
| Mon 09:00 | Ingest results, score last week, update scorecard | Scorecard + movers post |
| Tue 09:00 | Refit ratings, rerun simulation | Updated table probabilities |
| Thu 09:00 | Generate next predictions, draft copy | Draft content |
| Fri T−24h | **Lock and publish** | Immutable prediction |
| Matchday T−1h | Live model rerun after lineups | Unscored content post |

### The two-clock rule

The **locked** model is scored. The **live** model (which updates through team news and confirmed lineups) is content only and is never scored publicly. Confirmed lineups arrive roughly an hour before kickoff and represent the single largest information jump of the week — which makes it the best content moment and the worst thing to allow into your scorecard.

Label them differently on the site. If those two ever blur, the scorecard becomes worthless.

### Post-launch backlog

Ordered. Nothing here is allowed to touch the critical path before 21 August.

1. **Movement attribution** (section 7.4) — first thing after GW1, since it needs two consecutive runs to diff. Highest content value per hour of work in the entire backlog.
2. **What-if engine and match leverage** (section 8) — filtering mode first, forcing mode second.
3. **Goal allocation model** (section 6) — golden boot and assist races, late September, after availability is stable.
4. **LLM feature extraction** — press conferences and injury reports → structured availability records. Ollama, 8B at 4-bit, ~5GB VRAM. Tight on a 1660 Ti; test before committing to it. Backtest only on text timestamped before kickoff.
5. **LLM narration** — match previews and movers copy from model output. Never predictions.
6. **Text-to-SQL over DuckDB** — natural-language questions against your own data, which is also a strong demo for Ora.
7. **Shin's method** for de-vigging, replacing proportional normalisation.
8. **Event-sequence transformer** (v2, Oct/Nov) — the flagship technical content piece, once the pipeline is stable.

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Missed crowd snapshots | **Critical** — unrecoverable | Dual cron, gap alerting, VPS migration by Oct |
| Look-ahead bias in backtest | **Critical** — invalidates everything | Assertions in the harness, not discipline |
| Team name normalisation eats days | High | Budget the full day (Day 5), fail loudly on unknowns |
| Scope creep before 21 Aug | High | Nothing ships that isn't needed to lock a prediction on the 21st |
| Crowd overlay finds nothing | Medium | Pre-register it; the null is a publishable result |
| 6GB VRAM limits LLM | Low | LLM is post-launch by design |
| Single season proves nothing | Certain | Say so loudly and early; report CIs always |

---

## The thing to remember

380 matches is a tiny sample. A great model and a mediocre one are often statistically indistinguishable over a single season, and you will have stretches where you look brilliant and stretches where you look foolish — neither of which will mean much.

Pre-register, report confidence intervals, publish the failures. That posture is what separates this from every other account claiming their AI predicts football — and it is also, conveniently, the more interesting story.