# Semiconductor Information Diffusion and Relative Price Discovery

Stack: Python, pandas, NumPy, SciPy, Matplotlib, Yahoo Finance

Here I look into what happens after one semiconductor moves unusually far from economically related peers. Do the peers catch up, does the initiator reverse, or does the gap persist?

This project is an event study using daily semiconductor returns from 2015-2025. I compare defined peer groups with alternatives such as peers selected from trailing return correlations, then test whether post-event price adjustment is distinguishable from noise.

The main finding is narrow: I did not find strong evidence that large semiconductor-relative moves generally converge afterward. However, economically related pers showed more five-day catch-up than correlation-selected peers on the same events.

## Measuring convergence
For each event, I call the stock with the unusual move the "initiator" and compare it with a leave-one-out portfolio of "peers".

Post-event convergence has two components:
```
convergence = peer catch-up + initiator reversal
```
- Peer catch-up: peers move in the direction of the initiator's original shock.

- Initiator reversal: the initiating stock moves back toward its peers.

Keeping these components separate is important, because convergence can come from information spreading or the initiator simply reversing.

## Main result
Across 173 events with complete five-day outcomes:

- mean convergence: +0.38%

- mean peer catch-up: +0.22%

Both confidence intervals included zero, and ten-day convergence was slightly negative.

But, on the same 131 five day events:
| Peer definition | Mean five-day catch-up |
| --- | ---: |
| Economic peers | **+0.34%** |
| Trailing-correlation peers | **−0.27%** |

The paired difference is +0.61% with a confidence interval of +0.16% to +1.05%. This suggests that economic relationships captured more short-horizon adjustment than selecting peers from historical return correlation. It doesn't establish that economic peers themselves have statistically strong absolute diffusion, unfortunately.

## Event study
I created the universe and grouped companies into economic semiconductor peer sets. Daily adjusted prices and volumes come from Yahoo Finance from 2015–2025.

An event occurs when an initiator moves unusually far relative to its peers after removing the same-day equal-weight semiconductor-sector return. The relative move must exceed both: 5% and 3x its trailing 60-observation volatility. Peer catch-up, initiator reversal, and total converge are measured over 1, 3, 5, and 10 trading days.

## Secondary results/findings
There were two secondary patterns I found:
- Equipment-company events produced about +0.80% five-day peer catch-up, but the initiator continued moving in the original direction on average, leaving total convergence small.

- Lower prior semiconductor momentum was directionally associated with more convergence, although the result was not stable across horizons.

## Limitations
- Yahoo Finance is not an institutional point-in-time market database
- Economic peer classifications were mainly qualititative
- Universe is not survivorship-free
- International listings have different trading hours, holidays, currencies, and info sets
- Study uses daily data, cannot establish intraday leadership or profitability
