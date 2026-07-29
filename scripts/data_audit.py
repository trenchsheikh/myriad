"""Day 8 data audit — printable checks against DuckDB.

Acceptance (prd.md):
  - >= 15 seasons of results
  - >= 10 seasons with xG
  - zero unresolved team names
  - zero duplicate match_ids

Also reports: matches per season, xG coverage, missing odds, fixture counts.
Exit code 1 if any acceptance check fails.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb
import pandas as pd

log = logging.getLogger("data_audit")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_REPORT = ROOT / "notebooks" / "01_data_audit_report.md"

MIN_SEASONS = 15
MIN_XG_SEASONS = 10


def section(title: str) -> None:
    log.info("")
    log.info("=== %s ===", title)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Myriad DuckDB contents.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if not args.db.is_file():
        log.error("database not found: %s — run scripts.full_load first", args.db)
        return 1

    con = duckdb.connect(str(args.db), read_only=True)
    failures: list[str] = []
    lines: list[str] = ["# Myriad data audit", ""]

    def note(msg: str) -> None:
        log.info("%s", msg)
        lines.append(msg)

    try:
        # --- Matches per season ---
        section("Matches per season")
        by_season = con.execute(
            """
            SELECT season, COUNT(*) AS matches,
                   SUM(CASE WHEN home_xg IS NOT NULL THEN 1 ELSE 0 END) AS with_xg,
                   SUM(CASE WHEN odds_open_h IS NOT NULL THEN 1 ELSE 0 END) AS with_open_odds,
                   SUM(CASE WHEN odds_close_h IS NOT NULL THEN 1 ELSE 0 END) AS with_close_odds
            FROM matches
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchdf()
        note(by_season.to_string(index=False))
        n_seasons = len(by_season)
        note(f"\nSeasons of results: **{n_seasons}** (need >= {MIN_SEASONS})")
        if n_seasons < MIN_SEASONS:
            failures.append(f"only {n_seasons} seasons of results (need >= {MIN_SEASONS})")

        # --- xG coverage ---
        section("xG coverage")
        xg_seasons = int((by_season["with_xg"] > 0).sum())
        eligible = int(by_season.loc[by_season["season"] >= "2014-15", "matches"].sum())
        with_xg = int(by_season["with_xg"].sum())
        rate = 100.0 * with_xg / eligible if eligible else 0.0
        note(f"Seasons with xG: **{xg_seasons}** (need >= {MIN_XG_SEASONS})")
        note(f"xG rows: {with_xg} / {eligible} eligible (2014-15+) = {rate:.2f}%")
        if xg_seasons < MIN_XG_SEASONS:
            failures.append(f"only {xg_seasons} seasons with xG (need >= {MIN_XG_SEASONS})")

        # --- Missing odds ---
        section("Missing odds")
        odds = con.execute(
            """
            SELECT
              COUNT(*) AS matches,
              SUM(CASE WHEN odds_open_h IS NULL OR odds_open_d IS NULL
                         OR odds_open_a IS NULL THEN 1 ELSE 0 END) AS missing_open,
              SUM(CASE WHEN odds_close_h IS NULL OR odds_close_d IS NULL
                         OR odds_close_a IS NULL THEN 1 ELSE 0 END) AS missing_close
            FROM matches
            """
        ).fetchone()
        note(
            f"missing opening odds: {odds[1]} / {odds[0]} "
            f"({100 * odds[1] / odds[0]:.1f}%)"
        )
        note(
            f"missing closing odds: {odds[2]} / {odds[0]} "
            f"({100 * odds[2] / odds[0]:.1f}%) — expected for pre-2019 seasons"
        )

        # --- Unresolved team names ---
        section("Unresolved team names")
        null_teams = con.execute(
            """
            SELECT COUNT(*) FROM matches
            WHERE home_team_id IS NULL OR away_team_id IS NULL
               OR home_team_id = '' OR away_team_id = ''
            """
        ).fetchone()[0]
        note(f"matches with null/empty team_id: **{null_teams}** (need 0)")
        if null_teams:
            failures.append(f"{null_teams} matches with unresolved team names")

        # staging raw names not in aliases (belt and braces)
        staging_unknown = con.execute(
            """
            WITH names AS (
              SELECT DISTINCT home_team_raw AS name FROM matches_staging
              UNION
              SELECT DISTINCT away_team_raw FROM matches_staging
            )
            SELECT n.name
            FROM names n
            LEFT JOIN team_aliases a
              ON a.alias = n.name AND a.source = 'football-data'
            WHERE a.team_id IS NULL
            ORDER BY 1
            """
        ).fetchall()
        note(f"staging names without football-data alias: {len(staging_unknown)}")
        if staging_unknown:
            failures.append(
                f"unaliased staging names: {[r[0] for r in staging_unknown]}"
            )

        # --- Duplicate match_ids ---
        section("Duplicate match_ids")
        dups = con.execute(
            """
            SELECT match_id, COUNT(*) AS n
            FROM matches
            GROUP BY 1
            HAVING COUNT(*) > 1
            ORDER BY n DESC
            """
        ).fetchdf()
        note(f"duplicate match_id groups: **{len(dups)}** (need 0)")
        if not dups.empty:
            note(dups.head(10).to_string(index=False))
            failures.append(f"{len(dups)} duplicate match_id groups")

        # --- Fixtures ---
        section("Fixtures (2026-27)")
        fx = con.execute(
            """
            SELECT season, COUNT(*) AS n,
                   COUNT(DISTINCT home_team_id) AS home_teams,
                   MIN(kickoff_utc) AS first_ko,
                   MAX(kickoff_utc) AS last_ko
            FROM fixtures
            GROUP BY 1
            """
        ).fetchdf()
        note(fx.to_string(index=False) if not fx.empty else "no fixtures loaded")

        # --- Crowd ---
        section("Crowd snapshots")
        crowd = con.execute(
            """
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT captured_at) AS stamps,
                   MIN(captured_at) AS first_ts,
                   MAX(captured_at) AS last_ts
            FROM crowd_snapshots
            """
        ).fetchone()
        note(
            f"rows={crowd[0]} stamps={crowd[1]} "
            f"first={crowd[2]} last={crowd[3]}"
        )

        # --- Stadiums ---
        section("Stadium coordinates")
        stad = con.execute(
            """
            SELECT
              COUNT(*) AS teams,
              SUM(CASE WHEN stadium_lat IS NOT NULL AND stadium_lon IS NOT NULL
                       THEN 1 ELSE 0 END) AS with_coords
            FROM teams
            """
        ).fetchone()
        note(f"teams={stad[0]} with_coords={stad[1]}")

        # --- Acceptance summary ---
        section("Acceptance")
        if failures:
            for f in failures:
                log.error("FAIL: %s", f)
                lines.append(f"- FAIL: {f}")
            lines.append("")
            lines.append("**Result: FAILED**")
            rc = 1
        else:
            note("All Day 8 acceptance checks passed.")
            lines.append("")
            lines.append("**Result: PASSED**")
            rc = 0

        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.info("wrote report %s", args.report)
        return rc
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
