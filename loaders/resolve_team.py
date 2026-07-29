"""Resolve raw team name aliases to canonical team_id.

Raises on unknown aliases — never silently drops a row.
Unknown names corrupt every downstream join; fail loudly.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb
import pandas as pd

from models.dixon_coles import crowd_present_for_date

log = logging.getLogger("resolve_team")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEAMS = ROOT / "ref" / "teams.csv"
DEFAULT_ALIASES = ROOT / "ref" / "team_aliases.csv"
DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_SCHEMA = ROOT / "db" / "schema.sql"


class UnknownTeamError(KeyError):
    """Raised when an alias is not in the lookup table."""


class TeamResolver:
    def __init__(self, teams_path: Path, aliases_path: Path) -> None:
        self.teams = pd.read_csv(teams_path)
        self.aliases = pd.read_csv(aliases_path)

        if self.teams["team_id"].duplicated().any():
            dups = self.teams.loc[self.teams["team_id"].duplicated(), "team_id"]
            raise ValueError(f"duplicate team_id in teams.csv: {dups.tolist()}")

        # Alias uniqueness is per (alias, source); same spelling can map
        # identically from multiple sources. Global alias→id must agree.
        by_alias: dict[str, str] = {}
        for _, row in self.aliases.iterrows():
            alias = str(row["alias"]).strip()
            team_id = str(row["team_id"]).strip()
            if alias in by_alias and by_alias[alias] != team_id:
                raise ValueError(
                    f"alias {alias!r} maps to both {by_alias[alias]!r} and {team_id!r}"
                )
            by_alias[alias] = team_id
            # Also index lowercase for case-insensitive fallback
            by_alias.setdefault(alias.lower(), team_id)

        unknown_ids = set(by_alias.values()) - set(self.teams["team_id"])
        if unknown_ids:
            raise ValueError(f"aliases reference unknown team_id: {sorted(unknown_ids)}")

        self._lookup = by_alias

    def resolve(self, name: str, source: str | None = None) -> str:
        """Map a raw name to team_id. Raises UnknownTeamError if missing."""
        if name is None or (isinstance(name, float) and pd.isna(name)):
            raise UnknownTeamError("null team name")
        key = str(name).strip()
        if not key or key.lower() == "nan":
            raise UnknownTeamError(f"empty team name (source={source})")

        if source:
            # Prefer exact (alias, source) when available
            match = self.aliases[
                (self.aliases["alias"] == key) & (self.aliases["source"] == source)
            ]
            if len(match) == 1:
                return str(match.iloc[0]["team_id"])

        if key in self._lookup:
            return self._lookup[key]
        lower = key.lower()
        if lower in self._lookup:
            return self._lookup[lower]

        raise UnknownTeamError(
            f"unknown team alias {key!r} (source={source}). "
            f"Add it to ref/team_aliases.csv"
        )

    def resolve_series(self, series: pd.Series, source: str | None = None) -> pd.Series:
        unknown: list[str] = []
        out: list[str] = []
        for val in series:
            try:
                out.append(self.resolve(val, source=source))
            except UnknownTeamError:
                unknown.append(str(val))
                out.append("")  # placeholder; we raise below
        if unknown:
            uniq = sorted(set(unknown))
            raise UnknownTeamError(
                f"{len(uniq)} unknown alias(es): {uniq}. "
                f"Add them to ref/team_aliases.csv"
            )
        return pd.Series(out, index=series.index, dtype="string")


def load_ref_tables(con: duckdb.DuckDBPyConnection, resolver: TeamResolver) -> None:
    con.execute("DELETE FROM team_aliases")
    con.execute("DELETE FROM teams")
    con.register("_teams", resolver.teams)
    con.execute("INSERT INTO teams SELECT team_id, canonical_name, NULL, NULL FROM _teams")
    con.unregister("_teams")
    con.register("_aliases", resolver.aliases)
    con.execute("INSERT INTO team_aliases SELECT alias, source, team_id FROM _aliases")
    con.unregister("_aliases")


def promote_staging_to_matches(
    con: duckdb.DuckDBPyConnection,
    resolver: TeamResolver,
) -> int:
    """Resolve staging team names and (re)build the matches table."""
    staging = con.execute("SELECT * FROM matches_staging ORDER BY match_date").fetchdf()
    if staging.empty:
        raise RuntimeError("matches_staging is empty — run collectors.results first")

    home_ids = resolver.resolve_series(staging["home_team_raw"], source="football-data")
    away_ids = resolver.resolve_series(staging["away_team_raw"], source="football-data")

    matches = pd.DataFrame(
        {
            "match_id": [
                f"{row.match_date.date()}_{hid}_{aid}"
                for row, hid, aid in zip(staging.itertuples(), home_ids, away_ids)
            ],
            "season": staging["season"],
            "match_date": staging["match_date"],
            "kickoff_utc": pd.NaT,
            "home_team_id": home_ids,
            "away_team_id": away_ids,
            "home_goals": staging["home_goals"],
            "away_goals": staging["away_goals"],
            "home_xg": pd.NA,
            "away_xg": pd.NA,
            "referee": staging["referee"],
            "odds_open_h": staging["odds_open_h"],
            "odds_open_d": staging["odds_open_d"],
            "odds_open_a": staging["odds_open_a"],
            "odds_close_h": staging["odds_close_h"],
            "odds_close_d": staging["odds_close_d"],
            "odds_close_a": staging["odds_close_a"],
            "crowd_present": [
                crowd_present_for_date(d) for d in staging["match_date"]
            ],
        }
    )

    if matches["match_id"].duplicated().any():
        dups = matches.loc[matches["match_id"].duplicated(keep=False), "match_id"]
        raise RuntimeError(f"duplicate match_id values: {dups.head(10).tolist()}")

    null_teams = matches["home_team_id"].isna().sum() + matches["away_team_id"].isna().sum()
    if null_teams:
        raise RuntimeError(f"{null_teams} null team_id values after resolve")

    empty = (matches["home_team_id"] == "") | (matches["away_team_id"] == "")
    if empty.any():
        raise RuntimeError(f"{int(empty.sum())} empty team_id values after resolve")

    con.execute("DELETE FROM matches")
    # Existing DBs created before Day 9 may lack crowd_present.
    con.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS crowd_present BOOLEAN")
    con.register("_matches", matches)
    con.execute(
        """
        INSERT INTO matches (
          match_id, season, match_date, kickoff_utc,
          home_team_id, away_team_id, home_goals, away_goals,
          home_xg, away_xg, referee,
          odds_open_h, odds_open_d, odds_open_a,
          odds_close_h, odds_close_d, odds_close_a,
          crowd_present
        )
        SELECT
          match_id, season, match_date, kickoff_utc,
          home_team_id, away_team_id, home_goals, away_goals,
          home_xg, away_xg, referee,
          odds_open_h, odds_open_d, odds_open_a,
          odds_close_h, odds_close_d, odds_close_a,
          crowd_present
        FROM _matches
        """
    )
    con.unregister("_matches")
    return len(matches)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve team aliases and build matches.")
    parser.add_argument("--teams", type=Path, default=DEFAULT_TEAMS)
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIASES)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="resolve staging names but do not write matches",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    resolver = TeamResolver(args.teams, args.aliases)
    log.info(
        "loaded %d teams, %d aliases",
        len(resolver.teams),
        len(resolver.aliases),
    )

    # Dry-run resolve against staging first so we fail before writing.
    con = duckdb.connect(str(args.db))
    try:
        con.execute(args.schema.read_text(encoding="utf-8"))
        staging = con.execute(
            "SELECT DISTINCT home_team_raw AS name FROM matches_staging "
            "UNION SELECT DISTINCT away_team_raw FROM matches_staging"
        ).fetchdf()
        if staging.empty:
            log.error("matches_staging empty — run: uv run python -m collectors.results")
            return 1

        resolver.resolve_series(staging["name"], source="football-data")
        log.info("all %d distinct football-data names resolve", len(staging))

        if args.check_only:
            return 0

        load_ref_tables(con, resolver)
        n = promote_staging_to_matches(con, resolver)

        nulls = con.execute(
            """
            SELECT COUNT(*) FROM matches
            WHERE home_team_id IS NULL OR away_team_id IS NULL
               OR home_team_id = '' OR away_team_id = ''
            """
        ).fetchone()[0]
        dups = con.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT match_id FROM matches GROUP BY 1 HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]

        log.info("matches rows=%d null_team_ids=%d duplicate_ids=%d", n, nulls, dups)
        if nulls or dups:
            return 1
    except UnknownTeamError as exc:
        log.error("%s", exc)
        return 1
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
