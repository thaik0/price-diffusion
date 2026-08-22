# Stage 4: Semiconductor universe construction

## Purpose

Universe construction determines which securities could enter later research
before any diffusion pattern, event, peer relation, or return result is examined.
Defining the candidate set first prevents the hypothesis from influencing which
firms are retained. The Stage 4 output is eligibility metadata, not a portfolio.

## Workflow

`build_universe_membership` validates the security master, daily panel, manual
classification table, and version-controlled parameters. It evaluates every
security-master identifier on every date observed anywhere in the daily panel.
This full grid retains a row for a security with no observation on a date and
records `no_market_data` rather than silently dropping it.

The static rules require a reviewed semiconductor classification, a configured
US exchange, and a configured eligible instrument type. The dynamic rules use
only observations dated on or before the membership date. History is the count
of available trading observations including the current observation. Price is
the current unadjusted close. Liquidity is the trailing mean of `close * volume`
over the configured number of available trading observations, including the
current date. A full liquidity window is required.

All failed rules are written to `exclusion_reason` in deterministic order. An
eligible row has a null reason. Thresholds and allowed values come from
`configs/baseline.yaml`; none are empirical conclusions.

## Point-in-time membership and survivorship bias

A current list of successful semiconductor companies omits firms that failed,
were acquired, delisted, changed business, or changed listings. Backfilling that
list through history creates survivorship bias and can overstate tradability and
signal quality. Historical security-master coverage, delisted-security prices,
corporate-action histories, and dated classification decisions are needed for a
genuinely survivorship-free universe.

The included classification CSV is explicitly a current, manually reviewed seed
snapshot. `classification_as_of_date` records when that snapshot is considered
available. By default, construction excludes classified firms before that date
with `classification_not_available_as_of_date`. Retrospective use requires the
researcher to set `allow_classification_before_as_of: true`, leaving an explicit,
version-controlled record of the assumption. That override is suitable for
exploratory or sensitivity analysis, not a claim of point-in-time classification.

Rolling history and liquidity are calculated in ascending date order and never
use later rows. Adding future market observations therefore cannot change an
already constructed historical membership decision.

## Universe versus peers

The universe answers whether a security is eligible to participate at all. Peer
construction would answer which eligible firms are economically comparable to
another firm and with what weight. Stage 4 does not construct peer portfolios,
similarities, events, event studies, or strategies. Keeping these stages separate
prevents peer or outcome information from feeding back into universe selection.

## Why manual classification is acceptable

Semiconductor boundaries are economically nuanced: EDA, IP licensing, foundry,
packaging, and equipment firms may be misrepresented by broad vendor industry
codes. A small, documented manual table is transparent, reviewable, and stable.
It is preferable to an undocumented automatic inference. Reviewers should record
the rationale and ambiguous cases in `classification_notes`, preserve historical
versions, and avoid changing labels in response to research results.

## Current limitations

- The repository does not contain a survivorship-free historical security master,
  delisted returns, or acquisition and ticker histories.
- The seed classifications are current snapshots rather than dated histories of
  business-model changes. The as-of guard prevents silent retrospective use but
  does not manufacture missing historical knowledge.
- Exchange and `security_type` values depend on upstream security-master quality.
  A US exchange identifies a US listing, not a US-domiciled issuer; ADRs are
  intentionally allowed when configured.
- Observation counts are available trading rows, not exchange-calendar sessions.
  Suspensions and missing vendor rows both delay history and liquidity eligibility.
- Dollar volume uses unadjusted close times reported volume. Cross-provider volume,
  corporate-action, and ADR-ratio conventions can differ.
- Price and liquidity cutoffs favor larger, more tradable firms and may attenuate
  diffusion effects in small firms. They require pre-specified sensitivity tests.
- Manual classification introduces reviewer judgment and coverage risk. It should
  be independently reviewed and versioned before empirical use.
