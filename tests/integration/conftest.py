import pytest

from core.config import Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Settings from the developer's environment (`make` exports .env), forced to ENV=test."""
    return Settings(env="test")
