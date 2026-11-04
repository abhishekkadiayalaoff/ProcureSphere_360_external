import hashlib
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.audit.services import create_audit_log_service, export_auditor_data_service
from apps.budgets.models import Budget, SpendLedger
from apps.budgets.selectors import scope_budgets_queryset, scope_spend_ledger_queryset
from apps.invoices.models import SupplierInvoice
from apps.invoices.selectors import scope_invoices_queryset
from apps.orders.models import POLine, PurchaseOrder
from apps.orders.selectors import scope_purchase_orders_queryset
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.sourcing.models import AwardDecision, SourcingEvent, VendorBid
from apps.sourcing.services import approve_award_service, evaluate_and_award_sourcing_event_service
from apps.vendors.models import Vendor, VendorCategory


@pytest.fixture
def org_setup(db):
    org_a = Organization.objects.create(name="Enterprise Alpha", code="ORG-ALPHA")
    org_b = Organization.objects.create(name="Enterprise Beta", code="ORG-BETA")

    dept_a = Department.objects.create(organization=org_a, name="Engineering A", code="ENG-A")
    dept_b = Department.objects.create(organization=org_b, name="Marketing B", code="MKT-B")

    cc_a = CostCenter.objects.create(department=dept_a, code="CC-ENG-A", name="Engineering Cost Center")
    cc_b = CostCenter.objects.create(department=dept_b, code="CC-MKT-B", name="Marketing Cost Center")

    period = FiscalPeriod.objects.create(
        organization=org_a,
        name="FY2026-Q1",
        year=2026,
        period_number=1,
        start_date=timezone.now().date(),
        end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
    )

    role_mgr, _ = Role.objects.get_or_create(
        code=Role.PROC_MGR, defaults={"name": "Procurement Manager"}
    )
    role_auditor, _ = Role.objects.get_or_create(
        code=Role.AUDITOR, defaults={"name": "Compliance Auditor"}
    )

    mgr_a = User.objects.create_user(
        email="mgr.alpha@hpe.com",
        password="Password123!",
        role=role_mgr,
        department=dept_a,
        organization=org_a,
    )
    auditor_a = User.objects.create_user(
        email="auditor.alpha@hpe.com",
        password="Password123!",
        role=role_auditor,
        department=dept_a,
        organization=org_a,
    )
    mgr_b = User.objects.create_user(
        email="mgr.beta@hpe.com",
        password="Password123!",
        role=role_mgr,
        department=dept_b,
        organization=org_b,
    )

    category = VendorCategory.objects.create(name="IT Hardware", code="IT-HW")

    vendor_a = Vendor.objects.create(
        legal_name="Alpha Tech Solutions",
        trade_name="AlphaTech",
        category=category,
        organization=org_a,
        tax_identification_number="TIN-ALPHA-01",
        vendor_number="VND-ALPHA-01",
        status=Vendor.STATUS_ACTIVE,
        is_event_eligible=True,
    )
    vendor_b = Vendor.objects.create(
        legal_name="Beta Global Supplies",
        trade_name="BetaGlobal",
        category=category,
        organization=org_b,
        tax_identification_number="TIN-BETA-02",
        vendor_number="VND-BETA-02",
        status=Vendor.STATUS_ACTIVE,
        is_event_eligible=True,
    )

    # POs
    po_a = PurchaseOrder.objects.create(
        po_number="PO-ALPHA-001",
        vendor=vendor_a,
        cost_center=cc_a,
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("100.00"),
        total_amount=Decimal("1100.00"),
        status=PurchaseOrder.STATUS_ISSUED,
    )
    po_b = PurchaseOrder.objects.create(
        po_number="PO-BETA-001",
        vendor=vendor_b,
        cost_center=cc_b,
        subtotal=Decimal("2000.00"),
        tax_amount=Decimal("200.00"),
        total_amount=Decimal("2200.00"),
        status=PurchaseOrder.STATUS_ISSUED,
    )

    # Invoices
    inv_a = SupplierInvoice.objects.create(
        invoice_number="INV-ALPHA-01",
        vendor=vendor_a,
        po=po_a,
        invoice_date=timezone.now().date(),
        due_date=(timezone.now() + timezone.timedelta(days=30)).date(),
        subtotal=Decimal("1000.00"),
        total_amount=Decimal("1100.00"),
        status=SupplierInvoice.STATUS_RECEIVED,
    )
    inv_b = SupplierInvoice.objects.create(
        invoice_number="INV-BETA-01",
        vendor=vendor_b,
        po=po_b,
        invoice_date=timezone.now().date(),
        due_date=(timezone.now() + timezone.timedelta(days=30)).date(),
        subtotal=Decimal("2000.00"),
        total_amount=Decimal("2200.00"),
        status=SupplierInvoice.STATUS_RECEIVED,
    )

    # Budgets
    bgt_a = Budget.objects.create(
        cost_center=cc_a,
        fiscal_period=period,
        allocated_amount=Decimal("50000.00"),
        committed_amount=Decimal("1100.00"),
    )
    bgt_b = Budget.objects.create(
        cost_center=cc_b,
        fiscal_period=period,
        allocated_amount=Decimal("40000.00"),
        committed_amount=Decimal("2200.00"),
    )

    # Spend Ledger
    ledger_a = SpendLedger.objects.create(
        budget=bgt_a,
        entry_type=SpendLedger.ENTRY_COMMITMENT,
        amount=Decimal("1100.00"),
        reference_number="PO-ALPHA-001",
        description="Commitment for PO-ALPHA-001",
    )
    ledger_b = SpendLedger.objects.create(
        budget=bgt_b,
        entry_type=SpendLedger.ENTRY_COMMITMENT,
        amount=Decimal("2200.00"),
        reference_number="PO-BETA-001",
        description="Commitment for PO-BETA-001",
    )

    return {
        "org_a": org_a,
        "org_b": org_b,
        "mgr_a": mgr_a,
        "auditor_a": auditor_a,
        "mgr_b": mgr_b,
        "po_a": po_a,
        "po_b": po_b,
        "inv_a": inv_a,
        "inv_b": inv_b,
        "bgt_a": bgt_a,
        "bgt_b": bgt_b,
        "ledger_a": ledger_a,
        "ledger_b": ledger_b,
        "vendor_a": vendor_a,
    }


@pytest.mark.django_db
class TestRoleBasedDataScoping:
    def test_auditor_and_manager_cannot_access_cross_org_pos(self, org_setup):
        auditor = org_setup["auditor_a"]
        mgr = org_setup["mgr_a"]

        scoped_for_auditor = scope_purchase_orders_queryset(PurchaseOrder.objects.all(), auditor)
        scoped_for_mgr = scope_purchase_orders_queryset(PurchaseOrder.objects.all(), mgr)

        assert org_setup["po_a"] in scoped_for_auditor
        assert org_setup["po_b"] not in scoped_for_auditor

        assert org_setup["po_a"] in scoped_for_mgr
        assert org_setup["po_b"] not in scoped_for_mgr

    def test_auditor_and_manager_cannot_access_cross_org_invoices(self, org_setup):
        auditor = org_setup["auditor_a"]
        mgr = org_setup["mgr_a"]

        scoped_for_auditor = scope_invoices_queryset(SupplierInvoice.objects.all(), auditor)
        scoped_for_mgr = scope_invoices_queryset(SupplierInvoice.objects.all(), mgr)

        assert org_setup["inv_a"] in scoped_for_auditor
        assert org_setup["inv_b"] not in scoped_for_auditor

        assert org_setup["inv_a"] in scoped_for_mgr
        assert org_setup["inv_b"] not in scoped_for_mgr

    def test_auditor_and_manager_cannot_access_cross_org_budgets(self, org_setup):
        auditor = org_setup["auditor_a"]
        mgr = org_setup["mgr_a"]

        scoped_budgets = scope_budgets_queryset(Budget.objects.all(), auditor)
        assert org_setup["bgt_a"] in scoped_budgets
        assert org_setup["bgt_b"] not in scoped_budgets

        scoped_ledger = scope_spend_ledger_queryset(SpendLedger.objects.all(), auditor)
        assert org_setup["ledger_a"] in scoped_ledger
        assert org_setup["ledger_b"] not in scoped_ledger


@pytest.mark.django_db
class TestAuditLogImmutability:
    def test_bulk_delete_and_update_are_strictly_blocked(self, org_setup):
        log = create_audit_log_service(
            actor=org_setup["auditor_a"],
            action=AuditLog.ACTION_EXPORT,
            target_model="AuditorExport",
            target_object_id="test-123",
            new_state={"sample": "data"},
        )

        # 1. Bulk update prevention
        with pytest.raises(ValidationError, match="Bulk updates are strictly prohibited"):
            AuditLog.objects.filter(id=log.id).update(action="HACKED")

        # 2. Bulk delete prevention
        with pytest.raises(ValidationError, match="Bulk deletions are strictly prohibited"):
            AuditLog.objects.filter(id=log.id).delete()

        # 3. Instance delete prevention
        with pytest.raises((PermissionError, ValidationError)):
            log.delete()

        # Verify record remains unchanged in DB
        log.refresh_from_db()
        assert log.action == AuditLog.ACTION_EXPORT

    def test_report_export_generates_immutable_checksum_and_reference(self, org_setup):
        res = export_auditor_data_service(
            export_type="vendor_compliance",
            export_format="csv",
            actor=org_setup["auditor_a"],
        )

        assert "export_ref_id" in res
        assert "checksum" in res
        assert res["algorithm"] == "SHA-256"

        # Verify sha256 calculation matches actual content
        expected_hash = hashlib.sha256(res["content"].encode("utf-8")).hexdigest()
        assert res["checksum"] == expected_hash

        # Verify immutable AuditLog was written with the reference and checksum
        audit_entry = AuditLog.objects.filter(
            target_model="AuditorExport",
            target_object_id=res["export_ref_id"],
        ).first()

        assert audit_entry is not None
        assert audit_entry.new_state["checksum"] == expected_hash
        assert audit_entry.new_state["export_ref_id"] == res["export_ref_id"]


@pytest.mark.django_db
class TestAwardSeparationOfDuties:
    def test_recommender_cannot_approve_their_own_award(self, org_setup):
        mgr = org_setup["mgr_a"]
        vendor = org_setup["vendor_a"]

        event = SourcingEvent.objects.create(
            title="Hardware Tender",
            event_type=SourcingEvent.TYPE_RFQ,
            status=SourcingEvent.STATUS_COMMERCIAL_REVIEW,
            created_by=mgr,
            bid_start_date=timezone.now() - timezone.timedelta(days=2),
            bid_end_date=timezone.now() - timezone.timedelta(days=1),
        )
        bid = VendorBid.objects.create(
            event=event,
            vendor=vendor,
            status=VendorBid.STATUS_SUBMITTED,
            total_bid_amount=Decimal("15000.00"),
        )
        decision = AwardDecision.objects.create(
            event=event,
            winning_bid=bid,
            award_reason="Best value",
            status=AwardDecision.STATUS_PENDING,
            recommended_by=mgr,
            created_by=mgr,
        )
        event.status = SourcingEvent.STATUS_AWARD_APPROVAL
        event.save()

        # Manager trying to approve their own recommendation must fail
        with pytest.raises(ValidationError, match="Separation of duties violation"):
            approve_award_service(event=event, approver=mgr, comments="Self-approval")

    def test_different_manager_can_approve_award(self, org_setup):
        mgr_recommender = org_setup["mgr_a"]
        mgr_approver = org_setup["mgr_b"]
        vendor = org_setup["vendor_a"]

        event = SourcingEvent.objects.create(
            title="Software Tender",
            event_type=SourcingEvent.TYPE_RFQ,
            status=SourcingEvent.STATUS_AWARD_APPROVAL,
            created_by=mgr_recommender,
            bid_start_date=timezone.now() - timezone.timedelta(days=2),
            bid_end_date=timezone.now() - timezone.timedelta(days=1),
        )
        bid = VendorBid.objects.create(
            event=event,
            vendor=vendor,
            status=VendorBid.STATUS_SUBMITTED,
            total_bid_amount=Decimal("18000.00"),
        )
        decision = AwardDecision.objects.create(
            event=event,
            winning_bid=bid,
            award_reason="Best value proposal",
            status=AwardDecision.STATUS_PENDING,
            recommended_by=mgr_recommender,
            created_by=mgr_recommender,
        )

        approved = approve_award_service(event=event, approver=mgr_approver, comments="Approved by board")
        assert approved.status == AwardDecision.STATUS_APPROVED
        assert approved.approved_by == mgr_approver
