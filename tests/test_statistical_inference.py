import matplotlib
import numpy as np
import pandas as pd
import pytest
import statsmodels.formula.api as smf
from scipy import stats

from price_diffusion.statistical_inference import (
    InferenceConfig,
    StatisticalInferenceResult,
    calculate_event_time_statistics,
    fit_event_regressions,
    plot_event_time_with_confidence_intervals,
    plot_outcome_distributions,
    run_statistical_inference,
    save_inference_tables,
    summarize_event_outcomes,
)


matplotlib.use("Agg")


def outcome_frame() -> pd.DataFrame:
    convergence = [0.10, 0.20, -0.10, 0.00, np.nan]
    rows = []
    for index, value in enumerate(convergence):
        valid = index != 4
        peer = value / 2 if valid else np.nan
        reversal = value / 2 if valid else np.nan
        rows.append(
            {
                "event_id": f"e{index}",
                "event_date": pd.Timestamp("2024-01-02") + pd.Timedelta(days=index // 2),
                "security_id": f"firm{index // 2}",
                "direction": "positive" if index < 3 else "negative",
                "peer_definition": "economic",
                "subsector": "design" if index % 2 else "equipment",
                "horizon": 5,
                "return_specification": "semiconductor_adjusted",
                "initiator_car": -reversal if valid else np.nan,
                "peer_car": peer if valid else np.nan,
                "peer_catchup": peer,
                "initiator_reversal": reversal,
                "convergence": value,
                "initial_relative_shock": 0.08 if index < 3 else -0.08,
                "simultaneous_event_group": "g1" if index == 1 else pd.NA,
                "valid_horizon": valid,
                "missing_reason": None if valid else "missing_peer_observation",
            }
        )
    return pd.DataFrame(rows)


def regression_inputs(n: int = 80) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(7)
    rows = []
    characteristics = []
    for index in range(n):
        direction = "positive" if index % 2 == 0 else "negative"
        shock = (0.04 + index / 10_000) * (1 if direction == "positive" else -1)
        date = pd.Timestamp("2024-01-02") + pd.Timedelta(days=index % 20)
        volume = 1_000_000 + index * 11_000
        market_cap = 2_000_000_000 + index * 20_000_000
        peer_car = 0.01 + 0.35 * shock + rng.normal(0, 0.003)
        initiator_car = -0.005 - 0.20 * shock + rng.normal(0, 0.003)
        rows.append(
            {
                "event_id": f"event_{index}",
                "event_date": date,
                "security_id": f"firm_{index % 16}",
                "direction": direction,
                "peer_definition": "economic",
                "subsector": "design" if index % 3 else "equipment",
                "horizon": 5,
                "return_specification": "spec",
                "initial_relative_shock": shock,
                "simultaneous_event_group": "same_day" if index % 7 == 0 else pd.NA,
                "valid_horizon": True,
                "peer_car": peer_car,
                "initiator_car": initiator_car,
            }
        )
        characteristics.append(
            {
                "event_id": f"event_{index}",
                "volume": volume,
                "market_cap": market_cap,
                "market_volatility_regime": ("high" if index % 4 == 0 else "normal"),
                "semiconductor_volatility_regime": ("high" if index % 5 == 0 else "normal"),
                "information_date": date,
                "future_return": rng.normal(),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(characteristics)


def test_summary_statistics_and_analytical_interval_match_manual_calculation() -> None:
    outcomes = outcome_frame()
    summary, distribution, hypotheses, attrition = summarize_event_outcomes(
        outcomes, InferenceConfig(cluster_by=None)
    )
    row = summary.query("direction == 'all' and outcome == 'convergence'").iloc[0]
    values = np.array([0.10, 0.20, -0.10, 0.00])
    standard_error = stats.sem(values)
    critical = stats.t.ppf(0.975, len(values) - 1)

    assert row["mean"] == pytest.approx(values.mean())
    assert row["median"] == pytest.approx(0.05)
    assert row["standard_deviation"] == pytest.approx(values.std(ddof=1))
    assert row["standard_error"] == pytest.approx(standard_error)
    assert row["ci_lower"] == pytest.approx(values.mean() - critical * standard_error)
    assert row["ci_upper"] == pytest.approx(values.mean() + critical * standard_error)
    assert row["sample_size"] == 4
    assert row["proportion_positive"] == pytest.approx(0.5)
    assert {"minimum", "p05", "p25", "p75", "p95", "maximum"}.issubset(distribution.columns)
    assert hypotheses.query("direction == 'all' and outcome == 'convergence'")["alternative"].item() == "greater"
    assert hypotheses.query("direction == 'all' and outcome == 'peer_catchup'")["alternative"].item() == "two-sided"
    assert attrition.query("direction == 'all'")["invalid_horizons"].item() == 1


def test_clustered_mean_standard_error_matches_statsmodels() -> None:
    outcomes, *_ = (outcome_frame(),)
    summary, _, tests, _ = summarize_event_outcomes(outcomes, InferenceConfig(cluster_by="firm"))
    sample = outcomes.loc[outcomes["valid_horizon"]].copy()
    expected = smf.ols("convergence ~ 1", data=sample).fit(
        cov_type="cluster",
        cov_kwds={"groups": pd.factorize(sample["security_id"], sort=True)[0], "use_correction": True},
        use_t=True,
    )
    row = summary.query("direction == 'all' and outcome == 'convergence'").iloc[0]
    test = tests.query("direction == 'all' and outcome == 'convergence'").iloc[0]
    assert row["standard_error"] == pytest.approx(expected.bse.iloc[0])
    assert test["cluster_count"] == 2


def test_bootstrap_interval_is_reproducible_and_reports_analytical_test() -> None:
    config = InferenceConfig(
        interval_method="bootstrap", bootstrap_iterations=300, random_seed=11, cluster_by=None
    )
    first = summarize_event_outcomes(outcome_frame(), config)[0]
    second = summarize_event_outcomes(outcome_frame(), config)[0]
    pd.testing.assert_frame_equal(first, second)
    row = first.query("direction == 'all' and outcome == 'convergence'").iloc[0]
    assert row["interval_method"] == "bootstrap"
    assert np.isfinite(row["bootstrap_standard_error"])
    assert row["ci_lower"] <= row["mean"] <= row["ci_upper"]
    assert np.isfinite(row["p_value"])


def test_missing_events_are_retained_transparently() -> None:
    summary, _, _, attrition = summarize_event_outcomes(outcome_frame(), InferenceConfig(cluster_by=None))
    row = attrition.query("direction == 'all'").iloc[0]
    assert row["total_events"] == 5
    assert row["valid_horizons"] == 4
    assert row["invalid_horizons"] == 1
    assert row["missing_reasons"] == "missing_peer_observation"
    assert summary.query("direction == 'all'")["sample_size"].eq(4).all()


def test_single_cluster_cell_keeps_descriptives_and_marks_inference_undefined() -> None:
    outcomes = outcome_frame().iloc[:2].copy()
    outcomes["security_id"] = "only_firm"
    summary, _, tests, _ = summarize_event_outcomes(outcomes, InferenceConfig(cluster_by="firm"))
    row = summary.query("direction == 'all' and outcome == 'convergence'").iloc[0]
    test = tests.query("direction == 'all' and outcome == 'convergence'").iloc[0]
    assert row["sample_size"] == 2
    assert row["mean"] == pytest.approx(0.15)
    assert np.isnan(row["standard_error"])
    assert test["cluster_count"] == 1
    assert np.isnan(test["p_value"])


@pytest.mark.parametrize("cluster_by", ["firm", "event_date", "two_way"])
def test_regression_clustering_options_work(cluster_by: str) -> None:
    outcomes, characteristics = regression_inputs()
    table = fit_event_regressions(outcomes, characteristics, cluster_by=cluster_by)
    assert set(table["dependent_variable"]) == {"peer_car", "initiator_car"}
    assert {"coefficient", "standard_error", "ci_lower", "ci_upper", "p_value", "sample_size"}.issubset(table.columns)
    assert table["sample_size"].eq(80).all()
    assert table["cluster_by"].eq(cluster_by).all()


def test_regression_uses_fixed_contemporaneous_design_and_rejects_future_dates() -> None:
    outcomes, characteristics = regression_inputs()
    first = fit_event_regressions(outcomes, characteristics, cluster_by="firm")
    changed = characteristics.copy()
    changed["future_return"] = changed["future_return"] * 1_000_000
    second = fit_event_regressions(outcomes, changed, cluster_by="firm")
    pd.testing.assert_frame_equal(first, second)
    assert not first["term"].str.contains("future", case=False).any()

    future = characteristics.copy()
    future.loc[0, "information_date"] = outcomes.loc[0, "event_date"] + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="after the event"):
        fit_event_regressions(outcomes, future)


def test_event_time_statistics_use_post_event_cumulative_returns() -> None:
    rows = []
    for event, firm, direction, scale in (("a", "x", "positive", 1.0), ("b", "y", "negative", -1.0)):
        for day in (1, 2):
            rows.append(
                {
                    "event_id": event,
                    "event_date": pd.Timestamp("2024-01-02"),
                    "security_id": firm,
                    "relative_day": day,
                    "direction": direction,
                    "peer_definition": "economic",
                    "return_specification": "spec",
                    "initiator_return": 0.01 * scale,
                    "peer_return": 0.02 * scale,
                    "valid_observation": True,
                }
            )
    panel = pd.DataFrame(rows)
    table = calculate_event_time_statistics(panel, InferenceConfig(cluster_by=None))
    positive = table.query("relative_day == 2 and direction == 'positive' and outcome == 'convergence'").iloc[0]
    negative = table.query("relative_day == 2 and direction == 'negative' and outcome == 'convergence'").iloc[0]
    assert positive["mean"] == pytest.approx(0.02)
    assert negative["mean"] == pytest.approx(0.02)
    assert positive["sample_size"] == 1

    bootstrap = calculate_event_time_statistics(
        panel,
        InferenceConfig(interval_method="bootstrap", bootstrap_iterations=100, cluster_by=None),
    )
    combined = bootstrap.query("relative_day == 2 and direction == 'all' and outcome == 'convergence'").iloc[0]
    assert np.isfinite(combined["ci_lower"])
    assert np.isfinite(combined["ci_upper"])


def test_reporting_plots_and_saved_tables(tmp_path) -> None:
    outcomes = outcome_frame()
    result = run_statistical_inference(outcomes, config=InferenceConfig(cluster_by=None))
    paths = save_inference_tables(result, tmp_path)
    assert set(paths) == {"summary", "distribution", "hypotheses", "attrition", "regressions", "event_time"}
    assert all(path.exists() for path in paths.values())

    statistics = pd.DataFrame(
        {
            "relative_day": [1, 1, 1, 2, 2, 2],
            "direction": ["all"] * 6,
            "outcome": ["initiator_car", "peer_car", "convergence"] * 2,
            "mean": [0.01, 0.02, 0.01, 0.00, 0.03, 0.03],
            "ci_lower": [0.0] * 6,
            "ci_upper": [0.04] * 6,
        }
    )
    figure, _ = plot_event_time_with_confidence_intervals(statistics)
    distribution_figure, axes = plot_outcome_distributions(outcomes)
    assert len(figure.axes) == 1
    assert axes.shape == (3, 2)
    matplotlib.pyplot.close(figure)
    matplotlib.pyplot.close(distribution_figure)


def test_configuration_validation_prevents_unsupported_bootstrap() -> None:
    with pytest.raises(ValueError, match="two-way"):
        InferenceConfig(interval_method="bootstrap", cluster_by="two_way").validate()
