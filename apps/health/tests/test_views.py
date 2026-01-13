"""
Tests for the health check endpoint.
"""

import pytest


@pytest.mark.django_db
class TestHealthCheck:
    def test_health_check_returns_200(self, api_client):
        """Health endpoint returns 200 when all services are up."""
        response = api_client.get("/api/health/")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_health_check_contains_database_status(self, api_client):
        """Response includes database connection status."""
        response = api_client.get("/api/health/")
        data = response.json()
        assert "database" in data["checks"]
        assert data["checks"]["database"]["status"] == "connected"
        assert "latency_ms" in data["checks"]["database"]

    def test_health_check_contains_redis_status(self, api_client):
        """Response includes Redis connection status."""
        response = api_client.get("/api/health/")
        data = response.json()
        assert "redis" in data["checks"]
        assert data["checks"]["redis"]["status"] == "connected"
        assert "latency_ms" in data["checks"]["redis"]
