"""Descriptive event-study outcomes for detected relative-return shocks.

Peer portfolios are frozen at their event-date membership and weights.  The
module measures post-event paths; it deliberately performs no inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype

from price_diffusion.validation import (
    DataValidationError,
    ValidationIssue,
    validate_event_outcomes,
    validate_event_panel,
)


EVENT_OUTCOME_COLUMNS = (
    "event_id", "event_date", "security_id", "direction", "peer_definition",
    "subsector", "horizon", "return_specification", "initiator_car", "peer_car",
    "peer_catchup", "initiator_reversal", "convergence", "initial_relative_shock",
    "relative_volatility", "simultaneous_event_group", "earnings_flag",
    "overlapping_post_event_window", "valid_horizon", "missing_reason",
)


@dataclass(frozen=True)
class EventStudyConfig:
    """Pre-specified event windows and reporting horizons."""

    primary_horizons: tuple[int, ...] = (1, 5)
    descriptive_horizons: tuple[int, ...] = (3, 10)
    pre_event_days: int = 5
    post_event_days: int = 10

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> EventStudyConfig:
        values = config.get("event_study", config)
        window = values.get("event_window", {})
        result = cls(
            primary_horizons=tuple(int(value) for value in values["primary_horizons"]),
            descriptive_horizons=tuple(
                int(value) for value in values.get("descriptive_horizons", ())
            ),
            pre_event_days=int(window.get("pre_event_days", 5)),
            post_event_days=int(window.get("post_event_days", 10)),
        )
        result.validate()
        return result

    @property
    def horizons(self) -> tuple[int, ...]:
        """All configured horizons, deduplicated and sorted."""
        return tuple(sorted(set(self.primary_horizons + self.descriptive_horizons)))

    def validate(self) -> None:
        if not self.primary_horizons:
            raise ValueError("at least one primary event-study horizon is required")
        if any(value <= 0 for value in self.horizons):
            raise ValueError("event-study horizons must be positive")
        if self.pre_event_days < 0 or self.post_event_days < 0:
            raise ValueError("event-window lengths must be non-negative")
        if self.horizons and max(self.horizons) > self.post_event_days:
            raise ValueError("post_event_days must cover every configured horizon")


@dataclass(frozen=True)
class EventStudyResult:
    """Long event paths, horizon outcomes, and sample diagnostics."""

    event_panel: pd.DataFrame
    outcomes: pd.DataFrame
    diagnostics: Mapping[str, pd.DataFrame]


def _fail(dataset: str, code: str, message: str) -> None:
    raise DataValidationError([ValidationIssue(dataset, code, message)])


def _require_columns(frame: pd.DataFrame, required: set[str], dataset: str) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        _fail(dataset, "missing_columns", f"required columns are missing: {', '.join(missing)}")


def _validate_inputs(
    events: pd.DataFrame,
    returns: pd.DataFrame,
    peer_membership: pd.DataFrame,
    return_column: str,
) -> None:
    _require_columns(
        events,
        {
            "event_id",
            "date",
            "security_id",
            "direction",
            "peer_definition",
            "subsector",
            "relative_return",
            "relative_volatility",
            "simultaneous_event_group",
        },
        "events",
    )
    _require_columns(returns, {"date", "security_id", return_column}, "event_returns")
    _require_columns(
        peer_membership,
        {"date", "security_id", "peer_id", "peer_definition", "weight"},
        "peer_membership",
    )
    for name, frame in (
        ("events", events),
        ("event_returns", returns),
        ("peer_membership", peer_membership),
    ):
        if not is_datetime64_any_dtype(frame["date"]):
            _fail(name, "invalid_type", "date must be a pandas datetime column")
        if isinstance(frame["date"].dtype, pd.DatetimeTZDtype):
            _fail(name, "invalid_type", "date must be timezone-naive")
    if events["event_id"].duplicated().any():
        _fail("events", "duplicate_primary_key", "event_id values must be unique")
    if returns.duplicated(["date", "security_id"]).any():
        _fail("event_returns", "duplicate_primary_key", "date/security rows must be unique")
    if not is_numeric_dtype(returns[return_column]):
        _fail("event_returns", "invalid_type", f"{return_column} must be numeric")
    finite = returns[return_column].dropna().to_numpy(dtype=float)
    if not np.isfinite(finite).all():
        _fail("event_returns", "non_finite", f"{return_column} contains infinite values")
    if not is_numeric_dtype(peer_membership["weight"]):
        _fail("peer_membership", "invalid_type", "weight must be numeric")
    weights = peer_membership["weight"].to_numpy(dtype=float)
    if not np.isfinite(weights).all():
        _fail("peer_membership", "non_finite", "weights must be finite")
    if peer_membership["weight"].lt(0).any():
        _fail("peer_membership", "negative_weight", "weights must be non-negative")
    if peer_membership["security_id"].eq(peer_membership["peer_id"]).any():
        _fail("peer_membership", "self_peer", "peer portfolios must be leave-one-out")
    peer_key = ["date", "security_id", "peer_id", "peer_definition"]
    if peer_membership.duplicated(peer_key).any():
        _fail("peer_membership", "duplicate_primary_key", "peer relationships must be unique")
    group_key = ["date", "security_id", "peer_definition"]
    sums = peer_membership.groupby(group_key, dropna=False)["weight"].sum()
    if not np.allclose(sums.to_numpy(dtype=float), 1.0, atol=1e-8, rtol=0):
        _fail("peer_membership", "invalid_weight_sum", "peer weights must sum to one")
    valid_directions = events["direction"].isin(["positive", "negative"])
    if not valid_directions.all():
        _fail("events", "invalid_direction", "direction must be positive or negative")


def _direction_sign(value: object) -> int:
    return 1 if value == "positive" else -1


def _relative_dates(
    calendar: pd.DatetimeIndex,
    event_date: pd.Timestamp,
    pre_days: int,
    post_days: int,
) -> dict[int, pd.Timestamp | pd.NaT]:
    location = calendar.get_indexer([event_date])[0]
    if location < 0:
        return {day: pd.NaT for day in range(-pre_days, post_days + 1)}
    result: dict[int, pd.Timestamp | pd.NaT] = {}
    for relative_day in range(-pre_days, post_days + 1):
        position = location + relative_day
        result[relative_day] = calendar[position] if 0 <= position < len(calendar) else pd.NaT
    return result


def _frozen_peer_return(
    date: pd.Timestamp | pd.NaT,
    peers: pd.DataFrame,
    return_lookup: pd.Series,
) -> float:
    if pd.isna(date) or peers.empty:
        return np.nan
    observations = [return_lookup.get((date, peer_id), np.nan) for peer_id in peers["peer_id"]]
    values = np.asarray(observations, dtype=float)
    if np.isnan(values).any():
        return np.nan
    return float(np.dot(values, peers["weight"].to_numpy(dtype=float)))


def _overlap_flags(
    events: pd.DataFrame,
    event_panel: pd.DataFrame,
    post_days: int,
) -> dict[str, bool]:
    intervals: list[tuple[str, pd.Timestamp, pd.Timestamp]] = []
    for event_id, group in event_panel.groupby("event_id", sort=False):
        post = group.loc[group["relative_day"].between(1, post_days), "calendar_date"].dropna()
        if not post.empty:
            intervals.append((event_id, post.min(), post.max()))
    flags = {event_id: False for event_id in events["event_id"]}
    for position, (left_id, left_start, left_end) in enumerate(intervals):
        for right_id, right_start, right_end in intervals[position + 1 :]:
            if left_start <= right_end and right_start <= left_end:
                flags[left_id] = True
                flags[right_id] = True
    return flags


def build_event_panel(
    events: pd.DataFrame,
    returns: pd.DataFrame,
    peer_membership: pd.DataFrame,
    config: Mapping[str, Any] | EventStudyConfig,
    *,
    return_column: str,
    return_specification: str,
) -> pd.DataFrame:
    """Build a long event-time panel using event-date frozen peer portfolios."""
    parameters = config if isinstance(config, EventStudyConfig) else EventStudyConfig.from_mapping(config)
    parameters.validate()
    _validate_inputs(events, returns, peer_membership, return_column)
    if not return_specification.strip():
        raise ValueError("return_specification must be non-blank")

    calendar = pd.DatetimeIndex(sorted(returns["date"].dropna().unique()))
    return_lookup = returns.set_index(["date", "security_id"])[return_column]
    event_keys = events[["date", "security_id", "peer_definition"]].drop_duplicates()
    relevant_membership = peer_membership.merge(
        event_keys,
        on=["date", "security_id", "peer_definition"],
        how="inner",
        validate="many_to_one",
    )
    frozen_lookup = {
        key: group.sort_values("peer_id", kind="stable")
        for key, group in relevant_membership.groupby(
            ["date", "security_id", "peer_definition"], sort=False
        )
    }
    rows: list[dict[str, object]] = []
    for event in events.sort_values(["date", "event_id"], kind="stable").itertuples(index=False):
        sign = _direction_sign(event.direction)
        frozen = frozen_lookup.get(
            (event.date, event.security_id, event.peer_definition),
            peer_membership.iloc[0:0],
        )
        weights_valid = not frozen.empty and np.isclose(frozen["weight"].sum(), 1.0, atol=1e-8)
        if not weights_valid:
            frozen = frozen.iloc[0:0]
        relative_dates = _relative_dates(
            calendar, event.date, parameters.pre_event_days, parameters.post_event_days
        )
        for relative_day, calendar_date in relative_dates.items():
            initiator = (
                return_lookup.get((calendar_date, event.security_id), np.nan)
                if pd.notna(calendar_date)
                else np.nan
            )
            peer = _frozen_peer_return(calendar_date, frozen, return_lookup)
            rows.append(
                {
                    "event_id": event.event_id,
                    "event_date": event.date,
                    "security_id": event.security_id,
                    "relative_day": relative_day,
                    "calendar_date": calendar_date,
                    "direction": event.direction,
                    "peer_definition": event.peer_definition,
                    "return_specification": return_specification,
                    "initiator_return": initiator,
                    "peer_return": peer,
                    "signed_initiator_return": sign * initiator,
                    "signed_peer_return": sign * peer,
                    "valid_observation": bool(pd.notna(initiator) and pd.notna(peer)),
                    "event_date_peer_membership_valid": weights_valid,
                }
            )
    columns = [
        "event_id", "event_date", "security_id", "relative_day", "calendar_date",
        "direction", "peer_definition", "return_specification", "initiator_return",
        "peer_return", "signed_initiator_return", "signed_peer_return", "valid_observation",
        "event_date_peer_membership_valid",
    ]
    output = pd.DataFrame(rows, columns=columns)
    if not output.empty:
        validate_event_panel(output)
    return output


def _missing_reason(window: pd.DataFrame, horizon: int) -> str | None:
    reasons: list[str] = []
    if len(window) != horizon or window["calendar_date"].isna().any():
        reasons.append("end_of_sample")
    if window["initiator_return"].isna().any():
        reasons.append("missing_initiator_observation")
    if not window.empty and not window["event_date_peer_membership_valid"].all():
        reasons.append("missing_event_date_peer_membership")
    elif window["peer_return"].isna().any():
        reasons.append("missing_peer_observation")
    return ";".join(dict.fromkeys(reasons)) or None


def calculate_event_outcomes(
    events: pd.DataFrame,
    event_panel: pd.DataFrame,
    config: Mapping[str, Any] | EventStudyConfig,
) -> pd.DataFrame:
    """Calculate t+1 through t+h CARs and sign-normalized components."""
    parameters = config if isinstance(config, EventStudyConfig) else EventStudyConfig.from_mapping(config)
    parameters.validate()
    if event_panel.empty:
        return pd.DataFrame(columns=EVENT_OUTCOME_COLUMNS)
    overlap = _overlap_flags(events, event_panel, parameters.post_event_days)
    metadata = events.set_index("event_id")
    rows: list[dict[str, object]] = []
    for event_id, group in event_panel.groupby("event_id", sort=False):
        event = metadata.loc[event_id]
        sign = _direction_sign(event["direction"])
        for horizon in parameters.horizons:
            window = group.loc[group["relative_day"].between(1, horizon)].sort_values("relative_day")
            reason = _missing_reason(window, horizon)
            valid = reason is None and bool(window["valid_observation"].all())
            initiator_car = float(window["initiator_return"].sum()) if valid else np.nan
            peer_car = float(window["peer_return"].sum()) if valid else np.nan
            peer_catchup = sign * peer_car if valid else np.nan
            initiator_reversal = -sign * initiator_car if valid else np.nan
            convergence = peer_catchup + initiator_reversal if valid else np.nan
            rows.append(
                {
                    "event_id": event_id,
                    "event_date": event["date"],
                    "security_id": event["security_id"],
                    "direction": event["direction"],
                    "peer_definition": event["peer_definition"],
                    "subsector": event["subsector"],
                    "horizon": horizon,
                    "return_specification": group["return_specification"].iloc[0],
                    "initiator_car": initiator_car,
                    "peer_car": peer_car,
                    "peer_catchup": peer_catchup,
                    "initiator_reversal": initiator_reversal,
                    "convergence": convergence,
                    "initial_relative_shock": event["relative_return"],
                    "relative_volatility": event["relative_volatility"],
                    "simultaneous_event_group": event["simultaneous_event_group"],
                    "earnings_flag": event.get("earnings_flag", pd.NA),
                    "overlapping_post_event_window": overlap.get(event_id, False),
                    "valid_horizon": valid,
                    "missing_reason": reason,
                }
            )
    output = pd.DataFrame(rows, columns=EVENT_OUTCOME_COLUMNS).sort_values(
        ["event_date", "event_id", "horizon"], ignore_index=True
    )
    output["earnings_flag"] = pd.array(output["earnings_flag"], dtype="boolean")
    validate_event_outcomes(output)
    return output


def descriptive_summary(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Summarize valid outcomes by horizon and direction without inference."""
    valid = outcomes.loc[outcomes["valid_horizon"]].copy()
    columns = [
        "horizon", "direction", "event_count", "mean_convergence", "median_convergence",
        "mean_peer_catchup", "median_peer_catchup", "mean_initiator_reversal",
        "median_initiator_reversal", "proportion_positive_convergence",
    ]
    if valid.empty:
        return pd.DataFrame(columns=columns)
    summaries: list[pd.DataFrame] = []
    for direction, subset in (("all", valid), *valid.groupby("direction", sort=True)):
        summary = subset.groupby("horizon", as_index=False).agg(
            event_count=("event_id", "size"),
            mean_convergence=("convergence", "mean"),
            median_convergence=("convergence", "median"),
            mean_peer_catchup=("peer_catchup", "mean"),
            median_peer_catchup=("peer_catchup", "median"),
            mean_initiator_reversal=("initiator_reversal", "mean"),
            median_initiator_reversal=("initiator_reversal", "median"),
            proportion_positive_convergence=("convergence", lambda values: values.gt(0).mean()),
        )
        summary.insert(1, "direction", direction)
        summaries.append(summary)
    return pd.concat(summaries, ignore_index=True)[columns]


def event_diagnostics(events: pd.DataFrame, outcomes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return auditable event counts and horizon attrition tables."""
    invalid = outcomes.loc[~outcomes["valid_horizon"]].copy()
    if not invalid.empty:
        invalid = invalid.assign(missing_reason=invalid["missing_reason"].str.split(";"))
        invalid = invalid.explode("missing_reason")
    return {
        "total_events": pd.DataFrame({"total_detected_events": [events["event_id"].nunique()]}),
        "valid_by_horizon": outcomes.groupby("horizon", as_index=False)["valid_horizon"].sum().rename(
            columns={"valid_horizon": "valid_events"}
        ),
        "invalid_by_reason": invalid.groupby(["horizon", "missing_reason"], as_index=False).size().rename(
            columns={"size": "invalid_events"}
        ),
        "events_by_firm": events.groupby("security_id", as_index=False).size().rename(columns={"size": "event_count"}),
        "events_by_date": events.groupby("date", as_index=False).size().rename(columns={"size": "event_count"}),
        "events_by_subsector": events.groupby("subsector", as_index=False).size().rename(columns={"size": "event_count"}),
        "descriptive_summary": descriptive_summary(outcomes),
    }


def run_event_study(
    events: pd.DataFrame,
    returns: pd.DataFrame,
    peer_membership: pd.DataFrame,
    config: Mapping[str, Any] | EventStudyConfig,
    *,
    return_column: str,
    return_specification: str,
) -> EventStudyResult:
    """Build all Stage 8 descriptive datasets in one call."""
    panel = build_event_panel(
        events, returns, peer_membership, config,
        return_column=return_column, return_specification=return_specification,
    )
    outcomes = calculate_event_outcomes(events, panel, config)
    return EventStudyResult(panel, outcomes, event_diagnostics(events, outcomes))


def plot_event_time_path(event_panel: pd.DataFrame) -> tuple[plt.Figure, plt.Axes]:
    """Plot average sign-normalized cumulative paths over event time."""
    valid = event_panel.loc[event_panel["valid_observation"]].copy()
    valid["initiator_cumulative"] = valid.groupby("event_id")["signed_initiator_return"].cumsum()
    valid["peer_cumulative"] = valid.groupby("event_id")["signed_peer_return"].cumsum()
    valid["relative_convergence"] = valid["peer_cumulative"] - valid["initiator_cumulative"]
    means = valid.groupby("relative_day")[["initiator_cumulative", "peer_cumulative", "relative_convergence"]].mean()
    figure, axis = plt.subplots()
    means.plot(ax=axis)
    axis.axvline(0, color="black", linewidth=0.8)
    axis.set(xlabel="Relative trading day", ylabel="Average cumulative return")
    return figure, axis


def plot_component_comparison(outcomes: pd.DataFrame) -> tuple[plt.Figure, plt.Axes]:
    """Compare average peer catch-up and initiator reversal by horizon."""
    means = outcomes.loc[outcomes["valid_horizon"]].groupby("horizon")[["peer_catchup", "initiator_reversal"]].mean()
    figure, axis = plt.subplots()
    means.plot.bar(ax=axis)
    axis.set(xlabel="Horizon (trading days)", ylabel="Average component")
    return figure, axis
