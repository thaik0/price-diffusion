"""Point-in-time construction of economically defined semiconductor peers."""

from collections.abc import Callable, Iterable

import pandas as pd

from price_diffusion.data_contracts import PEER_CLASSIFICATION
from price_diffusion.validation import (
    DataValidationError,
    ValidationIssue,
    validate_peer_classification,
    validate_peer_membership,
    validate_security_master,
    validate_semiconductor_classification,
    validate_universe_membership,
)

ECONOMIC_SUBSECTOR_PEERS = "economic_subsector_peers"
BROAD_SEMICONDUCTOR_PEERS = "broad_semiconductor_peers"
TRAILING_RETURN_SIMILARITY_PEERS = "trailing_return_similarity_peers"

PEER_OUTPUT_COLUMNS = (
    "date",
    "security_id",
    "peer_id",
    "peer_definition",
    "weight",
)

PRIMARY_SUBSECTORS = frozenset(
    {
        "fabless_design",
        "integrated_device_manufacturer",
        "foundry",
        "memory",
        "equipment",
        "eda_ip",
        "packaging_testing",
        "analog_mixed_signal",
    }
)

CandidateBuilder = Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame]


def _economic_candidates(
    eligible: pd.DataFrame, classifications: pd.DataFrame
) -> pd.DataFrame:
    labelled = eligible.merge(
        classifications[["security_id", "peer_group"]],
        on="security_id",
        how="left",
        validate="many_to_one",
    )
    candidates = labelled.merge(
        labelled.rename(columns={"security_id": "peer_id"}),
        on=["date", "peer_group"],
        how="inner",
        validate="many_to_many",
    )
    return candidates.loc[
        candidates["security_id"].ne(candidates["peer_id"]),
        ["date", "security_id", "peer_id"],
    ]


def _broad_candidates(
    eligible: pd.DataFrame, classifications: pd.DataFrame
) -> pd.DataFrame:
    del classifications
    candidates = eligible.merge(
        eligible.rename(columns={"security_id": "peer_id"}),
        on="date",
        how="inner",
        validate="many_to_many",
    )
    return candidates.loc[
        candidates["security_id"].ne(candidates["peer_id"]),
        ["date", "security_id", "peer_id"],
    ]


PEER_DEFINITION_BUILDERS: dict[str, CandidateBuilder] = {
    ECONOMIC_SUBSECTOR_PEERS: _economic_candidates,
    BROAD_SEMICONDUCTOR_PEERS: _broad_candidates,
}


def _validate_classification_coverage(
    eligible: pd.DataFrame,
    classification: pd.DataFrame,
    dataset_name: str,
) -> None:
    classified = set(classification["security_id"])
    missing = sorted(set(eligible["security_id"]) - classified)
    if missing:
        raise DataValidationError(
            [
                ValidationIssue(
                    dataset_name,
                    "missing_classification",
                    "eligible securities lack classifications: "
                    + ", ".join(missing),
                )
            ]
        )


def _validate_subsectors(peer_classification: pd.DataFrame) -> None:
    unknown = sorted(set(peer_classification["subsector"]) - PRIMARY_SUBSECTORS)
    if unknown:
        raise DataValidationError(
            [
                ValidationIssue(
                    PEER_CLASSIFICATION.name,
                    "invalid_subsector",
                    "unsupported subsectors: " + ", ".join(unknown),
                )
            ]
        )


def _validate_subsector_consistency(
    semiconductor_classification: pd.DataFrame,
    peer_classification: pd.DataFrame,
) -> None:
    compared = semiconductor_classification[["security_id", "subsector"]].merge(
        peer_classification[["security_id", "subsector"]],
        on="security_id",
        how="inner",
        suffixes=("_semiconductor", "_peer"),
        validate="one_to_one",
    )
    mismatched = compared.loc[
        compared["subsector_semiconductor"].ne(compared["subsector_peer"]),
        "security_id",
    ].tolist()
    if mismatched:
        raise DataValidationError(
            [
                ValidationIssue(
                    PEER_CLASSIFICATION.name,
                    "inconsistent_subsector",
                    "subsector disagrees with semiconductor classification for: "
                    + ", ".join(sorted(mismatched)),
                )
            ]
        )


def build_peer_membership(
    security_master: pd.DataFrame,
    semiconductor_classification: pd.DataFrame,
    universe_membership: pd.DataFrame,
    peer_classification: pd.DataFrame,
    *,
    definitions: Iterable[str] = (ECONOMIC_SUBSECTOR_PEERS,),
) -> pd.DataFrame:
    """Build directed, equally weighted peer portfolios for eligible firms.

    Candidate builders are deliberately metadata-based. A future trailing-return
    builder can be registered without changing the output contract, but it is
    not implemented in this stage.
    """
    validate_security_master(security_master)
    validate_semiconductor_classification(
        semiconductor_classification, security_master
    )
    validate_universe_membership(universe_membership, security_master)
    validate_peer_classification(peer_classification, security_master)
    _validate_subsectors(peer_classification)
    _validate_subsector_consistency(
        semiconductor_classification, peer_classification
    )

    eligible = universe_membership.loc[
        universe_membership["eligible"], ["date", "security_id"]
    ].copy()
    _validate_classification_coverage(
        eligible, semiconductor_classification, "semiconductor_classification"
    )
    _validate_classification_coverage(
        eligible, peer_classification, PEER_CLASSIFICATION.name
    )

    requested = tuple(definitions)
    if not requested:
        raise ValueError("at least one peer definition is required")
    if len(requested) != len(set(requested)):
        raise ValueError("peer definitions must not be duplicated")

    outputs: list[pd.DataFrame] = []
    for definition in requested:
        if definition == TRAILING_RETURN_SIMILARITY_PEERS:
            raise NotImplementedError(
                "trailing return similarity peers are reserved for robustness analysis"
            )
        try:
            builder = PEER_DEFINITION_BUILDERS[definition]
        except KeyError as error:
            raise ValueError(f"unknown peer definition: {definition}") from error
        candidates = builder(eligible, peer_classification).copy()
        if candidates.empty:
            continue
        candidates["peer_definition"] = definition
        group_columns = ["date", "security_id", "peer_definition"]
        candidates["weight"] = 1.0 / candidates.groupby(group_columns)[
            "peer_id"
        ].transform("size")
        outputs.append(candidates[list(PEER_OUTPUT_COLUMNS)])

    if outputs:
        output = pd.concat(outputs, ignore_index=True).sort_values(
            ["date", "security_id", "peer_definition", "peer_id"],
            ignore_index=True,
        )
    else:
        output = pd.DataFrame(
            {
                "date": pd.Series(dtype="datetime64[ns]"),
                "security_id": pd.Series(dtype="object"),
                "peer_id": pd.Series(dtype="object"),
                "peer_definition": pd.Series(dtype="object"),
                "weight": pd.Series(dtype="float64"),
            }
        )
    validate_peer_membership(output, security_master, universe_membership)
    return output[list(PEER_OUTPUT_COLUMNS)]
