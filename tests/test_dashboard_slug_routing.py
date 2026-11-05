import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.organization.models import Organization
from apps.vendors.models import Vendor, VendorCategory


@pytest.mark.django_db
def test_all_role_dashboard_slug_urls_render_200(client):
    """
    Test that each role's specific dashboard slug URL returns 200 OK and renders the respective dashboard.
    """
    role_urls = [
        (Role.REQUESTER, "/requester/", "Requester"),
        (Role.DEPT_APPROVER, "/approver/", "Approver"),
        (Role.PROC_EXEC, "/procurement/", "Procurement"),
        (Role.PROC_MGR, "/manager/", "Manager"),
        (Role.FINANCE_AP, "/finance/", "Finance"),
        (Role.STORES_RECEIVER, "/stores/", "Stores"),
        (Role.LEGAL_MGR, "/legal/", "Legal"),
        (Role.AUDITOR, "/audit/dashboard/", "Auditor"),
        (Role.SUPER_ADMIN, "/superadmin/", "Admin"),
        (Role.VENDOR_USER, "/vendor/", "Vendor"),
    ]

    org = Organization.objects.create(name="Acme Corp", code="ORG-ACME")

    for role_code, url, expected_text in role_urls:
        role, _ = Role.objects.get_or_create(code=role_code, defaults={"name": role_code})
        user = User.objects.create_user(
            email=f"user_{role_code.lower()}@acme.com",
            password="Password123!",
            role=role,
            organization=org,
        )

        if role_code == Role.VENDOR_USER:
            cat = VendorCategory.objects.create(name="Test Category", code=f"VCAT-{role_code}")
            vendor = Vendor.objects.create(
                legal_name="Test Vendor Corp",
                tax_identification_number=f"TIN-{role_code}",
                category=cat,
                email=user.email,
                status=Vendor.STATUS_ACTIVE,
            )
            user.vendor = vendor
            user.save()

        client.force_login(user)
        response = client.get(url)
        assert response.status_code == 200, f"URL {url} for role {role_code} failed with {response.status_code}"
        assert expected_text.lower() in response.content.decode().lower()
        client.logout()


@pytest.mark.django_db
def test_login_redirects_to_respective_dashboard_slug(client):
    """
    Test that logging in redirects the user directly to their role-specific dashboard slug (not /).
    """
    test_cases = [
        (Role.REQUESTER, "/requester/"),
        (Role.DEPT_APPROVER, "/approver/"),
        (Role.PROC_EXEC, "/procurement/"),
        (Role.PROC_MGR, "/manager/"),
        (Role.FINANCE_AP, "/finance/"),
        (Role.STORES_RECEIVER, "/stores/"),
        (Role.LEGAL_MGR, "/legal/"),
        (Role.AUDITOR, "/audit/dashboard/"),
        (Role.SUPER_ADMIN, "/superadmin/"),
        (Role.VENDOR_USER, "/vendor/"),
    ]

    org = Organization.objects.create(name="Global Enterprise", code="ORG-GLOBAL")

    for role_code, expected_redirect_url in test_cases:
        client.logout()
        role, _ = Role.objects.get_or_create(code=role_code, defaults={"name": role_code})
        email = f"login_test_{role_code.lower()}@global.com"
        user = User.objects.create_user(
            email=email,
            password="Password123!",
            role=role,
            organization=org,
        )

        if role_code == Role.VENDOR_USER:
            cat = VendorCategory.objects.create(name="Vendor Cat", code=f"CAT-LOGIN-{role_code}")
            vendor = Vendor.objects.create(
                legal_name="Vendor Co",
                tax_identification_number=f"TIN-LOGIN-{role_code}",
                category=cat,
                email=email,
                status=Vendor.STATUS_ACTIVE,
            )
            user.vendor = vendor
            user.save()

        # Submit login form
        response = client.post("/login/", {"email": email, "password": "Password123!"})
        assert response.status_code == 302, f"Login for {email} failed: {response.status_code}"
        assert response.url == expected_redirect_url, f"Expected {expected_redirect_url}, got {response.url}"

        # If already authenticated and accessing /login/, should redirect to the same slug
        resp_auth = client.get("/login/")
        assert resp_auth.status_code == 302
        assert resp_auth.url == expected_redirect_url
        client.logout()


@pytest.mark.django_db
def test_dashboard_redirect_endpoint(client):
    """
    Test that /dashboard/ redirects to the respective dashboard slug for authenticated users.
    """
    role, _ = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})
    user = User.objects.create_user(
        email="req_redirect@example.com",
        password="Password123!",
        role=role,
    )
    client.force_login(user)
    response = client.get("/dashboard/")
    assert response.status_code == 302
    assert response.url == "/requester/"
