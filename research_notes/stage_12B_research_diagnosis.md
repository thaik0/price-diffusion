# Stage 12B Research Diagnosis

## Purpose

Stage 12A asked whether peer-relative semiconductor shocks converge on average.
Its weak unconditional result can mean either that there is no stable effect or
that the event sample mixes distinct economic mechanisms. Stage 12B therefore
examines what the events are, whether economically connected peer sets matter,
which observable conditions accompany the outcomes, and how sensitive the
descriptive conclusion is to reasonable design choices.

This stage is exploratory. It does not optimize a trading rule, select a
profitable subgroup, or convert post-hoc patterns into confirmed hypotheses.

## Analyses completed

- Event diagnostics: counts by time, company, subsector, and direction; largest
  shocks; pre-event volatility; strictly trailing volume percentiles; peer
  counts and portfolio coverage.
- Subsector and peer analysis: convergence, peer catch-up, and initiator
  reversal by subsector; strictly trailing peer-correlation measures; and a
  common-event comparison of economic, trailing-correlation, and broad
  semiconductor peers.
- Event characteristics: exploratory continuous relationships for shock size,
  liquidity, volume, semiconductor conditions, direction, and peer quality.
- Robustness exploration: thresholds from 2 to 4 sigma, horizons from 1 to 20
  trading days, raw and semiconductor-adjusted returns, core and extension
  universes, and two treatments of extreme outcomes.

Every subgroup table reports its sample size. Samples below 30 are labeled
`small_sample_descriptive_only` and are not ranked. Correlation peers and every
trailing characteristic use observations strictly before the event.

## 1. Why might unconditional convergence be weak?

The sample is heterogeneous in both composition and mechanism.

- Of 242 detected events, 109 (45.0%) are in analog/mixed signal, 62 (25.6%)
  in semiconductor equipment, 42 (17.4%) in fabless compute, and 29 (12.0%)
  in foundry. Six reviewed subsectors have no qualifying baseline event,
  largely because the core universe and minimum-three-peer rule do not provide
  eligible event samples for them.
- Five-day analog/mixed-signal convergence is close to zero (mean -0.15%,
  n=68), while the equipment estimate is +0.31% (n=47). In equipment, the
  components point in opposite directions: peer catch-up is +0.80% and
  initiator reversal is -0.49%. Pooling them can obscure mechanism rather than
  merely attenuate one common effect.
- The mean is sensitive to the event threshold. Five-day convergence falls
  from +0.88% at 2 sigma (n=243 complete outcomes) to +0.04% at 4 sigma
  (n=117). Because threshold samples are nested but differently affected by
  cooldown and completeness, this is descriptive evidence of threshold
  dependence, not proof that moderate shocks converge.
- Winsorizing at the 1st/99th percentiles or excluding observations more than
  three IQRs from the convergence distribution changes the five-day mean only
  modestly (from +0.38% to about +0.40%). The weak baseline is therefore not
  explained solely by a few extreme post-event outcomes.

## 2. Are there economically meaningful subgroups?

There is one mechanism-level pattern worth formal follow-up: at five days,
semiconductor-equipment events show mean peer catch-up of +0.80% (n=47,
descriptive 95% interval +0.28% to +1.33%) while initiator reversal is negative.
This is qualitatively consistent with information moving to economically
related equipment firms rather than the initiator correcting.

Fabless-compute and foundry point estimates place more of their convergence in
initiator reversal. The fabless-compute sample is only 34 complete five-day
events and its intervals are wide. Foundry has 24 and is explicitly a small
sample. These estimates motivate mechanism distinctions but do not support a
subsector ranking.

The core-plus-extension universe produces higher five-day convergence
(+1.21%, n=309 complete outcomes) than the core universe (+0.38%, n=173).
This comparison simultaneously changes eligible firms, peer portfolios, and
detected events. It may reflect information diffusion among additional firms,
but it may also reflect listing histories, geography, asynchronous trading, or
sample composition. A direct tier interaction on a common design is required
before interpreting it economically.

## 3. Does peer construction matter?

On the same baseline event dates, five-day mean convergence is +0.38% for
economic subsector peers (n=173), +0.15% for trailing-correlation peers (n=213),
and +0.29% for the broad semiconductor portfolio (n=131). All three descriptive
intervals include zero.

The decomposition differs more than the total. Economic peers have positive
mean catch-up (+0.22%); trailing-correlation peers have negative mean catch-up
(-0.19%); broad peers are approximately zero. However, event-level pre-event
peer similarity has little linear relationship with five-day convergence, and
the peer-definition intervals overlap substantially. The present evidence does
not establish that correlation peers improve economic measurement.

Broad portfolios have fewer complete long-horizon observations because the
frozen portfolio requires returns for every constituent. This attrition is part
of the estimand and should not be mistaken for a stronger or weaker effect.

## 4. Are events concentrated or noisy?

The events are concentrated, but no single company dominates the full sample.

- 2024 contributes 21.5% of events; the largest calendar month contributes
  4.1%.
- STM is the largest initiator at 24 events (9.9%), followed by MPWR and ON at
  21 each (8.7%).
- Positive events are 57.9% of the sample.
- The largest shocks often coincide with exceptional volume. For example, the
  largest event (CRDO on 2024-12-03, +47.8% relative shock) is at the 100th
  percentile of its strictly trailing volume history and about 8.4 times its
  trailing median volume. Several other largest events are similarly close to
  the top of their prior volume distributions.

This pattern suggests that at least some detector output reflects salient
firm-specific information rather than ordinary volatility. It does not identify
the information source: earnings and news flags are not populated, corporate
actions are only conservatively flagged, and market capitalization is missing
for every event. Unusual volume is evidence of salience, not evidence of a
particular causal mechanism.

## 5. Event-characteristic evidence

At five days, the exploratory slope for absolute shock magnitude is positive
(+0.74 percentage points of convergence per one-standard-deviation increase),
but its HC3 interval includes zero. The standardized-shock slope is close to
zero. Liquidity, volume percentile, abnormal volume, event direction, peer
count, and peer similarity also show weak linear relationships.

The clearest conditional association is with the prior 126-day semiconductor
return: lower prior sector returns accompany more five-day convergence (slope
-0.82 percentage points per standard deviation; exploratory 95% interval
-1.46% to -0.19%, n=173). The related bear-regime indicator points in the same
direction but is less precise. This is a regime hypothesis, not a confirmed
result, because it was selected after inspecting multiple relationships and
does not use a broad-market control.

## Robustness interpretation

- Raw and semiconductor-factor-adjusted returns give identical convergence by
  construction: subtracting the same contemporaneous factor from the initiator
  and frozen peer portfolio cancels in their difference. The mechanism
  components can still differ in level.
- A market-adjusted specification cannot be estimated because the frozen Stage
  11D data contain no broad-market benchmark. The output records it as
  `unavailable` rather than substituting a semiconductor factor.
- Excluding questionable securities is identical to the core universe because
  the reviewed security master contains zero questionable names.
- Tail treatments do not materially change the baseline five-day conclusion.
- Threshold and universe choices matter more than tail treatment, but both
  change event composition and therefore require controlled confirmation.

## Limitations

1. Only four of ten reviewed subsectors generate baseline events, so the study
   cannot diagnose memory, EDA/IP, packaging/testing, materials,
   mobile/connectivity, or integrated-device-manufacturer mechanisms under the
   current core/minimum-peer design.
2. Market capitalization has zero coverage. Broad-market volatility and a
   market-adjusted return series are also unavailable.
3. Earnings and news flags are placeholders, preventing event-type validation.
4. International listings introduce non-synchronous calendars and information
   timing that a common daily event clock may not fully represent.
5. The peer comparison holds event dates fixed. It identifies outcome
   sensitivity to the peer portfolio, not the combined effect of redefining
   both shocks and outcomes.
6. Confidence intervals and HC3 p-values are descriptive exploratory summaries;
   they do not correct for repeated firms, simultaneous events, overlapping
   windows, or the multiple specifications inspected here.
7. The retrospective 2026 classification is applied to 2015–2025 by the frozen
   design and is not a point-in-time historical industry classification.

## Recommended Stage 13 hypotheses

These hypotheses should be preregistered, estimated with firm/date-aware
dependence controls, and evaluated on an untouched holdout or through an
explicit sample split.

1. **Equipment diffusion mechanism.** For semiconductor-equipment events,
   five-day peer catch-up is positive, while initiator reversal is not the main
   source of convergence. Test the component contrast directly rather than only
   total convergence.
2. **Semiconductor regime interaction.** Five-day convergence is stronger after
   negative trailing semiconductor-sector returns than after positive trailing
   returns. Specify the trailing window and interaction before testing.
3. **Universe-tier heterogeneity.** Extension-tier initiators or peers have a
   different convergence response from core firms on a common, point-in-time
   peer and event design. Include explicit controls for geography and trading
   calendar overlap.
4. **Shock-scale nonlinearity.** Convergence is not monotonic in standardized
   shock size. Pre-specify a simple functional form or a small number of
   economically justified regions; do not search thresholds on the test set.
5. **Economic peers versus generic similarity.** Economic-subsector peers have
   greater post-event catch-up than trailing-correlation or broad peers for the
   same initiator events. This should be tested as a paired event-level
   difference with identical missing-data rules.

Before formal testing, the highest-value data improvements are a point-in-time
broad-market benchmark, point-in-time market capitalization, event/news labels,
and explicit local-market timestamp alignment.

## Validation record

- Correlation-peer maximum information date is strictly earlier than every
  event date: passed.
- Peer-quality trailing windows are strictly earlier than every event date:
  passed.
- Baseline event count remains 242 and baseline artifacts are not overwritten:
  passed.
- All subgroup/specification results report sample sizes and small-sample
  labels: passed.
- Conclusions are framed as descriptive and hypothesis-generating: passed.
