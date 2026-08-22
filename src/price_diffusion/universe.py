"""Approved-universe integration and point-in-time research eligibility.

The classification CSV is authoritative for economic membership. This module
validates and transports those decisions; it never infers semiconductor status
from prices, vendor industry codes, or eligibility outcomes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from price_diffusion.paths import PROJECT_ROOT
from price_diffusion.validation import (
    DataValidationError,
    ValidationIssue,
    validate_daily_panel,
    validate_security_master,
    validate_semiconductor_classification,
    validate_universe_membership,
)

METADATA_COLUMNS = (
    "ticker", "company_name", "exchange_or_market", "subsector",
    "semiconductor_role", "business_description", "inclusion_reason",
    "review_flag", "universe_tier", "notes",
)
SECURITY_MASTER_COLUMNS = (
    "security_id", "ticker", "company_name", "exchange_or_market", "subsector",
    "semiconductor_role", "universe_tier", "review_flag",
)
UNIVERSE_OUTPUT_COLUMNS = ("date", "security_id", "eligible", "exclusion_reason")

# The reviewed Stage 11A taxonomy, not a market-data inference.
APPROVED_SUBSECTORS = frozenset({
    "analog_mixed_signal", "eda_ip", "fabless_compute",
    "fabless_mobile_connectivity", "foundry",
    "integrated_device_manufacturer", "memory", "packaging_testing",
    "semiconductor_equipment", "semiconductor_materials",
})
APPROVED_UNIVERSE_TIERS = frozenset({"core", "extension", "questionable"})


def _metadata_error(code: str, message: str) -> None:
    raise DataValidationError(
        [ValidationIssue("semiconductor_classification", code, message)]
    )


def validate_classification_metadata(frame: pd.DataFrame) -> None:
    """Fail closed on the approved Stage 11A metadata contract."""
    if not isinstance(frame, pd.DataFrame):
        _metadata_error("not_dataframe", "metadata must be a pandas DataFrame")
    missing = sorted(set(METADATA_COLUMNS).difference(frame.columns))
    if missing:
        _metadata_error(
            "missing_columns", "required columns are missing: " + ", ".join(missing)
        )
    required = frame[list(METADATA_COLUMNS)]
    null_columns = required.columns[required.isna().any()].tolist()
    if null_columns:
        _metadata_error(
            "missing_classification", "null values occur in: " + ", ".join(null_columns)
        )
    non_strings = [
        column for column in METADATA_COLUMNS
        if not required[column].map(lambda value: isinstance(value, str)).all()
    ]
    if non_strings:
        _metadata_error(
            "invalid_type", "non-string values occur in: " + ", ".join(non_strings)
        )
    blank_columns = [
        column for column in METADATA_COLUMNS
        if required[column].str.strip().eq("").any()
    ]
    if blank_columns:
        _metadata_error(
            "missing_classification", "blank values occur in: " + ", ".join(blank_columns)
        )
    tickers = required["ticker"].str.strip().str.upper()
    duplicates = sorted(tickers[tickers.duplicated(keep=False)].unique())
    if duplicates:
        _metadata_error(
            "duplicate_security", "duplicate normalized tickers: " + ", ".join(duplicates)
        )
    invalid_subsectors = sorted(set(required["subsector"]) - APPROVED_SUBSECTORS)
    if invalid_subsectors:
        _metadata_error(
            "invalid_subsector", "unsupported subsectors: " + ", ".join(invalid_subsectors)
        )
    invalid_tiers = sorted(set(required["universe_tier"]) - APPROVED_UNIVERSE_TIERS)
    if invalid_tiers:
        _metadata_error(
            "invalid_universe_tier", "unsupported universe tiers: " + ", ".join(invalid_tiers)
        )


def load_semiconductor_metadata(
    path: str | Path = PROJECT_ROOT / "metadata" / "semiconductor_classification.csv",
) -> pd.DataFrame:
    """Load, validate, and minimally normalize researcher-approved metadata."""
    frame = pd.read_csv(Path(path), dtype=str, keep_default_na=False)
    validate_classification_metadata(frame)
    output = frame[list(METADATA_COLUMNS)].copy()
    for column in METADATA_COLUMNS:
        output[column] = output[column].str.strip()
    output["ticker"] = output["ticker"].str.upper()
    return output


def _security_id(ticker: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "_", ticker.upper()).strip("_")
    return f"SEC_{token}"


def build_security_master(metadata: pd.DataFrame) -> pd.DataFrame:
    """Create a security master while preserving all researcher-owned labels.

    Compatibility columns used by earlier pipeline stages follow the required
    Stage 11B fields. Persist generated IDs: a ticker change updates the mapping,
    not the internal identifier.
    """
    validate_classification_metadata(metadata)
    normalized = metadata.copy()
    for column in METADATA_COLUMNS:
        normalized[column] = normalized[column].str.strip()
    normalized["ticker"] = normalized["ticker"].str.upper()
    output = normalized[[
        "ticker", "company_name", "exchange_or_market", "subsector",
        "semiconductor_role", "universe_tier", "review_flag",
    ]].copy()
    output.insert(0, "security_id", output["ticker"].map(_security_id))
    if output["security_id"].duplicated().any():
        collisions = sorted(output.loc[
            output["security_id"].duplicated(False), "security_id"
        ].unique())
        _metadata_error(
            "duplicate_security_id", "identifier collisions: " + ", ".join(collisions)
        )
    # Structural compatibility only; these are not replacement classifications.
    output["exchange"] = output["exchange_or_market"]
    output["security_type"] = output["exchange_or_market"].str.contains(
        r"\bADR\b", case=False, regex=True
    ).map({True: "adr", False: "common_stock"})
    output["sector"] = "Semiconductor ecosystem"
    output["sub_industry"] = output["subsector"]
    output = output.sort_values("security_id", kind="stable", ignore_index=True)
    validate_security_master(output)
    return output


def classification_view(
    metadata: pd.DataFrame, security_master: pd.DataFrame
) -> pd.DataFrame:
    """Expose approved labels through the existing downstream data contract."""
    validate_classification_metadata(metadata)
    mapped = security_master[["security_id", "ticker"]].merge(
        metadata[["ticker", "company_name", "subsector", "notes"]],
        on="ticker", how="inner", validate="one_to_one",
    ).rename(columns={"notes": "classification_notes"})
    output = mapped[[
        "security_id", "ticker", "company_name", "subsector", "classification_notes"
    ]]
    validate_semiconductor_classification(output, security_master)
    return output


@dataclass(frozen=True)
class UniverseParameters:
    """Version-controlled rules for one daily eligibility run."""

    min_history_days: int
    min_price: float
    min_average_dollar_volume: float
    average_dollar_volume_window_days: int
    us_exchanges: tuple[str, ...]
    eligible_security_types: tuple[str, ...]
    classification_snapshot_date: pd.Timestamp
    allow_classification_before_as_of: bool = False
    allowed_universe_tiers: tuple[str, ...] = ("core",)
    allowed_exchange_or_markets: tuple[str, ...] = ()
    allow_adrs: bool = True
    universe_version: str = "legacy_unversioned"
    eligibility_start_date: pd.Timestamp | None = None
    eligibility_end_date: pd.Timestamp | None = None

    @property
    def classification_as_of_date(self) -> pd.Timestamp:
        """Backward-compatible alias for the classification provenance date."""
        return self.classification_snapshot_date

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "UniverseParameters":
        """Parse full/new config or the legacy Stage 4 universe section."""
        section = config.get("universe", config)
        if not isinstance(section, Mapping):
            raise ValueError("universe configuration must be a mapping")
        history = section.get("minimum_trading_history", section.get("min_history_days"))
        liquidity = section.get("liquidity", {})
        if not isinstance(liquidity, Mapping):
            raise ValueError("liquidity must be a mapping")
        min_adv = liquidity.get(
            "minimum_average_dollar_volume", section.get("min_average_dollar_volume")
        )
        window = liquidity.get(
            "trailing_window_days", section.get("average_dollar_volume_window_days")
        )
        min_price = section.get("minimum_price", section.get("min_price"))
        listing = section.get("listing_restrictions", {})
        adr = section.get("adr_handling", {})
        if not isinstance(listing, Mapping) or not isinstance(adr, Mapping):
            raise ValueError("listing_restrictions and adr_handling must be mappings")
        classification_date = section.get(
            "classification_snapshot_date", section.get("classification_as_of_date")
        )
        values = {
            "minimum_trading_history": history,
            "minimum_price": min_price,
            "minimum_average_dollar_volume": min_adv,
            "trailing_window_days": window,
            "classification_snapshot_date": classification_date,
        }
        missing = sorted(name for name, value in values.items() if value is None)
        if missing:
            raise ValueError("universe configuration is missing: " + ", ".join(missing))
        if isinstance(history, bool) or not isinstance(history, int) or history <= 0:
            raise ValueError("minimum_trading_history must be a positive integer")
        if isinstance(window, bool) or not isinstance(window, int) or window <= 0:
            raise ValueError("trailing_window_days must be a positive integer")
        tiers = _nonempty_strings(
            section.get("allowed_universe_tiers", ["core"]), "allowed_universe_tiers"
        )
        invalid_tiers = sorted(set(tiers) - APPROVED_UNIVERSE_TIERS)
        if invalid_tiers:
            raise ValueError(
                "allowed_universe_tiers contains invalid values: " + ", ".join(invalid_tiers)
            )
        raw_markets = listing.get("allowed_exchange_or_markets", [])
        if not isinstance(raw_markets, (list, tuple)):
            raise ValueError("allowed_exchange_or_markets must be a list")
        markets = tuple(
            value.strip() for value in raw_markets
            if isinstance(value, str) and value.strip()
        )
        exchanges = _nonempty_strings(
            section.get("us_exchanges", markets or ["NASDAQ", "NYSE", "NYSE American"]),
            "us_exchanges",
        )
        security_types = _nonempty_strings(
            section.get(
                "eligible_security_types",
                listing.get("eligible_security_types", ["common_stock", "adr"]),
            ),
            "eligible_security_types",
        )
        allow_adrs = adr.get("allow", "adr" in security_types)
        if not isinstance(allow_adrs, bool):
            raise ValueError("adr_handling.allow must be boolean")
        historical = section.get(
            "apply_classification_historically",
            section.get("allow_classification_before_as_of", False),
        )
        if not isinstance(historical, bool):
            raise ValueError("apply_classification_historically must be boolean")
        try:
            as_of = pd.Timestamp(values["classification_snapshot_date"])
        except (TypeError, ValueError) as error:
            raise ValueError("classification_snapshot_date must be a date") from error
        if as_of.tz is not None or as_of != as_of.normalize():
            raise ValueError(
                "classification_snapshot_date must be timezone-naive and date-only"
            )
        eligibility = section.get("eligibility", {})
        if not isinstance(eligibility, Mapping):
            raise ValueError("eligibility must be a mapping")
        eligibility_start = _optional_date(
            eligibility.get("start_date", section.get("eligibility_start_date")),
            "eligibility.start_date",
        )
        eligibility_end = _optional_date(
            eligibility.get("end_date", section.get("eligibility_end_date")),
            "eligibility.end_date",
        )
        if (
            eligibility_start is not None
            and eligibility_end is not None
            and eligibility_end < eligibility_start
        ):
            raise ValueError("eligibility.end_date must not precede eligibility.start_date")
        universe_version = section.get("universe_version", "legacy_unversioned")
        if not isinstance(universe_version, str) or not universe_version.strip():
            raise ValueError("universe_version must be a non-blank string")
        return cls(
            min_history_days=history,
            min_price=_nonnegative_number(min_price, "minimum_price"),
            min_average_dollar_volume=_nonnegative_number(
                min_adv, "minimum_average_dollar_volume"
            ),
            average_dollar_volume_window_days=window,
            us_exchanges=exchanges,
            eligible_security_types=security_types,
            classification_snapshot_date=as_of,
            allow_classification_before_as_of=historical,
            allowed_universe_tiers=tiers,
            allowed_exchange_or_markets=markets,
            allow_adrs=allow_adrs,
            universe_version=universe_version.strip(),
            eligibility_start_date=eligibility_start,
            eligibility_end_date=eligibility_end,
        )


def _nonnegative_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a non-negative number")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{name} must be a non-negative number")
    return numeric


def _optional_date(value: object, name: str) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a date") from error
    if parsed.tz is not None or parsed != parsed.normalize():
        raise ValueError(f"{name} must be timezone-naive and date-only")
    return parsed


def _nonempty_strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{name} must be a non-empty list of strings")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{name} must contain non-blank strings")
    return tuple(item.strip() for item in value)


def _market_features(
    daily_panel: pd.DataFrame, parameters: UniverseParameters
) -> pd.DataFrame:
    ordered = daily_panel.sort_values(["security_id", "date"], kind="stable").copy()
    ordered["history_days"] = ordered.groupby("security_id").cumcount().add(1)
    ordered["dollar_volume"] = ordered["close"] * ordered["volume"]
    ordered["average_dollar_volume"] = (
        ordered.groupby("security_id", sort=False)["dollar_volume"]
        .rolling(
            window=parameters.average_dollar_volume_window_days,
            min_periods=parameters.average_dollar_volume_window_days,
        ).mean().reset_index(level=0, drop=True)
    )
    return ordered[[
        "date", "security_id", "close", "history_days", "average_dollar_volume"
    ]]


def build_universe_membership(
    security_master: pd.DataFrame,
    daily_panel: pd.DataFrame,
    semiconductor_classification: pd.DataFrame,
    parameters: UniverseParameters | Mapping[str, Any],
) -> pd.DataFrame:
    """Evaluate each security/date using only observations available then."""
    if isinstance(parameters, Mapping):
        parameters = UniverseParameters.from_mapping(parameters)
    if not isinstance(parameters, UniverseParameters):
        raise TypeError("parameters must be UniverseParameters or a mapping")
    validate_security_master(security_master)
    validate_daily_panel(daily_panel, security_master)
    validate_semiconductor_classification(semiconductor_classification, security_master)
    dates = pd.Index(daily_panel["date"].drop_duplicates().sort_values(), name="date")
    identifiers = pd.Index(security_master["security_id"], name="security_id")
    grid = pd.MultiIndex.from_product([dates, identifiers]).to_frame(index=False)
    if grid.empty:
        empty = pd.DataFrame({
            "date": pd.Series(dtype="datetime64[ns]"),
            "security_id": pd.Series(dtype="object"),
            "eligible": pd.Series(dtype="bool"),
            "exclusion_reason": pd.Series(dtype="object"),
        })
        validate_universe_membership(empty, security_master)
        return empty[list(UNIVERSE_OUTPUT_COLUMNS)]
    fields = ["security_id", "exchange", "security_type"]
    fields += [
        name for name in ("exchange_or_market", "universe_tier")
        if name in security_master
    ]
    classified = semiconductor_classification[["security_id"]].assign(
        is_semiconductor=True
    )
    evaluated = (
        grid.merge(security_master[fields], on="security_id", how="left", validate="many_to_one")
        .merge(classified, on="security_id", how="left", validate="many_to_one")
        .merge(
            _market_features(daily_panel, parameters),
            on=["date", "security_id"], how="left", validate="one_to_one",
        )
    )
    evaluated["is_semiconductor"] = evaluated["is_semiconductor"].fillna(False).astype(bool)
    reasons: list[tuple[str, pd.Series]] = [
        ("missing_semiconductor_classification", ~evaluated["is_semiconductor"])
    ]
    if parameters.eligibility_start_date is not None:
        reasons.append((
            "before_eligibility_start_date",
            evaluated["date"].lt(parameters.eligibility_start_date),
        ))
    if parameters.eligibility_end_date is not None:
        reasons.append((
            "after_eligibility_end_date",
            evaluated["date"].gt(parameters.eligibility_end_date),
        ))
    if "universe_tier" in evaluated:
        reasons.append((
            "universe_tier_not_allowed",
            ~evaluated["universe_tier"].isin(parameters.allowed_universe_tiers),
        ))
    if parameters.allowed_exchange_or_markets and "exchange_or_market" in evaluated:
        reasons.append((
            "listing_restriction",
            ~evaluated["exchange_or_market"].isin(parameters.allowed_exchange_or_markets),
        ))
    else:
        reasons.append(("non_us_listing", ~evaluated["exchange"].isin(parameters.us_exchanges)))
    reasons.append((
        "ineligible_security_type",
        ~evaluated["security_type"].isin(parameters.eligible_security_types),
    ))
    if not parameters.allow_adrs:
        reasons.append(("adr_not_allowed", evaluated["security_type"].eq("adr")))
    if not parameters.allow_classification_before_as_of:
        reasons.append((
            "classification_not_available_as_of_date",
            evaluated["is_semiconductor"]
            & evaluated["date"].lt(parameters.classification_snapshot_date),
        ))
    has_data = evaluated["close"].notna()
    reasons.extend([
        ("missing_data", ~has_data),
        ("insufficient_history", has_data & evaluated["history_days"].lt(parameters.min_history_days)),
        ("below_minimum_price", has_data & evaluated["close"].lt(parameters.min_price)),
        ("insufficient_liquidity_history", has_data & evaluated["average_dollar_volume"].isna()),
        (
            "insufficient_liquidity",
            has_data & evaluated["average_dollar_volume"].notna()
            & evaluated["average_dollar_volume"].lt(parameters.min_average_dollar_volume),
        ),
    ])
    aliases = {
        "missing_data": "no_market_data",
        "insufficient_liquidity": "below_minimum_liquidity",
    }
    row_reasons = [[] for _ in range(len(evaluated))]
    for label, mask in reasons:
        for position in mask.to_numpy().nonzero()[0]:
            row_reasons[position].append(label)
            if label in aliases:
                row_reasons[position].append(aliases[label])
    output = evaluated[["date", "security_id"]].copy()
    output["eligible"] = [not values for values in row_reasons]
    output["exclusion_reason"] = [
        ";".join(values) if values else None for values in row_reasons
    ]
    output = output.sort_values(
        ["date", "security_id"], ignore_index=True
    )[list(UNIVERSE_OUTPUT_COLUMNS)]
    validate_universe_membership(output, security_master)
    return output


def build_approved_universe_membership(
    security_master: pd.DataFrame,
    daily_panel: pd.DataFrame,
    parameters: UniverseParameters | Mapping[str, Any],
) -> pd.DataFrame:
    """Build membership directly from an integrated Stage 11B master."""
    missing = sorted(set(SECURITY_MASTER_COLUMNS) - set(security_master.columns))
    if missing:
        raise ValueError("integrated security master is missing: " + ", ".join(missing))
    classification = security_master[[
        "security_id", "ticker", "company_name", "subsector"
    ]].copy()
    classification["classification_notes"] = (
        "Approved Stage 11A classification; see source metadata."
    )
    return build_universe_membership(
        security_master, daily_panel, classification, parameters
    )


def universe_membership_dataset(membership: pd.DataFrame) -> pd.DataFrame:
    """Return the Stage 11B publication shape with its documented ``reason`` name."""
    missing = sorted(set(UNIVERSE_OUTPUT_COLUMNS) - set(membership.columns))
    if missing:
        raise ValueError("membership is missing: " + ", ".join(missing))
    output = membership[list(UNIVERSE_OUTPUT_COLUMNS)].rename(
        columns={"exclusion_reason": "reason"}
    ).copy()
    output.loc[output["eligible"] & output["reason"].isna(), "reason"] = (
        "passes_core_requirements"
    )
    return output[["date", "security_id", "eligible", "reason"]]


def historical_coverage(
    security_master: pd.DataFrame,
    daily_panel: pd.DataFrame,
    *,
    factor_model_min_history: int,
    short_public_history_days: int,
    ticker_change_gap_days: int,
) -> pd.DataFrame:
    """Report coverage and conservative flags without changing membership."""
    validate_security_master(security_master)
    validate_daily_panel(daily_panel, security_master)
    rows: list[dict[str, object]] = []
    for security_id in security_master["security_id"]:
        observed = daily_panel.loc[
            daily_panel["security_id"].eq(security_id), "date"
        ].sort_values()
        if observed.empty:
            rows.append({
                "security_id": security_id,
                "first_available_trading_date": pd.NaT,
                "last_available_trading_date": pd.NaT,
                "number_of_observations": 0,
                "missing_days": 0,
                "insufficient_factor_model_history": True,
                "short_public_history": True,
                "possible_ticker_change": False,
            })
            continue
        count = len(observed)
        business_days = pd.bdate_range(observed.iloc[0], observed.iloc[-1])
        gaps = observed.diff().dt.days.dropna()
        rows.append({
            "security_id": security_id,
            "first_available_trading_date": observed.iloc[0],
            "last_available_trading_date": observed.iloc[-1],
            "number_of_observations": count,
            "missing_days": max(0, len(business_days) - count),
            "insufficient_factor_model_history": count < factor_model_min_history,
            "short_public_history": count < short_public_history_days,
            "possible_ticker_change": bool(gaps.gt(ticker_change_gap_days).any()),
        })
    return pd.DataFrame(rows)


def universe_diagnostics(
    security_master: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    as_of_date: str | pd.Timestamp | None = None,
) -> dict[str, pd.DataFrame]:
    """Return overall, subsector, tier, and exclusion diagnostics for one date."""
    validate_security_master(security_master)
    validate_universe_membership(membership, security_master)
    if membership.empty:
        current = membership
        date_value = pd.NaT
    else:
        date_value = (
            pd.Timestamp(as_of_date) if as_of_date is not None else membership["date"].max()
        )
        current = membership.loc[membership["date"].eq(date_value)]
    eligible_ids = set(current.loc[current["eligible"], "security_id"])
    total = len(security_master)
    eligible = len(eligible_ids)
    overall = pd.DataFrame([{
        "date": date_value,
        "total_manually_classified": total,
        "total_eligible": eligible,
        "eligibility_percentage": 100.0 * eligible / total if total else 0.0,
    }])
    labelled = security_master[[
        "security_id", "subsector", "universe_tier"
    ]].assign(eligible=lambda frame: frame["security_id"].isin(eligible_ids))
    by_subsector = labelled.groupby("subsector", sort=True).agg(
        classified=("security_id", "size"), eligible=("eligible", "sum")
    ).reset_index()
    by_tier = labelled.groupby("universe_tier", sort=True).agg(
        classified=("security_id", "size"), eligible=("eligible", "sum")
    ).reset_index()
    excluded = current.loc[
        ~current["eligible"], "exclusion_reason"
    ].dropna().str.split(";").explode()
    exclusions = excluded.value_counts().rename_axis("reason").reset_index(name="count")
    return {
        "overall": overall,
        "by_subsector": by_subsector,
        "by_universe_tier": by_tier,
        "exclusion_reasons": exclusions,
    }


def metadata_sha256(path: str | Path) -> str:
    """Hash metadata bytes exactly as versioned."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def create_universe_manifest(
    metadata_path: str | Path,
    security_master: pd.DataFrame,
    membership: pd.DataFrame,
    universe_config: Mapping[str, Any],
    *,
    creation_timestamp: str | None = None,
) -> dict[str, object]:
    """Create a JSON-serializable provenance record for one universe run."""
    metadata_file = Path(metadata_path)
    displayed_metadata_file = (
        metadata_file.relative_to(PROJECT_ROOT)
        if metadata_file.is_absolute() and metadata_file.is_relative_to(PROJECT_ROOT)
        else metadata_file
    )
    section = universe_config.get("universe", universe_config)
    if not isinstance(section, Mapping):
        raise ValueError("universe configuration must be a mapping")
    classification_date = section.get(
        "classification_snapshot_date", section.get("classification_as_of_date")
    )
    eligibility = section.get("eligibility", {})
    if not isinstance(eligibility, Mapping):
        eligibility = {}
    latest_eligible = 0 if membership.empty else int(
        membership.loc[
            membership["date"].eq(membership["date"].max()), "eligible"
        ].sum()
    )
    counts = security_master["subsector"].value_counts().sort_index()
    return {
        "metadata_file": str(displayed_metadata_file),
        "metadata_sha256": metadata_sha256(metadata_path),
        "universe_version": section.get("universe_version", "legacy_unversioned"),
        "classification_snapshot_date": classification_date,
        "eligibility_start_date": eligibility.get(
            "start_date", section.get("eligibility_start_date")
        ),
        "eligibility_end_date": eligibility.get(
            "end_date", section.get("eligibility_end_date")
        ),
        "universe_configuration": json.loads(
            json.dumps(dict(universe_config), default=str)
        ),
        "creation_timestamp": creation_timestamp
        or datetime.now(timezone.utc).isoformat(),
        "number_of_securities": int(len(security_master)),
        "number_eligible": latest_eligible,
        "eligibility_status": (
            "not_computed_no_market_data" if membership.empty else "computed"
        ),
        "eligibility_as_of_date": None
        if membership.empty else membership["date"].max().date().isoformat(),
        "subsector_counts": {
            str(key): int(value) for key, value in counts.items()
        },
    }


def write_universe_manifest(
    manifest: Mapping[str, object], path: str | Path
) -> None:
    """Write a stable, human-readable manifest."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(dict(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
