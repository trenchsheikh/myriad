"""Evaluation metrics for 1X2 football forecasts.

Headline metric: Ranked Probability Score (RPS).
Also: log loss, Brier score, calibration bins, bootstrap CIs over seasons.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

OUTCOME_HOME, OUTCOME_DRAW, OUTCOME_AWAY = 0, 1, 2


def outcome_index(home_goals: np.ndarray, away_goals: np.ndarray) -> np.ndarray:
    """Map scorelines to {0: home, 1: draw, 2: away}."""
    hg = np.asarray(home_goals)
    ag = np.asarray(away_goals)
    out = np.full(len(hg), OUTCOME_DRAW, dtype=int)
    out[hg > ag] = OUTCOME_HOME
    out[hg < ag] = OUTCOME_AWAY
    return out


def rps(
    p_home: np.ndarray,
    p_draw: np.ndarray,
    p_away: np.ndarray,
    outcomes: np.ndarray,
) -> np.ndarray:
    """Per-match Ranked Probability Score for ordered outcomes H < D < A.

    RPS = 0.5 * sum_{k=1}^{K-1} (CDF_pred(k) - CDF_obs(k))^2
    Lower is better. Perfect = 0.
    """
    p_home = np.asarray(p_home, dtype=float)
    p_draw = np.asarray(p_draw, dtype=float)
    p_away = np.asarray(p_away, dtype=float)
    y = np.asarray(outcomes, dtype=int)

    # Predicted CDF at H and at H+D
    cdf_p1 = p_home
    cdf_p2 = p_home + p_draw

    # Observed CDF: 1 if outcome <= category, else 0
    cdf_o1 = (y <= OUTCOME_HOME).astype(float)
    cdf_o2 = (y <= OUTCOME_DRAW).astype(float)

    return 0.5 * ((cdf_p1 - cdf_o1) ** 2 + (cdf_p2 - cdf_o2) ** 2)


def log_loss(
    p_home: np.ndarray,
    p_draw: np.ndarray,
    p_away: np.ndarray,
    outcomes: np.ndarray,
    eps: float = 1e-15,
) -> np.ndarray:
    """Per-match categorical log loss."""
    probs = np.column_stack(
        [
            np.asarray(p_home, dtype=float),
            np.asarray(p_draw, dtype=float),
            np.asarray(p_away, dtype=float),
        ]
    )
    probs = np.clip(probs, eps, 1.0)
    probs = probs / probs.sum(axis=1, keepdims=True)
    y = np.asarray(outcomes, dtype=int)
    return -np.log(probs[np.arange(len(y)), y])


def brier(
    p_home: np.ndarray,
    p_draw: np.ndarray,
    p_away: np.ndarray,
    outcomes: np.ndarray,
) -> np.ndarray:
    """Per-match multi-class Brier score."""
    probs = np.column_stack(
        [
            np.asarray(p_home, dtype=float),
            np.asarray(p_draw, dtype=float),
            np.asarray(p_away, dtype=float),
        ]
    )
    y = np.asarray(outcomes, dtype=int)
    one_hot = np.zeros_like(probs)
    one_hot[np.arange(len(y)), y] = 1.0
    return np.sum((probs - one_hot) ** 2, axis=1)


@dataclass
class MetricSummary:
    rps_mean: float
    logloss_mean: float
    brier_mean: float
    n: int


def summarise(
    p_home: np.ndarray,
    p_draw: np.ndarray,
    p_away: np.ndarray,
    outcomes: np.ndarray,
) -> MetricSummary:
    return MetricSummary(
        rps_mean=float(np.mean(rps(p_home, p_draw, p_away, outcomes))),
        logloss_mean=float(np.mean(log_loss(p_home, p_draw, p_away, outcomes))),
        brier_mean=float(np.mean(brier(p_home, p_draw, p_away, outcomes))),
        n=int(len(outcomes)),
    )


def calibration_table(
    p_home: np.ndarray,
    p_draw: np.ndarray,
    p_away: np.ndarray,
    outcomes: np.ndarray,
    bin_width: float = 0.05,
) -> pd.DataFrame:
    """Bin each outcome's predicted probability in `bin_width` buckets.

    Returns rows: outcome, bin_lo, bin_hi, n, mean_predicted, realised_freq.
    """
    labels = ["home", "draw", "away"]
    preds = {
        "home": np.asarray(p_home, dtype=float),
        "draw": np.asarray(p_draw, dtype=float),
        "away": np.asarray(p_away, dtype=float),
    }
    y = np.asarray(outcomes, dtype=int)
    realised = {
        "home": (y == OUTCOME_HOME).astype(float),
        "draw": (y == OUTCOME_DRAW).astype(float),
        "away": (y == OUTCOME_AWAY).astype(float),
    }

    edges = np.arange(0.0, 1.0 + bin_width, bin_width)
    rows: list[dict] = []
    for name in labels:
        p = preds[name]
        r = realised[name]
        # right-inclusive last bin
        bins = np.digitize(p, edges[1:-1], right=False)
        for b in range(len(edges) - 1):
            mask = bins == b
            n = int(mask.sum())
            if n == 0:
                continue
            rows.append(
                {
                    "outcome": name,
                    "bin_lo": float(edges[b]),
                    "bin_hi": float(edges[b + 1]),
                    "n": n,
                    "mean_predicted": float(p[mask].mean()),
                    "realised_freq": float(r[mask].mean()),
                }
            )
    return pd.DataFrame(rows)


def bootstrap_season_cis(
    frame: pd.DataFrame,
    n_boot: int = 1000,
    seed: int = 42,
    metric: str = "rps",
) -> dict[str, float]:
    """Bootstrap CIs by resampling seasons (not individual matches).

    `frame` must contain columns: season, p_home, p_draw, p_away,
    home_goals, away_goals.
    """
    required = {"season", "p_home", "p_draw", "p_away", "home_goals", "away_goals"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"bootstrap frame missing {sorted(missing)}")

    seasons = frame["season"].unique()
    if len(seasons) == 0:
        raise ValueError("no seasons to bootstrap")

    rng = np.random.default_rng(seed)
    scores = np.empty(n_boot, dtype=float)

    for i in range(n_boot):
        sample_seasons = rng.choice(seasons, size=len(seasons), replace=True)
        parts = [frame.loc[frame["season"] == s] for s in sample_seasons]
        boot = pd.concat(parts, ignore_index=True)
        y = outcome_index(boot["home_goals"].to_numpy(), boot["away_goals"].to_numpy())
        if metric == "rps":
            scores[i] = float(
                np.mean(rps(boot["p_home"], boot["p_draw"], boot["p_away"], y))
            )
        elif metric == "logloss":
            scores[i] = float(
                np.mean(log_loss(boot["p_home"], boot["p_draw"], boot["p_away"], y))
            )
        elif metric == "brier":
            scores[i] = float(
                np.mean(brier(boot["p_home"], boot["p_draw"], boot["p_away"], y))
            )
        else:
            raise ValueError(f"unknown metric {metric!r}")

    return {
        "metric": metric,
        "mean": float(scores.mean()),
        "std": float(scores.std(ddof=1)),
        "ci_low": float(np.quantile(scores, 0.025)),
        "ci_high": float(np.quantile(scores, 0.975)),
        "n_boot": n_boot,
        "n_seasons": int(len(seasons)),
    }


def score_predictions(df: pd.DataFrame) -> tuple[MetricSummary, pd.DataFrame, pd.DataFrame]:
    """Score a joined predictions+results frame.

    Required columns: p_home, p_draw, p_away, home_goals, away_goals.
    Optional: season (for per-season breakdown).
    """
    y = outcome_index(df["home_goals"].to_numpy(), df["away_goals"].to_numpy())
    summary = summarise(df["p_home"], df["p_draw"], df["p_away"], y)
    cal = calibration_table(df["p_home"], df["p_draw"], df["p_away"], y)

    per_season = pd.DataFrame()
    if "season" in df.columns:
        rows = []
        for season, g in df.groupby("season"):
            yy = outcome_index(g["home_goals"].to_numpy(), g["away_goals"].to_numpy())
            s = summarise(g["p_home"], g["p_draw"], g["p_away"], yy)
            rows.append(
                {
                    "season": season,
                    "n": s.n,
                    "rps": s.rps_mean,
                    "logloss": s.logloss_mean,
                    "brier": s.brier_mean,
                }
            )
        per_season = pd.DataFrame(rows).sort_values("season")

    return summary, cal, per_season
