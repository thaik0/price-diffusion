# Interview guide

Use this as a set of talking points, not a script. The strongest answer is usually the short one followed by the specific check that made the conclusion more cautious.

## 30-second version

I studied what happens after one semiconductor stock makes an unusually large move relative to economically related peers. I built a daily event study that separates peer catch-up from reversal in the initiating stock. The unconditional convergence result was weak, but on the same 131 five-day events, economic peers caught up 0.61% more than peers selected from trailing return correlations; the paired-bootstrap 95% interval was 0.16% to 1.05%. Selection-preserving null tests weakened the absolute diffusion claim, so my conclusion is about the value of economic peer definitions, not a universal anomaly.

## 2-minute version

I was interested in semiconductor equities because firms are tied through customers, suppliers, technology cycles, and capital spending, but those relationships are not necessarily the same as recent return correlation.

I manually reviewed the universe and economic peer groups, then defined an event as a stock's daily return relative to its leave-one-out peers exceeding both 5% and three times its shifted trailing volatility. The post-event outcome has two parts: peers moving in the direction of the original shock, which I call peer catch-up, and the initiating stock moving back, which I call initiator reversal. Their sum is convergence.

The frozen baseline was weak. Five-day convergence averaged 0.38%, but the confidence interval included zero, and ten-day convergence was slightly negative. That pushed me to ask whether peer definition mattered more than the unconditional average.

For the same events, I compared the reviewed economic peers with peers selected using only trailing return correlations. Over five days, economic-peer catch-up was 0.34% and correlation-peer catch-up was −0.27%. The paired difference was +0.61%, with a 95% bootstrap interval from +0.16% to +1.05% on 131 events.

Then I tried to break the result. I varied thresholds, horizons, returns, and universes; used random peers and matched pseudo-events; clustered and bootstrapped by event, firm, and date block; split the sample through time; and ran a null that simulated returns, redetected extreme events, and reran the study. Under that selection-preserving null, the empirical p-values were about 0.17 for five-day peer catch-up and 0.13 for convergence. So I would not claim universal or causal information diffusion. The result I defend is narrower: economic relationships identified short-horizon peer adjustment better than a fixed trailing-correlation rule in this sample.

## Likely quant interview questions

### Why semiconductor equities?

The sector has strong cross-firm economic links and enough heterogeneity to make the question interesting. Equipment makers, foundries, analog firms, and compute companies share cycles but do not have identical exposures. That gives a reason for one company's move to contain information about another without assuming the whole sector should react uniformly.

### Why economic peers?

The hypothesis is about economically related firms, so I wanted the peer map to reflect product markets and the value chain. A firm can share customers, input costs, or capex exposure with another firm even if their trailing daily correlations are unstable. The final result suggests that this distinction mattered, although the taxonomy is manually reconstructed and therefore imperfect.

### Why not use correlation peers from the start?

Correlation peers are a sensible statistical benchmark, not necessarily the right economic object. I started with economic peers because the motivating question concerned cross-firm information. After the unconditional result was weak, I added a fixed trailing-correlation comparison to test whether the economic taxonomy contributed anything beyond recent co-movement. I used only pre-event returns and compared the two definitions on identical events.

### How did you avoid lookahead bias?

Operational eligibility uses only data available through each date. Trailing volatility is shifted, correlation peers exclude the event date, and all peer portfolios are frozen at the event date. The focal stock is left out of its peer portfolio. The main caveat is that the current economic classification and reviewed universe were applied retrospectively, so the project is not fully survivorship-free or historically point in time.

### Why does extreme-event selection create mean-reversion bias?

Conditioning on an extreme noisy observation selects cases with unusually large transitory components. Even if returns have no real lead-lag mechanism, the next observation tends to be less extreme, which can look like gap closure. A confidence interval conditional on the observed events does not reproduce that selection step. That is why the strict null had to simulate returns, redetect events using the same rule, and then rebuild post-event outcomes.

### What did the null simulations test?

The selection-preserving null kept contemporaneous dependence and volatility regimes but disrupted the original lead-lag ordering. Each simulation reran detection and the event study. It asked whether the observed catch-up was unusually large relative to a world with similar dependence and event selection but without the original temporal sequence. At five days, catch-up was only at the 83rd percentile and convergence at the 87th, so the absolute results were not extreme under that null.

### Why can't you claim causality?

I observe daily prices, not the information channel. Common news, omitted factors, asynchronous market closes, liquidity, or classification error can produce the same pattern. I do not have clean news timestamps or a design that assigns information exposure independently of returns. The paired peer comparison is informative, but pairing does not turn an observational relationship into a causal one.

### What result surprised you?

The broad convergence story weakened more than I expected once I preserved event selection in the null. At the same time, the economic-minus-correlation comparison was cleaner than the absolute result. That changed the project from “do semiconductor prices converge?” to “which relationship map best describes short-horizon adjustment?”

### What happened with semiconductor equipment firms?

Equipment events had +0.80% mean five-day peer catch-up, which was interesting. But initiator reversal was −0.49%, meaning the initiating equipment stock continued in the shock direction on average. Total convergence was only +0.31% with a confidence interval crossing zero. I treat equipment as partial support for peer movement, not decisive evidence of convergence.

### Did larger shocks diffuse more?

No reliable nonlinear effect survived. I added one pre-specified squared standardized-shock term across three horizons and three outcomes. All nine confidence intervals included zero. I did not keep trying different breakpoints or nonlinear forms after that test failed.

### How stable was the result through time?

Absolute five-day catch-up was near zero in 2015–2018, negative in 2019–2021, and positive in 2022–2025; every period interval included zero. That makes the absolute effect look episodic and recent-sample dependent. The relative economic-peer comparison was more defensible than a claim of a time-stable level effect.

### What would you change with Bloomberg, CRSP, or similar data?

I would build an effective-dated security master with delisted firms and verified corporate actions, add market capitalization and a broad-market factor, and reconstruct historical classifications rather than applying a current taxonomy backward. I would also obtain timestamped earnings and news so I could distinguish common sector information from company-specific events. For international names, I would align sessions and currencies explicitly.

### Why didn't you build a trading strategy?

The research question was about price adjustment, and the absolute effect did not clear the strongest null tests. A backtest would add execution timing, costs, turnover, borrow, and data-revision issues before the mechanism was well identified. Building one at this stage would risk converting an uncertain event-study result into an inflated profitability claim.

### How would intraday data improve identification?

Intraday timestamps would show which stock moved first and whether a peer response occurred during overlapping trading hours, after a news release, or only when another market opened. That would reduce the ambiguity from non-synchronous daily closes. It would also let me estimate adjustment in minutes or hours and separate stale-price effects from a genuine delayed response.

### Why is the economic-minus-correlation comparison paired?

Both peer definitions are evaluated on the same initiator, date, direction, and complete-event sample. I take the within-event difference before bootstrapping. That controls for event-level conditions and makes the comparison more precise. It also means the initiator-return component cancels, so the convergence difference equals the peer-catch-up difference.

### What was the most important research decision?

Treating the weak baseline as information rather than as a reason to tune the event rule. I kept the baseline fixed, asked which part of the design was economically meaningful, formalized the peer-definition comparison, and then used nulls that repeated the selection process. That sequence produced a narrower but more credible conclusion.

## Candidate resume bullets

- Built a semiconductor-equity event study that decomposed post-shock convergence into peer catch-up and initiator reversal across 242 relative-price events.
- Found a **+0.61% five-day paired catch-up advantage** for economic versus trailing-correlation peers (95% bootstrap CI: +0.16% to +1.05%; n=131) and tested it against selection-preserving nulls.
- Designed point-in-time eligibility, leave-one-out peer portfolios, shifted-volatility event detection, and firm/date-block bootstrap checks for an international 2015–2025 daily panel.
- Documented a disciplined null result: absolute five-day economic-peer catch-up was not unusual under a selection-preserving simulation (empirical p≈0.17), limiting the claim to relative peer-definition evidence.
