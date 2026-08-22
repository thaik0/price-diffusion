"""Point-in-time construction of the semiconductor equity universe."""

import math
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from price_diffusion.validation import (
    validate_daily_panel,
    validate_security_master,
    validate_semiconductor_classification,
    validate_universe_membership,
)

UNIVERSE_OUTPUT_COLUMNS = (
    "date",
    "security_id",
    "eligible",
    "exclusion_reason",
)


@dataclass(frozen=True)
class UniverseParameters:
    """Version-controlled eligibility parameters for one universe run."""

    min_history_days: int
    min_price: float
    min_average_dollar_volume: float
    average_dollar_volume_window_days: int
    us_exchanges: tuple[str, ...]
    eligible_security_types: tuple[str, ...]
    classification_as_of_date: pd.Timestamp
    allow_classification_before_as_of: bool = False

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "UniverseParameters":
        """Parse either a full research config or its ``universe`` section."""
        section = config.get("universe", config)
        if not isinstance(section, Mapping):
            raise ValueError("universe configuration must be a mapping")

        required = {
            "min_history_days",
            "min_price",
            "min_average_dollar_volume",
            "average_dollar_volume_window_days",
            "us_exchanges",
            "eligible_security_types",
            "classification_as_of_date",
        }
        missing = sorted(required.difference(section))
        if missing:
            raise ValueError(
                "universe configuration is missing: " + ", ".join(missing)
            )

        min_history_days = section["min_history_days"]
        liquidity_window = section["average_dollar_volume_window_days"]
        if isinstance(min_history_days, bool) or not isinstance(min_history_days, int):
            raise ValueError("min_history_days must be a positive integer")
        if isinstance(liquidity_window, bool) or not isinstance(liquidity_window, int):
            raise ValueError(
                "average_dollar_volume_window_days must be a positive integer"
            )
        if min_history_days <= 0 or liquidity_window <= 0:
            raise ValueError("history and liquidity-window days must be positive")

        min_price = _nonnegative_number(section["min_price"], "min_price")
        min_adv = _nonnegative_number(
            section["min_average_dollar_volume"],
            "min_average_dollar_volume",
        )
        exchanges = _nonempty_strings(section["us_exchanges"], "us_exchanges")
        security_types = _nonempty_strings(
            section["eligible_security_types"], "eligible_security_types"
        )
        allow_historical = section.get("allow_classification_before_as_of", False)
        if not isinstance(allow_historical, bool):
            raise ValueError("allow_classification_before_as_of must be boolean")

        try:
            as_of = pd.Timestamp(section["classification_as_of_date"])
        except (TypeError, ValueError) as error:
            raise ValueError("classification_as_of_date must be a date") from error
        if as_of.tz is not None or as_of != as_of.normalize():
            raise ValueError(
                "classification_as_of_date must be timezone-naive and date-only"
            )

        return cls(
            min_history_days=min_history_days,
            min_price=min_price,
            min_average_dollar_volume=min_adv,
            average_dollar_volume_window_days=liquidity_window,
            us_exchanges=exchanges,
            eligible_security_types=security_types,
            classification_as_of_date=as_of,
            allow_classification_before_as_of=allow_historical,
        )


def _nonnegative_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a non-negative number")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{name} must be a non-negative number")
    return numeric


def _nonempty_strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{name} must be a non-empty list of strings")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{name} must contain non-blank strings")
    return tuple(item.strip() for item in value)


def _market_features(
    daily_panel: pd.DataFrame, parameters: UniverseParameters
) -> pd.DataFrame:
    ordered = daily_panel.sort_values(["security_id", "date"], kind="stable").copy()
    ordered["history_days"] = ordered.groupby("security_id").cumcount().add(1)
    ordered["dollar_volume"] = ordered["close"] * ordered["volume"]
    ordered["average_dollar_volume"] = (
        ordered.groupby("security_id", sort=False)["dollar_volume"]
        .rolling(
            window=parameters.average_dollar_volume_window_days,
            min_periods=parameters.average_dollar_volume_window_days,
        )
        .mean()
        .reset_index(level=0, drop=True)
    )
    return ordered[
        [
            "date",
            "security_id",
            "close",
            "history_days",
            "average_dollar_volume",
        ]
    ]


def build_universe_membership(
    security_master: pd.DataFrame,
    daily_panel: pd.DataFrame,
    semiconductor_classification: pd.DataFrame,
    parameters: UniverseParameters | Mapping[str, Any],
) -> pd.DataFrame:
    """Evaluate every master security on every observed market date.

    All rolling measures end on the membership date. The full date/security
    grid makes missing observations explicit rather than silently removing a
    security from the candidate set.
    """
    if isinstance(parameters, Mapping):
        parameters = UniverseParameters.from_mapping(parameters)
    if not isinstance(parameters, UniverseParameters):
        raise TypeError("parameters must be UniverseParameters or a mapping")

    validate_security_master(security_master)
    validate_daily_panel(daily_panel, security_master)
    validate_semiconductor_classification(
        semiconductor_classification, security_master
    )

    dates = pd.Index(daily_panel["date"].drop_duplicates().sort_values(), name="date")
    security_ids = pd.Index(security_master["security_id"], name="security_id")
    grid = pd.MultiIndex.from_product([dates, security_ids]).to_frame(index=False)
    if grid.empty:
        empty = pd.DataFrame(
            {
                "date": pd.Series(dtype="datetime64[ns]"),
                "security_id": pd.Series(dtype="object"),
                "eligible": pd.Series(dtype="bool"),
                "exclusion_reason": pd.Series(dtype="object"),
            }
        )
        validate_universe_membership(empty, security_master)
        return empty[list(UNIVERSE_OUTPUT_COLUMNS)]

    master_fields = security_master[["security_id", "exchange", "security_type"]]
    classified = semiconductor_classification[["security_id"]].assign(
        is_semiconductor=True
    )
    evaluated = (
        grid.merge(master_fields, on="security_id", how="left", validate="many_to_one")
        .merge(classified, on="security_id", how="left", validate="many_to_one")
        .merge(
            _market_features(daily_panel, parameters),
            on=["date", "security_id"],
            how="left",
            validate="one_to_one",
        )
    )
    evaluated["is_semiconductor"] = (
        evaluated["is_semiconductor"].fillna(False).astype(bool)
    )

    reason_columns: list[tuple[str, pd.Series]] = [
        ("missing_semiconductor_classification", ~evaluated["is_semiconductor"]),
        ("non_us_listing", ~evaluated["exchange"].isin(parameters.us_exchanges)),
        (
            "ineligible_security_type",
            ~evaluated["security_type"].isin(parameters.eligible_security_types),
        ),
    ]
    if not parameters.allow_classification_before_as_of:
        reason_columns.append(
            (
                "classification_not_available_as_of_date",
                evaluated["is_semiconductor"]
                & evaluated["date"].lt(parameters.classification_as_of_date),
            )
        )

    has_market_data = evaluated["close"].notna()
    reason_columns.extend(
        [
            ("no_market_data", ~has_market_data),
            (
                "insufficient_history",
                has_market_data
                & evaluated["history_days"].lt(parameters.min_history_days),
            ),
            (
                "below_minimum_price",
                has_market_data & evaluated["close"].lt(parameters.min_price),
            ),
            (
                "insufficient_liquidity_history",
                has_market_data & evaluated["average_dollar_volume"].isna(),
            ),
            (
                "below_minimum_liquidity",
                has_market_data
                & evaluated["average_dollar_volume"].notna()
                & evaluated["average_dollar_volume"].lt(
                    parameters.min_average_dollar_volume
                ),
            ),
        ]
    )

    reasons = [[] for _ in range(len(evaluated))]
    for label, mask in reason_columns:
        for position in mask.to_numpy().nonzero()[0]:
            reasons[position].append(label)

    output = evaluated[["date", "security_id"]].copy()
    output["eligible"] = [not row_reasons for row_reasons in reasons]
    output["exclusion_reason"] = [
        ";".join(row_reasons) if row_reasons else None for row_reasons in reasons
    ]
    output = output.sort_values(["date", "security_id"], ignore_index=True)
    output = output[list(UNIVERSE_OUTPUT_COLUMNS)]
    validate_universe_membership(output, security_master)
    return output
