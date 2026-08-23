import pandas as pd

from price_diffusion.research_diagnostics import (
    DiagnosticInputs,
    build_event_date_peer_definitions,
    summarize_outcomes,
)
from price_diffusion.peers import TRAILING_RETURN_SIMILARITY_PEERS


def test_outcome_summaries_report_counts_and_small_sample_labels() -> None:
    outcomes = pd.DataFrame(
        {
            "event_id": ["e1", "e2"],
            "horizon": [5, 5],
            "valid_horizon": [True, True],
            "convergence": [0.01, -0.01],
            "peer_catchup": [0.02, 0.00],
            "initiator_reversal": [-0.01, -0.01],
        }
    )

    summary = summarize_outcomes(outcomes, ["horizon"])

    assert set(summary["outcome"]) == {
        "convergence", "peer_catchup", "initiator_reversal"
    }
    assert summary["event_count"].eq(2).all()
    assert summary["sample_size"].eq(2).all()
    assert summary["sample_label"].eq("small_sample_descriptive_only").all()


def test_correlation_peers_use_only_dates_strictly_before_event() -> None:
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    panel_rows = []
    for security_id, returns in {
        "A": [0.01, 0.02, 0.03, 0.04, 0.50],
        "B": [0.01, 0.02, 0.03, 0.04, -0.50],
        "C": [-0.01, -0.02, -0.03, -0.04, 0.50],
    }.items():
        panel_rows.extend(
            {"date": date, "security_id": security_id, "return": value}
            for date, value in zip(dates, returns)
        )
    daily_panel = pd.DataFrame(panel_rows)
    event_date = dates[-1]
    events = pd.DataFrame(
        {
            "event_id": ["e1"], "date": [event_date], "security_id": ["A"],
            "peer_definition": ["economic_subsector_peers"],
        }
    )
    universe_membership = pd.DataFrame(
        {
            "date": [event_date] * 3,
            "security_id": ["A", "B", "C"],
            "eligible": [True, True, True],
        }
    )
    economic = pd.DataFrame(
        {
            "date": [event_date], "security_id": ["A"], "peer_id": ["B"],
            "peer_definition": ["economic_subsector_peers"], "weight": [1.0],
        }
    )
    inputs = DiagnosticInputs(
        config={}, security_master=pd.DataFrame(), universe_membership=universe_membership,
        daily_panel=daily_panel, peer_membership=economic, relative_returns=pd.DataFrame(),
        events=events, event_panel=pd.DataFrame(), event_outcomes=pd.DataFrame(),
    )

    memberships, audit = build_event_date_peer_definitions(
        inputs, correlation_lookback=4, correlation_minimum_history=3,
        correlation_peer_count=1,
    )
    selected = memberships.loc[
        memberships["peer_definition"].eq(TRAILING_RETURN_SIMILARITY_PEERS), "peer_id"
    ]

    assert selected.tolist() == ["B"]
    assert audit["correlation_information_max_date"].item() == dates[-2]
    assert audit["no_future_information_check"].all()
