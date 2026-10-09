# ruff: noqa: E402
import sys
from pathlib import Path

# Ensure src/ is on Python path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def db_roles(db):
    roles = {}
    for code, name in Role.ROLE_CHOICES:
        role, _ = Role.objects.get_or_create(code=code, defaults={"name": name})
        roles[code] = role
    return roles


@pytest.fixture
def super_admin_user(db, db_roles):
    return User.objects.create_superuser(
        email="admin@procuresphere.local",
        password="SuperAdminPassword123!",
        first_name="Super",
        last_name="Admin",
        role=db_roles[Role.SUPER_ADMIN],
    )


@pytest.fixture
def requester_user(db, db_roles):
    return User.objects.create_user(
        email="requester@procuresphere.local",
        password="RequesterPassword123!",
        first_name="John",
        last_name="Requester",
        role=db_roles[Role.REQUESTER],
    )
