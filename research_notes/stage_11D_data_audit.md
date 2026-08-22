# Stage 11D: data integration audit

## Scope and validation principle

Stage 11D verifies that the approved Stage 11A/11B universe metadata and the
Stage 11C Yahoo Finance snapshot can be joined safely before any empirical
results are estimated. It does not run an event study, change a universe label,
repair a ticker, fill a market holiday, winsorize a return, or revise the
research classifications. The eligibility policy below reflects the explicit
post-audit research decision to separate classification provenance from
historical eligibility and to use distinct baseline and extension history rules.

The deterministic implementation is in `src/price_diffusion/stage11d.py`. The
notebook only reads and presents generated artifacts. The assembled
`data/processed/daily_panel.parquet` is the first combined analytical dataset
and contains exactly:

`date, security_id, ticker, subsector, universe_tier, universe_version,
adj_close, return, volume, eligible, extension_eligible, extreme_return_flag`.

## Versioned historical eligibility policy

The current policy is identified as
`semiconductor_universe_2026_08_22_v1`. The classification snapshot date
(`2026-08-22`) records when the taxonomy was reviewed. It is not an eligibility
start date. The current classification is applied retrospectively by an
explicit configuration flag, and the resulting survivorship/look-back
limitation remains documented.

Eligibility begins on `2015-01-01`; the event-study estimation window remains a
separate `date_range` setting. Historical membership is written to
`data/processed/universe_membership.csv` for every security and observed global
trading date from the eligibility start through the latest market-data date.

Baseline eligibility uses only information available through each row date and
requires 252 observed trading days. Extension eligibility uses 60 observed
trading days and admits both `core` and `extension` classification tiers. Thus a
short-history security is never deleted: it remains in the panel, is excluded
from baseline while history is insufficient, and may enter extension analysis
once it satisfies the extension rule. This design avoids using eventual
full-sample observation counts to decide earlier eligibility.

The generated panel contains 92,346 baseline-eligible rows across 36
securities and 131,106 extension-eligible rows across 53 securities. On the
latest data date, 36 securities pass baseline and 53 pass extension rules.
`Q` and `CBRS` never enter baseline because they have fewer than 252 total
observations, but they contribute 147 and 10 extension-eligible observations
after reaching the 60-day extension threshold. `688825.SS` remains retained
with all 20 rows but does not yet meet even the extension history threshold.

## Successful integration

The mapping audit contains all 54 approved securities. Every security has
downloaded observations, every observed `security_id` occurs in the security
master, tickers agree across metadata and prices, required identifiers are
present, and no `security_id`, ticker, or Yahoo-symbol mapping is duplicated.
No ticker was changed during this stage.

The combined panel has 187,986 unique security-date rows for 54 securities from
2010-01-04 through 2026-08-21. It includes 36 core and 18 extension securities,
with 136,764 and 51,222 observations respectively. Returns are simple
close-to-close returns recalculated within each security from adjusted close.

## Historical coverage

The median security has 4,184 observations and 16.627 calendar years between
its first and last observations. Forty-two securities begin in 2010. Three
securities have fewer than the version-controlled 252-observation factor-model
minimum and are also flagged as short-history companies:

- `SEC_688825_SS` (`688825.SS`): 20 observations, beginning 2026-07-27;
- `SEC_CBRS` (`CBRS`): 69 observations, beginning 2026-05-14; and
- `SEC_Q` (`Q`): 206 observations, beginning 2025-10-27.

Four securities have less than two years of observed history as of the panel's
last date: the three above and `SEC_285A_T` (`285A.T`), which has 407
observations beginning 2024-12-18. The `recent_ipo` field is deliberately a
recent-listing-history proxy based on the first available Yahoo observation; it
is not independent proof of an IPO date. Corporate records should confirm these
dates before the flag is interpreted economically.

## Trading calendars and missing dates

The panel spans 15 exchange labels across North America, Europe, Japan, Korea,
mainland China, Hong Kong, and Taiwan. Exchange-session unions differ because
of local holidays, closures, and listing histories. For example, over each
exchange's available span the audit finds 32 weekdays without an observed
Euronext Milan session, 156 for Nasdaq/NYSE, 242 for Hong Kong, 249 for Korea,
251 for Tokyo, 273 for Taiwan, and 296 for Shenzhen. These counts are not
declared vendor errors: they include valid local non-trading days.

Within each security's own observed range, no security is absent on a date when
another security with the same exchange label trades. This is reassuring but
not definitive for exchanges represented by only one security. The audit uses
empirical local-exchange session unions rather than an external historical
calendar library, so a whole-exchange vendor omission cannot be distinguished
from a valid holiday without an authoritative calendar.

Non-overlapping histories are retained. Fourteen securities begin after the
global panel start, primarily because of later listing or later Yahoo coverage.
No international trading day is inserted or filled.

Peer portfolios in later stages must therefore be formed from securities with
observed returns on the relevant local date. Missing peers must not be assigned
zero returns, and the available peer count can vary by event date. Cross-market
lead/lag definitions must also remember that a shared calendar label does not
mean exchanges traded at the same clock time.

## Return quality

The return-quality audit finds:

- no duplicate security-date rows;
- no adjusted close at or below zero;
- no non-finite adjusted closes;
- no negative volumes;
- no return at or below -100%; and
- exactly one expected missing return for the first observation of each of the
  54 securities, with no later missing returns.

Two absolute daily adjusted-close returns exceed the unchanged 50% diagnostic
threshold:

- `AMD`, 2016-04-22: +52.2901%; and
- `SOI.PA`, 2014-12-22: -54.5024%.

These observations remain in the panel. The AMD move coincides with unusually
high reported volume; the Soitec move also has a large volume increase. That is
not enough to decide whether either value reflects news, a corporate action, or
a Yahoo adjustment issue. Both dates require source and corporate-action
triangulation before an event involving them is interpreted.
`extreme_return_flag` identifies both rows directly in the daily panel; it does
not alter `return`, `eligible`, or `extension_eligible`.

## Known limitations and future attention

- Yahoo Finance remains a revisable, non-point-in-time vendor source and the
  manually approved present-day universe remains vulnerable to survivorship
  bias.
- Current symbols are not an effective-dated identifier history; acquired,
  renamed, migrated, and delisted listings are not reconstructed.
- The empirical exchange-session audit is not a substitute for authoritative
  historical local calendars.
- Adjusted-close corporate-action histories, especially the two extreme-return
  dates, require an independent source for material empirical claims.
- Recent-listing proxies for `688825.SS`, `CBRS`, `Q`, and `285A.T` require
  confirmation from offering or exchange records.
- Prices remain in local listing currencies. No FX conversion or ADR-ratio
  normalization is introduced here.

## Stage 12 readiness decision

The versioned panel and historical membership are structurally ready for Stage
12. Baseline analyses must use `eligible`; explicitly labelled extension
analyses may use `extension_eligible`. The retrospective classification policy
and present-day-universe survivorship limitation must accompany interpretation.
The two flagged extreme returns remain review items and must not be silently
removed or winsorized.
