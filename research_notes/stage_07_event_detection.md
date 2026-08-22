# Stage 7: Event detection

## The event definition is the core research decision

The event-selection rule determines which observations enter every later analysis. It must therefore be fixed before examining post-event behavior. Changing the cutoff, history requirement, peer set, or cooldown after seeing later returns would condition the sample on the desired result. Stage 7 produces candidates for later research; it does not label information releases, identify leaders, or imply a profitable trade.

For security (i) on date (t), the measured divergence is

\[
D_{i,t}=AR_{i,t}-AR^{peer}_{i,t}.
\]

An observation is an event only when

\[
|D_{i,t}| > \max(c, k\sigma_{i,t}),
\]

where (c), (k), the volatility window, and eligibility requirements come from `configs/baseline.yaml`. The rolling sample standard deviation is shifted by one observation before it is evaluated, so the event-date return and all future returns are excluded.

## Why raw price moves are insufficient

A large stock return can reflect a market-wide move, a semiconductor-wide repricing, or news specific to an economic peer group. Raw returns cannot distinguish these components. Comparing abnormal returns with a dated, leave-one-out peer portfolio focuses the selection rule on company-versus-peer divergence. It does not prove that the residual is firm-specific information: factor omission, peer misspecification, liquidity, and data errors can still create large relative shocks.

The absolute floor prevents a low-volatility estimate from turning economically trivial moves into events. The volatility-scaled cutoff adapts to persistent differences in firm volatility and changing regimes. Requiring both protections makes the rule conservative but does not make its parameter choices uniquely correct.

## Eligibility and corporate actions

Event candidates require the configured number of observed peers and strictly trailing return history. Corporate-action labels provide an explicit validation boundary: `split`, `merger`, `abnormal_price_adjustment`, and `unknown` are excluded in the baseline. `unknown` is fail-closed because an unclassified extreme adjustment should not silently enter the research sample. These hooks depend on upstream point-in-time corporate-action data; the detector does not infer actions from prices.

`earnings_flag` and `news_identified_flag` are metadata placeholders only. They default to false and are not used to select events. No news collection or post-event analysis is part of this stage.

## Cooldown and simultaneous events

Cooldown suppresses later candidate dates within the configured number of calendar days. Firm cooldown treats repeated shocks for the same security as one possible information episode. Peer-group cooldown treats related firms as sharing an episode. The baseline applies both. All qualifying firms on the same date are evaluated as a batch, so group cooldown does not force one of several simultaneous movers to become the leader.

When at least two accepted securities from the same `peer_group` move extremely on the same date, they receive one deterministic `simultaneous_event_group` identifier. Direction may differ across firms. The flag records co-movement; it makes no temporal or causal leadership claim.

## Selection-bias risks and limitations

- Universe and classification snapshots can introduce survivorship and look-ahead bias if they are not historically valid.
- Economic peers are researcher-defined and may share omitted exposures or be affected by the focal firm itself.
- Hard cutoffs create discontinuities and multiple-testing concerns across firms and dates.
- Rolling volatility estimates lag regime changes and are noisy with short samples.
- Missing peer returns can alter portfolio composition; the peer-count minimum only partly addresses this.
- Calendar-day cooldown is a design choice and can merge distinct episodes or split a long episode.
- Corporate-action coverage, adjusted-price quality, stale prices, and liquidity can create false events.
- Events selected here are unusual relative returns, not verified information events, transmission evidence, trading signals, or profitability claims.

Later stages should report sensitivity to pre-declared alternative thresholds and peer definitions without choosing specifications based on post-event outcomes.
