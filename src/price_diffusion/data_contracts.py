"""Canonical dataframe contracts for the research pipeline.

The contracts in this module describe analysis-facing data.  Data-source
adapters may use different shapes internally, but must produce frames matching
these contracts before their output can be used by downstream research code.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ColumnKind(str, Enum):
    """Logical column types used by the dataframe validator."""

    STRING = "string"
    DATE = "date"
    BOOLEAN = "boolean"
    NUMERIC = "numeric"


@dataclass(frozen=True)
class ColumnContract:
    """Type and nullability requirements for one column."""

    kind: ColumnKind
    nullable: bool = False
    finite: bool = False


@dataclass(frozen=True)
class DataFrameContract:
    """Required columns and uniqueness key for one research dataset."""

    name: str
    columns: Mapping[str, ColumnContract]
    primary_key: tuple[str, ...]


def _columns(**columns: ColumnContract) -> Mapping[str, ColumnContract]:
    """Return an immutable column mapping."""
    return MappingProxyType(columns)


SECURITY_MASTER = DataFrameContract(
    name="security_master",
    columns=_columns(
        security_id=ColumnContract(ColumnKind.STRING),
        ticker=ColumnContract(ColumnKind.STRING),
        company_name=ColumnContract(ColumnKind.STRING),
        exchange=ColumnContract(ColumnKind.STRING),
        sector=ColumnContract(ColumnKind.STRING),
        sub_industry=ColumnContract(ColumnKind.STRING),
    ),
    primary_key=("security_id",),
)

UNIVERSE_MEMBERSHIP = DataFrameContract(
    name="universe_membership",
    columns=_columns(
        date=ColumnContract(ColumnKind.DATE),
        security_id=ColumnContract(ColumnKind.STRING),
        eligible=ColumnContract(ColumnKind.BOOLEAN),
    ),
    primary_key=("date", "security_id"),
)

DAILY_PANEL = DataFrameContract(
    name="daily_panel",
    columns=_columns(
        date=ColumnContract(ColumnKind.DATE),
        security_id=ColumnContract(ColumnKind.STRING),
        adjusted_close=ColumnContract(ColumnKind.NUMERIC, finite=True),
        close=ColumnContract(ColumnKind.NUMERIC, finite=True),
        volume=ColumnContract(ColumnKind.NUMERIC, finite=True),
        **{
            "return": ColumnContract(
                ColumnKind.NUMERIC, nullable=True, finite=True
            )
        },
    ),
    primary_key=("date", "security_id"),
)

PEER_MEMBERSHIP = DataFrameContract(
    name="peer_membership",
    columns=_columns(
        date=ColumnContract(ColumnKind.DATE),
        security_id=ColumnContract(ColumnKind.STRING),
        peer_id=ColumnContract(ColumnKind.STRING),
        weight=ColumnContract(ColumnKind.NUMERIC, finite=True),
        peer_definition=ColumnContract(ColumnKind.STRING),
    ),
    primary_key=("date", "security_id", "peer_id", "peer_definition"),
)

DATA_CONTRACTS = MappingProxyType(
    {
        contract.name: contract
        for contract in (
            SECURITY_MASTER,
            UNIVERSE_MEMBERSHIP,
            DAILY_PANEL,
            PEER_MEMBERSHIP,
        )
    }
)
