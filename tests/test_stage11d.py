from pathlib import Path

import pandas as pd
import pytest

from price_diffusion.stage11d import (
    DAILY_PANEL_COLUMNS,
    assemble_daily_panel,
    build_historical_coverage_audit,
    build_return_quality_report,
    build_security_mapping_audit,
    build_trading_calendar_audits,
)
from price_diffusion.universe import (
    UniverseParameters,
    build_security_master,
    load_semiconductor_metadata,
)


PROJECT_ROOT = Path(__file__).parents[1]


def _yahoo_master() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "security_id": "SEC_A", "ticker": "A", "yahoo_symbol": "A",
            "company_name": "A Co", "exchange": "Nasdaq", "currency": "USD",
        },
        {
            "security_id": "SEC_B", "ticker": "B", "yahoo_symbol": "B.L",
            "company_name": "B Co", "exchange": "London", "currency": "GBP",
        },
    ])


def _prices() -> pd.DataFrame:
    rows = []
    for security_id, ticker, dates, prices in (
        ("SEC_A", "A", ["2024-01-02", "2024-01-03", "2024-01-05"], [10, 16, 8]),
        ("SEC_B", "B", ["2024-01-02", "2024-01-04"], [20, 21]),
    ):
        for date, price in zip(dates, prices, strict=True):
            rows.append({
                "date": pd.Timestamp(date), "security_id": security_id,
                "ticker": ticker, "open": price, "high": price, "low": price,
                "close": price, "adj_close": price, "volume": 1_000,
            })
    return pd.DataFrame(rows)


def test_mapping_audit_reports_missing_data_without_repairing_mapping() -> None:
    prices = _prices().loc[lambda frame: frame["security_id"].eq("SEC_A")]
    audit = build_security_mapping_audit(_yahoo_master(), prices).set_index("security_id")

    assert bool(audit.loc["SEC_A", "data_found"])
    assert not bool(audit.loc["SEC_B", "data_found"])
    assert audit.loc["SEC_B", "issues"] == "no_downloaded_data"


def test_coverage_and_return_audits_flag_short_and_extreme_history() -> None:
    coverage = build_historical_coverage_audit(
        _yahoo_master(), _prices(), factor_model_min_history=4,
        short_history_observations=3,
    ).set_index("security_id")
    quality = build_return_quality_report(_yahoo_master(), _prices()).set_index(
        "security_id"
    )

    assert bool(coverage.loc["SEC_A", "insufficient_history_for_factor_models"])
    assert bool(coverage.loc["SEC_B", "short_history_company"])
    assert quality.loc["SEC_A", "extreme_daily_returns"] == 1
    assert quality.loc["SEC_A", "missing_returns_after_first"] == 0
    assert quality.loc["SEC_A", "missing_returns"] == 1


def test_calendar_audit_uses_local_sessions_and_does_not_fill_dates() -> None:
    security_calendar, exchange_calendar = build_trading_calendar_audits(
        _yahoo_master(), _prices()
    )

    assert len(_prices()) == 5
    assert set(security_calendar["exchange"]) == {"Nasdaq", "London"}
    assert exchange_calendar["weekdays_without_observed_exchange_session"].sum() > 0


def test_panel_assembly_has_required_contract_and_preserves_rules() -> None:
    metadata = load_semiconductor_metadata(
        PROJECT_ROOT / "metadata" / "semiconductor_classification.csv"
    ).iloc[:1]
    master = build_security_master(metadata)
    ticker = master.iloc[0]["ticker"]
    security_id = master.iloc[0]["security_id"]
    dates = pd.bdate_range("2026-08-24", periods=3)
    prices = pd.DataFrame({
        "date": dates,
        "security_id": security_id,
        "ticker": ticker,
        "open": [10.0, 11.0, 12.0],
        "high": [10.0, 11.0, 12.0],
        "low": [10.0, 11.0, 12.0],
        "close": [10.0, 11.0, 12.0],
        "adj_close": [10.0, 11.0, 12.0],
        "volume": [1_000_000.0, 1_000_000.0, 1_000_000.0],
    })
    parameters = {
        "minimum_trading_history": 2,
        "minimum_price": 5.0,
        "liquidity": {
            "minimum_average_dollar_volume": 1_000.0,
            "trailing_window_days": 2,
        },
        "allowed_universe_tiers": [master.iloc[0]["universe_tier"]],
        "listing_restrictions": {
            "allowed_exchange_or_markets": [master.iloc[0]["exchange_or_market"]]
        },
        "adr_handling": {"allow": True},
        "classification_as_of_date": "2026-08-22",
    }

    panel = assemble_daily_panel(prices, master, parameters)

    assert list(panel.columns) == list(DAILY_PANEL_COLUMNS)
    assert pd.isna(panel.loc[0, "return"])
    assert panel.loc[1, "return"] == pytest.approx(0.1)
    assert bool(panel.loc[1, "eligible"])


def test_historical_baseline_extension_version_and_extreme_flag_are_separate() -> None:
    metadata = load_semiconductor_metadata(
        PROJECT_ROOT / "metadata" / "semiconductor_classification.csv"
    ).loc[lambda frame: frame["universe_tier"].eq("core")].iloc[:1]
    master = build_security_master(metadata)
    ticker = master.iloc[0]["ticker"]
    security_id = master.iloc[0]["security_id"]
    dates = pd.bdate_range("2024-01-02", periods=4)
    prices = pd.DataFrame({
        "date": dates,
        "security_id": security_id,
        "ticker": ticker,
        "open": [10.0, 11.0, 12.0, 24.0],
        "high": [10.0, 11.0, 12.0, 24.0],
        "low": [10.0, 11.0, 12.0, 24.0],
        "close": [10.0, 11.0, 12.0, 24.0],
        "adj_close": [10.0, 11.0, 12.0, 24.0],
        "volume": 1_000_000.0,
    })
    common = {
        "minimum_price": 5.0,
        "liquidity": {
            "minimum_average_dollar_volume": 1_000.0,
            "trailing_window_days": 2,
        },
        "allowed_universe_tiers": ["core"],
        "listing_restrictions": {
            "allowed_exchange_or_markets": [master.iloc[0]["exchange_or_market"]]
        },
        "adr_handling": {"allow": True},
        "universe_version": "test_universe_v1",
        "classification_snapshot_date": "2026-08-22",
        "apply_classification_historically": True,
        "eligibility": {"start_date": "2024-01-02", "end_date": "2024-12-31"},
    }
    baseline = UniverseParameters.from_mapping({**common, "minimum_trading_history": 3})
    extension = UniverseParameters.from_mapping({**common, "minimum_trading_history": 2})

    panel = assemble_daily_panel(
        prices, master, baseline, extension_parameters=extension
    )

    assert panel["universe_version"].eq("test_universe_v1").all()
    assert not bool(panel.loc[1, "eligible"])
    assert bool(panel.loc[1, "extension_eligible"])
    assert bool(panel.loc[2, "eligible"])
    assert bool(panel.loc[3, "extreme_return_flag"])
    assert len(panel) == len(prices)
