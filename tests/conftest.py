"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
async def async_client() -> AsyncGenerator:
    """Create an async test client."""
    from httpx import AsyncClient

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
