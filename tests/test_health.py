import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
def test_health_check_endpoint(api_client):
    url = reverse("health_check")
    response = api_client.get(url)
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "redis" in data


@pytest.mark.django_db
def test_api_health_check_endpoint(api_client):
    url = reverse("api_health_check")
    response = api_client.get(url)
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]
