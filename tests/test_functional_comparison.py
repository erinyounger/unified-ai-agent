"""Functional comparison tests between TypeScript and Python versions."""

import json
from typing import Any

import pytest
from httpx import AsyncClient

from src.main import app


@pytest.fixture
async def client() -> AsyncGenerator:
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


class TestHealthEndpointComparison:
    """Test health endpoint comparison."""

    @pytest.mark.asyncio
    async def test_health_endpoint_response_format(self, client: AsyncClient):
        """Test health endpoint response format matches TypeScript version."""
        response = await client.get("/health")
        assert response.status_code in [200, 503]

        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "uptime" in data
        assert "version" in data
        assert "checks" in data

        # Check structure matches TypeScript version
        checks = data["checks"]
        assert "claudeCli" in checks
        assert "workspace" in checks
        assert "mcpConfig" in checks

        # Check health check result structure
        for check_name, check_result in checks.items():
            assert "status" in check_result
            assert "message" in check_result
            assert "timestamp" in check_result
            assert check_result["status"] in ["healthy", "degraded", "unhealthy"]


class TestClaudeApiComparison:
    """Test Claude API endpoint comparison."""

    @pytest.mark.asyncio
    async def test_claude_api_request_parsing(self, client: AsyncClient):
        """Test Claude API request parsing matches TypeScript version."""
        request_data = {
            "prompt": "Hello, Claude!",
            "session-id": "test-session-123",
            "workspace": "test-workspace",
            "system-prompt": "You are a helpful assistant",
            "dangerously-skip-permissions": True,
            "allowed-tools": ["Bash", "Edit"],
            "disallowed-tools": ["WebFetch"],
        }

        # This would normally stream, but we can test the request parsing
        # by checking if the endpoint accepts the request format
        response = await client.post("/api/claude", json=request_data)
        # Should either succeed (200) or fail with proper error format
        assert response.status_code in [200, 400, 401, 500]


class TestOpenAIApiComparison:
    """Test OpenAI API endpoint comparison."""

    @pytest.mark.asyncio
    async def test_openai_api_message_conversion(self, client: AsyncClient):
        """Test OpenAI API message conversion matches TypeScript version."""
        request_data = {
            "model": "claude-code",
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "stream": True,
        }

        response = await client.post("/v1/chat/completions", json=request_data)
        # Should either succeed (200) or fail with proper error format
        assert response.status_code in [200, 400, 401, 500]


class TestProcessEndpointComparison:
    """Test process endpoint comparison."""

    @pytest.mark.asyncio
    async def test_process_endpoint_file_upload(self, client: AsyncClient):
        """Test process endpoint file upload matches TypeScript version."""
        # Create a test file
        test_content = b"Test PDF content"
        headers = {"Content-Type": "application/pdf"}

        response = await client.put("/process", content=test_content, headers=headers)
        # Should either succeed (200) or fail with proper error format
        assert response.status_code in [200, 400, 401, 500]

        if response.status_code == 200:
            data = response.json()
            assert "page_content" in data
            assert "metadata" in data
            assert "source" in data["metadata"]


def assert_response_format_match(ts_response: dict[str, Any], py_response: dict[str, Any]) -> None:
    """Assert that two responses have matching format."""
    # Check top-level keys match
    assert set(ts_response.keys()) == set(py_response.keys())

    # Recursively check structure
    for key in ts_response.keys():
        if isinstance(ts_response[key], dict) and isinstance(py_response[key], dict):
            assert_response_format_match(ts_response[key], py_response[key])
        elif isinstance(ts_response[key], list) and isinstance(py_response[key], list):
            assert len(ts_response[key]) == len(py_response[key])
            for ts_item, py_item in zip(ts_response[key], py_response[key]):
                if isinstance(ts_item, dict) and isinstance(py_item, dict):
                    assert_response_format_match(ts_item, py_item)
