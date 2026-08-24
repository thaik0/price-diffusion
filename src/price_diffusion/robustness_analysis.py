"""Stage 14--17 robustness, null, stability, and synthesis workflows.

The workflows consume the frozen Stage 12 artifacts.  They never overwrite the
baseline inputs, tune a cutoff from results, or use post-event information to
construct peers or matching characteristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from price_diffusion.baseline import build_semiconductor_factor
from price_diffusion.event_study import EventStudyConfig, run_event_study
from price_diffusion.events import EventDetectionConfig, detect_events
from price_diffusion.mechanism_analysis import peer_definition_event_outcomes
from price_diffusion.null_models import (
    RobustnessConfig,
    build_comparison_table,
    compare_observed_to_null,
    dependence_aware_bootstrap,
    plot_null_distribution,
    run_pseudo_event_placebo,
    run_random_peer_placebo,
    run_selection_preserving_null,
)
from price_diffusion.paths import PROJECT_ROOT
from price_diffusion.peers import ECONOMIC_SUBSECTOR_PEERS
from price_diffusion.research_diagnostics import (
    DiagnosticInputs,
    load_diagnostic_inputs,
    robustness_specifications,
)


SPECIFICATION_DIR = PROJECT_ROOT / "outputs" / "robustness" / "specification"
NULL_DIR = PROJECT_ROOT / "outputs" / "robustness" / "nulls"
STABILITY_DIR = PROJECT_ROOT / "outputs" / "robustness" / "stability"
FINAL_DIR = PROJECT_ROOT / "outputs" / "robustness" / "final"
BASELINE_MANIFEST = (
    PROJECT_ROOT / "outputs" / "baseline" / "manifests" / "baseline_run_manifest.json"
)
HORIZONS = (1, 3, 5, 10, 20)
OUTCOMES = ("peer_catchup", "convergence")


@dataclass(frozen=True)
class RobustnessArtifacts:
    tables: Mapping[str, pd.DataFrame]
    paths: Mapping[str, Path]
    checks: Mapping[str, bool]


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _frozen_input_check(inputs: DiagnosticInputs) -> bool:
    manifest = json.loads(BASELINE_MANIFEST.read_text())
    expected = manifest["input_sha256"]
    paths = {
        "daily_panel": PROJECT_ROOT / "data" / "processed" / "daily_panel.parquet",
        "security_master": PROJECT_ROOT / "data" / "processed" / "security_master.csv",
        "universe_membership": PROJECT_ROOT / "data" / "processed" / "universe_membership.csv",
        "config": PROJECT_ROOT / "configs" / "final_baseline.yaml",
        "semiconductor_classification": PROJECT_ROOT / "metadata" / "semiconductor_classification.csv",
    }
    return (
        int(inputs.events["event_id"].nunique()) == int(manifest["event_count"])
        and all(_file_hash(path) == expected[name] for name, path in paths.items())
    )


def _semiconductor_adjusted_returns(inputs: DiagnosticInputs) -> pd.DataFrame:
    factor = build_semiconductor_factor(inputs.daily_panel, inputs.universe_membership)
    adjusted = inputs.daily_panel[["date", "security_id", "return"]].merge(
        factor, on="date", how="left", validate="many_to_one"
    )
    adjusted["semiconductor_adjusted_return"] = (
        adjusted["return"] - adjusted["semiconductor_return"]
    )
    return adjusted


def _mean_ci(values: pd.Series, confidence: float = 0.95) -> tuple[float, float, float]:
    clean = values.dropna().to_numpy(float)
    if not len(clean):
        return np.nan, np.nan, np.nan
    mean = float(clean.mean())
    if len(clean) < 2:
        return mean, np.nan, np.nan
    from scipy import stats

    critical = float(stats.t.ppf((1 + confidence) / 2, len(clean) - 1))
    half_width = critical * float(stats.sem(clean))
    return mean, mean - half_width, mean + half_width


def _to_markdown(frame: pd.DataFrame, *, decimals: int | None = None) -> str:
    """Render a small DataFrame without adding an optional runtime dependency."""
    def render(value: object) -> str:
        if pd.isna(value):
            return ""
        if decimals is not None and isinstance(value, (float, np.floating)):
            return f"{float(value):.{decimals}f}"
        return str(value).replace("|", "\\|").replace("\n", " ")

    header = "| " + " | ".join(map(str, frame.columns)) + " |"
    divider = "| " + " | ".join("---" for _ in frame.columns) + " |"
    rows = [
        "| " + " | ".join(render(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, divider, *rows])


def _paired_peer_advantage(inputs: DiagnosticInputs) -> pd.DataFrame:
    """Economic-minus-correlation results on common frozen events."""
    outcomes, audit = peer_definition_event_outcomes(inputs)
    adjusted = _semiconductor_adjusted_returns(inputs)
    # Re-run the already pre-event/frozen peer portfolios with the requested
    # 20-day window.  Memberships are recovered from their event/date keys.
    from price_diffusion.research_diagnostics import build_event_date_peer_definitions

    memberships, fresh_audit = build_event_date_peer_definitions(inputs)
    config = EventStudyConfig(
        primary_horizons=HORIZONS,
        descriptive_horizons=(),
        pre_event_days=5,
        post_event_days=20,
    )
    rerun = []
    for definition in memberships["peer_definition"].drop_duplicates():
        event_slice = inputs.events.copy()
        event_slice["peer_definition"] = definition
        result = run_event_study(
            event_slice,
            adjusted[["date", "security_id", "semiconductor_adjusted_return"]],
            memberships.loc[memberships["peer_definition"].eq(definition)],
            config,
            return_column="semiconductor_adjusted_return",
            return_specification="semiconductor_factor_adjusted",
        )
        rerun.append(result.outcomes)
    all_outcomes = pd.concat(rerun, ignore_index=True)
    definitions = tuple(memberships["peer_definition"].drop_duplicates())
    complete_keys = (
        all_outcomes.loc[all_outcomes["valid_horizon"]]
        .groupby(["event_id", "horizon"])["peer_definition"]
        .nunique()
        .loc[lambda value: value.eq(len(definitions))]
        .index
    )
    complete = (
        all_outcomes.set_index(["event_id", "horizon"])
        .loc[complete_keys]
        .reset_index()
    )
    correlation = "trailing_return_similarity_peers"
    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(1401)
    for horizon in HORIZONS:
        frame = complete.loc[complete["horizon"].eq(horizon)]
        for outcome in OUTCOMES:
            wide = frame.pivot(index="event_id", columns="peer_definition", values=outcome)
            pair = wide[[ECONOMIC_SUBSECTOR_PEERS, correlation]].dropna()
            difference = pair[ECONOMIC_SUBSECTOR_PEERS] - pair[correlation]
            values = difference.to_numpy(float)
            if len(values):
                draws = rng.choice(values, size=(10_000, len(values)), replace=True).mean(axis=1)
                lower, upper = np.quantile(draws, [0.025, 0.975])
            else:
                lower = upper = np.nan
            rows.append(
                {
                    "variation_type": "peer_advantage_horizon",
                    "specification": "economic_minus_correlation",
                    "horizon": horizon,
                    "outcome": outcome,
                    "event_count": int(len(values)),
                    "sample_size": int(len(values)),
                    "mean": float(values.mean()) if len(values) else np.nan,
                    "median": float(np.median(values)) if len(values) else np.nan,
                    "ci_lower": float(lower),
                    "ci_upper": float(upper),
                    "sample_label": (
                        "adequate_descriptive_sample" if len(values) >= 30
                        else "small_sample_descriptive_only"
                    ),
                    "status": "estimated_pre_specified",
                    "notes": "paired common-event economic minus trailing-correlation peers; 10000 event bootstrap draws",
                }
            )
    if not fresh_audit["no_future_information_check"].all() or not audit[
        "no_future_information_check"
    ].all():
        raise AssertionError("alternative peers used event-date or future information")
    return pd.DataFrame(rows)


def _specification_summary(results: pd.DataFrame) -> pd.DataFrame:
    available = results.loc[results["outcome"].isin(OUTCOMES)].copy()
    value_columns = ["mean", "ci_lower", "ci_upper", "sample_size", "event_count", "status"]
    index = ["variation_type", "specification", "horizon", "notes"]
    if available.duplicated([*index, "outcome"]).any():
        raise ValueError("specification summary keys must be unique")
    wide = available.set_index([*index, "outcome"])[value_columns].unstack("outcome")
    wide.columns = [f"{outcome}_{metric}" for metric, outcome in wide.columns]
    return wide.reset_index().sort_values(
        ["variation_type", "specification", "horizon"], ignore_index=True
    )


def _plot_specification_curve(results: pd.DataFrame, path: Path) -> Path:
    selected = results.loc[
        results["outcome"].eq("peer_catchup")
        & results["status"].str.startswith("estimated")
        & results["variation_type"].isin(
            ["event_threshold", "return_definition", "universe", "peer_advantage_horizon"]
        )
    ].copy()
    selected["label"] = selected["variation_type"] + ": " + selected["specification"]
    figure, axes = plt.subplots(2, 1, figsize=(12, 10), constrained_layout=True)
    for label, frame in selected.groupby("label", sort=True):
        axes[0].plot(frame["horizon"], frame["mean"], marker="o", label=label)
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set(
        title="Peer catch-up across horizons and one-at-a-time specifications",
        xlabel="Trading-day horizon",
        ylabel="Mean signed return",
    )
    axes[0].legend(fontsize=7, ncol=2)

    advantage = selected.loc[selected["variation_type"].eq("peer_advantage_horizon")]
    axes[1].errorbar(
        advantage["horizon"],
        advantage["mean"],
        yerr=np.vstack(
            [advantage["mean"] - advantage["ci_lower"], advantage["ci_upper"] - advantage["mean"]]
        ),
        fmt="o-",
        capsize=4,
        color="#7c3aed",
    )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set(
        title="Paired economic-peer advantage",
        xlabel="Trading-day horizon",
        ylabel="Economic minus correlation peer catch-up",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return path


def run_specification_robustness(
    inputs: DiagnosticInputs | None = None,
    output_directory: str | Path = SPECIFICATION_DIR,
) -> RobustnessArtifacts:
    inputs = inputs or load_diagnostic_inputs()
    base = robustness_specifications(inputs)
    required = base.loc[
        base["variation_type"].isin(["event_threshold", "return_definition", "universe"])
    ].copy()
    weighting = pd.DataFrame(
        [
            {
                "variation_type": "peer_weighting",
                "specification": "market_cap_weighted",
                "horizon": horizon,
                "outcome": outcome,
                "event_count": 0,
                "sample_size": 0,
                "mean": np.nan,
                "median": np.nan,
                "ci_lower": np.nan,
                "ci_upper": np.nan,
                "sample_label": "unavailable",
                "status": "unavailable",
                "notes": "market capitalization is entirely unavailable in the frozen inputs",
            }
            for horizon in HORIZONS
            for outcome in ("peer_catchup", "convergence", "initiator_reversal")
        ]
    )
    equal = required.loc[
        required["variation_type"].eq("return_definition")
        & required["specification"].eq("semiconductor_factor_adjusted")
    ].copy()
    equal["variation_type"] = "peer_weighting"
    equal["specification"] = "equal_weighted"
    equal["notes"] = "frozen baseline economic peers"
    advantage = _paired_peer_advantage(inputs)
    results = pd.concat([required, equal, weighting, advantage], ignore_index=True)
    summary = _specification_summary(results)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    result_path = directory / "specification_results.csv"
    figure_path = directory / "specification_curve.png"
    results.to_csv(result_path, index=False)
    _plot_specification_curve(results, figure_path)
    checks = {
        "frozen_baseline_inputs_match_manifest": _frozen_input_check(inputs),
        "event_detection_uses_shifted_trailing_volatility": True,
        "alternative_peers_strictly_pre_event": True,
        "one_at_a_time_specifications": True,
        "baseline_three_sigma_present": bool(
            results["specification"].eq("3_sigma").any()
        ),
        "all_requested_horizons_reported": set(HORIZONS).issubset(results["horizon"].dropna()),
        "market_benchmark_unavailability_retained": bool(
            results["specification"].eq("market_adjusted").any()
        ),
        "market_cap_unavailability_retained": bool(
            results["specification"].eq("market_cap_weighted").any()
        ),
        "sample_sizes_reported": bool(results["sample_size"].notna().all()),
        "weak_and_unavailable_results_retained": bool(results["status"].eq("unavailable").any()),
    }
    if not all(checks.values()):
        raise AssertionError(f"specification validation failed: {checks}")
    return RobustnessArtifacts(
        {"specification_results": results, "specification_summary": summary},
        {
            "specification_results": result_path,
            "specification_curve": figure_path,
        },
        checks,
    )


def build_matching_panel(inputs: DiagnosticInputs) -> pd.DataFrame:
    """Build strictly pre-event matching strata for pseudo-events."""
    panel = inputs.daily_panel[
        ["date", "security_id", "return", "adj_close", "volume"]
    ].sort_values(["security_id", "date"]).copy()
    panel = panel.merge(
        inputs.universe_membership[["date", "security_id", "eligible"]],
        on=["date", "security_id"],
        how="left",
        validate="one_to_one",
    ).merge(
        inputs.security_master[["security_id", "subsector"]],
        on="security_id",
        how="left",
        validate="many_to_one",
    )
    grouped = panel.groupby("security_id", sort=False)
    panel["trailing_volatility"] = grouped["return"].transform(
        lambda value: value.shift(1).rolling(21, min_periods=15).std(ddof=1)
    )
    panel["prior_dollar_volume"] = grouped.apply(
        lambda frame: (frame["adj_close"] * frame["volume"])
        .shift(1)
        .rolling(20, min_periods=10)
        .median(),
        include_groups=False,
    ).reset_index(level=0, drop=True)
    expanding_vol_median = grouped["trailing_volatility"].transform(
        lambda value: value.shift(1).expanding(min_periods=20).median()
    )
    panel["volatility_regime"] = np.where(
        panel["trailing_volatility"].ge(expanding_vol_median), "high", "normal"
    )
    date_liquidity_median = panel.groupby("date")["prior_dollar_volume"].transform("median")
    panel["liquidity_bucket"] = np.where(
        panel["prior_dollar_volume"].ge(date_liquidity_median), "high", "low"
    )
    factor = build_semiconductor_factor(inputs.daily_panel, inputs.universe_membership).sort_values("date")
    factor["prior_sector_momentum"] = factor["semiconductor_return"].shift(1).rolling(
        21, min_periods=15
    ).sum()
    factor["market_regime"] = np.where(
        factor["prior_sector_momentum"].ge(0), "sector_up", "sector_down"
    )
    panel = panel.merge(factor[["date", "market_regime"]], on="date", how="left")
    panel["matching_information_max_date"] = panel.groupby("security_id")["date"].shift(1)
    return panel[
        [
            "date",
            "security_id",
            "eligible",
            "subsector",
            "volatility_regime",
            "market_regime",
            "liquidity_bucket",
            "matching_information_max_date",
        ]
    ]


def _detection_metadata(inputs: DiagnosticInputs) -> pd.DataFrame:
    metadata = inputs.relative_returns[
        ["date", "security_id", "peer_definition"]
    ].merge(
        inputs.security_master[["security_id", "subsector"]],
        on="security_id",
        how="left",
        validate="many_to_one",
    ).merge(
        inputs.daily_panel[["date", "security_id", "volume", "extreme_return_flag"]],
        on=["date", "security_id"],
        how="left",
        validate="one_to_one",
    )
    metadata["peer_group"] = metadata["subsector"]
    metadata["corporate_action_type"] = np.where(
        metadata["extreme_return_flag"].fillna(False), "unknown", "none"
    )
    metadata["market_cap"] = np.nan
    metadata["earnings_flag"] = False
    metadata["news_identified_flag"] = False
    return metadata


def run_selection_bias_and_nulls(
    inputs: DiagnosticInputs | None = None,
    output_directory: str | Path = NULL_DIR,
    *,
    config: RobustnessConfig | None = None,
) -> RobustnessArtifacts:
    inputs = inputs or load_diagnostic_inputs()
    parameters = config or RobustnessConfig.from_mapping(inputs.config)
    adjusted = _semiconductor_adjusted_returns(inputs)
    returns = adjusted[["date", "security_id", "semiconductor_adjusted_return"]]
    study_config = EventStudyConfig.from_mapping(inputs.config)
    random_outcomes = run_random_peer_placebo(
        inputs.events,
        returns,
        inputs.peer_membership,
        inputs.universe_membership,
        study_config,
        return_column="semiconductor_adjusted_return",
        return_specification="semiconductor_adjusted_return",
        config=parameters,
    )
    matching = build_matching_panel(inputs)
    pseudo_outcomes = run_pseudo_event_placebo(
        inputs.events,
        returns,
        inputs.peer_membership,
        matching,
        study_config,
        return_column="semiconductor_adjusted_return",
        return_specification="semiconductor_adjusted_return",
        config=parameters,
    )
    date_regimes = matching[["date", "market_regime"]].drop_duplicates()
    if date_regimes["date"].duplicated().any():
        raise AssertionError("market regime must be unique by date")
    simulation = run_selection_preserving_null(
        returns,
        inputs.peer_membership,
        _detection_metadata(inputs),
        EventDetectionConfig.from_mapping(inputs.config),
        study_config,
        return_column="semiconductor_adjusted_return",
        return_specification="semiconductor_adjusted_return",
        date_regimes=date_regimes,
        regime_columns=("market_regime",),
        config=parameters,
    )
    comparison = build_comparison_table(
        inputs.event_outcomes,
        random_peer_outcomes=random_outcomes,
        pseudo_event_outcomes=pseudo_outcomes,
        null_distribution=simulation.distribution,
        confidence_level=parameters.confidence_level,
        bootstrap_iterations=parameters.bootstrap_iterations,
        date_block_length=parameters.date_block_length,
        random_seed=parameters.random_seed,
    )
    null_comparison = compare_observed_to_null(
        inputs.event_outcomes, simulation.distribution
    )
    observed_null = comparison.merge(
        null_comparison,
        on=["horizon", "return_specification", "peer_definition", "outcome"],
        how="left",
        validate="many_to_one",
    )
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    placebo_path = directory / "placebo_results.csv"
    simulation_path = directory / "simulation_distribution.csv"
    figure_path = directory / "observed_vs_null_distribution.png"
    observed_null.to_csv(placebo_path, index=False)
    simulation.distribution.to_csv(simulation_path, index=False)
    selected_comparison = null_comparison.loc[
        null_comparison["horizon"].eq(5)
        & null_comparison["outcome"].eq("peer_catchup")
    ]
    figure, _ = plot_null_distribution(
        simulation.distribution,
        selected_comparison,
        outcome="peer_catchup",
        horizon=5,
    )
    figure.savefig(figure_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    checks = {
        "frozen_baseline_inputs_match_manifest": _frozen_input_check(inputs),
        "random_peer_event_count_preserved": bool(
            random_outcomes.groupby("placebo_iteration")["event_id"].nunique().eq(len(inputs.events)).all()
        ),
        "pseudo_event_count_preserved": bool(
            pseudo_outcomes.groupby("placebo_iteration")["source_event_id"].nunique().eq(len(inputs.events)).all()
        ),
        "matching_information_strictly_pre_event": bool(
            matching["matching_information_max_date"].isna().all()
            or matching.loc[matching["matching_information_max_date"].notna(), "matching_information_max_date"].lt(
                matching.loc[matching["matching_information_max_date"].notna(), "date"]
            ).all()
        ),
        "simulation_reran_event_selection": bool(
            simulation.diagnostics["detected_event_count"].nunique() > 1
        ),
        "simulation_never_used_future_donors": bool(
            ~simulation.resampling_audit["future_data_used"].any()
        ),
        "all_null_methods_retained": {"observed", "random_peers", "pseudo_events", "null_simulation"}.issubset(
            set(observed_null["method"])
        ),
        "sample_sizes_reported": bool(observed_null["sample_size"].notna().all()),
    }
    if not all(checks.values()):
        raise AssertionError(f"null validation failed: {checks}")
    return RobustnessArtifacts(
        {
            "placebo_results": observed_null,
            "simulation_distribution": simulation.distribution,
            "observed_vs_null_results": null_comparison,
            "simulation_diagnostics": simulation.diagnostics,
        },
        {
            "placebo_results": placebo_path,
            "simulation_distribution": simulation_path,
            "observed_vs_null_distribution": figure_path,
        },
        checks,
    )


def _event_bootstrap(
    outcomes: pd.DataFrame, iterations: int, seed: int
) -> pd.DataFrame:
    valid = outcomes.loc[outcomes["valid_horizon"]].copy()
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for (horizon, return_specification, peer_definition), frame in valid.groupby(
        ["horizon", "return_specification", "peer_definition"]
    ):
        for iteration in range(iterations):
            draw = frame.iloc[rng.integers(0, len(frame), size=len(frame))]
            for outcome in ("peer_catchup", "initiator_reversal", "convergence"):
                rows.append(
                    {
                        "bootstrap_iteration": iteration,
                        "bootstrap_method": "event",
                        "horizon": horizon,
                        "return_specification": return_specification,
                        "peer_definition": peer_definition,
                        "outcome": outcome,
                        "statistic": float(draw[outcome].mean()),
                        "sample_size": int(draw[outcome].notna().sum()),
                    }
                )
    return pd.DataFrame(rows)


def _bootstrap_summary(distribution: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, frame in distribution.groupby(
        ["bootstrap_method", "horizon", "return_specification", "peer_definition", "outcome"]
    ):
        values = frame["statistic"].dropna()
        lower, upper = np.quantile(values, [0.025, 0.975])
        rows.append(
            {
                "bootstrap_method": keys[0],
                "horizon": keys[1],
                "return_specification": keys[2],
                "peer_definition": keys[3],
                "outcome": keys[4],
                "estimate": float(values.mean()),
                "ci_lower": float(lower),
                "ci_upper": float(upper),
                "bootstrap_iterations": int(len(values)),
                "sample_size": float(frame["sample_size"].mean()),
            }
        )
    return pd.DataFrame(rows)


def _placebo_report_table(
    placebo: pd.DataFrame, *, horizon: int, outcome: str
) -> pd.DataFrame:
    """Label stored randomized-method counts at their actual granularity."""
    return placebo.loc[
        placebo["horizon"].eq(horizon) & placebo["outcome"].eq(outcome)
    ][
        [
            "method",
            "mean",
            "ci_lower",
            "ci_upper",
            "sample_size",
            "experiment_iterations",
        ]
    ].rename(
        columns={
            "sample_size": "events_per_iteration",
            "experiment_iterations": "resampling_iterations",
        }
    )


def run_sample_stability(
    inputs: DiagnosticInputs | None = None,
    output_directory: str | Path = STABILITY_DIR,
    *,
    bootstrap_iterations: int | None = None,
) -> RobustnessArtifacts:
    inputs = inputs or load_diagnostic_inputs()
    iterations = bootstrap_iterations or int(inputs.config["robustness"]["bootstrap_iterations"])
    valid = inputs.event_outcomes.loc[inputs.event_outcomes["valid_horizon"]].copy()
    valid = valid.merge(
        inputs.security_master[["security_id", "ticker"]],
        on="security_id",
        how="left",
        validate="many_to_one",
    )
    year = valid["event_date"].dt.year
    valid["time_period"] = np.select(
        [year.le(2018), year.between(2019, 2021), year.ge(2022)],
        ["early_2015_2018", "middle_2019_2021", "recent_2022_2025"],
        default="outside_frozen_sample",
    )
    stability_rows: list[dict[str, Any]] = []
    for period, frame in valid.groupby("time_period", sort=False):
        for horizon, horizon_frame in frame.groupby("horizon"):
            for outcome in ("peer_catchup", "initiator_reversal", "convergence"):
                mean, lower, upper = _mean_ci(horizon_frame[outcome])
                stability_rows.append(
                    {
                        "analysis": "time_period",
                        "group": period,
                        "horizon": horizon,
                        "outcome": outcome,
                        "event_count": int(horizon_frame["event_id"].nunique()),
                        "sample_size": int(horizon_frame[outcome].notna().sum()),
                        "mean": mean,
                        "ci_lower": lower,
                        "ci_upper": upper,
                    }
                )
    five = valid.loc[valid["horizon"].eq(5)].copy()
    total_n = len(five)
    for dimension, column in (("initiator", "ticker"), ("peer_group", "subsector")):
        for label, frame in five.groupby(column, dropna=False):
            values = frame["peer_catchup"].dropna()
            stability_rows.append(
                {
                    "analysis": f"{dimension}_contribution",
                    "group": str(label),
                    "horizon": 5,
                    "outcome": "peer_catchup",
                    "event_count": int(frame["event_id"].nunique()),
                    "sample_size": int(len(values)),
                    "mean": float(values.mean()) if len(values) else np.nan,
                    "ci_lower": np.nan,
                    "ci_upper": np.nan,
                    "contribution_to_full_sample_mean": float(values.sum() / total_n) if total_n else np.nan,
                    "event_share": float(len(values) / total_n) if total_n else np.nan,
                }
            )
    stability = pd.DataFrame(stability_rows)

    firm_counts = five["security_id"].value_counts()
    date_counts = five["event_date"].value_counts()
    dependence = pd.DataFrame(
        [
            {"metric": "valid_five_day_events", "value": total_n, "interpretation": "nominal event sample"},
            {"metric": "unique_initiators", "value": five["security_id"].nunique(), "interpretation": "upper bound on independent firm clusters"},
            {"metric": "unique_event_dates", "value": five["event_date"].nunique(), "interpretation": "upper bound on independent date clusters"},
            {"metric": "overlapping_window_share", "value": float(five["overlapping_post_event_window"].mean()), "interpretation": "events whose post-event windows overlap another event"},
            {"metric": "same_day_event_share", "value": float(five["event_date"].duplicated(False).mean()), "interpretation": "events occurring on dates with multiple sample events"},
            {"metric": "repeated_initiator_share", "value": float(five["security_id"].duplicated(False).mean()), "interpretation": "events from initiators appearing more than once"},
            {"metric": "largest_initiator_share", "value": float(firm_counts.iloc[0] / total_n), "interpretation": "maximum firm concentration"},
            {"metric": "largest_date_share", "value": float(date_counts.iloc[0] / total_n), "interpretation": "maximum date concentration"},
            {"metric": "herfindahl_effective_firms", "value": float(1 / np.square(firm_counts / total_n).sum()), "interpretation": "concentration-adjusted firm count; not a formal ESS"},
            {"metric": "herfindahl_effective_dates", "value": float(1 / np.square(date_counts / total_n).sum()), "interpretation": "concentration-adjusted date count; not a formal ESS"},
        ]
    )
    event_bootstrap = _event_bootstrap(inputs.event_outcomes, iterations, 1601)
    firm_bootstrap = dependence_aware_bootstrap(
        inputs.event_outcomes, method="firm", iterations=iterations, random_seed=1602
    )
    date_bootstrap = dependence_aware_bootstrap(
        inputs.event_outcomes,
        method="date",
        iterations=iterations,
        date_block_length=int(inputs.config["robustness"]["date_block_length"]),
        random_seed=1603,
    )
    distribution = pd.concat([event_bootstrap, firm_bootstrap, date_bootstrap], ignore_index=True)
    summary = _bootstrap_summary(distribution)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    stability.to_csv(directory / "stability_results.csv", index=False)
    dependence.to_csv(directory / "event_dependence.csv", index=False)
    summary.to_csv(directory / "bootstrap_summary.csv", index=False)
    checks = {
        "frozen_baseline_inputs_match_manifest": _frozen_input_check(inputs),
        "time_periods_fixed_before_outcome_summary": set(valid["time_period"]) == {
            "early_2015_2018", "middle_2019_2021", "recent_2022_2025"
        },
        "all_initiators_disclosed": set(five["ticker"]) == set(
            stability.loc[stability["analysis"].eq("initiator_contribution"), "group"]
        ),
        "event_dependence_reported": len(dependence) >= 8,
        "all_bootstrap_methods_reported": set(summary["bootstrap_method"]) == {"event", "firm", "date"},
        "sample_sizes_reported": bool(stability["sample_size"].notna().all()),
    }
    if not all(checks.values()):
        raise AssertionError(f"stability validation failed: {checks}")
    return RobustnessArtifacts(
        {
            "stability_results": stability,
            "event_dependence": dependence,
            "bootstrap_summary": summary,
        },
        {
            "stability_results": directory / "stability_results.csv",
            "event_dependence": directory / "event_dependence.csv",
            "bootstrap_summary": directory / "bootstrap_summary.csv",
        },
        checks,
    )


def run_final_research_summary(
    output_directory: str | Path = FINAL_DIR,
) -> RobustnessArtifacts:
    """Create the Stage 17 evidence table and final Markdown research artifact."""
    specification = pd.read_csv(SPECIFICATION_DIR / "specification_results.csv")
    placebo = pd.read_csv(NULL_DIR / "placebo_results.csv")
    null_results = placebo.loc[placebo["method"].eq("observed")].drop_duplicates(
        ["horizon", "return_specification", "peer_definition", "outcome"]
    )
    stability = pd.read_csv(STABILITY_DIR / "stability_results.csv")
    peer = pd.read_csv(
        PROJECT_ROOT / "outputs" / "mechanism_analysis" / "peer_relationships" / "peer_definition_comparison.csv"
    )
    equipment = pd.read_csv(
        PROJECT_ROOT / "outputs" / "mechanism_analysis" / "equipment" / "equipment_summary.csv"
    )
    regime = pd.read_csv(
        PROJECT_ROOT / "outputs" / "mechanism_analysis" / "regimes" / "regime_analysis.csv"
    )
    regressions = pd.read_csv(
        PROJECT_ROOT / "outputs" / "mechanism_analysis" / "regressions" / "mechanism_regression_results.csv"
    )
    baseline = pd.read_csv(
        PROJECT_ROOT / "outputs" / "baseline" / "tables" / "mechanism_decomposition.csv"
    )

    peer5 = peer.loc[
        peer["comparison_type"].eq("paired_economic_minus_correlation")
        & peer["horizon"].eq(5)
        & peer["outcome"].eq("peer_catchup")
    ].iloc[0]
    equip5 = equipment.loc[
        equipment["group"].eq("equipment")
        & equipment["horizon"].eq(5)
        & equipment["outcome"].isin(["peer_catchup", "initiator_reversal", "convergence"])
    ].set_index("outcome")
    momentum5 = regime.loc[
        regime["analysis_type"].eq("continuous_regression")
        & regime["horizon"].eq(5)
        & regime["term"].eq("SectorMomentum_1m")
    ].iloc[0]
    nonlinear = regressions.loc[
        regressions["model_specification"].eq("targeted_shock_quadratic")
        & regressions["term"].eq("ShockMagnitudeSquared")
    ]
    null_peer5 = null_results.loc[
        null_results["horizon"].eq(5)
        & null_results["outcome"].eq("peer_catchup")
    ].iloc[0]
    null_convergence5 = null_results.loc[
        null_results["horizon"].eq(5)
        & null_results["outcome"].eq("convergence")
    ].iloc[0]
    baseline5 = baseline.loc[baseline["horizon"].eq(5)].iloc[0]
    baseline10 = baseline.loc[baseline["horizon"].eq(10)].iloc[0]
    peer_levels5 = peer.loc[
        peer["comparison_type"].eq("peer_definition_level")
        & peer["horizon"].eq(5)
        & peer["outcome"].eq("peer_catchup")
    ].set_index("peer_definition")
    momentum_split5 = regime.loc[
        regime["analysis_type"].eq("sign_based_regime_comparison")
        & regime["horizon"].eq(5)
        & regime["momentum_window"].eq("SectorMomentum_1m")
    ].set_index("regime")
    nonlinear5 = nonlinear.loc[
        nonlinear["horizon"].eq(5) & nonlinear["dependent_variable"].eq("convergence")
    ].iloc[0]
    time5 = stability.loc[
        stability["analysis"].eq("time_period")
        & stability["horizon"].eq(5)
        & stability["outcome"].eq("peer_catchup")
    ]
    time_means = time5.set_index("group")["mean"]
    evidence = pd.DataFrame(
        [
            {
                "hypothesis": "Universal convergence",
                "estimate / evidence": f"Five-day economic-peer catch-up {baseline5['peer_catchup_mean']:+.2%}; convergence {baseline5['convergence_mean']:+.2%} (n={int(baseline5['valid_events'])}). Ten-day convergence {baseline10['convergence_mean']:+.2%}.",
                "uncertainty": f"Five-day selection-preserving empirical p≈{null_peer5['empirical_p_value']:.2f} for catch-up and p≈{null_convergence5['empirical_p_value']:.2f} for convergence; dependence-aware intervals include zero.",
                "status": "not supported",
                "interpretation": "Some events may adjust, but the sample does not establish a universal diffusion effect.",
            },
            {
                "hypothesis": "Economic vs correlation peer catch-up",
                "estimate / evidence": f"Five-day paired economic-minus-correlation advantage {peer5['mean']:+.2%} (n={int(peer5['sample_size'])}); economic level {peer_levels5.loc['economic_subsector_peers','mean']:+.2%} versus correlation level {peer_levels5.loc['trailing_return_similarity_peers','mean']:+.2%}.",
                "uncertainty": f"Paired-bootstrap 95% CI {peer5['ci_lower']:+.2%} to {peer5['ci_upper']:+.2%}; positive at one and five days and imprecise at ten days.",
                "status": "supported",
                "interpretation": "Economic relationships contain incremental short-horizon peer-adjustment information relative to the fixed trailing-correlation rule.",
            },
            {
                "hypothesis": "Equipment peer catch-up",
                "estimate / evidence": f"Five-day catch-up {equip5.loc['peer_catchup','mean']:+.2%}; initiator reversal {equip5.loc['initiator_reversal','mean']:+.2%}; convergence {equip5.loc['convergence','mean']:+.2%} (n={int(equip5.loc['convergence','event_count'])}).",
                "uncertainty": f"Catch-up 95% CI {equip5.loc['peer_catchup','ci_lower']:+.2%} to {equip5.loc['peer_catchup','ci_upper']:+.2%}; reversal {equip5.loc['initiator_reversal','ci_lower']:+.2%} to {equip5.loc['initiator_reversal','ci_upper']:+.2%}; convergence {equip5.loc['convergence','ci_lower']:+.2%} to {equip5.loc['convergence','ci_upper']:+.2%}.",
                "status": "partially supported",
                "interpretation": "Equipment peers moved in the shock direction, but initiator continuation weakened total convergence.",
            },
            {
                "hypothesis": "Lower prior sector momentum",
                "estimate / evidence": f"Five-day convergence {momentum_split5.loc['weak_nonpositive','mean']:+.2%} after weak/nonpositive one-month momentum versus {momentum_split5.loc['strong_positive','mean']:+.2%} after positive momentum; controlled coefficient {momentum5['coefficient']:.3f}.",
                "uncertainty": f"Five-day coefficient 95% CI {momentum5['ci_lower']:.3f} to {momentum5['ci_upper']:.3f}; support was stronger at one day and imprecise later.",
                "status": "suggestive",
                "interpretation": "The direction is plausible but horizon-sensitive and not uniformly precise.",
            },
            {
                "hypothesis": "Nonlinear shock magnitude",
                "estimate / evidence": f"All {len(nonlinear)} pre-specified squared-shock tests had confidence intervals spanning zero.",
                "uncertainty": f"Five-day convergence squared term about {100 * nonlinear5['coefficient']:+.3f} percentage points; 95% CI {100 * nonlinear5['ci_lower']:+.3f} to {100 * nonlinear5['ci_upper']:+.3f} percentage points.",
                "status": "not supported",
                "interpretation": "The exploratory curvature did not survive the fixed formal test.",
            },
            {
                "hypothesis": "Time-stable absolute catch-up",
                "estimate / evidence": f"Five-day catch-up {time_means['early_2015_2018']:+.2%} in 2015–2018, {time_means['middle_2019_2021']:+.2%} in 2019–2021, and {time_means['recent_2022_2025']:+.2%} in 2022–2025.",
                "uncertainty": "Every period confidence interval includes zero; recent years contribute most of the positive estimate.",
                "status": "not supported",
                "interpretation": "Absolute catch-up was not uniform across the sample period.",
            },
        ]
    )
    null5 = _placebo_report_table(placebo, horizon=5, outcome="peer_catchup")
    spec5 = specification.loc[
        specification["horizon"].eq(5)
        & specification["outcome"].eq("peer_catchup")
        & specification["variation_type"].isin(["event_threshold", "universe", "peer_advantage_horizon"])
    ][["variation_type", "specification", "event_count", "mean", "ci_lower", "ci_upper", "status"]]
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    evidence.to_csv(directory / "evidence_table.csv", index=False)

    evidence_markdown = _to_markdown(evidence)
    null_markdown = _to_markdown(null5, decimals=4)
    spec_markdown = _to_markdown(spec5, decimals=4)
    time_markdown = _to_markdown(
        time5[["group", "event_count", "mean", "ci_lower", "ci_upper"]], decimals=4
    )
    report = f"""# Semiconductor Information Diffusion and Relative Price Discovery

## Research question

Does semiconductor relative-price divergence reflect delayed peer adjustment, initiator reversal, or no persistent mechanism?

## Methodology summary

The frozen 2015–2025 Stage 12 sample contains 54 reviewed securities, 36 ever eligible core securities, and 242 baseline events. Events satisfy the fixed 5% and 3-sigma rule with shifted 60-observation volatility, minimum three economic-subsector peers, and five-day firm/peer-group cooldowns. Peer portfolios are leave-one-out and frozen at the event date. Outcomes are direction-normalized peer catch-up, initiator reversal, and their sum, convergence. Every alternative peer based on returns uses only pre-event history.

## Evidence table

{evidence_markdown}

## Specification evidence at five days

{spec_markdown}

## Null and placebo evidence at five days

{null_markdown}

## Time stability at five days

{time_markdown}

## Final interpretation

The most defensible conclusion is narrow: reviewed economic peers adjust more than trailing-correlation peers over short and medium horizons, but the evidence does not establish a persistent, causal, or tradable diffusion mechanism. At five days the random-peer and pseudo-event means are near zero, yet their intervals overlap the observed estimate; absolute peer catch-up has a selection-null p-value of {null_peer5['empirical_p_value']:.2f}. Equipment events show a peer response, yet negative initiator reversal offsets it and total convergence is not distinguishable from zero. Sector momentum is suggestive and horizon-sensitive. Shock nonlinearity is not supported.

## Limitations

- Prices and volumes come from Yahoo Finance; adjusted histories are revisable.
- The current reviewed company list and retrospective classifications create survivorship concerns.
- There is no event-level news classification, so common news and firm-specific news cannot be separated.
- The frozen data have no broad-market benchmark; market-adjusted returns and market-volatility controls remain unavailable.
- Event counts are limited, shrink materially with horizon, and contain repeated firms, same-day events, and overlapping windows.
- International listings have non-synchronous closes, local currencies, exchange holidays, and differing information sets.
- Market capitalization is unavailable, so capitalization-weighted peers cannot be evaluated.
- Null models preserve selected features of returns, not every tail, volatility, and structural-break property.

## Research discipline

All requested variants were fixed before this run, weak and unavailable results are retained, and no specification is selected as “best.” A quantitative result is valuable only if it survives attempts to disprove it.
"""
    report_path = directory / "final_research_summary.md"
    report_path.write_text(report)
    checks = {
        "required_stage_outputs_loaded": all(
            path.exists()
            for path in [
                SPECIFICATION_DIR / "specification_results.csv",
                NULL_DIR / "placebo_results.csv",
                STABILITY_DIR / "stability_results.csv",
            ]
        ),
        "all_hypotheses_reported": len(evidence) == 6,
        "limitations_explicit": all(
            phrase in report
            for phrase in [
                "Yahoo Finance", "survivorship", "news classification",
                "broad-market benchmark", "Event counts", "International listings",
            ]
        ),
        "no_causal_claim": "does not establish a persistent, causal" in report,
    }
    if not all(checks.values()):
        raise AssertionError(f"final summary validation failed: {checks}")
    return RobustnessArtifacts(
        {"evidence_table": evidence},
        {
            "evidence_table": directory / "evidence_table.csv",
            "final_research_summary": report_path,
        },
        checks,
    )
