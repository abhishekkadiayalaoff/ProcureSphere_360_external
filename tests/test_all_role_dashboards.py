import pytest

from apps.accounts.models import Role, User
from apps.vendors.models import Vendor, VendorCategory


@pytest.mark.django_db
def test_all_role_dashboards_render_successfully(client):
    roles_to_test = [
        (Role.SUPER_ADMIN, "ProcureSphere 360"),
        (Role.REQUESTER, "Requester"),
        (Role.DEPT_APPROVER, "Approver"),
        (Role.PROC_MGR, "Manager"),
        (Role.PROC_EXEC, "Procurement"),
        (Role.STORES_RECEIVER, "Stores"),
        (Role.FINANCE_AP, "Finance"),
        (Role.LEGAL_MGR, "Legal"),
        (Role.AUDITOR, "Auditor"),
        (Role.VENDOR_USER, "Vendor"),
    ]

    for role_code, expected_snippet in roles_to_test:
        role, _ = Role.objects.get_or_create(code=role_code, defaults={"name": role_code})
        user = User.objects.create_user(
            email=f"user_{role_code.lower()}@hpe.com",
            password="Password123!",
            role=role,
        )

        if role_code == Role.VENDOR_USER:
            cat = VendorCategory.objects.create(name="Default Cat", code=f"CAT-{role_code}")
            vendor = Vendor.objects.create(
                legal_name="Test Vendor Inc",
                tax_identification_number=f"TAX-{role_code}",
                category=cat,
                email=user.email,
                status=Vendor.STATUS_ACTIVE,
            )
            user.vendor = vendor
            user.save()

        client.force_login(user)
        response = client.get("/")
        assert response.status_code == 200
        assert expected_snippet.lower() in response.content.decode().lower()
