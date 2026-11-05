import pytest
from django.urls import reverse
from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.organization.models import Organization, Location
from apps.organization.services import (
    create_location_service,
    update_location_service,
    delete_location_service,
)


@pytest.fixture
def location_test_data(db):
    org = Organization.objects.create(name="HPE India", code="HPE-IN", is_active=True)
    role_sa, _ = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})
    role_req, _ = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})

    admin = User.objects.create_user(
        email="admin@hpe-in.com",
        password="Password123!",
        role=role_sa,
        organization=org,
        is_staff=True,
    )
    requester = User.objects.create_user(
        email="requester@hpe-in.com",
        password="Password123!",
        role=role_req,
        organization=org,
    )
    loc = Location.objects.create(
        organization=org,
        code="LOC-HYD",
        name="Hyderabad Campus",
        city="Hyderabad",
        country="India",
        created_by=admin,
    )
    return {"org": org, "admin": admin, "requester": requester, "location": loc}


@pytest.mark.django_db
def test_location_services(location_test_data):
    data = location_test_data
    org = data["org"]
    admin = data["admin"]

    # 1. Create Location Service
    loc2 = create_location_service(
        organization=org,
        name="Operations Chennai",
        code="LOC-CHN",
        city="Chennai",
        country="India",
        address="Taramani Tech Park",
        actor=admin,
    )
    assert loc2.code == "LOC-CHN"
    assert loc2.name == "Operations Chennai"
    assert loc2.city == "Chennai"
    assert AuditLog.objects.filter(target_model="Location", target_object_id=str(loc2.id), action=AuditLog.ACTION_CREATE).exists()

    # 2. Update Location Service
    loc2 = update_location_service(
        location=loc2,
        name="Operations Chennai Tech Center",
        code="LOC-CHN",
        city="Chennai",
        country="India",
        address="OMR IT Zone",
        is_active=True,
        actor=admin,
    )
    assert loc2.name == "Operations Chennai Tech Center"
    assert AuditLog.objects.filter(target_model="Location", target_object_id=str(loc2.id), action=AuditLog.ACTION_UPDATE).exists()

    # 3. Delete Location Service
    loc_id = loc2.id
    success, msg = delete_location_service(location=loc2, actor=admin)
    assert success is True
    assert not Location.objects.filter(id=loc_id).exists()
    assert AuditLog.objects.filter(target_model="Location", target_object_id=str(loc_id), action=AuditLog.ACTION_DELETE).exists()


@pytest.mark.django_db
def test_location_views_and_access(client, location_test_data):
    data = location_test_data
    admin = data["admin"]
    requester = data["requester"]
    org = data["org"]

    # Non-admin denied
    client.force_login(requester)
    resp = client.get(reverse("superadmin:locations"))
    assert resp.status_code == 403

    # Admin access
    client.force_login(admin)
    resp = client.get(reverse("superadmin:locations"))
    assert resp.status_code == 200
    assert "LOC-HYD" in resp.content.decode()
    assert "Hyderabad Campus" in resp.content.decode()

    # Create modal view GET
    resp_create = client.get(reverse("superadmin:location_create"))
    assert resp_create.status_code == 200
    assert "Create Location" in resp_create.content.decode()

    # Create Location POST
    post_data = {
        "organization": str(org.id),
        "name": "Bangalore Tech Hub",
        "code": "LOC-BLR",
        "city": "Bangalore",
        "country": "India",
        "address": "Electronic City",
        "is_active": "on",
    }
    resp_post = client.post(reverse("superadmin:location_create"), post_data)
    assert resp_post.status_code == 200
    assert Location.objects.filter(organization=org, code="LOC-BLR").exists()

    # Edit Location POST
    blr_loc = Location.objects.get(organization=org, code="LOC-BLR")
    edit_data = {
        "organization": str(org.id),
        "name": "Bangalore Tech Hub - Phase 2",
        "code": "LOC-BLR",
        "city": "Bangalore",
        "country": "India",
        "address": "Electronic City Phase 1",
        "is_active": "on",
    }
    resp_edit = client.post(reverse("superadmin:location_edit", args=[blr_loc.id]), edit_data)
    assert resp_edit.status_code == 200
    blr_loc.refresh_from_db()
    assert blr_loc.name == "Bangalore Tech Hub - Phase 2"

    # Delete Location POST
    resp_del = client.post(reverse("superadmin:location_delete", args=[blr_loc.id]))
    assert resp_del.status_code == 302
    assert not Location.objects.filter(id=blr_loc.id).exists()
