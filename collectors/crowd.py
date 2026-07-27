"""Hourly crowd snapshot collector.

Captures the ephemeral fields from the FPL bootstrap-static endpoint.

These fields have NO history endpoint. `transfers_in_event` and
`transfers_out_event` reset every gameweek; `selected_by_percent` is a
current-value-only field. An hour not captured is an hour that never
existed and can never be recovered.

This is why this runs in CI on a schedule and not on a laptop.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"

# The FPL API rejects the default python-requests user agent intermittently.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

MAX_ATTEMPTS = 5
BACKOFF_BASE = 3  # seconds; 3, 6, 12, 24, 48

# Ephemeral fields are marked. Everything else is captured because it is
# cheap and because re-deriving it later is impossible if the schema drifts.
PLAYER_FIELDS = {
    "id": "player_id",
    "team": "team_fpl_id",
    "element_type": "position_id",
    "web_name": "web_name",
    "now_cost": "price",                          # ephemeral
    "cost_change_event": "price_change_event",    # ephemeral
    "selected_by_percent": "ownership_pct",       # EPHEMERAL - core signal
    "transfers_in_event": "transfers_in_ev",      # EPHEMERAL - core signal
    "transfers_out_event": "transfers_out_ev",    # EPHEMERAL - core signal
    "transfers_in": "transfers_in_total",
    "transfers_out": "transfers_out_total",
    "chance_of_playing_next_round": "play_chance_pct",   # availability
    "chance_of_playing_this_round": "play_chance_this",  # availability
    "news": "news",
    "news_added": "news_added",
    "status": "status",
    "minutes": "minutes",
    "total_points": "total_points",
    "form": "form",
    "ep_next": "ep_next",
}

NUMERIC = [
    "ownership_pct", "form", "ep_next", "price_change_event",
    "transfers_in_ev", "transfers_out_ev", "transfers_in_total",
    "transfers_out_total", "play_chance_pct", "play_chance_this",
    "minutes", "total_points", "price",
]

log = logging.getLogger("crowd")


def fetch(url: str = API_URL) -> dict:
    """GET the endpoint with exponential backoff. Raises after MAX_ATTEMPTS."""
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - we want to retry anything
            last_error = exc
            wait = BACKOFF_BASE * (2 ** (attempt - 1))
            log.warning("attempt %d/%d failed (%s)", attempt, MAX_ATTEMPTS, exc)
            if attempt < MAX_ATTEMPTS:
                time.sleep(wait)
    raise RuntimeError(f"all {MAX_ATTEMPTS} attempts failed") from last_error


def current_gameweek(payload: dict) -> int | None:
    """The gameweek the ephemeral transfer counters are currently scoped to."""
    for event in payload.get("events", []):
        if event.get("is_current"):
            return event.get("id")
    for event in payload.get("events", []):
        if event.get("is_next"):
            return event.get("id")
    return None


def extract(payload: dict, captured_at: datetime) -> pd.DataFrame:
    """Flatten the player list into the snapshot schema."""
    elements = payload.get("elements")
    if not elements:
        raise ValueError("payload contained no 'elements' - schema may have changed")

    df = pd.DataFrame(elements)

    missing = set(PLAYER_FIELDS) - set(df.columns)
    if missing:
        # Loud, not silent. A schema change must never degrade quietly.
        raise ValueError(f"expected fields absent from API response: {sorted(missing)}")

    df = df[list(PLAYER_FIELDS)].rename(columns=PLAYER_FIELDS)

    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    teams = {t["id"]: t["short_name"] for t in payload.get("teams", [])}
    df["team_short"] = df["team_fpl_id"].map(teams)

    df["captured_at"] = captured_at
    df["gameweek"] = current_gameweek(payload)

    return df


def write(df: pd.DataFrame, root: Path, captured_at: datetime) -> Path:
    """Write one snapshot to data/raw/crowd/YYYY-MM-DD/HH.parquet."""
    out_dir = root / captured_at.strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{captured_at.strftime('%H')}.parquet"
    df.to_parquet(out_path, engine="pyarrow", compression="zstd", index=False)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture one FPL crowd snapshot.")
    parser.add_argument("--out", default="data/raw/crowd", help="output root")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    payload = fetch()
    captured_at = datetime.now(timezone.utc).replace(microsecond=0)

    df = extract(payload, captured_at)
    path = write(df, Path(args.out), captured_at)

    size_kb = path.stat().st_size / 1024
    log.info(
        "captured %d players, gw=%s -> %s (%.0f KB)",
        len(df), df["gameweek"].iloc[0], path, size_kb,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
