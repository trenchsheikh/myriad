"""Scoreline probability matrix from Dixon-Coles rates.

Given λ_home, λ_away (and ρ), build an 11×11 Poisson score matrix with the
Dixon-Coles low-score adjustment, then collapse to 1X2 / BTTS / Over 2.5.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import poisson

from models.dixon_coles import dixon_coles_tau

MAX_GOALS = 10  # 0..10 inclusive → 11×11


def score_matrix(
    lam_home: float,
    lam_away: float,
    rho: float = 0.0,
    max_goals: int = MAX_GOALS,
) -> np.ndarray:
    """Return (max_goals+1)² matrix of P(home_goals, away_goals)."""
    goals = np.arange(0, max_goals + 1)
    ph = poisson.pmf(goals, max(lam_home, 1e-9))
    pa = poisson.pmf(goals, max(lam_away, 1e-9))
    mat = np.outer(ph, pa)

    for i in range(min(2, max_goals + 1)):
        for j in range(min(2, max_goals + 1)):
            mat[i, j] *= dixon_coles_tau(i, j, lam_home, lam_away, rho)

    total = mat.sum()
    if total <= 0:
        raise ValueError("score matrix has non-positive mass")
    mat /= total
    return mat


def collapse(mat: np.ndarray) -> dict[str, float]:
    """Collapse score matrix to market probabilities."""
    # mat[i, j] = P(home=i, away=j)
    home = float(np.tril(mat, k=-1).sum())  # i > j
    # Wait: rows=home goals, cols=away goals. Home win when i > j → below diagonal if
    # we use tril with... np.tril is lower triangle i>=j. Home win i>j is strict lower.
    # Actually tril(mat, k=-1) is i > j → home goals > away → home win. Correct.
    draw = float(np.trace(mat))
    away = float(np.triu(mat, k=1).sum())  # i < j

    # BTTS: both > 0
    btts = float(mat[1:, 1:].sum())

    # Over 2.5: home+away >= 3
    idx = np.indices(mat.shape)
    over25 = float(mat[(idx[0] + idx[1]) >= 3].sum())

    probs = {
        "p_home": home,
        "p_draw": draw,
        "p_away": away,
        "p_btts": btts,
        "p_over25": over25,
    }

    s = probs["p_home"] + probs["p_draw"] + probs["p_away"]
    if abs(s - 1.0) > 1e-9:
        raise AssertionError(f"1X2 probabilities sum to {s}, not 1.0")

    return probs


def predict_match(
    lam_home: float,
    lam_away: float,
    rho: float = 0.0,
    max_goals: int = MAX_GOALS,
) -> dict[str, float]:
    mat = score_matrix(lam_home, lam_away, rho=rho, max_goals=max_goals)
    return collapse(mat)
