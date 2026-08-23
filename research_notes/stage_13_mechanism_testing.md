# Stage 13: Mechanism Testing

## 1. Hypotheses tested

Stage 13 converted four Stage 12B exploratory patterns into fixed mechanism tests:

1. Semiconductor-equipment events have stronger post-event peer adjustment after controlling for event characteristics.
2. Reviewed economic-subsector peers show stronger catch-up than peers selected from trailing return correlations or the broad semiconductor basket.
3. Lower prior semiconductor-sector returns are associated with stronger convergence.
4. Standardized shock magnitude has a nonlinear relationship with post-event adjustment.

These are associational hypotheses. The analysis does not optimize thresholds, rank undisclosed subgroups, construct a strategy, or claim causality.

## 2. Methodology

All calculations use the 242 events and frozen inputs recorded in the Stage 12 baseline manifest. Stage 13 neither redetects events nor overwrites baseline artifacts.

### Mechanism regressions

Separate 1-, 5-, and 10-day OLS models were estimated for raw peer CAR, convergence, and initiator reversal. The primary specification includes an equipment indicator, absolute standardized shock magnitude, prior one-month semiconductor momentum, a strictly pre-event volume measure, and event direction. HC3 standard errors and 95% confidence intervals are reported. A single targeted extension adds squared standardized shock magnitude; no other functional forms or thresholds were searched.

The baseline contains only economic-subsector peer events, so `EconomicPeerIndicator` equals one throughout this regression sample and cannot be separately identified. Complete-case regression sample sizes are 226 events at one day, 173 at five days, and 114 at ten days.

### Equipment analysis

Equipment events were disclosed by company and year. Equipment was compared with all non-equipment events, and every individual subsector was also reported. The decomposition distinguishes raw peer and initiator CARs from direction-normalized peer catch-up, initiator reversal, and convergence. Valid equipment samples contain 58, 47, and 22 events at 1, 5, and 10 days, respectively. The 62 detected equipment events were distributed across AMAT (18), KLAC (16), LRCX (15), ASML (12), and DISCO/6146.T (1); no company was hidden.

Customer concentration, shared fabrication-industry exposure, and semiconductor capex cyclicality are economic interpretations only. The frozen panel does not directly measure customer concentration or capex exposure.

### Peer relationships

Economic-subsector, trailing-correlation, and broad semiconductor peers were evaluated on identical complete events at each horizon. Correlation peers use a 252-trading-day lookback, require 60 overlapping pre-event observations, exclude the event date, and are frozen at event-date membership. Common samples contain 208, 131, and 62 events at 1, 5, and 10 days. Economic-minus-correlation paired differences use a deterministic 10,000-replication event-level bootstrap.

### Market regimes

Prior one-month and three-month semiconductor momentum are compounded returns over 21 and 63 trading days, with every input lagged one day. Semiconductor volatility is the lagged 21-day annualized standard deviation. Continuous HC3 regressions are primary; the descriptive regime comparison splits at zero return into weak/nonpositive and strong/positive periods, an economic threshold rather than an optimized quantile. Broad-market volatility is unavailable because the frozen baseline contains no broad-market return series.

## 3. Main findings

### Mechanism regression

At five days, the equipment coefficient was -0.09 percentage points for raw peer CAR (95% CI -0.89 to +0.70) and -0.23 percentage points for convergence (95% CI -1.68 to +1.22), with 173 observations. Standardized shock magnitude, volume, direction, and one-month sector momentum also had economically modest or imprecise five-day coefficients. Model R-squared was about 1% to 3%, so these event characteristics explain little of the cross-sectional variation.

The squared shock term was small at every horizon and for every dependent variable; all nine confidence intervals included zero. At five days its coefficient was +0.003 percentage points for raw peer CAR and +0.036 percentage points for convergence per squared shock unit. The targeted nonlinear extension therefore did not confirm the exploratory nonlinear pattern.

### Equipment decomposition

The equipment result survives as a peer catch-up component, not as stronger overall convergence. Among 47 complete five-day equipment events, mean peer catch-up was +0.80% (95% CI +0.28% to +1.33%), while mean initiator reversal was -0.49% (95% CI -1.40% to +0.42%). Their sum produced mean convergence of +0.31% (95% CI -0.60% to +1.22%). For 126 non-equipment events, five-day peer catch-up was approximately zero and convergence was +0.40% (95% CI -0.62% to +1.42%). The conditional regression also did not show a larger five-day equipment convergence effect.

The company distribution is not dominated by one initiator, although the group is concentrated in four U.S./European large-cap equipment firms and the single DISCO event adds little independent evidence. Every company-level count remains below the 30-event small-sample threshold.

### Peer relationships

Economic peers produced the clearest formal support. In the 131-event common five-day sample, mean direction-normalized catch-up was +0.34% for economic peers, -0.27% for correlation peers, and +0.01% for the broad basket. The paired economic-minus-correlation catch-up difference was +0.61% (paired-bootstrap 95% CI +0.16% to +1.05%). Because initiator returns are identical within an event, the convergence difference is the same +0.61%.

The paired difference was also positive at one day (+0.53%, 95% CI +0.25% to +0.81%, n=208). At ten days it was +0.73%, but the interval included zero (-0.19% to +1.69%, n=62). Economic similarity therefore explains short- and medium-horizon peer adjustment better than the pre-specified statistical-similarity definition in this sample, with substantial long-horizon attrition.

### Market regime

The direction of the continuous relationship was consistent with the exploratory finding. In the five-day controlled model, the one-month momentum coefficient was -0.033 per unit prior return (95% CI -0.126 to +0.060) and the three-month coefficient was -0.039 (95% CI -0.089 to +0.011), both with 173 observations. The intervals are wide.

The descriptive five-day sign split showed +0.92% mean convergence in 73 weak/nonpositive one-month events versus -0.02% in 100 positive-momentum events. For three-month momentum, the corresponding means were +0.81% (n=57) and +0.17% (n=116). At one day, the controlled one-month momentum coefficient was negative with a confidence interval below zero; five- and ten-day estimates were negative but imprecise. The regime mechanism is therefore directionally supported and most visible at short horizons, not uniformly established across horizons.

## 4. Which exploratory findings survived formal testing

| Stage 12B finding | Stage 13 assessment | Interpretation |
|---|---|---|
| Equipment events have stronger five-day adjustment | Partially survived | Equipment peer catch-up was +0.80%, but negative initiator reversal offset it; overall convergence and the controlled equipment coefficient were not stronger. |
| Economic peers outperform correlation and broad peers | Survived most clearly | Paired economic-minus-correlation catch-up was +0.61% at five days with a bootstrap interval above zero; the result weakened at ten days. |
| Lower sector momentum predicts stronger convergence | Partially survived | Coefficients were consistently negative and weak-regime means were higher, but five- and ten-day intervals were wide. |
| Shock magnitude has nonlinear effects | Did not survive | The one pre-specified squared-shock extension was small and imprecise at all horizons and outcomes. |

“Survived” means that the fixed Stage 13 result is economically aligned and reasonably precise in this sample. It does not mean causal or universally replicable.

## 5. Limitations

- The analysis conditions on detected events and includes overlapping post-event windows.
- Yahoo adjusted prices are revisable, and corporate-action and earnings metadata remain incomplete.
- Present-day subsector classifications are applied retrospectively, and the universe is not survivorship-free.
- International closes are non-synchronous and listings use local currencies.
- The frozen baseline lacks a broad-market return series, so market volatility could not be estimated.
- Equipment customer concentration and capex exposure are plausible mechanisms but are not directly observed.
- Company, subsector, and ten-day samples are often small; every such result is labeled.
- Regression R-squared is low and confidence intervals are generally wide.
- The paired peer result depends on the pre-specified correlation lookback, minimum-history rule, and equal-weight portfolios.
- Multiple outcomes and horizons are shown for mechanism interpretation; p-values are contextual and are not used as a discovery filter.

## 6. Next research questions

1. Does the economic-peer advantage replicate on a later, untouched event sample with the peer taxonomy frozen in advance?
2. Can point-in-time customer and capex-exposure data distinguish shared-demand information from generic subsector co-movement?
3. Does the momentum relationship remain after adding a genuine broad-market factor and volatility series to a newly frozen dataset?
4. Are international-close and currency adjustments responsible for part of the peer-definition difference?
5. Can event-level earnings and news labels separate industry information diffusion from coincident firm-specific announcements without changing the event threshold?

## Validation record

All nine automated Stage 13 checks passed: sector and volume characteristics were strictly pre-event; correlation peers were strictly pre-event; regressions reported sample sizes; small samples were flagged; every subsector was disclosed; the baseline event count remained 242; all frozen input hashes matched the Stage 12 manifest; and market-volatility unavailability was disclosed. The machine-readable record is `outputs/mechanism_analysis/validation.csv`.
