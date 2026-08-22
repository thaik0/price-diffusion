# Stage 11C: Yahoo Finance data acquisition

## Scope and research principle

Stage 11C creates the first real daily market-data layer for the semiconductor
information-diffusion project.  Its purpose is to make source limitations and
coverage visible before event definitions, peer returns, or statistical results
are estimated.  The output is appropriate for exploratory research and pipeline
development; it is not treated as an institutional-quality point-in-time feed.

## Why Yahoo Finance

Yahoo Finance, accessed through `yfinance`, provides broad international daily
coverage through a scriptable interface at no direct data cost.  That makes it
useful for validating the project's data contracts and running an initial
cross-market study from 2010 onward.  The acquisition call requests unadjusted
OHLC, an explicit adjusted-close series, and volume.  Each vendor response is
saved before standardization so a later result can be traced to the downloaded
source snapshot.

Yahoo Finance was not chosen because it is complete or point-in-time correct.
It is a pragmatic first source.  Results that survive the research-design stage
should ultimately be replicated with a licensed source and stronger identifier,
corporate-action, and delisting histories.

## Security identity and Yahoo symbols

`metadata/security_master.csv` separates the stable research `security_id` from
both the project ticker and the current Yahoo symbol.  This matters because a
vendor symbol is an access key, not an economic identity: tickers can change,
listings can migrate, ADRs can differ from primary shares, and two vendors can
encode the same exchange suffix differently.  For example, the existing
research ID `SEC_ASM` maps to Yahoo's Amsterdam listing symbol `ASM.AS`.

The Stage 11B security IDs are retained.  A future ticker or vendor-symbol change
must update the mapping rather than create a new company identity.  A more mature
master should add effective dates, ISIN/CUSIP/SEDOL identifiers, listing IDs,
delisting status, and predecessor/successor relationships.

## Raw and standardized layers

Every run writes one timestamped directory beneath
`data/raw/yahoo_prices/`.  Raw files are opened in exclusive-create mode, and a
run identifier cannot be reused.  Consequently a rerun creates a new snapshot
instead of replacing evidence used by an earlier analysis.

The standardized price panel is written to
`data/interim/daily_prices.parquet` in long format with:

`date, security_id, ticker, open, high, low, close, adj_close, volume`.

The return panel is written to `data/interim/daily_returns.parquet` with:

`date, security_id, return, adj_close`.

Interim files represent the latest completed transformation and may be
regenerated.  Raw snapshots are the immutable provenance layer.

## Adjusted close and return methodology

Simple close-to-close returns are calculated independently within each security:

`return_t = (adj_close_t / adj_close_(t-1)) - 1`.

The first observation for each security has no prior price and therefore has a
missing return.  Missing source rows are not filled and calendar dates are not
manufactured.  A return following a gap compares consecutive available vendor
observations, so the audit must be consulted before interpreting it as a normal
one-session return.

Adjusted close is used because it is intended to account for splits and cash
distributions more consistently than raw close.  It is still a vendor-derived
series whose adjustment history can be revised or be incomplete.  The pipeline
requests `auto_adjust=False` so raw OHLC is not silently rewritten and the
explicit Yahoo `Adj Close` field remains visible.

## Audit interpretation

`outputs/diagnostics/data_audit.csv` reports every approved security, including
those with no downloaded observations.  Checks cover first and last dates,
observation counts, duplicate dates, non-positive prices, missing adjusted
prices, zero-volume days, large calendar gaps, missing returns after the first
observation, returns at or below -100%, and absolute returns greater than 50%.

The `missing_percentage` metric uses a Monday-Friday calendar between each
security's first and last observation.  It is a screening statistic, not a
definitive count of absent exchange sessions.  Valid local exchange holidays
will be counted in `missing_weekdays_or_holidays`.  Later work should replace
this estimate with exchange-specific historical calendars.

Extreme-return flags are prompts for investigation, not automatic errors.
Legitimate listing events, major news, stale-price corrections, and imperfect
corporate-action adjustments can all produce large observations.  The pipeline
does not winsorize, delete, or repair them silently.

## Known Yahoo Finance limitations

- **Survivorship bias:** the manually approved current universe and current
  Yahoo symbols do not reconstruct the full historical opportunity set.  Failed,
  acquired, and delisted firms can be absent.
- **Ticker and listing changes:** current symbols may not join cleanly across
  renames, exchange transfers, ADR changes, mergers, or predecessor companies.
- **Incomplete historical coverage:** some listings begin after 2010; newly
  listed or not-yet-trading approved companies can have little or no history.
  Vendor outages and market-specific history gaps are also possible.
- **Corporate actions:** adjusted close is convenient but its split, dividend,
  rights-offering, spin-off, and special-distribution treatment must be checked
  against primary or licensed records for material events.
- **Vendor revisions and reproducibility:** Yahoo can revise historical values or
  availability.  Immutable dated raw snapshots preserve what this project
  actually received, but they do not make the vendor record point-in-time.
- **Terms and operational stability:** `yfinance` is an unofficial access layer;
  endpoint behavior, throttling, and schemas can change.

## International listing complications

The universe spans the United States, Korea, mainland China, Hong Kong, Taiwan,
Japan, and several European exchanges.  These markets have different trading
weeks, holidays, occasional closures, price-limit rules, settlement conventions,
and liquidity patterns.  Yahoo daily timestamps can carry exchange timezones;
the standardizer removes the timezone while preserving the local daily date
label, avoiding an accidental UTC shift of Asian sessions.

Prices and returns remain in the listing currency recorded in the security
master (USD, EUR, JPY, KRW, CNY, HKD, or TWD).  No currency conversion is
attempted in Stage 11C.  A local-currency stock return is appropriate for an
initial within-listing event signal, but cross-country level comparisons and a
common investor's return require explicit FX data and a documented hedging or
translation convention.  ADRs are treated as their traded US listings, not as
interchangeable copies of primary shares.

## Future improvements

Priority upgrades are: exchange-specific session calendars; effective-dated
security and listing identifiers; delisted-company and delisting-return coverage;
independent corporate-action validation; explicit FX series; checksums and a
machine-readable download manifest; and source triangulation.  Institutional
replication candidates include CRSP for US securities, Bloomberg, Refinitiv,
FactSet, ICE, Compustat Security Daily, and authoritative exchange feeds.  Any
replacement must retain the raw/interim separation and make vendor-specific
mapping decisions reviewable.
