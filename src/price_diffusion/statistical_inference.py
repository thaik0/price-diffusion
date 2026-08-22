"""Dependence-aware statistical inference for Stage 9 event-study outcomes.

This module conditions on the events selected upstream.  Its estimates therefore
describe uncertainty within the detected-event sample; they are not
selection-preserving null tests and do not identify causal information diffusion.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.formula.api as smf
from scipy import stats


OUTCOMES = ("convergence", "peer_catchup", "initiator_reversal")
CELL_COLUMNS = ("horizon", "return_specification", "peer_definition")
CLUSTER_COLUMNS = {
    "firm": ("security_id",),
    "event_date": ("event_date",),
    "two_way": ("security_id", "event_date"),
}
ALTERNATIVES = {
    "convergence": "greater",
    "peer_catchup": "two-sided",
    "initiator_reversal": "two-sided",
}
REGRESSION_CHARACTERISTICS = (
    "event_id",
    "volume",
    "market_cap",
    "market_volatility_regime",
    "semiconductor_volatility_regime",
)


@dataclass(frozen=True)
class InferenceConfig:
    """Pre-specified uncertainty and reporting choices.

    Analytical intervals use a Student-t reference.  With clustering, the
    standard error is cluster robust and reference degrees of freedom are the
    smallest cluster count minus one.  Bootstrap intervals are percentile
    intervals; hypothesis-test p-values remain analytical.
    """

    confidence_level: float = 0.95
    interval_method: str = "analytical"
    trim_proportion: float = 0.10
    bootstrap_iterations: int = 2_000
    random_seed: int = 42
    cluster_by: str | None = "firm"

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> InferenceConfig:
        values = config.get("statistical_inference", config)
        result = cls(
            confidence_level=float(values.get("confidence_level", 0.95)),
            interval_method=str(values.get("interval_method", "analytical")),
            trim_proportion=float(values.get("trim_proportion", 0.10)),
            bootstrap_iterations=int(values.get("bootstrap_iterations", 2_000)),
            random_seed=int(values.get("random_seed", config.get("random_seed", 42))),
            cluster_by=values.get("cluster_by", "firm"),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be between zero and one")
        if self.interval_method not in {"analytical", "bootstrap"}:
            raise ValueError("interval_method must be analytical or bootstrap")
        if not 0 <= self.trim_proportion < 0.5:
            raise ValueError("trim_proportion must be in [0, 0.5)")
        if self.bootstrap_iterations < 100:
            raise ValueError("bootstrap_iterations must be at least 100")
        if self.cluster_by not in {None, *CLUSTER_COLUMNS}:
            raise ValueError("cluster_by must be firm, event_date, two_way, or None")
        if self.interval_method == "bootstrap" and self.cluster_by == "two_way":
            raise ValueError("bootstrap intervals do not support two-way clustering")


@dataclass(frozen=True)
class StatisticalInferenceResult:
    """Reusable Stage 9 tables and optional event-time statistics."""

    summary_table: pd.DataFrame
    distribution_summary: pd.DataFrame
    hypothesis_tests: pd.DataFrame
    attrition_table: pd.DataFrame
    regression_table: pd.DataFrame
    event_time_statistics: pd.DataFrame


def _require_columns(frame: pd.DataFrame, required: Sequence[str], name: str) -> None:
    missing = sorted(set(required).difference(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")


def _directions(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    result = [("all", frame)]
    result.extend((str(direction), group) for direction, group in frame.groupby("direction", sort=True))
    return result


def _cluster_codes(frame: pd.DataFrame, cluster_by: str | None) -> tuple[np.ndarray | None, int | None]:
    if cluster_by is None:
        return None, None
    columns = CLUSTER_COLUMNS[cluster_by]
    _require_columns(frame, columns, "inference sample")
    codes = [pd.factorize(frame[column], sort=True)[0] for column in columns]
    counts = [len(np.unique(code)) for code in codes]
    if min(counts) < 2:
        raise ValueError(f"cluster_by={cluster_by} requires at least two clusters")
    groups = codes[0] if len(codes) == 1 else np.column_stack(codes)
    return groups, min(counts)


def _analytical_mean_inference(
    sample: pd.DataFrame,
    outcome: str,
    confidence_level: float,
    cluster_by: str | None,
    alternative: str,
) -> dict[str, float | int | str | None]:
    values = sample[outcome].to_numpy(dtype=float)
    n = len(values)
    mean = float(np.mean(values)) if n else np.nan
    if n < 2:
        return {
            "standard_error": np.nan,
            "test_statistic": np.nan,
            "p_value": np.nan,
            "ci_lower": np.nan,
            "ci_upper": np.nan,
            "degrees_of_freedom": np.nan,
            "cluster_count": np.nan,
            "alternative": alternative,
        }

    if cluster_by is None:
        standard_error = float(stats.sem(values))
        degrees_of_freedom = n - 1
        cluster_count: int | None = None
    else:
        cluster_columns = CLUSTER_COLUMNS[cluster_by]
        counts = [sample[column].nunique(dropna=False) for column in cluster_columns]
        cluster_count = min(counts)
        if cluster_count < 2:
            return {
                "standard_error": np.nan,
                "test_statistic": np.nan,
                "p_value": np.nan,
                "ci_lower": np.nan,
                "ci_upper": np.nan,
                "degrees_of_freedom": np.nan,
                "cluster_count": cluster_count,
                "alternative": alternative,
            }
        groups, _ = _cluster_codes(sample, cluster_by)
        fitted = smf.ols(f"{outcome} ~ 1", data=sample).fit(
            cov_type="cluster",
            cov_kwds={"groups": groups, "use_correction": True},
            use_t=True,
        )
        standard_error = float(fitted.bse.iloc[0])
        degrees_of_freedom = int(cluster_count - 1)

    statistic = mean / standard_error if standard_error > 0 else np.nan
    if np.isnan(statistic):
        p_value = np.nan
    elif alternative == "greater":
        p_value = float(stats.t.sf(statistic, degrees_of_freedom))
    elif alternative == "less":
        p_value = float(stats.t.cdf(statistic, degrees_of_freedom))
    else:
        p_value = float(2 * stats.t.sf(abs(statistic), degrees_of_freedom))
    critical = float(stats.t.ppf((1 + confidence_level) / 2, degrees_of_freedom))
    return {
        "standard_error": standard_error,
        "test_statistic": statistic,
        "p_value": p_value,
        "ci_lower": mean - critical * standard_error,
        "ci_upper": mean + critical * standard_error,
        "degrees_of_freedom": degrees_of_freedom,
        "cluster_count": cluster_count if cluster_count is not None else np.nan,
        "alternative": alternative,
    }


def _bootstrap_mean_interval(
    sample: pd.DataFrame,
    outcome: str,
    config: InferenceConfig,
    seed_offset: int,
) -> tuple[float, float, float]:
    rng = np.random.default_rng(config.random_seed + seed_offset)
    values = sample[outcome].to_numpy(dtype=float)
    estimates = np.empty(config.bootstrap_iterations, dtype=float)
    if config.cluster_by is None:
        for index in range(config.bootstrap_iterations):
            estimates[index] = rng.choice(values, size=len(values), replace=True).mean()
    else:
        cluster_column = CLUSTER_COLUMNS[config.cluster_by][0]
        clusters = list(sample.groupby(cluster_column, sort=False, dropna=False))
        if len(clusters) < 2:
            return np.nan, np.nan, np.nan
        for index in range(config.bootstrap_iterations):
            selected = rng.integers(0, len(clusters), size=len(clusters))
            draw = np.concatenate([clusters[position][1][outcome].to_numpy(dtype=float) for position in selected])
            estimates[index] = draw.mean()
    alpha = 1 - config.confidence_level
    lower, upper = np.quantile(estimates, [alpha / 2, 1 - alpha / 2])
    return float(lower), float(upper), float(np.std(estimates, ddof=1))


def _distribution(values: np.ndarray, trim_proportion: float) -> dict[str, float]:
    if len(values) == 0:
        return {name: np.nan for name in (
            "mean", "median", "standard_deviation", "trimmed_mean", "proportion_positive",
            "minimum", "p05", "p25", "p75", "p95", "maximum", "skewness", "excess_kurtosis",
        )}
    return {
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "standard_deviation": float(np.std(values, ddof=1)) if len(values) > 1 else np.nan,
        "trimmed_mean": float(stats.trim_mean(values, trim_proportion)),
        "proportion_positive": float(np.mean(values > 0)),
        "minimum": float(np.min(values)),
        "p05": float(np.quantile(values, 0.05)),
        "p25": float(np.quantile(values, 0.25)),
        "p75": float(np.quantile(values, 0.75)),
        "p95": float(np.quantile(values, 0.95)),
        "maximum": float(np.max(values)),
        "skewness": float(stats.skew(values, bias=False)) if len(values) > 2 else np.nan,
        "excess_kurtosis": float(stats.kurtosis(values, bias=False)) if len(values) > 3 else np.nan,
    }


def summarize_event_outcomes(
    outcomes: pd.DataFrame,
    config: InferenceConfig | Mapping[str, Any] = InferenceConfig(),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build summary, full-distribution, hypothesis, and attrition tables.

    Invalid horizons and missing outcomes are excluded from estimation but
    retained in ``attrition``.  Positive and negative event cells are reported
    alongside an all-event cell.
    """
    parameters = config if isinstance(config, InferenceConfig) else InferenceConfig.from_mapping(config)
    parameters.validate()
    _require_columns(
        outcomes,
        (*CELL_COLUMNS, "event_id", "direction", "valid_horizon", "missing_reason", *OUTCOMES),
        "event outcomes",
    )
    if not outcomes.empty and not outcomes["direction"].isin(["positive", "negative"]).all():
        raise ValueError("direction must contain only positive or negative")

    summaries: list[dict[str, object]] = []
    distributions: list[dict[str, object]] = []
    hypotheses: list[dict[str, object]] = []
    attrition: list[dict[str, object]] = []
    seed_offset = 0
    grouped = outcomes.groupby(list(CELL_COLUMNS), sort=True, dropna=False)
    for cell, cell_frame in grouped:
        cell_values = dict(zip(CELL_COLUMNS, cell, strict=True))
        for direction, direction_frame in _directions(cell_frame):
            base = {**cell_values, "direction": direction}
            valid_horizon = direction_frame["valid_horizon"].fillna(False).astype(bool)
            reasons = direction_frame.loc[~valid_horizon, "missing_reason"].dropna().astype(str)
            attrition.append({
                **base,
                "total_events": int(direction_frame["event_id"].nunique()),
                "valid_horizons": int(valid_horizon.sum()),
                "invalid_horizons": int((~valid_horizon).sum()),
                "missing_reasons": ";".join(sorted(set(";".join(reasons).split(";")))) if len(reasons) else "",
            })
            for outcome in OUTCOMES:
                sample = direction_frame.loc[valid_horizon & direction_frame[outcome].notna()].copy()
                values = sample[outcome].to_numpy(dtype=float)
                inference = _analytical_mean_inference(
                    sample,
                    outcome,
                    parameters.confidence_level,
                    parameters.cluster_by,
                    ALTERNATIVES[outcome],
                )
                analytical_se = inference["standard_error"]
                if parameters.interval_method == "bootstrap" and len(sample) >= 2:
                    lower, upper, bootstrap_se = _bootstrap_mean_interval(sample, outcome, parameters, seed_offset)
                    inference["ci_lower"] = lower
                    inference["ci_upper"] = upper
                    seed_offset += 1
                else:
                    bootstrap_se = np.nan
                distribution = _distribution(values, parameters.trim_proportion)
                shared = {
                    **base,
                    "outcome": outcome,
                    "sample_size": len(sample),
                    "missing_outcome_count": int((valid_horizon & direction_frame[outcome].isna()).sum()),
                }
                summaries.append({
                    **shared,
                    "mean": distribution["mean"],
                    "median": distribution["median"],
                    "standard_deviation": distribution["standard_deviation"],
                    "trimmed_mean": distribution["trimmed_mean"],
                    "standard_error": analytical_se,
                    "bootstrap_standard_error": bootstrap_se,
                    "ci_lower": inference["ci_lower"],
                    "ci_upper": inference["ci_upper"],
                    "confidence_level": parameters.confidence_level,
                    "interval_method": parameters.interval_method,
                    "p_value": inference["p_value"],
                    "proportion_positive": distribution["proportion_positive"],
                })
                distributions.append({**shared, **distribution})
                standard_deviation = distribution["standard_deviation"]
                effect_size = (
                    distribution["mean"] / standard_deviation
                    if standard_deviation is not None and np.isfinite(standard_deviation) and standard_deviation > 0
                    else np.nan
                )
                hypotheses.append({
                    **shared,
                    "null_value": 0.0,
                    "alternative": inference["alternative"],
                    "test_statistic": inference["test_statistic"],
                    "p_value": inference["p_value"],
                    "ci_lower": inference["ci_lower"],
                    "ci_upper": inference["ci_upper"],
                    "effect_size": effect_size,
                    "standard_error": analytical_se,
                    "degrees_of_freedom": inference["degrees_of_freedom"],
                    "cluster_by": parameters.cluster_by or "none",
                    "cluster_count": inference["cluster_count"],
                })

    return tuple(pd.DataFrame(rows) for rows in (summaries, distributions, hypotheses, attrition))  # type: ignore[return-value]


def _regression_groups(frame: pd.DataFrame, cluster_by: str | None) -> tuple[np.ndarray | None, int | None]:
    return _cluster_codes(frame, cluster_by)


def fit_event_regressions(
    outcomes: pd.DataFrame,
    event_characteristics: pd.DataFrame,
    *,
    confidence_level: float = 0.95,
    cluster_by: str | None = "firm",
) -> pd.DataFrame:
    """Estimate separate peer-CAR and initiator-CAR models in each design cell.

    The formula is fixed to event-time information: signed initial shock,
    direction, log1p volume, log1p market capitalization, subsector, two named
    volatility regimes, and a simultaneous-event indicator.  Extra columns in
    ``event_characteristics`` are never admitted to the design matrix.
    """
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between zero and one")
    if cluster_by not in {None, *CLUSTER_COLUMNS}:
        raise ValueError("cluster_by must be firm, event_date, two_way, or None")
    _require_columns(
        outcomes,
        (*CELL_COLUMNS, "event_id", "event_date", "security_id", "direction", "subsector",
         "initial_relative_shock", "simultaneous_event_group", "valid_horizon", "peer_car", "initiator_car"),
        "event outcomes",
    )
    _require_columns(event_characteristics, REGRESSION_CHARACTERISTICS, "event characteristics")
    if event_characteristics["event_id"].duplicated().any():
        raise ValueError("event characteristics must have one row per event_id")
    if "information_date" in event_characteristics:
        information = event_characteristics[["event_id", "information_date"]].merge(
            outcomes[["event_id", "event_date"]].drop_duplicates(), on="event_id", how="inner"
        )
        if (pd.to_datetime(information["information_date"]) > pd.to_datetime(information["event_date"])).any():
            raise ValueError("event characteristics contain information dated after the event")

    selected = event_characteristics[list(REGRESSION_CHARACTERISTICS)].copy()
    merged = outcomes.merge(selected, on="event_id", how="left", validate="many_to_one")
    if merged[["volume", "market_cap"]].lt(0).any().any():
        raise ValueError("volume and market_cap must be non-negative")
    merged["log1p_volume"] = np.log1p(merged["volume"])
    merged["log1p_market_cap"] = np.log1p(merged["market_cap"])
    merged["simultaneous_event_flag"] = merged["simultaneous_event_group"].notna().astype(float)

    predictors = [
        "initial_relative_shock", "direction", "log1p_volume", "log1p_market_cap", "subsector",
        "market_volatility_regime", "semiconductor_volatility_regime", "simultaneous_event_flag",
    ]
    formula_rhs = (
        "initial_relative_shock + C(direction) + log1p_volume + log1p_market_cap + "
        "C(subsector) + C(market_volatility_regime) + C(semiconductor_volatility_regime) + "
        "simultaneous_event_flag"
    )
    rows: list[dict[str, object]] = []
    for cell, cell_frame in merged.groupby(list(CELL_COLUMNS), sort=True, dropna=False):
        cell_values = dict(zip(CELL_COLUMNS, cell, strict=True))
        for dependent in ("peer_car", "initiator_car"):
            required = [dependent, *predictors]
            sample = cell_frame.loc[cell_frame["valid_horizon"].fillna(False)].dropna(subset=required).copy()
            if sample.empty:
                continue
            groups, cluster_count = _regression_groups(sample, cluster_by)
            ordinary = smf.ols(f"{dependent} ~ {formula_rhs}", data=sample).fit()
            if ordinary.df_resid < 1:
                raise ValueError(f"insufficient regression degrees of freedom for {cell_values}, {dependent}")
            if cluster_by is None:
                fitted = ordinary.get_robustcov_results(cov_type="HC1", use_t=True)
                degrees_of_freedom = int(ordinary.df_resid)
            else:
                fitted = ordinary.get_robustcov_results(
                    cov_type="cluster",
                    groups=groups,
                    use_correction=True,
                    df_correction=True,
                    use_t=True,
                )
                degrees_of_freedom = int(cluster_count - 1)  # type: ignore[operator]
            names = ordinary.model.exog_names
            critical = float(stats.t.ppf((1 + confidence_level) / 2, degrees_of_freedom))
            for name, coefficient, standard_error in zip(names, fitted.params, fitted.bse, strict=True):
                statistic = coefficient / standard_error if standard_error > 0 else np.nan
                p_value = float(2 * stats.t.sf(abs(statistic), degrees_of_freedom)) if np.isfinite(statistic) else np.nan
                rows.append({
                    **cell_values,
                    "dependent_variable": dependent,
                    "term": name,
                    "coefficient": float(coefficient),
                    "standard_error": float(standard_error),
                    "ci_lower": float(coefficient - critical * standard_error),
                    "ci_upper": float(coefficient + critical * standard_error),
                    "p_value": p_value,
                    "sample_size": int(fitted.nobs),
                    "dropped_observations": int(len(cell_frame) - fitted.nobs),
                    "cluster_by": cluster_by or "none_hc1",
                    "cluster_count": cluster_count if cluster_count is not None else np.nan,
                    "degrees_of_freedom": degrees_of_freedom,
                })
    return pd.DataFrame(rows)


def calculate_event_time_statistics(
    event_panel: pd.DataFrame,
    config: InferenceConfig | Mapping[str, Any] = InferenceConfig(),
) -> pd.DataFrame:
    """Calculate post-event cumulative paths and confidence intervals by day."""
    parameters = config if isinstance(config, InferenceConfig) else InferenceConfig.from_mapping(config)
    _require_columns(
        event_panel,
        ("event_id", "event_date", "security_id", "relative_day", "direction",
         "peer_definition", "return_specification", "initiator_return", "peer_return", "valid_observation"),
        "event panel",
    )
    post = event_panel.loc[event_panel["relative_day"].gt(0)].sort_values(["event_id", "relative_day"]).copy()
    valid_to_date = post.groupby("event_id")["valid_observation"].cummin().astype(bool)
    post["initiator_car"] = post.groupby("event_id")["initiator_return"].cumsum().where(valid_to_date)
    post["peer_car"] = post.groupby("event_id")["peer_return"].cumsum().where(valid_to_date)
    sign = post["direction"].map({"positive": 1.0, "negative": -1.0})
    post["convergence"] = sign * (post["peer_car"] - post["initiator_car"])

    rows: list[dict[str, object]] = []
    seed_offset = 10_000
    group_columns = ["relative_day", "return_specification", "peer_definition"]
    for cell, frame in post.groupby(group_columns, sort=True, dropna=False):
        base = dict(zip(group_columns, cell, strict=True))
        for direction, direction_frame in _directions(frame):
            for outcome in ("initiator_car", "peer_car", "convergence"):
                sample = direction_frame.loc[direction_frame[outcome].notna()].copy()
                inference = _analytical_mean_inference(
                    sample, outcome, parameters.confidence_level, parameters.cluster_by, "two-sided"
                )
                if parameters.interval_method == "bootstrap" and len(sample) >= 2:
                    lower, upper, _ = _bootstrap_mean_interval(sample, outcome, parameters, seed_offset)
                    inference["ci_lower"] = lower
                    inference["ci_upper"] = upper
                    seed_offset += 1
                rows.append({
                    **base,
                    "direction": direction,
                    "outcome": outcome,
                    "mean": float(sample[outcome].mean()) if len(sample) else np.nan,
                    "ci_lower": inference["ci_lower"],
                    "ci_upper": inference["ci_upper"],
                    "standard_error": inference["standard_error"],
                    "sample_size": len(sample),
                })
    return pd.DataFrame(rows)


def plot_event_time_with_confidence_intervals(
    statistics: pd.DataFrame,
    *,
    direction: str = "all",
    return_specification: str | None = None,
    peer_definition: str | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """Plot initiator CAR, peer CAR, and convergence with confidence bands."""
    _require_columns(statistics, ("relative_day", "direction", "outcome", "mean", "ci_lower", "ci_upper"), "event-time statistics")
    selected = statistics.loc[statistics["direction"].eq(direction)]
    for column, value in (("return_specification", return_specification), ("peer_definition", peer_definition)):
        if value is not None:
            _require_columns(selected, (column,), "event-time statistics")
            selected = selected.loc[selected[column].eq(value)]
        elif column in selected and selected[column].nunique(dropna=False) > 1:
            raise ValueError(f"select one {column} before plotting")
    figure, axis = plt.subplots(figsize=(8, 5))
    for outcome, label in (
        ("initiator_car", "Initiator CAR"),
        ("peer_car", "Peer CAR"),
        ("convergence", "Convergence"),
    ):
        line = selected.loc[selected["outcome"].eq(outcome)].sort_values("relative_day")
        axis.plot(line["relative_day"], line["mean"], marker="o", label=label)
        axis.fill_between(line["relative_day"], line["ci_lower"], line["ci_upper"], alpha=0.16)
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set(xlabel="Post-event trading day", ylabel="Average cumulative abnormal return", title=f"Event-time paths: {direction} events")
    axis.legend()
    figure.tight_layout()
    return figure, axis


def plot_outcome_distributions(
    outcomes: pd.DataFrame,
    *,
    horizon: int | None = None,
    return_specification: str | None = None,
    peer_definition: str | None = None,
) -> tuple[plt.Figure, np.ndarray]:
    """Plot the three valid outcome distributions separately by shock direction."""
    _require_columns(outcomes, ("direction", "valid_horizon", *OUTCOMES), "event outcomes")
    valid = outcomes.loc[outcomes["valid_horizon"]].copy()
    for column, value in (
        ("horizon", horizon),
        ("return_specification", return_specification),
        ("peer_definition", peer_definition),
    ):
        if value is not None:
            _require_columns(valid, (column,), "event outcomes")
            valid = valid.loc[valid[column].eq(value)]
        elif column in valid and valid[column].nunique(dropna=False) > 1:
            raise ValueError(f"select one {column} before plotting")
    figure, axes = plt.subplots(3, 2, figsize=(11, 11), squeeze=False)
    for row, outcome in enumerate(OUTCOMES):
        for column, direction in enumerate(("positive", "negative")):
            axis = axes[row, column]
            values = valid.loc[valid["direction"].eq(direction), outcome].dropna()
            if len(values):
                sns.histplot(values, kde=len(values) >= 3, ax=axis)
            axis.axvline(0, color="black", linewidth=0.8)
            axis.set(title=f"{outcome.replace('_', ' ').title()} — {direction}", xlabel=outcome, ylabel="Count")
    figure.tight_layout()
    return figure, axes


def save_inference_tables(
    result: StatisticalInferenceResult,
    output_directory: str | Path = "outputs/tables",
) -> dict[str, Path]:
    """Save reusable Stage 9 CSV tables and return their paths."""
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    tables = {
        "summary": result.summary_table,
        "distribution": result.distribution_summary,
        "hypotheses": result.hypothesis_tests,
        "attrition": result.attrition_table,
        "regressions": result.regression_table,
        "event_time": result.event_time_statistics,
    }
    paths: dict[str, Path] = {}
    for name, table in tables.items():
        path = directory / f"stage_09_{name}.csv"
        table.to_csv(path, index=False)
        paths[name] = path
    return paths


def run_statistical_inference(
    outcomes: pd.DataFrame,
    *,
    event_panel: pd.DataFrame | None = None,
    event_characteristics: pd.DataFrame | None = None,
    config: InferenceConfig | Mapping[str, Any] = InferenceConfig(),
    output_directory: str | Path | None = None,
) -> StatisticalInferenceResult:
    """Run all requested Stage 9 analyses without altering event selection."""
    parameters = config if isinstance(config, InferenceConfig) else InferenceConfig.from_mapping(config)
    summary, distributions, hypotheses, attrition = summarize_event_outcomes(outcomes, parameters)
    regressions = (
        fit_event_regressions(
            outcomes,
            event_characteristics,
            confidence_level=parameters.confidence_level,
            cluster_by=parameters.cluster_by,
        )
        if event_characteristics is not None
        else pd.DataFrame()
    )
    event_time = (
        calculate_event_time_statistics(event_panel, parameters)
        if event_panel is not None
        else pd.DataFrame()
    )
    result = StatisticalInferenceResult(summary, distributions, hypotheses, attrition, regressions, event_time)
    if output_directory is not None:
        save_inference_tables(result, output_directory)
    return result
