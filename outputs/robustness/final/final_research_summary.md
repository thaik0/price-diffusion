# Semiconductor Information Diffusion and Relative Price Discovery

## Research question

Does semiconductor relative-price divergence reflect delayed peer adjustment, initiator reversal, or no persistent mechanism?

## Methodology summary

The frozen 2015–2025 Stage 12 sample contains 54 reviewed securities, 36 ever eligible core securities, and 242 baseline events. Events satisfy the fixed 5% and 3-sigma rule with shifted 60-observation volatility, minimum three economic-subsector peers, and five-day firm/peer-group cooldowns. Peer portfolios are leave-one-out and frozen at the event date. Outcomes are direction-normalized peer catch-up, initiator reversal, and their sum, convergence. Every alternative peer based on returns uses only pre-event history.

## Evidence table

| hypothesis | estimate / evidence | uncertainty | status | interpretation |
| --- | --- | --- | --- | --- |
| Universal convergence | Five-day economic-peer catch-up +0.22%; convergence +0.38% (n=173). Ten-day convergence -0.15%. | Five-day selection-preserving empirical p≈0.17 for catch-up and p≈0.13 for convergence; dependence-aware intervals include zero. | not supported | Some events may adjust, but the sample does not establish a universal diffusion effect. |
| Economic vs correlation peer catch-up | Five-day paired economic-minus-correlation advantage +0.61% (n=131); economic level +0.34% versus correlation level -0.27%. | Paired-bootstrap 95% CI +0.16% to +1.05%; positive at one and five days and imprecise at ten days. | supported | Economic relationships contain incremental short-horizon peer-adjustment information relative to the fixed trailing-correlation rule. |
| Equipment peer catch-up | Five-day catch-up +0.80%; initiator reversal -0.49%; convergence +0.31% (n=47). | Catch-up 95% CI +0.28% to +1.33%; reversal -1.40% to +0.42%; convergence -0.60% to +1.22%. | partially supported | Equipment peers moved in the shock direction, but initiator continuation weakened total convergence. |
| Lower prior sector momentum | Five-day convergence +0.92% after weak/nonpositive one-month momentum versus -0.02% after positive momentum; controlled coefficient -0.033. | Five-day coefficient 95% CI -0.126 to 0.060; support was stronger at one day and imprecise later. | suggestive | The direction is plausible but horizon-sensitive and not uniformly precise. |
| Nonlinear shock magnitude | All 9 pre-specified squared-shock tests had confidence intervals spanning zero. | Five-day convergence squared term about +0.036 percentage points; 95% CI -0.062 to +0.134 percentage points. | not supported | The exploratory curvature did not survive the fixed formal test. |
| Time-stable absolute catch-up | Five-day catch-up +0.01% in 2015–2018, -0.35% in 2019–2021, and +0.45% in 2022–2025. | Every period confidence interval includes zero; recent years contribute most of the positive estimate. | not supported | Absolute catch-up was not uniform across the sample period. |

## Specification evidence at five days

| variation_type | specification | event_count | mean | ci_lower | ci_upper | status |
| --- | --- | --- | --- | --- | --- | --- |
| event_threshold | 2_sigma | 243 | 0.0029 | -0.0008 | 0.0066 | estimated_exploratory |
| event_threshold | 2.5_sigma | 214 | 0.0020 | -0.0018 | 0.0059 | estimated_exploratory |
| event_threshold | 3_sigma | 173 | 0.0022 | -0.0020 | 0.0063 | estimated_exploratory |
| event_threshold | 4_sigma | 117 | 0.0015 | -0.0035 | 0.0065 | estimated_exploratory |
| universe | core | 173 | 0.0022 | -0.0020 | 0.0063 | estimated_exploratory |
| universe | core_plus_extension | 309 | 0.0019 | -0.0009 | 0.0047 | estimated_exploratory |
| universe | excluding_questionable | 173 | 0.0022 | -0.0020 | 0.0063 | estimated_exploratory |
| peer_advantage_horizon | economic_minus_correlation | 131 | 0.0061 | 0.0017 | 0.0106 | estimated_pre_specified |

## Null and placebo evidence at five days

| method | mean | ci_lower | ci_upper | events_per_iteration | resampling_iterations |
| --- | --- | --- | --- | --- | --- |
| null_simulation | 0.0002 | -0.0039 | 0.0044 | 82 | 500 |
| observed | 0.0022 | -0.0019 | 0.0059 | 173 | 1000 |
| pseudo_events | -0.0002 | -0.0042 | 0.0039 | 165 | 200 |
| random_peers | -0.0001 | -0.0027 | 0.0033 | 173 | 200 |

## Time stability at five days

| group | event_count | mean | ci_lower | ci_upper |
| --- | --- | --- | --- | --- |
| early_2015_2018 | 38 | 0.0001 | -0.0058 | 0.0059 |
| middle_2019_2021 | 29 | -0.0035 | -0.0107 | 0.0037 |
| recent_2022_2025 | 106 | 0.0045 | -0.0017 | 0.0107 |

## Final interpretation

The most defensible conclusion is narrow: reviewed economic peers adjust more than trailing-correlation peers over short and medium horizons, but the evidence does not establish a persistent, causal, or tradable diffusion mechanism. At five days the random-peer and pseudo-event means are near zero, yet their intervals overlap the observed estimate; absolute peer catch-up has a selection-null p-value of 0.17. Equipment events show a peer response, yet negative initiator reversal offsets it and total convergence is not distinguishable from zero. Sector momentum is suggestive and horizon-sensitive. Shock nonlinearity is not supported.

## Limitations

- Prices and volumes come from Yahoo Finance; adjusted histories are revisable.
- The current reviewed company list and retrospective classifications create survivorship concerns.
- There is no event-level news classification, so common news and firm-specific news cannot be separated.
- The frozen data have no broad-market benchmark; market-adjusted returns and market-volatility controls remain unavailable.
- Event counts are limited, shrink materially with horizon, and contain repeated firms, same-day events, and overlapping windows.
- International listings have non-synchronous closes, local currencies, exchange holidays, and differing information sets.
- Market capitalization is unavailable, so capitalization-weighted peers cannot be evaluated.
- Null models preserve selected features of returns, not every tail, volatility, and structural-break property.

## Research discipline

All requested variants were fixed before this run, weak and unavailable results are retained, and no specification is selected as “best.” A quantitative result is valuable only if it survives attempts to disprove it.
