"""Yahoo Finance acquisition, standardization, returns, and data auditing.

Raw vendor responses are immutable snapshots.  Standardized outputs are long
panels keyed by the stable research ``security_id`` rather than by a vendor
symbol.  Daily dates remain exchange-local calendar labels and prices/returns
remain in each listing's local currency.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from price_diffusion.paths import METADATA_DIR, OUTPUTS_DIR, PROJECT_ROOT

YAHOO_START_DATE = "2010-01-01"
SECURITY_MASTER_COLUMNS = (
    "security_id",
    "ticker",
    "yahoo_symbol",
    "company_name",
    "exchange",
    "currency",
)
DAILY_PRICE_COLUMNS = (
    "date",
    "security_id",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
)
DAILY_RETURN_COLUMNS = ("date", "security_id", "return", "adj_close")
AUDIT_COLUMNS = (
    "security_id",
    "ticker",
    "observation_count",
    "first_date",
    "last_date",
    "missing_percentage",
    "average_volume",
    "issues",
)

_YAHOO_COLUMN_ALIASES = {
    "date": "date",
    "datetime": "date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "adjclose": "adj_close",
    "adjustedclose": "adj_close",
    "volume": "volume",
}


@dataclass(frozen=True)
class YahooPipelineArtifacts:
    """In-memory outputs and paths produced by one acquisition run."""

    daily_prices: pd.DataFrame
    daily_returns: pd.DataFrame
    data_audit: pd.DataFrame
    download_status: pd.DataFrame
    raw_snapshot_dir: Path
    daily_prices_path: Path
    daily_returns_path: Path
    data_audit_path: Path
    download_status_path: Path


def load_security_master(
    path: str | Path = METADATA_DIR / "security_master.csv",
) -> pd.DataFrame:
    """Load and validate the Yahoo-facing security symbol mapping."""
    frame = pd.read_csv(Path(path), dtype=str, keep_default_na=False)
    missing = sorted(set(SECURITY_MASTER_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError("security master is missing columns: " + ", ".join(missing))

    output = frame[list(SECURITY_MASTER_COLUMNS)].copy()
    for column in SECURITY_MASTER_COLUMNS:
        output[column] = output[column].str.strip()
        if output[column].eq("").any():
            raise ValueError(f"security master column {column!r} contains blanks")

    for column in ("security_id", "ticker", "yahoo_symbol"):
        duplicates = sorted(output.loc[output[column].duplicated(False), column].unique())
        if duplicates:
            raise ValueError(
                f"security master column {column!r} contains duplicates: "
                + ", ".join(duplicates)
            )
    return output


def download_yahoo_history(
    yahoo_symbol: str,
    *,
    start: str = YAHOO_START_DATE,
    end: str | None = None,
) -> pd.DataFrame:
    """Download one unadjusted Yahoo response with an explicit Adj Close field."""
    try:
        import yfinance as yf
    except ImportError as error:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "yfinance is required for live downloads; install project dependencies"
        ) from error

    return yf.download(
        yahoo_symbol,
        start=start,
        end=end,
        auto_adjust=False,
        actions=False,
        repair=False,
        keepna=False,
        progress=False,
        threads=False,
        group_by="column",
        multi_level_index=False,
    )


def _canonical_yahoo_column(column: Any) -> str:
    parts = column if isinstance(column, tuple) else (column,)
    for part in parts:
        token = re.sub(r"[^a-z0-9]", "", str(part).lower())
        if token in _YAHOO_COLUMN_ALIASES:
            return _YAHOO_COLUMN_ALIASES[token]
    return "__".join(str(part) for part in parts if str(part))


def _normalize_yahoo_dates(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce")
    if isinstance(parsed.dtype, pd.DatetimeTZDtype):
        # Preserve the exchange-local date label; UTC conversion can move Asian
        # daily bars to the preceding calendar day.
        parsed = parsed.dt.tz_localize(None)
    return parsed.dt.normalize()


def standardize_yahoo_download(
    raw: pd.DataFrame,
    *,
    security_id: str,
    ticker: str,
) -> pd.DataFrame:
    """Convert one Yahoo response to the canonical long daily-price schema."""
    if not isinstance(raw, pd.DataFrame):
        raise TypeError("Yahoo downloader must return a pandas DataFrame")
    if raw.empty:
        return pd.DataFrame(columns=DAILY_PRICE_COLUMNS)

    flattened = raw.reset_index().copy()
    flattened.columns = [_canonical_yahoo_column(column) for column in flattened.columns]
    duplicated_columns = flattened.columns[flattened.columns.duplicated()].unique()
    if len(duplicated_columns):
        raise ValueError(
            "Yahoo response contains ambiguous columns: "
            + ", ".join(map(str, duplicated_columns))
        )

    required = {"date", "open", "high", "low", "close", "adj_close", "volume"}
    missing = sorted(required.difference(flattened.columns))
    if missing:
        raise ValueError("Yahoo response is missing columns: " + ", ".join(missing))

    standardized = pd.DataFrame(
        {
            "date": _normalize_yahoo_dates(flattened["date"]),
            "security_id": security_id,
            "ticker": ticker,
        }
    )
    for column in ("open", "high", "low", "close", "adj_close", "volume"):
        standardized[column] = pd.to_numeric(flattened[column], errors="coerce")

    price_columns = ["open", "high", "low", "close", "adj_close"]
    empty_placeholder = standardized[price_columns].isna().all(axis=1) & (
        standardized["volume"].isna() | standardized["volume"].eq(0)
    )
    standardized = standardized.loc[~empty_placeholder].copy()
    standardized = standardized[list(DAILY_PRICE_COLUMNS)]
    standardized = standardized.sort_values("date", kind="stable", ignore_index=True)
    return standardized


def write_raw_download(raw: pd.DataFrame, path: str | Path) -> Path:
    """Write an immutable raw CSV, failing if the target already exists."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="") as handle:
        raw.to_csv(handle, index=True)
    return target


def combine_daily_prices(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Combine standardized security frames and enforce a unique panel key."""
    nonempty = [frame for frame in frames if not frame.empty]
    if not nonempty:
        return pd.DataFrame(columns=DAILY_PRICE_COLUMNS)
    panel = pd.concat(nonempty, ignore_index=True)[list(DAILY_PRICE_COLUMNS)]
    panel = panel.sort_values(["security_id", "date"], kind="stable", ignore_index=True)
    duplicate_mask = panel.duplicated(["security_id", "date"], keep=False)
    if duplicate_mask.any():
        pairs = int(duplicate_mask.sum())
        raise ValueError(f"standardized prices contain {pairs} duplicate security/date rows")
    return panel


def calculate_daily_returns(daily_prices: pd.DataFrame) -> pd.DataFrame:
    """Calculate within-security simple returns from adjusted close."""
    missing = sorted(
        {"date", "security_id", "adj_close"}.difference(daily_prices.columns)
    )
    if missing:
        raise ValueError("daily prices are missing columns: " + ", ".join(missing))

    ordered = daily_prices.sort_values(
        ["security_id", "date"], kind="stable", ignore_index=True
    ).copy()
    prior = ordered.groupby("security_id", sort=False)["adj_close"].shift(1)
    ordered["return"] = ordered["adj_close"].div(prior).sub(1.0)
    return ordered[list(DAILY_RETURN_COLUMNS)]


def _estimated_missing_weekdays(security_prices: pd.DataFrame) -> tuple[int, float]:
    valid_dates = pd.DatetimeIndex(security_prices["date"].dropna().unique()).normalize()
    if len(valid_dates) == 0:
        return 0, 100.0
    expected = pd.bdate_range(valid_dates.min(), valid_dates.max())
    observed_weekdays = valid_dates[valid_dates.dayofweek < 5]
    missing_count = max(len(expected.difference(observed_weekdays)), 0)
    missing_percentage = 100.0 * missing_count / len(expected) if len(expected) else 0.0
    return missing_count, missing_percentage


def build_data_audit(
    security_master: pd.DataFrame,
    daily_prices: pd.DataFrame,
    daily_returns: pd.DataFrame | None = None,
    *,
    large_gap_days: int = 7,
    extreme_return_threshold: float = 0.50,
) -> pd.DataFrame:
    """Summarize coverage and flag gaps, price, volume, and return problems.

    Missing-day estimates use a Monday-Friday calendar.  Exchange holidays are
    intentionally not harmonized at this stage and therefore appear in the
    estimate; the issue label makes that limitation explicit.
    """
    master = security_master[list(SECURITY_MASTER_COLUMNS)].copy()
    returns = (
        calculate_daily_returns(daily_prices)
        if daily_returns is None
        else daily_returns.copy()
    )
    rows: list[dict[str, Any]] = []

    for security in master.itertuples(index=False):
        prices = daily_prices.loc[
            daily_prices["security_id"].eq(security.security_id)
        ].sort_values("date", kind="stable")
        security_returns = returns.loc[
            returns["security_id"].eq(security.security_id)
        ].sort_values("date", kind="stable")
        issues: list[str] = []
        observation_count = len(prices)

        if prices.empty:
            rows.append(
                {
                    "security_id": security.security_id,
                    "ticker": security.ticker,
                    "observation_count": 0,
                    "first_date": pd.NaT,
                    "last_date": pd.NaT,
                    "missing_percentage": 100.0,
                    "average_volume": np.nan,
                    "issues": "no_data",
                }
            )
            continue

        duplicate_count = int(prices.duplicated("date", keep=False).sum())
        if duplicate_count:
            issues.append(f"duplicate_dates={duplicate_count}")

        missing_weekdays, missing_percentage = _estimated_missing_weekdays(prices)
        if missing_weekdays:
            issues.append(f"missing_weekdays_or_holidays={missing_weekdays}")

        date_gaps = prices["date"].dropna().drop_duplicates().sort_values().diff().dt.days
        large_gaps = date_gaps[date_gaps >= large_gap_days]
        if len(large_gaps):
            issues.append(
                f"large_gaps={len(large_gaps)}(max_calendar_days={int(large_gaps.max())})"
            )

        zero_volume = int(prices["volume"].eq(0).sum())
        if zero_volume:
            issues.append(f"zero_volume_days={zero_volume}")

        price_columns = ["open", "high", "low", "close", "adj_close"]
        non_positive = int(prices[price_columns].le(0).sum().sum())
        if non_positive:
            issues.append(f"non_positive_prices={non_positive}")
        missing_adjusted = int(prices["adj_close"].isna().sum())
        if missing_adjusted:
            issues.append(f"missing_adjusted_prices={missing_adjusted}")

        if not security_returns.empty:
            return_values = security_returns["return"]
            impossible = int((return_values <= -1.0).sum())
            if impossible:
                issues.append(f"impossible_returns={impossible}")
            extreme = int((return_values.abs() > extreme_return_threshold).sum())
            if extreme:
                issues.append(f"extreme_returns={extreme}")
            missing_after_first = int(return_values.iloc[1:].isna().sum())
            if missing_after_first:
                issues.append(f"missing_returns_after_first={missing_after_first}")

        rows.append(
            {
                "security_id": security.security_id,
                "ticker": security.ticker,
                "observation_count": observation_count,
                "first_date": prices["date"].min(),
                "last_date": prices["date"].max(),
                "missing_percentage": missing_percentage,
                "average_volume": prices["volume"].mean(),
                "issues": "; ".join(issues),
            }
        )

    return pd.DataFrame(rows, columns=AUDIT_COLUMNS)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def run_yahoo_pipeline(
    *,
    security_master_path: str | Path = METADATA_DIR / "security_master.csv",
    raw_root: str | Path = PROJECT_ROOT / "data" / "raw" / "yahoo_prices",
    interim_dir: str | Path = PROJECT_ROOT / "data" / "interim",
    diagnostics_dir: str | Path = OUTPUTS_DIR / "diagnostics",
    start: str = YAHOO_START_DATE,
    end: str | None = None,
    run_id: str | None = None,
    downloader: Callable[..., pd.DataFrame] = download_yahoo_history,
) -> YahooPipelineArtifacts:
    """Run a complete Yahoo acquisition while preserving every raw response."""
    master = load_security_master(security_master_path)
    identifier = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_dir = Path(raw_root) / identifier
    # A run identifier is an immutability boundary.  Reusing one must fail before
    # any network call or write can alter a prior raw snapshot.
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    standardized_frames: list[pd.DataFrame] = []
    status_rows: list[dict[str, Any]] = []
    for security in master.itertuples(index=False):
        raw_path = snapshot_dir / (
            f"{_safe_filename(security.security_id)}__"
            f"{_safe_filename(security.yahoo_symbol)}.csv"
        )
        try:
            raw = downloader(security.yahoo_symbol, start=start, end=end)
            write_raw_download(raw, raw_path)
            standardized = standardize_yahoo_download(
                raw,
                security_id=security.security_id,
                ticker=security.ticker,
            )
            standardized_frames.append(standardized)
            status = "no_data" if standardized.empty else "downloaded"
            error = ""
        except Exception as exc:  # one unavailable listing must not erase the run
            standardized = pd.DataFrame(columns=DAILY_PRICE_COLUMNS)
            status = "error"
            error = f"{type(exc).__name__}: {exc}"

        status_rows.append(
            {
                "security_id": security.security_id,
                "ticker": security.ticker,
                "yahoo_symbol": security.yahoo_symbol,
                "status": status,
                "observation_count": len(standardized),
                "raw_path": (
                    str(raw_path.relative_to(PROJECT_ROOT))
                    if raw_path.exists() and raw_path.is_relative_to(PROJECT_ROOT)
                    else str(raw_path) if raw_path.exists() else ""
                ),
                "error": error,
            }
        )

    daily_prices = combine_daily_prices(standardized_frames)
    daily_returns = calculate_daily_returns(daily_prices)
    audit = build_data_audit(master, daily_prices, daily_returns)
    download_status = pd.DataFrame(status_rows)

    interim = Path(interim_dir)
    diagnostics = Path(diagnostics_dir)
    daily_prices_path = interim / "daily_prices.parquet"
    daily_returns_path = interim / "daily_returns.parquet"
    data_audit_path = diagnostics / "data_audit.csv"
    download_status_path = diagnostics / "yahoo_download_status.csv"
    _atomic_parquet(daily_prices, daily_prices_path)
    _atomic_parquet(daily_returns, daily_returns_path)
    diagnostics.mkdir(parents=True, exist_ok=True)
    audit.to_csv(data_audit_path, index=False)
    download_status.to_csv(download_status_path, index=False)

    return YahooPipelineArtifacts(
        daily_prices=daily_prices,
        daily_returns=daily_returns,
        data_audit=audit,
        download_status=download_status,
        raw_snapshot_dir=snapshot_dir,
        daily_prices_path=daily_prices_path,
        daily_returns_path=daily_returns_path,
        data_audit_path=data_audit_path,
        download_status_path=download_status_path,
    )
