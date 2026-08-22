"""Load version-controlled research configuration."""

from pathlib import Path
from typing import Any

import yaml

from price_diffusion.paths import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "baseline.yaml"

REQUIRED_SECTIONS = {
    "universe",
    "date_range",
    "event_thresholds",
    "event_study",
    "statistical_inference",
    "robustness",
    "peer_definition",
    "random_seed",
    "output_paths",
}


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load a YAML configuration and check its required top-level sections."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    if not isinstance(config, dict):
        raise ValueError(f"Configuration must be a mapping: {config_path}")

    missing = REQUIRED_SECTIONS.difference(config)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"Configuration is missing required sections: {missing_names}")

    return config
