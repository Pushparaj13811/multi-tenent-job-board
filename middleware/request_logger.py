import logging
import time

logger = logging.getLogger("apps.middleware.request")


class RequestLoggerMiddleware:
    """Logs every request with method, path, status code, user, and duration."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        if request.path == "/api/health/":
            return response

        user_id = (
            str(request.user.id)
            if hasattr(request, "user") and request.user.is_authenticated
            else "anonymous"
        )

        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "user_id": user_id,
                "ip": request.META.get(
                    "HTTP_X_REAL_IP", request.META.get("REMOTE_ADDR")
                ),
            },
        )

        return response
