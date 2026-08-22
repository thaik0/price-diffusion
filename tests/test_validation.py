import pandas as pd
import pytest

from price_diffusion.synthetic import SyntheticResearchData
from price_diffusion.validation import (
    DataValidationError,
    validate_daily_panel,
    validate_peer_membership,
    validate_research_data,
    validate_security_master,
    validate_universe_membership,
)


def _issue_codes(error: DataValidationError) -> set[str]:
    return {issue.code for issue in error.issues}


def test_valid_synthetic_datasets_pass(synthetic_data: SyntheticResearchData) -> None:
    validate_research_data(
        security_master=synthetic_data.security_master,
        universe_membership=synthetic_data.universe_membership,
        daily_panel=synthetic_data.daily_panel,
        peer_membership=synthetic_data.peer_membership,
    )


def test_missing_required_column_fails(synthetic_data: SyntheticResearchData) -> None:
    invalid = synthetic_data.security_master.drop(columns="exchange")

    with pytest.raises(DataValidationError) as caught:
        validate_security_master(invalid)

    assert "missing_columns" in _issue_codes(caught.value)


def test_invalid_column_type_fails(synthetic_data: SyntheticResearchData) -> None:
    invalid = synthetic_data.daily_panel.assign(volume="not numeric")

    with pytest.raises(DataValidationError) as caught:
        validate_daily_panel(invalid, synthetic_data.security_master)

    assert "invalid_type" in _issue_codes(caught.value)


def test_string_dates_are_not_silently_coerced(
    synthetic_data: SyntheticResearchData,
) -> None:
    invalid = synthetic_data.universe_membership.assign(
        date=lambda frame: frame["date"].dt.strftime("%Y-%m-%d")
    )

    with pytest.raises(DataValidationError) as caught:
        validate_universe_membership(invalid, synthetic_data.security_master)

    assert "invalid_type" in _issue_codes(caught.value)


def test_intraday_timestamp_is_not_a_valid_research_date(
    synthetic_data: SyntheticResearchData,
) -> None:
    invalid = synthetic_data.daily_panel.copy()
    invalid.loc[0, "date"] = invalid.loc[0, "date"] + pd.Timedelta(hours=16)

    with pytest.raises(DataValidationError) as caught:
        validate_daily_panel(invalid, synthetic_data.security_master)

    assert "invalid_date" in _issue_codes(caught.value)


def test_duplicate_security_id_is_detected(
    synthetic_data: SyntheticResearchData,
) -> None:
    invalid = pd.concat(
        [synthetic_data.security_master, synthetic_data.security_master.iloc[[0]]],
        ignore_index=True,
    )

    with pytest.raises(DataValidationError) as caught:
        validate_security_master(invalid)

    assert "duplicate_primary_key" in _issue_codes(caught.value)


def test_duplicate_daily_observation_is_detected(
    synthetic_data: SyntheticResearchData,
) -> None:
    invalid = pd.concat(
        [synthetic_data.daily_panel, synthetic_data.daily_panel.iloc[[0]]],
        ignore_index=True,
    )

    with pytest.raises(DataValidationError) as caught:
        validate_daily_panel(invalid, synthetic_data.security_master)

    assert "duplicate_primary_key" in _issue_codes(caught.value)


@pytest.mark.parametrize(
    ("column", "value", "expected_code"),
    [
        ("close", 0.0, "non_positive_price"),
        ("adjusted_close", -1.0, "non_positive_price"),
        ("volume", -1, "negative_volume"),
    ],
)
def test_invalid_market_values_fail(
    synthetic_data: SyntheticResearchData,
    column: str,
    value: float,
    expected_code: str,
) -> None:
    invalid = synthetic_data.daily_panel.copy()
    invalid.loc[0, column] = value

    with pytest.raises(DataValidationError) as caught:
        validate_daily_panel(invalid, synthetic_data.security_master)

    assert expected_code in _issue_codes(caught.value)


def test_unknown_universe_security_is_detected(
    synthetic_data: SyntheticResearchData,
) -> None:
    invalid = synthetic_data.universe_membership.copy()
    invalid.loc[0, "security_id"] = "SEC_UNKNOWN"

    with pytest.raises(DataValidationError) as caught:
        validate_universe_membership(invalid, synthetic_data.security_master)

    assert "invalid_security_reference" in _issue_codes(caught.value)


def test_self_peer_relationship_is_detected(
    synthetic_data: SyntheticResearchData,
) -> None:
    invalid = synthetic_data.peer_membership.copy()
    invalid.loc[0, "peer_id"] = invalid.loc[0, "security_id"]

    with pytest.raises(DataValidationError) as caught:
        validate_peer_membership(invalid, synthetic_data.security_master)

    assert "self_peer" in _issue_codes(caught.value)


def test_incorrect_peer_weights_are_detected(
    synthetic_data: SyntheticResearchData,
) -> None:
    invalid = synthetic_data.peer_membership.copy()
    invalid.loc[0, "weight"] = 0.4

    with pytest.raises(DataValidationError) as caught:
        validate_peer_membership(invalid, synthetic_data.security_master)

    assert "invalid_weight_sum" in _issue_codes(caught.value)


@pytest.mark.parametrize("peer_id", [None, "SEC_UNKNOWN"])
def test_missing_or_unknown_peer_is_detected(
    synthetic_data: SyntheticResearchData, peer_id: str | None
) -> None:
    invalid = synthetic_data.peer_membership.copy()
    invalid.loc[0, "peer_id"] = peer_id

    with pytest.raises(DataValidationError) as caught:
        validate_peer_membership(invalid, synthetic_data.security_master)

    codes = _issue_codes(caught.value)
    assert codes & {"null_values", "invalid_security_reference"}

