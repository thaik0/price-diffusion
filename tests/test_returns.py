import numpy as np
import pandas as pd
import pytest

from price_diffusion.returns import (
    build_relative_returns,
    calculate_abnormal_returns,
    calculate_peer_portfolio_returns,
    calculate_relative_abnormal_returns,
    estimate_trailing_factor_residuals,
)
from price_diffusion.validation import DataValidationError


@pytest.fixture
def example_returns() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 3 + ["2024-01-03"] * 3),
            "security_id": ["STOCK", "PEER_A", "PEER_B"] * 2,
            "return": [0.08, 0.01, 0.03, 0.05, 0.04, 0.06],
        }
    )


@pytest.fixture
def example_peers() -> pd.DataFrame:
    rows = []
    securities = ["STOCK", "PEER_A", "PEER_B"]
    for date in pd.to_datetime(["2024-01-02", "2024-01-03"]):
        for security_id in securities:
            peers = [peer for peer in securities if peer != security_id]
            for peer_id in peers:
                rows.append(
                    {
                        "date": date,
                        "security_id": security_id,
                        "peer_id": peer_id,
                        "peer_definition": "economic",
                        "weight": 0.5,
                    }
                )
    return pd.DataFrame(rows)


def test_manual_peer_relative_example_is_six_percent(
    example_returns: pd.DataFrame, example_peers: pd.DataFrame
) -> None:
    market = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02", "2024-01-03"]), "mkt": [0.0, 0.05]}
    )
    semiconductor = market.rename(columns={"mkt": "semi"})

    result = build_relative_returns(
        example_returns,
        example_peers,
        market,
        semiconductor,
        market_return_column="mkt",
        semiconductor_return_column="semi",
    )
    stock = result.loc[
        result["date"].eq(pd.Timestamp("2024-01-02"))
        & result["security_id"].eq("STOCK")
    ].iloc[0]

    assert stock["peer_return"] == pytest.approx(0.02)
    assert stock["relative_return"] == pytest.approx(0.06)


def test_market_adjusted_manual_example_is_zero(example_returns: pd.DataFrame) -> None:
    market = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02", "2024-01-03"]), "market": [0.01, 0.05]}
    )
    result = calculate_abnormal_returns(
        example_returns,
        market,
        factor_return_column="market",
        output_column="market_adjusted_return",
    )
    value = result.loc[
        result["date"].eq(pd.Timestamp("2024-01-03"))
        & result["security_id"].eq("STOCK"),
        "market_adjusted_return",
    ].item()

    assert value == pytest.approx(0.0)


def test_peer_portfolio_is_leave_one_out_and_weights_are_checked(
    example_returns: pd.DataFrame, example_peers: pd.DataFrame
) -> None:
    self_peer = example_peers.copy()
    self_peer.loc[0, "peer_id"] = self_peer.loc[0, "security_id"]
    with pytest.raises(DataValidationError, match="self_peer"):
        calculate_peer_portfolio_returns(example_returns, self_peer)

    bad_weights = example_peers.copy()
    bad_weights.loc[0, "weight"] = 0.25
    with pytest.raises(DataValidationError, match="invalid_weight_sum"):
        calculate_peer_portfolio_returns(example_returns, bad_weights)


def test_returns_join_on_date_not_row_position(
    example_returns: pd.DataFrame, example_peers: pd.DataFrame
) -> None:
    shuffled = example_returns.sample(frac=1.0, random_state=7).reset_index(drop=True)
    result = calculate_peer_portfolio_returns(shuffled, example_peers)
    stock_values = result.loc[result["security_id"].eq("STOCK")].set_index("date")

    assert stock_values.loc[pd.Timestamp("2024-01-02"), "peer_return"] == pytest.approx(0.02)
    assert stock_values.loc[pd.Timestamp("2024-01-03"), "peer_return"] == pytest.approx(0.05)


def test_missing_peer_observation_is_excluded_and_weights_renormalize(
    example_returns: pd.DataFrame, example_peers: pd.DataFrame
) -> None:
    missing_one = example_returns.loc[
        ~(
            example_returns["date"].eq(pd.Timestamp("2024-01-02"))
            & example_returns["security_id"].eq("PEER_B")
        )
    ]
    result = calculate_peer_portfolio_returns(missing_one, example_peers)
    stock = result.loc[
        result["date"].eq(pd.Timestamp("2024-01-02"))
        & result["security_id"].eq("STOCK")
    ].iloc[0]

    assert stock["peer_count"] == 1
    assert stock["peer_return"] == pytest.approx(0.01)

    no_peers = missing_one.loc[missing_one["security_id"].eq("STOCK")]
    no_peer_result = calculate_peer_portfolio_returns(no_peers, example_peers)
    value = no_peer_result.loc[
        no_peer_result["date"].eq(pd.Timestamp("2024-01-02"))
        & no_peer_result["security_id"].eq("STOCK"),
        "peer_return",
    ].item()
    assert np.isnan(value)


def test_relative_abnormal_return_matches_manual_calculation(
    example_returns: pd.DataFrame, example_peers: pd.DataFrame
) -> None:
    abnormal = example_returns.rename(columns={"return": "abnormal"})
    result = calculate_relative_abnormal_returns(
        abnormal, example_peers, abnormal_return_column="abnormal"
    )
    stock = result.loc[
        result["date"].eq(pd.Timestamp("2024-01-02"))
        & result["security_id"].eq("STOCK")
    ].iloc[0]

    assert stock["stock_abnormal_return"] == pytest.approx(0.08)
    assert stock["peer_abnormal_return"] == pytest.approx(0.02)
    assert stock["relative_abnormal_return"] == pytest.approx(0.06)


def test_factor_estimation_uses_strictly_trailing_window() -> None:
    dates = pd.date_range("2024-01-01", periods=7, freq="D")
    factor = np.arange(7, dtype=float) / 100.0
    stocks = pd.DataFrame(
        {"date": dates, "security_id": "STOCK", "return": 0.01 + 2.0 * factor}
    )
    factors = pd.DataFrame({"date": dates, "market": factor})

    baseline = estimate_trailing_factor_residuals(
        stocks,
        factors,
        factor_columns=["market"],
        estimation_window=3,
        min_observations=3,
    )
    parameters = baseline.model_parameters

    assert (parameters["estimation_end"] < parameters["date"]).all()
    assert (parameters["observation_count"] == 3).all()
    assert np.allclose(parameters["intercept"], 0.01)
    assert np.allclose(parameters["beta_market"], 2.0)
    assert np.allclose(
        baseline.residual_returns["factor_residual_return"].dropna(), 0.0, atol=1e-12
    )

    changed_future = stocks.copy()
    changed_future.loc[changed_future["date"].eq(dates[-1]), "return"] = 99.0
    changed = estimate_trailing_factor_residuals(
        changed_future,
        factors,
        factor_columns=["market"],
        estimation_window=3,
        min_observations=3,
    )
    cutoff = dates[-2]
    pd.testing.assert_frame_equal(
        baseline.model_parameters.loc[baseline.model_parameters["date"].le(cutoff)].reset_index(drop=True),
        changed.model_parameters.loc[changed.model_parameters["date"].le(cutoff)].reset_index(drop=True),
    )

    changed_current = stocks.copy()
    prediction_date = dates[-2]
    changed_current.loc[changed_current["date"].eq(prediction_date), "return"] = 50.0
    current_result = estimate_trailing_factor_residuals(
        changed_current,
        factors,
        factor_columns=["market"],
        estimation_window=3,
        min_observations=3,
    )
    expected_parameters = baseline.model_parameters.loc[
        baseline.model_parameters["date"].eq(prediction_date)
    ].reset_index(drop=True)
    actual_parameters = current_result.model_parameters.loc[
        current_result.model_parameters["date"].eq(prediction_date)
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(expected_parameters, actual_parameters)


def test_missing_factor_date_produces_missing_adjusted_return(
    example_returns: pd.DataFrame,
) -> None:
    market = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-03"]), "return": [0.05]}
    )
    result = calculate_abnormal_returns(example_returns, market)

    assert result.loc[
        result["date"].eq(pd.Timestamp("2024-01-02")), "abnormal_return"
    ].isna().all()
