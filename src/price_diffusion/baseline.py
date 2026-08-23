"""Frozen Stage 12 baseline study orchestration and reporting.

The module converts the Stage 11D artifacts into the Stage 5--9 analysis
datasets, runs the pre-specified event study, and writes human-readable
artifacts.  It does not tune thresholds, peer definitions, or horizons.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
import seaborn as sns

from price_diffusion.config import load_config
from price_diffusion.event_study import EventStudyResult, run_event_study
from price_diffusion.events import detect_events
from price_diffusion.paths import PROJECT_ROOT
from price_diffusion.peers import ECONOMIC_SUBSECTOR_PEERS, build_peer_membership
from price_diffusion.returns import (
    build_relative_returns,
    calculate_relative_abnormal_returns,
)
from price_diffusion.statistical_inference import (
    InferenceConfig,
    StatisticalInferenceResult,
    run_statistical_inference,
)
from price_diffusion.universe import classification_view, load_semiconductor_metadata
from price_diffusion.validation import validate_event_outcomes


CONFIG_PATH = PROJECT_ROOT / "configs" / "final_baseline.yaml"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
BASELINE_DIR = PROJECT_ROOT / "outputs" / "baseline"
OUTCOMES = ("convergence", "peer_catchup", "initiator_reversal")


@dataclass(frozen=True)
class BaselineArtifacts:
    """In-memory Stage 12 results and the generated artifact paths."""

    security_master: pd.DataFrame
    universe_membership: pd.DataFrame
    daily_panel: pd.DataFrame
    peer_membership: pd.DataFrame
    relative_returns: pd.DataFrame
    events: pd.DataFrame
    event_study: EventStudyResult
    inference: StatisticalInferenceResult
    tables: Mapping[str, pd.DataFrame]
    paths: Mapping[str, Path]


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_stage11d_inputs(
    config: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and date-limit the frozen Stage 11D analysis inputs."""
    master = pd.read_csv(PROCESSED_DIR / "security_master.csv")
    membership = pd.read_csv(PROCESSED_DIR / "universe_membership.csv")
    panel = pd.read_parquet(PROCESSED_DIR / "daily_panel.parquet")
    membership["date"] = pd.to_datetime(membership["date"])
    panel["date"] = pd.to_datetime(panel["date"])
    if "reason" in membership and "exclusion_reason" not in membership:
        membership = membership.rename(columns={"reason": "exclusion_reason"})
    start = pd.Timestamp(config["date_range"]["start"])
    end = pd.Timestamp(config["date_range"]["end"])
    membership = membership.loc[membership["date"].between(start, end)].copy()
    panel = panel.loc[panel["date"].between(start, end)].copy()
    membership["eligible"] = membership["eligible"].astype(bool)
    return master, membership, panel


def production_peer_classification(
    semiconductor_classification: pd.DataFrame,
) -> pd.DataFrame:
    """Use the reviewed Stage 11A subsector as the frozen economic peer group."""
    output = semiconductor_classification[["security_id", "subsector"]].copy()
    output["peer_group"] = output["subsector"]
    output["classification_notes"] = (
        "Stage 12 baseline group copied from the reviewed Stage 11A subsector."
    )
    return output[
        ["security_id", "subsector", "peer_group", "classification_notes"]
    ]


def build_semiconductor_factor(
    daily_panel: pd.DataFrame, universe_membership: pd.DataFrame
) -> pd.DataFrame:
    """Build the contemporaneous equal-weight eligible-semiconductor factor."""
    eligible = universe_membership.loc[
        universe_membership["eligible"], ["date", "security_id"]
    ]
    observations = eligible.merge(
        daily_panel[["date", "security_id", "return"]],
        on=["date", "security_id"],
        how="left",
        validate="one_to_one",
    )
    return (
        observations.groupby("date", as_index=False)["return"]
        .mean()
        .rename(columns={"return": "semiconductor_return"})
    )


def _analysis_datasets(
    config: Mapping[str, Any],
    security_master: pd.DataFrame,
    membership: pd.DataFrame,
    daily_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metadata = load_semiconductor_metadata()
    semiconductor_classification = classification_view(metadata, security_master)
    peer_classification = production_peer_classification(semiconductor_classification)
    peers = build_peer_membership(
        security_master,
        semiconductor_classification,
        membership,
        peer_classification,
        definitions=(ECONOMIC_SUBSECTOR_PEERS,),
    )

    factor = build_semiconductor_factor(daily_panel, membership)
    market_placeholder = factor[["date"]].assign(market_return=np.nan)
    relative = build_relative_returns(
        daily_panel[["date", "security_id", "return"]],
        peers,
        market_placeholder,
        factor,
        stock_return_column="return",
        market_return_column="market_return",
        semiconductor_return_column="semiconductor_return",
    )
    adjusted = daily_panel[["date", "security_id", "return"]].merge(
        factor, on="date", how="left", validate="many_to_one"
    )
    adjusted["semiconductor_adjusted_return"] = (
        adjusted["return"] - adjusted["semiconductor_return"]
    )
    relative_abnormal = calculate_relative_abnormal_returns(
        adjusted[["date", "security_id", "semiconductor_adjusted_return"]],
        peers,
        abnormal_return_column="semiconductor_adjusted_return",
    )
    relative = relative.merge(
        relative_abnormal[
            [
                "date",
                "security_id",
                "peer_definition",
                "peer_count",
                "relative_abnormal_return",
            ]
        ],
        on=["date", "security_id", "peer_definition"],
        how="left",
        validate="one_to_one",
    )

    candidates = relative_abnormal.merge(
        peer_classification[["security_id", "subsector", "peer_group"]],
        on="security_id",
        how="left",
        validate="many_to_one",
    ).merge(
        daily_panel[["date", "security_id", "volume", "extreme_return_flag"]],
        on=["date", "security_id"],
        how="left",
        validate="one_to_one",
    )
    candidates["corporate_action_type"] = np.where(
        candidates["extreme_return_flag"].fillna(False), "unknown", "none"
    )
    candidates["earnings_flag"] = False
    candidates["news_identified_flag"] = False
    candidates["market_cap"] = np.nan
    events = detect_events(candidates, config)
    return peers, relative, events, adjusted


def _mean_ci(values: pd.Series, confidence: float = 0.95) -> tuple[float, float, float]:
    clean = values.dropna().to_numpy(dtype=float)
    if not len(clean):
        return np.nan, np.nan, np.nan
    mean = float(clean.mean())
    if len(clean) < 2:
        return mean, np.nan, np.nan
    standard_error = float(stats.sem(clean))
    critical = float(stats.t.ppf((1 + confidence) / 2, len(clean) - 1))
    return mean, mean - critical * standard_error, mean + critical * standard_error


def event_path_statistics(
    event_panel: pd.DataFrame, confidence: float = 0.95
) -> pd.DataFrame:
    """Create signed cumulative event paths from t=-5 with event-level CIs."""
    ordered = event_panel.sort_values(["event_id", "relative_day"]).copy()
    complete = ordered.groupby("event_id")["valid_observation"].cummin().astype(bool)
    ordered["initiator_car"] = (
        ordered.groupby("event_id")["signed_initiator_return"].cumsum().where(complete)
    )
    ordered["peer_car"] = (
        ordered.groupby("event_id")["signed_peer_return"].cumsum().where(complete)
    )
    ordered["convergence"] = ordered["peer_car"] - ordered["initiator_car"]
    rows: list[dict[str, Any]] = []
    for relative_day, frame in ordered.groupby("relative_day", sort=True):
        for outcome in ("initiator_car", "peer_car", "convergence"):
            mean, lower, upper = _mean_ci(frame[outcome], confidence)
            rows.append(
                {
                    "relative_day": int(relative_day),
                    "outcome": outcome,
                    "mean": mean,
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "sample_size": int(frame[outcome].notna().sum()),
                }
            )
    return pd.DataFrame(rows)


def _sample_tables(
    security_master: pd.DataFrame,
    membership: pd.DataFrame,
    events: pd.DataFrame,
    outcomes: pd.DataFrame,
    coverage: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    latest = membership["date"].max()
    latest_membership = membership.loc[
        membership["date"].eq(latest),
        ["security_id", "eligible", "exclusion_reason"],
    ]
    ever = (
        membership.groupby("security_id", as_index=False)["eligible"]
        .any()
        .rename(columns={"eligible": "ever_baseline_eligible"})
    )
    sample = security_master[
        ["security_id", "ticker", "company_name", "subsector", "universe_tier"]
    ].merge(ever, on="security_id", how="left").merge(
        latest_membership, on="security_id", how="left", validate="one_to_one"
    )
    sample["ever_baseline_eligible"] = sample["ever_baseline_eligible"].fillna(False)
    sample["exclusion_reason"] = sample["exclusion_reason"].fillna("")
    short_ids = set(
        coverage.loc[coverage["short_history_company"].astype(bool), "security_id"]
    )
    sample["baseline_exclusion_reason"] = np.where(
        sample["ever_baseline_eligible"],
        "",
        np.where(
            sample["security_id"].isin(short_ids),
            "universe_tier_not_allowed;insufficient_history",
            "universe_tier_not_allowed",
        ),
    )
    sample_report = pd.DataFrame(
        [
            {"metric": "total_classified_securities", "value": len(security_master)},
            {
                "metric": "baseline_eligible_securities",
                "value": int(sample["ever_baseline_eligible"].sum()),
            },
            {
                "metric": "excluded_securities",
                "value": int((~sample["ever_baseline_eligible"]).sum()),
            },
            {
                "metric": "eligible_on_final_global_calendar_date",
                "value": int(sample["eligible"].sum()),
            },
            {"metric": "sample_end", "value": latest.date().isoformat()},
        ]
    )
    exclusions = sample.loc[~sample["ever_baseline_eligible"]].copy()
    exclusion_reasons = (
        exclusions.assign(
            baseline_exclusion_reason=exclusions["baseline_exclusion_reason"].str.split(";")
        )
        .explode("baseline_exclusion_reason")
        .groupby("baseline_exclusion_reason", as_index=False)
        .size()
        .rename(columns={"size": "security_count"})
    )
    short = coverage.loc[
        coverage["short_history_company"].astype(bool),
        [
            "security_id",
            "ticker",
            "first_trading_date",
            "last_trading_date",
            "number_of_observations",
            "issues",
        ],
    ].copy()

    event_rows = [
        {"dimension": "total", "label": "all", "event_count": events["event_id"].nunique()}
    ]
    for dimension, series in (
        ("direction", events["direction"]),
        ("year", events["date"].dt.year),
        ("subsector", events["subsector"]),
    ):
        counts = series.value_counts(dropna=False).sort_index()
        event_rows.extend(
            {"dimension": dimension, "label": str(label), "event_count": int(count)}
            for label, count in counts.items()
        )
    event_summary = pd.DataFrame(event_rows)

    company = events.groupby("security_id", as_index=False).agg(
        event_count=("event_id", "nunique"), subsector=("subsector", "first")
    ).merge(
        security_master[["security_id", "ticker", "company_name"]],
        on="security_id",
        how="left",
        validate="one_to_one",
    )
    total_events = max(events["event_id"].nunique(), 1)
    company["event_share"] = company["event_count"] / total_events
    initiators = max(company["security_id"].nunique(), 1)
    company["dominant_company_flag"] = company["event_share"].gt(
        max(0.10, 2.0 / initiators)
    )
    company = company.sort_values(["event_count", "ticker"], ascending=[False, True])

    date_concentration = (
        events.groupby("date", as_index=False)
        .agg(event_count=("event_id", "nunique"), subsector_count=("subsector", "nunique"))
        .sort_values(["event_count", "date"], ascending=[False, True])
    )
    date_concentration["many_simultaneous_shocks_flag"] = date_concentration[
        "event_count"
    ].ge(3)

    valid = outcomes.groupby("horizon", as_index=False).agg(
        total_events=("event_id", "nunique"), complete_horizons=("valid_horizon", "sum")
    )
    valid["excluded_horizons"] = valid["total_events"] - valid["complete_horizons"]
    invalid = outcomes.loc[~outcomes["valid_horizon"]].copy()
    if not invalid.empty:
        invalid["missing_reason"] = invalid["missing_reason"].str.split(";")
        invalid = invalid.explode("missing_reason")
        reasons = invalid.groupby(["horizon", "missing_reason"], as_index=False).size().rename(
            columns={"size": "excluded_events"}
        )
    else:
        reasons = pd.DataFrame(columns=["horizon", "missing_reason", "excluded_events"])
    return {
        "sample_report": sample_report,
        "security_sample": sample,
        "excluded_securities": exclusions,
        "exclusion_reason_summary": exclusion_reasons,
        "short_history_exclusions": short,
        "event_summary": event_summary,
        "company_concentration": company,
        "date_concentration": date_concentration,
        "horizon_missingness": valid,
        "missingness_reasons": reasons,
    }


def _result_tables(
    events: pd.DataFrame,
    outcomes: pd.DataFrame,
    inference: StatisticalInferenceResult,
    security_master: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    summary = inference.summary_table
    all_events = summary.loc[summary["direction"].eq("all")]
    rows: list[dict[str, Any]] = []
    for horizon in sorted(outcomes["horizon"].unique()):
        row: dict[str, Any] = {
            "horizon": int(horizon),
            "valid_events": int(
                outcomes.loc[outcomes["horizon"].eq(horizon), "valid_horizon"].sum()
            ),
        }
        for outcome in OUTCOMES:
            cell = all_events.loc[
                all_events["horizon"].eq(horizon) & all_events["outcome"].eq(outcome)
            ]
            for metric in ("mean", "median", "ci_lower", "ci_upper"):
                row[f"{outcome}_{metric}"] = cell[metric].iloc[0] if len(cell) else np.nan
        rows.append(row)
    mechanism = pd.DataFrame(rows)

    subsector = (
        events.groupby("subsector", as_index=False)
        .agg(
            event_count=("event_id", "nunique"),
            positive_shocks=("direction", lambda values: values.eq("positive").sum()),
            negative_shocks=("direction", lambda values: values.eq("negative").sum()),
            initiating_companies=("security_id", "nunique"),
        )
        .merge(
            security_master.groupby("subsector", as_index=False).agg(
                classified_securities=("security_id", "nunique")
            ),
            on="subsector",
            how="right",
        )
        .fillna(
            {
                "event_count": 0,
                "positive_shocks": 0,
                "negative_shocks": 0,
                "initiating_companies": 0,
            }
        )
    )
    count_columns = [
        "event_count", "positive_shocks", "negative_shocks", "initiating_companies"
    ]
    subsector[count_columns] = subsector[count_columns].astype(int)
    return {
        "mechanism_decomposition": mechanism,
        "subsector_summary": subsector,
        "distribution_statistics": inference.distribution_summary,
        "outcome_summary": inference.summary_table,
        "hypothesis_tests": inference.hypothesis_tests,
        "attrition": inference.attrition_table,
    }


def _plot_event_path(statistics: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(9, 5.5))
    labels = {
        "initiator_car": "Initiator signed CAR",
        "peer_car": "Peer signed CAR",
        "convergence": "Convergence",
    }
    for outcome, label in labels.items():
        line = statistics.loc[statistics["outcome"].eq(outcome)].sort_values("relative_day")
        axis.plot(line["relative_day"], line["mean"], marker="o", label=label)
        axis.fill_between(
            line["relative_day"], line["ci_lower"], line["ci_upper"], alpha=0.15
        )
    axis.axvline(0, color="black", linewidth=0.9)
    axis.axhline(0, color="black", linewidth=0.7)
    axis.set(
        xlabel="Relative trading day",
        ylabel="Average sign-normalized cumulative abnormal return",
        title="Average event path (95% confidence intervals)",
    )
    axis.legend(frameon=False)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_components(mechanism: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(8, 5))
    positions = np.arange(len(mechanism))
    width = 0.34
    for offset, outcome, label, color in (
        (-width / 2, "peer_catchup", "Peer catch-up", "#3b82f6"),
        (width / 2, "initiator_reversal", "Initiator reversal", "#f97316"),
    ):
        means = mechanism[f"{outcome}_mean"].to_numpy(float)
        lower = mechanism[f"{outcome}_ci_lower"].to_numpy(float)
        upper = mechanism[f"{outcome}_ci_upper"].to_numpy(float)
        errors = np.vstack([means - lower, upper - means])
        axis.bar(positions + offset, means, width, label=label, color=color, yerr=errors, capsize=3)
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set_xticks(positions, mechanism["horizon"].astype(str))
    axis.set(
        xlabel="Horizon (trading days)",
        ylabel="Average sign-normalized abnormal return",
        title="Convergence mechanism decomposition (95% confidence intervals)",
    )
    axis.legend(frameon=False)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_distributions(outcomes: pd.DataFrame, path: Path, horizon: int = 5) -> None:
    selected = outcomes.loc[
        outcomes["valid_horizon"] & outcomes["horizon"].eq(horizon)
    ]
    figure, axes = plt.subplots(3, 2, figsize=(11, 11), squeeze=False)
    for row, outcome in enumerate(OUTCOMES):
        for column, direction in enumerate(("positive", "negative")):
            axis = axes[row, column]
            values = selected.loc[selected["direction"].eq(direction), outcome].dropna()
            if len(values):
                sns.histplot(values, bins="auto", kde=len(values) >= 3, ax=axis, color="#2563eb")
            axis.axvline(0, color="black", linewidth=0.8)
            axis.set(
                title=f"{outcome.replace('_', ' ').title()} — {direction}",
                xlabel="Decimal return",
                ylabel="Event count",
            )
    figure.suptitle(f"Outcome distributions at the {horizon}-trading-day horizon", y=1.01)
    figure.tight_layout()
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _write_tables(tables: Mapping[str, pd.DataFrame], directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, table in tables.items():
        path = directory / f"{name}.csv"
        table.to_csv(path, index=False)
        paths[name] = path
    return paths


def _validate_baseline(
    events: pd.DataFrame,
    event_study: EventStudyResult,
    peers: pd.DataFrame,
    membership: pd.DataFrame,
    relative_returns: pd.DataFrame,
    daily_panel: pd.DataFrame,
    config: Mapping[str, Any],
) -> dict[str, bool]:
    outcomes = event_study.outcomes
    validate_event_outcomes(outcomes)
    endpoints = peers.merge(
        membership[["date", "security_id", "eligible"]],
        on=["date", "security_id"],
        how="left",
        validate="many_to_one",
    ).merge(
        membership[["date", "security_id", "eligible"]].rename(
            columns={"security_id": "peer_id", "eligible": "peer_eligible"}
        ),
        on=["date", "peer_id"],
        how="left",
        validate="many_to_one",
    )
    valid = outcomes.loc[outcomes["valid_horizon"]]
    signs = events.set_index("event_id")["direction"].map({"positive": 1.0, "negative": -1.0})
    expected = signs.reindex(valid["event_id"]).to_numpy() * (
        valid["peer_car"].to_numpy() - valid["initiator_car"].to_numpy()
    )
    start = pd.Timestamp(config["date_range"]["start"])
    end = pd.Timestamp(config["date_range"]["end"])
    values = config["event_thresholds"]
    volatility_input = relative_returns[
        [
            "date",
            "security_id",
            "peer_definition",
            "peer_count",
            "relative_abnormal_return",
        ]
    ].merge(
        daily_panel[["date", "security_id", "extreme_return_flag"]],
        on=["date", "security_id"],
        how="left",
        validate="one_to_one",
    ).sort_values(["security_id", "peer_definition", "date"], kind="stable")
    valid_history = (
        volatility_input["peer_count"].ge(int(values["minimum_peer_count"]))
        & ~volatility_input["extreme_return_flag"].fillna(False)
    )
    volatility_input["_eligible_return"] = volatility_input[
        "relative_abnormal_return"
    ].where(valid_history)
    volatility_input["_trailing_volatility"] = volatility_input.groupby(
        ["security_id", "peer_definition"], sort=False
    )["_eligible_return"].transform(
        lambda series: series.shift(1).rolling(
            int(values["volatility_window"]),
            min_periods=int(values["minimum_history_requirement"]),
        ).std(ddof=1)
    )
    checked_events = events.merge(
        volatility_input[
            ["date", "security_id", "peer_definition", "_trailing_volatility"]
        ],
        on=["date", "security_id", "peer_definition"],
        how="left",
        validate="one_to_one",
    )
    checks = {
        "no_self_peers": bool(peers["security_id"].ne(peers["peer_id"]).all()),
        "point_in_time_eligible_peer_endpoints": bool(
            endpoints["eligible"].all() and endpoints["peer_eligible"].all()
        ),
        "event_dates_within_frozen_sample": bool(events["date"].between(start, end).all()),
        "sign_normalization_valid": bool(
            np.allclose(valid["convergence"], expected, atol=1e-12, rtol=1e-12)
        ),
        "convergence_identity_valid": bool(
            np.allclose(
                valid["convergence"],
                valid["peer_catchup"] + valid["initiator_reversal"],
                atol=1e-12,
                rtol=1e-12,
            )
        ),
        "strictly_trailing_event_volatility": bool(
            np.allclose(
                checked_events["relative_volatility"],
                checked_events["_trailing_volatility"],
                atol=1e-12,
                rtol=1e-12,
            )
        ),
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise ValueError(f"baseline validation failed: {failed}")
    return checks


def interpret_mechanism(mechanism: pd.DataFrame, horizon: int = 5) -> str:
    """Return a cautious descriptive interpretation of one frozen horizon."""
    if mechanism.empty or horizon not in set(mechanism["horizon"]):
        return "No complete event outcomes are available for interpretation."
    row = mechanism.loc[mechanism["horizon"].eq(horizon)].iloc[0]
    peer = float(row["peer_catchup_mean"])
    reversal = float(row["initiator_reversal_mean"])
    if peer > 0 and reversal > 0:
        mechanism_text = "both delayed peer adjustment and initiator reversal"
    elif peer > 0:
        mechanism_text = "delayed peer adjustment"
    elif reversal > 0:
        mechanism_text = "temporary initiator dislocation followed by reversal"
    else:
        mechanism_text = "neither systematic peer catch-up nor initiator reversal"
    convergence = float(row["convergence_mean"])
    lower = float(row["convergence_ci_lower"])
    upper = float(row["convergence_ci_upper"])
    uncertainty = (
        "The confidence interval includes zero, so the estimate is imprecise"
        if lower <= 0 <= upper
        else "The confidence interval excludes zero in this conditional sample"
    )
    return (
        f"At {horizon} trading days, the point estimates are descriptively consistent with "
        f"{mechanism_text} (mean convergence {convergence:.4f}). {uncertainty}. "
        "This conditional event-study pattern is not causal evidence."
    )


def run_baseline(
    config_path: str | Path = CONFIG_PATH,
    output_directory: str | Path = BASELINE_DIR,
) -> BaselineArtifacts:
    """Run and persist the first frozen empirical baseline study."""
    config_path = Path(config_path)
    output_directory = Path(output_directory)
    config = load_config(config_path)
    master, membership, panel = _load_stage11d_inputs(config)
    peers, relative, events, adjusted = _analysis_datasets(
        config, master, membership, panel
    )
    return_specification = config["event_study"]["return_specification"]
    study = run_event_study(
        events,
        adjusted[["date", "security_id", return_specification]],
        peers,
        config,
        return_column=return_specification,
        return_specification=return_specification,
    )
    inference_config = InferenceConfig.from_mapping(config)
    inference = run_statistical_inference(
        study.outcomes, event_panel=study.event_panel, config=inference_config
    )
    coverage = pd.read_csv(PROJECT_ROOT / "outputs" / "diagnostics" / "historical_coverage_audit.csv")
    tables = _sample_tables(master, membership, events, study.outcomes, coverage)
    tables.update(_result_tables(events, study.outcomes, inference, master))
    path_statistics = event_path_statistics(
        study.event_panel, inference_config.confidence_level
    )
    tables["event_path_statistics"] = path_statistics

    checks = _validate_baseline(
        events, study, peers, membership, relative, panel, config
    )
    table_paths = _write_tables(tables, output_directory / "tables")
    figure_directory = output_directory / "figures"
    figure_directory.mkdir(parents=True, exist_ok=True)
    figure_paths = {
        "event_path": figure_directory / "event_path.png",
        "convergence_components": figure_directory / "convergence_components.png",
        "outcome_distributions": figure_directory / "outcome_distributions.png",
    }
    _plot_event_path(path_statistics, figure_paths["event_path"])
    _plot_components(tables["mechanism_decomposition"], figure_paths["convergence_components"])
    _plot_distributions(study.outcomes, figure_paths["outcome_distributions"], horizon=5)

    processed_paths = {
        "peer_membership": PROCESSED_DIR / "peer_membership.parquet",
        "relative_returns": PROCESSED_DIR / "relative_returns.parquet",
        "events": PROCESSED_DIR / "events.parquet",
        "event_panel": PROCESSED_DIR / "event_panel.parquet",
        "event_outcomes": PROCESSED_DIR / "event_outcomes.parquet",
    }
    for name, frame in (
        ("peer_membership", peers),
        ("relative_returns", relative),
        ("events", events),
        ("event_panel", study.event_panel),
        ("event_outcomes", study.outcomes),
    ):
        frame.to_parquet(processed_paths[name], index=False)

    manifest_directory = output_directory / "manifests"
    manifest_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_directory / "baseline_run_manifest.json"
    input_paths = {
        "config": config_path,
        "security_master": PROCESSED_DIR / "security_master.csv",
        "universe_membership": PROCESSED_DIR / "universe_membership.csv",
        "daily_panel": PROCESSED_DIR / "daily_panel.parquet",
        "semiconductor_classification": PROJECT_ROOT / "metadata" / "semiconductor_classification.csv",
    }
    manifest = {
        "stage": 12,
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "universe_version": config["universe"]["universe_version"],
        "sample_start": config["date_range"]["start"],
        "sample_end": config["date_range"]["end"],
        "peer_methodology": "equal-weight leave-one-out reviewed Stage 11A subsector peers",
        "event_definition": config["event_thresholds"],
        "horizons": sorted(
            config["event_study"]["primary_horizons"]
            + config["event_study"]["descriptive_horizons"]
        ),
        "return_specification": return_specification,
        "semiconductor_factor": "same-day equal-weight return of baseline-eligible securities",
        "distribution_figure_horizon": 5,
        "classified_security_count": int(master["security_id"].nunique()),
        "ever_baseline_eligible_security_count": int(
            membership.groupby("security_id")["eligible"].any().sum()
        ),
        "event_count": int(events["event_id"].nunique()),
        "positive_event_count": int(events["direction"].eq("positive").sum()),
        "negative_event_count": int(events["direction"].eq("negative").sum()),
        "validations": checks,
        "input_sha256": {name: _file_hash(path) for name, path in input_paths.items()},
        "output_sha256": {
            path.relative_to(output_directory).as_posix(): _file_hash(path)
            for path in [*table_paths.values(), *figure_paths.values()]
        },
        "interpretation": interpret_mechanism(tables["mechanism_decomposition"]),
        "limitations": [
            "The present-day reviewed classification is applied retrospectively.",
            "The universe is not survivorship-free.",
            "Yahoo adjusted prices are revisable and corporate-action metadata are incomplete.",
            "International closes are non-synchronous and returns remain in local listing currencies.",
            "Confidence intervals condition on detected events and do not establish causality.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths = {**table_paths, **figure_paths, **processed_paths, "manifest": manifest_path}
    return BaselineArtifacts(
        master, membership, panel, peers, relative, events, study, inference, tables, paths
    )


if __name__ == "__main__":  # pragma: no cover - exercised as a pipeline command
    run_baseline()
