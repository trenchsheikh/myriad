"""Walk-forward backtest harness (Day 11).

For each matchday D in the test range:
  1. Build training set with asof_ts < D
  2. Assert leakage checklist
  3. Fit Dixon-Coles
  4. Predict every fixture on D
  5. Append-only insert into predictions (model_variant='backtest')

Never fits on future data. Closing odds are never features.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from backtest.leakage import LeakageError, run_all_fit_guards
from models.dixon_coles import DEFAULT_XI, DixonColes
from models.score_matrix import predict_match

log = logging.getLogger("walkforward")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "myriad.duckdb"
DEFAULT_SCHEMA = ROOT / "db" / "schema.sql"
MODEL_VERSION = "dc-v0.1"
MODEL_VARIANT = "backtest"


def git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def load_matches(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = con.execute(
        """
        SELECT
          match_id, season, match_date, kickoff_utc,
          home_team_id, away_team_id,
          home_goals, away_goals,
          crowd_present,
          odds_open_h, odds_open_d, odds_open_a,
          home_xg, away_xg, referee
        FROM matches
        WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL
        ORDER BY COALESCE(kickoff_utc, CAST(match_date AS TIMESTAMP))
        """
    ).fetchdf()
    df["match_date"] = pd.to_datetime(df["match_date"])
    # asof_ts: prefer kickoff_utc; fall back to match_date at midnight UTC
    ko = pd.to_datetime(df["kickoff_utc"], utc=True, errors="coerce")
    fallback = pd.to_datetime(df["match_date"], utc=True)
    df["asof_ts"] = ko.fillna(fallback).dt.tz_convert("UTC").dt.tz_localize(None)
    if "crowd_present" in df.columns:
        df["crowd_present"] = df["crowd_present"].fillna(True).astype(bool)
    else:
        df["crowd_present"] = True
    return df


def matchdays_in_range(
    df: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[pd.Timestamp]:
    mask = (df["asof_ts"] >= start) & (df["asof_ts"] <= end)
    days = (
        df.loc[mask, "asof_ts"]
        .dt.normalize()
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    return [pd.Timestamp(d) for d in days]


def prediction_id(match_id: str, variant: str, version: str, sha: str) -> str:
    raw = f"{match_id}|{variant}|{version}|{sha}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def rates_or_league_avg(
    model: DixonColes,
    home: str,
    away: str,
    crowd: bool,
) -> tuple[float, float]:
    """Predict rates; unseen promoted sides get league-average attack/defence."""
    r = model.result_
    assert r is not None
    avg_att = float(np.mean(list(r.attack.values())))
    avg_def = float(np.mean(list(r.defence.values())))

    def att(t: str) -> float:
        return r.attack[t] if t in r.attack else avg_att

    def deff(t: str) -> float:
        return r.defence[t] if t in r.defence else avg_def

    gamma = r.home_adv if crowd else r.home_adv_empty
    lam_h = float(np.exp(att(home) + deff(away) + np.log(gamma)))
    lam_a = float(np.exp(att(away) + deff(home)))
    return lam_h, lam_a


def run_walkforward(
    matches: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    xi: float = DEFAULT_XI,
    max_matchdays: int | None = None,
    sha: str | None = None,
) -> pd.DataFrame:
    """Return a dataframe of predictions (not yet written to DB)."""
    sha = sha or git_sha()
    days = matchdays_in_range(matches, start, end)
    if max_matchdays is not None:
        days = days[:max_matchdays]

    if not days:
        raise ValueError(f"no matchdays between {start.date()} and {end.date()}")

    log.info(
        "walk-forward: %d matchdays from %s to %s (xi=%.5f)",
        len(days),
        days[0].date(),
        days[-1].date(),
        xi,
    )

    rows: list[dict] = []
    created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    model = DixonColes(xi=xi)

    for i, day in enumerate(days, 1):
        # Prediction timestamp D = start of that matchday (midnight).
        # All fixtures on this calendar day are predicted with info < midnight.
        # More precisely: fit on asof_ts < day's first kickoff would be ideal;
        # PRD says kickoff_utc < D. We use day-normalized midnight as D so
        # same-day earlier kickoffs don't leak into later ones on that day
        # via a shared fit — conservative (slightly less info than ideal).
        as_of = pd.Timestamp(day)

        train = matches.loc[matches["asof_ts"] < as_of].copy()
        test = matches.loc[matches["asof_ts"].dt.normalize() == as_of].copy()

        if train.empty:
            log.warning("skip %s — no training history", as_of.date())
            continue
        if test.empty:
            continue

        # --- Leakage checklist (assertions, not comments) ---
        run_all_fit_guards(train, as_of)

        # Fit uses only DC columns (explicitly drop anything unused)
        fit_cols = [
            c
            for c in [
                "match_id",
                "match_date",
                "asof_ts",
                "home_team_id",
                "away_team_id",
                "home_goals",
                "away_goals",
                "crowd_present",
                "season",
            ]
            if c in train.columns
        ]
        fit_df = train[fit_cols]
        run_all_fit_guards(fit_df, as_of)

        try:
            # Reuse model instance so warm-start carries across matchdays
            model.fit(fit_df, as_of=None)
        except Exception:
            log.exception("fit failed on %s", as_of.date())
            raise

        # Extra hard assert inside the fitted window
        if (fit_df["asof_ts"] >= as_of).any():
            raise LeakageError("post-fit leakage check failed")

        for row in test.itertuples(index=False):
            crowd = bool(getattr(row, "crowd_present", True))
            lam_h, lam_a = rates_or_league_avg(
                model, row.home_team_id, row.away_team_id, crowd
            )
            probs = predict_match(lam_h, lam_a, rho=model.result_.rho)
            pid = prediction_id(row.match_id, MODEL_VARIANT, MODEL_VERSION, sha)
            rows.append(
                {
                    "prediction_id": pid,
                    "created_at": created_at,
                    "model_version": MODEL_VERSION,
                    "model_variant": MODEL_VARIANT,
                    "match_id": row.match_id,
                    "p_home": probs["p_home"],
                    "p_draw": probs["p_draw"],
                    "p_away": probs["p_away"],
                    "p_btts": probs["p_btts"],
                    "p_over25": probs["p_over25"],
                    "is_locked": True,
                    "git_sha": sha,
                    "asof_ts": as_of,
                    "lam_home": lam_h,
                    "lam_away": lam_a,
                }
            )

        if i % 10 == 0 or i == len(days):
            log.info(
                "  %d/%d matchdays  last=%s  preds=%d  train=%d",
                i, len(days), as_of.date(), len(rows), len(train),
            )

    return pd.DataFrame(rows)


def write_predictions(con: duckdb.DuckDBPyConnection, preds: pd.DataFrame) -> int:
    """Append-only insert; skip prediction_ids already present."""
    if preds.empty:
        return 0

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
          prediction_id   VARCHAR PRIMARY KEY,
          created_at      TIMESTAMP,
          model_version   VARCHAR,
          model_variant   VARCHAR,
          match_id        VARCHAR,
          p_home          DOUBLE,
          p_draw          DOUBLE,
          p_away          DOUBLE,
          p_btts          DOUBLE,
          p_over25        DOUBLE,
          is_locked       BOOLEAN,
          git_sha         VARCHAR
        )
        """
    )

    db_cols = [
        "prediction_id",
        "created_at",
        "model_version",
        "model_variant",
        "match_id",
        "p_home",
        "p_draw",
        "p_away",
        "p_btts",
        "p_over25",
        "is_locked",
        "git_sha",
    ]
    frame = preds[db_cols].copy()

    existing = {
        r[0]
        for r in con.execute("SELECT prediction_id FROM predictions").fetchall()
    }
    fresh = frame.loc[~frame["prediction_id"].isin(existing)]
    skipped = len(frame) - len(fresh)
    if skipped:
        log.info("skipping %d already-stored prediction_ids (append-only)", skipped)
    if fresh.empty:
        return 0

    con.register("_preds", fresh)
    con.execute(
        f"INSERT INTO predictions SELECT {', '.join(db_cols)} FROM _preds"
    )
    con.unregister("_preds")
    return len(fresh)


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward Dixon-Coles backtest.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start", default="2024-08-01", help="YYYY-MM-DD")
    parser.add_argument("--end", default="2025-05-31", help="YYYY-MM-DD")
    parser.add_argument("--max-matchdays", type=int, default=None)
    parser.add_argument("--xi", type=float, default=DEFAULT_XI)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fit+predict but do not write to DuckDB",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)

    con = duckdb.connect(str(args.db))
    try:
        matches = load_matches(con)
        log.info("loaded %d completed matches", len(matches))

        preds = run_walkforward(
            matches,
            start=start,
            end=end,
            xi=args.xi,
            max_matchdays=args.max_matchdays,
        )
        log.info(
            "produced %d predictions  p_home mean=%.3f",
            len(preds),
            preds["p_home"].mean() if len(preds) else float("nan"),
        )

        if args.dry_run:
            log.info("dry-run — not writing to DB")
            print(preds.head(10).to_string(index=False))
            return 0

        n = write_predictions(con, preds)
        total = con.execute(
            "SELECT COUNT(*) FROM predictions WHERE model_variant = ?",
            [MODEL_VARIANT],
        ).fetchone()[0]
        log.info("inserted %d new rows; backtest predictions in DB: %d", n, total)
    except LeakageError as exc:
        log.error("LEAKAGE GUARD FIRED: %s", exc)
        return 2
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
