"""Pull Understat team xG and join onto matches.

Uses soccerdata's Understat reader (v1.9+ talks to the AJAX JSON API).
Coverage starts 2014-15. Join key: (match_date, home_team_id, away_team_id).

Reports join rate and lists unmatched rows — PRD threshold is 98%.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb
import pandas as pd
import soccerdata as sd

from loaders.resolve_team import TeamResolver, UnknownTeamError

log = logging.getLogger("understat")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_OUT = ROOT / "data" / "raw" / "understat"
DEFAULT_TEAMS = ROOT / "ref" / "teams.csv"
DEFAULT_ALIASES = ROOT / "ref" / "team_aliases.csv"
DEFAULT_SCHEMA = ROOT / "db" / "schema.sql"

# Understat EPL data begins 2014-15.
FIRST_SEASON_START = 2014
LAST_SEASON_START = 2025

LEAGUE = "ENG-Premier League"
JOIN_RATE_THRESHOLD = 0.98


def season_code(start_year: int) -> str:
    end = (start_year + 1) % 100
    return f"{start_year % 100:02d}{end:02d}"


def season_label(start_year: int) -> str:
    return f"{start_year}-{((start_year + 1) % 100):02d}"


def season_codes() -> list[str]:
    return [season_code(y) for y in range(FIRST_SEASON_START, LAST_SEASON_START + 1)]


def fetch_schedule(seasons: list[str] | None = None) -> pd.DataFrame:
    """Download Understat schedule (includes home_xg / away_xg)."""
    seasons = seasons or season_codes()
    log.info("fetching Understat schedule for seasons %s .. %s", seasons[0], seasons[-1])
    reader = sd.Understat(leagues=LEAGUE, seasons=seasons)
    raw = reader.read_schedule()
    df = raw.reset_index()

    # Keep only completed matches with xG
    before = len(df)
    df = df[df["is_result"].astype(bool) & df["has_data"].astype(bool)].copy()
    df = df.dropna(subset=["home_xg", "away_xg", "date", "home_team", "away_team"])
    log.info("schedule rows: %d raw -> %d with results+xG", before, len(df))
    return df


def normalise(df: pd.DataFrame, resolver: TeamResolver) -> pd.DataFrame:
    """Map Understat team names to canonical ids; derive match_date."""
    names = pd.Series(
        sorted(set(df["home_team"].astype(str)) | set(df["away_team"].astype(str)))
    )
    try:
        resolver.resolve_series(names, source="understat")
    except UnknownTeamError as exc:
        log.error("add missing Understat aliases: %s", exc)
        raise

    out = pd.DataFrame(
        {
            "understat_game_id": df["game_id"].astype("int64"),
            "season_code": df["season"].astype(str),
            "match_date": pd.to_datetime(df["date"]).dt.normalize().dt.tz_localize(None),
            "kickoff_utc": pd.to_datetime(df["date"], utc=True)
            .dt.tz_convert("UTC")
            .dt.tz_localize(None),
            "home_team_raw": df["home_team"].astype(str).str.strip(),
            "away_team_raw": df["away_team"].astype(str).str.strip(),
            "home_team_id": resolver.resolve_series(df["home_team"], source="understat"),
            "away_team_id": resolver.resolve_series(df["away_team"], source="understat"),
            "home_goals": pd.to_numeric(df["home_goals"], errors="coerce").astype("Int64"),
            "away_goals": pd.to_numeric(df["away_goals"], errors="coerce").astype("Int64"),
            "home_xg": pd.to_numeric(df["home_xg"], errors="coerce"),
            "away_xg": pd.to_numeric(df["away_xg"], errors="coerce"),
        }
    )
    # season label from code 1415 → 2014-15
    out["season"] = out["season_code"].map(
        lambda c: season_label(2000 + int(str(c)[:2]))
    )
    return out


def save_parquet(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "team_match_xg.parquet"
    df.to_parquet(path, index=False)
    log.info("wrote %s (%d rows)", path, len(df))
    return path


def join_and_update(
    con: duckdb.DuckDBPyConnection,
    xg: pd.DataFrame,
) -> dict:
    """Join xG onto matches; update home_xg/away_xg. Returns join stats."""
    eligible = con.execute(
        """
        SELECT COUNT(*) FROM matches
        WHERE season >= '2014-15'
        """
    ).fetchone()[0]

    con.register("_xg", xg)
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE xg_join AS
        SELECT
            m.match_id,
            m.season,
            m.match_date,
            m.home_team_id,
            m.away_team_id,
            x.home_xg,
            x.away_xg,
            x.kickoff_utc AS understat_kickoff,
            x.understat_game_id
        FROM matches m
        LEFT JOIN _xg x
          ON m.match_date = CAST(x.match_date AS DATE)
         AND m.home_team_id = x.home_team_id
         AND m.away_team_id = x.away_team_id
        WHERE m.season >= '2014-15'
        """
    )

    matched = con.execute(
        "SELECT COUNT(*) FROM xg_join WHERE home_xg IS NOT NULL"
    ).fetchone()[0]
    unmatched = con.execute(
        """
        SELECT match_id, season, match_date, home_team_id, away_team_id
        FROM xg_join WHERE home_xg IS NULL
        ORDER BY match_date
        """
    ).fetchdf()

    # Orphan Understat rows (in xG but no football-data match)
    orphans = con.execute(
        """
        SELECT x.season, CAST(x.match_date AS DATE) AS match_date,
               x.home_team_id, x.away_team_id, x.understat_game_id
        FROM _xg x
        LEFT JOIN matches m
          ON m.match_date = CAST(x.match_date AS DATE)
         AND m.home_team_id = x.home_team_id
         AND m.away_team_id = x.away_team_id
        WHERE m.match_id IS NULL
        ORDER BY x.match_date
        """
    ).fetchdf()

    rate = matched / eligible if eligible else 0.0
    log.info(
        "join: eligible=%d matched=%d rate=%.2f%% threshold=%.0f%%",
        eligible, matched, 100 * rate, 100 * JOIN_RATE_THRESHOLD,
    )

    if not unmatched.empty:
        log.warning("unmatched football-data rows (%d):", len(unmatched))
        for row in unmatched.head(20).itertuples(index=False):
            log.warning(
                "  %s %s %s vs %s",
                row.match_date, row.season, row.home_team_id, row.away_team_id,
            )
        if len(unmatched) > 20:
            log.warning("  ... and %d more", len(unmatched) - 20)

    if not orphans.empty:
        log.warning("orphan understat rows (%d) with no football-data match:", len(orphans))
        for row in orphans.head(20).itertuples(index=False):
            log.warning(
                "  %s %s %s vs %s (game_id=%s)",
                row.match_date, row.season, row.home_team_id, row.away_team_id,
                row.understat_game_id,
            )

    # Apply xG (+ kickoff when available) to matches
    con.execute(
        """
        UPDATE matches AS m
        SET
          home_xg = j.home_xg,
          away_xg = j.away_xg,
          kickoff_utc = COALESCE(j.understat_kickoff, m.kickoff_utc)
        FROM xg_join AS j
        WHERE m.match_id = j.match_id
          AND j.home_xg IS NOT NULL
        """
    )

    with_xg = con.execute(
        "SELECT COUNT(*) FROM matches WHERE home_xg IS NOT NULL"
    ).fetchone()[0]
    seasons_with_xg = con.execute(
        """
        SELECT COUNT(DISTINCT season) FROM matches
        WHERE home_xg IS NOT NULL
        """
    ).fetchone()[0]

    con.unregister("_xg")

    return {
        "eligible": eligible,
        "matched": matched,
        "rate": rate,
        "unmatched": unmatched,
        "orphans": orphans,
        "with_xg": with_xg,
        "seasons_with_xg": seasons_with_xg,
    }


def try_fuzzy_rescue(
    con: duckdb.DuckDBPyConnection,
    xg: pd.DataFrame,
    unmatched: pd.DataFrame,
) -> int:
    """Rescue unmatched rows by ±1 day date window (postponements).

    Only applies when home/away team ids match uniquely within the window.
    """
    if unmatched.empty:
        return 0

    rescued = 0
    con.register("_xg", xg)
    for row in unmatched.itertuples(index=False):
        candidates = con.execute(
            """
            SELECT understat_game_id, home_xg, away_xg, kickoff_utc, match_date
            FROM _xg
            WHERE home_team_id = ?
              AND away_team_id = ?
              AND CAST(match_date AS DATE)
                    BETWEEN CAST(? AS DATE) - INTERVAL 1 DAY
                        AND CAST(? AS DATE) + INTERVAL 1 DAY
            """,
            [row.home_team_id, row.away_team_id, row.match_date, row.match_date],
        ).fetchdf()
        if len(candidates) != 1:
            continue
        c = candidates.iloc[0]
        con.execute(
            """
            UPDATE matches
            SET home_xg = ?, away_xg = ?,
                kickoff_utc = COALESCE(?, kickoff_utc)
            WHERE match_id = ?
            """,
            [
                float(c["home_xg"]),
                float(c["away_xg"]),
                c["kickoff_utc"].to_pydatetime() if pd.notna(c["kickoff_utc"]) else None,
                row.match_id,
            ],
        )
        rescued += 1
        log.info(
            "fuzzy rescue %s: understat date %s (football-data %s)",
            row.match_id,
            pd.Timestamp(c["match_date"]).date(),
            row.match_date,
        )
    con.unregister("_xg")
    return rescued


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Understat xG into matches.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--teams", type=Path, default=DEFAULT_TEAMS)
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIASES)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--from-parquet",
        type=Path,
        default=None,
        help="reuse a previously saved parquet instead of downloading",
    )
    parser.add_argument(
        "--no-fuzzy",
        action="store_true",
        help="skip ±1 day rescue for postponed fixtures",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    resolver = TeamResolver(args.teams, args.aliases)

    if args.from_parquet:
        xg = pd.read_parquet(args.from_parquet)
        log.info("loaded %d rows from %s", len(xg), args.from_parquet)
    else:
        raw = fetch_schedule()
        xg = normalise(raw, resolver)
        save_parquet(xg, args.out)

    if not args.db.is_file():
        log.error("database missing (%s) — run results + resolve-teams first", args.db)
        return 1

    con = duckdb.connect(str(args.db))
    try:
        con.execute(args.schema.read_text(encoding="utf-8"))
        # Clear prior xG so re-runs are clean
        con.execute("UPDATE matches SET home_xg = NULL, away_xg = NULL")

        stats = join_and_update(con, xg)
        rescued = 0
        if not args.no_fuzzy and not stats["unmatched"].empty:
            rescued = try_fuzzy_rescue(con, xg, stats["unmatched"])
            if rescued:
                # Recompute rate after rescue
                matched = con.execute(
                    """
                    SELECT COUNT(*) FROM matches
                    WHERE season >= '2014-15' AND home_xg IS NOT NULL
                    """
                ).fetchone()[0]
                stats["matched"] = matched
                stats["rate"] = matched / stats["eligible"] if stats["eligible"] else 0.0
                stats["with_xg"] = con.execute(
                    "SELECT COUNT(*) FROM matches WHERE home_xg IS NOT NULL"
                ).fetchone()[0]
                log.info(
                    "after fuzzy rescue: matched=%d rate=%.2f%% (+%d)",
                    matched, 100 * stats["rate"], rescued,
                )

        log.info(
            "done: matches_with_xg=%d seasons_with_xg=%d join_rate=%.2f%%",
            stats["with_xg"],
            stats["seasons_with_xg"],
            100 * stats["rate"],
        )

        if stats["rate"] < JOIN_RATE_THRESHOLD:
            log.error(
                "join rate %.2f%% is below %.0f%% threshold — investigate unmatched rows",
                100 * stats["rate"],
                100 * JOIN_RATE_THRESHOLD,
            )
            return 1
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
