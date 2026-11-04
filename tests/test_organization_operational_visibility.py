import uuid
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.approvals.models import ApprovalAction, ApprovalPolicy, ApprovalStep
from apps.budgets.models import Budget
from apps.invoices.models import MatchException, SupplierInvoice
from apps.orders.models import PurchaseOrder
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.receipts.models import GoodsReceipt
from apps.requisitions.models import PurchaseRequisition
from apps.sourcing.models import SourcingEvent
from apps.vendors.models import Vendor, VendorCategory


@pytest.fixture
def multi_org_test_data(db, db_roles):
    """
    Sets up two isolated organizations with distinct operational footprints:
    - Organization 1: HPE (HPE-GLOBAL)
    - Organization 2: ACME (ACME-CORP)
    Plus a Global Super Admin and a non-admin Requester.
    """
    super_admin_role = db_roles[Role.SUPER_ADMIN]
    requester_role = db_roles[Role.REQUESTER]

    # Global Super Admin (unscoped)
    global_superadmin = User.objects.create_superuser(
        email="global_superadmin@procuresphere.local",
        password="SuperPassword123!",
        role=super_admin_role,
    )
    global_superadmin.must_change_password = False
    global_superadmin.save()

    # --- ORG 1: HPE ---
    org_hpe = Organization.objects.create(
        name="Hewlett Packard Enterprise",
        code="HPE-GLOBAL",
        tax_identifier="US-HPE-112233",
        address="1701 E Mossy Oaks Rd, Spring, TX 77389",
        is_active=True,
    )
    admin_hpe = User.objects.create_user(
        email="admin@hpe.com",
        password="Password123!",
        role=super_admin_role,
        organization=org_hpe,
        is_staff=True,
    )
    admin_hpe.must_change_password = False
    admin_hpe.save()
    org_hpe.admin_user = admin_hpe
    org_hpe.save(update_fields=["admin_user"])

    dept_hpe_it = Department.objects.create(
        organization=org_hpe,
        name="HPE IT Operations",
        code="HPE-IT-01",
    )
    cc_hpe_it = CostCenter.objects.create(
        department=dept_hpe_it,
        code="HPE-CC-IT",
        name="IT Infrastructure Cost Center",
        manager=admin_hpe,
    )

    user_hpe_req = User.objects.create_user(
        email="requester@hpe.com",
        password="Password123!",
        role=requester_role,
        organization=org_hpe,
        department=dept_hpe_it,
        cost_center=cc_hpe_it,
    )

    pr_hpe = PurchaseRequisition.objects.create(
        pr_number="PR-HPE-001",
        title="HPE Cloud Servers Cluster",
        justification="Hardware refresh",
        requester=user_hpe_req,
        department=dept_hpe_it,
        cost_center=cc_hpe_it,
        total_amount=Decimal("15000.00"),
        requested_delivery_date=timezone.now().date(),
        status=PurchaseRequisition.STATUS_SUBMITTED,
    )

    action_hpe = ApprovalAction.objects.create(
        target_object_id=pr_hpe.id,
        target_model_name="PurchaseRequisition",
        actor=user_hpe_req,
        action=ApprovalAction.ACTION_SUBMIT,
        previous_state="DRAFT",
        new_state="SUBMITTED",
        comments="Submitted PR for IT refresh.",
    )

    v_cat, _ = VendorCategory.objects.get_or_create(code="IT-HDW", defaults={"name": "Hardware"})
    vendor_hpe = Vendor.objects.create(
        legal_name="HPE Certified Server Supply LLC",
        vendor_number="VEN-HPE-01",
        tax_identification_number="TAX-HPE-VEN-01",
        category=v_cat,
        organization=org_hpe,
        status=Vendor.STATUS_ACTIVE,
    )

    po_hpe = PurchaseOrder.objects.create(
        po_number="PO-HPE-9001",
        vendor=vendor_hpe,
        requisition=pr_hpe,
        cost_center=cc_hpe_it,
        status=PurchaseOrder.STATUS_ISSUED,
        subtotal=Decimal("15000.00"),
        total_amount=Decimal("15000.00"),
    )

    # --- ORG 2: ACME ---
    org_acme = Organization.objects.create(
        name="ACME Corporation",
        code="ACME-CORP",
        tax_identifier="US-ACME-998877",
        address="100 Acme Way, Los Angeles, CA",
        is_active=True,
    )
    admin_acme = User.objects.create_user(
        email="admin@acme.com",
        password="Password123!",
        role=super_admin_role,
        organization=org_acme,
        is_staff=True,
    )
    admin_acme.must_change_password = False
    admin_acme.save()
    org_acme.admin_user = admin_acme
    org_acme.save(update_fields=["admin_user"])

    dept_acme_mkt = Department.objects.create(
        organization=org_acme,
        name="ACME Marketing",
        code="ACME-MKT-01",
    )
    cc_acme_mkt = CostCenter.objects.create(
        department=dept_acme_mkt,
        code="ACME-CC-MKT",
        name="Digital Ads Cost Center",
        manager=admin_acme,
    )

    user_acme_req = User.objects.create_user(
        email="requester@acme.com",
        password="Password123!",
        role=requester_role,
        organization=org_acme,
        department=dept_acme_mkt,
        cost_center=cc_acme_mkt,
    )

    pr_acme = PurchaseRequisition.objects.create(
        pr_number="PR-ACME-001",
        title="ACME Billboard Campaign",
        justification="Brand awareness",
        requester=user_acme_req,
        department=dept_acme_mkt,
        cost_center=cc_acme_mkt,
        total_amount=Decimal("25000.00"),
        requested_delivery_date=timezone.now().date(),
        status=PurchaseRequisition.STATUS_APPROVED,
    )

    vendor_acme = Vendor.objects.create(
        legal_name="ACME Global Media Partners",
        vendor_number="VEN-ACME-01",
        tax_identification_number="TAX-ACME-VEN-01",
        category=v_cat,
        organization=org_acme,
        status=Vendor.STATUS_ACTIVE,
    )

    return {
        "global_superadmin": global_superadmin,
        "org_hpe": org_hpe,
        "admin_hpe": admin_hpe,
        "dept_hpe_it": dept_hpe_it,
        "cc_hpe_it": cc_hpe_it,
        "user_hpe_req": user_hpe_req,
        "pr_hpe": pr_hpe,
        "action_hpe": action_hpe,
        "vendor_hpe": vendor_hpe,
        "po_hpe": po_hpe,
        "org_acme": org_acme,
        "admin_acme": admin_acme,
        "dept_acme_mkt": dept_acme_mkt,
        "cc_acme_mkt": cc_acme_mkt,
        "user_acme_req": user_acme_req,
        "pr_acme": pr_acme,
        "vendor_acme": vendor_acme,
    }


@pytest.mark.django_db
def test_authorized_superadmin_can_open_organization_dashboard(client, multi_org_test_data):
    """
    1. Authorized Super Admin can open the organization details dashboard.
    """
    data = multi_org_test_data
    client.force_login(data["global_superadmin"])

    url = reverse("superadmin:org_dashboard", args=[data["org_hpe"].id])
    res = client.get(url)

    assert res.status_code == 200
    content = res.content.decode()
    assert "Hewlett Packard Enterprise" in content
    assert "HPE-GLOBAL" in content
    assert "US-HPE-112233" in content
    assert "admin@hpe.com" in content
    assert "Back to Organizations" in content


@pytest.mark.django_db
def test_organization_name_and_view_button_navigation(client, multi_org_test_data):
    """
    2. Organization names and View buttons navigate to the dedicated details dashboard.
    """
    data = multi_org_test_data
    client.force_login(data["global_superadmin"])

    hpe_dash_url = reverse("superadmin:org_dashboard", args=[data["org_hpe"].id])

    # Check /superadmin/organizations/ contains links to dedicated dashboard
    res_list = client.get(reverse("superadmin:organizations"))
    assert res_list.status_code == 200
    content_list = res_list.content.decode()
    assert f'href="{hpe_dash_url}"' in content_list


@pytest.mark.django_db
def test_invalid_organization_id_returns_404(client, multi_org_test_data):
    """
    3. Invalid organization IDs return 404.
    """
    data = multi_org_test_data
    client.force_login(data["global_superadmin"])

    random_uuid = uuid.uuid4()
    url = reverse("superadmin:org_dashboard", args=[random_uuid])
    res = client.get(url)

    assert res.status_code == 404


@pytest.mark.django_db
def test_organization_data_isolation_users(client, multi_org_test_data):
    """
    4. Organization A displays only its own users; Organization B users are excluded.
    """
    data = multi_org_test_data
    client.force_login(data["global_superadmin"])

    # View HPE dashboard
    url_hpe = reverse("superadmin:org_dashboard", args=[data["org_hpe"].id])
    res_hpe = client.get(url_hpe + "?tab=users")
    assert res_hpe.status_code == 200
    content_hpe = res_hpe.content.decode()

    # Must contain HPE users
    assert "requester@hpe.com" in content_hpe
    assert "admin@hpe.com" in content_hpe

    # Must NOT contain ACME users
    assert "requester@acme.com" not in content_hpe
    assert "admin@acme.com" not in content_hpe


@pytest.mark.django_db
def test_organization_data_isolation_departments_and_cost_centers(client, multi_org_test_data):
    """
    5. Department and cost center records are correctly scoped.
    """
    data = multi_org_test_data
    client.force_login(data["global_superadmin"])

    # View HPE dashboard
    url_hpe = reverse("superadmin:org_dashboard", args=[data["org_hpe"].id])
    res_hpe = client.get(url_hpe + "?tab=departments")
    assert res_hpe.status_code == 200
    content_hpe = res_hpe.content.decode()

    # HPE Dept & Cost Center present
    assert "HPE IT Operations" in content_hpe
    assert "HPE-IT-01" in content_hpe
    assert "HPE-CC-IT" in content_hpe

    # ACME Dept & Cost Center absent
    assert "ACME Marketing" not in content_hpe
    assert "ACME-MKT-01" not in content_hpe
    assert "ACME-CC-MKT" not in content_hpe


@pytest.mark.django_db
def test_organization_data_isolation_prs_and_approvals(client, multi_org_test_data):
    """
    6. PRs and approvals are correctly scoped.
    """
    data = multi_org_test_data
    client.force_login(data["global_superadmin"])

    # View HPE dashboard
    url_hpe = reverse("superadmin:org_dashboard", args=[data["org_hpe"].id])
    res_hpe = client.get(url_hpe + "?tab=prs")
    assert res_hpe.status_code == 200
    content_hpe = res_hpe.content.decode()

    # HPE PR present, ACME PR absent
    assert "PR-HPE-001" in content_hpe
    assert "HPE Cloud Servers Cluster" in content_hpe
    assert "PR-ACME-001" not in content_hpe
    assert "ACME Billboard Campaign" not in content_hpe

    # Check approvals tab
    res_apprv = client.get(url_hpe + "?tab=approvals")
    assert res_apprv.status_code == 200
    content_apprv = res_apprv.content.decode()
    assert "Submitted PR for IT refresh." in content_apprv


@pytest.mark.django_db
def test_organization_data_isolation_vendors_and_purchase_orders(client, multi_org_test_data):
    """
    7. Vendors and purchase orders are correctly scoped.
    """
    data = multi_org_test_data
    client.force_login(data["global_superadmin"])

    url_hpe = reverse("superadmin:org_dashboard", args=[data["org_hpe"].id])

    # Vendors tab
    res_v = client.get(url_hpe + "?tab=vendors")
    assert res_v.status_code == 200
    content_v = res_v.content.decode()
    assert "HPE Certified Server Supply LLC" in content_v
    assert "ACME Global Media Partners" not in content_v

    # Orders tab
    res_po = client.get(url_hpe + "?tab=orders")
    assert res_po.status_code == 200
    content_po = res_po.content.decode()
    assert "PO-HPE-9001" in content_po


@pytest.mark.django_db
def test_summary_statistics_match_actual_database_records(client, multi_org_test_data):
    """
    8. Summary statistics match actual database records.
    """
    data = multi_org_test_data
    client.force_login(data["global_superadmin"])

    url_hpe = reverse("superadmin:org_dashboard", args=[data["org_hpe"].id])
    res = client.get(url_hpe)
    assert res.status_code == 200

    ctx = res.context
    assert ctx["total_users_count"] == 2  # admin_hpe, user_hpe_req
    assert ctx["departments_count"] == 1
    assert ctx["cost_centers_count"] == 1
    assert ctx["total_prs_count"] == 1
    assert ctx["pending_prs_count"] == 1
    assert ctx["total_vendors_count"] == 1
    assert ctx["total_pos_count"] == 1


@pytest.mark.django_db
def test_users_search_and_filtering(client, multi_org_test_data):
    """
    9. Search, filters and pagination work properly on the users tab.
    """
    data = multi_org_test_data
    client.force_login(data["global_superadmin"])

    url_hpe = reverse("superadmin:org_dashboard", args=[data["org_hpe"].id])

    # Search for requester
    res_search = client.get(url_hpe + "?tab=users&q_user=requester")
    assert res_search.status_code == 200
    search_emails = [u.email for u in res_search.context["users_page_obj"]]
    assert "requester@hpe.com" in search_emails
    assert "admin@hpe.com" not in search_emails

    # Filter by role SUPER_ADMIN
    res_role = client.get(url_hpe + "?tab=users&role=SUPER_ADMIN")
    assert res_role.status_code == 200
    role_emails = [u.email for u in res_role.context["users_page_obj"]]
    assert "admin@hpe.com" in role_emails
    assert "requester@hpe.com" not in role_emails


@pytest.mark.django_db
def test_unauthorized_users_cannot_access_dashboard(client, multi_org_test_data):
    """
    10. Unauthorized users cannot access Super Admin organization details.
    """
    data = multi_org_test_data

    # Anonymous user is redirected to login
    url_hpe = reverse("superadmin:org_dashboard", args=[data["org_hpe"].id])
    res_anon = client.get(url_hpe)
    assert res_anon.status_code == 302

    # Standard Requester user receives 403 Forbidden
    client.force_login(data["user_hpe_req"])
    res_req = client.get(url_hpe)
    assert res_req.status_code == 403
    assert b"Permission Denied" in res_req.content


@pytest.mark.django_db
def test_scoped_tenant_admin_cannot_access_other_organization(client, multi_org_test_data):
    """
    11. Scoped tenant admin cannot access another organization's dashboard (returns 403).
    """
    data = multi_org_test_data

    # Log in as HPE Admin
    client.force_login(data["admin_hpe"])

    # HPE Admin CAN view HPE dashboard
    url_hpe = reverse("superadmin:org_dashboard", args=[data["org_hpe"].id])
    res_own = client.get(url_hpe)
    assert res_own.status_code == 200

    # HPE Admin CANNOT view ACME dashboard (403 Forbidden)
    url_acme = reverse("superadmin:org_dashboard", args=[data["org_acme"].id])
    res_other = client.get(url_acme)
    assert res_other.status_code == 403
    assert b"Permission Denied" in res_other.content


@pytest.mark.django_db
def test_existing_organization_crud_still_works(client, multi_org_test_data):
    """
    12. Existing organization Create, View modal, Edit and Delete functions still work.
    """
    data = multi_org_test_data
    client.force_login(data["global_superadmin"])

    # Modal View (org_detail)
    url_detail = reverse("superadmin:org_detail", args=[data["org_hpe"].id])
    res_detail = client.get(url_detail)
    assert res_detail.status_code == 200
    assert "Hewlett Packard Enterprise" in res_detail.content.decode()

    # Modal Edit form GET
    url_edit = reverse("superadmin:org_edit", args=[data["org_hpe"].id])
    res_edit = client.get(url_edit)
    assert res_edit.status_code == 200

    # Modal Create form GET
    url_create = reverse("superadmin:org_create")
    res_create = client.get(url_create)
    assert res_create.status_code == 200


@pytest.mark.django_db
def test_role_dashboards_continue_working_unaffected(client, multi_org_test_data):
    """
    13. Existing Requester, Manager, Approver and other role dashboards continue to work.
    """
    data = multi_org_test_data

    # Requester home view
    client.force_login(data["user_hpe_req"])
    res = client.get(reverse("home"))
    assert res.status_code == 200
    assert any("requester_dashboard.html" in (t.name or "") for t in res.templates)


@pytest.mark.django_db
def test_superadmin_viewing_pr_uses_superadmin_layout_not_requester_desk(client, multi_org_test_data):
    """
    14. Super Admin viewing a requisition renders inside layouts/superadmin_base.html
        and NEVER inside the Requester Desk / requester sidebar.
    """
    data = multi_org_test_data
    pr = data["pr_hpe"]

    # 1. Global Super Admin views PR detail
    client.force_login(data["global_superadmin"])
    res_sa = client.get(reverse("requisition_detail", args=[pr.pk]))
    assert res_sa.status_code == 200
    assert res_sa.context["base_layout"] == "layouts/superadmin_base.html"
    content_sa = res_sa.content.decode()
    assert "Requester Desk" not in content_sa
    assert "REQUESTER MENU" not in content_sa
    assert "sa-sidebar" in content_sa
    assert "Back" in content_sa

    # 2. Global Super Admin views PR list
    res_sa_list = client.get(reverse("requisitions_list"))
    assert res_sa_list.status_code == 200
    assert res_sa_list.context["base_layout"] == "layouts/superadmin_base.html"
    content_sa_list = res_sa_list.content.decode()
    assert "Requester Desk" not in content_sa_list
    assert "sa-sidebar" in content_sa_list

    # 3. Requester user still gets requester_base.html
    client.force_login(data["user_hpe_req"])
    res_req = client.get(reverse("requisition_detail", args=[pr.pk]))
    assert res_req.status_code == 200
    assert res_req.context["base_layout"] == "layouts/requester_base.html"
    content_req = res_req.content.decode()
    assert "Requester Desk" in content_req

