# Stage 6: Relative returns

## Measurement objective

Raw stock returns mix firm-specific news with broad market repricing, industry
shocks, and movements shared by economically related firms. They are therefore
an unreliable standalone measure of firm-specific price discovery. Stage 6
creates several transparent measurements instead of prematurely selecting a
single event signal.

All returns are daily simple decimal returns. Every merge is keyed by date and
security identifier where relevant. Missing observations remain missing; they
are not interpreted as zero returns.

## Model progression

### 1. Raw peer-relative return

The baseline is the stock return minus the return of its dated peer portfolio.
Peer portfolios use the Stage 5 directed membership table, exclude the source
company, and support its equal weights. If a peer return is unavailable, that
peer is excluded and available weights are renormalized. If all peer returns
are unavailable, the peer and relative returns are missing.

This comparison matters because close economic peers can share customers,
products, supply constraints, and competitive exposures that a broad market
factor will not capture. Its main limitation is that peer selection can be
imperfect and a small peer group can be noisy. Contagion or information
diffusion into peers also makes the benchmark endogenous to the phenomenon of
interest.

### 2. Market-adjusted return

Market-adjusted return subtracts a configurable dated market return. It removes
one broad source of common movement and is easy to interpret. A unit loading is
implicitly assumed, however, so stocks with systematically high or low market
beta can remain misadjusted.

### 3. Semiconductor-adjusted return

Semiconductor-adjusted return subtracts a configurable dated industry-factor
return. It can remove sector-wide repricing missed by the market adjustment.
The result depends on factor construction and may remove economically meaningful
industry information. A factor containing the focal stock can also introduce a
mechanical self-inclusion effect, so future empirical work should consider a
leave-one-out industry factor.

### 4. Factor residual architecture

The rolling ordinary-least-squares interface supports configurable factor
columns, estimation-window length, and minimum observations. For each return
date it fits only complete observations strictly before that date, uses the
latest observations in the trailing window, and records the estimation start,
estimation end, observation count, intercept, and factor coefficients.

Point-in-time estimation is essential: fitting on the event date or later data
would allow future returns to influence the expected return and contaminate the
residual. The current implementation is intentionally modest. It does not
choose factors, winsorize data, model time-varying volatility, correct standard
errors, or decide whether coefficients are sufficiently stable.

### 5. Relative abnormal return

Relative abnormal return subtracts the leave-one-out peer portfolio's abnormal
return from the stock's abnormal return. This is the primary candidate for a
future event detector because it combines systematic adjustment with an
economically local comparison. If every stock and peer has the same unit-loaded
factor subtracted on a date, that common factor cancels algebraically; richer
factor models with security-specific loadings will make this layer more
distinctive.

## Interpretation limits

None of these measurements identifies an event, establishes causality, or
defines a tradable signal. Daily data cannot identify intraday leadership.
Non-synchronous trading, stale prices, corporate actions, changing peer sets,
missing returns, and factor measurement error can all affect results. Stage 6
stores measurements and estimation metadata so those choices can be tested
later without embedding thresholds or event-study logic in the return layer.
