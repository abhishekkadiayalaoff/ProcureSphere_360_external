import pytest
from decimal import Decimal
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.organization.models import Organization, Department, CostCenter, FiscalPeriod, Location
from apps.budgets.models import Budget
from apps.approvals.models import ApprovalPolicy


@pytest.fixture
def admin_dashboards_setup(db):
    # 1. Global Super Admin
    role_sa, _ = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})
    role_req, _ = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})
    role_app, _ = Role.objects.get_or_create(code=Role.DEPT_APPROVER, defaults={"name": "Department Approver"})
    role_proc, _ = Role.objects.get_or_create(code=Role.PROC_EXEC, defaults={"name": "Procurement Executive"})

    global_superadmin = User.objects.create_superuser(
        email="global.superadmin@procuresphere.test",
        password="GlobalPassword123!",
        role=role_sa,
    )

    # 2. Organization & Org Admin
    org = Organization.objects.create(name="HPE Global", code="HPE-GLB", is_active=True)
    org_admin = User.objects.create_user(
        email="org.admin@hpe.test",
        password="OrgAdminPassword123!",
        role=role_sa,
        organization=org,
        is_staff=True,
    )
    org.admin_user = org_admin
    org.save(update_fields=["admin_user"])

    dept = Department.objects.create(organization=org, name="IT Operations", code="IT-OPS")
    cc = CostCenter.objects.create(department=dept, code="CC-IT-101", name="IT Infrastructure")
    loc = Location.objects.create(organization=org, code="LOC-HYD", name="Hyderabad Campus")

    today = timezone.localdate()
    period = FiscalPeriod.objects.create(
        organization=org, year=2026, period_number=1, name="FY26-Q1",
        start_date=today, end_date=today + timezone.timedelta(days=90),
    )
    budget = Budget.objects.create(cost_center=cc, fiscal_period=period, allocated_amount=Decimal("50000.00"))
    policy = ApprovalPolicy.objects.create(name="Default PR Policy", module="PR", is_active=True)

    return {
        "global_superadmin": global_superadmin,
        "org_admin": org_admin,
        "org": org,
        "dept": dept,
        "cc": cc,
        "loc": loc,
        "period": period,
        "budget": budget,
        "policy": policy,
        "role_req": role_req,
        "role_app": role_app,
        "role_proc": role_proc,
    }


@pytest.mark.django_db
def test_all_superadmin_dashboard_urls_and_buttons(admin_dashboards_setup):
    """Verifies that all Super Admin navigation URLs, detail views, and modals load with 200 OK."""
    client = Client()
    client.force_login(admin_dashboards_setup["global_superadmin"])

    urls_to_test = [
        "/superadmin/",
        "/admin/dashboard/",
        "/superadmin/organizations/",
        "/superadmin/organizations/create/",
        f"/superadmin/organizations/{admin_dashboards_setup['org'].id}/",
        f"/superadmin/organizations/{admin_dashboards_setup['org'].id}/view/",
        f"/superadmin/organizations/{admin_dashboards_setup['org'].id}/edit/",
        "/superadmin/locations/",
        "/superadmin/locations/create/",
        f"/superadmin/locations/{admin_dashboards_setup['loc'].id}/edit/",
        "/superadmin/users/",
        "/superadmin/users/create/",
        "/vendors/",
        "/vendors/create/",
        "/superadmin/policies/",
        "/superadmin/policies/create/",
        f"/superadmin/policies/{admin_dashboards_setup['policy'].id}/edit/",
        "/superadmin/budgets/",
        "/superadmin/fiscal-periods/create/",
        f"/superadmin/fiscal-periods/{admin_dashboards_setup['period'].id}/edit/",
        "/superadmin/budgets/create/",
        f"/superadmin/budgets/{admin_dashboards_setup['budget'].id}/edit/",
        "/invoices/settings/tolerances/",
        "/notifications/",
        "/reports/hub/",
        "/superadmin/audit/",
        "/superadmin/audit/export/?format=csv",
        "/superadmin/audit/export/?format=xlsx",
    ]

    for url in urls_to_test:
        response = client.get(url)
        assert response.status_code == 200, f"Superadmin URL failed: {url} with status {response.status_code}"


@pytest.mark.django_db
def test_all_org_admin_dashboard_urls_and_buttons(admin_dashboards_setup):
    """Verifies that all Organization Admin navigation URLs, detail views, and modals load with 200 OK."""
    client = Client()
    client.force_login(admin_dashboards_setup["org_admin"])

    urls_to_test = [
        "/admin/dashboard/",
        "/superadmin/",
        "/superadmin/organizations/",
        "/superadmin/locations/",
        "/superadmin/locations/create/",
        f"/superadmin/locations/{admin_dashboards_setup['loc'].id}/edit/",
        "/superadmin/departments/create/",
        f"/superadmin/departments/{admin_dashboards_setup['dept'].id}/edit/",
        "/superadmin/cost-centers/create/",
        f"/superadmin/cost-centers/{admin_dashboards_setup['cc'].id}/edit/",
        f"/superadmin/cost-centers/options/?department={admin_dashboards_setup['dept'].id}",
        "/superadmin/users/",
        "/superadmin/users/create/",
        "/vendors/",
        "/superadmin/policies/",
        "/superadmin/policies/create/",
        f"/superadmin/policies/{admin_dashboards_setup['policy'].id}/edit/",
        "/superadmin/budgets/",
        "/invoices/settings/tolerances/",
        "/notifications/",
        "/reports/hub/",
        "/superadmin/audit/",
    ]

    for url in urls_to_test:
        response = client.get(url)
        assert response.status_code == 200, f"Org Admin URL failed: {url} with status {response.status_code}"


@pytest.mark.django_db
def test_user_form_department_and_cost_center_only_for_requester(admin_dashboards_setup):
    """
    Verifies that Department and Cost Center options are conditional strictly for Requesters:
    - On GET /superadmin/users/create/: #requester-dept-cc-wrapper is hidden by default.
    - If non-requester role (e.g. Procurement Exec, Approver) is submitted, department & cost center are cleared/None.
    - If Requester role is submitted, department & cost center are required and saved.
    """
    client = Client()
    client.force_login(admin_dashboards_setup["org_admin"])

    # 1. GET user create modal
    res = client.get("/superadmin/users/create/")
    assert res.status_code == 200
    content = res.content.decode("utf-8")

    # Verify requester wrapper exists and has display: none by default
    assert 'id="requester-dept-cc-wrapper"' in content
    assert 'id="org-wide-role-wrapper"' in content
    assert "Organization-Wide Access" in content

    # 2. Create Non-Requester (Department Approver) -> Department & Cost Center are None
    res_app = client.post(
        "/superadmin/users/create/",
        {
            "email": "approver.orgwide@hpe.test",
            "phone_number": "9876543210",
            "role": str(admin_dashboards_setup["role_app"].pk),
            "department": "",
            "cost_center": "",
            "send_welcome_email": "on",
            "send_welcome_email_present": "1",
            "is_active": "on",
        },
    )
    assert res_app.status_code == 200
    user_app = User.objects.get(email="approver.orgwide@hpe.test")
    assert user_app.role == admin_dashboards_setup["role_app"]
    assert user_app.department is None
    assert user_app.cost_center is None
    assert user_app.organization == admin_dashboards_setup["org"]

    # 3. Create Requester without department -> rejected by validation
    res_req_invalid = client.post(
        "/superadmin/users/create/",
        {
            "email": "requester.bad@hpe.test",
            "role": str(admin_dashboards_setup["role_req"].pk),
            "department": "",
            "cost_center": "",
        },
    )
    assert res_req_invalid.status_code == 200
    assert "Department is required for Requester accounts." in res_req_invalid.content.decode("utf-8")

    # 4. Create Requester with department + cost center -> successfully created
    res_req_valid = client.post(
        "/superadmin/users/create/",
        {
            "email": "requester.valid@hpe.test",
            "phone_number": "9112233445",
            "role": str(admin_dashboards_setup["role_req"].pk),
            "department": str(admin_dashboards_setup["dept"].pk),
            "cost_center": str(admin_dashboards_setup["cc"].pk),
            "send_welcome_email": "on",
            "send_welcome_email_present": "1",
            "is_active": "on",
        },
    )
    assert res_req_valid.status_code == 200
    user_req = User.objects.get(email="requester.valid@hpe.test")
    assert user_req.role == admin_dashboards_setup["role_req"]
    assert user_req.department == admin_dashboards_setup["dept"]
    assert user_req.cost_center == admin_dashboards_setup["cc"]
