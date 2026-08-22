"""Small deterministic contract-valid datasets used by tests and examples."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SyntheticResearchData:
    """The four core research frames as one fixture bundle."""

    security_master: pd.DataFrame
    universe_membership: pd.DataFrame
    daily_panel: pd.DataFrame
    peer_membership: pd.DataFrame


@dataclass(frozen=True)
class SyntheticUniverseData:
    """Inputs and thresholds covering the main Stage 4 eligibility cases."""

    security_master: pd.DataFrame
    daily_panel: pd.DataFrame
    semiconductor_classification: pd.DataFrame
    universe_parameters: dict[str, object]


@dataclass(frozen=True)
class SyntheticPeerData:
    """Stage 5 inputs spanning close and unrelated semiconductor groups."""

    security_master: pd.DataFrame
    semiconductor_classification: pd.DataFrame
    universe_membership: pd.DataFrame
    peer_classification: pd.DataFrame


def make_synthetic_peer_data() -> SyntheticPeerData:
    """Create AI-compute, memory, equipment, and analog peer examples."""
    specifications = [
        ("SEC_AI_A", "AIA", "AI Accelerator A", "fabless_design", "ai_compute"),
        ("SEC_AI_B", "AIB", "AI Accelerator B", "fabless_design", "ai_compute"),
        ("SEC_MEM", "MEM", "Memory Producer", "memory", "memory_products"),
        ("SEC_EQP", "EQP", "Wafer Equipment", "equipment", "wafer_equipment"),
        (
            "SEC_ANA",
            "ANA",
            "Analog Devices",
            "analog_mixed_signal",
            "analog_signal_chain",
        ),
    ]
    security_master = pd.DataFrame(
        {
            "security_id": [row[0] for row in specifications],
            "ticker": [row[1] for row in specifications],
            "company_name": [row[2] for row in specifications],
            "exchange": ["NASDAQ"] * len(specifications),
            "security_type": ["common_stock"] * len(specifications),
            "sector": ["Information Technology"] * len(specifications),
            "sub_industry": ["Semiconductors"] * len(specifications),
        }
    )
    semiconductor_classification = pd.DataFrame(
        {
            "security_id": [row[0] for row in specifications],
            "ticker": [row[1] for row in specifications],
            "company_name": [row[2] for row in specifications],
            "subsector": [row[3] for row in specifications],
            "classification_notes": [
                "Synthetic semiconductor classification for Stage 5 tests."
            ]
            * len(specifications),
        }
    )
    peer_classification = pd.DataFrame(
        {
            "security_id": [row[0] for row in specifications],
            "subsector": [row[3] for row in specifications],
            "peer_group": [row[4] for row in specifications],
            "classification_notes": [
                f"Human-reviewed synthetic grouping based on {row[4].replace('_', ' ')}."
                for row in specifications
            ],
        }
    )
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    universe_membership = pd.DataFrame(
        [
            {
                "date": date,
                "security_id": security_id,
                "eligible": not (
                    date == dates[1] and security_id == "SEC_AI_B"
                ),
                "exclusion_reason": (
                    "insufficient_liquidity"
                    if date == dates[1] and security_id == "SEC_AI_B"
                    else None
                ),
            }
            for date in dates
            for security_id in security_master["security_id"]
        ]
    ).astype({"eligible": "bool"})
    return SyntheticPeerData(
        security_master=security_master,
        semiconductor_classification=semiconductor_classification,
        universe_membership=universe_membership,
        peer_classification=peer_classification,
    )


def make_synthetic_research_data() -> SyntheticResearchData:
    """Create semiconductor-like observations with point-in-time peer edges."""
    security_master = pd.DataFrame(
        {
            "security_id": ["SEC_NVDA", "SEC_AMD", "SEC_INTC"],
            "ticker": ["NVDA", "AMD", "INTC"],
            "company_name": [
                "Nvidia Analog",
                "Advanced Micro Devices Synthetic",
                "Integrated Circuits Synthetic",
            ],
            "exchange": ["NASDAQ", "NASDAQ", "NASDAQ"],
            "security_type": ["common_stock"] * 3,
            "sector": ["Information Technology"] * 3,
            "sub_industry": ["Semiconductors"] * 3,
        }
    )

    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    universe_membership = pd.DataFrame(
        [
            {
                "date": date,
                "security_id": security_id,
                "eligible": True,
                "exclusion_reason": None,
            }
            for date in dates
            for security_id in security_master["security_id"]
        ]
    ).astype({"eligible": "bool"})

    prices = {
        "SEC_NVDA": [50.0, 51.0, 50.5],
        "SEC_AMD": [140.0, 142.0, 145.0],
        "SEC_INTC": [47.0, 46.5, 47.5],
    }
    volumes = {
        "SEC_NVDA": [1_000_000, 1_100_000, 950_000],
        "SEC_AMD": [800_000, 820_000, 900_000],
        "SEC_INTC": [600_000, 610_000, 590_000],
    }
    panel_rows: list[dict[str, object]] = []
    for security_id, security_prices in prices.items():
        for position, (date, price, volume) in enumerate(
            zip(dates, security_prices, volumes[security_id])
        ):
            prior = security_prices[position - 1] if position else None
            panel_rows.append(
                {
                    "date": date,
                    "security_id": security_id,
                    "adjusted_close": price,
                    "close": price,
                    "volume": volume,
                    "return": None if prior is None else price / prior - 1.0,
                }
            )
    daily_panel = pd.DataFrame(panel_rows)

    peer_rows: list[dict[str, object]] = []
    security_ids = security_master["security_id"].tolist()
    for date in dates:
        for security_id in security_ids:
            peers = [candidate for candidate in security_ids if candidate != security_id]
            for peer_id in peers:
                peer_rows.append(
                    {
                        "date": date,
                        "security_id": security_id,
                        "peer_id": peer_id,
                        "weight": 1.0 / len(peers),
                        "peer_definition": "equal_weight_semiconductor",
                    }
                )
    peer_membership = pd.DataFrame(peer_rows)

    return SyntheticResearchData(
        security_master=security_master,
        universe_membership=universe_membership,
        daily_panel=daily_panel,
        peer_membership=peer_membership,
    )


def make_synthetic_universe_data() -> SyntheticUniverseData:
    """Create valid, non-semiconductor, new-listing, and illiquid cases."""
    security_master = pd.DataFrame(
        {
            "security_id": [
                "SEC_VALID",
                "SEC_ADR",
                "SEC_RETAIL",
                "SEC_NEW",
                "SEC_ILLIQUID",
            ],
            "ticker": ["VALID", "SADR", "SHOP", "NEW", "ILLIQ"],
            "company_name": [
                "Valid Fabless Synthetic",
                "Valid Foundry ADR Synthetic",
                "Non Semiconductor Retail Synthetic",
                "Newly Listed Semiconductor Synthetic",
                "Illiquid Semiconductor Synthetic",
            ],
            "exchange": ["NASDAQ", "NYSE", "NYSE", "NASDAQ", "NASDAQ"],
            "security_type": [
                "common_stock",
                "adr",
                "common_stock",
                "common_stock",
                "common_stock",
            ],
            "sector": [
                "Information Technology",
                "Information Technology",
                "Consumer Discretionary",
                "Information Technology",
                "Information Technology",
            ],
            "sub_industry": [
                "Semiconductors",
                "Semiconductors",
                "Specialty Retail",
                "Semiconductors",
                "Semiconductors",
            ],
        }
    )
    semiconductor_classification = pd.DataFrame(
        {
            "security_id": ["SEC_VALID", "SEC_ADR", "SEC_NEW", "SEC_ILLIQUID"],
            "ticker": ["VALID", "SADR", "NEW", "ILLIQ"],
            "company_name": [
                "Valid Fabless Synthetic",
                "Valid Foundry ADR Synthetic",
                "Newly Listed Semiconductor Synthetic",
                "Illiquid Semiconductor Synthetic",
            ],
            "subsector": [
                "fabless_design",
                "foundry",
                "integrated_device_manufacturer",
                "analog_mixed_signal",
            ],
            "classification_notes": [
                "Synthetic manually assigned semiconductor example.",
                "Synthetic manually assigned US-listed ADR example.",
                "Synthetic manually assigned recent listing example.",
                "Synthetic manually assigned low-liquidity example.",
            ],
        }
    )

    dates = pd.bdate_range("2024-01-02", periods=5)
    specifications = {
        "SEC_VALID": (dates, 20.0, 200.0),
        "SEC_ADR": (dates, 25.0, 160.0),
        "SEC_RETAIL": (dates, 30.0, 200.0),
        "SEC_NEW": (dates[-2:], 15.0, 200.0),
        "SEC_ILLIQUID": (dates, 10.0, 5.0),
    }
    rows: list[dict[str, object]] = []
    for security_id, (security_dates, base_price, volume) in specifications.items():
        prior: float | None = None
        for position, date in enumerate(security_dates):
            price = base_price + position
            rows.append(
                {
                    "date": date,
                    "security_id": security_id,
                    "adjusted_close": price,
                    "close": price,
                    "volume": volume,
                    "return": None if prior is None else price / prior - 1.0,
                }
            )
            prior = price

    return SyntheticUniverseData(
        security_master=security_master,
        daily_panel=pd.DataFrame(rows),
        semiconductor_classification=semiconductor_classification,
        universe_parameters={
            "min_history_days": 3,
            "min_price": 5.0,
            "min_average_dollar_volume": 1_000.0,
            "average_dollar_volume_window_days": 3,
            "us_exchanges": ["NASDAQ", "NYSE"],
            "eligible_security_types": ["common_stock", "adr"],
            "classification_as_of_date": "2024-01-02",
            "allow_classification_before_as_of": False,
        },
    )


def make_synthetic_raw_market_data() -> pd.DataFrame:
    """Create deterministic multi-year raw prices with realistic row gaps.

    Missing observations are represented by absent rows. They deliberately occur
    on different dates for different securities so return logic cannot rely on a
    balanced calendar.
    """
    dates = pd.bdate_range("2022-01-03", "2024-12-31")
    specifications = {
        "NVDA": (75.0, 0.0007, 3_000_000),
        "AMD": (130.0, 0.0004, 2_000_000),
        "INTC": (48.0, 0.0001, 1_500_000),
    }
    rows: list[dict[str, object]] = []
    for security_position, (ticker, (base, drift, base_volume)) in enumerate(
        specifications.items()
    ):
        for position, date in enumerate(dates):
            # Source gaps vary by security and include more than one business day.
            if security_position and position % (89 + 11 * security_position) == 0:
                continue
            cyclical_move = ((position % 17) - 8) * 0.00015
            adjusted_close = base * (1.0 + drift * position + cyclical_move)
            close = adjusted_close * (1.0 + 0.0002 * security_position)
            rows.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "adjusted_close": round(adjusted_close, 6),
                    "close": round(close, 6),
                    "volume": base_volume + (position % 23) * 10_000,
                }
            )
    return pd.DataFrame(rows).sample(frac=1.0, random_state=314159).reset_index(drop=True)


def make_invalid_synthetic_raw_market_data(case: str) -> pd.DataFrame:
    """Create one explicitly invalid raw market example for pipeline tests."""
    invalid = make_synthetic_raw_market_data().iloc[:20].copy()
    if case == "negative_price":
        invalid.loc[invalid.index[0], "adjusted_close"] = -1.0
    elif case == "negative_volume":
        invalid.loc[invalid.index[0], "volume"] = -1
    elif case == "malformed_date":
        invalid.loc[invalid.index[0], "date"] = "not-a-date"
    elif case == "duplicate":
        invalid = pd.concat([invalid, invalid.iloc[[0]]], ignore_index=True)
    elif case == "missing_value":
        invalid.loc[invalid.index[0], "close"] = None
    elif case == "unknown_security":
        invalid.loc[invalid.index[0], "ticker"] = "UNKNOWN"
    else:
        raise ValueError(f"unknown invalid synthetic case: {case}")
    return invalid
