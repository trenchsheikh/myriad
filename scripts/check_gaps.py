"""Assert the crowd snapshot log has no gap larger than 90 minutes.

Reads distinct `captured_at` values from DuckDB (or falls back to scanning
Parquet files) and fails loudly if any consecutive pair is more than
MAX_GAP_MINUTES apart.

An hour not captured is permanently gone — this script is the early warning.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import timedelta
from pathlib import Path

import duckdb
import pandas as pd

log = logging.getLogger("check_gaps")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_CROWD_ROOT = ROOT / "data" / "raw" / "crowd"
MAX_GAP_MINUTES = 90


def timestamps_from_db(db_path: Path) -> list[pd.Timestamp]:
    if not db_path.is_file():
        raise FileNotFoundError(f"database not found: {db_path}")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT DISTINCT captured_at FROM crowd_snapshots ORDER BY 1"
        ).fetchall()
    finally:
        con.close()
    return [pd.Timestamp(r[0]) for r in rows]


def timestamps_from_parquet(crowd_root: Path) -> list[pd.Timestamp]:
    paths = sorted(crowd_root.glob("*/*.parquet"))
    if not paths:
        raise FileNotFoundError(f"no parquet under {crowd_root}")
    stamps: list[pd.Timestamp] = []
    for path in paths:
        series = pd.read_parquet(path, columns=["captured_at"])["captured_at"]
        stamps.extend(pd.to_datetime(series.unique(), utc=True))
    return sorted(set(stamps))


def find_gaps(
    stamps: list[pd.Timestamp],
    max_gap: timedelta,
) -> list[tuple[pd.Timestamp, pd.Timestamp, timedelta]]:
    gaps: list[tuple[pd.Timestamp, pd.Timestamp, timedelta]] = []
    for prev, curr in zip(stamps, stamps[1:]):
        delta = curr - prev
        if delta > max_gap:
            gaps.append((prev, curr, delta))
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if crowd capture gaps exceed 90 minutes."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--crowd-root", type=Path, default=DEFAULT_CROWD_ROOT)
    parser.add_argument(
        "--max-gap-minutes",
        type=int,
        default=MAX_GAP_MINUTES,
        help="maximum allowed gap between consecutive captures (default 90)",
    )
    parser.add_argument(
        "--parquet-only",
        action="store_true",
        help="scan Parquet files instead of DuckDB",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if args.parquet_only or not args.db.is_file():
        if not args.parquet_only and not args.db.is_file():
            log.warning("DB missing (%s); falling back to Parquet scan", args.db)
        stamps = timestamps_from_parquet(args.crowd_root)
        source = "parquet"
    else:
        stamps = timestamps_from_db(args.db)
        source = "duckdb"

    if not stamps:
        log.error("no captured_at values found (%s)", source)
        return 1

    # Normalise to UTC-aware for consistent deltas
    stamps = [pd.Timestamp(t).tz_convert("UTC") if pd.Timestamp(t).tzinfo
              else pd.Timestamp(t, tz="UTC") for t in stamps]
    stamps = sorted(set(stamps))

    max_gap = timedelta(minutes=args.max_gap_minutes)
    gaps = find_gaps(stamps, max_gap)

    span = stamps[-1] - stamps[0]
    log.info(
        "source=%s stamps=%d first=%s last=%s span=%s",
        source,
        len(stamps),
        stamps[0].isoformat(),
        stamps[-1].isoformat(),
        span,
    )

    if not gaps:
        log.info("OK: no gaps > %d minutes", args.max_gap_minutes)
        return 0

    log.error("FOUND %d gap(s) > %d minutes:", len(gaps), args.max_gap_minutes)
    for prev, curr, delta in gaps:
        minutes = delta.total_seconds() / 60
        log.error(
            "  %s → %s  (%.0f min)",
            prev.isoformat(),
            curr.isoformat(),
            minutes,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
