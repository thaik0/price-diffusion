import pandas as pd

from price_diffusion.robustness_analysis import (
    _bootstrap_summary,
    _placebo_report_table,
)


def test_bootstrap_summary_persists_only_compact_statistics() -> None:
    distribution = pd.DataFrame(
        {
            "bootstrap_method": ["event", "event"],
            "horizon": [5, 5],
            "return_specification": ["adjusted", "adjusted"],
            "peer_definition": ["economic", "economic"],
            "outcome": ["peer_catchup", "peer_catchup"],
            "statistic": [0.01, 0.03],
            "sample_size": [10, 12],
        }
    )

    summary = _bootstrap_summary(distribution)

    assert list(summary.columns) == [
        "bootstrap_method",
        "horizon",
        "return_specification",
        "peer_definition",
        "outcome",
        "estimate",
        "ci_lower",
        "ci_upper",
        "bootstrap_iterations",
        "sample_size",
    ]
    assert summary.loc[0, "estimate"] == 0.02
    assert summary.loc[0, "bootstrap_iterations"] == 2
    assert summary.loc[0, "sample_size"] == 11


def test_placebo_report_labels_stored_counts_at_iteration_granularity() -> None:
    placebo = pd.DataFrame(
        {
            "horizon": [5],
            "outcome": ["peer_catchup"],
            "method": ["null_simulation"],
            "mean": [0.001],
            "ci_lower": [-0.01],
            "ci_upper": [0.01],
            "sample_size": [82],
            "experiment_iterations": [500],
        }
    )

    displayed = _placebo_report_table(placebo, horizon=5, outcome="peer_catchup")

    assert displayed.loc[0, "events_per_iteration"] == 82
    assert displayed.loc[0, "resampling_iterations"] == 500
    assert "sample_size" not in displayed
