# Final research summary

## 1. Research question

I started with a simple question: when one semiconductor stock moves sharply away from related companies, who moves next?

There are three possible answers. Peers may catch up to the initiating stock, the initiator may reverse, or the original divergence may persist. Those paths have different interpretations. Peer catch-up is consistent with delayed adjustment elsewhere in the group. Initiator reversal looks more like a temporary relative-price dislocation or an overreaction in the initiating stock. No convergence suggests that the initial move was firm-specific, that peers had already incorporated the information, or that daily data are too coarse to identify the sequence.

The project is an observational event study, not a trading strategy. Its purpose is to measure the post-event path and test whether peer choice changes what can be learned from it. The final answer is narrower than the question that motivated the work: economically defined peers showed more short-horizon catch-up than peers chosen from trailing return correlations, but absolute economic-peer catch-up was not unusual enough under the strongest null models to establish universal information diffusion.

## 2. Economic motivation

Semiconductor companies are linked in ways that are economically concrete but not always visible in recent return correlations. Firms can serve the same end markets, sell complementary components into the same devices, buy from the same equipment suppliers, depend on the same foundries, or respond to the same capital-spending cycle. News about demand, utilization, pricing, process technology, or export restrictions can therefore matter beyond the company named in the original announcement.

At the same time, semiconductor equities are volatile and exposed to broad common factors. A large relative move can be noise, a corporate action, stale international pricing, an earnings surprise specific to one company, or a normal response to different factor loadings. A pattern that looks like diffusion after selecting extreme moves may also be mechanical mean reversion. I was therefore interested in two separate questions:

1. Is there absolute post-event catch-up or convergence after semiconductor relative-price shocks?
2. Do economic relationships identify the firms that adjust better than a statistical peer rule based on past return correlation?

The second question became the more informative one. It compares two peer maps on the same events, which removes the initiator's post-event return from the difference and focuses attention on which peer set moves.

## 3. Data and universe

The frozen estimation window runs from January 2015 through December 2025. I manually reviewed 54 semiconductor securities across the United States, Europe, Japan, Korea, Taiwan, mainland China, and Hong Kong. Thirty-six core securities were eligible at some point in the baseline sample. The remaining names stayed in the metadata as an extension group or as short-history cases rather than being silently dropped.

Prices and volumes came from Yahoo Finance. The data layer stores stable research identifiers separately from vendor tickers, keeps immutable raw downloads, and builds standardized daily panels from adjusted close. Eligibility is dated. Price, trading-history, and liquidity rules use observations available through each membership date, so a company cannot qualify using its future trading history.

That point-in-time treatment has an important boundary. The economic classification was reconstructed manually from a current reviewed snapshot and applied retrospectively. It is not a true historical industry database, and the company list is not survivorship-free. Acquired, failed, delisted, renamed, or previously public firms can be missing. “Point in time” in this project accurately describes the operational eligibility calculations, not the completeness of the security master or the historical taxonomy.

The baseline used a manually reviewed economic taxonomy. Economic peers were other eligible securities in the same narrow peer group, equal weighted and leave one out. The focal stock could never be its own peer. Peer identities and weights were frozen on the event date so post-event missingness or price behavior could not change the portfolio after the shock.

For the main comparison, I also built trailing-return-correlation peers. These used a 252-trading-day lookback, required at least 60 overlapping pre-event observations, excluded the event date, and were frozen at the event date. A broad semiconductor basket supplied a third comparison. The correlation rule was fixed before the formal test; it was not tuned to make economic peers look better.

## 4. Event construction

The signal begins with the initiating stock's daily return relative to its leave-one-out economic peers. I also subtract a same-day equal-weight semiconductor-sector return from the stock and peer components. Because the same unit-loaded factor appears on both sides, it cancels algebraically from the event-day stock-minus-peer divergence. It still affects the separately reported post-event component levels and is therefore documented in the run manifest.

An event occurs when the absolute relative move exceeds the larger of 5% and three times shifted trailing 60-observation volatility. The volatility estimate requires 60 prior valid observations and excludes the event-day return. The event also requires at least three eligible peers. Five-day cooldowns at the firm and peer-group level reduce immediate repeat detections. Known splits, mergers, abnormal price adjustments, and unresolved corporate-action cases are excluded by the fixed rule rather than repaired or winsorized after inspection.

The detector found 242 events: 140 positive and 102 negative. By subsector, there were 109 analog/mixed-signal events, 62 equipment events, 42 fabless-compute events, and 29 foundry events. Some other groups never met the minimum of three eligible leave-one-out peers. Outcome counts fall with the horizon because the frozen peer portfolio requires complete observations: 226 events at one day, 196 at three days, 173 at five days, and 114 at ten days.

For event direction \(s\), where \(s=+1\) after a positive shock and \(s=-1\) after a negative shock, I define:

- peer catch-up as \(s \times\) peer cumulative abnormal return;
- initiator reversal as \(-s \times\) initiator cumulative abnormal return; and
- convergence as peer catch-up plus initiator reversal.

Positive values always mean movement that closes the original gap. Outcomes begin at t+1; day 0 selects the event and is not counted as post-event adjustment.

## 5. Baseline result

The baseline was closer to a practical null than a strong result. Mean one-day convergence was +0.54% with a 95% firm-clustered interval from −0.16% to +1.24%. At five days, mean convergence was +0.38% with an interval from −0.31% to +1.06%. The five-day estimate decomposed into +0.22% peer catch-up and +0.16% initiator reversal. Both component intervals included zero, both component medians were slightly negative, and only 51.4% of five-day convergence outcomes were positive.

By ten days, mean convergence was −0.15%. Peer catch-up remained mildly positive, but initiator reversal had changed sign, meaning that initiators continued in the original shock direction on average. The short-horizon point estimates were therefore neither precise nor persistent.

This was an important diagnosis. If I had stopped after the event-study mean, the story would have been easy to overstate: “large semiconductor shocks are followed by convergence.” The distribution did not support that wording. Confidence intervals were wide, medians were close to zero, and the result weakened with the horizon. The baseline said that some events may contain delayed adjustment, not that diffusion is a general property of the sample.

## 6. Research diagnosis

After the weak unconditional result, I looked at pre-declared sources of heterogeneity rather than searching for a new event threshold. The questions were practical: did certain subsectors behave differently, did prior sector conditions matter, did larger standardized shocks behave nonlinearly, and did the economic peer map contain information that a return-based map missed?

The exploratory work pointed most clearly to equipment events and peer definition. Equipment firms sit near a common semiconductor capital-spending channel, so peer adjustment had an economic interpretation. Economic peers also appeared to catch up more than correlation-selected or broad peers. Lower prior semiconductor momentum was associated with stronger convergence in some views. A plot of outcome against standardized shock size suggested possible curvature.

These patterns were treated as leads, not conclusions. I fixed four mechanism tests: an equipment indicator in controlled regressions and a disclosed equipment decomposition; a same-event comparison of economic, correlation, and broad peers; continuous lagged sector-momentum regressions plus a zero-return sign split; and one squared-shock extension. No additional nonlinear forms, breakpoints, or subgroup rankings were searched after seeing the formal results.

## 7. Formal mechanism tests

### Economic peers versus correlation peers

This was the strongest finding. On the common five-day sample of 131 events, mean direction-normalized peer catch-up was +0.34% for economic peers, −0.27% for trailing-correlation peers, and +0.01% for the broad semiconductor basket. The paired economic-minus-correlation catch-up difference was **+0.61%**, with a 10,000-replication paired-bootstrap 95% interval of **+0.16% to +1.05%**.

Because the initiating stock's return is identical across peer definitions within an event, the convergence difference is also +0.61%. That does not mean the initiator behavior supports diffusion; it means the peer-definition comparison cleanly cancels it.

The paired difference was +0.53% at one day (95% CI +0.25% to +0.81%; n=208). At ten days it remained positive at +0.73%, but the interval ran from −0.19% to +1.69% and the common sample had fallen to 62. Specification work later found the advantage positive with intervals above zero at one, three, and five days, then imprecise at ten days. The defensible statement is short- and medium-horizon outperformance of the fixed correlation-peer alternative, not a permanent effect.

### Equipment events

Equipment events were interesting but not decisive. Among 47 complete five-day equipment events, mean peer catch-up was +0.80% (95% CI +0.28% to +1.33%). Mean initiator reversal was −0.49% (95% CI −1.40% to +0.42%), so mean convergence was only +0.31% (95% CI −0.60% to +1.22%).

The negative reversal term means equipment initiators tended to continue in the original direction, offsetting peers that moved the same way. Non-equipment events had approximately zero five-day peer catch-up and +0.40% convergence. A controlled equipment coefficient did not show stronger five-day convergence. The equipment result is therefore evidence about one component, not proof of a stronger total adjustment mechanism.

### Prior sector momentum

Lower prior semiconductor momentum received suggestive, horizon-sensitive support. At five days, events following weak or nonpositive one-month sector returns averaged +0.92% convergence, compared with −0.02% after positive momentum. The controlled one-month momentum coefficient was −0.033 per unit prior return, but its 95% interval was wide at −0.126 to +0.060. The three-month coefficient was also negative and imprecise.

At one day, both one- and three-month momentum coefficients had intervals below zero. Five- and ten-day directions were generally consistent but uncertain. This is a plausible state dependence, not a stable law. It deserves the label “suggestive,” especially because the sign split is descriptive and the magnitude changes by horizon.

### Shock magnitude

The nonlinear shock hypothesis failed. The single pre-specified extension added squared standardized shock magnitude to the mechanism regressions at one, five, and ten days for peer CAR, convergence, and initiator reversal. All nine confidence intervals included zero. At five days, the convergence squared-shock coefficient was about +0.036 percentage points per squared shock unit, with an interval from roughly −0.062 to +0.134 percentage points.

The exploratory curve did not survive the formal test. I retained that failure because it is part of the research result, not a reason to try another polynomial or search for a threshold.

## 8. Robustness and null models

I used several checks because extreme-event studies are unusually vulnerable to selection and dependence.

One-at-a-time specification changes covered event thresholds from two to four trailing standard deviations, horizons from one to twenty days, raw versus semiconductor-adjusted returns, the core versus extension universe, and removal of questionable firms. Market-cap peer weights were unavailable because the frozen data have no market capitalization. A true broad-market adjustment was also unavailable because the frozen baseline has no broad-market return series. Those missing checks are limitations, not results.

Absolute five-day economic-peer catch-up stayed mildly positive across nearby event thresholds, but conventional intervals included zero. The economic-minus-correlation advantage was much more stable through five days. At twenty days, common-sample attrition left too little evidence for a useful conclusion.

Random-peer and matched pseudo-event placebos had five-day peer-catch-up means near zero. Their intervals nevertheless overlapped the observed +0.22%, so the directional comparison was encouraging but not conclusive. These placebos separately test whether the chosen peers and event dates matter; neither fully reproduces the process that selected an extreme relative move.

The main null was selection preserving. It retained contemporaneous dependence and volatility regimes, disrupted the original lead-lag ordering, redetected events, and reran the event study in each simulation. At five days, observed peer catch-up sat at the 83rd null percentile, with an upper-tail empirical p-value of about 0.17. Observed convergence sat at the 87th percentile, with p about 0.13. The estimates were above the average null outcome, but the null was not rejected at conventional levels. This materially weakened the claim of absolute diffusion.

Dependence also matters. The 173 five-day events reduced to 20 initiator clusters and 138 unique event dates; roughly 88% had overlapping post-event windows and 35% occurred on dates with multiple sample events. Event, firm, and five-date-block bootstrap intervals for absolute peer catch-up all included zero.

Time stability was imperfect. Five-day peer catch-up was about +0.01% in 2015–2018, −0.35% in 2019–2021, and +0.45% in 2022–2025. Every period interval included zero. The estimate was strongest in the recent subsample rather than uniform across the decade.

## 9. Final interpretation

The most defensible conclusion is comparative:

> Economically defined semiconductor peers exhibited stronger short-horizon peer catch-up than peers selected from trailing return correlations.

The five-day paired advantage was +0.61%, with a bootstrap interval from +0.16% to +1.05% on 131 common events. The one-day comparison pointed in the same direction, and reasonable short-horizon specification changes did not erase it. Economic relationships appear to carry incremental information about which firms adjust after a relative shock beyond what was captured by the fixed trailing-correlation rule.

The evidence does not establish a universal information-diffusion effect. Absolute economic-peer catch-up was modest, dependent on the sample period, and not convincingly distinguishable from the selection-preserving null. Equipment peers moved, but initiator continuation weakened total convergence. Sector momentum was suggestive rather than stable. Nonlinear shock magnitude was not supported.

I interpret the evidence as consistent with limited, episodic cross-firm adjustment. I cannot tell from daily prices whether the mechanism is slow information transmission, asynchronous international closes, common news arriving at different times, liquidity differences, or an omitted factor. I also cannot infer a profitable trade after costs and real-time implementation constraints. The project found a useful relational result and a reason to be skeptical of the broader anomaly story.

## 10. Limitations

- **Data quality.** Yahoo adjusted prices are revisable, and the project does not have institutional corporate-action, delisting-return, or identifier histories.
- **Historical universe.** The current reviewed company list is not survivorship-free. The manual taxonomy was applied retrospectively rather than reconstructed from dated source documents.
- **International timing.** Local-market closing times, holidays, currencies, and information sets differ. Daily observations cannot establish who could observe whose move first.
- **Event labels.** Earnings and news flags are incomplete. Common sector news cannot be cleanly separated from firm-specific information.
- **Factor model.** The frozen baseline does not include a broad-market benchmark. The equal-weight semiconductor factor includes the focal stock, although it cancels from the event-day relative signal.
- **Sample size and dependence.** Long-horizon and subsector samples are small. Repeated firms, simultaneous events, and overlapping outcome windows reduce effective independence.
- **Identification.** This is observational evidence. It cannot establish causal information transmission or separate economic linkage from omitted common exposures.
- **Implementation.** Daily closes, revised vendor data, international timing, turnover, costs, and borrow constraints were not modeled. No trading claim follows from the event-study estimates.

## 11. What I would investigate next

The next step would be better identification, not more specification searching. With Bloomberg, Refinitiv, CRSP/Compustat, or exchange data, I would first rebuild the universe with effective-dated identifiers, delisted firms, verified corporate actions, market capitalization, and a broad-market benchmark. I would time-stamp earnings, guidance, customer announcements, export-control news, and industry reports so events could be separated into common and firm-specific information.

Intraday quotes and trades would be especially valuable. They would let me align markets in UTC, distinguish stale closes from delayed adjustment, observe which security moved first, and measure adjustment in hours rather than calendar dates. A natural design would compare overlapping trading hours with overnight or non-overlapping market pairs while keeping the economic-versus-correlation peer contrast fixed.

I would also replace the retrospective taxonomy with dated economic relationships where possible: customer-supplier links, foundry exposure, product segments, and equipment spending. That would test whether the result comes from real transmission channels or simply from a better static industry grouping.

I would not begin by tuning thresholds or building a trading backtest. The current evidence does not justify that jump. The useful next question is whether better timing and better relationship data can turn the comparative peer result into a more clearly identified economic mechanism.
