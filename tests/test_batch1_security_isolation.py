import os
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.accounts.models import Role, User
from apps.organization.models import CostCenter, Department, Organization
from apps.vendors.models import Vendor, VendorCategory, VendorDocument


@pytest.fixture
def batch1_setup(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

    org = Organization.objects.create(name="HPE Global", code="HPE-B1")
    dept = Department.objects.create(name="IT Operations", code="IT-B1", organization=org)
    cc = CostCenter.objects.create(name="Infrastructure", code="CC-B1", department=dept)
    category = VendorCategory.objects.create(name="Hardware", code="CAT-HW-B1")

    # Roles
    role_admin, _ = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})
    role_req, _ = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})
    role_legal, _ = Role.objects.get_or_create(code=Role.LEGAL_MGR, defaults={"name": "Legal Manager"})
    role_vendor, _ = Role.objects.get_or_create(code=Role.VENDOR_USER, defaults={"name": "Vendor User"})

    # Users
    admin = User.objects.create_user(
        email="admin.b1@test.local", password="Password123!", role=role_admin, is_staff=True, is_superuser=True
    )
    requester = User.objects.create_user(
        email="req.b1@test.local", password="Password123!", role=role_req, department=dept, cost_center=cc
    )
    legal = User.objects.create_user(
        email="legal.b1@test.local", password="Password123!", role=role_legal
    )

    vendor_a = Vendor.objects.create(
        vendor_number="VEN-B1-01",
        legal_name="Vendor Alpha",
        tax_identification_number="TIN-ALPHA-01",
        category=category,
        organization=org,
        status=Vendor.STATUS_ACTIVE,
    )
    vendor_b = Vendor.objects.create(
        vendor_number="VEN-B1-02",
        legal_name="Vendor Beta",
        tax_identification_number="TIN-BETA-02",
        category=category,
        organization=org,
        status=Vendor.STATUS_ACTIVE,
    )

    vendor_user_a = User.objects.create_user(
        email="user@alpha.test", password="Password123!", role=role_vendor, vendor=vendor_a
    )
    vendor_user_b = User.objects.create_user(
        email="user@beta.test", password="Password123!", role=role_vendor, vendor=vendor_b
    )

    # Create dummy files in media root
    doc_a_rel = "vendor_docs/alpha_kyc.pdf"
    doc_a_abs = os.path.join(settings.MEDIA_ROOT, doc_a_rel)
    os.makedirs(os.path.dirname(doc_a_abs), exist_ok=True)
    with open(doc_a_abs, "wb") as f:
        f.write(b"%PDF-1.4 Alpha KYC Secret Document Content")

    VendorDocument.objects.create(
        vendor=vendor_a,
        document_type=VendorDocument.DOC_TYPE_TAX,
        title="Alpha Tax Certificate",
        file=doc_a_rel,
    )

    contract_rel = "contracts/confidential_agreement.pdf"
    contract_abs = os.path.join(settings.MEDIA_ROOT, contract_rel)
    os.makedirs(os.path.dirname(contract_abs), exist_ok=True)
    with open(contract_abs, "wb") as f:
        f.write(b"%PDF-1.4 Confidential Contract Master Agreement")

    return {
        "admin": admin,
        "requester": requester,
        "legal": legal,
        "vendor_user_a": vendor_user_a,
        "vendor_user_b": vendor_user_b,
        "vendor_a": vendor_a,
        "vendor_b": vendor_b,
        "doc_a_url": f"/media/{doc_a_rel}",
        "contract_url": f"/media/{contract_rel}",
    }


def test_def_001_demo_roles_are_not_superuser(batch1_setup):
    """DEF-001: Non-superadmin users must not have is_superuser or is_staff."""
    assert not batch1_setup["requester"].is_superuser
    assert not batch1_setup["requester"].is_staff
    assert not batch1_setup["legal"].is_superuser
    assert not batch1_setup["legal"].is_staff
    assert not batch1_setup["vendor_user_a"].is_superuser
    assert not batch1_setup["vendor_user_a"].is_staff

    assert batch1_setup["admin"].is_superuser
    assert batch1_setup["admin"].is_staff


def test_def_002_media_unauthenticated_access_blocked(client, batch1_setup):
    """DEF-002: Anonymous users cannot download media files directly."""
    resp = client.get(batch1_setup["doc_a_url"])
    assert resp.status_code in [401, 403], f"Unauthenticated user accessed media: {resp.status_code}"


def test_def_002_media_path_traversal_blocked(client, batch1_setup):
    """DEF-002: Directory traversal attempts are rejected."""
    client.force_login(batch1_setup["requester"])
    resp = client.get("/media/../etc/passwd")
    assert resp.status_code in [403, 404]


def test_def_002_vendor_cannot_access_other_vendor_media(client, batch1_setup):
    """DEF-002: Vendor B cannot download Vendor A's KYC document."""
    # Vendor B attempting to access Vendor A's file
    client.force_login(batch1_setup["vendor_user_b"])
    resp = client.get(batch1_setup["doc_a_url"])
    assert resp.status_code == 403, f"Vendor B improperly accessed Vendor A's document: {resp.status_code}"

    # Vendor A can access their own document
    client.force_login(batch1_setup["vendor_user_a"])
    resp = client.get(batch1_setup["doc_a_url"])
    assert resp.status_code == 200, f"Vendor A failed to access their own document: {resp.status_code}"
    assert b"Alpha KYC Secret Document Content" in resp.getvalue()


def test_def_002_requester_cannot_access_confidential_contract_media(client, batch1_setup):
    """DEF-002: Requesters cannot access legal contract media files."""
    client.force_login(batch1_setup["requester"])
    resp = client.get(batch1_setup["contract_url"])
    assert resp.status_code == 403

    # Legal manager can access
    client.force_login(batch1_setup["legal"])
    resp = client.get(batch1_setup["contract_url"])
    assert resp.status_code == 200
    assert b"Confidential Contract Master Agreement" in resp.getvalue()


def test_def_003_vendor_blocked_from_internal_staff_ui_views(client, batch1_setup):
    """DEF-003: Vendor users receive 403 when trying to access internal UI routes."""
    client.force_login(batch1_setup["vendor_user_a"])

    internal_ui_routes = [
        "/requisitions/",
        "/contracts/",
        "/orders/",
        "/invoices/",
        "/receipts/",
        "/budgets/",
        "/reports/",
        "/superadmin/users/",
        "/manager/pipeline/",
    ]
    for url in internal_ui_routes:
        resp = client.get(url)
        assert resp.status_code == 403, f"Vendor unexpectedly accessed internal route {url} with status {resp.status_code}"


def test_def_003_vendor_blocked_from_internal_api_endpoints(client, batch1_setup):
    """DEF-003: Vendor users receive 403 JSON when trying to access internal REST endpoints."""
    client.force_login(batch1_setup["vendor_user_a"])

    internal_api_routes = [
        "/api/v1/requisitions/",
        "/api/v1/contracts/",
        "/api/v1/budgets/",
        "/api/v1/reports/",
        "/api/v1/audit/",
    ]
    for url in internal_api_routes:
        resp = client.get(url)
        assert resp.status_code == 403, f"Vendor unexpectedly accessed internal API {url} with status {resp.status_code}"
        assert resp.json().get("error", {}).get("code") == "FORBIDDEN"


def test_def_003_vendor_portal_allowed_for_vendor(client, batch1_setup):
    """DEF-003: Vendor users can freely access the vendor portal routes."""
    client.force_login(batch1_setup["vendor_user_a"])
    resp = client.get("/vendor/dashboard/")
    assert resp.status_code in [200, 302]
