# Stage 10: Null Models and Placebo Experiments

## Purpose

An average post-event convergence estimate is not, by itself, evidence of
information diffusion. Stage 7 deliberately selects unusually large
company-minus-peer moves. Even if returns contain no cross-company transmission,
extreme observations tend to be followed by less-extreme observations. This
regression-to-the-mean mechanism can create apparent initiator reversal and can
make the relative gap shrink mechanically.

Stage 10 therefore asks a stronger question: is convergence after the observed
events larger than convergence produced by realistic versions of the same
research procedure when the proposed economic relationship or timing is absent?
All thresholds, cooldowns, horizons, sign conventions, peer-weight constraints,
and missing-data rules remain fixed. The robustness code changes the input under
the null and calls the existing Stage 7 detector and Stage 8 event-study engine.

## Pre-specified null hypotheses

### Random-peer placebo

The null hypothesis is that, conditional on the initiator, event date, eligible
semiconductor universe, peer count, and weight vector, economically classified
peers have the same post-event catch-up and convergence as randomly selected
semiconductor companies.

For every event and iteration, sampling is without replacement from companies
eligible on the event date, excludes the initiator, preserves the economic
portfolio's peer count, and preserves the exact multiset of weights. The event
date and event company do not change. This experiment is useful because it asks
whether peer identity contains economic information rather than merely exposing
the initiator to a diversified semiconductor basket. It does not establish that
the classification is the unique or optimal peer definition.

### Matched pseudo-event placebo

The null hypothesis is that actual event dates have no more post-date catch-up,
reversal, or convergence than eligible non-event dates for the same company with
the same pre-specified matching characteristics.

The default exact strata are subsector, volatility regime, market regime, and
liquidity bucket. The company is fixed, the pseudo-date must be eligible, and a
valid economic peer portfolio must exist on that date. Dates within the configured
exclusion window around any real event for that company are excluded. Stage 8
then freezes the economic peer basket on the sampled pseudo-date and applies the
same horizons and convergence formula. Matching makes ordinary state differences
less likely to drive the comparison, but it can only control characteristics that
were measured and included before results were examined. Sparse exact-match
strata are a design limitation and must not be relaxed after seeing results.

### Selection-preserving return null

The primary null hypothesis is that the observed mean convergence is typical of
a return process that preserves realistic market structure and the full event
selection procedure but contains no original cross-company lead-lag path.

The implemented simulation starts from a date-by-company return matrix:

1. It separates each date's cross-sectional mean (the common semiconductor
   component) from the company residual vector.
2. It keeps the common component on its original target date, preserving the
   realized market environment.
3. It draws a whole residual vector from the same pre-specified market regime.
   Moving the vector as one unit preserves its contemporaneous cross-sectional
   dependence rather than simulating independent company returns.
4. Donor dates are restricted to the target date or earlier. An audit table
   records every source/target pair, and the simulation fails if future data is
   used.
5. Draws are independent across target dates, destroying the original temporal
   sequence in which one company's residual preceded another company's residual.
6. Peer-relative abnormal returns are recalculated, Stage 7 detects a new set of
   extreme events, and Stage 8 measures those events without modification.

Rerunning detection is the essential selection control. Simulating outcomes only
for the already-selected real events would condition on an extreme observed
sample without reproducing how that sample arose. It would therefore fail to
measure the regression-to-the-mean bias induced by selection.

This is not an iid random-return simulation. It retains the target-date common
component, regime path, marginal residual vectors, and within-vector
cross-sectional dependence. It does not claim to preserve every higher-order
feature of returns. In particular, independently reordering residual vectors can
weaken residual volatility clustering and nonlinear serial dependence beyond what
is represented by the regime labels.

### Temporal falsification

The null/falsification question is whether the same apparent relation exists when
the arrow of time is reversed. The normal Stage 8 outcome calculation is applied
to days `t-h` through `t-1` instead of `t+1` through `t+h`, with the event and its
direction held fixed. A systematic pre-event pattern may reflect anticipation,
common shocks, selection, or timing error; it cannot be interpreted as the future
peer response causing the past event. The temporal placebo is diagnostic rather
than proof that the forward result is causal.

## Empirical comparison

For each horizon, return specification, peer definition, and outcome, the
selection-preserving simulation stores one mean statistic per valid null
iteration. The report contains:

- the observed mean;
- the null mean and standard deviation;
- the number of usable null iterations;
- the observed sample size;
- a finite-simulation, upper-tail empirical p-value
  `(1 + count(null >= observed)) / (B + 1)`; and
- the observed percentile within the null distribution.

The plus-one correction prevents a reported p-value of zero. The one-sided
alternative is pre-specified because convergence, peer catch-up, and initiator
reversal are sign-normalized so that larger positive values represent stronger
movement in the hypothesized direction.

Outperforming zero is weaker evidence than outperforming the selection-preserving
null. For example:

- Observed mean convergence: 5.0%.
- Null mean convergence: 4.5%.

The observed value is positive, but nearly all of it is reproduced mechanically
by the null. The economically relevant excess is only 0.5 percentage points, and
evidence is weak unless 5.0% lies unusually far into the null tail.

By contrast:

- Observed mean convergence: 5.0%.
- Null mean convergence: 0.0%.

If the null distribution is sufficiently concentrated around zero, the full
five percentage points are unexplained by the selection-preserving benchmark.
That is stronger evidence for an effect associated with the original economic
relationships and timing. It still does not, by itself, identify a causal news
transmission mechanism.

## Dependence-aware bootstrap

Two bootstrap schemes are available and should be reported as complementary
sensitivity analyses:

- The firm-block bootstrap samples companies with replacement and retains every
  event, horizon, and overlapping window belonging to each selected company.
  It addresses repeated events within firms.
- The date-block bootstrap samples contiguous blocks of event dates and retains
  all events on each selected date. It addresses same-day correlation, local
  market episodes, and some dependence created by overlapping windows.

Neither scheme makes every event independent. Firm blocks do not fully model
cross-firm common shocks, while date blocks do not retain all long-run dependence
within a company. Comparing them reveals whether conclusions depend heavily on a
single clustering view. Overlapping windows are retained and flagged rather than
silently discarded.

## Validation and reproducibility

The Stage 10 tests verify that:

- random peers exclude the initiator;
- random peers are eligible on the event date;
- peer counts, non-negative weights, unit weight sums, and the original weight
  multiset are preserved;
- every random-peer iteration retains the real event count;
- pseudo-events retain one row per real event, preserve the company, exactly
  match the configured strata, satisfy eligibility, avoid real-event windows,
  and have valid dated peers;
- synchronous null resampling retains the date-specific common component;
- every simulated donor date is no later than its target date;
- each null iteration reruns detection and event study with stable configuration
  signatures;
- convergence, peer catch-up, and initiator reversal are all compared;
- firm and date block bootstraps are deterministic under a fixed seed; and
- null-distribution and placebo-comparison plots can be generated from the
  standardized tables.

Random seeds and production iteration counts live in `configs/baseline.yaml`.
Tests intentionally use much smaller counts and deterministic synthetic panels;
their numeric output demonstrates mechanics, not an empirical semiconductor
finding.

## Important limitations

1. Exact pseudo-event matching can fail in small or unusual strata. Expanding a
   stratum after inspecting results would change the design and is prohibited.
2. Random semiconductor peers can share broad sector factors with economic
   peers, so the placebo is demanding but not a no-correlation control.
3. Synchronous residual-vector resampling preserves contemporaneous dependence
   and the common market path, but not every form of temporal dependence,
   stochastic volatility, tail dependence, listing churn, or structural break.
4. Causal donor restriction emphasizes the expanding historical distribution;
   early target dates have fewer possible donors.
5. Null iterations can produce different event counts. This is intentional:
   selection is rerun rather than forcing simulated observations to mimic the
   realized event count. Random-peer and pseudo-event placebos, by contrast,
   preserve the real count by construction.
6. Event windows that extend beyond the sample or have missing returns remain
   invalid under the existing Stage 8 rules; null iterations with no valid events
   do not contribute a statistic and are reported transparently.
7. Empirical p-values describe extremeness under the implemented null model.
   They do not compensate for post-hoc choices across thresholds, horizons,
   return specifications, or null designs.
8. A result that beats every placebo is stronger evidence against research-design
   artifacts, not automatic proof of a tradable strategy or causal information
   diffusion.
