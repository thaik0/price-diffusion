"""Confirmatory Stage 13 mechanism tests on the frozen Stage 12 baseline.

This module contains every calculation used by the Stage 13 notebooks.  It
never redetects baseline events or overwrites Stage 11/12 data.  All market
characteristics and correlation peers use information strictly before the
event date.  Estimates are associational mechanism tests, not causal claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

from price_diffusion.baseline import build_semiconductor_factor
from price_diffusion.event_study import run_event_study
from price_diffusion.paths import PROJECT_ROOT
from price_diffusion.peers import (
    BROAD_SEMICONDUCTOR_PEERS,
    ECONOMIC_SUBSECTOR_PEERS,
    TRAILING_RETURN_SIMILARITY_PEERS,
)
from price_diffusion.research_diagnostics import (
    DiagnosticInputs,
    build_event_date_peer_definitions,
    load_diagnostic_inputs,
)


OUTPUT_DIR = PROJECT_ROOT / "outputs" / "mechanism_analysis"
BASELINE_MANIFEST = PROJECT_ROOT / "outputs" / "baseline" / "manifests" / "baseline_run_manifest.json"
EQUIPMENT_SUBSECTOR = "semiconductor_equipment"
HORIZONS = (1, 5, 10)
REGRESSION_OUTCOMES = ("peer_car", "convergence", "initiator_reversal")
EQUIPMENT_OUTCOMES = (
    "peer_car", "initiator_car", "peer_catchup", "initiator_reversal", "convergence"
)
PEER_OUTCOMES = ("peer_car", "peer_catchup", "convergence")
SMALL_SAMPLE_THRESHOLD = 30


@dataclass(frozen=True)
class MechanismArtifacts:
    """Tables, figure paths, and validation checks from a Stage 13 analysis."""

    tables: Mapping[str, pd.DataFrame]
    paths: Mapping[str, Path]
    checks: Mapping[str, bool] | None = None


def _sample_label(size: int) -> str:
    return (
        "small_sample_descriptive_only"
        if size < SMALL_SAMPLE_THRESHOLD
        else "adequate_analysis_sample"
    )


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


def _compound_return(values: pd.Series) -> float:
    clean = values.dropna().to_numpy(dtype=float)
    return float(np.prod(1 + clean) - 1) if len(clean) else np.nan


def _trailing_sector_characteristics(inputs: DiagnosticInputs) -> pd.DataFrame:
    """Create sector state variables with a one-day lag at every date."""
    factor = build_semiconductor_factor(
        inputs.daily_panel, inputs.universe_membership
    ).sort_values("date")
    lagged = factor["semiconductor_return"].shift(1)
    factor["SectorMomentum_1m"] = lagged.rolling(21, min_periods=15).apply(
        _compound_return, raw=False
    )
    factor["SectorMomentum_3m"] = lagged.rolling(63, min_periods=45).apply(
        _compound_return, raw=False
    )
    factor["SectorMomentum"] = factor["SectorMomentum_1m"]
    factor["SectorVolatility"] = (
        lagged.rolling(21, min_periods=15).std(ddof=1) * np.sqrt(252)
    )
    factor["sector_information_max_date"] = factor["date"].shift(1)
    # The frozen Stage 12 data have no broad-market return series.
    factor["MarketVolatility"] = np.nan
    return factor[
        [
            "date",
            "SectorMomentum",
            "SectorMomentum_1m",
            "SectorMomentum_3m",
            "SectorVolatility",
            "MarketVolatility",
            "sector_information_max_date",
        ]
    ]


def _pre_event_volume_measure(inputs: DiagnosticInputs) -> pd.DataFrame:
    """Measure prior-week volume relative to the preceding 60-day median."""
    panel = inputs.daily_panel[["date", "security_id", "volume"]].sort_values(
        ["security_id", "date"]
    )
    rows: list[dict[str, Any]] = []
    by_security = {
        security_id: group.set_index("date")["volume"]
        for security_id, group in panel.groupby("security_id", sort=False)
    }
    for event in inputs.events[["event_id", "date", "security_id"]].itertuples(index=False):
        history = by_security.get(event.security_id, pd.Series(dtype=float))
        history = history.loc[history.index < event.date].dropna()
        recent = history.tail(5)
        reference = history.iloc[:-5].tail(60) if len(history) > 5 else history.iloc[0:0]
        ratio = np.nan
        if len(recent) >= 3 and len(reference) >= 20 and reference.median() > 0:
            ratio = float(np.log(recent.mean() / reference.median()))
        rows.append(
            {
                "event_id": event.event_id,
                "VolumeMeasure": ratio,
                "volume_information_max_date": history.index.max() if len(history) else pd.NaT,
                "volume_recent_count": int(len(recent)),
                "volume_reference_count": int(len(reference)),
            }
        )
    return pd.DataFrame(rows)


def build_mechanism_characteristics(inputs: DiagnosticInputs) -> pd.DataFrame:
    """Build the pre-specified event-level Stage 13 explanatory variables."""
    events = inputs.events.copy().merge(
        inputs.security_master[["security_id", "ticker", "company_name"]],
        on="security_id",
        how="left",
        validate="many_to_one",
    )
    events["EquipmentIndicator"] = events["subsector"].eq(EQUIPMENT_SUBSECTOR).astype(int)
    events["EconomicPeerIndicator"] = events["peer_definition"].eq(
        ECONOMIC_SUBSECTOR_PEERS
    ).astype(int)
    events["ShockMagnitude"] = events["relative_return"].abs().div(
        events["relative_volatility"].replace(0, np.nan)
    )
    events["ShockMagnitudeSquared"] = events["ShockMagnitude"].pow(2)
    events["EventDirection"] = events["direction"].eq("positive").astype(int)
    events = events.merge(
        _trailing_sector_characteristics(inputs), on="date", how="left", validate="many_to_one"
    ).merge(_pre_event_volume_measure(inputs), on="event_id", how="left", validate="one_to_one")
    events["no_future_sector_information"] = (
        events["sector_information_max_date"].isna()
        | events["sector_information_max_date"].lt(events["date"])
    )
    events["no_future_volume_information"] = (
        events["volume_information_max_date"].isna()
        | events["volume_information_max_date"].lt(events["date"])
    )
    return events


def mechanism_regression_results(
    inputs: DiagnosticInputs,
    characteristics: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Estimate the pre-specified HC3 OLS mechanism regressions."""
    characteristics = (
        build_mechanism_characteristics(inputs)
        if characteristics is None
        else characteristics
    )
    columns = [
        "event_id",
        "EquipmentIndicator",
        "ShockMagnitude",
        "ShockMagnitudeSquared",
        "SectorMomentum",
        "VolumeMeasure",
        "EventDirection",
        "EconomicPeerIndicator",
    ]
    analysis = inputs.event_outcomes.loc[
        inputs.event_outcomes["valid_horizon"]
        & inputs.event_outcomes["horizon"].isin(HORIZONS)
        & inputs.event_outcomes["peer_definition"].eq(ECONOMIC_SUBSECTOR_PEERS)
    ].merge(characteristics[columns], on="event_id", how="left", validate="many_to_one")
    primary_predictors = [
        "EquipmentIndicator",
        "ShockMagnitude",
        "SectorMomentum",
        "VolumeMeasure",
        "EventDirection",
    ]
    model_specs = {
        "primary_linear": primary_predictors,
        "targeted_shock_quadratic": [*primary_predictors, "ShockMagnitudeSquared"],
    }
    rows: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        horizon_frame = analysis.loc[analysis["horizon"].eq(horizon)]
        for outcome in REGRESSION_OUTCOMES:
            for model_spec, predictors in model_specs.items():
                sample = horizon_frame[[outcome, *predictors]].dropna()
                base = {
                    "model_specification": model_spec,
                    "horizon": horizon,
                    "dependent_variable": outcome,
                    "sample_size": int(len(sample)),
                    "event_count": int(sample.index.nunique()),
                    "r_squared": np.nan,
                    "adjusted_r_squared": np.nan,
                    "covariance_estimator": "HC3",
                    "sample_label": _sample_label(len(sample)),
                    "status": "insufficient_data",
                }
                if len(sample) <= len(predictors) + 1 or any(
                    sample[column].nunique() < 2 for column in predictors
                ):
                    rows.append(
                        {
                            **base,
                            "term": "model",
                            "coefficient": np.nan,
                            "standard_error": np.nan,
                            "ci_lower": np.nan,
                            "ci_upper": np.nan,
                            "p_value_context_only": np.nan,
                        }
                    )
                    continue
                model = sm.OLS(sample[outcome], sm.add_constant(sample[predictors])).fit(
                    cov_type="HC3"
                )
                intervals = model.conf_int(alpha=0.05)
                base.update(
                    {
                        "r_squared": float(model.rsquared),
                        "adjusted_r_squared": float(model.rsquared_adj),
                        "status": "estimated_confirmatory",
                    }
                )
                for term in model.params.index:
                    rows.append(
                        {
                            **base,
                            "term": term,
                            "coefficient": float(model.params[term]),
                            "standard_error": float(model.bse[term]),
                            "ci_lower": float(intervals.loc[term, 0]),
                            "ci_upper": float(intervals.loc[term, 1]),
                            "p_value_context_only": float(model.pvalues[term]),
                        }
                    )
    return pd.DataFrame(rows)


def equipment_analysis_tables(
    inputs: DiagnosticInputs,
    characteristics: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Fully disclose equipment concentration and outcome decomposition."""
    characteristics = (
        build_mechanism_characteristics(inputs)
        if characteristics is None
        else characteristics
    )
    event_columns = [
        "event_id", "date", "security_id", "ticker", "company_name", "subsector",
        "EquipmentIndicator",
    ]
    events = characteristics[event_columns]
    equipment = events.loc[events["EquipmentIndicator"].eq(1)]
    concentration_rows: list[dict[str, Any]] = []
    for dimension, labels in {
        "company": equipment["ticker"],
        "year": equipment["date"].dt.year.astype(str),
    }.items():
        counts = labels.value_counts(dropna=False).sort_index()
        concentration_rows.extend(
            {
                "dimension": dimension,
                "label": str(label),
                "event_count": int(count),
                "event_share_within_equipment": float(count / max(len(equipment), 1)),
                "sample_label": _sample_label(int(count)),
            }
            for label, count in counts.items()
        )
    concentration = pd.DataFrame(concentration_rows)

    outcomes = inputs.event_outcomes.loc[
        inputs.event_outcomes["valid_horizon"]
        & inputs.event_outcomes["horizon"].isin(HORIZONS)
    ].merge(events[["event_id", "subsector", "EquipmentIndicator"]], on=["event_id", "subsector"])
    rows: list[dict[str, Any]] = []
    groupings: list[tuple[str, str, pd.DataFrame]] = []
    for indicator, group in outcomes.groupby("EquipmentIndicator", sort=False):
        label = "equipment" if indicator else "all_non_equipment"
        groupings.append(("binary", label, group))
    for subsector, group in outcomes.groupby("subsector", sort=True):
        groupings.append(("subsector_full_disclosure", str(subsector), group))
    for grouping, label, group in groupings:
        for horizon in HORIZONS:
            horizon_frame = group.loc[group["horizon"].eq(horizon)]
            for outcome in EQUIPMENT_OUTCOMES:
                values = horizon_frame[outcome].dropna()
                mean, lower, upper = _mean_ci(values)
                rows.append(
                    {
                        "grouping": grouping,
                        "group": label,
                        "horizon": horizon,
                        "outcome": outcome,
                        "event_count": int(horizon_frame["event_id"].nunique()),
                        "sample_size": int(len(values)),
                        "mean": mean,
                        "median": float(values.median()) if len(values) else np.nan,
                        "ci_lower": lower,
                        "ci_upper": upper,
                        "sample_label": _sample_label(len(values)),
                    }
                )
    comparison = pd.DataFrame(rows)
    return {
        "equipment_analysis": concentration,
        "equipment_summary": comparison.loc[comparison["grouping"].eq("binary")].copy(),
        "equipment_vs_other_subsectors": comparison.loc[
            comparison["grouping"].eq("subsector_full_disclosure")
        ].copy(),
    }


def equipment_event_path(
    inputs: DiagnosticInputs,
    characteristics: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Create post-event cumulative paths for equipment and other events."""
    characteristics = (
        build_mechanism_characteristics(inputs)
        if characteristics is None
        else characteristics
    )
    panel = inputs.event_panel.loc[inputs.event_panel["relative_day"].between(1, 10)].merge(
        characteristics[["event_id", "EquipmentIndicator"]], on="event_id", how="left"
    ).sort_values(["event_id", "relative_day"])
    valid = panel.groupby("event_id")["valid_observation"].cummin().astype(bool)
    panel["initiator_car"] = panel.groupby("event_id")["initiator_return"].cumsum().where(valid)
    panel["peer_car"] = panel.groupby("event_id")["peer_return"].cumsum().where(valid)
    panel["peer_catchup"] = panel.groupby("event_id")["signed_peer_return"].cumsum().where(valid)
    signed_initiator = panel.groupby("event_id")["signed_initiator_return"].cumsum().where(valid)
    panel["initiator_reversal"] = -signed_initiator
    panel["convergence"] = panel["peer_catchup"] + panel["initiator_reversal"]
    rows: list[dict[str, Any]] = []
    for (indicator, relative_day), group in panel.groupby(
        ["EquipmentIndicator", "relative_day"], sort=True
    ):
        for outcome in EQUIPMENT_OUTCOMES:
            values = group[outcome].dropna()
            mean, lower, upper = _mean_ci(values)
            rows.append(
                {
                    "group": "equipment" if indicator else "all_non_equipment",
                    "relative_day": int(relative_day),
                    "outcome": outcome,
                    "sample_size": int(len(values)),
                    "mean": mean,
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "sample_label": _sample_label(len(values)),
                }
            )
    return pd.DataFrame(rows)


def peer_definition_event_outcomes(
    inputs: DiagnosticInputs,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Re-estimate identical baseline events under all three peer definitions."""
    memberships, audit = build_event_date_peer_definitions(inputs)
    factor = build_semiconductor_factor(inputs.daily_panel, inputs.universe_membership)
    adjusted = inputs.daily_panel[["date", "security_id", "return"]].merge(
        factor, on="date", how="left", validate="many_to_one"
    )
    adjusted["semiconductor_adjusted_return"] = (
        adjusted["return"] - adjusted["semiconductor_return"]
    )
    outputs: list[pd.DataFrame] = []
    for definition in (
        ECONOMIC_SUBSECTOR_PEERS,
        TRAILING_RETURN_SIMILARITY_PEERS,
        BROAD_SEMICONDUCTOR_PEERS,
    ):
        events = inputs.events.copy()
        events["peer_definition"] = definition
        study = run_event_study(
            events,
            adjusted[["date", "security_id", "semiconductor_adjusted_return"]],
            memberships.loc[memberships["peer_definition"].eq(definition)],
            inputs.config,
            return_column="semiconductor_adjusted_return",
            return_specification="semiconductor_adjusted_return",
        )
        outputs.append(study.outcomes)
    return pd.concat(outputs, ignore_index=True), audit


def _paired_bootstrap_interval(
    differences: pd.Series,
    *,
    replications: int = 10_000,
    seed: int = 13,
) -> tuple[float, float]:
    values = differences.dropna().to_numpy(dtype=float)
    if len(values) < 2:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(replications, len(values)), replace=True).mean(axis=1)
    lower, upper = np.quantile(means, [0.025, 0.975])
    return float(lower), float(upper)


def peer_definition_comparison(
    outcomes: pd.DataFrame,
    *,
    bootstrap_replications: int = 10_000,
    seed: int = 13,
) -> pd.DataFrame:
    """Summarize common-event peer outcomes and paired economic-minus-correlation tests."""
    definitions = (
        ECONOMIC_SUBSECTOR_PEERS,
        TRAILING_RETURN_SIMILARITY_PEERS,
        BROAD_SEMICONDUCTOR_PEERS,
    )
    valid = outcomes.loc[
        outcomes["valid_horizon"] & outcomes["horizon"].isin(HORIZONS)
    ].copy()
    complete_ids = (
        valid.groupby(["event_id", "horizon"])["peer_definition"]
        .nunique()
        .loc[lambda values: values.eq(len(definitions))]
        .index
    )
    complete = valid.set_index(["event_id", "horizon"]).loc[complete_ids].reset_index()
    rows: list[dict[str, Any]] = []
    for (definition, horizon), group in complete.groupby(
        ["peer_definition", "horizon"], sort=True
    ):
        for outcome in PEER_OUTCOMES:
            values = group[outcome].dropna()
            mean, lower, upper = _mean_ci(values)
            rows.append(
                {
                    "comparison_type": "peer_definition_level",
                    "peer_definition": definition,
                    "horizon": int(horizon),
                    "outcome": outcome,
                    "event_count": int(group["event_id"].nunique()),
                    "sample_size": int(len(values)),
                    "mean": mean,
                    "median": float(values.median()) if len(values) else np.nan,
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "bootstrap_replications": 0,
                    "sample_label": _sample_label(len(values)),
                }
            )
    for horizon in HORIZONS:
        horizon_frame = complete.loc[complete["horizon"].eq(horizon)]
        if horizon_frame.empty:
            continue
        for outcome in PEER_OUTCOMES:
            wide = horizon_frame.pivot(index="event_id", columns="peer_definition", values=outcome)
            pair = wide[[ECONOMIC_SUBSECTOR_PEERS, TRAILING_RETURN_SIMILARITY_PEERS]].dropna()
            differences = pair[ECONOMIC_SUBSECTOR_PEERS] - pair[TRAILING_RETURN_SIMILARITY_PEERS]
            lower, upper = _paired_bootstrap_interval(
                differences, replications=bootstrap_replications, seed=seed + horizon
            )
            rows.append(
                {
                    "comparison_type": "paired_economic_minus_correlation",
                    "peer_definition": "economic_minus_correlation",
                    "horizon": horizon,
                    "outcome": outcome,
                    "event_count": int(len(differences)),
                    "sample_size": int(len(differences)),
                    "mean": float(differences.mean()) if len(differences) else np.nan,
                    "median": float(differences.median()) if len(differences) else np.nan,
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "bootstrap_replications": bootstrap_replications,
                    "sample_label": _sample_label(len(differences)),
                }
            )
    return pd.DataFrame(rows)


def regime_analysis(
    inputs: DiagnosticInputs,
    characteristics: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Estimate continuous momentum models and transparent sign-based comparisons."""
    characteristics = (
        build_mechanism_characteristics(inputs)
        if characteristics is None
        else characteristics
    )
    columns = [
        "event_id", "SectorMomentum_1m", "SectorMomentum_3m", "SectorVolatility",
        "MarketVolatility", "ShockMagnitude", "EquipmentIndicator", "EventDirection",
        "VolumeMeasure",
    ]
    analysis = inputs.event_outcomes.loc[
        inputs.event_outcomes["valid_horizon"]
        & inputs.event_outcomes["horizon"].isin(HORIZONS)
    ].merge(characteristics[columns], on="event_id", how="left", validate="many_to_one")
    rows: list[dict[str, Any]] = []
    controls = ["ShockMagnitude", "EquipmentIndicator", "EventDirection", "VolumeMeasure"]
    for horizon in HORIZONS:
        horizon_frame = analysis.loc[analysis["horizon"].eq(horizon)]
        for momentum in ("SectorMomentum_1m", "SectorMomentum_3m"):
            sample = horizon_frame[["convergence", momentum, "SectorVolatility", *controls]].dropna()
            predictors = [momentum, "SectorVolatility", *controls]
            if len(sample) > len(predictors) + 1 and all(
                sample[column].nunique() > 1 for column in predictors
            ):
                model = sm.OLS(
                    sample["convergence"], sm.add_constant(sample[predictors])
                ).fit(cov_type="HC3")
                intervals = model.conf_int(alpha=0.05)
                for term in (momentum, "SectorVolatility"):
                    rows.append(
                        {
                            "analysis_type": "continuous_regression",
                            "horizon": horizon,
                            "momentum_window": momentum,
                            "regime": "continuous",
                            "term": term,
                            "sample_size": int(len(sample)),
                            "event_count": int(len(sample)),
                            "mean": np.nan,
                            "median": np.nan,
                            "coefficient": float(model.params[term]),
                            "standard_error": float(model.bse[term]),
                            "ci_lower": float(intervals.loc[term, 0]),
                            "ci_upper": float(intervals.loc[term, 1]),
                            "r_squared": float(model.rsquared),
                            "sample_label": _sample_label(len(sample)),
                            "status": "estimated_confirmatory",
                        }
                    )
            for regime, mask in {
                "weak_nonpositive": horizon_frame[momentum].le(0),
                "strong_positive": horizon_frame[momentum].gt(0),
            }.items():
                values = horizon_frame.loc[mask, "convergence"].dropna()
                mean, lower, upper = _mean_ci(values)
                rows.append(
                    {
                        "analysis_type": "sign_based_regime_comparison",
                        "horizon": horizon,
                        "momentum_window": momentum,
                        "regime": regime,
                        "term": "convergence",
                        "sample_size": int(len(values)),
                        "event_count": int(len(values)),
                        "mean": mean,
                        "median": float(values.median()) if len(values) else np.nan,
                        "coefficient": np.nan,
                        "standard_error": np.nan,
                        "ci_lower": lower,
                        "ci_upper": upper,
                        "r_squared": np.nan,
                        "sample_label": _sample_label(len(values)),
                        "status": "descriptive_regime_comparison",
                    }
                )
    rows.append(
        {
            "analysis_type": "data_availability",
            "horizon": np.nan,
            "momentum_window": "not_applicable",
            "regime": "not_applicable",
            "term": "MarketVolatility",
            "sample_size": 0,
            "event_count": 0,
            "mean": np.nan,
            "median": np.nan,
            "coefficient": np.nan,
            "standard_error": np.nan,
            "ci_lower": np.nan,
            "ci_upper": np.nan,
            "r_squared": np.nan,
            "sample_label": _sample_label(0),
            "status": "unavailable_frozen_baseline_has_no_market_return_series",
        }
    )
    return pd.DataFrame(rows)


def _save_figure(figure: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return path


def _plot_mechanism_coefficients(results: pd.DataFrame, path: Path) -> Path:
    selected = results.loc[
        results["status"].eq("estimated_confirmatory")
        & results["model_specification"].eq("primary_linear")
        & results["term"].ne("const")
        & results["horizon"].eq(5)
    ].copy()
    outcomes = list(REGRESSION_OUTCOMES)
    terms = [
        "EquipmentIndicator", "ShockMagnitude", "SectorMomentum", "VolumeMeasure",
        "EventDirection",
    ]
    figure, axes = plt.subplots(1, len(outcomes), figsize=(15, 5), sharey=True)
    for axis, outcome in zip(axes, outcomes):
        frame = selected.loc[selected["dependent_variable"].eq(outcome)].set_index("term").reindex(terms)
        positions = np.arange(len(terms))
        axis.errorbar(
            frame["coefficient"], positions,
            xerr=np.vstack([
                frame["coefficient"] - frame["ci_lower"],
                frame["ci_upper"] - frame["coefficient"],
            ]),
            fmt="o", color="#1d4ed8", capsize=3,
        )
        axis.axvline(0, color="black", linewidth=0.8)
        axis.set_title(outcome.replace("_", " ").title())
        axis.set_xlabel("Coefficient (95% HC3 CI)")
        axis.set_yticks(positions, terms)
    figure.suptitle("Five-day mechanism coefficients (outcomes in decimal returns)")
    return _save_figure(figure, path)


def _plot_equipment(path_table: pd.DataFrame, summary: pd.DataFrame, directory: Path) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    for group, color in (("equipment", "#b45309"), ("all_non_equipment", "#1d4ed8")):
        frame = path_table.loc[
            path_table["group"].eq(group) & path_table["outcome"].eq("convergence")
        ]
        axes[0].plot(frame["relative_day"], frame["mean"], marker="o", label=group, color=color)
        axes[0].fill_between(frame["relative_day"], frame["ci_lower"], frame["ci_upper"], color=color, alpha=0.15)
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set(title="Post-event convergence path", xlabel="Trading day", ylabel="Mean convergence")
    axes[0].legend()
    five = summary.loc[summary["horizon"].eq(5)]
    labels = ["peer_catchup", "initiator_reversal", "convergence"]
    x = np.arange(len(labels))
    width = 0.36
    for offset, (group, color) in zip((-width / 2, width / 2), (("equipment", "#b45309"), ("all_non_equipment", "#1d4ed8"))):
        frame = five.loc[five["group"].eq(group)].set_index("outcome").reindex(labels)
        axes[1].bar(x + offset, frame["mean"], width, label=group, color=color)
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set(title="Five-day decomposition", ylabel="Mean signed return")
    axes[1].set_xticks(x, [label.replace("_", "\n") for label in labels])
    axes[1].legend()
    outputs["equipment_vs_other"] = _save_figure(
        figure, directory / "equipment_vs_other.png"
    )

    figure, axis = plt.subplots(figsize=(8, 5))
    for group, color in (("equipment", "#b45309"), ("all_non_equipment", "#1d4ed8")):
        frame = path_table.loc[
            path_table["group"].eq(group) & path_table["outcome"].eq("convergence")
        ]
        axis.plot(frame["relative_day"], frame["mean"], marker="o", label=group, color=color)
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set(title="Equipment event convergence path", xlabel="Trading day", ylabel="Mean convergence")
    axis.legend()
    outputs["equipment_event_path"] = _save_figure(
        figure, directory / "equipment_event_path.png"
    )

    figure, axis = plt.subplots(figsize=(8, 5))
    for offset, (group, color) in zip(
        (-width / 2, width / 2),
        (("equipment", "#b45309"), ("all_non_equipment", "#1d4ed8")),
    ):
        frame = five.loc[five["group"].eq(group)].set_index("outcome").reindex(labels)
        axis.bar(x + offset, frame["mean"], width, label=group, color=color)
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set(title="Equipment convergence decomposition", ylabel="Five-day mean signed return")
    axis.set_xticks(x, [label.replace("_", "\n") for label in labels])
    axis.legend()
    outputs["equipment_convergence_decomposition"] = _save_figure(
        figure, directory / "equipment_convergence_decomposition.png"
    )
    return outputs


def _plot_peer_comparison(comparison: pd.DataFrame, path: Path) -> Path:
    selected = comparison.loc[
        comparison["comparison_type"].eq("peer_definition_level")
        & comparison["horizon"].eq(5)
        & comparison["outcome"].isin(PEER_OUTCOMES)
    ]
    definitions = [
        ECONOMIC_SUBSECTOR_PEERS,
        TRAILING_RETURN_SIMILARITY_PEERS,
        BROAD_SEMICONDUCTOR_PEERS,
    ]
    figure, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    for axis, outcome in zip(axes, PEER_OUTCOMES):
        frame = selected.loc[selected["outcome"].eq(outcome)].set_index("peer_definition").reindex(definitions)
        positions = np.arange(len(definitions))
        axis.errorbar(
            positions, frame["mean"],
            yerr=np.vstack([frame["mean"] - frame["ci_lower"], frame["ci_upper"] - frame["mean"]]),
            fmt="o", color="#1d4ed8", capsize=4,
        )
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_xticks(positions, ["economic", "correlation", "broad"])
        axis.set(title=outcome.replace("_", " ").title(), xlabel="Peer definition")
    axes[0].set_ylabel("Five-day mean (95% CI)")
    return _save_figure(figure, path)


def _plot_regime_effects(regimes: pd.DataFrame, path: Path) -> Path:
    selected = regimes.loc[
        regimes["analysis_type"].eq("sign_based_regime_comparison")
        & regimes["horizon"].eq(5)
    ]
    figure, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for axis, window in zip(axes, ("SectorMomentum_1m", "SectorMomentum_3m")):
        frame = selected.loc[selected["momentum_window"].eq(window)].set_index("regime").reindex(
            ["weak_nonpositive", "strong_positive"]
        )
        positions = np.arange(2)
        axis.errorbar(
            positions, frame["mean"],
            yerr=np.vstack([frame["mean"] - frame["ci_lower"], frame["ci_upper"] - frame["mean"]]),
            fmt="o", color="#1d4ed8", capsize=4,
        )
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_xticks(positions, ["weak / nonpositive", "strong / positive"])
        axis.set(title=window.replace("SectorMomentum_", "Prior "), xlabel="Sign-based regime")
    axes[0].set_ylabel("Five-day mean convergence (95% CI)")
    return _save_figure(figure, path)


def _write_tables(tables: Mapping[str, pd.DataFrame], directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, table in tables.items():
        path = directory / f"{name}.csv"
        table.to_csv(path, index=False)
        paths[name] = path
    return paths


def run_mechanism_regressions(
    inputs: DiagnosticInputs | None = None,
    output_directory: str | Path = OUTPUT_DIR / "regressions",
) -> MechanismArtifacts:
    inputs = inputs or load_diagnostic_inputs()
    characteristics = build_mechanism_characteristics(inputs)
    results = mechanism_regression_results(inputs, characteristics)
    directory = Path(output_directory)
    paths = _write_tables({"mechanism_regression_results": results}, directory)
    paths["mechanism_coefficients"] = _plot_mechanism_coefficients(
        results, OUTPUT_DIR / "figures" / "mechanism_coefficients.png"
    )
    return MechanismArtifacts(
        {"mechanism_regression_results": results, "event_characteristics": characteristics},
        paths,
    )


def run_equipment_analysis(
    inputs: DiagnosticInputs | None = None,
    output_directory: str | Path = OUTPUT_DIR / "equipment",
) -> MechanismArtifacts:
    inputs = inputs or load_diagnostic_inputs()
    characteristics = build_mechanism_characteristics(inputs)
    tables = equipment_analysis_tables(inputs, characteristics)
    path_table = equipment_event_path(inputs, characteristics)
    tables = {**tables, "equipment_event_path": path_table}
    paths = _write_tables(tables, Path(output_directory))
    paths.update(
        _plot_equipment(path_table, tables["equipment_summary"], OUTPUT_DIR / "figures")
    )
    return MechanismArtifacts(tables, paths)


def run_peer_relationship_analysis(
    inputs: DiagnosticInputs | None = None,
    output_directory: str | Path = OUTPUT_DIR / "peer_relationships",
) -> MechanismArtifacts:
    inputs = inputs or load_diagnostic_inputs()
    outcomes, audit = peer_definition_event_outcomes(inputs)
    comparison = peer_definition_comparison(outcomes)
    tables = {"peer_definition_comparison": comparison, "peer_information_audit": audit}
    paths = _write_tables(tables, Path(output_directory))
    paths["peer_definition_comparison_figure"] = _plot_peer_comparison(
        comparison, OUTPUT_DIR / "figures" / "peer_definition_comparison.png"
    )
    return MechanismArtifacts(tables, paths)


def run_regime_analysis(
    inputs: DiagnosticInputs | None = None,
    output_directory: str | Path = OUTPUT_DIR / "regimes",
) -> MechanismArtifacts:
    inputs = inputs or load_diagnostic_inputs()
    characteristics = build_mechanism_characteristics(inputs)
    results = regime_analysis(inputs, characteristics)
    paths = _write_tables({"regime_analysis": results}, Path(output_directory))
    paths["regime_effects"] = _plot_regime_effects(
        results, OUTPUT_DIR / "figures" / "regime_effects.png"
    )
    return MechanismArtifacts(
        {"regime_analysis": results, "event_characteristics": characteristics}, paths
    )


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_stage13(
    inputs: DiagnosticInputs,
    artifacts: Mapping[str, MechanismArtifacts],
) -> dict[str, bool]:
    """Enforce Stage 13 leakage, disclosure, and traceability requirements."""
    characteristics = artifacts["regressions"].tables["event_characteristics"]
    audit = artifacts["peers"].tables["peer_information_audit"]
    regressions = artifacts["regressions"].tables["mechanism_regression_results"]
    equipment = artifacts["equipment"].tables["equipment_vs_other_subsectors"]
    peer_comparison = artifacts["peers"].tables["peer_definition_comparison"]
    regimes = artifacts["regimes"].tables["regime_analysis"]
    manifest = json.loads(BASELINE_MANIFEST.read_text())
    expected = manifest["input_sha256"]
    frozen_paths = {
        "daily_panel": PROJECT_ROOT / "data" / "processed" / "daily_panel.parquet",
        "security_master": PROJECT_ROOT / "data" / "processed" / "security_master.csv",
        "universe_membership": PROJECT_ROOT / "data" / "processed" / "universe_membership.csv",
        "config": PROJECT_ROOT / "configs" / "final_baseline.yaml",
        "semiconductor_classification": PROJECT_ROOT / "metadata" / "semiconductor_classification.csv",
    }
    disclosed = set(equipment["group"].dropna())
    observed = set(inputs.events["subsector"].dropna())
    reporting_tables = (regressions, equipment, peer_comparison, regimes)
    checks = {
        "sector_characteristics_strictly_pre_event": bool(
            characteristics["no_future_sector_information"].all()
        ),
        "volume_characteristics_strictly_pre_event": bool(
            characteristics["no_future_volume_information"].all()
        ),
        "correlation_peers_strictly_pre_event": bool(audit["no_future_information_check"].all()),
        "regressions_report_sample_sizes": bool(regressions["sample_size"].notna().all()),
        "small_samples_are_flagged": all("sample_label" in table for table in reporting_tables),
        "all_subsectors_disclosed": disclosed == observed,
        "baseline_event_count_unchanged": int(inputs.events["event_id"].nunique()) == int(
            manifest["event_count"]
        ),
        "frozen_baseline_input_hashes_match": all(
            _file_hash(path) == expected[name] for name, path in frozen_paths.items()
        ),
        "market_volatility_unavailability_disclosed": bool(
            regimes["status"].eq(
                "unavailable_frozen_baseline_has_no_market_return_series"
            ).any()
        ),
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise ValueError(f"Stage 13 validation failed: {failed}")
    return checks


def run_stage13() -> tuple[Mapping[str, MechanismArtifacts], Mapping[str, bool]]:
    """Run all Stage 13 mechanism analyses against the frozen baseline."""
    inputs = load_diagnostic_inputs()
    artifacts = {
        "regressions": run_mechanism_regressions(inputs),
        "equipment": run_equipment_analysis(inputs),
        "peers": run_peer_relationship_analysis(inputs),
        "regimes": run_regime_analysis(inputs),
    }
    checks = validate_stage13(inputs, artifacts)
    validation = pd.DataFrame(
        {"check": list(checks), "passed": list(checks.values())}
    )
    validation_path = OUTPUT_DIR / "validation.csv"
    validation.to_csv(validation_path, index=False)
    return artifacts, checks
