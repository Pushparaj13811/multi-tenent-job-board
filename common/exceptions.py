from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler that returns a consistent error envelope:
    {
        "error": "Human-readable error message.",
        "code": "machine_readable_code",
        "details": {}
    }
    """
    response = exception_handler(exc, context)

    if response is None:
        return response

    # Build the standard envelope
    error_data = {
        "error": "",
        "code": "",
        "details": {},
    }

    if isinstance(response.data, dict):
        # DRF validation errors come as {"field": ["error msg"]}
        detail = response.data.get("detail", None)
        if detail:
            # Single error (e.g., 404, 403, 401)
            error_data["error"] = str(detail)
            error_data["code"] = getattr(detail, "code", "error") if hasattr(detail, "code") else _get_code(exc)
        else:
            # Field-level validation errors
            error_data["error"] = "Validation error."
            error_data["code"] = "validation_error"
            error_data["details"] = response.data
    elif isinstance(response.data, list):
        error_data["error"] = str(response.data[0]) if response.data else "An error occurred."
        error_data["code"] = _get_code(exc)
    else:
        error_data["error"] = str(response.data)
        error_data["code"] = _get_code(exc)

    response.data = error_data
    return response


def _get_code(exc):
    """Extract error code from exception."""
    if isinstance(exc, APIException):
        return exc.default_code
    return "error"
