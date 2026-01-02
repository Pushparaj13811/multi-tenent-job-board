"""
Tests for the custom exception handler.
"""

from django.test import RequestFactory
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.views import APIView

from common.exceptions import custom_exception_handler


def _make_context():
    """Create a minimal context dict for the exception handler."""
    factory = RequestFactory()
    request = factory.get("/")
    return {"view": APIView(), "request": request}


class TestCustomExceptionHandler:
    def test_error_format_has_error_code_details_keys(self):
        """Response envelope contains error, code, and details keys."""
        exc = NotFound()
        context = _make_context()
        response = custom_exception_handler(exc, context)

        assert "error" in response.data
        assert "code" in response.data
        assert "details" in response.data
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_validation_error_formats_details(self):
        """Field-level validation errors are placed in details."""
        exc = ValidationError({"email": ["This field is required."]})
        context = _make_context()
        response = custom_exception_handler(exc, context)

        assert response.data["code"] == "validation_error"
        assert "email" in response.data["details"]
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_404_error_format(self):
        """404 errors follow the standard envelope format."""
        exc = NotFound("Not found.")
        context = _make_context()
        response = custom_exception_handler(exc, context)

        assert response.data["error"] == "Not found."
        assert response.data["code"] == "not_found"
        assert response.data["details"] == {}
