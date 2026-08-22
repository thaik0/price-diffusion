"""Fail-closed validation for the core research datasets."""

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)

from price_diffusion.data_contracts import (
    DAILY_PANEL,
    PEER_MEMBERSHIP,
    SEMICONDUCTOR_CLASSIFICATION,
    SECURITY_MASTER,
    UNIVERSE_MEMBERSHIP,
    ColumnContract,
    ColumnKind,
    DataFrameContract,
)

WEIGHT_SUM_TOLERANCE = 1e-8


@dataclass(frozen=True)
class ValidationIssue:
    """One machine-readable contract violation."""

    dataset: str
    code: str
    message: str


class DataValidationError(ValueError):
    """Raised when one or more research data contracts are violated."""

    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues = tuple(issues)
        if not self.issues:
            raise ValueError("DataValidationError requires at least one issue")
        details = "; ".join(
            f"{issue.dataset}.{issue.code}: {issue.message}" for issue in self.issues
        )
        super().__init__(details)


def _issue(contract: DataFrameContract, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(contract.name, code, message)


def _type_is_valid(series: pd.Series, column: ColumnContract) -> bool:
    non_null = series.dropna()
    if column.kind is ColumnKind.STRING:
        return bool(non_null.map(lambda value: isinstance(value, str)).all())
    if column.kind is ColumnKind.DATE:
        return is_datetime64_any_dtype(series.dtype) and not isinstance(
            series.dtype, pd.DatetimeTZDtype
        )
    if column.kind is ColumnKind.BOOLEAN:
        return is_bool_dtype(series.dtype)
    if column.kind is ColumnKind.NUMERIC:
        return is_numeric_dtype(series.dtype) and not is_bool_dtype(series.dtype)
    return False


def collect_contract_issues(
    frame: pd.DataFrame, contract: DataFrameContract
) -> list[ValidationIssue]:
    """Collect general schema, date, and primary-key violations."""
    if not isinstance(frame, pd.DataFrame):
        return [_issue(contract, "not_dataframe", "value must be a pandas DataFrame")]

    issues: list[ValidationIssue] = []
    missing_columns = sorted(set(contract.columns).difference(frame.columns))
    if missing_columns:
        issues.append(
            _issue(
                contract,
                "missing_columns",
                f"required columns are missing: {', '.join(missing_columns)}",
            )
        )

    for name, column in contract.columns.items():
        if name not in frame:
            continue
        series = frame[name]
        if not column.nullable and series.isna().any():
            issues.append(
                _issue(contract, "null_values", f"column {name!r} contains null values")
            )
        if not _type_is_valid(series, column):
            issues.append(
                _issue(
                    contract,
                    "invalid_type",
                    f"column {name!r} must have logical type {column.kind.value}",
                )
            )
            continue

        non_null = series.dropna()
        if column.kind is ColumnKind.STRING and non_null.str.strip().eq("").any():
            issues.append(
                _issue(contract, "blank_string", f"column {name!r} contains blanks")
            )
        if column.kind is ColumnKind.DATE and not non_null.dt.normalize().equals(non_null):
            issues.append(
                _issue(
                    contract,
                    "invalid_date",
                    f"column {name!r} must contain midnight-normalized dates",
                )
            )
        if column.finite and not np.isfinite(non_null.to_numpy()).all():
            issues.append(
                _issue(
                    contract,
                    "non_finite",
                    f"column {name!r} contains infinite values",
                )
            )

    if all(name in frame for name in contract.primary_key):
        duplicate_mask = frame.duplicated(list(contract.primary_key), keep=False)
        if duplicate_mask.any():
            issues.append(
                _issue(
                    contract,
                    "duplicate_primary_key",
                    f"{int(duplicate_mask.sum())} rows share primary key "
                    f"{contract.primary_key}",
                )
            )
    return issues


def _known_security_issues(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    contract: DataFrameContract,
    security_master: pd.DataFrame,
) -> list[ValidationIssue]:
    if "security_id" not in security_master:
        return [
            _issue(
                contract,
                "invalid_security_reference",
                "security_master has no security_id column",
            )
        ]

    known = set(security_master["security_id"].dropna())
    issues: list[ValidationIssue] = []
    for name in columns:
        if name not in frame:
            continue
        unknown = sorted(
            (set(frame[name].dropna()) - known), key=lambda value: str(value)
        )
        if unknown:
            values = ", ".join(repr(value) for value in unknown)
            issues.append(
                _issue(
                    contract,
                    "invalid_security_reference",
                    f"column {name!r} contains unknown securities: {values}",
                )
            )
    return issues


def _raise_if_issues(issues: list[ValidationIssue]) -> None:
    if issues:
        raise DataValidationError(issues)


def validate_security_master(frame: pd.DataFrame) -> None:
    """Validate security metadata and unique security identifiers."""
    _raise_if_issues(collect_contract_issues(frame, SECURITY_MASTER))


def validate_semiconductor_classification(
    frame: pd.DataFrame, security_master: pd.DataFrame
) -> None:
    """Validate manually reviewed semiconductor labels and security references."""
    issues = collect_contract_issues(frame, SEMICONDUCTOR_CLASSIFICATION)
    issues.extend(
        _known_security_issues(
            frame,
            ("security_id",),
            SEMICONDUCTOR_CLASSIFICATION,
            security_master,
        )
    )
    _raise_if_issues(issues)


def validate_universe_membership(
    frame: pd.DataFrame, security_master: pd.DataFrame
) -> None:
    """Validate point-in-time eligibility and its security references."""
    issues = collect_contract_issues(frame, UNIVERSE_MEMBERSHIP)
    issues.extend(
        _known_security_issues(
            frame, ("security_id",), UNIVERSE_MEMBERSHIP, security_master
        )
    )
    _raise_if_issues(issues)


def validate_daily_panel(frame: pd.DataFrame, security_master: pd.DataFrame) -> None:
    """Validate daily observations, prices, volume, and security references."""
    issues = collect_contract_issues(frame, DAILY_PANEL)
    issues.extend(
        _known_security_issues(frame, ("security_id",), DAILY_PANEL, security_master)
    )
    if "adjusted_close" in frame and is_numeric_dtype(frame["adjusted_close"]):
        if frame["adjusted_close"].le(0).any():
            issues.append(
                _issue(DAILY_PANEL, "non_positive_price", "adjusted_close must be > 0")
            )
    if "close" in frame and is_numeric_dtype(frame["close"]):
        if frame["close"].le(0).any():
            issues.append(_issue(DAILY_PANEL, "non_positive_price", "close must be > 0"))
    if "volume" in frame and is_numeric_dtype(frame["volume"]):
        if frame["volume"].lt(0).any():
            issues.append(_issue(DAILY_PANEL, "negative_volume", "volume must be >= 0"))
    return_inputs = {"date", "security_id", "adjusted_close", "return"}
    can_check_returns = (
        return_inputs <= set(frame.columns)
        and is_datetime64_any_dtype(frame["date"])
        and is_numeric_dtype(frame["adjusted_close"])
        and is_numeric_dtype(frame["return"])
        and not frame[["date", "security_id", "adjusted_close"]].isna().any().any()
        and not frame.duplicated(["date", "security_id"]).any()
        and np.isfinite(frame["adjusted_close"].to_numpy()).all()
        and frame["adjusted_close"].gt(0).all()
    )
    if can_check_returns:
        ordered = frame.sort_values(["security_id", "date"], kind="stable")
        prior = ordered.groupby("security_id", sort=False)["adjusted_close"].shift(1)
        expected = ordered["adjusted_close"].div(prior).sub(1.0)
        actual = ordered["return"]
        first_observation = prior.isna()
        invalid_first = actual[first_observation].notna()
        later = ~first_observation
        invalid_later = actual[later].isna()
        comparable = later & actual.notna()
        mismatch = ~np.isclose(
            actual[comparable].to_numpy(dtype=float),
            expected[comparable].to_numpy(dtype=float),
            rtol=1e-10,
            atol=1e-12,
        )
        invalid_count = int(invalid_first.sum() + invalid_later.sum() + mismatch.sum())
        if invalid_count:
            issues.append(
                _issue(
                    DAILY_PANEL,
                    "invalid_return",
                    f"{invalid_count} returns do not match adjusted-close simple returns",
                )
            )
    _raise_if_issues(issues)


def validate_peer_membership(
    frame: pd.DataFrame, security_master: pd.DataFrame
) -> None:
    """Validate directed, weighted, point-in-time peer relationships."""
    issues = collect_contract_issues(frame, PEER_MEMBERSHIP)
    issues.extend(
        _known_security_issues(
            frame, ("security_id", "peer_id"), PEER_MEMBERSHIP, security_master
        )
    )
    if {"security_id", "peer_id"} <= set(frame.columns):
        self_peer_count = int(frame["security_id"].eq(frame["peer_id"]).sum())
        if self_peer_count:
            issues.append(
                _issue(
                    PEER_MEMBERSHIP,
                    "self_peer",
                    f"{self_peer_count} rows use the security itself as a peer",
                )
            )

    group_columns = ["date", "security_id", "peer_definition"]
    if set(group_columns + ["weight"]) <= set(frame.columns) and is_numeric_dtype(
        frame["weight"]
    ):
        if frame["weight"].lt(0).any():
            issues.append(
                _issue(PEER_MEMBERSHIP, "negative_weight", "weights must be >= 0")
            )
        weight_sums = frame.groupby(group_columns, dropna=False)["weight"].sum()
        invalid_sums = weight_sums[
            ~np.isclose(weight_sums.to_numpy(), 1.0, atol=WEIGHT_SUM_TOLERANCE, rtol=0)
        ]
        if not invalid_sums.empty:
            issues.append(
                _issue(
                    PEER_MEMBERSHIP,
                    "invalid_weight_sum",
                    f"{len(invalid_sums)} peer groups have weights that do not sum to 1",
                )
            )
    _raise_if_issues(issues)


def validate_research_data(
    *,
    security_master: pd.DataFrame,
    universe_membership: pd.DataFrame,
    daily_panel: pd.DataFrame,
    peer_membership: pd.DataFrame,
) -> None:
    """Validate all four core datasets and their cross-dataset references."""
    validate_security_master(security_master)
    validate_universe_membership(universe_membership, security_master)
    validate_daily_panel(daily_panel, security_master)
    validate_peer_membership(peer_membership, security_master)
