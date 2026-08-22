# Stage 11B: approved universe integration

## Economic universe and daily eligibility

The economic universe answers which companies belong to the semiconductor
ecosystem. Its sole authority is
`metadata/semiconductor_classification.csv`, reviewed by the researcher in
Stage 11A. Software validates and transports its fields but does not infer,
revise, add, or remove classifications.

The eligible universe answers a different question: which approved security
lines satisfy the pre-specified operational rules on a particular date. A
security can remain an economic peer while temporarily failing price, history,
liquidity, listing, or data-availability rules. Consequently the security master
and peer metadata are never filtered to the daily eligible set. Downstream peer
relationships join through `security_id`, not raw ticker strings.

## Integration workflow

`load_semiconductor_metadata` validates the ten-column Stage 11A schema,
nonblank classifications, unique normalized tickers, approved subsectors, and
approved universe tiers. `build_security_master` assigns an internal identifier
and carries the researcher-owned company, listing, subsector, role, tier, and
review fields without modification. Compatibility columns support earlier
pipeline stages but are not alternative economic classifications.

Security IDs are bootstrapped from the approved security-line ticker and then
persisted. For example, the current NVIDIA line maps to `SEC_NVDA`. If its ticker
changes later, the ticker-to-ID mapping must be updated while `SEC_NVDA` stays
fixed. Regenerating an ID from the new ticker would break historical joins.

## Point-in-time eligibility

Rules are loaded from `configs/final_baseline.yaml`. The configuration records:

- allowed universe tiers;
- minimum unadjusted price;
- minimum number of observed trading days;
- trailing average dollar-volume threshold and window;
- allowed researcher-selected listing lines and instrument types; and
- explicit ADR treatment.

History and trailing average dollar volume use observations through the
membership date, inclusive. They do not use a security's eventual full-sample
history, later liquidity, later listing survival, or future prices. Every
security is evaluated on every date present in the daily panel. An absent row is
recorded as missing data rather than silently dropping the company. Failed rules
are retained in deterministic order in `exclusion_reason`; eligibility requires
that no rule fail.

The metadata is a current review snapshot dated 2026-08-22. The baseline is
fail-closed before that date. Setting `allow_classification_before_as_of: true`
is an explicit retrospective research assumption, not evidence that the current
classification was historically known.

## Why classification remains manual

Semiconductor ecosystem boundaries are economic judgments. Foundries, EDA and
IP vendors, equipment suppliers, packaging and testing companies, materials
firms, and diversified manufacturers are not reliably captured by a single
vendor industry code. A reviewed file makes judgment visible and versionable.
Automating that judgment from returns, liquidity, or business descriptions
would entangle sample selection with measured outcomes and could overwrite
researcher decisions.

## Bias controls and failure modes

Look-ahead bias enters if a date is screened using later observations—for
example, requiring that a company eventually accumulate 252 observations or
using its full-sample average liquidity. The implementation uses cumulative and
trailing values ending on each date, and tests verify that later observations do
not alter earlier membership.

Survivorship bias enters earlier: today's approved company list omits firms that
failed, were acquired, delisted, or left the ecosystem. Backfilling the current
list cannot create a survivorship-free historical universe. The classification
as-of guard prevents silent backfilling but does not reconstruct missing firms.

Ticker symbols are vendor- and time-dependent. They can be reused, changed after
corporate actions, or identify different listing lines across exchanges. Internal
security IDs isolate analysis tables from ticker strings, but a maintained
historical identifier map is still required.

Missing prices can reflect exchange holidays, suspensions, vendor gaps, ticker
changes, or delisting. The coverage report therefore flags long gaps as
`possible_ticker_change` rather than asserting one. Missing business weekdays
are diagnostics, not classification decisions.

## Coverage diagnostics

`historical_coverage` reports first and last available dates, observation count,
business-weekday gaps, insufficient factor-model history, short public history,
and possible ticker changes. `universe_diagnostics` reports overall eligibility,
classified and eligible counts by subsector and tier, and exploded exclusion
reasons for a selected date. The manifest records the exact metadata hash,
configuration, timestamp, security count, latest eligible count, and subsector
counts.

## Current limitations

- No production daily market-data panel is versioned in the repository, so the
  checked-in manifest cannot claim empirical daily eligibility.
- The current metadata snapshot is not a dated history of classifications,
  acquisitions, delistings, domicile changes, or business-model changes.
- The security master lacks permanent vendor identifiers such as PERMNO/FIGI and
  an effective-dated ticker/listing map.
- Exact exchange strings are a temporary listing-line contract. A normalized,
  effective-dated exchange and security-type reference table would be stronger.
- ADR volume is not yet normalized for depositary ratios; the baseline exposes
  this explicitly and leaves ratio normalization disabled.
- Business-day missing counts do not use exchange-specific holiday calendars,
  so cross-market coverage gaps may be overstated.
- A long observation gap is only a ticker-change warning, not proof of a ticker
  change. Corporate-action and vendor symbology data are needed to resolve it.
- Price and liquidity thresholds favor larger, more tradable firms and require
  planned sensitivity analysis.
