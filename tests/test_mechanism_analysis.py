import numpy as np
import pandas as pd

from price_diffusion.mechanism_analysis import (
    build_mechanism_characteristics,
    peer_definition_comparison,
)
from price_diffusion.peers import (
    BROAD_SEMICONDUCTOR_PEERS,
    ECONOMIC_SUBSECTOR_PEERS,
    TRAILING_RETURN_SIMILARITY_PEERS,
)
from price_diffusion.research_diagnostics import DiagnosticInputs


def _characteristic_inputs() -> DiagnosticInputs:
    dates = pd.bdate_range("2023-01-02", periods=90)
    panel = pd.DataFrame(
        {
            "date": np.tile(dates, 2),
            "security_id": np.repeat(["A", "B"], len(dates)),
            "return": np.tile(np.linspace(-0.002, 0.003, len(dates)), 2),
            "volume": np.concatenate(
                [np.arange(100, 100 + len(dates)), np.arange(200, 200 + len(dates))]
            ),
        }
    )
    membership = panel[["date", "security_id"]].assign(eligible=True)
    event_date = dates[-1]
    events = pd.DataFrame(
        {
            "event_id": ["e1"],
            "date": [event_date],
            "security_id": ["A"],
            "direction": ["positive"],
            "relative_return": [0.06],
            "relative_volatility": [0.02],
            "peer_definition": [ECONOMIC_SUBSECTOR_PEERS],
            "subsector": ["semiconductor_equipment"],
        }
    )
    master = pd.DataFrame(
        {
            "security_id": ["A", "B"],
            "ticker": ["AAA", "BBB"],
            "company_name": ["A Co", "B Co"],
        }
    )
    return DiagnosticInputs(
        config={},
        security_master=master,
        universe_membership=membership,
        daily_panel=panel,
        peer_membership=pd.DataFrame(),
        relative_returns=pd.DataFrame(),
        events=events,
        event_panel=pd.DataFrame(),
        event_outcomes=pd.DataFrame(),
    )


def test_mechanism_characteristics_use_only_pre_event_information() -> None:
    characteristics = build_mechanism_characteristics(_characteristic_inputs())

    assert characteristics["EquipmentIndicator"].item() == 1
    assert characteristics["EconomicPeerIndicator"].item() == 1
    assert characteristics["ShockMagnitude"].item() == 3.0
    assert characteristics["no_future_sector_information"].all()
    assert characteristics["no_future_volume_information"].all()
    assert characteristics["sector_information_max_date"].item() < characteristics["date"].item()
    assert characteristics["volume_information_max_date"].item() < characteristics["date"].item()


def test_peer_comparison_uses_paired_identical_event_differences() -> None:
    rows = []
    values = {
        ECONOMIC_SUBSECTOR_PEERS: [0.03, 0.05],
        TRAILING_RETURN_SIMILARITY_PEERS: [0.01, 0.02],
        BROAD_SEMICONDUCTOR_PEERS: [0.02, 0.03],
    }
    for definition, peer_values in values.items():
        for event_id, value in zip(["e1", "e2"], peer_values):
            rows.append(
                {
                    "event_id": event_id,
                    "horizon": 5,
                    "peer_definition": definition,
                    "valid_horizon": True,
                    "peer_car": value,
                    "peer_catchup": value,
                    "convergence": value + 0.01,
                    "initiator_reversal": 0.01,
                }
            )
    comparison = peer_definition_comparison(
        pd.DataFrame(rows), bootstrap_replications=500, seed=7
    )
    paired = comparison.loc[
        comparison["comparison_type"].eq("paired_economic_minus_correlation")
        & comparison["horizon"].eq(5)
        & comparison["outcome"].eq("peer_catchup")
    ].iloc[0]

    assert paired["sample_size"] == 2
    assert np.isclose(paired["mean"], 0.025)
    assert paired["bootstrap_replications"] == 500
    assert paired["ci_lower"] <= paired["mean"] <= paired["ci_upper"]
