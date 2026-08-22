from pathlib import Path

from price_diffusion.config import load_config
from price_diffusion.paths import PROJECT_ROOT


def test_required_directories_exist() -> None:
    relative_directories = (
        "configs",
        "data/raw",
        "data/interim",
        "data/processed",
        "metadata",
        "notebooks",
        "src/price_diffusion",
        "tests",
        "outputs/figures",
        "outputs/tables",
        "outputs/diagnostics",
    )

    for relative_directory in relative_directories:
        assert (PROJECT_ROOT / relative_directory).is_dir(), relative_directory


def test_configured_output_directories_exist() -> None:
    output_paths = load_config()["output_paths"]

    for relative_path in output_paths.values():
        assert (PROJECT_ROOT / Path(relative_path)).is_dir(), relative_path
