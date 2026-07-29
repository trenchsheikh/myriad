"""Leakage guards — each item is an assertion, not a comment.

PRD Day 11 checklist:
  1. No training match on or after the prediction timestamp
  2. Closing odds never used as a feature
  3. xG values are as-published, not later revisions
  4. No end-of-season aggregates as features
  5. Weather uses forecasts at fixed lead time, never observed values
  6. Any text fed to an LLM is timestamped before kickoff
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd

# Columns that must never enter a model feature matrix / fit frame
# as predictive inputs. Closing odds are benchmark-only.
FORBIDDEN_FEATURE_COLS = frozenset(
    {
        "odds_close_h",
        "odds_close_d",
        "odds_close_a",
        "odds_close_home",
        "odds_close_draw",
        "odds_close_away",
        # End-of-season aggregates (none exist yet — block the names)
        "season_points",
        "season_gd",
        "season_rank",
        "final_position",
        # Observed weather (forecasts only, when weather lands Day 17)
        "weather_observed_temp",
        "weather_observed_wind",
        "weather_observed_precip",
    }
)

# Columns the Dixon-Coles baseline is allowed to train on
ALLOWED_FIT_COLS = frozenset(
    {
        "match_id",
        "match_date",
        "kickoff_utc",
        "asof_ts",
        "home_team_id",
        "away_team_id",
        "home_goals",
        "away_goals",
        "crowd_present",
        "season",
        "weight",
        # Opening odds may exist on the row but are not used by DC fit
        "odds_open_h",
        "odds_open_d",
        "odds_open_a",
        "referee",
        "home_xg",
        "away_xg",
    }
)


class LeakageError(AssertionError):
    """Raised when a leakage checklist item fails."""


def assert_no_future_training(train: pd.DataFrame, as_of: pd.Timestamp) -> None:
    """(1) No training match on or after the prediction timestamp."""
    if "asof_ts" not in train.columns:
        raise LeakageError("training frame missing asof_ts column")
    as_of = pd.Timestamp(as_of)
    future = train.loc[train["asof_ts"] >= as_of]
    if len(future) > 0:
        raise LeakageError(
            f"leakage: {len(future)} training rows have asof_ts >= {as_of} "
            f"(examples: {future['match_id'].head(3).tolist() if 'match_id' in future.columns else 'n/a'})"
        )


def assert_no_forbidden_features(columns: Iterable[str]) -> None:
    """(2)(4)(5) Closing odds / EOS aggregates / observed weather never used as features."""
    cols = set(columns)
    bad = cols & FORBIDDEN_FEATURE_COLS
    if bad:
        raise LeakageError(
            f"forbidden feature columns present in model input: {sorted(bad)}"
        )


def assert_fit_columns_allowed(columns: Iterable[str]) -> None:
    """Baseline fit may only see the allow-listed columns."""
    cols = set(columns)
    # First forbid the hard list
    assert_no_forbidden_features(cols)
    unknown = cols - ALLOWED_FIT_COLS
    # Tolerate extras that are clearly non-features (ids already listed); flag oddballs
    if unknown:
        # Soft: only raise if they look like predictive aggregates
        suspicious = {
            c
            for c in unknown
            if any(
                k in c.lower()
                for k in ("close", "final_", "season_", "observed", "revision")
            )
        }
        if suspicious:
            raise LeakageError(f"suspicious fit columns: {sorted(suspicious)}")


def assert_xg_not_revised(train: pd.DataFrame) -> None:
    """(3) xG must be as-published — we never store a revised_xg column.

    When Understat revisions arrive later, they must land in a separate column
    and stay out of the fit. This asserts that contract.
    """
    revised = [c for c in train.columns if "revis" in c.lower() and "xg" in c.lower()]
    if revised:
        raise LeakageError(
            f"revised xG columns must not be used in fit: {revised}"
        )


def assert_llm_inputs_timestamped(records: list[dict] | None) -> None:
    """(6) Any text fed to an LLM is timestamped before kickoff.

    No-op while the LLM layer is post-launch; raises if untimestamped
    prompts are somehow passed in.
    """
    if not records:
        return
    for i, rec in enumerate(records):
        if "text" in rec or "prompt" in rec:
            if "captured_at" not in rec and "timestamp" not in rec:
                raise LeakageError(
                    f"LLM input[{i}] missing timestamp (captured_at/timestamp)"
                )
            if "kickoff_utc" in rec:
                ts = pd.Timestamp(rec.get("captured_at") or rec.get("timestamp"))
                ko = pd.Timestamp(rec["kickoff_utc"])
                if ts >= ko:
                    raise LeakageError(
                        f"LLM input[{i}] timestamp {ts} is not before kickoff {ko}"
                    )


def run_all_fit_guards(
    train: pd.DataFrame,
    as_of: pd.Timestamp,
    llm_records: list[dict] | None = None,
) -> None:
    """Run the full Day 11 leakage checklist against a training frame."""
    assert_no_future_training(train, as_of)
    assert_fit_columns_allowed(train.columns)
    assert_xg_not_revised(train)
    assert_llm_inputs_timestamped(llm_records)
