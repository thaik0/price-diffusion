import numpy as np
import pandas as pd
import pytest

from price_diffusion.event_study import (
    EventStudyConfig,
    build_event_panel,
    calculate_event_outcomes,
    descriptive_summary,
    event_diagnostics,
    run_event_study,
)
from price_diffusion.validation import (
    DataValidationError,
    validate_event_outcomes,
    validate_event_panel,
)


def study_config(*horizons: int, pre: int = 2, post: int = 5) -> EventStudyConfig:
    return EventStudyConfig(
        primary_horizons=tuple(horizons or (1, 3, 5)),
        descriptive_horizons=(),
        pre_event_days=pre,
        post_event_days=post,
    )


def example_inputs(
    *,
    direction: str = "positive",
    second_event: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2024-01-01", periods=12)
    event_date = dates[3]
    events = [
        {
            "event_id": "event_a",
            "date": event_date,
            "security_id": "INIT",
            "direction": direction,
            "peer_definition": "economic",
            "subsector": "design",
            "relative_return": 0.08 if direction == "positive" else -0.08,
            "relative_volatility": 0.02,
            "simultaneous_event_group": pd.NA,
            "earnings_flag": False,
        }
    ]
    if second_event:
        events.append(
            {
                **events[0],
                "event_id": "event_b",
                "date": dates[5],
                "security_id": "OTHER",
            }
        )
    values = {
        "INIT": [0.0, 0.0, 0.0, 0.50, -0.01, -0.02, -0.01, 0.0, 0.0, 0.0, 0.0, 0.0],
        "PEER_A": [0.0, 0.0, 0.0, 0.10, 0.01, 0.01, 0.01, 0.0, 0.0, 0.0, 0.0, 0.0],
        "PEER_B": [0.0, 0.0, 0.0, 0.20, 0.20, 0.20, 0.20, 0.0, 0.0, 0.0, 0.0, 0.0],
        "OTHER": [0.0] * 12,
    }
    returns = pd.DataFrame(
        [
            {"date": date, "security_id": security_id, "abnormal": value}
            for security_id, observations in values.items()
            for date, value in zip(dates, observations, strict=True)
        ]
    )
    peers = pd.DataFrame(
        [
            {
                "date": event_date,
                "security_id": "INIT",
                "peer_id": "PEER_A",
                "peer_definition": "economic",
                "weight": 1.0,
            },
            # Future reclassification must not replace the event-date peer.
            {
                "date": dates[4],
                "security_id": "INIT",
                "peer_id": "PEER_B",
                "peer_definition": "economic",
                "weight": 1.0,
            },
            {
                "date": dates[5],
                "security_id": "OTHER",
                "peer_id": "PEER_A",
                "peer_definition": "economic",
                "weight": 1.0,
            },
        ]
    )
    return pd.DataFrame(events), returns, peers


def test_event_day_is_visible_but_excluded_and_windows_have_no_off_by_one() -> None:
    events, returns, peers = example_inputs()
    result = run_event_study(
        events, returns, peers, study_config(1, 3),
        return_column="abnormal", return_specification="semiconductor_adjusted_return",
    )

    day_zero = result.event_panel.loc[result.event_panel["relative_day"].eq(0)].iloc[0]
    one_day = result.outcomes.loc[result.outcomes["horizon"].eq(1)].iloc[0]
    three_day = result.outcomes.loc[result.outcomes["horizon"].eq(3)].iloc[0]
    assert day_zero["initiator_return"] == pytest.approx(0.50)
    assert one_day["initiator_car"] == pytest.approx(-0.01)
    assert one_day["peer_car"] == pytest.approx(0.01)
    assert three_day["initiator_car"] == pytest.approx(-0.04)
    assert three_day["peer_car"] == pytest.approx(0.03)
    assert day_zero["calendar_date"] == pd.Timestamp("2024-01-04")
    assert result.event_panel.loc[result.event_panel["relative_day"].eq(1), "calendar_date"].item() == pd.Timestamp("2024-01-05")


def test_event_date_peer_set_and_weights_are_frozen() -> None:
    events, returns, peers = example_inputs()
    panel = build_event_panel(
        events, returns, peers, study_config(1),
        return_column="abnormal", return_specification="spec",
    )

    assert panel.loc[panel["relative_day"].eq(1), "peer_return"].item() == pytest.approx(0.01)

    changed_future = peers.copy()
    changed_future.loc[changed_future["date"].gt(events.iloc[0]["date"]), "peer_id"] = "PEER_B"
    changed = build_event_panel(
        events, returns, changed_future, study_config(1),
        return_column="abnormal", return_specification="spec",
    )
    pd.testing.assert_series_equal(panel["peer_return"], changed["peer_return"])


@pytest.mark.parametrize(
    ("direction", "initiator", "peer", "expected"),
    [
        ("positive", 0.00, 0.03, (0.03, 0.00, 0.03)),
        ("positive", -0.04, 0.00, (0.00, 0.04, 0.04)),
        ("positive", -0.02, 0.02, (0.02, 0.02, 0.04)),
        ("negative", 0.03, -0.02, (0.02, 0.03, 0.05)),
    ],
)
def test_manual_sign_normalization_examples(
    direction: str,
    initiator: float,
    peer: float,
    expected: tuple[float, float, float],
) -> None:
    events, returns, peers = example_inputs(direction=direction)
    event_date = events.iloc[0]["date"]
    next_date = returns.loc[returns["date"].gt(event_date), "date"].min()
    returns.loc[(returns["date"].eq(next_date)) & returns["security_id"].eq("INIT"), "abnormal"] = initiator
    returns.loc[(returns["date"].eq(next_date)) & returns["security_id"].eq("PEER_A"), "abnormal"] = peer
    result = run_event_study(
        events, returns, peers, study_config(1),
        return_column="abnormal", return_specification="spec",
    ).outcomes.iloc[0]

    assert result["peer_catchup"] == pytest.approx(expected[0])
    assert result["initiator_reversal"] == pytest.approx(expected[1])
    assert result["convergence"] == pytest.approx(expected[2])
    assert result["convergence"] == pytest.approx(
        result["peer_catchup"] + result["initiator_reversal"]
    )
    sign = 1 if direction == "positive" else -1
    assert result["convergence"] == pytest.approx(sign * (peer - initiator))


def test_incomplete_horizons_are_retained_with_explicit_reasons() -> None:
    events, returns, peers = example_inputs()
    returns = returns.loc[returns["date"].le(pd.Timestamp("2024-01-08"))]
    outcomes = run_event_study(
        events, returns, peers, study_config(1, 5),
        return_column="abnormal", return_specification="spec",
    ).outcomes

    assert len(outcomes) == 2
    assert outcomes.set_index("horizon").loc[1, "valid_horizon"]
    invalid = outcomes.set_index("horizon").loc[5]
    assert not invalid["valid_horizon"]
    assert "end_of_sample" in invalid["missing_reason"]
    assert np.isnan(invalid["convergence"])


def test_missing_peer_observation_and_membership_are_distinguished() -> None:
    events, returns, peers = example_inputs()
    next_date = pd.Timestamp("2024-01-05")
    missing_return = returns.loc[~(returns["date"].eq(next_date) & returns["security_id"].eq("PEER_A"))]
    outcome = run_event_study(
        events, missing_return, peers, study_config(1),
        return_column="abnormal", return_specification="spec",
    ).outcomes.iloc[0]
    assert outcome["missing_reason"] == "missing_peer_observation"

    no_membership = peers.loc[peers["date"].ne(events.iloc[0]["date"])]
    outcome = run_event_study(
        events, returns, no_membership, study_config(1),
        return_column="abnormal", return_specification="spec",
    ).outcomes.iloc[0]
    assert "missing_event_date_peer_membership" in outcome["missing_reason"]


def test_overlapping_post_event_windows_are_flagged_without_dropping_events() -> None:
    events, returns, peers = example_inputs(second_event=True)
    outcomes = run_event_study(
        events, returns, peers, study_config(3),
        return_column="abnormal", return_specification="spec",
    ).outcomes

    assert outcomes["event_id"].nunique() == 2
    assert outcomes["overlapping_post_event_window"].all()


def test_descriptive_outputs_and_diagnostics_are_counts_not_inference() -> None:
    events, returns, peers = example_inputs()
    outcome = run_event_study(
        events, returns, peers, study_config(1),
        return_column="abnormal", return_specification="spec",
    ).outcomes
    summary = descriptive_summary(outcome)
    diagnostics = event_diagnostics(events, outcome)

    assert set(summary["direction"]) == {"all", "positive"}
    assert summary["event_count"].eq(1).all()
    assert diagnostics["total_events"]["total_detected_events"].item() == 1
    assert diagnostics["events_by_firm"]["event_count"].item() == 1


def test_stage_8_contracts_reject_broken_convergence_identity() -> None:
    events, returns, peers = example_inputs()
    result = run_event_study(
        events, returns, peers, study_config(1),
        return_column="abnormal", return_specification="spec",
    )
    validate_event_panel(result.event_panel)
    validate_event_outcomes(result.outcomes)

    broken = result.outcomes.copy()
    broken.loc[0, "convergence"] += 0.01
    with pytest.raises(DataValidationError, match="invalid_convergence"):
        validate_event_outcomes(broken)
