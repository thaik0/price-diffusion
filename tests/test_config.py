from pathlib import Path

from price_diffusion.config import REQUIRED_SECTIONS, load_config
from price_diffusion.event_study import EventStudyConfig
from price_diffusion.statistical_inference import InferenceConfig
from price_diffusion.null_models import RobustnessConfig


def test_baseline_config_loads() -> None:
    config = load_config()

    assert REQUIRED_SECTIONS <= config.keys()
    assert config["random_seed"] == 42
    assert config["date_range"]["start"] <= config["date_range"]["end"]
    assert config["universe"]["min_history_days"] > 0
    assert config["universe"]["min_price"] >= 0
    assert config["universe"]["min_average_dollar_volume"] >= 0
    event = config["event_thresholds"]
    assert event["minimum_relative_move"] >= 0
    assert event["volatility_window"] >= event["minimum_history_requirement"]
    assert event["threshold_multiplier"] >= 0
    assert event["cooldown_period"] >= 0
    assert event["minimum_peer_count"] > 0
    study = config["event_study"]
    assert study["primary_horizons"] == [1, 5]
    assert study["descriptive_horizons"] == [3, 10]
    assert max(study["primary_horizons"] + study["descriptive_horizons"]) <= study["event_window"]["post_event_days"]
    parameters = EventStudyConfig.from_mapping(config)
    assert parameters.horizons == (1, 3, 5, 10)
    inference = InferenceConfig.from_mapping(config)
    assert inference.cluster_by == "firm"
    assert inference.confidence_level == 0.95
    robustness = RobustnessConfig.from_mapping(config)
    assert robustness.null_iterations == 1000
    assert robustness.date_block_length == 5


def test_config_can_load_from_explicit_path() -> None:
    path = Path("configs/baseline.yaml")

    assert load_config(path)["universe"]["name"] == "semiconductor_equities"
