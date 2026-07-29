"""Smoke-fit Dixon-Coles on DuckDB matches (Day 9)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb
import pandas as pd

from models.dixon_coles import DixonColes

log = logging.getLogger("fit_dc")

DEFAULT_DB = ROOT / "data" / "myriad.duckdb"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit Dixon-Coles baseline.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--min-season",
        default="2014-15",
        help="earliest season to include (default 2014-15, xG era)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    con = duckdb.connect(str(args.db), read_only=True)
    try:
        df = con.execute(
            """
            SELECT match_date, home_team_id, away_team_id,
                   home_goals, away_goals, crowd_present, season
            FROM matches
            WHERE season >= ?
              AND home_goals IS NOT NULL
              AND away_goals IS NOT NULL
            ORDER BY match_date
            """,
            [args.min_season],
        ).fetchdf()
    finally:
        con.close()

    empty = (~df["crowd_present"].astype(bool)).sum() if "crowd_present" in df.columns else 0
    log.info(
        "training rows=%d seasons=%s..%s empty_stadium=%d",
        len(df),
        df["season"].min(),
        df["season"].max(),
        int(empty),
    )

    model = DixonColes()
    result = model.fit(df)

    # Rank teams by attack - defence (rough strength)
    strength = {
        t: result.attack[t] - result.defence[t] for t in result.teams
    }
    ranked = sorted(strength.items(), key=lambda x: -x[1])
    log.info("top 5 by attack-defence:")
    for t, s in ranked[:5]:
        log.info("  %s  strength=%.3f  α=%.3f  β=%.3f", t, s, result.attack[t], result.defence[t])
    log.info("bottom 5:")
    for t, s in ranked[-5:]:
        log.info("  %s  strength=%.3f  α=%.3f  β=%.3f", t, s, result.attack[t], result.defence[t])

    # Sample rates: Arsenal vs Man City with crowd
    if "arsenal" in result.attack and "man_city" in result.attack:
        lh, la = model.rates("arsenal", "man_city", crowd_present=True)
        log.info("sample λ Arsenal vs Man City (crowd): home=%.3f away=%.3f", lh, la)

    if not result.success:
        log.warning("optimizer reported success=False: %s", result.message)
        # L-BFGS-B often stops on ftol with success=True; if False still check nll
    log.info(
        "γ=%.3f γ_empty=%.3f (empty should be closer to 1.0) ρ=%.4f",
        result.home_adv,
        result.home_adv_empty,
        result.rho,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
