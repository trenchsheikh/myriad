"""Write a calibration plot from scored backtest predictions (Day 13)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.metrics import calibration_table, outcome_index

log = logging.getLogger("plot_cal")

DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_OUT = ROOT / "docs" / "calibration.png"


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibration plot for backtest preds.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--variant", default="backtest")
    parser.add_argument("--model-version", default=None,
                        help="optional filter on predictions.model_version")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    con = duckdb.connect(str(args.db), read_only=True)
    try:
        if args.model_version:
            df = con.execute(
                """
                SELECT p.p_home, p.p_draw, p.p_away,
                       m.home_goals, m.away_goals, m.season
                FROM predictions p
                JOIN matches m ON m.match_id = p.match_id
                WHERE p.model_variant = ? AND p.model_version = ?
                  AND m.home_goals IS NOT NULL
                """,
                [args.variant, args.model_version],
            ).fetchdf()
        else:
            df = con.execute(
                """
                SELECT p.p_home, p.p_draw, p.p_away,
                       m.home_goals, m.away_goals, m.season
                FROM predictions p
                JOIN matches m ON m.match_id = p.match_id
                WHERE p.model_variant = ?
                  AND m.home_goals IS NOT NULL
                """,
                [args.variant],
            ).fetchdf()
    finally:
        con.close()

    if df.empty:
        log.error("no predictions to plot")
        return 1

    y = outcome_index(df["home_goals"], df["away_goals"])
    cal = calibration_table(df["p_home"], df["p_draw"], df["p_away"], y, bin_width=0.05)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
    for ax, outcome, color in zip(
        axes, ["home", "draw", "away"], ["#2a6f97", "#6c757d", "#9b2226"]
    ):
        sub = cal.loc[cal["outcome"] == outcome]
        ax.plot([0, 1], [0, 1], "--", color="#adb5bd", linewidth=1)
        if not sub.empty:
            ax.scatter(
                sub["mean_predicted"],
                sub["realised_freq"],
                s=np.clip(sub["n"] * 3, 20, 200),
                c=color,
                alpha=0.85,
                edgecolors="white",
                linewidths=0.5,
            )
        ax.set_title(outcome.capitalize())
        ax.set_xlabel("Predicted probability")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal")
    axes[0].set_ylabel("Realised frequency")
    fig.suptitle(
        f"Calibration (5pp bins) — n={len(df)}  "
        f"{df['season'].min()}..{df['season'].max()}",
        fontsize=12,
    )
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=140)
    plt.close(fig)
    log.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
