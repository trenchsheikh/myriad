"""Benchmark probability forecasts for 1X2 markets.

- De-vig closing (or opening) odds via proportional normalisation
- Naive baselines: empirical base rates, home-always
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from eval.metrics import outcome_index, summarise


def devig_proportional(
    odds_h: np.ndarray,
    odds_d: np.ndarray,
    odds_a: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert decimal odds to probabilities by proportional normalisation.

    p_i = (1/odds_i) / sum_j(1/odds_j)

    Shin's method is a later refinement (overround attribution differs when
    one outcome is heavily favoured). Tracked as a Day 12+ follow-up.
    """
    inv_h = 1.0 / np.asarray(odds_h, dtype=float)
    inv_d = 1.0 / np.asarray(odds_d, dtype=float)
    inv_a = 1.0 / np.asarray(odds_a, dtype=float)
    total = inv_h + inv_d + inv_a
    return inv_h / total, inv_d / total, inv_a / total


def base_rate_probs(
    home_goals: np.ndarray,
    away_goals: np.ndarray,
) -> tuple[float, float, float]:
    """Empirical P(H), P(D), P(A) from a history sample."""
    y = outcome_index(home_goals, away_goals)
    n = len(y)
    if n == 0:
        raise ValueError("empty history for base rates")
    p_h = float(np.mean(y == 0))
    p_d = float(np.mean(y == 1))
    p_a = float(np.mean(y == 2))
    return p_h, p_d, p_a


def home_always_probs(n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Degenerate 'home team always wins' baseline."""
    ones = np.ones(n, dtype=float)
    zeros = np.zeros(n, dtype=float)
    return ones, zeros, zeros


@dataclass
class BenchmarkResult:
    name: str
    n: int
    rps: float
    logloss: float
    brier: float


def score_odds_benchmark(
    odds_h: np.ndarray,
    odds_d: np.ndarray,
    odds_a: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    name: str = "closing_devig",
) -> BenchmarkResult:
    """De-vig odds and score against results. Drops rows with missing odds."""
    odds_h = np.asarray(odds_h, dtype=float)
    odds_d = np.asarray(odds_d, dtype=float)
    odds_a = np.asarray(odds_a, dtype=float)
    hg = np.asarray(home_goals)
    ag = np.asarray(away_goals)

    ok = np.isfinite(odds_h) & np.isfinite(odds_d) & np.isfinite(odds_a)
    ok &= (odds_h > 1.0) & (odds_d > 1.0) & (odds_a > 1.0)
    if ok.sum() == 0:
        raise ValueError(f"no valid odds rows for benchmark {name}")

    ph, pd_, pa = devig_proportional(odds_h[ok], odds_d[ok], odds_a[ok])
    y = outcome_index(hg[ok], ag[ok])
    s = summarise(ph, pd_, pa, y)
    return BenchmarkResult(
        name=name, n=s.n, rps=s.rps_mean, logloss=s.logloss_mean, brier=s.brier_mean
    )


def score_naive_baselines(
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    history_home_goals: np.ndarray | None = None,
    history_away_goals: np.ndarray | None = None,
) -> list[BenchmarkResult]:
    """Base-rate and home-always baselines.

    If history_* provided, base rates are estimated from history (no leakage
    into the scored sample). Otherwise uses the scored sample itself (only OK
    for descriptive baselines, not honest walk-forward).
    """
    hg = np.asarray(home_goals)
    ag = np.asarray(away_goals)
    y = outcome_index(hg, ag)
    n = len(y)

    if history_home_goals is None:
        p_h, p_d, p_a = base_rate_probs(hg, ag)
        rate_name = "base_rates_insample"
    else:
        p_h, p_d, p_a = base_rate_probs(history_home_goals, history_away_goals)
        rate_name = "base_rates"

    ph = np.full(n, p_h)
    pd_ = np.full(n, p_d)
    pa = np.full(n, p_a)
    s_rate = summarise(ph, pd_, pa, y)

    hh, hd, ha = home_always_probs(n)
    s_home = summarise(hh, hd, ha, y)

    return [
        BenchmarkResult(
            name=rate_name,
            n=s_rate.n,
            rps=s_rate.rps_mean,
            logloss=s_rate.logloss_mean,
            brier=s_rate.brier_mean,
        ),
        BenchmarkResult(
            name="home_always",
            n=s_home.n,
            rps=s_home.rps_mean,
            logloss=s_home.logloss_mean,
            brier=s_home.brier_mean,
        ),
    ]


def attach_devig_columns(
    df: pd.DataFrame,
    odds_h: str = "odds_close_h",
    odds_d: str = "odds_close_d",
    odds_a: str = "odds_close_a",
    prefix: str = "close",
) -> pd.DataFrame:
    """Add de-vigged probability columns; leaves NaN where odds missing."""
    out = df.copy()
    h, d, a = out[odds_h], out[odds_d], out[odds_a]
    ok = h.notna() & d.notna() & a.notna() & (h > 1) & (d > 1) & (a > 1)
    ph = np.full(len(out), np.nan)
    pd_ = np.full(len(out), np.nan)
    pa = np.full(len(out), np.nan)
    if ok.any():
        ph[ok.to_numpy()], pd_[ok.to_numpy()], pa[ok.to_numpy()] = devig_proportional(
            h[ok].to_numpy(), d[ok].to_numpy(), a[ok].to_numpy()
        )
    out[f"p_{prefix}_home"] = ph
    out[f"p_{prefix}_draw"] = pd_
    out[f"p_{prefix}_away"] = pa
    return out
