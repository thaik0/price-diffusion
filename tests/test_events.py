import numpy as np
import pandas as pd
import pytest

from price_diffusion.events import EventDetectionConfig, detect_events


def event_config(**overrides: object) -> EventDetectionConfig:
    values: dict[str, object] = {
        "minimum_relative_move": 0.05,
        "volatility_window": 5,
        "threshold_multiplier": 2.0,
        "cooldown_period": 3,
        "minimum_peer_count": 2,
        "minimum_history_requirement": 5,
        "cooldown_scope": "firm",
    }
    values.update(overrides)
    return EventDetectionConfig(**values)  # type: ignore[arg-type]


def candidate_rows(
    security_id: str,
    shocks: dict[int, float],
    *,
    peer_group: str = "logic",
    peer_count: int = 3,
) -> list[dict[str, object]]:
    dates = pd.date_range("2024-01-01", periods=12, freq="D")
    baseline = [-0.01, 0.01, -0.01, 0.01, 0.0, -0.01, 0.01, 0.0, -0.01, 0.01, 0.0, 0.0]
    return [
        {
            "date": date,
            "security_id": security_id,
            "peer_definition": "economic_subsector_peers",
            "peer_group": peer_group,
            "subsector": "design",
            "peer_count": peer_count,
            "corporate_action_type": "none",
            "relative_abnormal_return": shocks.get(position, value),
            "volume": 1_000_000.0,
            "market_cap": 10_000_000_000.0,
        }
        for position, (date, value) in enumerate(zip(dates, baseline, strict=True))
    ]


def test_positive_ten_percent_company_two_percent_peers_is_event() -> None:
    # The precomputed company-minus-peer abnormal return is 10% - 2% = +8%.
    frame = pd.DataFrame(candidate_rows("POS", {5: 0.10 - 0.02}))

    events = detect_events(frame, event_config())

    assert len(events) == 1
    assert events.iloc[0]["direction"] == "positive"
    assert events.iloc[0]["relative_return"] == pytest.approx(0.08)


def test_negative_eight_percent_company_positive_one_percent_peers_is_event() -> None:
    # The precomputed company-minus-peer abnormal return is -8% - 1% = -9%.
    frame = pd.DataFrame(candidate_rows("NEG", {5: -0.08 - 0.01}))

    events = detect_events(frame, event_config())

    assert len(events) == 1
    assert events.iloc[0]["direction"] == "negative"
    assert events.iloc[0]["relative_return"] == pytest.approx(-0.09)


def test_threshold_volatility_uses_only_observations_before_event_date() -> None:
    baseline = pd.DataFrame(candidate_rows("STOCK", {5: 0.08}))
    changed_current = baseline.copy()
    changed_current.loc[changed_current["date"].eq(pd.Timestamp("2024-01-06")), "relative_abnormal_return"] = 8.0

    first = detect_events(baseline, event_config(cooldown_period=0))
    changed = detect_events(changed_current, event_config(cooldown_period=0))
    first_vol = first.loc[first["date"].eq(pd.Timestamp("2024-01-06")), "relative_volatility"].item()
    changed_vol = changed.loc[changed["date"].eq(pd.Timestamp("2024-01-06")), "relative_volatility"].item()

    assert first_vol == pytest.approx(changed_vol)
    assert first_vol == pytest.approx(np.std([-0.01, 0.01, -0.01, 0.01, 0.0], ddof=1))


def test_repeated_shocks_within_firm_cooldown_produce_one_event() -> None:
    frame = pd.DataFrame(candidate_rows("STOCK", {5: 0.08, 7: -0.09}))

    events = detect_events(frame, event_config(cooldown_period=3, cooldown_scope="firm"))

    assert events["date"].tolist() == [pd.Timestamp("2024-01-06")]


def test_peer_group_cooldown_blocks_later_related_firm() -> None:
    frame = pd.DataFrame(
        candidate_rows("A", {5: 0.08}) + candidate_rows("B", {7: -0.09})
    )

    events = detect_events(frame, event_config(cooldown_period=3, cooldown_scope="peer_group"))

    assert events["security_id"].tolist() == ["A"]


def test_simultaneous_related_movers_share_group_without_forced_leader() -> None:
    frame = pd.DataFrame(
        candidate_rows("A", {5: 0.08}) + candidate_rows("B", {5: -0.09})
    )

    events = detect_events(frame, event_config(cooldown_scope="both"))

    assert set(events["security_id"]) == {"A", "B"}
    assert events["simultaneous_event_group"].notna().all()
    assert events["simultaneous_event_group"].nunique() == 1


def test_insufficient_peer_count_is_excluded() -> None:
    frame = pd.DataFrame(candidate_rows("STOCK", {5: 0.08}, peer_count=1))

    assert detect_events(frame, event_config(minimum_peer_count=2)).empty


def test_insufficient_history_is_excluded() -> None:
    frame = pd.DataFrame(candidate_rows("STOCK", {4: 0.08}))

    assert detect_events(frame, event_config()).empty


@pytest.mark.parametrize("action", ["split", "merger", "abnormal_price_adjustment", "unknown"])
def test_configured_corporate_actions_are_excluded(action: str) -> None:
    frame = pd.DataFrame(candidate_rows("STOCK", {5: 0.08}))
    frame.loc[frame["date"].eq(pd.Timestamp("2024-01-06")), "corporate_action_type"] = action

    assert detect_events(frame, event_config()).empty


def test_metadata_placeholders_default_false_and_market_cap_can_be_missing() -> None:
    frame = pd.DataFrame(candidate_rows("STOCK", {5: 0.08})).drop(columns="market_cap")

    event = detect_events(frame, event_config()).iloc[0]

    assert pd.isna(event["market_cap"])
    assert not event["earnings_flag"]
    assert not event["news_identified_flag"]
