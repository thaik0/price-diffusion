# Stage 3: Market Data Ingestion and Normalization

The purpose of this layer is not to maximize the quantity of market data. It is
to establish a small, auditable boundary between source observations and the
research dataset. A statistically sophisticated result cannot recover from an
ambiguous identifier, duplicated observation, unadjusted split, or silently
filled price.

## Why normalization is necessary

Market-data providers use different column names, identifier conventions, date
formats, calendars, adjustment policies, and units. Research code should not
need to know whether a row originated in CSV, Yahoo Finance, Polygon, CRSP, or
Bloomberg. The source adapter therefore produces a tabular observation, and the
normalization layer converts it to one stable contract.

The Stage 3 path is:

1. Load source observations without research transformations.
2. Rename provider fields to canonical raw fields where necessary.
3. Parse timezone-naive market dates and normalize them to midnight.
4. Resolve the provider identifier through `security_master`.
5. Reject missing values, ambiguous identifiers, duplicates, and impossible
   price or volume values.
6. Sort independently by security and date.
7. Calculate adjusted-close simple returns.
8. Validate the completed `daily_panel` contract.

This sequence is fail-closed. It does not guess an unknown ticker, average
duplicates, replace a missing price, or turn an absent date into a zero return.

## Why adjusted prices are used

The quoted close is the price observed at the end of a session, but its history
can have mechanical discontinuities caused by stock splits, reverse splits,
dividends, and other corporate actions. Adjusted close attempts to place prices
on a comparable basis through time. Computing returns from the unadjusted close
could misclassify a split as an enormous economic loss even when shareholder
value did not change by that amount.

The raw close is retained because it is useful for audit and future questions
that require the contemporaneous quoted price. The return field is calculated
from adjusted close. Adjustment policies differ among vendors, so a future
adapter must document the vendor's policy and any point-in-time limitations.

## Why returns belong in this layer

Simple return is a deterministic transformation of normalized prices:

`return_t = adjusted_close_t / adjusted_close_(t-1) - 1`

Calculating it once at the data boundary makes every downstream study consume
the same definition. It also allows validation to compare the stored return
with the stored adjusted prices. Calculation is grouped by security, and the
first available observation remains missing because no prior observation exists.

“Prior” means the preceding available row for the same security, not the prior
calendar date. A weekend, exchange holiday, suspension, or source gap creates
no artificial observation. The next observed return spans that interval. This
choice preserves what is known while leaving calendar alignment to a later,
explicit research design.

## Common quantitative market-data problems

- Duplicate security/date rows from overlapping downloads or revised files.
- Malformed, timezone-shifted, or intraday timestamps presented as daily dates.
- Ticker reuse, ticker changes, multiple share classes, and vendor-specific IDs.
- Survivorship bias from resolving historical data against only today's firms.
- Split or dividend discontinuities in unadjusted prices.
- Vendor adjustments that are revised retrospectively.
- Missing observations confused with a genuine zero return or zero volume.
- Prices or volumes parsed as strings, and sentinel values such as `-1` or
  infinity treated as observations.
- Mixed currencies, exchanges, listing venues, or volume units.
- Unsorted input and calculations that accidentally cross security boundaries.

Stage 3 catches the subset expressible in the current contract: unresolved or
ambiguous securities, duplicate dates, malformed dates, missing required
values, non-finite or non-positive prices, negative volume, and returns that do
not reproduce adjusted-close simple returns.

## Preparation for future event studies

An event study needs a dependable security-date panel before it can define an
event window, estimate an expected return, or compare a focal firm with peers.
This layer supplies that base while deliberately making none of those research
choices. Later stages can align events and trading calendars knowing that:

- every row has a canonical `security_id`;
- each security/date observation is unique;
- dates and ordering are deterministic;
- price and volume constraints have been checked; and
- returns have one documented, reproducible definition.

The remaining limitations are intentional. There is no external provider,
exchange-calendar validation, currency normalization, delisting-return model,
corporate-action audit, or point-in-time identifier history yet. CSV inputs and
`security_master` are assumed to carry the provenance needed to add those
capabilities later without changing downstream research logic.
