from pathlib import Path

from price_diffusion.config import REQUIRED_SECTIONS, load_config


def test_baseline_config_loads() -> None:
    config = load_config()

    assert REQUIRED_SECTIONS <= config.keys()
    assert config["random_seed"] == 42
    assert config["date_range"]["start"] <= config["date_range"]["end"]
    assert config["universe"]["min_history_days"] > 0
    assert config["universe"]["min_price"] >= 0
    assert config["universe"]["min_average_dollar_volume"] >= 0


def test_config_can_load_from_explicit_path() -> None:
    path = Path("configs/baseline.yaml")

    assert load_config(path)["universe"]["name"] == "semiconductor_equities"
