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
        security_type=ColumnContract(ColumnKind.STRING),
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
        exclusion_reason=ColumnContract(ColumnKind.STRING, nullable=True),
    ),
    primary_key=("date", "security_id"),
)

SEMICONDUCTOR_CLASSIFICATION = DataFrameContract(
    name="semiconductor_classification",
    columns=_columns(
        security_id=ColumnContract(ColumnKind.STRING),
        ticker=ColumnContract(ColumnKind.STRING),
        company_name=ColumnContract(ColumnKind.STRING),
        subsector=ColumnContract(ColumnKind.STRING),
        classification_notes=ColumnContract(ColumnKind.STRING),
    ),
    primary_key=("security_id",),
)

PEER_CLASSIFICATION = DataFrameContract(
    name="peer_classification",
    columns=_columns(
        security_id=ColumnContract(ColumnKind.STRING),
        subsector=ColumnContract(ColumnKind.STRING),
        peer_group=ColumnContract(ColumnKind.STRING),
        classification_notes=ColumnContract(ColumnKind.STRING),
    ),
    primary_key=("security_id",),
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

RELATIVE_RETURNS = DataFrameContract(
    name="relative_returns",
    columns=_columns(
        date=ColumnContract(ColumnKind.DATE),
        security_id=ColumnContract(ColumnKind.STRING),
        peer_definition=ColumnContract(ColumnKind.STRING),
        stock_return=ColumnContract(ColumnKind.NUMERIC, nullable=True, finite=True),
        peer_return=ColumnContract(ColumnKind.NUMERIC, nullable=True, finite=True),
        relative_return=ColumnContract(ColumnKind.NUMERIC, nullable=True, finite=True),
        market_adjusted_return=ColumnContract(
            ColumnKind.NUMERIC, nullable=True, finite=True
        ),
        semiconductor_adjusted_return=ColumnContract(
            ColumnKind.NUMERIC, nullable=True, finite=True
        ),
    ),
    primary_key=("date", "security_id", "peer_definition"),
)

EVENTS = DataFrameContract(
    name="events",
    columns=_columns(
        event_id=ColumnContract(ColumnKind.STRING),
        date=ColumnContract(ColumnKind.DATE),
        security_id=ColumnContract(ColumnKind.STRING),
        direction=ColumnContract(ColumnKind.STRING),
        relative_return=ColumnContract(ColumnKind.NUMERIC, finite=True),
        relative_volatility=ColumnContract(ColumnKind.NUMERIC, finite=True),
        threshold_used=ColumnContract(ColumnKind.NUMERIC, finite=True),
        peer_definition=ColumnContract(ColumnKind.STRING),
        subsector=ColumnContract(ColumnKind.STRING),
        volume=ColumnContract(ColumnKind.NUMERIC, nullable=True, finite=True),
        market_cap=ColumnContract(ColumnKind.NUMERIC, nullable=True, finite=True),
        simultaneous_event_group=ColumnContract(
            ColumnKind.STRING, nullable=True
        ),
        corporate_action_type=ColumnContract(ColumnKind.STRING),
        earnings_flag=ColumnContract(ColumnKind.BOOLEAN),
        news_identified_flag=ColumnContract(ColumnKind.BOOLEAN),
    ),
    primary_key=("event_id",),
)

DATA_CONTRACTS = MappingProxyType(
    {
        contract.name: contract
        for contract in (
            SECURITY_MASTER,
            SEMICONDUCTOR_CLASSIFICATION,
            PEER_CLASSIFICATION,
            UNIVERSE_MEMBERSHIP,
            DAILY_PANEL,
            PEER_MEMBERSHIP,
            RELATIVE_RETURNS,
            EVENTS,
        )
    }
)
