import pytest

from price_diffusion.synthetic import SyntheticResearchData, make_synthetic_research_data


@pytest.fixture
def synthetic_data() -> SyntheticResearchData:
    return make_synthetic_research_data()

