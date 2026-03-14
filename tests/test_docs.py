"""Tests for OpenAPI schema and Swagger UI endpoints."""

import pytest
from rest_framework import status


@pytest.fixture
def schema(api_client):
    """Fetch and return the parsed OpenAPI schema."""
    response = api_client.get("/api/schema/", HTTP_ACCEPT="application/json")
    assert response.status_code == status.HTTP_200_OK
    return response.json()


@pytest.mark.django_db
class TestOpenAPIDocs:
    def test_schema_endpoint_returns_200(self, api_client):
        response = api_client.get("/api/schema/")
        assert response.status_code == status.HTTP_200_OK

    def test_schema_is_valid_openapi(self, schema):
        assert schema["openapi"].startswith("3.")
        assert schema["info"]["title"] == "HireFlow API"
        assert schema["info"]["version"] == "1.0.0"
        assert "paths" in schema

    def test_swagger_ui_returns_200(self, api_client):
        response = api_client.get("/api/docs/")
        assert response.status_code == status.HTTP_200_OK

    def test_schema_contains_auth_endpoints(self, schema):
        paths = schema["paths"]
        assert "/api/auth/register/" in paths
        assert "/api/auth/login/" in paths

    def test_schema_contains_job_endpoints(self, schema):
        paths = schema["paths"]
        assert "/api/jobs/" in paths

    def test_schema_contains_application_endpoints(self, schema):
        paths = schema["paths"]
        assert "/api/applications/" in paths
