"""Selection-aware null models and placebo experiments for Stage 10.

The routines in this module never redefine an event or outcome.  They construct
alternative peer sets, dates, or return panels and then call the Stage 7 and 8
engines with the same configuration used for the observed sample.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from price_diffusion.event_study import (
    EventStudyConfig,
    calculate_event_outcomes,
    run_event_study,
)
from price_diffusion.events import EventDetectionConfig, detect_events
from price_diffusion.returns import calculate_relative_abnormal_returns


OUTCOMES = ("convergence", "peer_catchup", "initiator_reversal")
CELL_COLUMNS = ("horizon", "return_specification", "peer_definition")
METHOD_LABELS = {
    "observed": "Observed events",
    "random_peers": "Random peers",
    "pseudo_events": "Pseudo-events",
    "null_simulation": "Null simulation",
    "temporal_placebo": "Temporal placebo",
}


@dataclass(frozen=True)
class RobustnessConfig:
    """Pre-specified Stage 10 experiment and resampling parameters."""

    random_peer_iterations: int = 500
    pseudo_event_iterations: int = 500
    null_iterations: int = 1_000
    bootstrap_iterations: int = 2_000
    date_block_length: int = 5
    confidence_level: float = 0.95
    pseudo_event_exclusion_days: int = 10
    match_columns: tuple[str, ...] = (
        "subsector",
        "volatility_regime",
        "market_regime",
        "liquidity_bucket",
    )
    random_seed: int = 42

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> RobustnessConfig:
        values = config.get("robustness", config)
        result = cls(
            random_peer_iterations=int(values.get("random_peer_iterations", 500)),
            pseudo_event_iterations=int(values.get("pseudo_event_iterations", 500)),
            null_iterations=int(values.get("null_iterations", 1_000)),
            bootstrap_iterations=int(values.get("bootstrap_iterations", 2_000)),
            date_block_length=int(values.get("date_block_length", 5)),
            confidence_level=float(values.get("confidence_level", 0.95)),
            pseudo_event_exclusion_days=int(values.get("pseudo_event_exclusion_days", 10)),
            match_columns=tuple(values.get("match_columns", cls.match_columns)),
            random_seed=int(values.get("random_seed", config.get("random_seed", 42))),
        )
        result.validate()
        return result

    def validate(self) -> None:
        for name in (
            "random_peer_iterations",
            "pseudo_event_iterations",
            "null_iterations",
            "bootstrap_iterations",
            "date_block_length",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be between zero and one")
        if self.pseudo_event_exclusion_days < 0:
            raise ValueError("pseudo_event_exclusion_days must be non-negative")
        if not self.match_columns or len(self.match_columns) != len(set(self.match_columns)):
            raise ValueError("match_columns must contain unique names")


@dataclass(frozen=True)
class NullSimulationResult:
    """Event-level null results, iteration statistics, and audit records."""

    event_results: pd.DataFrame
    distribution: pd.DataFrame
    diagnostics: pd.DataFrame
    resampling_audit: pd.DataFrame


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], name: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")


def _config_signature(config: EventDetectionConfig | EventStudyConfig | Mapping[str, Any]) -> str:
    if isinstance(config, (EventDetectionConfig, EventStudyConfig)):
        values: Any = asdict(config)
    else:
        values = config
    encoded = json.dumps(values, sort_keys=True, default=str).encode()
    return sha256(encoded).hexdigest()[:16]


def _parameters(
    config: RobustnessConfig | Mapping[str, Any],
) -> RobustnessConfig:
    return config if isinstance(config, RobustnessConfig) else RobustnessConfig.from_mapping(config)


def sample_random_peer_membership(
    events: pd.DataFrame,
    economic_peer_membership: pd.DataFrame,
    universe_membership: pd.DataFrame,
    *,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Replace event-date economic peers with eligible random semiconductors.

    The number and exact multiset of original weights are retained for every
    event portfolio. Sampling is without replacement and excludes the focal
    company. Only event-date rows are returned because Stage 8 freezes peers at
    event time.
    """
    _require_columns(events, ("event_id", "date", "security_id", "peer_definition"), "events")
    _require_columns(
        economic_peer_membership,
        ("date", "security_id", "peer_id", "peer_definition", "weight"),
        "economic peer membership",
    )
    _require_columns(universe_membership, ("date", "security_id", "eligible"), "universe membership")
    if universe_membership.duplicated(["date", "security_id"]).any():
        raise ValueError("universe membership date/security rows must be unique")

    rng = np.random.default_rng(random_seed)
    rows: list[dict[str, object]] = []
    eligible = universe_membership.loc[universe_membership["eligible"].astype(bool)]
    original_lookup = {
        key: group.sort_values("peer_id", kind="stable")
        for key, group in economic_peer_membership.groupby(
            ["date", "security_id", "peer_definition"], sort=False
        )
    }
    eligible_by_date = {
        date: np.sort(group["security_id"].astype(str).unique())
        for date, group in eligible.groupby("date", sort=False)
    }
    for event in events.sort_values(["date", "event_id"], kind="stable").itertuples(index=False):
        original = original_lookup.get(
            (event.date, event.security_id, event.peer_definition),
            economic_peer_membership.iloc[0:0],
        )
        if original.empty:
            raise ValueError(f"event {event.event_id} has no event-date economic peers")
        candidates = eligible_by_date.get(event.date, np.array([], dtype=object))
        candidates = candidates[candidates != event.security_id]
        if len(candidates) < len(original):
            raise ValueError(f"event {event.event_id} has too few eligible random-peer candidates")
        selected = rng.choice(candidates, size=len(original), replace=False)
        weights = original["weight"].to_numpy(dtype=float).copy()
        rng.shuffle(weights)
        for peer_id, weight in zip(selected, weights, strict=True):
            rows.append(
                {
                    "date": event.date,
                    "security_id": event.security_id,
                    "peer_id": peer_id,
                    "peer_definition": event.peer_definition,
                    "weight": float(weight),
                }
            )
    output = pd.DataFrame(rows)
    validate_random_peer_placebo(output, events, economic_peer_membership, universe_membership)
    return output.sort_values(
        ["date", "security_id", "peer_definition", "peer_id"], ignore_index=True
    )


def validate_random_peer_placebo(
    random_membership: pd.DataFrame,
    events: pd.DataFrame,
    economic_peer_membership: pd.DataFrame,
    universe_membership: pd.DataFrame,
) -> None:
    """Fail closed when random peers violate eligibility, count, or weights."""
    _require_columns(
        random_membership,
        ("date", "security_id", "peer_id", "peer_definition", "weight"),
        "random peer membership",
    )
    if random_membership["security_id"].eq(random_membership["peer_id"]).any():
        raise ValueError("random peers must exclude the initiator")
    key = ["date", "security_id", "peer_definition"]
    weight_sums = random_membership.groupby(key, dropna=False)["weight"].sum()
    if not np.allclose(weight_sums.to_numpy(float), 1.0, atol=1e-10, rtol=0):
        raise ValueError("random-peer weights must sum to one")
    if random_membership["weight"].lt(0).any():
        raise ValueError("random-peer weights must be non-negative")

    event_keys = events[key].drop_duplicates()
    actual_counts = random_membership.groupby(key).size().rename("random_count")
    relevant_original = economic_peer_membership.merge(
        event_keys, on=key, how="inner", validate="many_to_one"
    )
    original_counts = relevant_original.groupby(key).size().rename("original_count")
    counts = event_keys.merge(actual_counts, on=key, how="left").merge(
        original_counts, on=key, how="left"
    )
    if counts[["random_count", "original_count"]].isna().any().any() or not counts[
        "random_count"
    ].eq(counts["original_count"]).all():
        raise ValueError("random-peer portfolios must preserve original peer counts")

    eligible = universe_membership.loc[universe_membership["eligible"], ["date", "security_id"]]
    checked = random_membership.merge(
        eligible.rename(columns={"security_id": "peer_id"}),
        on=["date", "peer_id"],
        how="left",
        indicator=True,
    )
    if checked["_merge"].ne("both").any():
        raise ValueError("random peers must be eligible on the event date")

    original_lookup = {
        keys: group
        for keys, group in relevant_original.groupby(key, sort=False)
    }
    for keys, random_group in random_membership.groupby(key, sort=False):
        original = original_lookup[keys]
        if not np.allclose(
            np.sort(random_group["weight"].to_numpy(float)),
            np.sort(original["weight"].to_numpy(float)),
            atol=1e-12,
            rtol=0,
        ):
            raise ValueError("random peers must preserve the original weighting rule")


def run_random_peer_placebo(
    events: pd.DataFrame,
    returns: pd.DataFrame,
    economic_peer_membership: pd.DataFrame,
    universe_membership: pd.DataFrame,
    event_study_config: EventStudyConfig | Mapping[str, Any],
    *,
    return_column: str,
    return_specification: str,
    config: RobustnessConfig | Mapping[str, Any] = RobustnessConfig(),
) -> pd.DataFrame:
    """Run repeated event studies with eligible random event-date peers."""
    parameters = _parameters(config)
    event_keys = events[["date", "security_id", "peer_definition"]].drop_duplicates()
    relevant_economic_membership = economic_peer_membership.merge(
        event_keys,
        on=["date", "security_id", "peer_definition"],
        how="inner",
        validate="many_to_one",
    )
    relevant_universe = universe_membership.loc[
        universe_membership["date"].isin(events["date"].unique())
    ].copy()
    outputs: list[pd.DataFrame] = []
    for iteration in range(parameters.random_peer_iterations):
        membership = sample_random_peer_membership(
            events,
            relevant_economic_membership,
            relevant_universe,
            random_seed=parameters.random_seed + iteration,
        )
        outcomes = run_event_study(
            events,
            returns,
            membership,
            event_study_config,
            return_column=return_column,
            return_specification=return_specification,
        ).outcomes
        outcomes.insert(0, "placebo_iteration", iteration)
        outcomes.insert(1, "method", "random_peers")
        outputs.append(outcomes)
    return pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()


def sample_pseudo_events(
    events: pd.DataFrame,
    matching_panel: pd.DataFrame,
    peer_membership: pd.DataFrame,
    *,
    match_columns: Sequence[str],
    exclusion_days: int = 10,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Sample one eligible, exactly matched non-event date per real event."""
    _require_columns(events, ("event_id", "date", "security_id", "peer_definition"), "events")
    _require_columns(
        matching_panel,
        ("date", "security_id", "eligible", *match_columns),
        "pseudo-event matching panel",
    )
    _require_columns(
        peer_membership,
        ("date", "security_id", "peer_definition", "peer_id", "weight"),
        "peer membership",
    )
    if matching_panel.duplicated(["date", "security_id"]).any():
        raise ValueError("matching panel must have unique date/security rows")
    rng = np.random.default_rng(random_seed)
    real_dates_by_firm = {
        firm: tuple(group["date"])
        for firm, group in events.groupby("security_id", sort=False)
    }
    matching_by_firm = {
        firm: group.copy()
        for firm, group in matching_panel.groupby("security_id", sort=False)
    }
    matching_lookup = matching_panel.set_index(["date", "security_id"])
    valid_peer_keys = peer_membership.groupby(
        ["date", "security_id", "peer_definition"], as_index=False
    )["weight"].sum()
    valid_peer_keys = valid_peer_keys.loc[np.isclose(valid_peer_keys["weight"], 1.0)]
    valid_peer_dates = {
        (security_id, definition): set(group["date"])
        for (security_id, definition), group in valid_peer_keys.groupby(
            ["security_id", "peer_definition"], sort=False
        )
    }
    rows: list[dict[str, object]] = []
    for event in events.sort_values(["date", "event_id"], kind="stable").itertuples(index=False):
        event_dict = event._asdict()
        try:
            source = matching_lookup.loc[(event.date, event.security_id)]
        except KeyError as error:
            raise ValueError(f"event {event.event_id} must have one matching-panel row") from error
        if isinstance(source, pd.DataFrame):
            raise ValueError(f"event {event.event_id} must have one matching-panel row")
        candidates = matching_by_firm[event.security_id]
        candidates = candidates.loc[candidates["eligible"].astype(bool)].copy()
        for column in match_columns:
            candidates = candidates.loc[candidates[column].eq(source[column])]
        for real_date in real_dates_by_firm[event.security_id]:
            distance = (candidates["date"] - real_date).abs().dt.days
            candidates = candidates.loc[distance.gt(exclusion_days)]
        candidates = candidates.loc[
            candidates["date"].isin(
                valid_peer_dates.get((event.security_id, event.peer_definition), set())
            )
        ]
        if candidates.empty:
            raise ValueError(f"event {event.event_id} has no eligible exactly matched pseudo-date")
        chosen = candidates.iloc[int(rng.integers(0, len(candidates)))]
        event_dict["source_event_id"] = event.event_id
        event_dict["event_id"] = f"pseudo_{sha256(f'{event.event_id}|{chosen['date']}'.encode()).hexdigest()[:16]}"
        event_dict["date"] = chosen["date"]
        event_dict["simultaneous_event_group"] = pd.NA
        for column in match_columns:
            event_dict[column] = chosen[column]
        rows.append(event_dict)
    output = pd.DataFrame(rows)
    validate_pseudo_events(output, events, matching_panel, match_columns, exclusion_days)
    return output


def validate_pseudo_events(
    pseudo_events: pd.DataFrame,
    real_events: pd.DataFrame,
    matching_panel: pd.DataFrame,
    match_columns: Sequence[str],
    exclusion_days: int,
) -> None:
    """Validate pseudo count, company, strata, date exclusion, and eligibility."""
    if len(pseudo_events) != len(real_events):
        raise ValueError("pseudo-event sampling must preserve the event count")
    merged = pseudo_events.merge(
        real_events[["event_id", "date", "security_id"]].rename(
            columns={"event_id": "source_event_id", "date": "real_date", "security_id": "real_security_id"}
        ),
        on="source_event_id",
        how="left",
        validate="one_to_one",
    )
    if merged["real_security_id"].isna().any() or not merged["security_id"].eq(
        merged["real_security_id"]
    ).all():
        raise ValueError("pseudo-events must preserve the event company")
    if (merged["date"] - merged["real_date"]).abs().dt.days.le(exclusion_days).any():
        raise ValueError("pseudo dates must lie outside the event exclusion window")
    characteristics = matching_panel[["date", "security_id", "eligible", *match_columns]]
    selected = pseudo_events.merge(
        characteristics,
        on=["date", "security_id"],
        suffixes=("", "_candidate"),
        how="left",
        validate="many_to_one",
    )
    if selected["eligible"].isna().any() or not selected["eligible"].astype(bool).all():
        raise ValueError("pseudo-events must obey universe eligibility")
    sources = real_events[["event_id", "date", "security_id"]].merge(
        characteristics,
        on=["date", "security_id"],
        how="left",
        validate="one_to_one",
    ).rename(columns={"event_id": "source_event_id"})
    compared = selected.merge(
        sources[["source_event_id", *match_columns]],
        on="source_event_id",
        suffixes=("_pseudo", "_real"),
    )
    for column in match_columns:
        if not compared[f"{column}_pseudo"].eq(compared[f"{column}_real"]).all():
            raise ValueError(f"pseudo-events must exactly match {column}")


def run_pseudo_event_placebo(
    events: pd.DataFrame,
    returns: pd.DataFrame,
    peer_membership: pd.DataFrame,
    matching_panel: pd.DataFrame,
    event_study_config: EventStudyConfig | Mapping[str, Any],
    *,
    return_column: str,
    return_specification: str,
    config: RobustnessConfig | Mapping[str, Any] = RobustnessConfig(),
) -> pd.DataFrame:
    """Run event studies on matched, eligible non-event dates."""
    parameters = _parameters(config)
    event_firms = set(events["security_id"])
    relevant_matching_panel = matching_panel.loc[
        matching_panel["security_id"].isin(event_firms)
    ].copy()
    relevant_peer_membership = peer_membership.loc[
        peer_membership["security_id"].isin(event_firms)
    ].copy()
    outputs: list[pd.DataFrame] = []
    for iteration in range(parameters.pseudo_event_iterations):
        pseudo = sample_pseudo_events(
            events,
            relevant_matching_panel,
            relevant_peer_membership,
            match_columns=parameters.match_columns,
            exclusion_days=parameters.pseudo_event_exclusion_days,
            random_seed=parameters.random_seed + 100_000 + iteration,
        )
        outcomes = run_event_study(
            pseudo,
            returns,
            relevant_peer_membership,
            event_study_config,
            return_column=return_column,
            return_specification=return_specification,
        ).outcomes
        outcomes = outcomes.merge(
            pseudo[["event_id", "source_event_id"]], on="event_id", how="left", validate="many_to_one"
        )
        outcomes.insert(0, "placebo_iteration", iteration)
        outcomes.insert(1, "method", "pseudo_events")
        outputs.append(outcomes)
    return pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()


def temporal_placebo(
    events: pd.DataFrame,
    event_panel: pd.DataFrame,
    event_study_config: EventStudyConfig | Mapping[str, Any],
) -> pd.DataFrame:
    """Apply the normal outcome calculation to pre-event windows in reverse time."""
    reversed_panel = event_panel.copy()
    reversed_panel["relative_day"] = -reversed_panel["relative_day"]
    outcomes = calculate_event_outcomes(events, reversed_panel, event_study_config)
    outcomes.insert(0, "method", "temporal_placebo")
    return outcomes


def resample_returns_without_lead_lag(
    returns: pd.DataFrame,
    *,
    return_column: str,
    date_regimes: pd.DataFrame | None = None,
    regime_columns: Sequence[str] = (),
    random_seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Causally resample synchronous residual vectors within market regimes.

    The date-specific cross-sectional mean is retained. Whole residual vectors
    are sampled from the same regime using only dates no later than the target,
    which preserves their contemporaneous covariance and prevents future-data
    use. Independent date draws break the original cross-company lead-lag path.
    """
    _require_columns(returns, ("date", "security_id", return_column), "returns")
    if returns.duplicated(["date", "security_id"]).any():
        raise ValueError("returns must have unique date/security rows")
    pivot = returns.pivot(index="date", columns="security_id", values=return_column).sort_index()
    if pivot.empty:
        raise ValueError("returns cannot be empty")
    common = pivot.mean(axis=1, skipna=True)
    residuals = pivot.sub(common, axis=0)
    dates = pd.DataFrame({"date": pivot.index})
    if regime_columns:
        if date_regimes is None:
            raise ValueError("date_regimes is required when regime_columns are specified")
        _require_columns(date_regimes, ("date", *regime_columns), "date regimes")
        if date_regimes["date"].duplicated().any():
            raise ValueError("date regimes must have unique dates")
        dates = dates.merge(
            date_regimes[["date", *regime_columns]], on="date", how="left", validate="one_to_one"
        )
        if dates[list(regime_columns)].isna().any().any():
            raise ValueError("every return date must have complete regime labels")
    else:
        dates["null_regime_all"] = "all"
        regime_columns = ("null_regime_all",)

    rng = np.random.default_rng(random_seed)
    audit_rows: list[dict[str, object]] = []
    donor_pools: dict[tuple[object, ...], list[int]] = {}
    donor_indices: list[int] = []
    for target_index, target in enumerate(dates.itertuples(index=False)):
        target_date = target.date
        regime_key = tuple(getattr(target, column) for column in regime_columns)
        pool = donor_pools.setdefault(regime_key, [])
        # Adding the target before drawing exactly implements donor_date <=
        # target_date while avoiding a full DataFrame filter for every date.
        pool.append(target_index)
        donor_index = pool[int(rng.integers(0, len(pool)))]
        donor_indices.append(donor_index)
        donor_date = dates.iloc[donor_index]["date"]
        audit_rows.append(
            {
                "target_date": target_date,
                "source_date": donor_date,
                "future_data_used": bool(donor_date > target_date),
                **{
                    column: getattr(target, column)
                    for column in regime_columns
                    if column != "null_regime_all"
                },
            }
        )
    simulated = pd.DataFrame(
        common.to_numpy()[:, None] + residuals.to_numpy()[donor_indices],
        index=pivot.index,
        columns=pivot.columns,
    )
    long = simulated.rename_axis(columns="security_id").reset_index().melt(
        id_vars="date", var_name="security_id", value_name=return_column
    )
    original_columns = [column for column in returns.columns if column not in {return_column}]
    output = returns[original_columns].merge(
        long, on=["date", "security_id"], how="left", validate="one_to_one"
    )
    audit = pd.DataFrame(audit_rows)
    if audit["future_data_used"].any():
        raise AssertionError("null resampling may not use future donor dates")
    return output, audit


def _build_detection_input(
    simulated_returns: pd.DataFrame,
    peer_membership: pd.DataFrame,
    detection_metadata: pd.DataFrame,
    return_column: str,
) -> pd.DataFrame:
    relative = calculate_relative_abnormal_returns(
        simulated_returns,
        peer_membership,
        abnormal_return_column=return_column,
    )
    # A simulated donor vector can carry the frozen panel's listing/calendar
    # missingness onto a target date. Such rows are not observable event
    # candidates and must be removed before the strict detector validation,
    # exactly as unavailable observed returns are absent from the production
    # relative-return panel.
    relative = relative.loc[relative["relative_abnormal_return"].notna()].copy()
    keys = ["date", "security_id", "peer_definition"]
    _require_columns(
        detection_metadata,
        (*keys, "peer_group", "subsector", "corporate_action_type"),
        "detection metadata",
    )
    if detection_metadata.duplicated(keys).any():
        raise ValueError("detection metadata must have unique date/security/definition rows")
    extras = [column for column in detection_metadata.columns if column not in relative.columns]
    output = relative.merge(
        detection_metadata[keys + extras], on=keys, how="left", validate="one_to_one"
    )
    required = ["peer_group", "subsector", "corporate_action_type"]
    if output[required].isna().any().any():
        raise ValueError("detection metadata does not cover every simulated relative return")
    return output


def run_selection_preserving_null(
    returns: pd.DataFrame,
    peer_membership: pd.DataFrame,
    detection_metadata: pd.DataFrame,
    event_detection_config: EventDetectionConfig | Mapping[str, Any],
    event_study_config: EventStudyConfig | Mapping[str, Any],
    *,
    return_column: str,
    return_specification: str,
    date_regimes: pd.DataFrame | None = None,
    regime_columns: Sequence[str] = (),
    config: RobustnessConfig | Mapping[str, Any] = RobustnessConfig(),
) -> NullSimulationResult:
    """Resample returns, redetect events, and rerun Stage 8 each iteration."""
    parameters = _parameters(config)
    event_outputs: list[pd.DataFrame] = []
    distribution_rows: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    audits: list[pd.DataFrame] = []
    detection_signature = _config_signature(event_detection_config)
    study_signature = _config_signature(event_study_config)

    for iteration in range(parameters.null_iterations):
        simulated, audit = resample_returns_without_lead_lag(
            returns,
            return_column=return_column,
            date_regimes=date_regimes,
            regime_columns=regime_columns,
            random_seed=parameters.random_seed + 200_000 + iteration,
        )
        audit.insert(0, "null_iteration", iteration)
        audits.append(audit)
        detection_input = _build_detection_input(
            simulated, peer_membership, detection_metadata, return_column
        )
        events = detect_events(detection_input, event_detection_config)
        result = run_event_study(
            events,
            simulated,
            peer_membership,
            event_study_config,
            return_column=return_column,
            return_specification=return_specification,
        )
        outcomes = result.outcomes.copy()
        if not outcomes.empty:
            outcomes.insert(0, "null_iteration", iteration)
            outcomes.insert(1, "method", "null_simulation")
            event_outputs.append(outcomes)
        diagnostics.append(
            {
                "null_iteration": iteration,
                "detected_event_count": int(events["event_id"].nunique()),
                "valid_outcome_count": int(result.outcomes["valid_horizon"].sum()) if not result.outcomes.empty else 0,
                "detection_config_signature": detection_signature,
                "event_study_config_signature": study_signature,
                "future_data_used": bool(audit["future_data_used"].any()),
            }
        )
        valid = result.outcomes.loc[result.outcomes["valid_horizon"]]
        for cell, cell_frame in valid.groupby(list(CELL_COLUMNS), sort=True, dropna=False):
            base = dict(zip(CELL_COLUMNS, cell, strict=True))
            for outcome in OUTCOMES:
                values = cell_frame[outcome].dropna()
                distribution_rows.append(
                    {
                        "null_iteration": iteration,
                        **base,
                        "outcome": outcome,
                        "statistic": float(values.mean()) if len(values) else np.nan,
                        "sample_size": int(len(values)),
                        "detected_event_count": int(events["event_id"].nunique()),
                    }
                )
    columns = ["null_iteration", "method"]
    empty_events = pd.DataFrame(columns=columns)
    return NullSimulationResult(
        pd.concat(event_outputs, ignore_index=True) if event_outputs else empty_events,
        pd.DataFrame(distribution_rows),
        pd.DataFrame(diagnostics),
        pd.concat(audits, ignore_index=True),
    )


def compare_observed_to_null(
    observed_outcomes: pd.DataFrame,
    null_distribution: pd.DataFrame,
) -> pd.DataFrame:
    """Compute finite-simulation empirical p-values and percentile locations."""
    _require_columns(
        observed_outcomes,
        (*CELL_COLUMNS, "valid_horizon", *OUTCOMES),
        "observed outcomes",
    )
    _require_columns(
        null_distribution,
        (*CELL_COLUMNS, "outcome", "statistic", "null_iteration"),
        "null distribution",
    )
    observed = observed_outcomes.loc[observed_outcomes["valid_horizon"]]
    rows: list[dict[str, object]] = []
    for cell, frame in observed.groupby(list(CELL_COLUMNS), sort=True, dropna=False):
        base = dict(zip(CELL_COLUMNS, cell, strict=True))
        selected_null = null_distribution.copy()
        for column, value in base.items():
            selected_null = selected_null.loc[selected_null[column].eq(value)]
        for outcome in OUTCOMES:
            observed_values = frame[outcome].dropna()
            observed_statistic = float(observed_values.mean()) if len(observed_values) else np.nan
            null_values = selected_null.loc[
                selected_null["outcome"].eq(outcome), "statistic"
            ].dropna().to_numpy(float)
            if len(null_values) and np.isfinite(observed_statistic):
                p_value = (1 + np.sum(null_values >= observed_statistic)) / (len(null_values) + 1)
                percentile = 100 * (
                    np.sum(null_values < observed_statistic)
                    + 0.5 * np.sum(null_values == observed_statistic)
                ) / len(null_values)
            else:
                p_value = percentile = np.nan
            rows.append(
                {
                    **base,
                    "outcome": outcome,
                    "observed_statistic": observed_statistic,
                    "observed_sample_size": int(len(observed_values)),
                    "null_mean": float(np.mean(null_values)) if len(null_values) else np.nan,
                    "null_standard_deviation": float(np.std(null_values, ddof=1)) if len(null_values) > 1 else np.nan,
                    "null_iterations": int(len(null_values)),
                    "empirical_p_value": float(p_value),
                    "percentile_location": float(percentile),
                    "alternative": "greater",
                }
            )
    return pd.DataFrame(rows)


def dependence_aware_bootstrap(
    outcomes: pd.DataFrame,
    *,
    method: str,
    iterations: int = 2_000,
    date_block_length: int = 5,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Bootstrap whole firms or contiguous event-date blocks.

    Firm blocks retain every event and overlapping horizon for a sampled firm.
    Date blocks retain all same-date events and local runs of correlated dates.
    """
    if method not in {"firm", "date"}:
        raise ValueError("method must be firm or date")
    if iterations < 1 or date_block_length < 1:
        raise ValueError("iterations and date_block_length must be positive")
    _require_columns(
        outcomes,
        (*CELL_COLUMNS, "security_id", "event_date", "valid_horizon", *OUTCOMES),
        "outcomes",
    )
    valid = outcomes.loc[outcomes["valid_horizon"]].copy()
    if valid.empty:
        return pd.DataFrame()
    rng = np.random.default_rng(random_seed)
    rows: list[dict[str, object]] = []
    firms = valid["security_id"].drop_duplicates().to_numpy()
    dates = np.sort(valid["event_date"].drop_duplicates().to_numpy())
    for iteration in range(iterations):
        if method == "firm":
            selected = rng.choice(firms, size=len(firms), replace=True)
            draw = pd.concat(
                [valid.loc[valid["security_id"].eq(firm)] for firm in selected],
                ignore_index=True,
            )
        else:
            selected_dates: list[np.datetime64] = []
            while len(selected_dates) < len(dates):
                start = int(rng.integers(0, len(dates)))
                block = [dates[(start + offset) % len(dates)] for offset in range(date_block_length)]
                selected_dates.extend(block)
            draw = pd.concat(
                [valid.loc[valid["event_date"].eq(date)] for date in selected_dates[: len(dates)]],
                ignore_index=True,
            )
        for cell, frame in draw.groupby(list(CELL_COLUMNS), sort=True, dropna=False):
            base = dict(zip(CELL_COLUMNS, cell, strict=True))
            for outcome in OUTCOMES:
                values = frame[outcome].dropna()
                rows.append(
                    {
                        "bootstrap_iteration": iteration,
                        "bootstrap_method": method,
                        **base,
                        "outcome": outcome,
                        "statistic": float(values.mean()) if len(values) else np.nan,
                        "sample_size": int(len(values)),
                    }
                )
    return pd.DataFrame(rows)


def _summarize_method(
    outcomes: pd.DataFrame,
    method: str,
    confidence_level: float,
    *,
    bootstrap_method: str,
    bootstrap_iterations: int,
    date_block_length: int,
    random_seed: int,
) -> pd.DataFrame:
    valid = outcomes.loc[outcomes["valid_horizon"]].copy()
    iteration_column = next(
        (column for column in ("placebo_iteration", "null_iteration") if column in valid),
        None,
    )
    bootstrap = (
        dependence_aware_bootstrap(
            valid,
            method=bootstrap_method,
            iterations=bootstrap_iterations,
            date_block_length=date_block_length,
            random_seed=random_seed,
        )
        if iteration_column is None
        else pd.DataFrame()
    )
    rows: list[dict[str, object]] = []
    for cell, frame in valid.groupby(list(CELL_COLUMNS), sort=True, dropna=False):
        base = dict(zip(CELL_COLUMNS, cell, strict=True))
        for outcome in OUTCOMES:
            values = frame[outcome].dropna()
            if iteration_column:
                estimates = frame.groupby(iteration_column)[outcome].mean().dropna().to_numpy(float)
                reported_sample_size = int(
                    round(frame.groupby(iteration_column)[outcome].count().mean())
                )
            else:
                estimates_frame = bootstrap.loc[bootstrap["outcome"].eq(outcome)]
                for column, value in base.items():
                    estimates_frame = estimates_frame.loc[estimates_frame[column].eq(value)]
                estimates = estimates_frame["statistic"].dropna().to_numpy(float)
                reported_sample_size = int(len(values))
            alpha = 1 - confidence_level
            lower, upper = (
                np.quantile(estimates, [alpha / 2, 1 - alpha / 2])
                if len(estimates)
                else (np.nan, np.nan)
            )
            rows.append(
                {
                    **base,
                    "method": method,
                    "method_label": METHOD_LABELS.get(method, method),
                    "outcome": outcome,
                    "mean": float(values.mean()) if len(values) else np.nan,
                    "ci_lower": float(lower),
                    "ci_upper": float(upper),
                    "sample_size": reported_sample_size,
                    "experiment_iterations": int(len(estimates)),
                }
            )
    return pd.DataFrame(rows)


def build_comparison_table(
    observed_outcomes: pd.DataFrame,
    *,
    random_peer_outcomes: pd.DataFrame | None = None,
    pseudo_event_outcomes: pd.DataFrame | None = None,
    temporal_outcomes: pd.DataFrame | None = None,
    null_distribution: pd.DataFrame | None = None,
    confidence_level: float = 0.95,
    bootstrap_method: str = "firm",
    bootstrap_iterations: int = 2_000,
    date_block_length: int = 5,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Create a standardized method/outcome comparison table.

    Observed and temporal confidence intervals use the requested dependence-aware
    bootstrap. Repeated randomized experiments use the distribution of their
    iteration-level means, and simulated-null intervals use null iteration means.
    """
    summary_options = {
        "bootstrap_method": bootstrap_method,
        "bootstrap_iterations": bootstrap_iterations,
        "date_block_length": date_block_length,
        "random_seed": random_seed,
    }
    tables = [
        _summarize_method(
            observed_outcomes, "observed", confidence_level, **summary_options
        )
    ]
    for method, frame in (
        ("random_peers", random_peer_outcomes),
        ("pseudo_events", pseudo_event_outcomes),
        ("temporal_placebo", temporal_outcomes),
    ):
        if frame is not None and not frame.empty:
            tables.append(
                _summarize_method(frame, method, confidence_level, **summary_options)
            )
    if null_distribution is not None and not null_distribution.empty:
        alpha = 1 - confidence_level
        null_rows: list[dict[str, object]] = []
        for cell, frame in null_distribution.groupby(
            [*CELL_COLUMNS, "outcome"], sort=True, dropna=False
        ):
            base = dict(zip((*CELL_COLUMNS, "outcome"), cell, strict=True))
            values = frame["statistic"].dropna().to_numpy(float)
            lower, upper = np.quantile(values, [alpha / 2, 1 - alpha / 2]) if len(values) else (np.nan, np.nan)
            null_rows.append(
                {
                    **base,
                    "method": "null_simulation",
                    "method_label": METHOD_LABELS["null_simulation"],
                    "mean": float(np.mean(values)) if len(values) else np.nan,
                    "ci_lower": float(lower),
                    "ci_upper": float(upper),
                    "sample_size": int(round(frame["sample_size"].mean())) if len(frame) else 0,
                    "experiment_iterations": int(len(values)),
                }
            )
        tables.append(pd.DataFrame(null_rows))
    return pd.concat(tables, ignore_index=True).sort_values(
        [*CELL_COLUMNS, "outcome", "method"], ignore_index=True
    )


def plot_null_distribution(
    null_distribution: pd.DataFrame,
    null_comparison: pd.DataFrame,
    *,
    outcome: str = "convergence",
    horizon: int | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """Plot a simulated null distribution and its observed statistic."""
    selected = null_distribution.loc[null_distribution["outcome"].eq(outcome)]
    comparison = null_comparison.loc[null_comparison["outcome"].eq(outcome)]
    if horizon is not None:
        selected = selected.loc[selected["horizon"].eq(horizon)]
        comparison = comparison.loc[comparison["horizon"].eq(horizon)]
    elif selected["horizon"].nunique() > 1:
        raise ValueError("select one horizon before plotting")
    for column in ("return_specification", "peer_definition"):
        if selected[column].nunique(dropna=False) > 1:
            raise ValueError(f"select one {column} before plotting")
    values = selected["statistic"].dropna()
    if values.empty or len(comparison) != 1:
        raise ValueError("plot requires one non-empty null cell and one observed comparison row")
    figure, axis = plt.subplots(figsize=(8, 5))
    axis.hist(values, bins="auto", alpha=0.75, color="#4C78A8")
    observed = float(comparison.iloc[0]["observed_statistic"])
    axis.axvline(observed, color="#E45756", linewidth=2, label=f"Observed: {observed:.4f}")
    axis.axvline(values.mean(), color="black", linestyle="--", label=f"Null mean: {values.mean():.4f}")
    axis.set(xlabel=f"Mean {outcome.replace('_', ' ')}", ylabel="Null iterations", title="Selection-preserving null distribution")
    axis.legend()
    figure.tight_layout()
    return figure, axis


def plot_placebo_comparison(
    comparison_table: pd.DataFrame,
    *,
    horizon: int | None = None,
) -> tuple[plt.Figure, np.ndarray]:
    """Compare observed, random-peer, and pseudo-event outcome means."""
    selected = comparison_table.copy()
    if horizon is not None:
        selected = selected.loc[selected["horizon"].eq(horizon)]
    elif selected["horizon"].nunique() > 1:
        raise ValueError("select one horizon before plotting")
    for column in ("return_specification", "peer_definition"):
        if selected[column].nunique(dropna=False) > 1:
            raise ValueError(f"select one {column} before plotting")
    methods = [method for method in METHOD_LABELS if method in set(selected["method"])]
    figure, axes = plt.subplots(1, 3, figsize=(13, 4), squeeze=False)
    for axis, outcome in zip(axes[0], OUTCOMES, strict=True):
        frame = selected.loc[selected["outcome"].eq(outcome)].set_index("method").reindex(methods)
        positions = np.arange(len(frame))
        errors = np.vstack([frame["mean"] - frame["ci_lower"], frame["ci_upper"] - frame["mean"]])
        axis.bar(positions, frame["mean"], color="#72B7B2")
        axis.errorbar(positions, frame["mean"], yerr=errors, fmt="none", color="black", capsize=3)
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_xticks(positions, frame["method_label"], rotation=30, ha="right")
        axis.set_title(outcome.replace("_", " ").title())
    figure.tight_layout()
    return figure, axes[0]


def save_robustness_tables(
    tables: Mapping[str, pd.DataFrame],
    output_directory: str | Path = "outputs/tables",
) -> dict[str, Path]:
    """Write Stage 10 data products with stable, descriptive names."""
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, table in tables.items():
        path = directory / f"stage_10_{name}.csv"
        table.to_csv(path, index=False)
        paths[name] = path
    return paths
