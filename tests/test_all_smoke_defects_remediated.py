import json
import os
from decimal import Decimal

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.approvals.models import ApprovalAction, ApprovalPolicy
from apps.audit.models import AuditLog
from apps.budgets.models import Budget
from apps.contracts.models import Contract
from apps.invoices.models import SupplierInvoice
from apps.orders.models import POLine, PurchaseOrder
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.receipts.models import GoodsReceipt
from apps.requisitions.models import PRLine, PurchaseRequisition
from apps.sourcing.models import BidInvite, BidLine, SourcingEvent, VendorBid
from apps.vendors.models import Vendor, VendorDocument


@pytest.fixture
def rbac_setup(db):
    """Sets up standard roles, test organization, departments, and users."""
    roles_data = [
        (Role.SUPER_ADMIN, "Super Admin"),
        (Role.REQUESTER, "Requester"),
        (Role.DEPT_APPROVER, "Department Approver"),
        (Role.PROC_EXEC, "Procurement Executive"),
        (Role.PROC_MGR, "Procurement Manager"),
        (Role.FINANCE_AP, "Finance / AP"),
        (Role.STORES_RECEIVER, "Stores Receiver"),
        (Role.LEGAL_MGR, "Legal Manager"),
        (Role.AUDITOR, "Auditor"),
        (Role.VENDOR_USER, "Vendor User"),
    ]
    roles = {}
    for code, name in roles_data:
        r, _ = Role.objects.get_or_create(code=code, defaults={"name": name})
        roles[code] = r

    org, _ = Organization.objects.get_or_create(code="HPE", defaults={"name": "HPE Corp"})
    dept, _ = Department.objects.get_or_create(code="IT", organization=org, defaults={"name": "IT Dept"})
    cc, _ = CostCenter.objects.get_or_create(code="CC-IT", department=dept, defaults={"name": "IT Compute"})
    fp, _ = FiscalPeriod.objects.get_or_create(
        organization=org,
        year=2026,
        period_number=1,
        defaults={
            "name": "2026-Q1",
            "start_date": timezone.now().date(),
            "end_date": timezone.now().date() + timezone.timedelta(days=90),
        },
    )

    budget, _ = Budget.objects.get_or_create(
        cost_center=cc,
        fiscal_period=fp,
        defaults={
            "allocated_amount": Decimal("100000.00"),
            "committed_amount": Decimal("0.00"),
            "actual_amount": Decimal("0.00"),
        },
    )

    from apps.vendors.models import VendorCategory
    cat, _ = VendorCategory.objects.get_or_create(code="IT-SERV", defaults={"name": "IT Services"})

    import uuid
    # Active vendor
    uid1 = str(uuid.uuid4())[:8]
    uid2 = str(uuid.uuid4())[:8]
    vendor, _ = Vendor.objects.get_or_create(
        organization=org,
        vendor_number=f"VEN-{uid1}",
        defaults={
            "legal_name": "Acme Corp",
            "category": cat,
            "tax_identification_number": f"TAX-{uid1}",
            "status": Vendor.STATUS_ACTIVE,
        },
    )

    # Draft vendor
    draft_vendor, _ = Vendor.objects.get_or_create(
        organization=org,
        vendor_number=f"VEN-DRAFT-{uid2}",
        defaults={
            "legal_name": "Draft Supplier Ltd",
            "category": cat,
            "tax_identification_number": f"TAX-{uid2}",
            "status": Vendor.STATUS_DRAFT,
        },
    )
    if not draft_vendor.category:
        draft_vendor.category = cat
        draft_vendor.save()

    users = {}
    for code in roles:
        u, _ = User.objects.get_or_create(
            email=f"qa.{code.lower()}@example.test",
            defaults={
                "username": f"qa.{code.lower()}@example.test",
                "role": roles[code],
                "organization": org,
                "department": dept,
                "is_superuser": (code == Role.SUPER_ADMIN),
                "is_staff": (code == Role.SUPER_ADMIN),
            },
        )
        u.role = roles[code]
        u.is_superuser = (code == Role.SUPER_ADMIN)
        u.is_staff = (code == Role.SUPER_ADMIN)
        if code == Role.VENDOR_USER:
            u.vendor = vendor
        u.save()
        users[code] = u

    return {
        "roles": roles,
        "org": org,
        "dept": dept,
        "cc": cc,
        "fp": fp,
        "budget": budget,
        "vendor": vendor,
        "draft_vendor": draft_vendor,
        "users": users,
    }


@pytest.mark.django_db
class TestSmokeDefectsRemediated:
    """Systematic independent verification of all 39 smoke test cases across 25 defects."""

    # ──────────────────────────────────────────────────────────────────────────
    # Group A: Startup & Health (TC-SUP-031 / DEF-017)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_sup_031_unknown_ui_url_clean_404(self):
        """TC-SUP-031: Unknown UI URL returns clean HTTP 404 without debug trace/URLconf leak."""
        client = Client()
        response = client.get("/this-page-does-not-exist/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        content = response.content.decode("utf-8", errors="ignore")
        assert "Traceback (most recent call last)" not in content
        assert "Using the URLconf defined in" not in content

    # ──────────────────────────────────────────────────────────────────────────
    # Group B: Authentication (TC-AUTH-029, TC-AUTH-031 / DEF-003, DEF-004)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_auth_029_numeric_credentials_rejected(self):
        """TC-AUTH-029: API login rejected cleanly with HTTP 400 when email/password are numbers."""
        client = Client()
        response = client.post(
            "/api/v1/auth/login/",
            data={"email": 123, "password": 456},
            content_type="application/json",
        )
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED)
        data = response.json()
        assert "Traceback" not in str(data)
        assert "AttributeError" not in str(data)

    def test_tc_auth_031_excessively_long_email_rejected(self):
        """TC-AUTH-031: API login rejected cleanly with HTTP 400 when email exceeds 254 chars."""
        client = Client()
        response = client.post(
            "/api/v1/auth/login/",
            data={"email": "a" * 5000, "password": "Password123!"},
            content_type="application/json",
        )
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED)
        data = response.json()
        assert "DataError" not in str(data)

    # ──────────────────────────────────────────────────────────────────────────
    # Group C: Users & Roles / RBAC (DEF-001, DEF-023, DEF-022, DEF-006, DEF-019, DEF-024)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_usr_025_and_tc_rbac_013_auditor_user_list_read_access(self, rbac_setup):
        """TC-USR-025 & TC-RBAC-013: Auditor has read access to the user list per RBAC matrix."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.AUDITOR])
        response = client.get("/api/v1/accounts/users/")
        assert response.status_code == status.HTTP_200_OK

    def test_tc_rbac_001_requester_cannot_list_all_system_users(self, rbac_setup):
        """TC-RBAC-001: Non-superuser Requester cannot list all system users (gets 403 or scoped)."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.REQUESTER])
        response = client.get("/api/v1/accounts/users/")
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_200_OK)
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            users_returned = data.get("results", data)
            # Must be scoped only to self, never all 800+ system users
            assert len(users_returned) <= 1

    def test_tc_rbac_002_vendor_cannot_read_audit_logs(self, rbac_setup):
        """TC-RBAC-002: Vendor user must not read system audit logs."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.VENDOR_USER])
        response = client.get("/api/v1/audit/logs/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_tc_rbac_003_finance_cannot_create_user(self, rbac_setup):
        """TC-RBAC-003: Finance user must not create users."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.FINANCE_AP])
        response = client.post(
            "/api/v1/accounts/users/",
            data={"email": "new.user@example.test", "role": str(rbac_setup["roles"][Role.REQUESTER].id)},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_tc_rbac_004_stores_receiver_cannot_list_contracts(self, rbac_setup):
        """TC-RBAC-004: Stores receiver must not list contracts."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.STORES_RECEIVER])
        response = client.get("/api/v1/contracts/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_tc_rbac_020_tc_rbac_021_approval_policies_access(self, rbac_setup):
        """TC-RBAC-020 & TC-RBAC-021: Stores receiver and Legal manager cannot read approval policies."""
        client = APIClient()
        for role_code in [Role.STORES_RECEIVER, Role.LEGAL_MGR]:
            client.force_authenticate(user=rbac_setup["users"][role_code])
            response = client.get("/api/v1/approvals/policies/")
            assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_tc_rbac_040_041_046_invoices_api_access(self, rbac_setup):
        """TC-RBAC-040, 041, 046: Requester, Dept Approver, and Legal Mgr cannot read invoices API."""
        client = APIClient()
        for role_code in [Role.REQUESTER, Role.DEPT_APPROVER, Role.LEGAL_MGR]:
            client.force_authenticate(user=rbac_setup["users"][role_code])
            response = client.get("/api/v1/invoices/")
            assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_tc_inv_041_ui_rbac_requester_cannot_open_invoice_list(self, rbac_setup):
        """TC-INV-041: UI RBAC - REQUESTER cannot open /invoices/."""
        client = Client()
        client.force_login(rbac_setup["users"][Role.REQUESTER])
        response = client.get("/invoices/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_tc_rbac_072_073_budgets_access(self, rbac_setup):
        """TC-RBAC-072 & TC-RBAC-073: Stores receiver and Legal manager cannot read budgets."""
        client = APIClient()
        for role_code in [Role.STORES_RECEIVER, Role.LEGAL_MGR]:
            client.force_authenticate(user=rbac_setup["users"][role_code])
            response = client.get("/api/v1/budgets/")
            assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_tc_rbac_088_vendor_user_can_read_own_po_goods_receipts(self, rbac_setup):
        """TC-RBAC-088: Vendor user can read goods receipts of its own POs."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.VENDOR_USER])
        response = client.get("/api/v1/receipts/")
        assert response.status_code == status.HTTP_200_OK

    # ──────────────────────────────────────────────────────────────────────────
    # Group D: Approval Workflow (TC-APR-004, TC-APR-020 / DEF-016, DEF-025)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_apr_004_policy_min_greater_than_max_rejected(self, rbac_setup):
        """TC-APR-004: Approval policy with min_amount > max_amount is rejected."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.SUPER_ADMIN])
        response = client.post(
            "/api/v1/approvals/policies/",
            data={
                "name": "Invalid Policy Range",
                "module": "PR",
                "min_amount": "5000.00",
                "max_amount": "1000.00",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_tc_apr_020_no_errordetail_repr_leak(self, rbac_setup):
        """TC-APR-020: Error responses do not leak python repr ErrorDetail(string=...)."""
        client = APIClient()
        requester = rbac_setup["users"][Role.REQUESTER]
        client.force_authenticate(user=requester)

        # Create a requisition and approval action
        pr = PurchaseRequisition.objects.create(
            pr_number="PR-TEST-APR-20",
            title="Office Supplies",
            justification="Projector",
            requester=requester,
            department=rbac_setup["dept"],
            cost_center=rbac_setup["cc"],
            total_amount=Decimal("100.00"),
            requested_delivery_date=timezone.now().date() + timezone.timedelta(days=7),
            status=PurchaseRequisition.STATUS_SUBMITTED,
        )
        action_obj = ApprovalAction.objects.create(
            target_model_name="PurchaseRequisition",
            target_object_id=str(pr.id),
            actor=requester,
            action=ApprovalAction.ACTION_APPROVE,
            comments="Self-approval attempt",
        )

        response = client.post(f"/api/v1/approvals/actions/{action_obj.id}/approve/", data={"comment": "Approve self"})
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN)
        content_str = response.content.decode("utf-8")
        assert "ErrorDetail(" not in content_str

    # ──────────────────────────────────────────────────────────────────────────
    # Group E: Purchase Requisitions (TC-REQ-003, TC-REQ-030 / DEF-015, DEF-021)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_req_003_pr_without_lines_rejected(self, rbac_setup):
        """TC-REQ-003: Requisition without lines is rejected."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.REQUESTER])
        response = client.post(
            "/api/v1/requisitions/",
            data={
                "title": "Empty PR",
                "justification": "Testing empty lines",
                "department": str(rbac_setup["dept"].id),
                "cost_center": str(rbac_setup["cc"].id),
                "lines": [],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_tc_req_030_search_query_parameter_wired(self, rbac_setup):
        """TC-REQ-030: Search with no match returns an empty page on GET /api/v1/requisitions/."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.REQUESTER])
        response = client.get("/api/v1/requisitions/?search=NONEXISTENT_KEYWORD_XYZ_9999")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data.get("results", data)
        assert len(results) == 0

    # ──────────────────────────────────────────────────────────────────────────
    # Group F: Sourcing & Bids (TC-SRC-047 / DEF-012)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_src_047_vendor_amend_negative_price_rejected(self, rbac_setup):
        """TC-SRC-047: Vendor amend with negative price is rejected."""
        vendor_user = rbac_setup["users"][Role.VENDOR_USER]
        event = SourcingEvent.objects.create(
            event_number="EVT-2026-001",
            title="Laptops RFP",
            status=SourcingEvent.STATUS_BID_WINDOW,
            bid_start_date=timezone.now() - timezone.timedelta(days=1),
            bid_end_date=timezone.now() + timezone.timedelta(days=5),
            event_type=SourcingEvent.TYPE_RFP,
        )
        BidInvite.objects.create(event=event, vendor=rbac_setup["vendor"])
        bid = VendorBid.objects.create(
            event=event,
            vendor=rbac_setup["vendor"],
            bid_number="BID-2026-001",
            status=VendorBid.STATUS_SUBMITTED,
            total_bid_amount=Decimal("1000.00"),
        )
        client = APIClient()
        client.force_authenticate(user=vendor_user)
        response = client.post(
            f"/api/v1/sourcing-events/bids/{bid.id}/amend/",
            data={
                "amendment_reason": "Lower prices",
                "line_items": [
                    {
                        "item_description": "ThinkPad",
                        "quantity": 5,
                        "quoted_unit_price": "-100.00",
                    }
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ──────────────────────────────────────────────────────────────────────────
    # Group G: Purchase Orders (TC-PO-003, TC-PO-005, TC-PO-006, TC-PO-024, TC-WFL-003 / DEF-013, DEF-009, DEF-008, DEF-014)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_po_003_po_without_lines_rejected(self, rbac_setup):
        """TC-PO-003: Create PO without lines is rejected."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.PROC_MGR])
        response = client.post(
            "/api/v1/purchase-orders/",
            data={
                "vendor": str(rbac_setup["vendor"].id),
                "cost_center": str(rbac_setup["cc"].id),
                "lines": [],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_tc_po_005_po_negative_unit_price_rejected(self, rbac_setup):
        """TC-PO-005: Create PO with negative unit price is rejected."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.PROC_MGR])
        response = client.post(
            "/api/v1/purchase-orders/",
            data={
                "vendor": str(rbac_setup["vendor"].id),
                "cost_center": str(rbac_setup["cc"].id),
                "lines": [
                    {
                        "item_description": "Server Rack",
                        "quantity": 1,
                        "unit_price": "-500.00",
                    }
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_tc_po_006_and_tc_wfl_003_draft_vendor_po_rejected(self, rbac_setup):
        """TC-PO-006 & TC-WFL-003: PO cannot be created for a DRAFT vendor."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.PROC_MGR])
        response = client.post(
            "/api/v1/purchase-orders/",
            data={
                "vendor": str(rbac_setup["draft_vendor"].id),
                "cost_center": str(rbac_setup["cc"].id),
                "lines": [
                    {
                        "item_description": "Server Rack",
                        "quantity": 1,
                        "unit_price": "500.00",
                    }
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not ACTIVE" in str(response.json())

    def test_tc_po_024_amend_cancelled_po_refused(self, rbac_setup):
        """TC-PO-024: Amending a CANCELLED purchase order is refused."""
        po = PurchaseOrder.objects.create(
            po_number="PO-CANCELLED-01",
            vendor=rbac_setup["vendor"],
            cost_center=rbac_setup["cc"],
            status=PurchaseOrder.STATUS_CANCELLED,
            total_amount=Decimal("100.00"),
        )
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.PROC_MGR])
        response = client.post(
            f"/api/v1/purchase-orders/{po.id}/amend/",
            data={"reason": "Revive and change lines"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ──────────────────────────────────────────────────────────────────────────
    # Group H: Goods Receipts (TC-GRN-004 / DEF-010)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_grn_004_receive_more_than_ordered_rejected(self, rbac_setup):
        """TC-GRN-004: Goods receipt quantity exceeding ordered quantity is rejected."""
        po = PurchaseOrder.objects.create(
            po_number="PO-GRN-TEST-01",
            vendor=rbac_setup["vendor"],
            cost_center=rbac_setup["cc"],
            status=PurchaseOrder.STATUS_ISSUED,
            total_amount=Decimal("200.00"),
        )
        po_line = POLine.objects.create(
            po=po,
            item_description="Monitor",
            quantity=Decimal("2.00"),
            unit_price=Decimal("100.00"),
        )
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.STORES_RECEIVER])
        response = client.post(
            "/api/v1/receipts/",
            data={
                "po": str(po.id),
                "lines": [
                    {
                        "po_line_id": str(po_line.id),
                        "quantity_received": "999.00",
                        "quantity_accepted": "999.00",
                    }
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ──────────────────────────────────────────────────────────────────────────
    # Group I: Invoices (TC-INV-006 / DEF-011)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_inv_006_duplicate_invoice_number_rejected(self, rbac_setup):
        """TC-INV-006: Create invoice with duplicate invoice number is rejected."""
        po = PurchaseOrder.objects.create(
            po_number="PO-INV-TEST-01",
            vendor=rbac_setup["vendor"],
            cost_center=rbac_setup["cc"],
            status=PurchaseOrder.STATUS_ISSUED,
            total_amount=Decimal("100.00"),
        )
        SupplierInvoice.objects.create(
            vendor=rbac_setup["vendor"],
            po=po,
            invoice_number="INV-2026-DUP01",
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=30),
            subtotal=Decimal("100.00"),
            tax_amount=Decimal("10.00"),
            total_amount=Decimal("110.00"),
        )
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.FINANCE_AP])
        response = client.post(
            "/api/v1/invoices/",
            data={
                "vendor": str(rbac_setup["vendor"].id),
                "po": str(po.id),
                "invoice_number": "INV-2026-DUP01",
                "invoice_date": str(timezone.now().date()),
                "due_date": str(timezone.now().date() + timezone.timedelta(days=30)),
                "subtotal": "100.00",
                "tax_amount": "10.00",
                "total_amount": "110.00",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ──────────────────────────────────────────────────────────────────────────
    # Group J: Reports & Dashboards (TC-RPT-018, 022, 024, 039, TC-DSH-036 / DEF-007, DEF-005)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_rpt_vendor_reports_endpoints_forbidden(self, rbac_setup):
        """TC-RPT-018, 022, 024: Reports closed to VENDOR_USER."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.VENDOR_USER])
        endpoints = [
            "/api/v1/reports/receipt-delivery-summary/",
            "/api/v1/reports/contract-expiry/",
            "/api/v1/reports/contract-obligation/",
        ]
        for ep in endpoints:
            response = client.get(ep)
            assert response.status_code == status.HTTP_403_FORBIDDEN, f"Expected 403 for {ep}"

    def test_tc_rpt_039_ui_rbac_vendor_reports_hub_denied(self, rbac_setup):
        """TC-RPT-039: UI RBAC - VENDOR_USER cannot open the reports hub (/reports/)."""
        client = Client()
        client.force_login(rbac_setup["users"][Role.VENDOR_USER])
        response = client.get("/reports/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_tc_dsh_036_vendor_user_denied_requisition_list_ui(self, rbac_setup):
        """TC-DSH-036: Vendor portal user is denied /requisitions/."""
        client = Client()
        client.force_login(rbac_setup["users"][Role.VENDOR_USER])
        response = client.get("/requisitions/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ──────────────────────────────────────────────────────────────────────────
    # Group K: Audit Trail & Exports (TC-AUD-059 / DEF-020)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_aud_059_auditor_post_export_allowed(self, rbac_setup):
        """TC-AUD-059: Auditor POST /api/v1/audit/logs/export/ allowed."""
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.AUDITOR])
        response = client.post(
            "/api/v1/audit/logs/export/",
            data={"export_type": "audit_logs", "export_format": "csv"},
            format="json",
        )
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED)

    # ──────────────────────────────────────────────────────────────────────────
    # Group L: File Upload & Security (TC-UPL-015, TC-UPL-016, TC-SEC-014 / DEF-018, DEF-002)
    # ──────────────────────────────────────────────────────────────────────────

    def test_tc_upl_015_contract_upload_empty_file_rejected(self, rbac_setup):
        """TC-UPL-015: Contract document upload rejects 0-byte file."""
        contract = Contract.objects.create(
            contract_number="CTR-2026-001",
            title="SaaS Agreement",
            vendor=rbac_setup["vendor"],
            contract_value=Decimal("50000.00"),
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=365),
            status=Contract.STATUS_DRAFT,
            contract_owner=rbac_setup["users"][Role.LEGAL_MGR],
        )
        empty_pdf = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.LEGAL_MGR])
        response = client.post(
            f"/api/v1/contracts/{contract.id}/upload-document/",
            data={"title": "Empty Doc", "file": empty_pdf},
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_tc_upl_016_contract_upload_disguised_executable_rejected(self, rbac_setup):
        """TC-UPL-016: Contract document upload rejects MZ executable disguised as .pdf."""
        contract = Contract.objects.create(
            contract_number="CTR-2026-002",
            title="Hardware SLA",
            vendor=rbac_setup["vendor"],
            contract_value=Decimal("50000.00"),
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=365),
            status=Contract.STATUS_DRAFT,
            contract_owner=rbac_setup["users"][Role.LEGAL_MGR],
        )
        fake_pdf = SimpleUploadedFile("fake.pdf", b"MZ\x90\x00\x03\x00\x00\x00This is an executable", content_type="application/pdf")
        client = APIClient()
        client.force_authenticate(user=rbac_setup["users"][Role.LEGAL_MGR])
        response = client.post(
            f"/api/v1/contracts/{contract.id}/upload-document/",
            data={"title": "Disguised Executable", "file": fake_pdf},
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_tc_sec_014_unauthenticated_kyc_download_blocked(self, rbac_setup):
        """TC-SEC-014: KYC documents in /media/vendor_documents/ are not publicly downloadable without authentication."""
        client = Client()
        response = client.get("/media/vendor_documents/2026/10/qa_pan_test.pdf")
        # Must be 401 or 403 (unauthenticated blocked)
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
