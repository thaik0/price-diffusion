import pandas as pd

from price_diffusion.synthetic import make_synthetic_universe_data
from price_diffusion.universe import (
    UniverseParameters,
    build_universe_membership,
)
from price_diffusion.validation import validate_universe_membership


def _built() -> tuple[object, pd.DataFrame]:
    inputs = make_synthetic_universe_data()
    membership = build_universe_membership(
        inputs.security_master,
        inputs.daily_panel,
        inputs.semiconductor_classification,
        inputs.universe_parameters,
    )
    return inputs, membership


def _row(membership: pd.DataFrame, date: str, security_id: str) -> pd.Series:
    selected = membership.loc[
        membership["date"].eq(pd.Timestamp(date))
        & membership["security_id"].eq(security_id)
    ]
    assert len(selected) == 1
    return selected.iloc[0]


def test_unclassified_security_is_explicitly_excluded() -> None:
    _, membership = _built()

    retail = membership.loc[membership["security_id"].eq("SEC_RETAIL")]
    assert not retail["eligible"].any()
    assert retail["exclusion_reason"].str.contains(
        "missing_semiconductor_classification"
    ).all()


def test_history_and_unavailable_new_listing_are_recorded() -> None:
    _, membership = _built()

    assert "insufficient_history" in _row(
        membership, "2024-01-03", "SEC_VALID"
    )["exclusion_reason"]
    assert _row(membership, "2024-01-04", "SEC_VALID")["eligible"]
    assert "no_market_data" in _row(
        membership, "2024-01-02", "SEC_NEW"
    )["exclusion_reason"]
    assert "insufficient_history" in _row(
        membership, "2024-01-08", "SEC_NEW"
    )["exclusion_reason"]


def test_liquidity_filter_uses_trailing_dollar_volume() -> None:
    _, membership = _built()

    early = _row(membership, "2024-01-03", "SEC_ILLIQUID")
    mature = _row(membership, "2024-01-04", "SEC_ILLIQUID")
    assert "insufficient_liquidity_history" in early["exclusion_reason"]
    assert "below_minimum_liquidity" in mature["exclusion_reason"]
    assert not mature["eligible"]


def test_price_filter_records_its_reason() -> None:
    inputs = make_synthetic_universe_data()
    parameters = dict(inputs.universe_parameters)
    parameters["min_price"] = 22.1
    membership = build_universe_membership(
        inputs.security_master,
        inputs.daily_panel,
        inputs.semiconductor_classification,
        parameters,
    )

    row = _row(membership, "2024-01-04", "SEC_VALID")
    assert not row["eligible"]
    assert "below_minimum_price" in row["exclusion_reason"]


def test_future_observation_does_not_change_historical_membership() -> None:
    inputs, original = _built()
    panel = inputs.daily_panel.copy()
    prior = panel.loc[panel["security_id"].eq("SEC_VALID"), "adjusted_close"].iloc[-1]
    future_price = 500.0
    future = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2025-01-02"),
                "security_id": "SEC_VALID",
                "adjusted_close": future_price,
                "close": future_price,
                "volume": 10_000_000.0,
                "return": future_price / prior - 1.0,
            }
        ]
    )
    extended = build_universe_membership(
        inputs.security_master,
        pd.concat([panel, future], ignore_index=True),
        inputs.semiconductor_classification,
        inputs.universe_parameters,
    )

    historical = extended.loc[extended["date"].le(original["date"].max())]
    pd.testing.assert_frame_equal(original, historical.reset_index(drop=True))


def test_classification_snapshot_guard_is_fail_closed() -> None:
    inputs = make_synthetic_universe_data()
    guarded = dict(inputs.universe_parameters)
    guarded["classification_as_of_date"] = "2024-01-08"
    membership = build_universe_membership(
        inputs.security_master,
        inputs.daily_panel,
        inputs.semiconductor_classification,
        guarded,
    )

    row = _row(membership, "2024-01-05", "SEC_VALID")
    assert not row["eligible"]
    assert "classification_not_available_as_of_date" in row["exclusion_reason"]


def test_output_contract_and_adr_eligibility() -> None:
    inputs, membership = _built()
    parameters = UniverseParameters.from_mapping(inputs.universe_parameters)

    validate_universe_membership(membership, inputs.security_master)
    assert parameters.min_history_days == 3
    assert list(membership.columns) == [
        "date",
        "security_id",
        "eligible",
        "exclusion_reason",
    ]
    assert _row(membership, "2024-01-04", "SEC_ADR")["eligible"]
