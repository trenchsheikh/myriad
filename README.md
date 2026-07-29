# Myriad

A Premier League season simulator that plays out the rest of the season
ten thousand times every week and publishes every prediction publicly
scored — built live, in the open.

## Status

Day 2. Schema + DuckDB loader + gap checker. See `PROGRESS.md`.

## Why a cron job before a model

The crowd signal fields have no history endpoint. They overwrite
themselves. Every hour not captured is permanently unrecoverable, so
collection starts before anything else exists.

## Layout

- `collectors/` — data collection
- `db/` — DuckDB schema
- `loaders/` — Parquet → DuckDB
- `scripts/` — checks and utilities
- `data/` — captured snapshots (on the `data` branch); local DuckDB is gitignored

## Licence

MIT
