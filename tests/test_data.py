from pathlib import Path

import pandas as pd
import pytest

from price_diffusion.data import (
    DAILY_PRICE_COLUMNS,
    build_data_audit,
    calculate_daily_returns,
    combine_daily_prices,
    load_security_master,
    standardize_yahoo_download,
    write_raw_download,
)


def _security_master() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "security_id": "SEC_NVDA",
                "ticker": "NVDA",
                "yahoo_symbol": "NVDA",
                "company_name": "NVIDIA Corporation",
                "exchange": "Nasdaq",
                "currency": "USD",
            },
            {
                "security_id": "SEC_8035_T",
                "ticker": "8035.T",
                "yahoo_symbol": "8035.T",
                "company_name": "Tokyo Electron Limited",
                "exchange": "Tokyo Stock Exchange",
                "currency": "JPY",
            },
        ]
    )


def _raw_yahoo_frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "Open": [100.0, 105.0, 110.0],
            "High": [102.0, 108.0, 112.0],
            "Low": [99.0, 104.0, 109.0],
            "Close": [101.0, 107.0, 111.0],
            "Adj Close": [100.0, 110.0, 99.0],
            "Volume": [1_000, 0, 1_200],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-10"]),
    )
    frame.index.name = "Date"
    return frame


def test_symbol_mapping_loads_correctly(tmp_path: Path) -> None:
    path = tmp_path / "security_master.csv"
    _security_master().to_csv(path, index=False)

    loaded = load_security_master(path)

    assert list(loaded.columns) == [
        "security_id",
        "ticker",
        "yahoo_symbol",
        "company_name",
        "exchange",
        "currency",
    ]
    assert loaded.set_index("security_id").loc["SEC_8035_T", "yahoo_symbol"] == "8035.T"


def test_downloaded_data_is_standardized_with_required_columns() -> None:
    prices = standardize_yahoo_download(
        _raw_yahoo_frame(), security_id="SEC_NVDA", ticker="NVDA"
    )

    assert list(prices.columns) == list(DAILY_PRICE_COLUMNS)
    assert prices["adj_close"].notna().all()
    assert prices["security_id"].eq("SEC_NVDA").all()


def test_empty_vendor_placeholders_are_dropped_but_partial_rows_are_audited() -> None:
    raw = _raw_yahoo_frame()
    raw.loc[pd.Timestamp("2024-01-06")] = [None, None, None, None, None, 0]
    raw.loc[pd.Timestamp("2024-01-08")] = [100, 101, 99, 100, None, 500]

    prices = standardize_yahoo_download(raw, security_id="SEC_NVDA", ticker="NVDA")
    audit = build_data_audit(_security_master(), prices)

    assert pd.Timestamp("2024-01-06") not in set(prices["date"])
    assert pd.Timestamp("2024-01-08") in set(prices["date"])
    assert "missing_adjusted_prices=1" in audit.loc[0, "issues"]


def test_combined_prices_have_no_duplicate_security_date_pairs() -> None:
    nvda = standardize_yahoo_download(
        _raw_yahoo_frame(), security_id="SEC_NVDA", ticker="NVDA"
    )
    tokyo_electron = standardize_yahoo_download(
        _raw_yahoo_frame(), security_id="SEC_8035_T", ticker="8035.T"
    )

    combined = combine_daily_prices([tokyo_electron, nvda])

    assert not combined.duplicated(["security_id", "date"]).any()
    with pytest.raises(ValueError, match="duplicate security/date"):
        combine_daily_prices([nvda, nvda])


def test_returns_use_adjusted_close_and_are_calculated_correctly() -> None:
    prices = standardize_yahoo_download(
        _raw_yahoo_frame(), security_id="SEC_NVDA", ticker="NVDA"
    )

    returns = calculate_daily_returns(prices)

    assert pd.isna(returns.loc[0, "return"])
    assert returns.loc[1, "return"] == pytest.approx(110.0 / 100.0 - 1.0)
    assert returns.loc[2, "return"] == pytest.approx(99.0 / 110.0 - 1.0)


def test_audit_detects_missing_days_large_gaps_and_zero_volume() -> None:
    prices = standardize_yahoo_download(
        _raw_yahoo_frame(), security_id="SEC_NVDA", ticker="NVDA"
    )

    audit = build_data_audit(_security_master(), prices)
    nvda = audit.set_index("security_id").loc["SEC_NVDA"]
    missing_security = audit.set_index("security_id").loc["SEC_8035_T"]

    assert nvda["missing_percentage"] > 0
    assert "missing_weekdays_or_holidays=" in nvda["issues"]
    assert "zero_volume_days=1" in nvda["issues"]
    assert "large_gaps=1" in nvda["issues"]
    assert missing_security["observation_count"] == 0
    assert missing_security["issues"] == "no_data"


def test_raw_download_is_never_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "raw" / "SEC_NVDA__NVDA.csv"
    original = _raw_yahoo_frame()
    write_raw_download(original, target)
    first_contents = target.read_bytes()

    with pytest.raises(FileExistsError):
        write_raw_download(original.iloc[:1], target)

    assert target.read_bytes() == first_contents
