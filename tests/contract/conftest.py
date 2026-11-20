"""Repository contracts are static checks and need no external services."""

import pytest


@pytest.fixture(autouse=True)
def clean_database():
    yield
