import numpy as np
import pandas as pd

from price_diffusion.baseline import (
    build_semiconductor_factor,
    event_path_statistics,
    interpret_mechanism,
    production_peer_classification,
)


def test_production_peer_groups_copy_reviewed_subsectors() -> None:
    classification = pd.DataFrame(
        {
            "security_id": ["A", "B"],
            "subsector": ["foundry", "semiconductor_equipment"],
        }
    )
    peers = production_peer_classification(classification)

    assert peers["peer_group"].equals(peers["subsector"])
    assert peers["classification_notes"].str.contains("Stage 11A").all()


def test_semiconductor_factor_uses_only_point_in_time_eligible_rows() -> None:
    date = pd.Timestamp("2024-01-02")
    panel = pd.DataFrame(
        {
            "date": [date, date, date],
            "security_id": ["A", "B", "C"],
            "return": [0.01, 0.03, 0.90],
        }
    )
    membership = pd.DataFrame(
        {
            "date": [date, date, date],
            "security_id": ["A", "B", "C"],
            "eligible": [True, True, False],
        }
    )

    factor = build_semiconductor_factor(panel, membership)
    assert factor["semiconductor_return"].item() == 0.02


def test_event_path_is_sign_normalized_and_has_requested_window() -> None:
    rows = []
    for event_id, direction, sign in (("p", "positive", 1), ("n", "negative", -1)):
        for day in range(-1, 2):
            rows.append(
                {
                    "event_id": event_id,
                    "relative_day": day,
                    "valid_observation": True,
                    "signed_initiator_return": sign * sign * 0.01,
                    "signed_peer_return": 0.0,
                    "direction": direction,
                }
            )
    statistics = event_path_statistics(pd.DataFrame(rows))

    assert set(statistics["relative_day"]) == {-1, 0, 1}
    day_one = statistics.loc[
        statistics["relative_day"].eq(1)
        & statistics["outcome"].eq("initiator_car"),
        "mean",
    ].item()
    assert np.isclose(day_one, 0.03)


def test_interpretation_is_descriptive_and_reports_imprecision() -> None:
    mechanism = pd.DataFrame(
        {
            "horizon": [5],
            "convergence_mean": [0.004],
            "convergence_ci_lower": [-0.002],
            "convergence_ci_upper": [0.010],
            "peer_catchup_mean": [0.002],
            "initiator_reversal_mean": [0.002],
        }
    )
    text = interpret_mechanism(mechanism)

    assert "point estimates" in text
    assert "includes zero" in text
    assert "not causal evidence" in text
