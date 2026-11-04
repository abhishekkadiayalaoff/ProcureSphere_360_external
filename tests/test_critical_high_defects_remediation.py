from decimal import Decimal
import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.approvals.models import ApprovalAction, ApprovalPolicy, ApprovalStep
from apps.contracts.models import Contract
from apps.invoices.models import MatchException, SupplierInvoice
from apps.orders.models import POLine, PurchaseOrder
from apps.organization.models import CostCenter, Department, Organization
from apps.receipts.models import GoodsReceipt
from apps.requisitions.models import PurchaseRequisition
from apps.vendors.models import Vendor, VendorCategory, VendorDocument


@pytest.fixture
def defect_test_data(db):
    org = Organization.objects.create(name="Remediation Enterprise", code="REM-ORG")
    dept = Department.objects.create(name="Remediation Dept", code="REM-DEPT", organization=org)
    cost_center = CostCenter.objects.create(name="Remediation CC", code="REM-CC", department=dept)

    # Roles
    role_admin, _ = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})
    role_req, _ = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})
    role_dept_app, _ = Role.objects.get_or_create(code=Role.DEPT_APPROVER, defaults={"name": "Dept Approver"})
    role_fin, _ = Role.objects.get_or_create(code=Role.FINANCE_AP, defaults={"name": "Finance AP"})
    role_proc_exec, _ = Role.objects.get_or_create(code=Role.PROC_EXEC, defaults={"name": "Procurement Executive"})
    role_proc_mgr, _ = Role.objects.get_or_create(code=Role.PROC_MGR, defaults={"name": "Procurement Manager"})
    role_auditor, _ = Role.objects.get_or_create(code=Role.AUDITOR, defaults={"name": "Auditor"})
    role_vendor, _ = Role.objects.get_or_create(code=Role.VENDOR_USER, defaults={"name": "Vendor User"})

    # Users
    admin_user = User.objects.create_user(
        email="admin.rem@test.com", password="Password123!", role=role_admin, is_staff=True, is_superuser=True
    )
    requester = User.objects.create_user(
        email="requester.rem@test.com", password="Password123!", role=role_req, department=dept, cost_center=cost_center
    )
    dept_approver = User.objects.create_user(
        email="approver.rem@test.com", password="Password123!", role=role_dept_app, department=dept
    )
    finance_user = User.objects.create_user(
        email="finance.rem@test.com", password="Password123!", role=role_fin, department=dept
    )
    proc_exec = User.objects.create_user(
        email="procexec.rem@test.com", password="Password123!", role=role_proc_exec, department=dept
    )
    proc_mgr = User.objects.create_user(
        email="procmgr.rem@test.com", password="Password123!", role=role_proc_mgr, department=dept
    )
    auditor = User.objects.create_user(
        email="auditor.rem@test.com", password="Password123!", role=role_auditor
    )

    # Vendors
    category = VendorCategory.objects.create(name="Tech Hardware", code="TECH-HDW")
    vendor_active = Vendor.objects.create(
        vendor_number="VND-REM-01",
        legal_name="Apex Technologies Active",
        tax_identification_number="TAX-APEX-01",
        category=category,
        status=Vendor.STATUS_ACTIVE,
    )
    vendor_suspended = Vendor.objects.create(
        vendor_number="VND-REM-02",
        legal_name="Apex Technologies Suspended",
        tax_identification_number="TAX-APEX-02",
        category=category,
        status=Vendor.STATUS_SUSPENDED,
    )
    vendor_draft = Vendor.objects.create(
        vendor_number="VND-REM-03",
        legal_name="Apex Technologies Draft",
        tax_identification_number="TAX-APEX-03",
        category=category,
        status=Vendor.STATUS_DRAFT,
    )

    vendor_user = User.objects.create_user(
        email="vendor.apex@test.com", password="Password123!", role=role_vendor, vendor=vendor_active
    )
    other_vendor = Vendor.objects.create(
        vendor_number="VND-REM-04",
        legal_name="Other Vendor Corp",
        tax_identification_number="TAX-OTH-01",
        category=category,
        status=Vendor.STATUS_ACTIVE,
    )
    other_vendor_user = User.objects.create_user(
        email="other.vendor@test.com", password="Password123!", role=role_vendor, vendor=other_vendor
    )

    return {
        "org": org,
        "dept": dept,
        "cost_center": cost_center,
        "admin_user": admin_user,
        "requester": requester,
        "dept_approver": dept_approver,
        "finance_user": finance_user,
        "proc_exec": proc_exec,
        "proc_mgr": proc_mgr,
        "auditor": auditor,
        "vendor_user": vendor_user,
        "other_vendor_user": other_vendor_user,
        "vendor_active": vendor_active,
        "vendor_suspended": vendor_suspended,
        "vendor_draft": vendor_draft,
        "other_vendor": other_vendor,
        "category": category,
        "role_req": role_req,
        "role_admin": role_admin,
    }


@pytest.mark.django_db
def test_def_001_superuser_only_for_superadmin(defect_test_data):
    """
    DEF-001: Non-SUPER_ADMIN users cannot have is_superuser or is_staff enabled.
    """
    role_req = defect_test_data["role_req"]
    user = User(
        email="rogue.req@test.com",
        role=role_req,
        is_superuser=True,
        is_staff=True,
    )
    user.set_password("Password123!")
    user.save()

    user.refresh_from_db()
    assert user.is_superuser is False
    assert user.is_staff is False

    # Super admin retains is_superuser
    admin = defect_test_data["admin_user"]
    admin.is_superuser = True
    admin.is_staff = True
    admin.save()
    admin.refresh_from_db()
    assert admin.is_superuser is True


@pytest.mark.django_db
def test_def_004_delete_blocked_when_children_exist(defect_test_data):
    """
    DEF-004: Deleting organization with departments or department with cost centers returns 400.
    """
    client = APIClient()
    client.force_authenticate(user=defect_test_data["admin_user"])

    # Attempt to delete Organization having departments (registered under 'entities')
    org = defect_test_data["org"]
    res = client.delete(f"/api/v1/organization/entities/{org.id}/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot delete organization" in str(res.data)

    # Attempt to delete Department having cost centers
    dept = defect_test_data["dept"]
    res = client.delete(f"/api/v1/organization/departments/{dept.id}/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot delete department" in str(res.data)


@pytest.mark.django_db
def test_def_007_approver_authorization_on_approval_actions(defect_test_data):
    """
    DEF-007: Requester or unauthorized role cannot reject approval actions.
    """
    pr = PurchaseRequisition.objects.create(
        pr_number="PR-REM-001",
        title="Test PR for Rejection",
        justification="Hardware replenishment",
        requested_delivery_date=timezone.now().date() + timezone.timedelta(days=14),
        requester=defect_test_data["requester"],
        department=defect_test_data["dept"],
        cost_center=defect_test_data["cost_center"],
        total_amount=Decimal("5000.00"),
        status=PurchaseRequisition.STATUS_SUBMITTED,
    )
    action = ApprovalAction.objects.create(
        target_object_id=pr.id,
        target_model_name="PurchaseRequisition",
        action=ApprovalAction.ACTION_SUBMIT,
        actor=defect_test_data["requester"],
        previous_state=PurchaseRequisition.STATUS_DRAFT,
        new_state=PurchaseRequisition.STATUS_SUBMITTED,
    )

    client = APIClient()
    client.force_authenticate(user=defect_test_data["requester"])
    res = client.post(f"/api/v1/approvals/actions/{action.id}/reject/", {"comments": "Requester self-rejecting"})
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_def_010_activating_unverified_vendor_blocked(defect_test_data):
    """
    DEF-010: Activating vendor without completed verified KYC documents returns 400.
    """
    client = APIClient()
    client.force_authenticate(user=defect_test_data["proc_mgr"])

    vendor_draft = defect_test_data["vendor_draft"]
    res = client.post(
        f"/api/v1/vendors/{vendor_draft.id}/governance-status/",
        {"status": Vendor.STATUS_ACTIVE, "reason": "Attempting early activation"},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    vendor_draft.refresh_from_db()
    assert vendor_draft.status != Vendor.STATUS_ACTIVE


@pytest.mark.django_db
def test_def_012_pr_draft_only_modification_and_deletion(defect_test_data):
    """
    DEF-012: Modifying or deleting non-DRAFT PR via API returns 400.
    """
    pr = PurchaseRequisition.objects.create(
        pr_number="PR-REM-002",
        title="Submitted PR",
        justification="Upgrade equipment",
        requested_delivery_date=timezone.now().date() + timezone.timedelta(days=14),
        requester=defect_test_data["requester"],
        department=defect_test_data["dept"],
        cost_center=defect_test_data["cost_center"],
        total_amount=Decimal("1200.00"),
        status=PurchaseRequisition.STATUS_SUBMITTED,
    )

    client = APIClient()
    client.force_authenticate(user=defect_test_data["requester"])

    # Modification
    res = client.patch(f"/api/v1/requisitions/{pr.id}/", {"title": "Changed Title"})
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # Deletion
    res = client.delete(f"/api/v1/requisitions/{pr.id}/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_def_015_po_amendment_validation(defect_test_data):
    """
    DEF-015: Malformed PO amendment data returns 400, not 500.
    """
    po = PurchaseOrder.objects.create(
        po_number="PO-REM-001",
        version=1,
        vendor=defect_test_data["vendor_active"],
        cost_center=defect_test_data["cost_center"],
        status=PurchaseOrder.STATUS_ISSUED,
        total_amount=Decimal("1000.00"),
    )
    POLine.objects.create(
        po=po,
        item_description="Server Rack",
        quantity=Decimal("1"),
        unit_price=Decimal("1000.00"),
    )

    client = APIClient()
    client.force_authenticate(user=defect_test_data["proc_exec"])

    # Negative quantity amendment line
    res = client.post(
        f"/api/v1/purchase-orders/{po.id}/amend/",
        {
            "reason": "Test Bad Amendment",
            "lines": [{"item_description": "Server Rack", "quantity": -5, "unit_price": 100}],
        },
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_def_016_po_creation_blocked_for_suspended_vendor(defect_test_data):
    """
    DEF-016: Creating PO for suspended vendor returns 400.
    """
    client = APIClient()
    client.force_authenticate(user=defect_test_data["proc_exec"])

    res = client.post(
        "/api/v1/purchase-orders/",
        {
            "vendor": defect_test_data["vendor_suspended"].id,
            "cost_center": defect_test_data["cost_center"].id,
            "line_items": [{"item_description": "Laptop", "quantity": 1, "unit_price": 500}],
        },
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "ACTIVE" in str(res.data)


@pytest.mark.django_db
def test_def_017_018_po_draft_only_modification_and_deletion(defect_test_data):
    """
    DEF-017, DEF-018: Modifying or deleting ISSUED PO returns 400.
    """
    po = PurchaseOrder.objects.create(
        po_number="PO-REM-002",
        version=1,
        vendor=defect_test_data["vendor_active"],
        cost_center=defect_test_data["cost_center"],
        status=PurchaseOrder.STATUS_ISSUED,
        total_amount=Decimal("1000.00"),
    )

    client = APIClient()
    client.force_authenticate(user=defect_test_data["proc_exec"])

    res = client.patch(f"/api/v1/purchase-orders/{po.id}/", {"terms_and_conditions": "New Terms"})
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    res = client.delete(f"/api/v1/purchase-orders/{po.id}/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_def_021_022_receipt_quantity_and_over_receipt_validation(defect_test_data):
    """
    DEF-021, DEF-022: Over-receipt and negative receipt quantities return 400.
    """
    po = PurchaseOrder.objects.create(
        po_number="PO-REM-003",
        version=1,
        vendor=defect_test_data["vendor_active"],
        cost_center=defect_test_data["cost_center"],
        status=PurchaseOrder.STATUS_ISSUED,
        total_amount=Decimal("1000.00"),
    )
    line = POLine.objects.create(
        po=po,
        item_description="Storage Unit",
        quantity=Decimal("10"),
        unit_price=Decimal("100.00"),
    )

    client = APIClient()
    client.force_authenticate(user=defect_test_data["admin_user"])

    # Over receipt (15 > 10)
    res = client.post(
        "/api/v1/receipts/",
        {
            "purchase_order": po.id,
            "po_line": line.id,
            "quantity_received": 15,
            "quantity_accepted": 15,
        },
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # Non-positive receipt
    res = client.post(
        "/api/v1/receipts/",
        {
            "purchase_order": po.id,
            "po_line": line.id,
            "quantity_received": 0,
            "quantity_accepted": 0,
        },
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_def_027_028_029_invoice_paid_modification_match_blocked(defect_test_data):
    """
    DEF-027, DEF-028, DEF-029: Modifying, deleting, or re-running match on PAID invoice returns 400.
    """
    today = timezone.now().date()
    po = PurchaseOrder.objects.create(
        po_number="PO-REM-004",
        version=1,
        vendor=defect_test_data["vendor_active"],
        cost_center=defect_test_data["cost_center"],
        status=PurchaseOrder.STATUS_ISSUED,
        total_amount=Decimal("1000.00"),
    )
    inv = SupplierInvoice.objects.create(
        invoice_number="INV-PAID-01",
        vendor=defect_test_data["vendor_active"],
        po=po,
        invoice_date=today,
        due_date=today + timezone.timedelta(days=30),
        subtotal=Decimal("1000.00"),
        total_amount=Decimal("1000.00"),
        status=SupplierInvoice.STATUS_PAID,
    )

    client = APIClient()
    client.force_authenticate(user=defect_test_data["finance_user"])

    res = client.patch(f"/api/v1/invoices/{inv.id}/", {"notes": "Trying to modify paid invoice"})
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    res = client.delete(f"/api/v1/invoices/{inv.id}/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    res = client.post(f"/api/v1/invoices/{inv.id}/run-match/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot re-run 3-way matching" in str(res.data)


@pytest.mark.django_db
def test_def_030_match_exception_vendor_isolation(defect_test_data):
    """
    DEF-030: Vendor user querying match exceptions sees only their own vendor exceptions.
    """
    today = timezone.now().date()
    po1 = PurchaseOrder.objects.create(
        po_number="PO-REM-005",
        version=1,
        vendor=defect_test_data["vendor_active"],
        cost_center=defect_test_data["cost_center"],
        status=PurchaseOrder.STATUS_ISSUED,
        total_amount=Decimal("100.00"),
    )
    inv1 = SupplierInvoice.objects.create(
        invoice_number="INV-VND-01",
        vendor=defect_test_data["vendor_active"],
        po=po1,
        invoice_date=today,
        due_date=today + timezone.timedelta(days=30),
        subtotal=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        status=SupplierInvoice.STATUS_EXCEPTION,
    )
    exc1 = MatchException.objects.create(
        invoice=inv1,
        exception_type=MatchException.TYPE_PRICE_VARIANCE,
        description="Vendor 1 Price Variance",
    )

    po2 = PurchaseOrder.objects.create(
        po_number="PO-REM-006",
        version=1,
        vendor=defect_test_data["other_vendor"],
        cost_center=defect_test_data["cost_center"],
        status=PurchaseOrder.STATUS_ISSUED,
        total_amount=Decimal("100.00"),
    )
    inv2 = SupplierInvoice.objects.create(
        invoice_number="INV-OTH-01",
        vendor=defect_test_data["other_vendor"],
        po=po2,
        invoice_date=today,
        due_date=today + timezone.timedelta(days=30),
        subtotal=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        status=SupplierInvoice.STATUS_EXCEPTION,
    )
    exc2 = MatchException.objects.create(
        invoice=inv2,
        exception_type=MatchException.TYPE_PRICE_VARIANCE,
        description="Other Vendor Variance",
    )

    client = APIClient()
    client.force_authenticate(user=defect_test_data["vendor_user"])

    res = client.get("/api/v1/invoices/exceptions/")
    assert res.status_code == status.HTTP_200_OK
    results = res.data.get("results", res.data)
    exception_ids = [e["id"] for e in results]
    assert str(exc1.id) in exception_ids
    assert str(exc2.id) not in exception_ids


@pytest.mark.django_db
def test_def_034_035_contract_draft_only_modification_and_deletion(defect_test_data):
    """
    DEF-034, DEF-035: Modifying or deleting ACTIVE contract returns 400.
    """
    contract = Contract.objects.create(
        contract_number="CON-REM-001",
        title="Active SLA Contract",
        vendor=defect_test_data["vendor_active"],
        contract_owner=defect_test_data["admin_user"],
        status=Contract.STATUS_ACTIVE,
        contract_value=Decimal("50000.00"),
        start_date=timezone.now().date(),
        end_date=timezone.now().date() + timezone.timedelta(days=365),
    )

    client = APIClient()
    client.force_authenticate(user=defect_test_data["admin_user"])

    res = client.patch(f"/api/v1/contracts/{contract.id}/", {"title": "Modifying Active Contract"})
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    res = client.delete(f"/api/v1/contracts/{contract.id}/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_def_046_audit_log_report_auditor_only(defect_test_data):
    """
    DEF-046: Non-auditor/superadmin accessing /api/v1/reports/audit-logs/ returns 403.
    """
    client = APIClient()
    client.force_authenticate(user=defect_test_data["requester"])

    res = client.get("/api/v1/reports/audit-logs/")
    assert res.status_code == status.HTTP_403_FORBIDDEN

    client.force_authenticate(user=defect_test_data["auditor"])
    res = client.get("/api/v1/reports/audit-logs/")
    assert res.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_def_056_approval_step_api(defect_test_data):
    """
    DEF-056: ApprovalStep endpoint is available under /api/v1/approvals/steps/ and allows step creation.
    """
    policy = ApprovalPolicy.objects.create(
        name="PR Rem Policy",
        module="REQUISITION",
        min_amount=Decimal("0.00"),
    )
    client = APIClient()
    client.force_authenticate(user=defect_test_data["admin_user"])
    res = client.post(
        "/api/v1/approvals/steps/",
        {
            "policy": str(policy.id),
            "step_number": 1,
            "approver_role": str(defect_test_data["dept_approver"].role.id),
            "description": "Step 1 Dept Approval",
        },
        format="json",
    )
    assert res.status_code == status.HTTP_201_CREATED
    assert ApprovalStep.objects.filter(policy=policy, step_number=1).exists()


def test_def_051_unhandled_exception_returns_json():
    """
    DEF-051: Unhandled exceptions return standardized JSON error rather than HTML debug page.
    """
    from apps.core.exceptions import custom_exception_handler
    exc = Exception("Simulated unhandled system crash")
    response = custom_exception_handler(exc, {})
    assert response is not None
    assert response.status_code == 500
    assert response.data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "Simulated unhandled system crash" in response.data["error"]["details"]

