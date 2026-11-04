from decimal import Decimal
import os
import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.budgets.models import Budget
from apps.contracts.models import Contract
from apps.invoices.models import PaymentStatus, SupplierInvoice
from apps.invoices.services import create_supplier_invoice_service, mark_invoice_paid_service
from apps.orders.models import POLine, PurchaseOrder
from apps.orders.services import amend_purchase_order_service, generate_purchase_order_service
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.receipts.models import GoodsReceipt
from apps.requisitions.models import PurchaseRequisition
from apps.requisitions.services import (
    approve_purchase_requisition_service,
    create_purchase_requisition_service,
    submit_purchase_requisition_service,
)
from apps.vendors.models import Vendor, VendorCategory, VendorDocument


@pytest.fixture
def remediation_setup(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

    org = Organization.objects.create(name="HPE Global", code="HPE-REM")
    dept_it = Department.objects.create(name="IT Operations", code="IT-REM", organization=org)
    dept_hr = Department.objects.create(name="HR Operations", code="HR-REM", organization=org)

    cc_it = CostCenter.objects.create(name="IT Infrastructure", code="CC-IT-REM", department=dept_it)
    cc_hr = CostCenter.objects.create(name="HR Recruitment", code="CC-HR-REM", department=dept_hr)

    fiscal_period = FiscalPeriod.objects.create(
        organization=org, year=2026, period_number=1, name="Q1-2026",
        start_date="2026-01-01", end_date="2026-03-31"
    )

    budget_it = Budget.objects.create(
        cost_center=cc_it, fiscal_period=fiscal_period, allocated_amount=Decimal("100000.00")
    )
    budget_hr = Budget.objects.create(
        cost_center=cc_hr, fiscal_period=fiscal_period, allocated_amount=Decimal("50000.00")
    )

    category = VendorCategory.objects.create(name="Hardware", code="CAT-HW-REM")

    # Roles
    role_admin, _ = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})
    role_req, _ = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})
    role_approver, _ = Role.objects.get_or_create(code=Role.DEPT_APPROVER, defaults={"name": "Dept Approver"})
    role_procexec, _ = Role.objects.get_or_create(code=Role.PROC_EXEC, defaults={"name": "Proc Exec"})
    role_procmgr, _ = Role.objects.get_or_create(code=Role.PROC_MGR, defaults={"name": "Proc Mgr"})
    role_finance, _ = Role.objects.get_or_create(code=Role.FINANCE_AP, defaults={"name": "Finance AP"})
    role_stores, _ = Role.objects.get_or_create(code=Role.STORES_RECEIVER, defaults={"name": "Stores Receiver"})
    role_legal, _ = Role.objects.get_or_create(code=Role.LEGAL_MGR, defaults={"name": "Legal Manager"})
    role_vendor, _ = Role.objects.get_or_create(code=Role.VENDOR_USER, defaults={"name": "Vendor User"})

    # Users
    admin = User.objects.create_user(
        email="admin.rem@test.local", password="Password123!", role=role_admin, is_staff=True, is_superuser=True
    )
    requester = User.objects.create_user(
        email="req.it@test.local", password="Password123!", role=role_req, department=dept_it, cost_center=cc_it
    )
    approver = User.objects.create_user(
        email="app.it@test.local", password="Password123!", role=role_approver, department=dept_it
    )
    proc_exec = User.objects.create_user(
        email="exec.rem@test.local", password="Password123!", role=role_procexec, organization=org
    )
    proc_mgr = User.objects.create_user(
        email="mgr.rem@test.local", password="Password123!", role=role_procmgr, organization=org
    )
    finance = User.objects.create_user(
        email="fin.rem@test.local", password="Password123!", role=role_finance, organization=org
    )
    stores = User.objects.create_user(
        email="stores.rem@test.local", password="Password123!", role=role_stores, organization=org
    )
    legal = User.objects.create_user(
        email="legal.rem@test.local", password="Password123!", role=role_legal, organization=org
    )

    vendor_active = Vendor.objects.create(
        vendor_number="VEN-REM-01", legal_name="Cisco Global",
        tax_identification_number="TIN-REM-01", category=category, organization=org,
        status=Vendor.STATUS_ACTIVE,
    )
    vendor_draft = Vendor.objects.create(
        vendor_number="VEN-REM-02", legal_name="Draft Supplier",
        tax_identification_number="TIN-REM-02", category=category, organization=org,
        status=Vendor.STATUS_DRAFT,
    )
    vendor_suspended = Vendor.objects.create(
        vendor_number="VEN-REM-03", legal_name="Suspended Supplier",
        tax_identification_number="TIN-REM-03", category=category, organization=org,
        status=Vendor.STATUS_SUSPENDED,
    )

    vendor_user = User.objects.create_user(
        email="user@cisco.test", password="Password123!", role=role_vendor, vendor=vendor_active
    )

    # Documents
    doc_rel = "vendor_docs/cisco_tax.pdf"
    doc_abs = os.path.join(settings.MEDIA_ROOT, doc_rel)
    os.makedirs(os.path.dirname(doc_abs), exist_ok=True)
    with open(doc_abs, "wb") as f:
        f.write(b"%PDF-1.4 Cisco Tax Verification Document")

    VendorDocument.objects.create(
        vendor=vendor_active, document_type=VendorDocument.DOC_TYPE_TAX,
        title="Cisco Tax Clearance", file=doc_rel,
    )

    contract_rel = "contracts/sla_cisco.pdf"
    contract_abs = os.path.join(settings.MEDIA_ROOT, contract_rel)
    os.makedirs(os.path.dirname(contract_abs), exist_ok=True)
    with open(contract_abs, "wb") as f:
        f.write(b"%PDF-1.4 SLA Cisco Confidential Document")

    return {
        "admin": admin,
        "requester": requester,
        "approver": approver,
        "proc_exec": proc_exec,
        "proc_mgr": proc_mgr,
        "finance": finance,
        "stores": stores,
        "legal": legal,
        "vendor_user": vendor_user,
        "vendor_active": vendor_active,
        "vendor_draft": vendor_draft,
        "vendor_suspended": vendor_suspended,
        "dept_it": dept_it,
        "dept_hr": dept_hr,
        "cc_it": cc_it,
        "cc_hr": cc_hr,
        "doc_url": f"/media/{doc_rel}",
        "contract_url": f"/media/{contract_rel}",
    }


# ─── DEF-001, DEF-002, DEF-003 Tests ──────────────────────────────────────────

def test_def_001_demo_roles_are_not_superuser(remediation_setup):
    """DEF-001: Non-superadmin users must not have is_superuser or is_staff."""
    for role_name in ["requester", "approver", "proc_exec", "proc_mgr", "finance", "stores", "legal", "vendor_user"]:
        user = remediation_setup[role_name]
        assert not user.is_superuser, f"{role_name} has is_superuser=True"
        assert not user.is_staff, f"{role_name} has is_staff=True"

    assert remediation_setup["admin"].is_superuser
    assert remediation_setup["admin"].is_staff


def test_def_002_media_unauthenticated_and_traversal_blocked(client, remediation_setup):
    """DEF-002: Anonymous users and directory traversal are rejected on media files."""
    resp = client.get(remediation_setup["doc_url"])
    assert resp.status_code in [401, 403]

    client.force_login(remediation_setup["requester"])
    resp_trav = client.get("/media/../etc/passwd")
    assert resp_trav.status_code in [403, 404]


def test_def_003_vendor_blocked_from_internal_staff_pages(client, remediation_setup):
    """DEF-003: Vendor users receive 403 when trying to access internal staff UI and API routes."""
    client.force_login(remediation_setup["vendor_user"])

    for url in ["/requisitions/", "/contracts/", "/orders/", "/invoices/", "/budgets/", "/reports/"]:
        resp = client.get(url)
        assert resp.status_code == 403, f"Vendor improperly accessed {url}"

    for api_url in ["/api/v1/requisitions/", "/api/v1/contracts/", "/api/v1/budgets/", "/api/v1/reports/"]:
        resp = client.get(api_url)
        assert resp.status_code == 403
        assert resp.json().get("error", {}).get("code") == "FORBIDDEN"


# ─── DEF-004, DEF-006 Tests ───────────────────────────────────────────────────

def test_def_004_requester_budget_queryset_scoping(remediation_setup):
    """DEF-004: Requester only sees their own cost center budget via API."""
    client = APIClient()
    client.force_authenticate(user=remediation_setup["requester"])
    resp = client.get("/api/v1/budgets/")
    assert resp.status_code == 200
    results = resp.json().get("results", resp.json())
    cc_ids = [r["cost_center"] for r in results]
    assert str(remediation_setup["cc_it"].id) in cc_ids
    assert str(remediation_setup["cc_hr"].id) not in cc_ids  # Other department budget excluded!


def test_def_006_proc_exec_cannot_create_contracts(remediation_setup):
    """DEF-006: Procurement Executive cannot POST contracts via API (403 Forbidden)."""
    client = APIClient()
    client.force_authenticate(user=remediation_setup["proc_exec"])
    resp = client.post("/api/v1/contracts/", {
        "title": "Unauthorized Contract",
        "vendor": str(remediation_setup["vendor_active"].id),
        "contract_value": "10000.00",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
    })
    assert resp.status_code == 403


# ─── DEF-008, DEF-009, DEF-010, DEF-011 Tests ────────────────────────────────

def test_def_008_cannot_create_po_for_inactive_or_draft_vendor(remediation_setup):
    """DEF-008: PO creation for DRAFT or SUSPENDED vendor is blocked."""
    client = APIClient()
    client.force_authenticate(user=remediation_setup["proc_exec"])

    # Attempt PO for draft vendor
    resp_draft = client.post("/api/v1/purchase-orders/", {
        "vendor": str(remediation_setup["vendor_draft"].id),
        "cost_center": str(remediation_setup["cc_it"].id),
        "lines": [{"item_description": "Widget", "quantity": "10", "unit_price": "50.00"}],
    }, format="json")
    assert resp_draft.status_code == 400

    # Attempt PO for suspended vendor
    resp_susp = client.post("/api/v1/purchase-orders/", {
        "vendor": str(remediation_setup["vendor_suspended"].id),
        "cost_center": str(remediation_setup["cc_it"].id),
        "lines": [{"item_description": "Widget", "quantity": "10", "unit_price": "50.00"}],
    }, format="json")
    assert resp_susp.status_code == 400


def test_def_009_negative_line_items_on_po_rejected(remediation_setup):
    """DEF-009: Negative line item quantities or unit prices on POs are rejected."""
    client = APIClient()
    client.force_authenticate(user=remediation_setup["proc_exec"])

    resp_neg_qty = client.post("/api/v1/purchase-orders/", {
        "vendor": str(remediation_setup["vendor_active"].id),
        "cost_center": str(remediation_setup["cc_it"].id),
        "lines": [{"item_description": "Bad Line", "quantity": "-5", "unit_price": "10.00"}],
    }, format="json")
    assert resp_neg_qty.status_code == 400

    resp_neg_price = client.post("/api/v1/purchase-orders/", {
        "vendor": str(remediation_setup["vendor_active"].id),
        "cost_center": str(remediation_setup["cc_it"].id),
        "lines": [{"item_description": "Bad Price", "quantity": "5", "unit_price": "-10.00"}],
    }, format="json")
    assert resp_neg_price.status_code == 400


def test_def_010_over_receipt_on_goods_receipt_rejected(remediation_setup):
    """DEF-010: Goods Receipt cannot exceed remaining quantity on PO line."""
    po = generate_purchase_order_service(
        vendor=remediation_setup["vendor_active"],
        cost_center=remediation_setup["cc_it"],
        line_items=[{"item_description": "Network Router", "quantity": 10, "unit_price": 500.00}],
        created_by_user=remediation_setup["proc_exec"],
    )
    po_line = po.lines.first()

    client = APIClient()
    client.force_authenticate(user=remediation_setup["stores"])

    # Over-receive 15 when ordered quantity is 10
    resp_over = client.post("/api/v1/receipts/", {
        "po": str(po.id),
        "lines": [{"po_line_id": str(po_line.id), "quantity_received": "15"}],
    }, format="json")
    assert resp_over.status_code == 400


def test_def_011_po_amendment_blocked_on_cancelled_or_draft_po(remediation_setup):
    """DEF-011: PO amendment cannot be submitted on CANCELLED or DRAFT POs."""
    po = generate_purchase_order_service(
        vendor=remediation_setup["vendor_active"],
        cost_center=remediation_setup["cc_it"],
        line_items=[{"item_description": "Network Router", "quantity": 5, "unit_price": 500.00}],
        created_by_user=remediation_setup["proc_exec"],
    )
    po.status = PurchaseOrder.STATUS_CANCELLED
    po.save(update_fields=["status"])

    client = APIClient()
    client.force_authenticate(user=remediation_setup["proc_exec"])

    resp = client.post(f"/api/v1/purchase-orders/{po.id}/amend/", {
        "reason": "Attempt amendment on cancelled PO",
    }, format="json")
    assert resp.status_code == 400


# ─── DEF-014, DEF-017, DEF-018 Tests ──────────────────────────────────────────

def test_def_014_invoice_creation_with_uuid_string_returns_201_no_500(remediation_setup):
    """DEF-014: POST /api/v1/invoices/create-invoice/ with string po_line UUID succeeds without 500."""
    po = generate_purchase_order_service(
        vendor=remediation_setup["vendor_active"],
        cost_center=remediation_setup["cc_it"],
        line_items=[{"item_description": "Switch Port", "quantity": 10, "unit_price": 100.00}],
        created_by_user=remediation_setup["proc_exec"],
    )
    po_line = po.lines.first()

    client = APIClient()
    client.force_authenticate(user=remediation_setup["finance"])

    resp = client.post("/api/v1/invoices/create-invoice/", {
        "vendor_id": str(remediation_setup["vendor_active"].id),
        "po_id": str(po.id),
        "invoice_number": "INV-TEST-014",
        "invoice_date": "2026-03-01",
        "due_date": "2026-03-31",
        "line_items": [
            {
                "po_line": str(po_line.id),  # String UUID!
                "quantity": 10,
                "unit_price": 100.00,
            }
        ],
    }, format="json")

    assert resp.status_code == 201, f"Expected 201 Created but received {resp.status_code}: {resp.data}"
    assert resp.data["invoice_number"] == "INV-TEST-014"


def test_def_017_invoice_marked_paid_creates_payment_status_record(remediation_setup):
    """DEF-017: Marking an invoice paid creates a PaymentStatus record with transaction reference."""
    po = generate_purchase_order_service(
        vendor=remediation_setup["vendor_active"],
        cost_center=remediation_setup["cc_it"],
        line_items=[{"item_description": "Power Cable", "quantity": 10, "unit_price": 20.00}],
        created_by_user=remediation_setup["proc_exec"],
    )
    invoice = create_supplier_invoice_service(
        vendor=remediation_setup["vendor_active"],
        po=po,
        invoice_number="INV-PAY-017",
        invoice_date="2026-03-01",
        due_date="2026-03-31",
        line_items=[{"po_line": po.lines.first(), "quantity": 10, "unit_price": 20.00}],
        created_by_user=remediation_setup["finance"],
    )
    invoice.status = SupplierInvoice.STATUS_READY_FOR_PAYMENT
    invoice.save(update_fields=["status"])

    # Mark paid with payment reference
    mark_invoice_paid_service(
        invoice=invoice,
        user=remediation_setup["finance"],
        payment_reference="UTR-HPE-20260301-9988",
        payment_method="NEFT_RTGS",
    )
    invoice.refresh_from_db()
    assert invoice.status == SupplierInvoice.STATUS_PAID

    payment = PaymentStatus.objects.filter(invoice=invoice).first()
    assert payment is not None, "PaymentStatus record was not created!"
    assert payment.payment_reference == "UTR-HPE-20260301-9988"
    assert payment.payment_method == "NEFT_RTGS"
    assert payment.amount_paid == invoice.total_amount


def test_def_018_pr_creation_rejects_mismatched_cost_center(remediation_setup):
    """DEF-018: Creating a PR with a CostCenter that doesn't belong to the Department is rejected."""
    import pytest
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="does not belong to Department"):
        create_purchase_requisition_service(
            title="Mismatched PR",
            justification="Testing mismatched cost center",
            requester=remediation_setup["requester"],
            department=remediation_setup["dept_hr"],  # HR Department
            cost_center=remediation_setup["cc_it"],   # IT Cost Center (Mismatch!)
            requested_delivery_date="2026-04-01",
            line_items=[{"item_description": "Item", "quantity": 1, "estimated_unit_price": 100.00}],
        )
