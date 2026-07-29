"""Pull the 2026-27 fixture list from the FPL fixtures endpoint.

Maps FPL team ids to canonical team_id via bootstrap-static short names
and ref/team_aliases.csv. Also loads stadium lat/lon into the teams table.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb
import pandas as pd
import requests

from loaders.resolve_team import TeamResolver, UnknownTeamError

log = logging.getLogger("fixtures")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_SCHEMA = ROOT / "db" / "schema.sql"
DEFAULT_TEAMS = ROOT / "ref" / "teams.csv"
DEFAULT_ALIASES = ROOT / "ref" / "team_aliases.csv"
DEFAULT_STADIUMS = ROOT / "ref" / "stadiums.csv"
DEFAULT_OUT = ROOT / "data" / "raw" / "fixtures"

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

SEASON = "2026-27"


def fetch_json(url: str) -> dict | list:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fpl_team_map(bootstrap: dict, resolver: TeamResolver) -> dict[int, str]:
    """FPL numeric team id → canonical team_id."""
    mapping: dict[int, str] = {}
    unknown: list[str] = []
    for team in bootstrap.get("teams", []):
        fpl_id = int(team["id"])
        # Prefer short_name (ARS); fall back to display name.
        candidates = [team.get("short_name"), team.get("name")]
        resolved = None
        for cand in candidates:
            if not cand:
                continue
            try:
                resolved = resolver.resolve(cand, source="fpl")
                break
            except UnknownTeamError:
                continue
        if resolved is None:
            unknown.append(str(team.get("name") or team.get("short_name")))
        else:
            mapping[fpl_id] = resolved
    if unknown:
        raise UnknownTeamError(
            f"unknown FPL teams: {unknown}. Add aliases to ref/team_aliases.csv"
        )
    return mapping


def parse_fixtures(raw: list[dict], team_map: dict[int, str]) -> pd.DataFrame:
    rows = []
    for fx in raw:
        home_fpl = int(fx["team_h"])
        away_fpl = int(fx["team_a"])
        if home_fpl not in team_map or away_fpl not in team_map:
            raise UnknownTeamError(
                f"fixture {fx.get('id')} references unknown FPL team "
                f"home={home_fpl} away={away_fpl}"
            )
        kickoff = pd.to_datetime(fx.get("kickoff_time"), utc=True, errors="coerce")
        if pd.isna(kickoff):
            raise ValueError(f"fixture {fx.get('id')} missing kickoff_time")
        rows.append(
            {
                "fixture_id": int(fx["id"]),
                "season": SEASON,
                "gameweek": fx.get("event"),
                "kickoff_utc": kickoff.tz_convert("UTC").tz_localize(None),
                "home_team_id": team_map[home_fpl],
                "away_team_id": team_map[away_fpl],
                "finished": bool(fx.get("finished")),
                "fpl_code": fx.get("code"),
            }
        )
    df = pd.DataFrame(rows)
    if df["fixture_id"].duplicated().any():
        raise RuntimeError("duplicate fixture_id in FPL response")
    return df


def load_stadiums(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    stadiums = pd.read_csv(path)
    required = {"team_id", "stadium_name", "lat", "lon"}
    missing = required - set(stadiums.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")

    # Ensure every stadium team_id exists in teams; insert missing rows.
    existing = {
        r[0]
        for r in con.execute("SELECT team_id FROM teams").fetchall()
    }
    for _, row in stadiums.iterrows():
        tid = str(row["team_id"])
        if tid not in existing:
            # Pull canonical name from teams.csv via a separate path is cleaner;
            # for safety insert with team_id as name placeholder then update.
            con.execute(
                "INSERT INTO teams (team_id, canonical_name, stadium_lat, stadium_lon) "
                "VALUES (?, ?, ?, ?)",
                [tid, tid, float(row["lat"]), float(row["lon"])],
            )
            existing.add(tid)
        else:
            con.execute(
                "UPDATE teams SET stadium_lat = ?, stadium_lon = ? WHERE team_id = ?",
                [float(row["lat"]), float(row["lon"]), tid],
            )
    return len(stadiums)


def load_fixtures(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    con.execute("DELETE FROM fixtures WHERE season = ?", [SEASON])
    con.register("_fx", df)
    con.execute(
        """
        INSERT INTO fixtures
        SELECT fixture_id, season, gameweek, kickoff_utc,
               home_team_id, away_team_id, finished, fpl_code
        FROM _fx
        """
    )
    con.unregister("_fx")
    return con.execute(
        "SELECT COUNT(*) FROM fixtures WHERE season = ?", [SEASON]
    ).fetchone()[0]


def sync_teams_from_csv(con: duckdb.DuckDBPyConnection, teams_path: Path) -> None:
    """Upsert canonical teams from ref/teams.csv (covers newly promoted clubs)."""
    teams = pd.read_csv(teams_path)
    con.register("_teams_csv", teams)
    con.execute(
        """
        INSERT INTO teams (team_id, canonical_name, stadium_lat, stadium_lon)
        SELECT team_id, canonical_name, NULL, NULL FROM _teams_csv
        ON CONFLICT (team_id) DO UPDATE SET canonical_name = EXCLUDED.canonical_name
        """
    )
    con.unregister("_teams_csv")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load FPL fixtures + stadium coords.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--teams", type=Path, default=DEFAULT_TEAMS)
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIASES)
    parser.add_argument("--stadiums", type=Path, default=DEFAULT_STADIUMS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    resolver = TeamResolver(args.teams, args.aliases)

    bootstrap = fetch_json(BOOTSTRAP_URL)
    assert isinstance(bootstrap, dict)
    team_map = fpl_team_map(bootstrap, resolver)
    log.info("mapped %d FPL teams to canonical ids", len(team_map))
    for fpl_id, tid in sorted(team_map.items(), key=lambda x: x[1]):
        log.info("  FPL %2d -> %s", fpl_id, tid)

    raw = fetch_json(FIXTURES_URL)
    assert isinstance(raw, list)
    fixtures = parse_fixtures(raw, team_map)
    log.info(
        "fixtures: %d total, finished=%d, gw range=%s-%s",
        len(fixtures),
        int(fixtures["finished"].sum()),
        fixtures["gameweek"].min(),
        fixtures["gameweek"].max(),
    )

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / f"fixtures_{SEASON.replace('-', '')}.parquet"
    fixtures.to_parquet(out_path, index=False)
    log.info("wrote %s", out_path)

    args.db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(args.db))
    try:
        con.execute(args.schema.read_text(encoding="utf-8"))
        sync_teams_from_csv(con, args.teams)
        n_stad = load_stadiums(con, args.stadiums)
        n_fx = load_fixtures(con, fixtures)

        null_coords = con.execute(
            "SELECT COUNT(*) FROM teams WHERE stadium_lat IS NULL OR stadium_lon IS NULL"
        ).fetchone()[0]
        null_teams = con.execute(
            """
            SELECT COUNT(*) FROM fixtures
            WHERE home_team_id IS NULL OR away_team_id IS NULL
               OR home_team_id = '' OR away_team_id = ''
            """
        ).fetchone()[0]

        log.info(
            "done: fixtures=%d stadiums_loaded=%d teams_missing_coords=%d "
            "fixtures_null_team=%d",
            n_fx, n_stad, null_coords, null_teams,
        )
        if null_teams:
            return 1
        # Only require coords for clubs in the current fixture list
        current = set(fixtures["home_team_id"]) | set(fixtures["away_team_id"])
        coords = {
            r[0]: (r[1], r[2])
            for r in con.execute(
                "SELECT team_id, stadium_lat, stadium_lon FROM teams"
            ).fetchall()
        }
        missing_coords = [
            tid
            for tid in sorted(current)
            if tid not in coords
            or coords[tid][0] is None
            or coords[tid][1] is None
        ]
        if missing_coords:
            log.error("current PL clubs missing stadium coords: %s", missing_coords)
            return 1
        log.info("all %d current PL clubs have stadium coords", len(current))
    except UnknownTeamError as exc:
        log.error("%s", exc)
        return 1
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
