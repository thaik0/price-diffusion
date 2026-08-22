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
            "sector": ["Information Technology"] * 3,
            "sub_industry": ["Semiconductors"] * 3,
        }
    )

    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    universe_membership = pd.DataFrame(
        [
            {"date": date, "security_id": security_id, "eligible": True}
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

