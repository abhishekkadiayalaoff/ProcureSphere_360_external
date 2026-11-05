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


@pytest.mark.django_db
def test_dept_approver_dashboard_handles_missing_department_and_org(client):
    from apps.organization.models import Department, Organization

    role, _ = Role.objects.get_or_create(
        code=Role.DEPT_APPROVER, defaults={"name": "Department Approver"}
    )
    org = Organization.objects.create(name="Approver Render Org", code="APPR-ORG")
    Department.objects.create(organization=org, name="Operations", code="APPR-OPS")

    # Organization assigned but user.department is None: the dashboard resolves a
    # fallback department, exercising the former `user.department.name` crash path.
    org_only_user = User.objects.create_user(
        email="approver_org_only@hpe.com", role=role, organization=org
    )
    client.force_login(org_only_user)
    response = client.get("/approver/")
    assert response.status_code == 200

    # Neither organization nor department assigned: must still render with guidance.
    orphan_user = User.objects.create_user(
        email="approver_orphan@hpe.com", role=role
    )
    client.force_login(orphan_user)
    response = client.get("/approver/")
    assert response.status_code == 200
    assert "not linked to a department" in response.content.decode()
