"""Copy beside ProcureSphere's root urls.py (usually src/config/urls.py).

Register health and readyz in that URLconf. See SETUP.md for integration.
Uses Django's default database and settings.REDIS_URL.
"""

import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, InterfaceError, connections, transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@transaction.non_atomic_requests
@never_cache
@require_safe
def health(request):
    """Liveness: do not query the database, Redis, sessions, or users."""
    return JsonResponse({"status": "healthy"})


def _database_status():
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        return "connected" if row == (1,) else "disconnected"
    except (DatabaseError, InterfaceError, ImproperlyConfigured) as exc:
        # Log the error class only; connection strings may contain credentials.
        logger.warning("Database readiness failed (%s)", type(exc).__name__)
        return "disconnected"


def _redis_status():
    redis_url = getattr(settings, "REDIS_URL", "")
    if not redis_url:
        return "not_configured"

    # Import here so a missing Redis package doesn't break /health.
    try:
        from redis import Redis, RedisError
        from redis.backoff import NoBackoff
        from redis.retry import Retry
    except ImportError:
        logger.warning("Redis readiness failed: install the redis package")
        return "not_configured"

    try:
        with Redis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry=Retry(NoBackoff(), 0),
        ) as client:
            return "connected" if client.ping() else "disconnected"
    except (RedisError, OSError, ValueError, TypeError) as exc:
        logger.warning("Redis readiness failed (%s)", type(exc).__name__)
        return "disconnected"


@transaction.non_atomic_requests
@never_cache
@require_safe
def readyz(request):
    """Readiness: always report both checks, including after a failure."""
    database = _database_status()
    redis = _redis_status()
    ready = database == "connected" and redis == "connected"
    return JsonResponse(
        {
            "status": "ready" if ready else "not_ready",
            "database": database,
            "redis": redis,
        },
        status=200 if ready else 503,
    )


# Django 5.1+ LoginRequiredMiddleware recognizes these attributes. On older
# Django versions they are harmless. Custom login middleware needs its own
# exact-path exemptions, as described in SETUP.md.
health.login_required = False
readyz.login_required = False  # ProcureSphere 360: health and readiness endpoints
