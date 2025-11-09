"""Tests for health check endpoint."""

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health_endpoint():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code in [200, 503]  # 200 for healthy/degraded, 503 for unhealthy

    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "uptime" in data
    assert "version" in data
    assert "checks" in data

    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert isinstance(data["checks"], dict)


def test_root_endpoint():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Unified AI Agent"
    assert data["version"] == "0.7.1"
    assert data["status"] == "running"

