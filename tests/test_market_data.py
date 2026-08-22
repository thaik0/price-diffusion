from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from price_diffusion.market_data import (
    CSVMarketDataSource,
    build_daily_panel,
    ingest_market_data,
    load_market_data,
)
from price_diffusion.synthetic import (
    SyntheticResearchData,
    make_invalid_synthetic_raw_market_data,
    make_synthetic_raw_market_data,
)
from price_diffusion.validation import DataValidationError, validate_daily_panel


def _issue_codes(error: DataValidationError) -> set[str]:
    return {issue.code for issue in error.issues}


def _manual_raw_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2024-01-05",
                "ticker": "AMD",
                "adjusted_close": 55,
                "close": 55,
                "volume": 30,
            },
            {
                "date": "2024-01-02",
                "ticker": "NVDA",
                "adjusted_close": 100,
                "close": 101,
                "volume": 10,
            },
            {
                "date": "2024-01-08",
                "ticker": "NVDA",
                "adjusted_close": 108,
                "close": 109,
                "volume": 12,
            },
            {
                "date": "2024-01-02",
                "ticker": "AMD",
                "adjusted_close": 50,
                "close": 50,
                "volume": 20,
            },
            {
                "date": "2024-01-03",
                "ticker": "NVDA",
                "adjusted_close": 110,
                "close": 111,
                "volume": 11,
            },
        ]
    )


def test_build_daily_panel_maps_sorts_and_calculates_manual_returns(
    synthetic_data: SyntheticResearchData,
) -> None:
    panel = build_daily_panel(_manual_raw_data(), synthetic_data.security_master)

    assert panel[["security_id", "date"]].equals(
        panel[["security_id", "date"]].sort_values(
            ["security_id", "date"], ignore_index=True
        )
    )
    amd = panel.loc[panel["security_id"].eq("SEC_AMD")].reset_index(drop=True)
    nvda = panel.loc[panel["security_id"].eq("SEC_NVDA")].reset_index(drop=True)
    assert pd.isna(amd.loc[0, "return"])
    assert amd.loc[1, "return"] == pytest.approx(55 / 50 - 1)
    assert pd.isna(nvda.loc[0, "return"])
    assert nvda.loc[1, "return"] == pytest.approx(110 / 100 - 1)
    # The Jan 4-5 gap creates no artificial rows or zero returns.
    assert nvda.loc[2, "return"] == pytest.approx(108 / 110 - 1)
    assert len(nvda) == 3
    assert list(panel.columns) == [
        "date",
        "security_id",
        "adjusted_close",
        "close",
        "volume",
        "return",
    ]


def test_csv_source_supports_column_mapping_and_pipeline(
    tmp_path, synthetic_data: SyntheticResearchData
) -> None:
    csv_path = tmp_path / "vendor_prices.csv"
    _manual_raw_data().rename(
        columns={"ticker": "Symbol", "adjusted_close": "Adj Close"}
    ).to_csv(csv_path, index=False)
    source = CSVMarketDataSource(
        csv_path, column_map={"Symbol": "ticker", "Adj Close": "adjusted_close"}
    )

    loaded = load_market_data(source)
    panel = ingest_market_data(source, synthetic_data.security_master)

    assert {"ticker", "adjusted_close"} <= set(loaded.columns)
    assert len(panel) == len(loaded)


@dataclass
class InMemorySource:
    frame: pd.DataFrame

    def load(self) -> pd.DataFrame:
        return self.frame


def test_source_interface_is_not_csv_specific(
    synthetic_data: SyntheticResearchData,
) -> None:
    panel = ingest_market_data(
        InMemorySource(_manual_raw_data()), synthetic_data.security_master
    )
    assert len(panel) == 5


def test_multi_year_synthetic_data_is_valid_and_contains_source_gaps(
    synthetic_data: SyntheticResearchData,
) -> None:
    raw = make_synthetic_raw_market_data()
    panel = build_daily_panel(raw, synthetic_data.security_master)

    assert panel["date"].dt.year.nunique() == 3
    assert panel["security_id"].nunique() == 3
    counts = panel.groupby("security_id").size()
    assert counts.nunique() > 1
    validate_daily_panel(panel, synthetic_data.security_master)


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("negative_price", "non_positive_price"),
        ("negative_volume", "negative_volume"),
        ("malformed_date", "malformed_date"),
        ("duplicate", "duplicate_primary_key"),
        ("missing_value", "null_values"),
        ("unknown_security", "invalid_security_reference"),
    ],
)
def test_invalid_raw_market_data_fails(
    case: str, expected_code: str, synthetic_data: SyntheticResearchData
) -> None:
    with pytest.raises(DataValidationError) as caught:
        build_daily_panel(
            make_invalid_synthetic_raw_market_data(case),
            synthetic_data.security_master,
        )

    assert expected_code in _issue_codes(caught.value)


@pytest.mark.parametrize("bad_return", [0.25, -1.0, np.nan])
def test_validator_rejects_returns_inconsistent_with_adjusted_prices(
    bad_return: float, synthetic_data: SyntheticResearchData
) -> None:
    invalid = synthetic_data.daily_panel.copy()
    second_nvda = invalid.index[invalid["security_id"].eq("SEC_NVDA")][1]
    invalid.loc[second_nvda, "return"] = bad_return

    with pytest.raises(DataValidationError) as caught:
        validate_daily_panel(invalid, synthetic_data.security_master)

    assert "invalid_return" in _issue_codes(caught.value)


def test_validator_rejects_return_on_first_security_observation(
    synthetic_data: SyntheticResearchData,
) -> None:
    invalid = synthetic_data.daily_panel.copy()
    invalid.loc[invalid.index[0], "return"] = 0.0

    with pytest.raises(DataValidationError) as caught:
        validate_daily_panel(invalid, synthetic_data.security_master)

    assert "invalid_return" in _issue_codes(caught.value)
