import logging
import time

from django.db import connection
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)


def health_check(request):
    """
    GET /api/health/
    Returns 200 if all subsystems are reachable, 503 if any are down.
    No authentication required — called by infrastructure.
    """
    checks = {}
    healthy = True

    # ── Database check ──
    db_start = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = {
            "status": "connected",
            "latency_ms": round((time.monotonic() - db_start) * 1000, 1),
        }
    except Exception as e:
        logger.error("Health check: database unreachable: %s", e)
        checks["database"] = {"status": "unreachable", "error": str(e)}
        healthy = False

    # ── Redis check ──
    redis_start = time.monotonic()
    try:
        from django_redis import get_redis_connection

        redis_conn = get_redis_connection("default")
        redis_conn.ping()
        checks["redis"] = {
            "status": "connected",
            "latency_ms": round((time.monotonic() - redis_start) * 1000, 1),
        }
    except Exception as e:
        logger.error("Health check: Redis unreachable: %s", e)
        checks["redis"] = {"status": "unreachable", "error": str(e)}
        healthy = False

    response_data = {
        "status": "healthy" if healthy else "unhealthy",
        "timestamp": timezone.now().isoformat(),
        "checks": checks,
    }

    status_code = 200 if healthy else 503
    return JsonResponse(response_data, status=status_code)
