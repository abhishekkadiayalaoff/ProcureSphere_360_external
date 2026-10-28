import pytest
from decimal import Decimal
from django.utils import timezone
from rest_framework import status
from apps.accounts.models import Role, User
from apps.organization.models import Organization, Department, CostCenter
from apps.vendors.models import Vendor, VendorCategory
from apps.requisitions.models import PurchaseRequisition, PRLine
from apps.sourcing.models import SourcingEvent, VendorBid
from apps.orders.models import PurchaseOrder, POLine
from apps.receipts.models import GoodsReceipt, ReceiptLine
from apps.invoices.models import SupplierInvoice, InvoiceLine, MatchException
from apps.approvals.models import ApprovalAction


@pytest.fixture
def base_setup(db):
    org = Organization.objects.create(name="Enterprise Org", code="ENT_ORG")
    dept = Department.objects.create(organization=org, name="Procurement", code="PROC_DEPT")
    cc = CostCenter.objects.create(department=dept, code="CC_PROC", name="Procurement CC")

    superadmin_role, _ = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})
    pm_role, _ = Role.objects.get_or_create(code=Role.PROC_MGR, defaults={"name": "Procurement Manager"})
    req_role, _ = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})
    stores_role, _ = Role.objects.get_or_create(code=Role.STORES_RECEIVER, defaults={"name": "Stores Receiver"})
    finance_role, _ = Role.objects.get_or_create(code=Role.FINANCE_AP, defaults={"name": "Finance AP"})
    vendor_role, _ = Role.objects.get_or_create(code=Role.VENDOR_USER, defaults={"name": "Vendor User"})

    admin_user = User.objects.create_superuser(email="admin@test.com", password="Pass123!Password")
    pm_user = User.objects.create_user(email="pm@test.com", password="Pass123!Password", role=pm_role, department=dept)
    req_user = User.objects.create_user(email="req@test.com", password="Pass123!Password", role=req_role, department=dept, cost_center=cc)
    stores_user = User.objects.create_user(email="stores@test.com", password="Pass123!Password", role=stores_role, department=dept)
    finance_user = User.objects.create_user(email="finance@test.com", password="Pass123!Password", role=finance_role, department=dept)

    cat = VendorCategory.objects.create(code="IT", name="IT")
    vendor = Vendor.objects.create(legal_name="Acme Corp", vendor_number="VND-001", status="ACTIVE", category=cat, created_by=admin_user)
    vendor_user = User.objects.create_user(email="vendor@test.com", password="Pass123!Password", role=vendor_role, vendor=vendor)

    return {
        "org": org,
        "dept": dept,
        "cc": cc,
        "admin": admin_user,
        "pm": pm_user,
        "req": req_user,
        "stores": stores_user,
        "finance": finance_user,
        "vendor": vendor,
        "vendor_user": vendor_user,
    }


def test_tc_063_approvals_action_reject_missing_reason(client, base_setup):
    """TC-063: Missing rejection reason in approval action rejection must return 400 Bad Request."""
    action = ApprovalAction.objects.create(
        target_object_id=str(base_setup["vendor"].id),
        target_model_name="Vendor",
        actor=base_setup["pm"],
        action="PENDING",
        comments="Initial submission",
    )
    client.force_login(base_setup["pm"])
    res = client.post(
        f"/api/v1/approvals/actions/{action.id}/reject/",
        data={"reason": ""},
        content_type="application/json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Rejection comments are mandatory" in str(res.data)


def test_tc_073_requisition_approve_missing_comments(client, base_setup):
    """TC-073: Missing approval comments in PR approval must return 400 Bad Request."""
    pr = PurchaseRequisition.objects.create(
        pr_number="PR-FIX-001",
        title="Laptops",
        justification="Engineering expansion",
        requester=base_setup["req"],
        department=base_setup["dept"],
        cost_center=base_setup["cc"],
        status=PurchaseRequisition.STATUS_SUBMITTED,
        total_amount=Decimal("1500.00"),
        requested_delivery_date=timezone.now().date(),
    )
    client.force_login(base_setup["pm"])
    res = client.post(
        f"/api/v1/requisitions/{pr.id}/approve/",
        data={"comments": ""},
        content_type="application/json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Approval comments / justification are mandatory" in str(res.data)


def test_tc_077_requisition_cancel_non_draft(client, base_setup):
    """TC-077: Cancelling an already approved or submitted PR must return 400 Bad Request."""
    pr = PurchaseRequisition.objects.create(
        pr_number="PR-FIX-002",
        title="Monitors",
        justification="Hardware refresh",
        requester=base_setup["req"],
        department=base_setup["dept"],
        cost_center=base_setup["cc"],
        status=PurchaseRequisition.STATUS_APPROVED,
        total_amount=Decimal("800.00"),
        requested_delivery_date=timezone.now().date(),
    )
    client.force_login(base_setup["req"])
    res = client.post(
        f"/api/v1/requisitions/{pr.id}/cancel/",
        data={"reason": "No longer needed"},
        content_type="application/json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot cancel requisition in 'APPROVED' status" in str(res.data)


def test_tc_091_po_acknowledge_missing_notes(client, base_setup):
    """TC-091: PO acknowledgement without notes must return 400 Bad Request."""
    po = PurchaseOrder.objects.create(
        po_number="PO-FIX-001",
        vendor=base_setup["vendor"],
        cost_center=base_setup["cc"],
        status=PurchaseOrder.STATUS_ISSUED,
        created_by=base_setup["pm"],
        total_amount=Decimal("1200.00"),
    )
    client.force_login(base_setup["vendor_user"])
    res = client.post(
        f"/api/v1/purchase-orders/{po.id}/acknowledge/",
        data={"acknowledgement_notes": ""},
        content_type="application/json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Acknowledgement notes are required" in str(res.data)


def test_tc_103_receipts_handoff_missing_storage_location(client, base_setup):
    """TC-103: Receipts stock handoff without storage location must return 400 Bad Request."""
    po = PurchaseOrder.objects.create(
        po_number="PO-FIX-002",
        vendor=base_setup["vendor"],
        cost_center=base_setup["cc"],
        status=PurchaseOrder.STATUS_ISSUED,
        created_by=base_setup["pm"],
        total_amount=Decimal("1200.00"),
    )
    grn = GoodsReceipt.objects.create(
        grn_number="GRN-FIX-001",
        po=po,
        received_by=base_setup["stores"],
        received_date=timezone.now(),
    )
    client.force_login(base_setup["stores"])
    res = client.post(
        f"/api/v1/receipts/{grn.id}/handoff/",
        data={"storage_location": ""},
        content_type="application/json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Storage location is required" in str(res.data)


def test_tc_107_invoice_run_match_invalid_status(client, base_setup):
    """TC-107: Running 3-way match on PAID or REJECTED invoice must return 400 Bad Request."""
    po = PurchaseOrder.objects.create(
        po_number="PO-FIX-003",
        vendor=base_setup["vendor"],
        cost_center=base_setup["cc"],
        status=PurchaseOrder.STATUS_ISSUED,
        created_by=base_setup["pm"],
        total_amount=Decimal("1200.00"),
    )
    invoice = SupplierInvoice.objects.create(
        invoice_number="INV-FIX-001",
        vendor=base_setup["vendor"],
        po=po,
        status=SupplierInvoice.STATUS_PAID,
        subtotal=Decimal("1000.00"),
        total_amount=Decimal("1000.00"),
        invoice_date=timezone.now().date(),
        due_date=timezone.now().date(),
    )
    client.force_login(base_setup["finance"])
    res = client.post(
        f"/api/v1/invoices/{invoice.id}/run-match/",
        content_type="application/json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot run 3-way match on invoice in status 'PAID'" in str(res.data)


def test_tc_111_invoice_resolve_exception_validation_and_routing(client, base_setup):
    """TC-111: Resolving match exception requires notes and works via both nested and flat URLs."""
    po = PurchaseOrder.objects.create(
        po_number="PO-FIX-004",
        vendor=base_setup["vendor"],
        cost_center=base_setup["cc"],
        status=PurchaseOrder.STATUS_ISSUED,
        created_by=base_setup["pm"],
        total_amount=Decimal("1200.00"),
    )
    invoice = SupplierInvoice.objects.create(
        invoice_number="INV-FIX-002",
        vendor=base_setup["vendor"],
        po=po,
        status=SupplierInvoice.STATUS_EXCEPTION,
        subtotal=Decimal("1000.00"),
        total_amount=Decimal("1000.00"),
        invoice_date=timezone.now().date(),
        due_date=timezone.now().date(),
    )
    exc = MatchException.objects.create(
        invoice=invoice,
        exception_type=MatchException.TYPE_PRICE_VARIANCE,
        status=MatchException.STATUS_OPEN,
        description="Price variance",
    )
    client.force_login(base_setup["finance"])

    # Nested URL without notes -> 400
    res_nested_empty = client.post(
        f"/api/v1/invoices/{invoice.id}/exceptions/{exc.id}/resolve/",
        data={"resolution_notes": ""},
        content_type="application/json",
    )
    assert res_nested_empty.status_code == status.HTTP_400_BAD_REQUEST
    assert "Resolution notes are required" in str(res_nested_empty.data)

    # Flat URL without notes -> 400
    res_flat_empty = client.post(
        f"/api/v1/invoices/exceptions/{exc.id}/resolve/",
        data={"resolution_notes": ""},
        content_type="application/json",
    )
    assert res_flat_empty.status_code == status.HTTP_400_BAD_REQUEST
    assert "Resolution notes are required" in str(res_flat_empty.data)

    # Valid resolve via nested URL -> 200
    res_valid = client.post(
        f"/api/v1/invoices/{invoice.id}/exceptions/{exc.id}/resolve/",
        data={"resolution_notes": "Variance within acceptable threshold approved by Finance."},
        content_type="application/json",
    )
    assert res_valid.status_code == status.HTTP_200_OK


def test_tc_083_sourcing_award_approve_flat_and_nested_urls(client, base_setup):
    """TC-083 to 086: Award approve works via both /events/{id}/award-approve/ and /{id}/award-approve/."""
    event = SourcingEvent.objects.create(
        event_number="SE-FIX-001",
        title="RFQ Sourcing",
        event_type="RFQ",
        status=SourcingEvent.STATUS_AWARD_APPROVAL,
        bid_start_date=timezone.now(),
        bid_end_date=timezone.now() + timezone.timedelta(days=7),
        description="Test RFQ",
        created_by=base_setup["pm"],
    )
    client.force_login(base_setup["pm"])

    # Flat URL missing winning bid -> 400
    res_flat = client.post(
        f"/api/v1/sourcing-events/{event.id}/award-approve/",
        data={"action": "APPROVE"},
        content_type="application/json",
    )
    assert res_flat.status_code == status.HTTP_400_BAD_REQUEST
    assert "A valid submitted winning bid must be selected" in str(res_flat.data)

    # Nested URL invalid action -> 400
    res_nested = client.post(
        f"/api/v1/sourcing-events/events/{event.id}/award-approve/",
        data={"action": "INVALID_ACTION"},
        content_type="application/json",
    )
    assert res_nested.status_code == status.HTTP_400_BAD_REQUEST
    assert "Supported actions: APPROVE, REJECT, RETURN" in str(res_nested.data)
