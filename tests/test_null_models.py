import matplotlib
import numpy as np
import pandas as pd
import pytest

from price_diffusion.event_study import EventStudyConfig, run_event_study
from price_diffusion.events import EventDetectionConfig
from price_diffusion.null_models import (
    RobustnessConfig,
    build_comparison_table,
    compare_observed_to_null,
    dependence_aware_bootstrap,
    plot_null_distribution,
    plot_placebo_comparison,
    resample_returns_without_lead_lag,
    run_random_peer_placebo,
    run_selection_preserving_null,
    sample_pseudo_events,
    sample_random_peer_membership,
    temporal_placebo,
    validate_random_peer_placebo,
)


matplotlib.use("Agg")


def placebo_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2024-01-02", periods=10)
    event_date = dates[3]
    events = pd.DataFrame(
        [
            {
                "event_id": "real_1",
                "date": event_date,
                "security_id": "A",
                "direction": "positive",
                "peer_definition": "economic",
                "subsector": "design",
                "relative_return": 0.08,
                "relative_volatility": 0.01,
                "simultaneous_event_group": pd.NA,
                "earnings_flag": False,
            }
        ]
    )
    values = {
        "A": [0, 0, 0, 0.08, -0.01, -0.01, 0, 0, 0, 0],
        "B": [0, 0, 0, 0.01, 0.02, 0.01, 0, 0, 0, 0],
        "C": [0, 0, 0, 0.00, 0.01, 0.00, 0, 0, 0, 0],
        "D": [0, 0, 0, -0.01, -0.02, 0.00, 0, 0, 0, 0],
    }
    returns = pd.DataFrame(
        [
            {"date": date, "security_id": firm, "abnormal": value}
            for firm, observations in values.items()
            for date, value in zip(dates, observations, strict=True)
        ]
    )
    economic = pd.DataFrame(
        [
            {
                "date": event_date,
                "security_id": "A",
                "peer_id": peer,
                "peer_definition": "economic",
                "weight": weight,
            }
            for peer, weight in (("B", 0.7), ("C", 0.3))
        ]
    )
    universe = pd.DataFrame(
        [
            {"date": date, "security_id": firm, "eligible": True}
            for date in dates
            for firm in values
        ]
    )
    return events, returns, economic, universe


def study_config() -> EventStudyConfig:
    return EventStudyConfig(
        primary_horizons=(1, 2), descriptive_horizons=(), pre_event_days=2, post_event_days=2
    )


def test_random_peer_placebo_preserves_count_weights_and_eligibility() -> None:
    events, _, economic, universe = placebo_inputs()
    random = sample_random_peer_membership(
        events, economic, universe, random_seed=9
    )
    assert len(random) == 2
    assert not random["peer_id"].eq("A").any()
    assert sorted(random["weight"]) == pytest.approx([0.3, 0.7])
    assert random["weight"].sum() == pytest.approx(1.0)

    broken = random.copy()
    broken.loc[0, "peer_id"] = "A"
    with pytest.raises(ValueError, match="exclude"):
        validate_random_peer_placebo(broken, events, economic, universe)


def test_random_peer_event_results_preserve_event_count_each_iteration() -> None:
    events, returns, economic, universe = placebo_inputs()
    result = run_random_peer_placebo(
        events,
        returns,
        economic,
        universe,
        study_config(),
        return_column="abnormal",
        return_specification="spec",
        config=RobustnessConfig(
            random_peer_iterations=3,
            pseudo_event_iterations=1,
            null_iterations=1,
            bootstrap_iterations=1,
        ),
    )
    counts = result.groupby("placebo_iteration")["event_id"].nunique()
    assert counts.eq(len(events)).all()
    assert set(result["method"]) == {"random_peers"}


def test_pseudo_events_match_company_strata_and_eligibility() -> None:
    events, _, economic, universe = placebo_inputs()
    event_date = events.loc[0, "date"]
    candidate_date = pd.Timestamp("2024-02-01")
    matching = pd.DataFrame(
        [
            {
                "date": event_date,
                "security_id": "A",
                "eligible": True,
                "subsector": "design",
                "volatility_regime": "high",
                "market_regime": "up",
                "liquidity_bucket": "large",
            },
            {
                "date": candidate_date,
                "security_id": "A",
                "eligible": True,
                "subsector": "design",
                "volatility_regime": "high",
                "market_regime": "up",
                "liquidity_bucket": "large",
            },
            {
                "date": pd.Timestamp("2024-03-01"),
                "security_id": "A",
                "eligible": False,
                "subsector": "design",
                "volatility_regime": "high",
                "market_regime": "up",
                "liquidity_bucket": "large",
            },
        ]
    )
    candidate_peers = economic.assign(date=candidate_date)
    memberships = pd.concat([economic, candidate_peers], ignore_index=True)
    pseudo = sample_pseudo_events(
        events,
        matching,
        memberships,
        match_columns=(
            "subsector",
            "volatility_regime",
            "market_regime",
            "liquidity_bucket",
        ),
        exclusion_days=5,
        random_seed=1,
    )
    assert len(pseudo) == len(events)
    assert pseudo.loc[0, "date"] == candidate_date
    assert pseudo.loc[0, "security_id"] == events.loc[0, "security_id"]
    assert pseudo.loc[0, "source_event_id"] == "real_1"


def test_temporal_placebo_uses_pre_event_not_post_event_returns() -> None:
    events, returns, economic, _ = placebo_inputs()
    event_date = events.loc[0, "date"]
    previous_date = returns.loc[returns["date"].lt(event_date), "date"].max()
    returns.loc[
        returns["date"].eq(previous_date) & returns["security_id"].eq("A"), "abnormal"
    ] = -0.03
    returns.loc[
        returns["date"].eq(previous_date) & returns["security_id"].eq("B"), "abnormal"
    ] = 0.01
    returns.loc[
        returns["date"].eq(previous_date) & returns["security_id"].eq("C"), "abnormal"
    ] = 0.01
    observed = run_event_study(
        events,
        returns,
        economic,
        study_config(),
        return_column="abnormal",
        return_specification="spec",
    )
    placebo = temporal_placebo(events, observed.event_panel, study_config())
    one_day = placebo.loc[placebo["horizon"].eq(1)].iloc[0]
    assert one_day["initiator_car"] == pytest.approx(-0.03)
    assert one_day["peer_car"] == pytest.approx(0.01)
    assert one_day["convergence"] == pytest.approx(0.04)


def simulation_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2024-01-02", periods=35)
    firms = ["A", "B", "C", "D"]
    rng = np.random.default_rng(123)
    rows = []
    for position, date in enumerate(dates):
        market = 0.002 * np.sin(position / 3)
        residual = rng.normal(0, 0.007, len(firms))
        if position in {8, 14, 20, 26}:
            residual[position // 6 % len(firms)] += 0.06
        for firm, value in zip(firms, residual, strict=True):
            rows.append({"date": date, "security_id": firm, "abnormal": market + value})
    returns = pd.DataFrame(rows)
    peers = pd.DataFrame(
        [
            {
                "date": date,
                "security_id": firm,
                "peer_id": peer,
                "peer_definition": "economic",
                "weight": 1 / 3,
            }
            for date in dates
            for firm in firms
            for peer in firms
            if peer != firm
        ]
    )
    metadata = pd.DataFrame(
        [
            {
                "date": date,
                "security_id": firm,
                "peer_definition": "economic",
                "peer_group": "all_semis",
                "subsector": "design",
                "corporate_action_type": "none",
                "volume": 1_000_000.0,
                "market_cap": 1_000_000_000.0,
            }
            for date in dates
            for firm in firms
        ]
    )
    return returns, peers, metadata


def test_synchronous_null_preserves_common_component_and_never_uses_future() -> None:
    returns, _, _ = simulation_inputs()
    regimes = pd.DataFrame(
        {
            "date": sorted(returns["date"].unique()),
            "market_regime": ["calm"] * returns["date"].nunique(),
        }
    )
    simulated, audit = resample_returns_without_lead_lag(
        returns,
        return_column="abnormal",
        date_regimes=regimes,
        regime_columns=("market_regime",),
        random_seed=7,
    )
    original_mean = returns.groupby("date")["abnormal"].mean()
    simulated_mean = simulated.groupby("date")["abnormal"].mean()
    pd.testing.assert_series_equal(original_mean, simulated_mean)
    assert (audit["source_date"] <= audit["target_date"]).all()
    assert not audit["future_data_used"].any()


def test_selection_preserving_null_redetects_events_with_same_methodology() -> None:
    returns, peers, metadata = simulation_inputs()
    detector = EventDetectionConfig(
        minimum_relative_move=0.012,
        volatility_window=5,
        threshold_multiplier=1.0,
        cooldown_period=0,
        minimum_peer_count=2,
        minimum_history_requirement=5,
        cooldown_scope="none",
    )
    robustness = RobustnessConfig(
        random_peer_iterations=1,
        pseudo_event_iterations=1,
        null_iterations=3,
        bootstrap_iterations=2,
        random_seed=17,
    )
    result = run_selection_preserving_null(
        returns,
        peers,
        metadata,
        detector,
        study_config(),
        return_column="abnormal",
        return_specification="spec",
        config=robustness,
    )
    assert len(result.diagnostics) == 3
    assert result.diagnostics["detection_config_signature"].nunique() == 1
    assert result.diagnostics["event_study_config_signature"].nunique() == 1
    assert not result.diagnostics["future_data_used"].any()
    assert result.diagnostics["detected_event_count"].gt(0).all()
    assert set(result.distribution["outcome"]) == {
        "convergence",
        "peer_catchup",
        "initiator_reversal",
    }


def simple_outcomes() -> pd.DataFrame:
    rows = []
    for index, convergence in enumerate((0.05, 0.03, 0.07, 0.01)):
        rows.append(
            {
                "event_id": f"e{index}",
                "event_date": pd.Timestamp("2024-01-02") + pd.Timedelta(days=index // 2),
                "security_id": f"f{index // 2}",
                "direction": "positive",
                "peer_definition": "economic",
                "horizon": 1,
                "return_specification": "spec",
                "valid_horizon": True,
                "convergence": convergence,
                "peer_catchup": convergence / 2,
                "initiator_reversal": convergence / 2,
            }
        )
    return pd.DataFrame(rows)


def test_null_comparison_empirical_p_value_and_percentile() -> None:
    observed = simple_outcomes()
    null = pd.DataFrame(
        [
            {
                "null_iteration": index,
                "horizon": 1,
                "return_specification": "spec",
                "peer_definition": "economic",
                "outcome": outcome,
                "statistic": value,
                "sample_size": 4,
            }
            for outcome in ("convergence", "peer_catchup", "initiator_reversal")
            for index, value in enumerate((0.0, 0.01, 0.02))
        ]
    )
    comparison = compare_observed_to_null(observed, null)
    row = comparison.loc[comparison["outcome"].eq("convergence")].iloc[0]
    assert row["observed_statistic"] == pytest.approx(0.04)
    assert row["null_mean"] == pytest.approx(0.01)
    assert row["empirical_p_value"] == pytest.approx(0.25)
    assert row["percentile_location"] == pytest.approx(100.0)


@pytest.mark.parametrize("method", ["firm", "date"])
def test_dependence_aware_bootstrap_supports_firm_and_date_blocks(method: str) -> None:
    distribution = dependence_aware_bootstrap(
        simple_outcomes(),
        method=method,
        iterations=5,
        date_block_length=2,
        random_seed=4,
    )
    assert distribution["bootstrap_iteration"].nunique() == 5
    assert set(distribution["outcome"]) == {
        "convergence",
        "peer_catchup",
        "initiator_reversal",
    }
    assert distribution["bootstrap_method"].eq(method).all()


def test_comparison_tables_and_visualizations_cover_all_outcomes() -> None:
    observed = simple_outcomes()
    random = pd.concat(
        [observed.assign(placebo_iteration=index, method="random_peers") for index in range(3)],
        ignore_index=True,
    )
    pseudo = pd.concat(
        [observed.assign(placebo_iteration=index, method="pseudo_events") for index in range(3)],
        ignore_index=True,
    )
    null = pd.DataFrame(
        [
            {
                "null_iteration": index,
                "horizon": 1,
                "return_specification": "spec",
                "peer_definition": "economic",
                "outcome": outcome,
                "statistic": 0.005 * index,
                "sample_size": 4,
            }
            for index in range(5)
            for outcome in ("convergence", "peer_catchup", "initiator_reversal")
        ]
    )
    table = build_comparison_table(
        observed,
        random_peer_outcomes=random,
        pseudo_event_outcomes=pseudo,
        null_distribution=null,
        bootstrap_iterations=20,
    )
    assert set(table["method"]) == {
        "observed",
        "random_peers",
        "pseudo_events",
        "null_simulation",
    }
    assert set(table["outcome"]) == {
        "convergence",
        "peer_catchup",
        "initiator_reversal",
    }
    comparison = compare_observed_to_null(observed, null)
    null_figure, _ = plot_null_distribution(null, comparison, horizon=1)
    placebo_figure, axes = plot_placebo_comparison(table, horizon=1)
    assert len(null_figure.axes) == 1
    assert len(axes) == 3
    matplotlib.pyplot.close(null_figure)
    matplotlib.pyplot.close(placebo_figure)
