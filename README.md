# Myriad

A Premier League season simulator that plays out the rest of the season
ten thousand times every week and publishes every prediction publicly
scored — built live, in the open.

## Status

Day 1. Crowd snapshot logger only.

## Why a cron job before a model

The crowd signal fields have no history endpoint. They overwrite
themselves. Every hour not captured is permanently unrecoverable, so
collection starts before anything else exists.

## Layout

- `collectors/` — data collection
- `data/` — captured snapshots (on the `data` branch)

## Licence

MIT
