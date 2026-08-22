# Semiconductor Information Diffusion and Relative Price Discovery

This repository provides the reproducible research foundation for studying how
information is incorporated into semiconductor equity prices and how price
discovery propagates across economically related firms.

## Current status

Stage 1 establishes the project layout, Python package, baseline configuration,
and infrastructure tests. It deliberately does **not** implement data ingestion,
event detection, trading strategies, statistical analysis, or machine learning.

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
