import pandas as pd
import pytest
import yaml
from pathlib import Path

from price_diffusion.synthetic import make_synthetic_universe_data
from price_diffusion.universe import (
    APPROVED_SUBSECTORS,
    UniverseParameters,
    build_approved_universe_membership,
    build_security_master,
    build_universe_membership,
    create_universe_manifest,
    historical_coverage,
    load_semiconductor_metadata,
    universe_diagnostics,
    validate_classification_metadata,
)
from price_diffusion.validation import DataValidationError, validate_universe_membership


PROJECT_ROOT = Path(__file__).parents[1]


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


def _metadata() -> pd.DataFrame:
    return load_semiconductor_metadata(
        PROJECT_ROOT / "metadata" / "semiconductor_classification.csv"
    )


def test_reviewed_metadata_builds_complete_security_master() -> None:
    metadata = _metadata()
    master = build_security_master(metadata)

    assert len(master) == len(metadata) == 54
    assert set(metadata["subsector"]) == APPROVED_SUBSECTORS
    assert not master["security_id"].duplicated().any()
    assert master.loc[master["ticker"].eq("NVDA"), "security_id"].item() == "SEC_NVDA"
    for column in (
        "security_id", "ticker", "company_name", "exchange_or_market",
        "subsector", "semiconductor_role", "universe_tier", "review_flag",
    ):
        assert column in master


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda frame: frame.drop(columns="semiconductor_role"), "missing_columns"),
        (lambda frame: pd.concat([frame, frame.iloc[[0]]]), "duplicate_security"),
        (lambda frame: frame.assign(subsector="not_a_subsector"), "invalid_subsector"),
        (lambda frame: frame.assign(universe_tier="invalid"), "invalid_universe_tier"),
        (lambda frame: frame.assign(semiconductor_role=""), "missing_classification"),
    ],
)
def test_metadata_validation_fails_closed(mutation, code: str) -> None:
    with pytest.raises(DataValidationError) as caught:
        validate_classification_metadata(mutation(_metadata()))

    assert code in {issue.code for issue in caught.value.issues}


def test_integrated_eligibility_respects_tier_and_trailing_information() -> None:
    metadata = _metadata().iloc[:2].copy()
    metadata.loc[metadata.index[0], "universe_tier"] = "core"
    metadata.loc[metadata.index[1], "universe_tier"] = "extension"
    master = build_security_master(metadata)
    dates = pd.bdate_range("2026-08-24", periods=3)
    rows = []
    for security_id in master["security_id"]:
        for position, date in enumerate(dates):
            price = 10.0 + position
            rows.append({
                "date": date,
                "security_id": security_id,
                "adjusted_close": price,
                "close": price,
                "volume": 1_000.0,
                "return": None if position == 0 else price / (price - 1.0) - 1.0,
            })
    panel = pd.DataFrame(rows)
    parameters = {
        "minimum_trading_history": 2,
        "minimum_price": 5.0,
        "liquidity": {
            "minimum_average_dollar_volume": 1_000.0,
            "trailing_window_days": 2,
        },
        "allowed_universe_tiers": ["core"],
        "listing_restrictions": {
            "allowed_exchange_or_markets": master["exchange_or_market"].tolist()
        },
        "adr_handling": {"allow": True},
        "classification_as_of_date": "2026-08-22",
    }
    membership = build_approved_universe_membership(master, panel, parameters)
    core_id = master.loc[master["universe_tier"].eq("core"), "security_id"].item()
    extension_id = master.loc[
        master["universe_tier"].eq("extension"), "security_id"
    ].item()

    assert not _row(membership, str(dates[0].date()), core_id)["eligible"]
    assert _row(membership, str(dates[1].date()), core_id)["eligible"]
    assert "universe_tier_not_allowed" in _row(
        membership, str(dates[2].date()), extension_id
    )["exclusion_reason"]

    changed = panel.copy()
    changed.loc[changed["date"].eq(dates[2]), "volume"] = 0.0
    rebuilt = build_approved_universe_membership(master, changed, parameters)
    pd.testing.assert_frame_equal(
        membership.loc[membership["date"].lt(dates[2])].reset_index(drop=True),
        rebuilt.loc[rebuilt["date"].lt(dates[2])].reset_index(drop=True),
    )


def test_diagnostics_coverage_manifest_and_generation_are_deterministic(tmp_path) -> None:
    metadata_path = PROJECT_ROOT / "metadata" / "semiconductor_classification.csv"
    metadata = _metadata()
    master = build_security_master(metadata)
    empty_panel = pd.DataFrame({
        "date": pd.Series(dtype="datetime64[ns]"),
        "security_id": pd.Series(dtype="object"),
        "adjusted_close": pd.Series(dtype="float64"),
        "close": pd.Series(dtype="float64"),
        "volume": pd.Series(dtype="float64"),
        "return": pd.Series(dtype="float64"),
    })
    with (PROJECT_ROOT / "configs" / "final_baseline.yaml").open() as stream:
        config = yaml.safe_load(stream)
    first = build_approved_universe_membership(master, empty_panel, config)
    second = build_approved_universe_membership(master, empty_panel, config)
    pd.testing.assert_frame_equal(first, second)

    coverage = historical_coverage(
        master,
        empty_panel,
        factor_model_min_history=252,
        short_public_history_days=252,
        ticker_change_gap_days=30,
    )
    assert len(coverage) == 54
    assert coverage["insufficient_factor_model_history"].all()
    diagnostics = universe_diagnostics(master, first)
    assert diagnostics["overall"]["total_manually_classified"].item() == 54
    assert diagnostics["by_universe_tier"].set_index("universe_tier").loc["core", "classified"] == 36

    manifest_one = create_universe_manifest(
        metadata_path, master, first, config["universe"],
        creation_timestamp="2026-08-22T00:00:00+00:00",
    )
    manifest_two = create_universe_manifest(
        metadata_path, master, second, config["universe"],
        creation_timestamp="2026-08-22T00:00:00+00:00",
    )
    assert manifest_one == manifest_two
    assert manifest_one["number_of_securities"] == 54
