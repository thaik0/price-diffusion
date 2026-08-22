from price_diffusion.data_contracts import (
    DAILY_PANEL,
    DATA_CONTRACTS,
    PEER_MEMBERSHIP,
    SEMICONDUCTOR_CLASSIFICATION,
    SECURITY_MASTER,
    UNIVERSE_MEMBERSHIP,
    ColumnKind,
)


def test_all_core_contracts_are_registered() -> None:
    assert set(DATA_CONTRACTS) == {
        "security_master",
        "semiconductor_classification",
        "universe_membership",
        "daily_panel",
        "peer_membership",
    }


def test_contract_primary_keys_are_explicit() -> None:
    assert SECURITY_MASTER.primary_key == ("security_id",)
    assert SEMICONDUCTOR_CLASSIFICATION.primary_key == ("security_id",)
    assert UNIVERSE_MEMBERSHIP.primary_key == ("date", "security_id")
    assert DAILY_PANEL.primary_key == ("date", "security_id")
    assert PEER_MEMBERSHIP.primary_key == (
        "date",
        "security_id",
        "peer_id",
        "peer_definition",
    )


def test_nullable_core_fields_are_explicit() -> None:
    nullable = {
        (contract.name, name)
        for contract in DATA_CONTRACTS.values()
        for name, column in contract.columns.items()
        if column.nullable
    }

    assert nullable == {
        ("daily_panel", "return"),
        ("universe_membership", "exclusion_reason"),
    }
    assert DAILY_PANEL.columns["return"].kind is ColumnKind.NUMERIC
