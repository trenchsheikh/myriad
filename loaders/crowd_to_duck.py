"""Load crowd Parquet snapshots into DuckDB.

Idempotent: re-running skips `captured_at` values already present in
`crowd_snapshots`. Never updates or deletes existing rows (append-only).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb
import pandas as pd

log = logging.getLogger("crowd_to_duck")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_SCHEMA = ROOT / "db" / "schema.sql"
DEFAULT_CROWD_ROOT = ROOT / "data" / "raw" / "crowd"

# FPL element_type → display position (canonical team_id mapping is Day 5).
POSITION_MAP = {
    1: "GKP",
    2: "DEF",
    3: "MID",
    4: "FWD",
}

CROWD_COLUMNS = [
    "captured_at",
    "player_id",
    "team_id",
    "position",
    "price",
    "ownership_pct",
    "transfers_in_ev",
    "transfers_out_ev",
    "play_chance_pct",
    "news",
    "news_added",
]


def as_utc(value) -> pd.Timestamp:
    """Normalise any timestamp to UTC-aware for set comparisons.

    DuckDB returns naive datetimes; Parquet from the collector is UTC-aware.
    Without this, idempotent reloads silently double-insert.
    """
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def as_naive_utc(series: pd.Series) -> pd.Series:
    """UTC wall-clock with tz stripped — safe to store in DuckDB TIMESTAMP.

    Inserting tz-aware values makes DuckDB convert to the machine's local
    timezone and drop the offset, which breaks idempotency across reloads.
    """
    s = pd.to_datetime(series, utc=True, errors="coerce")
    return s.dt.tz_localize(None)


def apply_schema(con: duckdb.DuckDBPyConnection, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    con.execute(sql)


def discover_parquet(crowd_root: Path) -> list[Path]:
    if not crowd_root.is_dir():
        return []
    return sorted(crowd_root.glob("*/*.parquet"))


def already_loaded(con: duckdb.DuckDBPyConnection) -> set[pd.Timestamp]:
    rows = con.execute(
        "SELECT DISTINCT captured_at FROM crowd_snapshots"
    ).fetchall()
    return {as_utc(r[0]) for r in rows}


def parquet_to_frame(path: Path) -> pd.DataFrame:
    """Map a collector Parquet file onto the crowd_snapshots schema."""
    raw = pd.read_parquet(path)

    required = {
        "captured_at",
        "player_id",
        "team_short",
        "position_id",
        "price",
        "ownership_pct",
        "transfers_in_ev",
        "transfers_out_ev",
        "play_chance_pct",
        "news",
        "news_added",
    }
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")

    out = pd.DataFrame(
        {
            "captured_at": as_naive_utc(raw["captured_at"]),
            "player_id": raw["player_id"].astype("int64"),
            # Temporary until Day 5 team normalisation — FPL short name.
            "team_id": raw["team_short"].astype(str),
            "position": raw["position_id"].map(POSITION_MAP),
            "price": raw["price"].astype("Int64"),
            "ownership_pct": pd.to_numeric(raw["ownership_pct"], errors="coerce"),
            "transfers_in_ev": raw["transfers_in_ev"].astype("Int64"),
            "transfers_out_ev": raw["transfers_out_ev"].astype("Int64"),
            "play_chance_pct": raw["play_chance_pct"].astype("Int64"),
            "news": raw["news"].astype(str).where(raw["news"].notna(), None),
            "news_added": as_naive_utc(raw["news_added"]),
        }
    )

    unknown_pos = out["position"].isna().sum()
    if unknown_pos:
        raise ValueError(f"{path}: {unknown_pos} rows with unknown position_id")

    return out[CROWD_COLUMNS]


def load_new_snapshots(
    con: duckdb.DuckDBPyConnection,
    crowd_root: Path,
) -> tuple[int, int, int]:
    """Insert unseen snapshots. Returns (files_seen, files_loaded, rows_inserted)."""
    paths = discover_parquet(crowd_root)
    if not paths:
        log.warning("no parquet files under %s", crowd_root)
        return 0, 0, 0

    loaded = already_loaded(con)
    files_loaded = 0
    rows_inserted = 0

    for path in paths:
        frame = parquet_to_frame(path)
        capture_times = {as_utc(t) for t in frame["captured_at"].unique()}

        if capture_times <= loaded:
            log.info("skip (already loaded): %s", path)
            continue

        # Partial overlap should not happen with hour-stamped files; refuse
        # rather than risk duplicate player rows for a shared timestamp.
        overlap = capture_times & loaded
        if overlap:
            raise RuntimeError(
                f"{path}: partial overlap with DB timestamps {sorted(overlap)}"
            )

        con.register("_crowd_batch", frame)
        con.execute(
            f"INSERT INTO crowd_snapshots SELECT {', '.join(CROWD_COLUMNS)} FROM _crowd_batch"
        )
        con.unregister("_crowd_batch")

        loaded |= capture_times
        files_loaded += 1
        rows_inserted += len(frame)
        log.info("loaded %s (%d rows)", path, len(frame))

    return len(paths), files_loaded, rows_inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Load crowd Parquet into DuckDB.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--crowd-root", type=Path, default=DEFAULT_CROWD_ROOT)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    args.db.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(args.db))
    try:
        apply_schema(con, args.schema)
        seen, loaded, rows = load_new_snapshots(con, args.crowd_root)
        total = con.execute("SELECT COUNT(*) FROM crowd_snapshots").fetchone()[0]
        stamps = con.execute(
            "SELECT COUNT(DISTINCT captured_at) FROM crowd_snapshots"
        ).fetchone()[0]
        log.info(
            "done: files=%d loaded=%d rows_inserted=%d | db rows=%d stamps=%d",
            seen, loaded, rows, total, stamps,
        )
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
