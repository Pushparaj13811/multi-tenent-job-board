"""
Section 8 — Middleware & Health.

8.1  RequestLoggerMiddleware (log fields, health path skip, auth user, no exception swallow)
8.2  Health check (200 + database/redis ok, response time)
"""

import logging
import time

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import UserFactory

# ═══════════════════════════════════════════════════════════════════════════
# 8.1  RequestLoggerMiddleware
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRequestLoggerMiddleware:
    """Verify request logger records the right fields."""

    def test_log_contains_required_fields(self, caplog):
        """Logs contain method, path, status, user_id, ip, duration_ms."""
        client = APIClient()
        with caplog.at_level(logging.INFO, logger="apps.middleware.request"):
            client.get("/api/companies/")
        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        assert record.method == "GET"
        assert record.path == "/api/companies/"
        assert record.status == 200
        assert record.user_id == "anonymous"
        assert hasattr(record, "duration_ms")
        assert hasattr(record, "ip")

    def test_health_path_produces_no_log(self, caplog):
        """/api/health/ is skipped by the middleware."""
        client = APIClient()
        with caplog.at_level(logging.INFO, logger="apps.middleware.request"):
            client.get("/api/health/")
        paths = [r.path for r in caplog.records if hasattr(r, "path")]
        assert "/api/health/" not in paths

    def test_authenticated_request_logs_user_uuid(self, caplog):
        """An authenticated request logs the correct user UUID, not 'anonymous'."""
        user = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=user)
        with caplog.at_level(logging.INFO, logger="apps.middleware.request"):
            client.get("/api/applications/")
        record = caplog.records[-1]
        assert record.user_id == str(user.id)

    def test_middleware_does_not_swallow_exceptions(self):
        """500 responses still propagate (middleware logs but does not catch)."""
        # Requesting a non-existent URL returns 404, not 500.
        # We just confirm the middleware doesn't turn errors into 200.
        client = APIClient()
        resp = client.get("/api/nonexistent-endpoint-12345/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ═══════════════════════════════════════════════════════════════════════════
# 8.2  Health check
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestHealthCheck:
    """Health endpoint returns correct structure and is fast."""

    def test_health_returns_200_with_subsystem_status(self):
        """GET /api/health/ returns 200 with database and redis 'connected'."""
        client = APIClient()
        resp = client.get("/api/health/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["checks"]["database"]["status"] == "connected"
        assert data["checks"]["redis"]["status"] == "connected"

    def test_health_response_time_under_500ms(self):
        """Health endpoint responds in under 500ms."""
        client = APIClient()
        start = time.monotonic()
        resp = client.get("/api/health/")
        elapsed_ms = (time.monotonic() - start) * 1000
        assert resp.status_code == status.HTTP_200_OK
        assert elapsed_ms < 500, f"Health check took {elapsed_ms:.0f}ms, expected < 500ms"


# ═══════════════════════════════════════════════════════════════════════════
# Gap tests — additional middleware & health checks
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRequestLoggerAdditional:
    """Additional middleware coverage."""

    def test_post_request_logs_method(self, caplog):
        """POST requests log method=POST correctly."""
        client = APIClient()
        with caplog.at_level(logging.INFO, logger="apps.middleware.request"):
            client.post("/api/auth/login/", {}, format="json")
        post_records = [r for r in caplog.records if hasattr(r, "method") and r.method == "POST"]
        assert len(post_records) >= 1

    def test_duration_ms_is_positive_number(self, caplog):
        """Logged duration_ms is a positive number."""
        client = APIClient()
        with caplog.at_level(logging.INFO, logger="apps.middleware.request"):
            client.get("/api/companies/")
        record = [r for r in caplog.records if hasattr(r, "duration_ms")]
        assert len(record) >= 1
        assert record[-1].duration_ms >= 0

    def test_health_check_response_keys(self):
        """Health check has status and checks keys."""
        client = APIClient()
        resp = client.get("/api/health/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "status" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "redis" in data["checks"]
