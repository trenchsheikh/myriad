"""Download Premier League results + odds from football-data.co.uk.

Seasons 2010-11 through 2025-26. Writes raw CSVs under data/raw/results/
and loads them into DuckDB table matches_staging (no team normalisation).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from io import StringIO
from pathlib import Path

import duckdb
import pandas as pd
import requests

log = logging.getLogger("results")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "raw" / "results"
DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_SCHEMA = ROOT / "db" / "schema.sql"

BASE_URL = "https://www.football-data.co.uk/mmz4281/{code}/E0.csv"

# Start year of each season to download (inclusive).
FIRST_SEASON_START = 2010
LAST_SEASON_START = 2025

# Columns required by the PRD. Older seasons may lack closing odds.
KEEP_COLS = [
    "Date",
    "HomeTeam",
    "AwayTeam",
    "FTHG",
    "FTAG",
    "Referee",
    "B365H",
    "B365D",
    "B365A",
    "B365CH",
    "B365CD",
    "B365CA",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
}

MAX_ATTEMPTS = 4
BACKOFF_BASE = 2


def season_code(start_year: int) -> str:
    """2010 -> '1011', 2025 -> '2526'."""
    end = (start_year + 1) % 100
    return f"{start_year % 100:02d}{end:02d}"


def season_label(start_year: int) -> str:
    """2010 -> '2010-11'."""
    return f"{start_year}-{((start_year + 1) % 100):02d}"


def season_range() -> list[int]:
    return list(range(FIRST_SEASON_START, LAST_SEASON_START + 1))


def fetch_csv(url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            # football-data sometimes serves latin-1 adjacent content
            resp.encoding = resp.apparent_encoding or "utf-8"
            text = resp.text
            if "HomeTeam" not in text.splitlines()[0]:
                raise ValueError(f"unexpected CSV header from {url}")
            return text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            wait = BACKOFF_BASE * (2 ** (attempt - 1))
            log.warning("attempt %d/%d failed for %s (%s)", attempt, MAX_ATTEMPTS, url, exc)
            if attempt < MAX_ATTEMPTS:
                time.sleep(wait)
    raise RuntimeError(f"failed to download {url}") from last_error


def parse_season(text: str, start_year: int) -> pd.DataFrame:
    """Parse one season CSV into the staging schema."""
    raw = pd.read_csv(StringIO(text))
    # Drop fully empty trailing rows football-data sometimes appends
    raw = raw.dropna(how="all")
    if raw.empty:
        raise ValueError(f"empty CSV for season {season_label(start_year)}")

    for col in KEEP_COLS:
        if col not in raw.columns:
            raw[col] = pd.NA

    df = raw[KEEP_COLS].copy()
    df["season"] = season_label(start_year)
    df["season_code"] = season_code(start_year)

    # Dates are DD/MM/YY or DD/MM/YYYY depending on season
    df["match_date"] = pd.to_datetime(
        df["Date"], dayfirst=True, format="mixed", errors="coerce"
    )
    bad = df["match_date"].isna().sum()
    if bad:
        raise ValueError(
            f"{season_label(start_year)}: {bad} rows with unparseable Date"
        )

    for col in ("FTHG", "FTAG"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    for col in ("B365H", "B365D", "B365A", "B365CH", "B365CD", "B365CA"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["HomeTeam"] = df["HomeTeam"].astype(str).str.strip()
    df["AwayTeam"] = df["AwayTeam"].astype(str).str.strip()
    df["Referee"] = df["Referee"].astype(str).str.strip().where(df["Referee"].notna(), None)

    # Drop rows missing essentials
    before = len(df)
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG", "match_date"])
    dropped = before - len(df)
    if dropped:
        log.warning("%s: dropped %d incomplete rows", season_label(start_year), dropped)

    return df.rename(
        columns={
            "HomeTeam": "home_team_raw",
            "AwayTeam": "away_team_raw",
            "FTHG": "home_goals",
            "FTAG": "away_goals",
            "Referee": "referee",
            "B365H": "odds_open_h",
            "B365D": "odds_open_d",
            "B365A": "odds_open_a",
            "B365CH": "odds_close_h",
            "B365CD": "odds_close_d",
            "B365CA": "odds_close_a",
        }
    )[
        [
            "season",
            "season_code",
            "match_date",
            "home_team_raw",
            "away_team_raw",
            "home_goals",
            "away_goals",
            "referee",
            "odds_open_h",
            "odds_open_d",
            "odds_open_a",
            "odds_close_h",
            "odds_close_d",
            "odds_close_a",
        ]
    ]


def download_all(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for start in season_range():
        code = season_code(start)
        url = BASE_URL.format(code=code)
        path = out_dir / f"E0_{code}.csv"
        log.info("fetching %s -> %s", url, path.name)
        text = fetch_csv(url)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
        time.sleep(0.4)  # be polite to football-data.co.uk
    return paths


def load_csvs(paths: list[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        # season start year from filename E0_1011.csv → 2010
        code = path.stem.split("_", 1)[1]
        start_year = 2000 + int(code[:2])
        text = path.read_text(encoding="utf-8")
        frames.append(parse_season(text, start_year))
        log.info("parsed %s (%d rows)", path.name, len(frames[-1]))
    return pd.concat(frames, ignore_index=True)


def apply_schema(con: duckdb.DuckDBPyConnection, schema_path: Path) -> None:
    con.execute(schema_path.read_text(encoding="utf-8"))


def load_staging(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Replace matches_staging contents (raw reload is fine before normalisation)."""
    con.execute("DELETE FROM matches_staging")
    con.register("_results_batch", df)
    con.execute(
        """
        INSERT INTO matches_staging
        SELECT
            season, season_code, match_date,
            home_team_raw, away_team_raw,
            home_goals, away_goals, referee,
            odds_open_h, odds_open_d, odds_open_a,
            odds_close_h, odds_close_d, odds_close_a
        FROM _results_batch
        """
    )
    con.unregister("_results_batch")
    return con.execute("SELECT COUNT(*) FROM matches_staging").fetchone()[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Download PL results from football-data.co.uk")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="reuse existing CSVs under --out",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if args.skip_download:
        paths = sorted(args.out.glob("E0_*.csv"))
        if not paths:
            log.error("no CSVs under %s; run without --skip-download", args.out)
            return 1
    else:
        paths = download_all(args.out)

    df = load_csvs(paths)
    log.info(
        "combined: %d matches across %d seasons (%s .. %s)",
        len(df),
        df["season"].nunique(),
        df["season"].min(),
        df["season"].max(),
    )

    args.db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(args.db))
    try:
        apply_schema(con, args.schema)
        n = load_staging(con, df)
        seasons = con.execute(
            "SELECT season, COUNT(*) FROM matches_staging GROUP BY 1 ORDER BY 1"
        ).fetchall()
        for season, count in seasons:
            log.info("  %s: %d matches", season, count)
        log.info("matches_staging rows=%d", n)
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
