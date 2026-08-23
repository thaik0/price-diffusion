# Stage 12: frozen baseline empirical results

## Methodology

This stage asks what happens after a pre-specified extreme semiconductor
peer-relative price shock. It does not ask whether a trading strategy is
profitable and does not identify a causal information channel.

The estimation sample is fixed at 2015-01-01 through 2025-12-31. It uses the
manually reviewed Stage 11A core universe and the Stage 11D point-in-time
`eligible` flag. Economic peers are all other eligible securities in the same
reviewed Stage 11A subsector, equally weighted and leave-one-out. Peer identities
and weights are frozen on the event date. This production mapping is necessary
because the older `metadata/peer_classification.csv` is explicitly a Stage 5
smoke-test seed and includes neither the final universe nor the final taxonomy.

The event signal is the initiating security's semiconductor-adjusted return
minus its peer portfolio's semiconductor-adjusted return. The semiconductor
factor is the same-day equal-weight return of baseline-eligible securities. With
a common unit-loaded factor, it cancels algebraically from the event-day
stock-minus-peer divergence. The factor remains relevant to the separately
reported initiator and peer CAR components and is therefore recorded in the run
manifest.

Events satisfy the frozen rule
`abs(relative abnormal return) > max(5%, 3 × trailing 60-observation volatility)`.
The volatility calculation is shifted by one observation and requires 60 prior
valid observations, at least three peers, and the configured firm and peer-group
cooldowns. Stage 11D rows flagged as unresolved extreme adjusted-price returns
are passed to the detector as `unknown` corporate-action observations and are
excluded by the frozen rule rather than silently repaired or winsorized.

Post-event outcomes cover t+1 through t+h for h = 1, 3, 5, and 10 trading days.
For event direction sign s (+1 for a positive shock and -1 for a negative
shock):

- peer catch-up = s × peer CAR;
- initiator reversal = -s × initiator CAR; and
- convergence = peer catch-up + initiator reversal.

Positive values mean gap closure for either shock direction. Reported 95%
analytical intervals use firm-clustered standard errors and condition on the
detected-event sample.

## Sample description

The reviewed metadata contains 54 securities. Thirty-six core securities are
baseline eligible at some point in the frozen sample; 18 extension-tier
securities are excluded from the baseline by design and remain in metadata.
Only 29 securities are eligible on the final global calendar date because
several international exchanges are closed on 2025-12-31; this final-date count
does not redefine the 36-security baseline universe.

Three short-history securities are reported separately and retained in
metadata:

- CXMT (`688825.SS`): 20 observations beginning 2026-07-27;
- Cerebras (`CBRS`): 69 observations beginning 2026-05-14; and
- Qnity (`Q`): 206 observations beginning 2025-10-27.

All three have insufficient history for baseline estimation. They are also
extension-tier securities, so neither fact is used to alter the core sample.

The detector identifies 242 events: 140 positive and 102 negative. Event counts
by year are 14, 16, 7, 16, 14, 23, 9, 13, 29, 52, and 49 from 2015 through 2025.
The sample contains 109 analog/mixed-signal events, 62 equipment events, 42
fabless-compute events, and 29 foundry events. Other subsectors have fewer than
the configured three eligible leave-one-out peers and therefore generate no
baseline events; this is a consequence of the frozen minimum-peer rule, not a
post-results deletion.

No company crosses the diagnostic dominance threshold. STMicroelectronics has
the largest count (24 events, 9.9% of the sample), followed by MPWR and onsemi
(21 each). Nine dates have at least three simultaneous shocks. The highest
counts are five events on 2023-05-25 and five on 2024-12-03.

Complete outcome counts decline with the horizon because the frozen peer
portfolio requires every member and the initiator to have an observation on
every event-time date:

| Horizon | Complete | Excluded |
|---:|---:|---:|
| 1 | 226 | 16 |
| 3 | 196 | 46 |
| 5 | 173 | 69 |
| 10 | 114 | 128 |

Missing peer observations are the binding reason at each horizon; international
holiday and non-synchronous calendar coverage therefore matter materially.

## Baseline findings

Mean outcomes are decimal returns:

| Horizon | Convergence | Peer catch-up | Initiator reversal |
|---:|---:|---:|---:|
| 1 | 0.0054 | 0.0026 | 0.0028 |
| 3 | 0.0021 | 0.0018 | 0.0003 |
| 5 | 0.0038 | 0.0022 | 0.0016 |
| 10 | -0.0015 | 0.0026 | -0.0041 |

At the primary one-day horizon, mean convergence is 54 basis points (95% CI
-16 to 124 basis points), the median is 24 basis points, and 54.0% of outcomes
are positive. At the primary five-day horizon, mean convergence is 38 basis
points (95% CI -31 to 106 basis points), the median is 10 basis points, and
51.4% are positive. Five-day peer catch-up averages 22 basis points and
initiator reversal averages 16 basis points, but both medians are slightly
negative and both confidence intervals include zero.

At ten days, average convergence is slightly negative and the initiator
reversal component has changed sign. None of the all-event convergence
confidence intervals excludes zero. The one-day one-sided conditional p-value
is 0.062; the five-day value is 0.133. These are conditional-on-selection
statistics, not selection-preserving null-model evidence.

The point estimates at one and five days are descriptively consistent with a
mix of delayed peer adjustment and initiator reversal. The distributional
evidence is weak: medians are near zero, positive proportions are close to one
half, tails are wide, and uncertainty intervals include zero. The baseline
therefore does not establish a robust anomaly and does not support a claim that
information definitely diffuses.

The event-path figure cumulates signed abnormal returns from t=-5. Its green
line is the cumulative peer-minus-initiator gap: the large negative day-zero
level is the selected shock, while an upward move after day zero represents
convergence. The component figure reports post-event outcomes directly. The
distribution figure is fixed at the primary five-day horizon rather than
pooling correlated horizons.

## Validation

The run verifies that event dates remain inside the frozen sample, peer
portfolios exclude the initiator, both peer endpoints are eligible on the edge
date, event volatility exactly matches a shifted trailing calculation, sign
normalization matches `s × (peer CAR - initiator CAR)`, and convergence equals
peer catch-up plus initiator reversal. The notebook reruns the source pipeline;
core transformations are not implemented in notebook cells.

## Limitations

- The 2026 reviewed classification is applied retrospectively and the current
  company list is not survivorship-free.
- Yahoo adjusted prices are revisable. Corporate-action metadata are incomplete;
  the Stage 11D extreme-return flags are a conservative but narrow proxy.
- Prices remain in local listing currencies. The common semiconductor factor
  does not remove FX movements.
- International market closes are non-synchronous. A shared date is not proof
  that one market could have observed another market's same-date close.
- The equal-weight industry factor contains the focal security. Although it
  cancels from the relative event signal, it can affect the level of the
  reported peer and initiator components.
- Strict complete-frozen-peer windows create substantial horizon attrition,
  especially at ten days.
- Confidence intervals condition on selected events and do not reproduce the
  full event-detection process. Stage 10 null models are needed for that
  comparison.
- Daily data cannot identify intraday leadership, a news timestamp, or an
  information source.

## Unanswered questions

1. Do the Stage 10 selection-preserving nulls produce convergence distributions
   similar to the empirical sample?
2. How sensitive are the components to a pre-declared leave-one-out industry
   factor and synchronized local-market calendars?
3. Are the positive and negative shock asymmetries stable after accounting for
   event-date clustering and simultaneous sector shocks?
4. How much of the ten-day attrition is attributable to specific international
   calendar combinations?
5. Do independently verified corporate actions or earnings announcements
   explain influential tail events?

