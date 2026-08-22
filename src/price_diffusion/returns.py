"""Point-in-time abnormal and peer-relative return transformations."""

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype

from price_diffusion.validation import (
    DataValidationError,
    ValidationIssue,
    validate_relative_returns,
)

RELATIVE_RETURN_COLUMNS = (
    "date",
    "security_id",
    "peer_definition",
    "stock_return",
    "peer_return",
    "relative_return",
    "market_adjusted_return",
    "semiconductor_adjusted_return",
)


@dataclass(frozen=True)
class FactorResidualResult:
    """Rolling factor residuals and the parameters used for each prediction."""

    residual_returns: pd.DataFrame
    model_parameters: pd.DataFrame


def _fail(dataset: str, code: str, message: str) -> None:
    raise DataValidationError([ValidationIssue(dataset, code, message)])


def _validate_return_frame(
    frame: pd.DataFrame, *, value_column: str, dataset: str, security_column: str
) -> None:
    required = {"date", security_column, value_column}
    missing = sorted(required.difference(frame.columns))
    if missing:
        _fail(dataset, "missing_columns", f"required columns are missing: {', '.join(missing)}")
    if not is_datetime64_any_dtype(frame["date"]):
        _fail(dataset, "invalid_type", "date must be a pandas datetime column")
    if isinstance(frame["date"].dtype, pd.DatetimeTZDtype):
        _fail(dataset, "invalid_type", "date must be timezone-naive")
    if not frame["date"].dt.normalize().equals(frame["date"]):
        _fail(dataset, "invalid_date", "dates must be normalized to midnight")
    if frame[["date", security_column]].isna().any().any():
        _fail(dataset, "null_values", "date and security identifiers may not be null")
    if not is_numeric_dtype(frame[value_column]):
        _fail(dataset, "invalid_type", f"{value_column} must be numeric")
    if frame.duplicated(["date", security_column]).any():
        _fail(dataset, "duplicate_primary_key", "date/security pairs must be unique")
    values = frame[value_column].dropna().to_numpy(dtype=float)
    if not np.isfinite(values).all():
        _fail(dataset, "non_finite", f"{value_column} contains infinite values")


def _validate_peer_input(peer_membership: pd.DataFrame) -> None:
    required = {"date", "security_id", "peer_id", "peer_definition", "weight"}
    missing = sorted(required.difference(peer_membership.columns))
    if missing:
        _fail("peer_membership", "missing_columns", f"required columns are missing: {', '.join(missing)}")
    if peer_membership[["date", "security_id", "peer_id", "peer_definition", "weight"]].isna().any().any():
        _fail("peer_membership", "null_values", "peer membership fields may not be null")
    if not is_datetime64_any_dtype(peer_membership["date"]):
        _fail("peer_membership", "invalid_type", "date must be a pandas datetime column")
    peer_key = ["date", "security_id", "peer_id", "peer_definition"]
    if peer_membership.duplicated(peer_key).any():
        _fail("peer_membership", "duplicate_primary_key", "peer relationships must be unique")
    if peer_membership["security_id"].eq(peer_membership["peer_id"]).any():
        _fail("peer_membership", "self_peer", "peer portfolios must be leave-one-out")
    if not is_numeric_dtype(peer_membership["weight"]):
        _fail("peer_membership", "invalid_type", "weight must be numeric")
    if peer_membership["weight"].lt(0).any():
        _fail("peer_membership", "negative_weight", "weights must be non-negative")
    if not np.isfinite(peer_membership["weight"].to_numpy(dtype=float)).all():
        _fail("peer_membership", "non_finite", "weights must be finite")
    keys = ["date", "security_id", "peer_definition"]
    sums = peer_membership.groupby(keys, dropna=False)["weight"].sum()
    if not np.allclose(sums.to_numpy(dtype=float), 1.0, atol=1e-8, rtol=0):
        _fail("peer_membership", "invalid_weight_sum", "peer weights must sum to one")


def calculate_peer_portfolio_returns(
    returns: pd.DataFrame,
    peer_membership: pd.DataFrame,
    *,
    return_column: str = "return",
) -> pd.DataFrame:
    """Calculate dated peer returns, renormalizing over observed peers.

    Missing peer observations are excluded. A portfolio with no observed peer
    returns is retained with a missing ``peer_return``.
    """
    _validate_return_frame(
        returns,
        value_column=return_column,
        dataset="returns",
        security_column="security_id",
    )
    _validate_peer_input(peer_membership)

    keys = ["date", "security_id", "peer_definition"]
    groups = peer_membership[keys].drop_duplicates()
    peer_values = returns[["date", "security_id", return_column]].rename(
        columns={"security_id": "peer_id", return_column: "peer_observation"}
    )
    joined = peer_membership.merge(
        peer_values, on=["date", "peer_id"], how="left", validate="many_to_one"
    )
    observed = joined["peer_observation"].notna()
    joined["available_weight"] = joined["weight"].where(observed, 0.0)
    joined["weighted_return"] = (
        joined["peer_observation"].fillna(0.0) * joined["available_weight"]
    )
    aggregates = joined.groupby(keys, as_index=False).agg(
        weighted_return=("weighted_return", "sum"),
        available_weight=("available_weight", "sum"),
        peer_count=("peer_observation", "count"),
    )
    aggregates["peer_return"] = aggregates["weighted_return"].div(
        aggregates["available_weight"].replace(0.0, np.nan)
    )
    return groups.merge(
        aggregates[keys + ["peer_return", "peer_count"]],
        on=keys,
        how="left",
        validate="one_to_one",
    ).sort_values(keys, ignore_index=True)


def calculate_abnormal_returns(
    stock_returns: pd.DataFrame,
    factor_returns: pd.DataFrame,
    *,
    stock_return_column: str = "return",
    factor_return_column: str = "return",
    output_column: str = "abnormal_return",
) -> pd.DataFrame:
    """Subtract a configurable dated factor from each stock return."""
    _validate_return_frame(
        stock_returns,
        value_column=stock_return_column,
        dataset="stock_returns",
        security_column="security_id",
    )
    required = {"date", factor_return_column}
    missing = sorted(required.difference(factor_returns.columns))
    if missing:
        _fail("factor_returns", "missing_columns", f"required columns are missing: {', '.join(missing)}")
    if factor_returns["date"].duplicated().any():
        _fail("factor_returns", "duplicate_primary_key", "factor dates must be unique")
    if not is_datetime64_any_dtype(factor_returns["date"]):
        _fail("factor_returns", "invalid_type", "date must be a pandas datetime column")
    if not is_numeric_dtype(factor_returns[factor_return_column]):
        _fail("factor_returns", "invalid_type", f"{factor_return_column} must be numeric")
    factor_values = factor_returns[factor_return_column].dropna().to_numpy(dtype=float)
    if not np.isfinite(factor_values).all():
        _fail("factor_returns", "non_finite", f"{factor_return_column} contains infinite values")

    output = stock_returns[["date", "security_id", stock_return_column]].merge(
        factor_returns[["date", factor_return_column]].rename(
            columns={factor_return_column: "factor_return"}
        ),
        on="date",
        how="left",
        validate="many_to_one",
    )
    output[output_column] = output[stock_return_column] - output["factor_return"]
    return output.rename(columns={stock_return_column: "stock_return"})[
        ["date", "security_id", "stock_return", "factor_return", output_column]
    ]


def calculate_relative_abnormal_returns(
    abnormal_returns: pd.DataFrame,
    peer_membership: pd.DataFrame,
    *,
    abnormal_return_column: str = "abnormal_return",
) -> pd.DataFrame:
    """Compare each stock abnormal return with its leave-one-out peers."""
    peers = calculate_peer_portfolio_returns(
        abnormal_returns, peer_membership, return_column=abnormal_return_column
    ).rename(columns={"peer_return": "peer_abnormal_return"})
    stocks = abnormal_returns[["date", "security_id", abnormal_return_column]]
    output = peers.merge(
        stocks, on=["date", "security_id"], how="left", validate="many_to_one"
    )
    output["relative_abnormal_return"] = (
        output[abnormal_return_column] - output["peer_abnormal_return"]
    )
    return output.rename(columns={abnormal_return_column: "stock_abnormal_return"})[
        [
            "date",
            "security_id",
            "peer_definition",
            "peer_count",
            "stock_abnormal_return",
            "peer_abnormal_return",
            "relative_abnormal_return",
        ]
    ]


def build_relative_returns(
    daily_returns: pd.DataFrame,
    peer_membership: pd.DataFrame,
    market_returns: pd.DataFrame,
    semiconductor_factor_returns: pd.DataFrame,
    *,
    stock_return_column: str = "return",
    market_return_column: str = "return",
    semiconductor_return_column: str = "return",
) -> pd.DataFrame:
    """Build the required Stage 6 daily relative-return dataset."""
    peers = calculate_peer_portfolio_returns(
        daily_returns, peer_membership, return_column=stock_return_column
    )
    stocks = daily_returns[["date", "security_id", stock_return_column]].rename(
        columns={stock_return_column: "stock_return"}
    )
    output = peers.merge(
        stocks, on=["date", "security_id"], how="left", validate="many_to_one"
    )
    output["relative_return"] = output["stock_return"] - output["peer_return"]

    market = calculate_abnormal_returns(
        daily_returns,
        market_returns,
        stock_return_column=stock_return_column,
        factor_return_column=market_return_column,
        output_column="market_adjusted_return",
    )[["date", "security_id", "market_adjusted_return"]]
    semiconductor = calculate_abnormal_returns(
        daily_returns,
        semiconductor_factor_returns,
        stock_return_column=stock_return_column,
        factor_return_column=semiconductor_return_column,
        output_column="semiconductor_adjusted_return",
    )[["date", "security_id", "semiconductor_adjusted_return"]]
    output = output.merge(
        market, on=["date", "security_id"], how="left", validate="many_to_one"
    ).merge(
        semiconductor,
        on=["date", "security_id"],
        how="left",
        validate="many_to_one",
    )
    output = output[list(RELATIVE_RETURN_COLUMNS)].sort_values(
        ["date", "security_id", "peer_definition"], ignore_index=True
    )
    validate_relative_returns(output)
    return output


def estimate_trailing_factor_residuals(
    stock_returns: pd.DataFrame,
    factor_returns: pd.DataFrame,
    *,
    factor_columns: Sequence[str],
    stock_return_column: str = "return",
    estimation_window: int = 60,
    min_observations: int | None = None,
) -> FactorResidualResult:
    """Estimate rolling OLS residuals using only observations before each date.

    This is deliberately a small architecture for future factor models. It
    stores one parameter row per prediction and does not choose factors or
    estimation-window values for the researcher.
    """
    if estimation_window < 1:
        raise ValueError("estimation_window must be positive")
    minimum = estimation_window if min_observations is None else min_observations
    if minimum < len(factor_columns) + 1 or minimum > estimation_window:
        raise ValueError(
            "min_observations must exceed the number of regressors and be no "
            "larger than estimation_window"
        )
    factors = tuple(factor_columns)
    if not factors or len(factors) != len(set(factors)):
        raise ValueError("factor_columns must contain unique factor names")
    _validate_return_frame(
        stock_returns,
        value_column=stock_return_column,
        dataset="stock_returns",
        security_column="security_id",
    )
    missing = sorted(({"date"} | set(factors)).difference(factor_returns.columns))
    if missing:
        _fail("factor_returns", "missing_columns", f"required columns are missing: {', '.join(missing)}")
    if factor_returns["date"].duplicated().any():
        _fail("factor_returns", "duplicate_primary_key", "factor dates must be unique")
    if not is_datetime64_any_dtype(factor_returns["date"]):
        _fail("factor_returns", "invalid_type", "date must be a pandas datetime column")
    for factor in factors:
        if not is_numeric_dtype(factor_returns[factor]):
            _fail("factor_returns", "invalid_type", f"{factor} must be numeric")
        values = factor_returns[factor].dropna().to_numpy(dtype=float)
        if not np.isfinite(values).all():
            _fail("factor_returns", "non_finite", f"{factor} contains infinite values")

    combined = stock_returns[["date", "security_id", stock_return_column]].merge(
        factor_returns[["date", *factors]], on="date", how="left", validate="many_to_one"
    ).sort_values(["security_id", "date"], kind="stable")
    residual_rows: list[dict[str, object]] = []
    parameter_rows: list[dict[str, object]] = []
    for security_id, group in combined.groupby("security_id", sort=False):
        group = group.reset_index(drop=True)
        complete = group[[stock_return_column, *factors]].notna().all(axis=1)
        for position, current in group.iterrows():
            residual = np.nan
            eligible = group.loc[: position - 1] if position else group.iloc[0:0]
            eligible = eligible.loc[complete.iloc[:position].to_numpy()].tail(
                estimation_window
            )
            if len(eligible) >= minimum and current[[*factors]].notna().all() and pd.notna(current[stock_return_column]):
                design = np.column_stack(
                    [np.ones(len(eligible)), eligible[list(factors)].to_numpy(float)]
                )
                coefficients, _, _, _ = np.linalg.lstsq(
                    design, eligible[stock_return_column].to_numpy(float), rcond=None
                )
                prediction = coefficients[0] + np.dot(
                    coefficients[1:], current[list(factors)].to_numpy(float)
                )
                residual = float(current[stock_return_column] - prediction)
                row: dict[str, object] = {
                    "date": current["date"],
                    "security_id": security_id,
                    "estimation_start": eligible["date"].iloc[0],
                    "estimation_end": eligible["date"].iloc[-1],
                    "observation_count": len(eligible),
                    "intercept": float(coefficients[0]),
                }
                row.update(
                    {f"beta_{name}": float(value) for name, value in zip(factors, coefficients[1:])}
                )
                parameter_rows.append(row)
            residual_rows.append(
                {
                    "date": current["date"],
                    "security_id": security_id,
                    "stock_return": current[stock_return_column],
                    "factor_residual_return": residual,
                }
            )

    residuals = pd.DataFrame(residual_rows).sort_values(
        ["date", "security_id"], ignore_index=True
    )
    parameter_columns = [
        "date",
        "security_id",
        "estimation_start",
        "estimation_end",
        "observation_count",
        "intercept",
        *(f"beta_{name}" for name in factors),
    ]
    parameters = pd.DataFrame(parameter_rows, columns=parameter_columns).sort_values(
        ["date", "security_id"], ignore_index=True
    )
    return FactorResidualResult(residuals, parameters)
