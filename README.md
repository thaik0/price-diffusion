# Semiconductor Information Diffusion and Relative Price Discovery

This repository provides the reproducible research foundation for studying how
information is incorporated into semiconductor equity prices and how price
discovery propagates across economically related firms.

## Current status

Stage 2 defines and validates the four core research datasets. It deliberately
does **not** download market data, connect to external APIs, detect events,
calculate strategies, or perform statistical analysis.

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
| `security_master` | `security_id`, `ticker`, `company_name`, `exchange`, `sector`, `sub_industry` | `security_id` |
| `universe_membership` | `date`, `security_id`, `eligible` | `date`, `security_id` |
| `daily_panel` | `date`, `security_id`, `adjusted_close`, `close`, `volume`, `return` | `date`, `security_id` |
| `peer_membership` | `date`, `security_id`, `peer_id`, `weight`, `peer_definition` | `date`, `security_id`, `peer_id`, `peer_definition` |

Dates must be timezone-naive pandas datetimes normalized to midnight. Strings
are not silently parsed. Identifiers and metadata strings must be populated,
prices must be positive, volume must be non-negative, and numeric observations
must be finite. `return` is the sole nullable core field because the first
observation for a security may not have a prior price.

Universe and panel identifiers must resolve to the security master. Peer edges
are directed, may not point to the source security, and both endpoints must
resolve to the master. Within each `(date, security_id, peer_definition)` group,
non-negative weights must sum to one.

### Why point-in-time data matters

Universe eligibility and peer membership are dated facts rather than permanent
security attributes. Replacing historical membership with today's universe or
today's peer set would introduce survivorship and look-ahead bias: the research
would use information that was unavailable on the date being studied. Keeping
the date in each key forces downstream joins to state which historical snapshot
they use and allows changes in listings, eligibility, and economic relationships
to be represented without rewriting history.

### Future market-data boundary

Future source adapters will write immutable vendor responses to `data/raw/`,
standardize identifiers, dates, corporate-action adjustments, and units in
`data/interim/`, then construct these four frames. Before any frame is promoted
to `data/processed/` or consumed by event and strategy code, call:

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
