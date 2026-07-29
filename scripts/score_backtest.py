"""Score stored backtest predictions against results + benchmarks (Day 12)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Running as `python scripts/foo.py` puts scripts/ on sys.path, not the repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb
import pandas as pd

from eval.benchmarks import score_naive_baselines, score_odds_benchmark
from eval.metrics import bootstrap_season_cis, score_predictions

log = logging.getLogger("score_backtest")

DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_REPORT = ROOT / "docs" / "eval_smoke.md"


def load_joined(
    con: duckdb.DuckDBPyConnection,
    variant: str = "backtest",
) -> pd.DataFrame:
    return con.execute(
        """
        SELECT
          p.prediction_id, p.match_id, p.model_version, p.model_variant,
          p.p_home, p.p_draw, p.p_away, p.p_btts, p.p_over25,
          p.git_sha, p.created_at,
          m.season, m.match_date,
          m.home_team_id, m.away_team_id,
          m.home_goals, m.away_goals,
          m.odds_open_h, m.odds_open_d, m.odds_open_a,
          m.odds_close_h, m.odds_close_d, m.odds_close_a
        FROM predictions p
        JOIN matches m ON m.match_id = p.match_id
        WHERE p.model_variant = ?
          AND m.home_goals IS NOT NULL
        ORDER BY m.match_date
        """,
        [variant],
    ).fetchdf()


def main() -> int:
    parser = argparse.ArgumentParser(description="Score backtest predictions.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--variant", default="backtest")
    parser.add_argument("--model-version", default=None,
                        help="optional filter on predictions.model_version")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--n-boot", type=int, default=1000)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    con = duckdb.connect(str(args.db), read_only=True)
    try:
        if args.model_version:
            df = con.execute(
                """
                SELECT
                  p.prediction_id, p.match_id, p.model_version, p.model_variant,
                  p.p_home, p.p_draw, p.p_away, p.p_btts, p.p_over25,
                  p.git_sha, p.created_at,
                  m.season, m.match_date,
                  m.home_team_id, m.away_team_id,
                  m.home_goals, m.away_goals,
                  m.odds_open_h, m.odds_open_d, m.odds_open_a,
                  m.odds_close_h, m.odds_close_d, m.odds_close_a
                FROM predictions p
                JOIN matches m ON m.match_id = p.match_id
                WHERE p.model_variant = ? AND p.model_version = ?
                  AND m.home_goals IS NOT NULL
                ORDER BY m.match_date
                """,
                [args.variant, args.model_version],
            ).fetchdf()
        else:
            df = load_joined(con, variant=args.variant)
    finally:
        con.close()

    if df.empty:
        log.error("no predictions for variant=%s — run walkforward first", args.variant)
        return 1

    log.info("scoring %d predictions (%s .. %s)", len(df), df["season"].min(), df["season"].max())

    summary, cal, per_season = score_predictions(df)
    log.info(
        "model RPS=%.4f  logloss=%.4f  brier=%.4f  n=%d",
        summary.rps_mean,
        summary.logloss_mean,
        summary.brier_mean,
        summary.n,
    )

    lines = [
        "# Eval smoke report",
        "",
        f"Variant: `{args.variant}`  ",
        f"Matches: **{summary.n}**  ",
        f"Seasons: {df['season'].min()} .. {df['season'].max()}",
        "",
        "## Model",
        "",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| RPS | {summary.rps_mean:.4f} |",
        f"| Log loss | {summary.logloss_mean:.4f} |",
        f"| Brier | {summary.brier_mean:.4f} |",
        "",
    ]

    # Benchmarks on the same rows
    benches = []
    try:
        benches.append(
            score_odds_benchmark(
                df["odds_close_h"],
                df["odds_close_d"],
                df["odds_close_a"],
                df["home_goals"],
                df["away_goals"],
                name="closing_devig",
            )
        )
    except ValueError as exc:
        log.warning("closing odds benchmark skipped: %s", exc)

    try:
        benches.append(
            score_odds_benchmark(
                df["odds_open_h"],
                df["odds_open_d"],
                df["odds_open_a"],
                df["home_goals"],
                df["away_goals"],
                name="opening_devig",
            )
        )
    except ValueError as exc:
        log.warning("opening odds benchmark skipped: %s", exc)

    benches.extend(
        score_naive_baselines(
            df["home_goals"].to_numpy(),
            df["away_goals"].to_numpy(),
            # Honest-ish: use all prior completed matches in DB would be better;
            # for smoke, in-sample rates are labelled as such.
        )
    )

    lines += ["## Benchmarks", "", "| Name | n | RPS | Log loss | Brier |", "|------|--:|----:|---------:|------:|"]
    for b in benches:
        log.info(
            "benchmark %-18s RPS=%.4f logloss=%.4f brier=%.4f n=%d",
            b.name, b.rps, b.logloss, b.brier, b.n,
        )
        lines.append(
            f"| {b.name} | {b.n} | {b.rps:.4f} | {b.logloss:.4f} | {b.brier:.4f} |"
        )
    lines.append("")

    # Bootstrap CIs (need >= 2 seasons for meaningful season bootstrap;
    # with 1 season, still runs but CI is degenerate — warn)
    n_seasons = df["season"].nunique()
    if n_seasons >= 1:
        boot = bootstrap_season_cis(df, n_boot=args.n_boot, metric="rps")
        log.info(
            "bootstrap RPS mean=%.4f CI=[%.4f, %.4f] (seasons=%d)",
            boot["mean"], boot["ci_low"], boot["ci_high"], boot["n_seasons"],
        )
        lines += [
            "## Bootstrap RPS (season resample)",
            "",
            f"- mean: **{boot['mean']:.4f}**",
            f"- 95% CI: [{boot['ci_low']:.4f}, {boot['ci_high']:.4f}]",
            f"- seasons: {boot['n_seasons']}, boots: {boot['n_boot']}",
            "",
        ]
        if n_seasons < 2:
            lines.append(
                "_Note: fewer than 2 seasons — CI is not meaningful yet "
                "(Day 13 full backtest will fix this)._"
            )
            lines.append("")

    if not per_season.empty:
        lines += ["## Per season", "", per_season.to_string(index=False), ""]

    if not cal.empty:
        lines += [
            "## Calibration (5pp bins, sample)",
            "",
            cal.head(20).to_string(index=False),
            "",
        ]

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("wrote %s", args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
