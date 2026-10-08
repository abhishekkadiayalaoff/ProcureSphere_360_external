from django.urls import path

from .views import HealthAPIView, health_check_view, home_view

urlpatterns = [
    path("", home_view, name="home"),
    path("health/", health_check_view, name="health_check"),
    path("api/v1/health/", HealthAPIView.as_view(), name="api_health_check"),
]
