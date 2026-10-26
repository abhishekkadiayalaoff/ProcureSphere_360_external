import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_endpoint(client):
    url = reverse("health")
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.django_db
def test_readyz_endpoint(client):
    url = reverse("readyz")
    response = client.get(url)
    # Status code will be 200 if db and redis are connected, or 503 if redis is down
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "redis" in data
