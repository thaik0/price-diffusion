"""Stage 11D audits and assembly for the first combined research dataset.

The module reports observed data problems without repairing prices, changing
identifiers, harmonizing exchange calendars, or altering universe rules.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from price_diffusion.data import calculate_daily_returns
from price_diffusion.paths import OUTPUTS_DIR, PROJECT_ROOT
from price_diffusion.universe import (
    UniverseParameters,
    build_approved_universe_membership,
    create_universe_manifest,
    write_universe_manifest,
)

MAPPING_AUDIT_COLUMNS = (
    "security_id", "ticker", "yahoo_symbol", "data_found", "first_date",
    "last_date", "issues",
)
COVERAGE_AUDIT_COLUMNS = (
    "security_id", "ticker", "first_trading_date", "last_trading_date",
    "number_of_observations", "years_covered",
    "insufficient_history_for_factor_models", "short_history_company",
    "recent_ipo", "issues",
)
RETURN_QUALITY_COLUMNS = (
    "security_id", "ticker", "number_of_observations", "missing_returns",
    "missing_returns_after_first", "duplicate_dates", "extreme_daily_returns",
    "impossible_returns", "missing_adj_close", "non_finite_adj_close",
    "non_positive_adj_close", "negative_volume", "max_abs_return",
    "extreme_return_dates", "issues",
)
DAILY_PANEL_COLUMNS = (
    "date", "security_id", "ticker", "subsector", "universe_tier",
    "universe_version", "adj_close", "return", "volume", "eligible",
    "extension_eligible", "extreme_return_flag",
)
HISTORICAL_ELIGIBILITY_COLUMNS = (
    "date", "security_id", "universe_version", "eligible", "reason",
    "extension_eligible", "extension_reason",
)


@dataclass(frozen=True)
class Stage11DArtifacts:
    """Frames and paths created by a Stage 11D run."""

    security_mapping_audit: pd.DataFrame
    historical_coverage_audit: pd.DataFrame
    trading_calendar_audit: pd.DataFrame
    exchange_calendar_summary: pd.DataFrame
    return_quality_report: pd.DataFrame
    historical_eligibility: pd.DataFrame
    daily_panel: pd.DataFrame
    security_mapping_audit_path: Path
    historical_coverage_audit_path: Path
    trading_calendar_audit_path: Path
    exchange_calendar_summary_path: Path
    return_quality_report_path: Path
    historical_eligibility_path: Path
    daily_panel_path: Path
    universe_manifest_path: Path


def _clean_string(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def build_security_mapping_audit(
    security_master: pd.DataFrame, daily_prices: pd.DataFrame
) -> pd.DataFrame:
    """Audit approved mappings and observed identifiers without changing either."""
    required_master = {"security_id", "ticker", "yahoo_symbol"}
    required_prices = {"security_id", "ticker", "date"}
    missing_master = sorted(required_master.difference(security_master.columns))
    missing_prices = sorted(required_prices.difference(daily_prices.columns))
    if missing_master or missing_prices:
        raise ValueError(
            "mapping audit inputs are missing columns: "
            + ", ".join(missing_master + missing_prices)
        )

    master = security_master.copy()
    observed_ids = set(daily_prices["security_id"].dropna().map(str))
    master_ids = set(master["security_id"].dropna().map(str))
    downloaded_ticker_ids = (
        daily_prices.assign(
            _ticker=daily_prices["ticker"].map(_clean_string),
            _security_id=daily_prices["security_id"].map(_clean_string),
        )
        .loc[lambda frame: frame["_ticker"].ne("") & frame["_security_id"].ne("")]
        .groupby("_ticker")["_security_id"]
        .nunique()
    )
    rows: list[dict[str, Any]] = []
    for _, security in master.iterrows():
        security_id = _clean_string(security["security_id"])
        ticker = _clean_string(security["ticker"])
        yahoo_symbol = _clean_string(security["yahoo_symbol"])
        prices = daily_prices.loc[daily_prices["security_id"].astype(str).eq(security_id)]
        issues: list[str] = []
        if not security_id:
            issues.append("missing_security_id")
        if not ticker:
            issues.append("missing_ticker")
        if not yahoo_symbol:
            issues.append("missing_yahoo_symbol")
        for column, value in (
            ("security_id", security_id), ("ticker", ticker),
            ("yahoo_symbol", yahoo_symbol),
        ):
            if value and int(master[column].map(_clean_string).eq(value).sum()) > 1:
                issues.append(f"duplicate_{column}")
        observed_tickers = sorted(
            value for value in prices["ticker"].dropna().map(_clean_string).unique()
            if value
        )
        missing_downloaded_tickers = int(prices["ticker"].map(_clean_string).eq("").sum())
        if missing_downloaded_tickers:
            issues.append(f"downloaded_rows_missing_ticker={missing_downloaded_tickers}")
        if len(observed_tickers) > 1:
            issues.append("multiple_downloaded_tickers=" + "|".join(observed_tickers))
        elif observed_tickers and observed_tickers[0] != ticker:
            issues.append(f"downloaded_ticker_mismatch={observed_tickers[0]}")
        if ticker and downloaded_ticker_ids.get(ticker, 0) > 1:
            issues.append("downloaded_ticker_maps_to_multiple_security_ids")
        if prices.empty:
            issues.append("no_downloaded_data")
        rows.append({
            "security_id": security_id,
            "ticker": ticker,
            "yahoo_symbol": yahoo_symbol,
            "data_found": not prices.empty,
            "first_date": prices["date"].min() if not prices.empty else pd.NaT,
            "last_date": prices["date"].max() if not prices.empty else pd.NaT,
            "issues": "; ".join(dict.fromkeys(issues)),
        })

    for unexpected_id in sorted(observed_ids - master_ids):
        prices = daily_prices.loc[daily_prices["security_id"].astype(str).eq(unexpected_id)]
        tickers = sorted(prices["ticker"].dropna().map(_clean_string).unique())
        rows.append({
            "security_id": unexpected_id,
            "ticker": "|".join(tickers),
            "yahoo_symbol": "",
            "data_found": True,
            "first_date": prices["date"].min(),
            "last_date": prices["date"].max(),
            "issues": "downloaded_security_not_in_master",
        })
    missing_security_ids = int(daily_prices["security_id"].map(_clean_string).eq("").sum())
    if missing_security_ids:
        rows.append({
            "security_id": "",
            "ticker": "",
            "yahoo_symbol": "",
            "data_found": True,
            "first_date": pd.NaT,
            "last_date": pd.NaT,
            "issues": f"downloaded_rows_missing_security_id={missing_security_ids}",
        })
    return pd.DataFrame(rows, columns=MAPPING_AUDIT_COLUMNS)


def build_historical_coverage_audit(
    security_master: pd.DataFrame,
    daily_prices: pd.DataFrame,
    *,
    factor_model_min_history: int = 252,
    short_history_observations: int = 252,
    recent_ipo_years: float = 2.0,
) -> pd.DataFrame:
    """Report observed history; ``recent_ipo`` is a conservative listing-age proxy."""
    sample_end = pd.to_datetime(daily_prices["date"]).max()
    rows: list[dict[str, Any]] = []
    for security in security_master[["security_id", "ticker"]].itertuples(index=False):
        dates = pd.to_datetime(daily_prices.loc[
            daily_prices["security_id"].eq(security.security_id), "date"
        ]).dropna().sort_values()
        count = len(dates)
        first = dates.iloc[0] if count else pd.NaT
        last = dates.iloc[-1] if count else pd.NaT
        years = (last - first).days / 365.25 if count else 0.0
        insufficient = count < factor_model_min_history
        short = count < short_history_observations
        recent = bool(
            count and pd.notna(sample_end)
            and (sample_end - first).days < recent_ipo_years * 365.25
        )
        issues: list[str] = []
        if not count:
            issues.append("no_data")
        if insufficient:
            issues.append("insufficient_history_for_factor_models")
        if short:
            issues.append("short_history_company")
        if recent:
            issues.append("recent_ipo_proxy")
        rows.append({
            "security_id": security.security_id,
            "ticker": security.ticker,
            "first_trading_date": first,
            "last_trading_date": last,
            "number_of_observations": count,
            "years_covered": round(years, 3),
            "insufficient_history_for_factor_models": insufficient,
            "short_history_company": short,
            "recent_ipo": recent,
            "issues": "; ".join(issues),
        })
    return pd.DataFrame(rows, columns=COVERAGE_AUDIT_COLUMNS)


def build_trading_calendar_audits(
    security_master: pd.DataFrame, daily_prices: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare each listing with empirical local-exchange session unions.

    No dates are inserted.  Weekdays on which no security from an exchange has
    data are reported as local holidays/closures/data gaps, not assumed missing.
    """
    master = security_master[["security_id", "ticker", "exchange"]].copy()
    labelled = daily_prices[["security_id", "date"]].merge(
        master, on="security_id", how="left", validate="many_to_one"
    )
    labelled["date"] = pd.to_datetime(labelled["date"])
    global_first = labelled["date"].min()
    global_last = labelled["date"].max()
    local_sessions = {
        exchange: pd.DatetimeIndex(group["date"].dropna().unique()).sort_values()
        for exchange, group in labelled.groupby("exchange", dropna=False)
    }
    security_rows: list[dict[str, Any]] = []
    for security in master.itertuples(index=False):
        dates = pd.DatetimeIndex(labelled.loc[
            labelled["security_id"].eq(security.security_id), "date"
        ].dropna().unique()).sort_values()
        local = local_sessions.get(security.exchange, pd.DatetimeIndex([]))
        if len(dates):
            relevant_local = local[(local >= dates.min()) & (local <= dates.max())]
            missing_local = relevant_local.difference(dates)
            gaps = pd.Series(dates).diff().dt.days.dropna()
            non_overlap_start = max((dates.min() - global_first).days, 0)
            non_overlap_end = max((global_last - dates.max()).days, 0)
        else:
            missing_local = local
            gaps = pd.Series(dtype=float)
            non_overlap_start = non_overlap_end = np.nan
        issues: list[str] = []
        if len(missing_local):
            issues.append(f"missing_local_exchange_dates={len(missing_local)}")
        if pd.notna(non_overlap_start) and non_overlap_start:
            issues.append(f"non_overlap_start_calendar_days={non_overlap_start}")
        if pd.notna(non_overlap_end) and non_overlap_end:
            issues.append(f"non_overlap_end_calendar_days={non_overlap_end}")
        security_rows.append({
            "security_id": security.security_id,
            "ticker": security.ticker,
            "exchange": security.exchange,
            "first_trading_date": dates.min() if len(dates) else pd.NaT,
            "last_trading_date": dates.max() if len(dates) else pd.NaT,
            "observed_sessions": len(dates),
            "local_exchange_sessions_in_observed_period": len(dates) + len(missing_local),
            "missing_local_exchange_dates": len(missing_local),
            "max_calendar_gap_days": int(gaps.max()) if len(gaps) else 0,
            "non_overlap_start_calendar_days": non_overlap_start,
            "non_overlap_end_calendar_days": non_overlap_end,
            "issues": "; ".join(issues),
        })

    exchange_rows: list[dict[str, Any]] = []
    for exchange, sessions in sorted(local_sessions.items(), key=lambda item: str(item[0])):
        if len(sessions):
            weekdays = pd.bdate_range(sessions.min(), sessions.max())
            absent_weekdays = weekdays.difference(sessions)
            start_gap = max((sessions.min() - global_first).days, 0)
            end_gap = max((global_last - sessions.max()).days, 0)
        else:
            absent_weekdays = pd.DatetimeIndex([])
            start_gap = end_gap = np.nan
        exchange_rows.append({
            "exchange": exchange,
            "number_of_securities": int(master["exchange"].eq(exchange).sum()),
            "first_observed_session": sessions.min() if len(sessions) else pd.NaT,
            "last_observed_session": sessions.max() if len(sessions) else pd.NaT,
            "observed_exchange_sessions": len(sessions),
            "weekdays_without_observed_exchange_session": len(absent_weekdays),
            "non_overlap_start_calendar_days": start_gap,
            "non_overlap_end_calendar_days": end_gap,
        })
    return pd.DataFrame(security_rows), pd.DataFrame(exchange_rows)


def build_return_quality_report(
    security_master: pd.DataFrame,
    daily_prices: pd.DataFrame,
    *,
    extreme_return_threshold: float = 0.50,
) -> pd.DataFrame:
    """Audit adjusted-close simple returns without deleting or winsorizing rows."""
    returns = calculate_daily_returns(daily_prices)
    rows: list[dict[str, Any]] = []
    for security in security_master[["security_id", "ticker"]].itertuples(index=False):
        prices = daily_prices.loc[
            daily_prices["security_id"].eq(security.security_id)
        ].sort_values("date", kind="stable")
        security_returns = returns.loc[
            returns["security_id"].eq(security.security_id)
        ].sort_values("date", kind="stable")
        values = security_returns["return"]
        extreme_mask = values.abs().gt(extreme_return_threshold)
        impossible_mask = values.le(-1.0) | ~np.isfinite(values.fillna(0.0))
        adjusted = pd.to_numeric(prices["adj_close"], errors="coerce")
        volume = pd.to_numeric(prices["volume"], errors="coerce")
        duplicate_dates = int(prices.duplicated("date", keep=False).sum())
        missing_returns = int(values.isna().sum())
        expected_first_missing = 1 if len(values) else 0
        missing_after_first = max(missing_returns - expected_first_missing, 0)
        counts = {
            "duplicate_dates": duplicate_dates,
            "extreme_daily_returns": int(extreme_mask.sum()),
            "impossible_returns": int(impossible_mask.sum()),
            "missing_adj_close": int(adjusted.isna().sum()),
            "non_finite_adj_close": int((~np.isfinite(adjusted.fillna(0.0))).sum()),
            "non_positive_adj_close": int(adjusted.le(0).sum()),
            "negative_volume": int(volume.lt(0).sum()),
        }
        issues = [f"{name}={count}" for name, count in counts.items() if count]
        if missing_after_first:
            issues.append(f"missing_returns_after_first={missing_after_first}")
        extreme_dates = security_returns.loc[extreme_mask, "date"].dt.strftime(
            "%Y-%m-%d"
        ).tolist()
        rows.append({
            "security_id": security.security_id,
            "ticker": security.ticker,
            "number_of_observations": len(prices),
            "missing_returns": missing_returns,
            "missing_returns_after_first": missing_after_first,
            **counts,
            "max_abs_return": values.abs().max(),
            "extreme_return_dates": "|".join(extreme_dates),
            "issues": "; ".join(issues),
        })
    return pd.DataFrame(rows, columns=RETURN_QUALITY_COLUMNS)


def build_historical_eligibility(
    eligibility_input: pd.DataFrame,
    integrated_security_master: pd.DataFrame,
    baseline_parameters: UniverseParameters,
    extension_parameters: UniverseParameters,
) -> pd.DataFrame:
    """Generate versioned baseline and extension membership histories."""
    if extension_parameters.universe_version != baseline_parameters.universe_version:
        raise ValueError("baseline and extension must use the same universe_version")
    if (
        extension_parameters.eligibility_start_date
        != baseline_parameters.eligibility_start_date
        or extension_parameters.eligibility_end_date
        != baseline_parameters.eligibility_end_date
    ):
        raise ValueError("baseline and extension must use the same eligibility dates")
    baseline = build_approved_universe_membership(
        integrated_security_master, eligibility_input, baseline_parameters
    ).rename(columns={"exclusion_reason": "reason"})
    extension = build_approved_universe_membership(
        integrated_security_master, eligibility_input, extension_parameters
    ).rename(columns={
        "eligible": "extension_eligible",
        "exclusion_reason": "extension_reason",
    })
    output = baseline.merge(
        extension,
        on=["date", "security_id"],
        how="inner",
        validate="one_to_one",
    )
    output.insert(2, "universe_version", baseline_parameters.universe_version)
    start = baseline_parameters.eligibility_start_date
    end = baseline_parameters.eligibility_end_date
    if start is not None:
        output = output.loc[output["date"].ge(start)]
    if end is not None:
        output = output.loc[output["date"].le(end)]
    return output[list(HISTORICAL_ELIGIBILITY_COLUMNS)].reset_index(drop=True)


def assemble_daily_panel(
    daily_prices: pd.DataFrame,
    integrated_security_master: pd.DataFrame,
    universe_parameters: UniverseParameters | dict[str, Any],
    *,
    extension_parameters: UniverseParameters | None = None,
    extreme_return_threshold: float = 0.50,
) -> pd.DataFrame:
    """Assemble versioned baseline/extension eligibility and quality flags."""
    required = {
        "date", "security_id", "ticker", "adj_close", "close", "volume"
    }
    missing = sorted(required.difference(daily_prices.columns))
    if missing:
        raise ValueError("daily prices are missing: " + ", ".join(missing))
    duplicate_mask = daily_prices.duplicated(["security_id", "date"], keep=False)
    if duplicate_mask.any():
        raise ValueError("daily prices contain duplicate security/date rows")

    prices = daily_prices.sort_values(
        ["security_id", "date"], kind="stable", ignore_index=True
    ).copy()
    calculated = calculate_daily_returns(prices)
    eligibility_input = prices.rename(columns={"adj_close": "adjusted_close"})[
        ["date", "security_id", "adjusted_close", "close", "volume"]
    ].copy()
    eligibility_input["return"] = calculated["return"].to_numpy()
    baseline_parameters = (
        UniverseParameters.from_mapping(universe_parameters)
        if isinstance(universe_parameters, dict)
        else universe_parameters
    )
    if not isinstance(baseline_parameters, UniverseParameters):
        raise TypeError("universe_parameters must define UniverseParameters")
    extension_parameters = extension_parameters or baseline_parameters
    membership = build_historical_eligibility(
        eligibility_input,
        integrated_security_master,
        baseline_parameters,
        extension_parameters,
    )
    observed_membership = membership[
        ["date", "security_id", "eligible", "extension_eligible"]
    ]
    labels = integrated_security_master[
        ["security_id", "ticker", "subsector", "universe_tier"]
    ]
    output = (
        prices[["date", "security_id", "ticker", "adj_close", "volume"]]
        .merge(labels, on=["security_id", "ticker"], how="left", validate="many_to_one")
        .merge(
            observed_membership, on=["date", "security_id"], how="left",
            validate="one_to_one",
        )
    )
    output["return"] = calculated["return"].to_numpy()
    outside_window = output["eligible"].isna()
    output.loc[outside_window, ["eligible", "extension_eligible"]] = False
    output["universe_version"] = baseline_parameters.universe_version
    output["extreme_return_flag"] = output["return"].abs().gt(
        extreme_return_threshold
    )
    if output[["subsector", "universe_tier"]].isna().any().any():
        raise ValueError("daily panel assembly produced unmapped metadata")
    output = output[list(DAILY_PANEL_COLUMNS)].sort_values(
        ["date", "security_id"], kind="stable", ignore_index=True
    )
    output[["eligible", "extension_eligible", "extreme_return_flag"]] = output[[
        "eligible", "extension_eligible", "extreme_return_flag"
    ]].astype(bool)
    return output


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def run_stage11d(
    *,
    yahoo_security_master_path: str | Path = PROJECT_ROOT / "metadata" / "security_master.csv",
    integrated_security_master_path: str | Path = PROJECT_ROOT / "data" / "processed" / "security_master.csv",
    daily_prices_path: str | Path = PROJECT_ROOT / "data" / "interim" / "daily_prices.parquet",
    config_path: str | Path = PROJECT_ROOT / "configs" / "final_baseline.yaml",
    diagnostics_dir: str | Path = OUTPUTS_DIR / "diagnostics",
    output_path: str | Path = PROJECT_ROOT / "data" / "processed" / "daily_panel.parquet",
    historical_eligibility_path: str | Path = PROJECT_ROOT / "data" / "processed" / "universe_membership.csv",
    universe_manifest_path: str | Path = OUTPUTS_DIR / "manifests" / "universe_manifest.json",
) -> Stage11DArtifacts:
    """Run the complete deterministic Stage 11D audit and assembly."""
    yahoo_master = pd.read_csv(yahoo_security_master_path, dtype=str, keep_default_na=False)
    integrated_master = pd.read_csv(
        integrated_security_master_path, dtype=str, keep_default_na=False
    )
    prices = pd.read_parquet(daily_prices_path)
    prices["date"] = pd.to_datetime(prices["date"])
    with Path(config_path).open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    parameters = UniverseParameters.from_mapping(config)
    extension_history = int(
        config.get("universe", {}).get("extension_minimum_trading_history", 60)
    )
    extension_parameters = replace(
        parameters,
        min_history_days=extension_history,
        allowed_universe_tiers=("core", "extension"),
    )
    checks = config.get("universe", {}).get("coverage_checks", {})

    mapping = build_security_mapping_audit(yahoo_master, prices)
    coverage = build_historical_coverage_audit(
        yahoo_master,
        prices,
        factor_model_min_history=int(checks.get("factor_model_min_history", 252)),
        short_history_observations=int(checks.get("short_public_history_days", 252)),
    )
    calendar, exchange_calendar = build_trading_calendar_audits(yahoo_master, prices)
    returns = build_return_quality_report(yahoo_master, prices)
    panel = assemble_daily_panel(
        prices,
        integrated_master,
        parameters,
        extension_parameters=extension_parameters,
    )
    eligibility_input = prices.rename(columns={"adj_close": "adjusted_close"})[
        ["date", "security_id", "adjusted_close", "close", "volume"]
    ].sort_values(["security_id", "date"], kind="stable", ignore_index=True)
    eligibility_input["return"] = calculate_daily_returns(prices.sort_values(
        ["security_id", "date"], kind="stable", ignore_index=True
    ))["return"].to_numpy()
    historical_eligibility = build_historical_eligibility(
        eligibility_input,
        integrated_master,
        parameters,
        extension_parameters,
    )

    diagnostics = Path(diagnostics_dir)
    diagnostics.mkdir(parents=True, exist_ok=True)
    paths = {
        "mapping": diagnostics / "security_mapping_audit.csv",
        "coverage": diagnostics / "historical_coverage_audit.csv",
        "calendar": diagnostics / "trading_calendar_audit.csv",
        "exchange_calendar": diagnostics / "exchange_calendar_summary.csv",
        "returns": diagnostics / "return_quality_report.csv",
    }
    mapping.to_csv(paths["mapping"], index=False)
    coverage.to_csv(paths["coverage"], index=False)
    calendar.to_csv(paths["calendar"], index=False)
    exchange_calendar.to_csv(paths["exchange_calendar"], index=False)
    returns.to_csv(paths["returns"], index=False)
    panel_path = Path(output_path)
    _atomic_parquet(panel, panel_path)
    membership_path = Path(historical_eligibility_path)
    membership_path.parent.mkdir(parents=True, exist_ok=True)
    historical_eligibility.to_csv(membership_path, index=False)
    manifest_path = Path(universe_manifest_path)
    manifest = create_universe_manifest(
        PROJECT_ROOT / "metadata" / "semiconductor_classification.csv",
        integrated_master,
        historical_eligibility,
        config["universe"],
    )
    manifest["number_extension_eligible"] = int(
        historical_eligibility.loc[
            historical_eligibility["date"].eq(historical_eligibility["date"].max()),
            "extension_eligible",
        ].sum()
    )
    write_universe_manifest(manifest, manifest_path)
    return Stage11DArtifacts(
        security_mapping_audit=mapping,
        historical_coverage_audit=coverage,
        trading_calendar_audit=calendar,
        exchange_calendar_summary=exchange_calendar,
        return_quality_report=returns,
        historical_eligibility=historical_eligibility,
        daily_panel=panel,
        security_mapping_audit_path=paths["mapping"],
        historical_coverage_audit_path=paths["coverage"],
        trading_calendar_audit_path=paths["calendar"],
        exchange_calendar_summary_path=paths["exchange_calendar"],
        return_quality_report_path=paths["returns"],
        historical_eligibility_path=membership_path,
        daily_panel_path=panel_path,
        universe_manifest_path=manifest_path,
    )


if __name__ == "__main__":  # pragma: no cover - exercised as a pipeline command
    run_stage11d()
