from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from redis import Redis
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView


def health_check_view(request):
    """
    Health check endpoint returning DB and Redis status.
    """
    health_status = {
        "status": "healthy",
        "service": "ProcureSphere 360",
        "database": "unknown",
        "redis": "unknown",
    }

    # Check Database connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            health_status["database"] = "ok"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check Redis connection
    try:
        redis_client = Redis.from_url(settings.REDIS_URL, socket_timeout=2)
        if redis_client.ping():
            health_status["redis"] = "ok"
    except Exception as e:
        health_status["redis"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    http_status = 200 if health_status["status"] == "healthy" else 503
    return JsonResponse(health_status, status=http_status)


class HealthAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return health_check_view(request)


def home_view(request):
    """
    Dashboard / Landing page view.
    """
    return render(
        request,
        "pages/dashboard.html",
        {
            "project_name": "ProcureSphere 360",
            "version": "1.0.0-DRAFT",
        },
    )
