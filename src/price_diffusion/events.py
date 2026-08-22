"""Point-in-time detection of unusually large peer-relative abnormal returns."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype

from price_diffusion.validation import DataValidationError, ValidationIssue, validate_events

EVENT_COLUMNS = (
    "event_id",
    "date",
    "security_id",
    "direction",
    "relative_return",
    "relative_volatility",
    "threshold_used",
    "peer_definition",
    "subsector",
    "volume",
    "market_cap",
    "simultaneous_event_group",
    "corporate_action_type",
    "earnings_flag",
    "news_identified_flag",
)

KNOWN_CORPORATE_ACTION_TYPES = {
    "none",
    "split",
    "merger",
    "abnormal_price_adjustment",
    "unknown",
}


@dataclass(frozen=True)
class EventDetectionConfig:
    """Pre-specified parameters governing event selection."""

    minimum_relative_move: float
    volatility_window: int
    threshold_multiplier: float
    cooldown_period: int
    minimum_peer_count: int
    minimum_history_requirement: int
    cooldown_scope: str = "firm"
    exclude_corporate_action_types: tuple[str, ...] = (
        "split",
        "merger",
        "abnormal_price_adjustment",
        "unknown",
    )

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> EventDetectionConfig:
        """Build from either the full configuration or event-threshold section."""
        values = config.get("event_thresholds", config)
        required = {
            "minimum_relative_move",
            "volatility_window",
            "threshold_multiplier",
            "cooldown_period",
            "minimum_peer_count",
            "minimum_history_requirement",
        }
        missing = sorted(required.difference(values))
        if missing:
            raise ValueError(f"event configuration is missing: {', '.join(missing)}")
        result = cls(
            minimum_relative_move=float(values["minimum_relative_move"]),
            volatility_window=int(values["volatility_window"]),
            threshold_multiplier=float(values["threshold_multiplier"]),
            cooldown_period=int(values["cooldown_period"]),
            minimum_peer_count=int(values["minimum_peer_count"]),
            minimum_history_requirement=int(values["minimum_history_requirement"]),
            cooldown_scope=str(values.get("cooldown_scope", "firm")),
            exclude_corporate_action_types=tuple(
                values.get("exclude_corporate_action_types", cls.exclude_corporate_action_types)
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.minimum_relative_move < 0 or self.threshold_multiplier < 0:
            raise ValueError("event thresholds must be non-negative")
        if self.volatility_window < 2:
            raise ValueError("volatility_window must be at least 2")
        if not 2 <= self.minimum_history_requirement <= self.volatility_window:
            raise ValueError(
                "minimum_history_requirement must be between 2 and volatility_window"
            )
        if self.cooldown_period < 0 or self.minimum_peer_count < 1:
            raise ValueError("cooldown_period must be non-negative and minimum_peer_count positive")
        if self.cooldown_scope not in {"none", "firm", "peer_group", "both"}:
            raise ValueError("cooldown_scope must be none, firm, peer_group, or both")
        unknown = set(self.exclude_corporate_action_types) - KNOWN_CORPORATE_ACTION_TYPES
        if unknown:
            raise ValueError(f"unknown excluded corporate action types: {sorted(unknown)}")


def _fail(code: str, message: str) -> None:
    raise DataValidationError([ValidationIssue("event_candidates", code, message)])


def _validate_input(frame: pd.DataFrame, relative_return_column: str) -> None:
    required = {
        "date",
        "security_id",
        "peer_definition",
        "peer_group",
        "subsector",
        "peer_count",
        "corporate_action_type",
        relative_return_column,
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        _fail("missing_columns", f"required columns are missing: {', '.join(missing)}")
    if not is_datetime64_any_dtype(frame["date"]):
        _fail("invalid_type", "date must be a pandas datetime column")
    if isinstance(frame["date"].dtype, pd.DatetimeTZDtype):
        _fail("invalid_type", "date must be timezone-naive")
    if not frame["date"].dt.normalize().equals(frame["date"]):
        _fail("invalid_date", "dates must be normalized to midnight")
    key = ["date", "security_id", "peer_definition"]
    if frame.duplicated(key).any():
        _fail("duplicate_primary_key", "date/security/peer-definition rows must be unique")
    if frame[list(required)].isna().any().any():
        _fail("null_values", "required event inputs may not be null")
    for column in (relative_return_column, "peer_count"):
        if not is_numeric_dtype(frame[column]):
            _fail("invalid_type", f"{column} must be numeric")
        if not np.isfinite(frame[column].to_numpy(dtype=float)).all():
            _fail("non_finite", f"{column} must be finite")
    if frame["peer_count"].lt(0).any():
        _fail("negative_peer_count", "peer_count must be non-negative")


def _event_id(row: pd.Series) -> str:
    key = f"{row['date']:%Y-%m-%d}|{row['security_id']}|{row['peer_definition']}"
    return f"evt_{sha256(key.encode()).hexdigest()[:16]}"


def _simultaneous_id(date: pd.Timestamp, peer_definition: str, peer_group: str) -> str:
    key = f"{date:%Y-%m-%d}|{peer_definition}|{peer_group}"
    return f"sim_{sha256(key.encode()).hexdigest()[:16]}"


def _apply_cooldown(candidates: pd.DataFrame, config: EventDetectionConfig) -> pd.DataFrame:
    """Retain all same-day movers, then block later firm/group episodes."""
    if candidates.empty or config.cooldown_scope == "none" or config.cooldown_period == 0:
        return candidates.copy()
    last_firm: dict[str, pd.Timestamp] = {}
    last_group: dict[tuple[str, str], pd.Timestamp] = {}
    accepted: list[int] = []
    firm_enabled = config.cooldown_scope in {"firm", "both"}
    group_enabled = config.cooldown_scope in {"peer_group", "both"}
    for date, same_day in candidates.groupby("date", sort=True):
        day_accept: list[int] = []
        for index, row in same_day.iterrows():
            group_key = (row["peer_definition"], row["peer_group"])
            firm_blocked = firm_enabled and row["security_id"] in last_firm and (
                date - last_firm[row["security_id"]]
            ).days <= config.cooldown_period
            group_blocked = group_enabled and group_key in last_group and (
                date - last_group[group_key]
            ).days <= config.cooldown_period
            if not firm_blocked and not group_blocked:
                day_accept.append(index)
        accepted.extend(day_accept)
        accepted_day = candidates.loc[day_accept]
        if firm_enabled:
            last_firm.update({security_id: date for security_id in accepted_day["security_id"]})
        if group_enabled:
            last_group.update(
                {
                    (row["peer_definition"], row["peer_group"]): date
                    for _, row in accepted_day.iterrows()
                }
            )
    return candidates.loc[accepted].copy()


def detect_events(
    relative_returns: pd.DataFrame,
    config: Mapping[str, Any] | EventDetectionConfig,
    *,
    relative_return_column: str = "relative_abnormal_return",
) -> pd.DataFrame:
    """Detect events using strictly trailing volatility and configured filters.

    The input must already contain the company-minus-peer abnormal return. Rows
    below peer/history requirements and configured corporate-action classes are
    ineligible. No post-event observations are read or produced.
    """
    parameters = (
        config if isinstance(config, EventDetectionConfig) else EventDetectionConfig.from_mapping(config)
    )
    parameters.validate()
    _validate_input(relative_returns, relative_return_column)

    work = relative_returns.copy()
    for column, default in (
        ("volume", np.nan),
        ("market_cap", np.nan),
        ("earnings_flag", False),
        ("news_identified_flag", False),
    ):
        if column not in work:
            work[column] = default
    invalid_actions = set(work["corporate_action_type"].dropna()) - KNOWN_CORPORATE_ACTION_TYPES
    if invalid_actions or work["corporate_action_type"].isna().any():
        _fail("invalid_corporate_action", "corporate_action_type contains null or unknown labels")

    group_keys = ["security_id", "peer_definition"]
    work = work.sort_values([*group_keys, "date"], kind="stable").reset_index(drop=True)
    valid_history = (
        work["peer_count"].ge(parameters.minimum_peer_count)
        & ~work["corporate_action_type"].isin(parameters.exclude_corporate_action_types)
    )
    work["_volatility_input"] = work[relative_return_column].where(valid_history)
    trailing = work.groupby(group_keys, sort=False)["_volatility_input"].transform(
        lambda values: values.shift(1).rolling(
            window=parameters.volatility_window,
            min_periods=parameters.minimum_history_requirement,
        ).std(ddof=1)
    )
    work["relative_volatility"] = trailing
    work["threshold_used"] = np.maximum(
        parameters.minimum_relative_move,
        parameters.threshold_multiplier * work["relative_volatility"],
    )
    eligible = (
        work["relative_volatility"].notna()
        & work["peer_count"].ge(parameters.minimum_peer_count)
        & ~work["corporate_action_type"].isin(parameters.exclude_corporate_action_types)
    )
    candidates = work.loc[
        eligible & work[relative_return_column].abs().gt(work["threshold_used"])
    ].copy()
    candidates = candidates.sort_values(
        ["date", "security_id", "peer_definition"], kind="stable"
    )
    events = _apply_cooldown(candidates, parameters)
    events["direction"] = np.where(events[relative_return_column].gt(0), "positive", "negative")
    events["event_id"] = pd.Series(
        (_event_id(row) for _, row in events.iterrows()),
        index=events.index,
        dtype="object",
    )
    events["simultaneous_event_group"] = pd.Series(pd.NA, index=events.index, dtype="object")
    simultaneous_counts = events.groupby(
        ["date", "peer_definition", "peer_group"]
    )["security_id"].transform("nunique")
    simultaneous = simultaneous_counts.ge(2)
    simultaneous_values = [
        _simultaneous_id(row["date"], row["peer_definition"], row["peer_group"])
        for _, row in events.loc[simultaneous].iterrows()
    ]
    events.loc[simultaneous, "simultaneous_event_group"] = simultaneous_values
    events = events.rename(columns={relative_return_column: "relative_return"})
    output = events[list(EVENT_COLUMNS)].sort_values(
        ["date", "security_id", "peer_definition"], ignore_index=True
    )
    validate_events(output)
    return output
