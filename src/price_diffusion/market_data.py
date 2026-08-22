"""Provider-neutral ingestion and normalization of daily market observations."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype

from price_diffusion.validation import (
    DataValidationError,
    ValidationIssue,
    validate_daily_panel,
    validate_security_master,
)

RAW_VALUE_COLUMNS = ("date", "adjusted_close", "close", "volume")
DAILY_PANEL_COLUMNS = (
    "date",
    "security_id",
    "adjusted_close",
    "close",
    "volume",
    "return",
)


@runtime_checkable
class MarketDataSource(Protocol):
    """A replaceable source of tabular daily market observations."""

    def load(self) -> pd.DataFrame:
        """Load observations without applying research transformations."""


@dataclass(frozen=True)
class CSVMarketDataSource:
    """Load raw observations from CSV, optionally renaming source columns."""

    path: str | Path
    column_map: Mapping[str, str] = field(default_factory=dict)
    read_csv_options: Mapping[str, Any] = field(default_factory=dict)

    def load(self) -> pd.DataFrame:
        frame = pd.read_csv(Path(self.path), **dict(self.read_csv_options))
        return frame.rename(columns=dict(self.column_map))


def _fail(code: str, message: str) -> None:
    raise DataValidationError([ValidationIssue("daily_panel", code, message)])


def load_market_data(source: MarketDataSource) -> pd.DataFrame:
    """Load a defensive copy of source data through the common source interface."""
    if not isinstance(source, MarketDataSource):
        raise TypeError("source must implement load() -> pandas.DataFrame")
    frame = source.load()
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("market data source load() must return a pandas DataFrame")
    return frame.copy(deep=True)


def _normalize_dates(values: pd.Series) -> pd.Series:
    if values.isna().any():
        _fail("null_values", "raw column 'date' contains null values")
    try:
        parsed = pd.to_datetime(values, errors="raise", format="mixed")
    except (TypeError, ValueError, OverflowError) as error:
        _fail("malformed_date", f"raw column 'date' cannot be parsed: {error}")

    if not is_datetime64_any_dtype(parsed.dtype) or isinstance(
        parsed.dtype, pd.DatetimeTZDtype
    ):
        _fail(
            "malformed_date",
            "raw dates must be timezone-naive and parseable",
        )
    return parsed.dt.normalize()


def _normalize_numeric(values: pd.Series, name: str) -> pd.Series:
    if values.isna().any():
        _fail("null_values", f"raw column {name!r} contains null values")
    if is_bool_dtype(values.dtype):
        _fail("invalid_type", f"raw column {name!r} must be numeric, not boolean")
    try:
        numeric = pd.to_numeric(values, errors="raise")
    except (TypeError, ValueError) as error:
        _fail("invalid_type", f"raw column {name!r} must be numeric: {error}")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        _fail("non_finite", f"raw column {name!r} contains infinite values")
    return numeric


def calculate_simple_returns(panel: pd.DataFrame) -> pd.Series:
    """Calculate adjusted-close simple returns by security in panel row order."""
    prior_price = panel.groupby("security_id", sort=False)["adjusted_close"].shift(1)
    returns = panel["adjusted_close"].div(prior_price).sub(1.0)
    return returns.astype(float)


def build_daily_panel(
    raw_market_data: pd.DataFrame,
    security_master: pd.DataFrame,
    *,
    source_identifier_column: str = "ticker",
) -> pd.DataFrame:
    """Normalize raw observations, resolve identifiers, calculate returns, and validate."""
    if not isinstance(raw_market_data, pd.DataFrame):
        raise TypeError("raw_market_data must be a pandas DataFrame")
    validate_security_master(security_master)

    required = set(RAW_VALUE_COLUMNS) | {source_identifier_column}
    missing = sorted(required.difference(raw_market_data.columns))
    if missing:
        _fail("missing_columns", f"raw data is missing: {', '.join(missing)}")
    if source_identifier_column not in security_master.columns:
        _fail(
            "invalid_security_reference",
            f"security_master has no {source_identifier_column!r} column",
        )

    identifiers = raw_market_data[source_identifier_column]
    if identifiers.isna().any():
        _fail(
            "null_values",
            f"raw identifier column {source_identifier_column!r} contains null values",
        )
    if not identifiers.map(lambda value: isinstance(value, str)).all():
        _fail(
            "invalid_type",
            f"raw identifier column {source_identifier_column!r} must contain strings",
        )
    identifiers = identifiers.str.strip()
    if identifiers.eq("").any():
        _fail(
            "blank_string",
            f"raw identifier column {source_identifier_column!r} contains blanks",
        )

    master_identifiers = security_master[source_identifier_column]
    ambiguous = master_identifiers[master_identifiers.duplicated(keep=False)].unique()
    if len(ambiguous):
        values = ", ".join(repr(value) for value in sorted(ambiguous))
        _fail(
            "ambiguous_security_reference",
            f"security_master identifiers are not unique: {values}",
        )

    normalized = pd.DataFrame(
        {
            "date": _normalize_dates(raw_market_data["date"]),
            source_identifier_column: identifiers,
            "adjusted_close": _normalize_numeric(
                raw_market_data["adjusted_close"], "adjusted_close"
            ),
            "close": _normalize_numeric(raw_market_data["close"], "close"),
            "volume": _normalize_numeric(raw_market_data["volume"], "volume"),
        }
    )

    duplicate_mask = normalized.duplicated(
        [source_identifier_column, "date"], keep=False
    )
    if duplicate_mask.any():
        _fail(
            "duplicate_primary_key",
            f"{int(duplicate_mask.sum())} raw rows share a security/date pair",
        )

    identifier_map = security_master.set_index(source_identifier_column)["security_id"]
    normalized["security_id"] = normalized[source_identifier_column].map(identifier_map)
    if normalized["security_id"].isna().any():
        unknown = sorted(
            normalized.loc[
                normalized["security_id"].isna(), source_identifier_column
            ].unique()
        )
        values = ", ".join(repr(value) for value in unknown)
        _fail("invalid_security_reference", f"unknown source identifiers: {values}")

    panel = normalized[
        ["date", "security_id", "adjusted_close", "close", "volume"]
    ].sort_values(["security_id", "date"], kind="stable", ignore_index=True)
    panel["return"] = calculate_simple_returns(panel)
    panel = panel[list(DAILY_PANEL_COLUMNS)]

    validate_daily_panel(panel, security_master)
    return panel


def ingest_market_data(
    source: MarketDataSource,
    security_master: pd.DataFrame,
    *,
    source_identifier_column: str = "ticker",
) -> pd.DataFrame:
    """Load a source and construct a validated analysis-ready daily panel."""
    return build_daily_panel(
        load_market_data(source),
        security_master,
        source_identifier_column=source_identifier_column,
    )
