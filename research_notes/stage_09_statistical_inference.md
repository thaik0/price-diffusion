# Stage 9: Statistical inference

## Scope

Stage 9 asks whether post-event convergence, peer catch-up, and initiator
reversal are distinguishable from a zero conditional mean in the detected-event
sample. It does not revisit event thresholds, search specifications, simulate a
trading strategy, or construct selection-preserving null samples. The event
definitions and sign normalization remain those fixed in Stages 7 and 8.

A descriptive average cannot distinguish a stable pattern from sampling
variation. A few extremes can also make a mean look large while the median,
trimmed mean, and central distribution remain near zero. Each design cell
therefore reports the mean, median, standard deviation, 10% trimmed mean,
standard error, confidence interval, fraction positive, quantiles, range,
skewness, kurtosis, valid sample size, and missing-event attrition.

## Hypotheses

The pre-specified convergence test is

\[
H_0: E[C_{e,h}] = 0, \qquad H_A: E[C_{e,h}] > 0.
\]

The directional alternative follows the economic definition of convergence.
Peer catch-up and initiator reversal are tested separately against zero with
two-sided alternatives. Separate component tests reveal whether convergence
came from peer movement, initiator reversal, or both. Tests are produced by
horizon, return specification, peer definition, and positive/negative shock,
with an all-events row for reference.

These are conventional within-sample tests. Multiple cells imply multiple
comparisons; Stage 9 does not treat isolated small p-values as discoveries and
does not perform a broad specification search.

## Confidence intervals and assumptions

The analytical interval is

\[
\bar{x} \pm t_{1-\alpha/2,\nu}\,SE(\bar{x}).
\]

Without clustering, this uses the sample standard error and assumes event
observations are independent with a Student-t reference. That assumption is
usually implausible here, so iid inference is explicit rather than the default.

With one-way clustering, the mean is an intercept-only regression and its
covariance is cluster robust with a small-sample correction. Reference degrees
of freedom equal the cluster count minus one. Analytical two-way clustering by
firm and event date is also supported; the smaller cluster count sets the
reference degrees of freedom. Cluster-robust inference is unreliable with few
clusters, a dominant cluster, or dependence beyond the named dimensions.

Optional bootstrap confidence intervals are percentile intervals. An iid
bootstrap resamples events; a clustered bootstrap resamples whole firm or date
blocks. Seed and draw count are configured. Hypothesis-test p-values remain
based on the analytical cluster-robust statistic, so a percentile interval is
not silently treated as a null-imposed bootstrap test. Two-way cluster bootstrap
is intentionally unavailable: a valid multiway scheme requires more care than
one-way block resampling and belongs with later null simulations.

## Effect size versus statistical significance

The standardized effect is the sample mean divided by the sample standard
deviation. It describes magnitude in within-cell standard-deviation units.
Statistical significance instead combines magnitude, dispersion, sample size,
and dependence. A tiny effect can be precise in a large sample; a large effect
can remain uncertain in a small or highly clustered sample. Raw and standardized
effects therefore accompany the interval and p-value.

### Worked uncertainty example

Suppose one cell estimates 10% convergence with a 95% interval from -8% to 28%.
The point estimate is economically large, but the data remain compatible with
no convergence and modest divergence. The conclusion is that the estimate is
imprecise, not that a 10% effect has been established.

Now suppose another cell estimates only 3% convergence with a 95% interval from
2% to 4%. Its estimate is smaller but much more precise, and the interval
excludes zero. The second result is stronger evidence of a positive conditional
mean; the first may still be more economically important if future data confirm
it. Interpretation depends jointly on effect size and uncertainty.

## Why events are dependent

One firm can generate several events, sharing management, liquidity, investor
base, and measurement error. Several semiconductor firms can also trigger on
one date because of common macroeconomic, industry, or supply-chain news.
Treating these rows as iid counts shared shocks as independent information and
can understate uncertainty.

Firm clustering allows arbitrary covariance among events from one initiator.
Date clustering allows arbitrary covariance among events on one date. Two-way
clustering addresses both analytically. It still cannot cover all dependence:
overlapping windows, persistent sector regimes, and cross-date spillovers can
remain. Results must report the cluster definition and cluster count.

## Regression decomposition

Separate models are estimated for peer CAR and initiator CAR within each
horizon, return-specification, and peer-definition cell:

\[
Y_{e,h}=\alpha_h + \beta_h X_e + \gamma_h'Controls_e + \epsilon_{e,h}.
\]

The fixed event-characteristic design includes signed initial relative shock,
event direction, `log1p(volume)`, `log1p(market_cap)`, and subsector. Controls
are market volatility regime, semiconductor volatility regime, and a
simultaneous-event flag. Logs improve numerical conditioning without adding
future information. Categorical variables use indicator coding. The design
avoids automatic feature generation, interactions, and specification grids.

Characteristics merge by event ID. Only the named allowlist enters the formula;
extra columns are ignored. If `information_date` is supplied, a value after the
event fails validation. This guards the interface, but the researcher remains
responsible for ensuring that volume, market cap, and regimes are true
point-in-time values. Coefficients are conditional associations, not structural
causal effects. Direction and signed shock can be strongly related, sparse
categories can be unstable, and controls can contain measurement error.

## Missingness and reporting

Only valid Stage 8 horizons with nonmissing outcomes enter an estimate. Invalid
rows remain in an attrition table with reasons; they are never converted to
zeros. Every result reports sample size. If missingness depends on shock size,
liquidity, or subsequent returns, complete-case estimates can be selected.

Reusable CSV outputs are written under `outputs/tables/`: summary, full
distribution, hypotheses, attrition, regressions, and event-time statistics.
Event-time figures show initiator CAR, peer CAR, and sign-normalized convergence
with intervals. Distribution figures separate positive and negative events.

## Why this stage does not prove causality

Conditional-on-selection inference asks whether a selected-event mean is
measured precisely relative to zero. It does not show how often the same pattern
arises because the sample selected unusually large relative moves, overlapping
windows, common news, or multiple inspected cells. It also cannot establish
that information traveled from initiators to peers. Selection-preserving
simulations and placebo tests belong to a later stage. A pattern is not evidence
until uncertainty is measured, and measured uncertainty alone is not causality.
