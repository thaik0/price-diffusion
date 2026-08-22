# Semiconductor Information Diffusion and Relative Price Discovery

This repository provides the reproducible research foundation for studying how
information is incorporated into semiconductor equity prices and how price
discovery propagates across economically related firms.

## Current status

Stage 10 adds random-peer and matched pseudo-event placebos, a causal
regime-stratified selection-preserving return null, reversed-time falsification,
and firm/date block bootstraps. Every experiment reuses the pre-specified Stage 7
event detector and Stage 8 outcome engine rather than changing thresholds or
horizons after observing results. See `research_notes/stage_10_null_models.md`
for assumptions, interpretation, and limitations.

## Design philosophy

- **Research correctness:** assumptions and experiment parameters live in
  version-controlled configuration rather than being hidden in notebooks.
- **Reproducibility:** experiments should start from an explicit configuration
  and random seed, and write artifacts to stable output directories.
- **Simplicity:** use small functions and the standard scientific Python stack;
  add abstractions only when repeated research work justifies them.
- **Separation of concerns:** reusable and testable logic belongs in `src/`,
  while notebooks are for exploration, diagnostics, and presentation.
- **Data provenance:** `data/raw/` is reserved for immutable source data;
  transformations should progress through `interim/` to `processed/`.

The values in `configs/baseline.yaml` are placeholders for the first empirical
design. They are not validated research choices and should be revised before an
experiment is interpreted.

## Core data contracts

Contracts are defined in `src/price_diffusion/data_contracts.py`; fail-closed,
non-mutating validation is implemented in `src/price_diffusion/validation.py`.
Extra source columns may be retained, but every required field must satisfy its
logical type, nullability rule, and dataset key.

| Dataset | Required fields | Primary key |
| --- | --- | --- |
| `security_master` | `security_id`, `ticker`, `company_name`, `exchange`, `security_type`, `sector`, `sub_industry` | `security_id` |
| `semiconductor_classification` | `security_id`, `ticker`, `company_name`, `subsector`, `classification_notes` | `security_id` |
| `peer_classification` | `security_id`, `subsector`, `peer_group`, `classification_notes` | `security_id` |
| `universe_membership` | `date`, `security_id`, `eligible`, `exclusion_reason` | `date`, `security_id` |
| `daily_panel` | `date`, `security_id`, `adjusted_close`, `close`, `volume`, `return` | `date`, `security_id` |
| `peer_membership` | `date`, `security_id`, `peer_id`, `weight`, `peer_definition` | `date`, `security_id`, `peer_id`, `peer_definition` |
| `relative_returns` | `date`, `security_id`, `peer_definition`, `stock_return`, `peer_return`, `relative_return`, `market_adjusted_return`, `semiconductor_adjusted_return` | `date`, `security_id`, `peer_definition` |
| `events` | `event_id`, `date`, `security_id`, `direction`, `relative_return`, `relative_volatility`, `threshold_used`, `peer_definition`, `subsector`, metadata flags | `event_id` |

### Event detection

Stage 7 applies `abs(relative_abnormal_return) > max(minimum_relative_move,
threshold_multiplier * trailing_volatility)`. The rolling volatility input is
shifted before estimation, so neither the event-date shock nor future returns
can affect its threshold. Event parameters live under `event_thresholds` in the
baseline configuration.

```python
from price_diffusion.config import load_config
from price_diffusion.events import detect_events

events = detect_events(relative_abnormal_returns, load_config())
```

The input supplies dated `peer_count`, `peer_group`, `subsector`, and an explicit
`corporate_action_type` classification alongside the Stage 6 relative abnormal
return. Optional earnings and news flags are metadata only. See
`research_notes/stage_07_event_detection.md` for the design rationale and
limitations.

### Relative-return measurement

Stage 6 joins returns to peer membership by date, excludes the focal company,
and renormalizes weights over peers with observed returns. Configurable market
and semiconductor factor series are also joined by date; absent factor dates
remain missing rather than becoming zero returns. The rolling factor interface
uses observations strictly before each prediction date and retains its fitted
coefficients and estimation boundaries.

```python
from price_diffusion.returns import build_relative_returns

relative_returns = build_relative_returns(
    daily_panel,
    peer_membership,
    market_returns,
    semiconductor_factor_returns,
    market_return_column="market_return",
    semiconductor_return_column="semiconductor_return",
)
```

Relative abnormal returns are exposed as a separate transformation so the
researcher can explicitly choose which abnormal-return model is being compared.
See `research_notes/stage_06_relative_returns.md` for assumptions and limits.

Dates must be timezone-naive pandas datetimes normalized to midnight. Strings
are not silently parsed. Identifiers and metadata strings must be populated,
prices must be positive, volume must be non-negative, and numeric observations
must be finite. `return` is the sole nullable core field because the first
observation for a security may not have a prior price.

Universe and panel identifiers must resolve to the security master. Peer edges
are directed, may not point to the source security, and both endpoints must
resolve to the master. Within each `(date, security_id, peer_definition)` group,
non-negative weights must sum to one.

### Universe construction

The Stage 4 builder evaluates every security-master identifier on every market
date, including unavailable securities, and records all failed eligibility
rules. Thresholds and allowed exchanges and instrument types are stored under
`universe` in `configs/baseline.yaml`. History and average dollar volume use
only observations through the membership date.

```python
from price_diffusion.config import load_config
from price_diffusion.universe import build_universe_membership

universe_membership = build_universe_membership(
    security_master,
    daily_panel,
    semiconductor_classification,
    load_config(),
)
```

The bundled classification is a current seed snapshot for human review. Its
configured as-of date blocks silent historical reuse by default. A retrospective
override must be explicit and does not make the data survivorship-free. See
`research_notes/stage_04_universe_construction.md` for the design and limitations.

### Peer construction

Peer construction first restricts both relationship endpoints to securities
eligible on the same date. `economic_subsector_peers` then matches the narrower
reviewed `peer_group` label and equal-weights the remaining non-self peers.
`broad_semiconductor_peers` includes every other eligible semiconductor.

```python
from price_diffusion.peers import (
    BROAD_SEMICONDUCTOR_PEERS,
    ECONOMIC_SUBSECTOR_PEERS,
    build_peer_membership,
)

peer_membership = build_peer_membership(
    security_master,
    semiconductor_classification,
    universe_membership,
    peer_classification,
    definitions=(ECONOMIC_SUBSECTOR_PEERS, BROAD_SEMICONDUCTOR_PEERS),
)
```

The output is directed and dated, and weights sum to one within each non-empty
source/date/definition portfolio. The architecture reserves a trailing-return
similarity definition, but Stage 5 intentionally does not implement it. See
`research_notes/stage_05_peer_construction.md` for rationale and limitations.

### Why point-in-time data matters

Universe eligibility and peer membership are dated facts rather than permanent
security attributes. Replacing historical membership with today's universe or
today's peer set would introduce survivorship and look-ahead bias: the research
would use information that was unavailable on the date being studied. Keeping
the date in each key forces downstream joins to state which historical snapshot
they use and allows changes in listings, eligibility, and economic relationships
to be represented without rewriting history.

### Market-data boundary

Source adapters write immutable vendor responses to `data/raw/`; the Stage 3
pipeline standardizes identifiers and dates, calculates adjusted-close simple
returns, and validates the result before it is promoted to `data/processed/`.
CSV is the first adapter, behind an interface intended for future API or vendor
implementations. For validation of all four research frames, call:

```python
from price_diffusion.validation import validate_research_data

validate_research_data(
    security_master=security_master,
    universe_membership=universe_membership,
    daily_panel=daily_panel,
    peer_membership=peer_membership,
)
```

Validation is a gate, not a repair step. An adapter must explicitly resolve a
bad type, missing identifier, duplicate key, invalid value, or malformed peer
group and record the transformation in provenance metadata. Deterministic
synthetic examples are available from
`price_diffusion.synthetic.make_synthetic_research_data` for adapter and
pipeline tests that must not use external data.

Construct a daily panel from CSV with:

```python
from price_diffusion.market_data import CSVMarketDataSource, ingest_market_data

source = CSVMarketDataSource(
    "data/raw/vendor_prices.csv",
    column_map={"Symbol": "ticker", "Adj Close": "adjusted_close"},
)
daily_panel = ingest_market_data(source, security_master)
```

Raw canonical columns are `date`, `ticker`, `adjusted_close`, `close`, and
`volume`. Missing rows remain gaps: returns compare each security's consecutive
available observations and do not invent calendar-day records.

## Setup

Create and activate a virtual environment, then install the project in editable
mode with its test dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the tests from the repository root:

```bash
python -m pytest
```

Load the baseline configuration from Python:

```python
from price_diffusion.config import load_config

config = load_config()
seed = config["random_seed"]
```

## Notebook workflow

Notebooks should import reusable code from the installed `price_diffusion`
package. They should not alter `sys.path`, duplicate source functions, or become
the only record of a transformation. Once exploratory logic is stable, move it
to `src/price_diffusion/`, add tests, and call it from the notebook.

Run notebooks from the repository root so relative paths agree with the
version-controlled configuration. Treat notebook outputs as disposable unless
an artifact is intentionally written to `outputs/figures/`, `outputs/tables/`,
or `outputs/diagnostics/`.

## Descriptive event study

Stage 8 freezes each event's dated peer membership and weights, builds a long
event-time panel, and measures t+1 through t+h initiator CAR, peer CAR, peer
catch-up, initiator reversal, and their total convergence. The selected return
column and its specification label are explicit, and incomplete horizons remain
in the output with a reason.

```python
from price_diffusion.event_study import run_event_study

result = run_event_study(
    events,
    abnormal_returns,
    peer_membership,
    config,
    return_column="semiconductor_adjusted_return",
    return_specification="semiconductor_adjusted_return",
)
event_panel = result.event_panel
event_outcomes = result.outcomes
diagnostics = result.diagnostics
```

These outputs are descriptive only. Stage 8 does not perform significance
tests or support causal claims about information diffusion.

## Statistical inference

Stage 9 measures uncertainty around detected-event outcomes without changing
event definitions or simulating selection-preserving nulls. It reports complete
distributions for convergence, peer catch-up, and initiator reversal by horizon,
return specification, peer definition, and shock direction. Analytical
Student-t and reproducible percentile-bootstrap confidence intervals are
available.

Convergence uses a one-sided test against a positive mean; peer catch-up and
initiator reversal use two-sided tests against zero. The default covariance
estimator clusters by initiating firm. Event-date and analytical two-way
clustering are also supported. These are conditional-on-selection associations,
not causal evidence.

Conditional peer-CAR and initiator-CAR regressions use a fixed, parsimonious
design: signed initial shock, direction, event-date volume and market
capitalization, subsector, two volatility regimes, and a simultaneous-event
flag. Only named contemporaneous fields enter the model.

```python
from price_diffusion.statistical_inference import InferenceConfig, run_statistical_inference

inference = run_statistical_inference(
    result.outcomes,
    event_panel=result.event_panel,
    event_characteristics=event_characteristics,
    config=InferenceConfig(cluster_by="firm"),
    output_directory="outputs/tables",
)
```

The call writes summary, distribution, hypothesis, attrition, regression, and
event-time CSV tables under `outputs/tables/`.

## Repository layout

```text
configs/                 Version-controlled experiment settings
data/raw/                Immutable source data (not committed)
data/interim/            Intermediate transformations (not committed)
data/processed/          Analysis-ready datasets (not committed)
metadata/                Data dictionaries and provenance records
notebooks/               Exploration and research communication
src/price_diffusion/     Reusable research code
tests/                   Automated checks
outputs/figures/         Generated figures
outputs/tables/          Generated tables
outputs/diagnostics/     Generated diagnostics
```
