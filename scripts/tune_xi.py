"""Tune Dixon-Coles time-decay half-life on early seasons only (Day 13).

Grid-search half-lives on 2015-16..2018-19 walk-forward RPS, then report
the winner for the full 2015-26 backtest. Holdout seasons are NOT used
to pick ξ.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.walkforward import load_matches, run_walkforward, write_predictions
from eval.metrics import outcome_index, summarise

log = logging.getLogger("tune_xi")

DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_REPORT = ROOT / "docs" / "xi_tune.md"
DEFAULT_HALF_LIVES = [60.0, 90.0, 182.5, 365.0]


def score_preds(preds: pd.DataFrame, matches: pd.DataFrame) -> float:
    joined = preds.merge(
        matches[["match_id", "home_goals", "away_goals", "season"]],
        on="match_id",
        how="inner",
    )
    if joined.empty:
        return float("nan")
    y = outcome_index(joined["home_goals"], joined["away_goals"])
    return summarise(joined["p_home"], joined["p_draw"], joined["p_away"], y).rps_mean


def main() -> int:
    parser = argparse.ArgumentParser(description="Grid-search DC half-life on early seasons.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--tune-start", default="2015-08-01")
    parser.add_argument("--tune-end", default="2019-05-31")
    parser.add_argument(
        "--half-lives",
        default=",".join(str(h) for h in DEFAULT_HALF_LIVES),
        help="comma-separated half-lives in days",
    )
    parser.add_argument("--stride", type=int, default=2,
                        help="every Nth matchday during tune (speed)")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--write-db", action="store_true",
                        help="also persist tune-window predictions")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    half_lives = [float(x) for x in args.half_lives.split(",") if x.strip()]
    start = pd.Timestamp(args.tune_start)
    end = pd.Timestamp(args.tune_end)

    con = duckdb.connect(str(args.db))
    try:
        matches = load_matches(con)
        log.info(
            "tuning on %s .. %s  half_lives=%s  stride=%d",
            start.date(), end.date(), half_lives, args.stride,
        )

        rows = []
        best_rps = float("inf")
        best_hl = half_lives[0]

        for hl in half_lives:
            xi = np.log(2) / hl
            version = f"dc-tune-hl{hl:.0f}"
            log.info("--- half-life=%.1fd  xi=%.5f ---", hl, xi)
            preds = run_walkforward(
                matches,
                start=start,
                end=end,
                xi=xi,
                model_version=version,
                stride=args.stride,
            )
            rps = score_preds(preds, matches)
            log.info("half-life=%.1f  RPS=%.4f  n=%d", hl, rps, len(preds))
            rows.append({"half_life_days": hl, "xi": xi, "rps": rps, "n": len(preds)})
            if rps < best_rps:
                best_rps = rps
                best_hl = hl
            if args.write_db and not preds.empty:
                write_predictions(con, preds)

        table = pd.DataFrame(rows).sort_values("rps")
        log.info("BEST half-life=%.1fd  RPS=%.4f", best_hl, best_rps)

        lines = [
            "# ξ / half-life tune (Day 13)",
            "",
            f"Tune window: **{start.date()} -> {end.date()}** (early seasons only).",
            f"Stride: every **{args.stride}** matchday(s).",
            "",
            "Holdout seasons (2019-20+) were **not** used to pick xi.",
            "",
            "| half-life (days) | xi | RPS | n |",
            "|-----------------:|--:|----:|--:|",
        ]
        for r in table.itertuples(index=False):
            mark = " **<- best**" if r.half_life_days == best_hl else ""
            lines.append(
                f"| {r.half_life_days:.1f} | {r.xi:.5f} | {r.rps:.4f} | {r.n} |{mark}"
            )
        lines += [
            "",
            f"**Selected half-life: {best_hl:.1f} days** "
            f"(xi = {np.log(2) / best_hl:.5f}).",
            "",
            "Use this for the full 2015-16 -> 2025-26 walk-forward.",
            "",
        ]
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines), encoding="utf-8")
        log.info("wrote %s", args.report)

        # Machine-readable pick for downstream scripts
        pick = ROOT / "docs" / "xi_best.txt"
        pick.write_text(f"{best_hl}\n", encoding="utf-8")
        log.info("wrote %s", pick)
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
