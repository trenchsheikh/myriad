# Myriad

A Premier League season simulator that plays out the rest of the season
ten thousand times every week and publishes every prediction publicly
scored — built live, in the open.

## What it does

1. **Collects** an hourly crowd signal from FPL — transfer activity, ownership,
   availability — fields that have no history endpoint and reset every gameweek.
2. **Fits** a Dixon-Coles model on 15+ seasons of results and xG data.
3. **Overlays** the crowd signal to test whether aggregated fantasy-manager
   behaviour contains match-outcome information not already priced into
   betting markets.
4. **Simulates** the remaining season 10,000 times and publishes every
   prediction with a timestamp and git SHA — publicly scored, never edited.

## Status

Day 5. Team name normalisation. See `PROGRESS.md`.

## Why a cron job before a model

The crowd signal fields have no history endpoint. They overwrite
themselves. Every hour not captured is permanently unrecoverable, so
collection starts before anything else exists.

## Quick start

```bash
# Install (requires Python 3.11+ and uv)
uv sync

# Pull snapshots from the data branch
git fetch origin data
git checkout origin/data -- data/raw/crowd

# Load into DuckDB
uv run python -m loaders.crowd_to_duck

# Check for capture gaps (fails if any gap > 90 minutes)
uv run python scripts/check_gaps.py

# Or use the Makefile shortcuts
make ingest        # load crowd data
make check-gaps    # run gap check
```

## Layout

- `collectors/` — data collection (crowd.py runs hourly in CI)
- `db/` — DuckDB schema
- `loaders/` — Parquet → DuckDB ingestion
- `scripts/` — checks and utilities
- `data/` — captured snapshots (on the `data` branch); local DuckDB is gitignored

## Licence

MIT
