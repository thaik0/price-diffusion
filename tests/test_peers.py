from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from price_diffusion.peers import (
    BROAD_SEMICONDUCTOR_PEERS,
    ECONOMIC_SUBSECTOR_PEERS,
    PRIMARY_SUBSECTORS,
    TRAILING_RETURN_SIMILARITY_PEERS,
    build_peer_membership,
)
from price_diffusion.synthetic import SyntheticPeerData, make_synthetic_peer_data
from price_diffusion.validation import DataValidationError, validate_peer_membership


@pytest.fixture
def peer_data() -> SyntheticPeerData:
    return make_synthetic_peer_data()


def _build(data: SyntheticPeerData, *definitions: str) -> pd.DataFrame:
    return build_peer_membership(
        data.security_master,
        data.semiconductor_classification,
        data.universe_membership,
        data.peer_classification,
        definitions=definitions or (ECONOMIC_SUBSECTOR_PEERS,),
    )


def _codes(error: DataValidationError) -> set[str]:
    return {issue.code for issue in error.issues}


def test_reviewed_peer_metadata_has_required_taxonomy() -> None:
    path = Path(__file__).parents[1] / "metadata" / "peer_classification.csv"
    metadata = pd.read_csv(path)

    assert list(metadata.columns) == [
        "security_id",
        "subsector",
        "peer_group",
        "classification_notes",
    ]
    assert not metadata["security_id"].duplicated().any()
    assert set(metadata["subsector"]) == PRIMARY_SUBSECTORS
    assert metadata["classification_notes"].str.strip().ne("").all()
    assert metadata["classification_notes"].str.contains("human review").all()


def test_economic_peers_are_close_groups_not_unrelated_firms(
    peer_data: SyntheticPeerData,
) -> None:
    peers = _build(peer_data)
    first_date = pd.Timestamp("2024-01-02")
    ai_a = peers.loc[
        peers["date"].eq(first_date) & peers["security_id"].eq("SEC_AI_A")
    ]

    assert ai_a["peer_id"].tolist() == ["SEC_AI_B"]
    assert not set(ai_a["peer_id"]) & {"SEC_MEM", "SEC_EQP", "SEC_ANA"}
    assert peers["security_id"].ne(peers["peer_id"]).all()


def test_weights_sum_to_one(peer_data: SyntheticPeerData) -> None:
    peers = _build(
        peer_data, ECONOMIC_SUBSECTOR_PEERS, BROAD_SEMICONDUCTOR_PEERS
    )
    sums = peers.groupby(["date", "security_id", "peer_definition"])["weight"].sum()
    assert np.allclose(sums, 1.0)


def test_broad_peers_include_all_other_eligible_companies(
    peer_data: SyntheticPeerData,
) -> None:
    peers = _build(peer_data, BROAD_SEMICONDUCTOR_PEERS)
    first_date = peers["date"].min()
    ai_a = peers.loc[
        peers["date"].eq(first_date) & peers["security_id"].eq("SEC_AI_A")
    ]

    assert set(ai_a["peer_id"]) == {"SEC_AI_B", "SEC_MEM", "SEC_EQP", "SEC_ANA"}
    assert np.allclose(ai_a["weight"], 0.25)


def test_historical_membership_and_date_eligibility_are_respected(
    peer_data: SyntheticPeerData,
) -> None:
    peers = _build(peer_data, ECONOMIC_SUBSECTOR_PEERS, BROAD_SEMICONDUCTOR_PEERS)
    second_date = pd.Timestamp("2024-01-03")
    current = peers.loc[peers["date"].eq(second_date)]

    assert "SEC_AI_B" not in set(current["security_id"])
    assert "SEC_AI_B" not in set(current["peer_id"])
    assert not (
        current["peer_definition"].eq(ECONOMIC_SUBSECTOR_PEERS)
        & current["security_id"].eq("SEC_AI_A")
    ).any()


def test_missing_peer_classification_is_detected(peer_data: SyntheticPeerData) -> None:
    missing = peer_data.peer_classification.loc[
        peer_data.peer_classification["security_id"].ne("SEC_AI_A")
    ]

    with pytest.raises(DataValidationError) as caught:
        build_peer_membership(
            peer_data.security_master,
            peer_data.semiconductor_classification,
            peer_data.universe_membership,
            missing,
        )

    assert "missing_classification" in _codes(caught.value)


def test_missing_semiconductor_classification_is_detected(
    peer_data: SyntheticPeerData,
) -> None:
    missing = peer_data.semiconductor_classification.loc[
        peer_data.semiconductor_classification["security_id"].ne("SEC_AI_A")
    ]

    with pytest.raises(DataValidationError) as caught:
        build_peer_membership(
            peer_data.security_master,
            missing,
            peer_data.universe_membership,
            peer_data.peer_classification,
        )

    assert "missing_classification" in _codes(caught.value)


def test_inconsistent_subsector_labels_are_detected(
    peer_data: SyntheticPeerData,
) -> None:
    inconsistent = peer_data.peer_classification.copy()
    inconsistent.loc[
        inconsistent["security_id"].eq("SEC_AI_A"), "subsector"
    ] = "memory"

    with pytest.raises(DataValidationError) as caught:
        build_peer_membership(
            peer_data.security_master,
            peer_data.semiconductor_classification,
            peer_data.universe_membership,
            inconsistent,
        )

    assert "inconsistent_subsector" in _codes(caught.value)


def test_duplicate_peer_relationship_is_detected(peer_data: SyntheticPeerData) -> None:
    peers = _build(peer_data, BROAD_SEMICONDUCTOR_PEERS)
    duplicate = pd.concat([peers, peers.iloc[[0]]], ignore_index=True)

    with pytest.raises(DataValidationError) as caught:
        validate_peer_membership(
            duplicate, peer_data.security_master, peer_data.universe_membership
        )

    assert "duplicate_primary_key" in _codes(caught.value)


def test_ineligible_peer_endpoint_is_detected(peer_data: SyntheticPeerData) -> None:
    peers = _build(peer_data, BROAD_SEMICONDUCTOR_PEERS)
    invalid = peers.copy()
    invalid.loc[0, "date"] = pd.Timestamp("2024-01-03")
    invalid.loc[0, "peer_id"] = "SEC_AI_B"

    with pytest.raises(DataValidationError) as caught:
        validate_peer_membership(
            invalid, peer_data.security_master, peer_data.universe_membership
        )

    assert "ineligible_peer_endpoint" in _codes(caught.value)


def test_return_similarity_extension_is_explicitly_deferred(
    peer_data: SyntheticPeerData,
) -> None:
    with pytest.raises(NotImplementedError, match="robustness"):
        _build(peer_data, TRAILING_RETURN_SIMILARITY_PEERS)
