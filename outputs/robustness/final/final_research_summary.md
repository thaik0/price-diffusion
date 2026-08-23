# Semiconductor Information Diffusion and Relative Price Discovery

## Research question

Does semiconductor relative-price divergence reflect delayed peer adjustment, initiator reversal, or no persistent mechanism?

## Methodology summary

The frozen 2015–2025 Stage 12 sample contains 54 reviewed securities, 36 ever eligible core securities, and 242 baseline events. Events satisfy the fixed 5% and 3-sigma rule with shifted 60-observation volatility, minimum three economic-subsector peers, and five-day firm/peer-group cooldowns. Peer portfolios are leave-one-out and frozen at the event date. Outcomes are direction-normalized peer catch-up, initiator reversal, and their sum, convergence. Every alternative peer based on returns uses only pre-event history.

## Evidence table

| hypothesis | evidence | conclusion |
| --- | --- | --- |
| Economic peers outperform correlation peers | Five-day paired advantage 0.61% (95% CI 0.16% to 1.05%; n=131); absolute catch-up is at selection-null percentile 83 (p=0.17). | Peer-definition advantage survives at short/medium horizons; absolute diffusion evidence weakens under the selection null. |
| Equipment diffusion | Five-day peer catch-up 0.80%, initiator reversal -0.49%, convergence 0.31%. | Peer component survives; total convergence remains weak. |
| Lower sector momentum strengthens convergence | Five-day one-month momentum coefficient -0.033 (95% CI -0.126 to 0.060). | Directional and horizon-sensitive, not robustly established. |
| Shock nonlinearity | All 9 pre-specified squared-shock intervals include zero. | Not confirmed. |

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

| method | mean | ci_lower | ci_upper | sample_size |
| --- | --- | --- | --- | --- |
| null_simulation | 0.0002 | -0.0039 | 0.0044 | 82 |
| observed | 0.0022 | -0.0019 | 0.0059 | 173 |
| pseudo_events | -0.0002 | -0.0042 | 0.0039 | 165 |
| random_peers | -0.0001 | -0.0027 | 0.0033 | 173 |

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
