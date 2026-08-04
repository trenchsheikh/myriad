"""Dixon-Coles bivariate Poisson model for football scores.

Parameters
----------
α_i  : attack strength for team i
β_i  : defence strength for team i (higher = weaker defence; goals conceded rate)
γ    : home advantage multiplier (crowd present)
γ_e  : home advantage when stadium empty (COVID)
τ    : low-score dependence (Dixon-Coles correction)
ξ    : time-decay rate; weight = exp(-ξ · days_ago)

Rates
-----
λ_home = exp(α_home + β_away + γ_*)
λ_away = exp(α_away + β_home)

Identifiability: sum(α) = 0 enforced by reconstructing the last attack param.

Design note — why this shape of model
-------------------------------------
Inspired by the framing in DeepMind's TacticAI (Wang et al., Nature
Communications 2024): the model's structure should encode something true about
football, not just be a flexible function fit to the data. TacticAI does this
with group-equivariant GNNs, because a corner kick is invariant to reflection
and to player relabelling. Here the same instinct produces a much smaller
model: goals are low-count (Poisson), low scorelines are correlated in a way
independent Poissons get wrong (τ), home advantage is real and changed when
stadiums emptied (γ / γ_e), and team strength drifts (ξ).

That is ~2n+3 parameters. It is the baseline any learned representation has to
beat on held-out seasons before it earns its complexity — see
docs/feature_log.md for the decision rule.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

log = logging.getLogger("dixon_coles")

# ~6-month half-life: ξ = ln(2) / 182.5
DEFAULT_HALF_LIFE_DAYS = 182.5
DEFAULT_XI = np.log(2) / DEFAULT_HALF_LIFE_DAYS

# Premier League COVID empty-stadium window (restart → limited fans return)
EMPTY_STADIUM_START = date(2020, 6, 17)
EMPTY_STADIUM_END = date(2021, 5, 16)


def crowd_present_for_date(match_date: date | datetime | pd.Timestamp) -> bool:
    d = pd.Timestamp(match_date).date()
    return not (EMPTY_STADIUM_START <= d <= EMPTY_STADIUM_END)


def dixon_coles_tau(home_goals: int, away_goals: int, lam_h: float, lam_a: float, rho: float) -> float:
    """Multiplicative low-score correction τ(i,j)."""
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lam_h * lam_a * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lam_h * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lam_a * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def match_loglik(
    home_goals: int,
    away_goals: int,
    lam_h: float,
    lam_a: float,
    rho: float,
) -> float:
    """Log probability of an observed scoreline under Dixon-Coles."""
    # Clamp rates away from zero for numerical stability
    lam_h = max(lam_h, 1e-6)
    lam_a = max(lam_a, 1e-6)
    tau = dixon_coles_tau(home_goals, away_goals, lam_h, lam_a, rho)
    # tau can go non-positive for extreme rho; soft-floor
    tau = max(tau, 1e-12)
    return (
        np.log(tau)
        + poisson.logpmf(home_goals, lam_h)
        + poisson.logpmf(away_goals, lam_a)
    )


@dataclass
class DixonColesResult:
    teams: list[str]
    attack: dict[str, float]
    defence: dict[str, float]
    home_adv: float
    home_adv_empty: float
    rho: float
    xi: float
    nll: float
    n_matches: int
    success: bool
    message: str


class DixonColes:
    def __init__(self, xi: float = DEFAULT_XI) -> None:
        self.xi = float(xi)
        self.result_: DixonColesResult | None = None
        self._last_theta: np.ndarray | None = None
        self._last_teams: list[str] | None = None

    def _prepare(self, matches: pd.DataFrame, as_of: pd.Timestamp | None) -> pd.DataFrame:
        df = matches.copy()
        required = {
            "match_date",
            "home_team_id",
            "away_team_id",
            "home_goals",
            "away_goals",
        }
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"matches missing columns: {sorted(missing)}")

        df["match_date"] = pd.to_datetime(df["match_date"])
        df = df.dropna(subset=["home_goals", "away_goals", "home_team_id", "away_team_id"])
        df["home_goals"] = df["home_goals"].astype(int)
        df["away_goals"] = df["away_goals"].astype(int)

        if "crowd_present" not in df.columns:
            df["crowd_present"] = df["match_date"].map(crowd_present_for_date)
        else:
            df["crowd_present"] = df["crowd_present"].fillna(
                df["match_date"].map(crowd_present_for_date)
            ).astype(bool)

        if as_of is not None:
            as_of = pd.Timestamp(as_of)
            # Leakage guard: nothing on or after as_of
            if (df["match_date"] >= as_of).any():
                future = df.loc[df["match_date"] >= as_of]
                raise AssertionError(
                    f"leakage: {len(future)} training rows have match_date >= {as_of.date()}"
                )
            df = df.loc[df["match_date"] < as_of]

        if df.empty:
            raise ValueError("no matches available for fit")

        ref = df["match_date"].max()
        days_ago = (ref - df["match_date"]).dt.days.astype(float)
        df["weight"] = np.exp(-self.xi * days_ago.to_numpy())
        return df.reset_index(drop=True)

    def fit(
        self,
        matches: pd.DataFrame,
        as_of: pd.Timestamp | None = None,
    ) -> DixonColesResult:
        df = self._prepare(matches, as_of)
        teams = sorted(
            set(df["home_team_id"].astype(str)) | set(df["away_team_id"].astype(str))
        )
        team_index = {t: i for i, t in enumerate(teams)}
        n = len(teams)

        home_idx = df["home_team_id"].map(team_index).to_numpy()
        away_idx = df["away_team_id"].map(team_index).to_numpy()
        hg = df["home_goals"].to_numpy()
        ag = df["away_goals"].to_numpy()
        crowd = df["crowd_present"].to_numpy()
        weights = df["weight"].to_numpy()

        # params: attack[0..n-2], defence[0..n-1], log_gamma, log_gamma_empty, rho
        # attack[n-1] reconstructed so sum(attack)=0
        n_att_free = n - 1
        n_def = n

        def unpack(theta: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float, float]:
            att_free = theta[:n_att_free]
            defence = theta[n_att_free : n_att_free + n_def]
            log_g = theta[n_att_free + n_def]
            log_ge = theta[n_att_free + n_def + 1]
            rho = theta[n_att_free + n_def + 2]
            attack = np.empty(n)
            attack[:-1] = att_free
            attack[-1] = -att_free.sum()
            return attack, defence, np.exp(log_g), np.exp(log_ge), rho

        def nll(theta: np.ndarray) -> float:
            attack, defence, gamma, gamma_e, rho = unpack(theta)
            if abs(rho) > 1.0:
                return 1e9
            ha = np.where(crowd, gamma, gamma_e)
            lam_h = np.exp(attack[home_idx] + defence[away_idx] + np.log(ha))
            lam_a = np.exp(attack[away_idx] + defence[home_idx])
            lam_h = np.maximum(lam_h, 1e-6)
            lam_a = np.maximum(lam_a, 1e-6)

            # Vectorised Dixon-Coles τ
            tau = np.ones(len(df), dtype=float)
            m00 = (hg == 0) & (ag == 0)
            m01 = (hg == 0) & (ag == 1)
            m10 = (hg == 1) & (ag == 0)
            m11 = (hg == 1) & (ag == 1)
            tau[m00] = 1.0 - lam_h[m00] * lam_a[m00] * rho
            tau[m01] = 1.0 + lam_h[m01] * rho
            tau[m10] = 1.0 + lam_a[m10] * rho
            tau[m11] = 1.0 - rho
            tau = np.maximum(tau, 1e-12)

            ll = (
                np.log(tau)
                + poisson.logpmf(hg, lam_h)
                + poisson.logpmf(ag, lam_a)
            )
            return float(-np.dot(weights, ll))

        # Init: attack 0, defence 0, gamma~1.3, gamma_empty~1.05, rho~-0.05
        x0 = np.zeros(n_att_free + n_def + 3)
        x0[n_att_free + n_def] = np.log(1.3)
        x0[n_att_free + n_def + 1] = np.log(1.05)
        x0[n_att_free + n_def + 2] = -0.05

        # Warm-start from previous fit when the team set is identical
        warm = (
            self._last_theta is not None
            and self._last_teams == teams
            and len(self._last_theta) == len(x0)
        )
        if warm:
            x0 = self._last_theta.copy()

        log.debug(
            "fitting Dixon-Coles: teams=%d matches=%d xi=%.5f warm=%s",
            n, len(df), self.xi, warm,
        )
        opt = minimize(
            nll,
            x0,
            method="L-BFGS-B",
            options={
                "maxiter": 120 if warm else 800,
                "ftol": 1e-7 if warm else 1e-9,
            },
        )
        self._last_theta = opt.x.copy()
        self._last_teams = list(teams)

        attack, defence, gamma, gamma_e, rho = unpack(opt.x)
        result = DixonColesResult(
            teams=teams,
            attack={t: float(attack[i]) for i, t in enumerate(teams)},
            defence={t: float(defence[i]) for i, t in enumerate(teams)},
            home_adv=float(gamma),
            home_adv_empty=float(gamma_e),
            rho=float(rho),
            xi=self.xi,
            nll=float(opt.fun),
            n_matches=len(df),
            success=bool(opt.success),
            message=str(opt.message),
        )
        self.result_ = result
        log.debug(
            "fit done: success=%s nll=%.2f gamma=%.3f gamma_empty=%.3f rho=%.4f",
            result.success, result.nll, result.home_adv, result.home_adv_empty, result.rho,
        )
        return result

    def rates(
        self,
        home_team_id: str,
        away_team_id: str,
        crowd_present: bool = True,
    ) -> tuple[float, float]:
        if self.result_ is None:
            raise RuntimeError("call fit() first")
        r = self.result_
        if home_team_id not in r.attack or away_team_id not in r.attack:
            raise KeyError(f"unknown team in fit: {home_team_id!r} / {away_team_id!r}")
        gamma = r.home_adv if crowd_present else r.home_adv_empty
        lam_h = np.exp(r.attack[home_team_id] + r.defence[away_team_id] + np.log(gamma))
        lam_a = np.exp(r.attack[away_team_id] + r.defence[home_team_id])
        return float(lam_h), float(lam_a)
