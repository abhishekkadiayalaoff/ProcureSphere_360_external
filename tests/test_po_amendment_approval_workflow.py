from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.budgets.models import Budget, SpendLedger
from apps.notifications.models import Notification
from apps.orders.models import POAmendment, POLine, PurchaseOrder
from apps.orders.services import (
    acknowledge_purchase_order_service,
    amend_purchase_order_service,
    approve_po_amendment_service,
    generate_purchase_order_service,
    reject_po_amendment_service,
    request_po_amendment_service,
)
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.vendors.models import Vendor, VendorCategory


@pytest.fixture
def amendment_workflow_env(db):
    org = Organization.objects.create(name="Enterprise Global", code="ENT-GLB")
    dept = Department.objects.create(
        organization=org, name="IT Operations", code="IT-OPS"
    )
    cc = CostCenter.objects.create(
        department=dept, code="CC-IT-900", name="Infrastructure"
    )

    now = timezone.now().date()
    period = FiscalPeriod.objects.create(
        organization=org,
        name="FY2026-Q4",
        year=2026,
        period_number=4,
        start_date=now.replace(month=1, day=1),
        end_date=now.replace(month=12, day=31),
        is_closed=False,
    )

    budget = Budget.objects.create(
        cost_center=cc,
        fiscal_period=period,
        allocated_amount=Decimal("100000.00"),
        committed_amount=Decimal("0.00"),
        actual_amount=Decimal("0.00"),
    )

    category = VendorCategory.objects.create(name="IT Hardware", code="IT-HW")

    vendor = Vendor.objects.create(
        organization=org,
        category=category,
        legal_name="Global Tech Networks Inc",
        vendor_number="VND-AMEND-01",
        tax_identification_number="TIN-AMEND-01",
        status=Vendor.STATUS_ACTIVE,
    )

    role_mgr, _ = Role.objects.get_or_create(
        code=Role.PROC_MGR, defaults={"name": "Procurement Manager"}
    )
    role_exec, _ = Role.objects.get_or_create(
        code=Role.PROC_EXEC, defaults={"name": "Procurement Executive"}
    )
    role_vendor, _ = Role.objects.get_or_create(
        code=Role.VENDOR_USER, defaults={"name": "Vendor Representative"}
    )

    manager1 = User.objects.create_user(
        email="proc.mgr01@procuresphere.com",
        role=role_mgr,
        first_name="Alice",
        last_name="Manager",
    )
    manager2 = User.objects.create_user(
        email="proc.mgr02@procuresphere.com",
        role=role_mgr,
        first_name="Bob",
        last_name="Approver",
    )
    executive = User.objects.create_user(
        email="proc.exec01@procuresphere.com",
        role=role_exec,
        first_name="Charlie",
        last_name="Executive",
    )
    vendor_user = User.objects.create_user(
        email="rep@globaltech.com",
        role=role_vendor,
        vendor=vendor,
        first_name="Dave",
        last_name="VendorRep",
    )

    po = generate_purchase_order_service(
        vendor=vendor,
        cost_center=cc,
        line_items=[
            {
                "item_description": "Network Switches 24-Port",
                "quantity": Decimal("10.00"),
                "unit_price": Decimal("1000.00"),
            }
        ],
        created_by_user=executive,
    )
    # Total = 10,000 subtotal + 10% tax = 11,000
    assert po.total_amount == Decimal("11000.00")
    assert po.status == PurchaseOrder.STATUS_ISSUED

    # Vendor acknowledges initial PO
    po = acknowledge_purchase_order_service(
        po=po, vendor_user=vendor_user, acknowledgement_notes="Initial acceptance"
    )
    assert po.status == PurchaseOrder.STATUS_ACKNOWLEDGED

    return {
        "org": org,
        "dept": dept,
        "cc": cc,
        "budget": budget,
        "vendor": vendor,
        "manager1": manager1,
        "manager2": manager2,
        "executive": executive,
        "vendor_user": vendor_user,
        "po": po,
    }


@pytest.mark.django_db
def test_request_po_amendment_sets_pending_and_notifies_managers(
    amendment_workflow_env,
):
    env = amendment_workflow_env
    po = env["po"]
    orig_line = po.lines.first()

    # Executive requests amendment (increase qty from 10 to 15 -> proposed total $16,500, delta +$5,500)
    amendment = request_po_amendment_service(
        po=po,
        reason="Scope expansion: 5 additional switches for data center B",
        updated_line_items=[
            {
                "id": str(orig_line.id),
                "item_description": orig_line.item_description,
                "quantity": Decimal("15.00"),
                "unit_price": Decimal("1000.00"),
            }
        ],
        requested_by_user=env["executive"],
    )

    po.refresh_from_db()
    assert amendment.status == POAmendment.STATUS_PENDING
    assert amendment.delta_amount == Decimal("5500.00")
    assert po.status == PurchaseOrder.STATUS_AMENDMENT_PENDING
    # Version should not increment until approved
    assert po.version == 1

    # AuditLog must record pending amendment request (AuditLog orders by -timestamp, so first() is newest)
    log = AuditLog.objects.filter(
        target_model="PurchaseOrder", target_object_id=str(po.id)
    ).first()
    assert log is not None
    assert log.new_state["status"] == PurchaseOrder.STATUS_AMENDMENT_PENDING

    # Notification sent to Procurement Managers
    mgr_notif = Notification.objects.filter(
        recipient=env["manager1"],
        notification_type=Notification.TYPE_PO_AMENDMENT,
    ).last()
    assert mgr_notif is not None
    assert "Pending Approval" in mgr_notif.title


@pytest.mark.django_db
def test_separation_of_duties_enforced_on_po_amendment_approval(amendment_workflow_env):
    env = amendment_workflow_env
    po = env["po"]
    orig_line = po.lines.first()

    # Manager 1 requests amendment
    amendment = request_po_amendment_service(
        po=po,
        reason="Requested by manager",
        updated_line_items=[
            {
                "id": str(orig_line.id),
                "item_description": orig_line.item_description,
                "quantity": Decimal("12.00"),
                "unit_price": Decimal("1000.00"),
            }
        ],
        requested_by_user=env["manager1"],
    )

    # Manager 1 attempts to approve their own amendment -> MUST FAIL
    with pytest.raises(ValidationError, match="Separation of duties violation"):
        approve_po_amendment_service(
            amendment=amendment,
            approver=env["manager1"],
        )

    # Different manager (Manager 2) approves -> MUST SUCCEED
    updated_po = approve_po_amendment_service(
        amendment=amendment,
        approver=env["manager2"],
        comments="Approved by secondary manager.",
    )
    assert updated_po.version == 2
    amendment.refresh_from_db()
    assert amendment.status == POAmendment.STATUS_APPROVED
    assert amendment.approved_by == env["manager2"]


@pytest.mark.django_db
def test_po_amendment_approval_adjusts_budget_commitment_and_mandates_vendor_reack(
    amendment_workflow_env,
):
    env = amendment_workflow_env
    po = env["po"]
    budget = env["budget"]
    orig_line = po.lines.first()
    orig_line_id = orig_line.id

    budget.refresh_from_db()
    initial_commitment = budget.committed_amount
    assert initial_commitment == Decimal("11000.00")

    # Executive requests amendment (qty from 10 to 14: subtotal $14,000, tax $1,400, total $15,400, delta +$4,400)
    amendment = request_po_amendment_service(
        po=po,
        reason="Additional switches required",
        updated_line_items=[
            {
                "id": str(orig_line.id),
                "item_description": orig_line.item_description,
                "quantity": Decimal("14.00"),
                "unit_price": Decimal("1000.00"),
            }
        ],
        requested_by_user=env["executive"],
    )

    # Manager approves
    updated_po = approve_po_amendment_service(
        amendment=amendment,
        approver=env["manager1"],
        comments="Budget approved.",
    )

    po.refresh_from_db()
    budget.refresh_from_db()

    # 1. Version incremented
    assert po.version == 2
    assert po.total_amount == Decimal("15400.00")

    # 2. Line ID preserved
    line = po.lines.first()
    assert line.id == orig_line_id
    assert line.quantity == Decimal("14.00")

    # 3. Budget commitment updated by delta +$4,400 -> $15,400
    assert budget.committed_amount == Decimal("15400.00")
    ledger_entry = SpendLedger.objects.filter(
        budget=budget,
        reference_number=f"{po.po_number}-AMD1",
        entry_type=SpendLedger.ENTRY_COMMITMENT,
    ).last()
    assert ledger_entry is not None
    assert ledger_entry.amount == Decimal("4400.00")

    # 4. Mandatory vendor re-acknowledgement enforced
    assert po.status == PurchaseOrder.STATUS_ISSUED
    assert po.acknowledged_at is None
    assert po.acknowledged_by is None

    # Vendor re-acknowledges amended order
    ack_po = acknowledge_purchase_order_service(
        po=po,
        vendor_user=env["vendor_user"],
        acknowledgement_notes="V2 accepted with delivery extension.",
    )
    assert ack_po.status == PurchaseOrder.STATUS_ACKNOWLEDGED
    assert ack_po.acknowledged_at is not None
    assert ack_po.acknowledged_by == env["vendor_user"]


@pytest.mark.django_db
def test_po_amendment_rejection_reverts_po_status(amendment_workflow_env):
    env = amendment_workflow_env
    po = env["po"]
    orig_line = po.lines.first()

    assert po.status == PurchaseOrder.STATUS_ACKNOWLEDGED

    amendment = request_po_amendment_service(
        po=po,
        reason="Cost expansion request",
        updated_line_items=[
            {
                "id": str(orig_line.id),
                "item_description": orig_line.item_description,
                "quantity": Decimal("20.00"),
                "unit_price": Decimal("1000.00"),
            }
        ],
        requested_by_user=env["executive"],
    )

    po.refresh_from_db()
    assert po.status == PurchaseOrder.STATUS_AMENDMENT_PENDING

    # Manager rejects with mandatory reason
    reverted_po = reject_po_amendment_service(
        amendment=amendment,
        rejector=env["manager1"],
        reason="Budget freeze: Q4 expansion rejected by finance committee.",
    )

    po.refresh_from_db()
    amendment.refresh_from_db()

    # Reverted back to ACKNOWLEDGED
    assert po.status == PurchaseOrder.STATUS_ACKNOWLEDGED
    assert po.version == 1
    assert po.total_amount == Decimal("11000.00")

    assert amendment.status == POAmendment.STATUS_REJECTED
    assert (
        amendment.rejection_reason
        == "Budget freeze: Q4 expansion rejected by finance committee."
    )
    assert amendment.approved_by == env["manager1"]

    # Notification sent to requester
    exec_notif = Notification.objects.filter(
        recipient=env["executive"],
        notification_type=Notification.TYPE_PO_AMENDMENT,
    ).last()
    assert exec_notif is not None
    assert "Rejected" in exec_notif.title


@pytest.mark.django_db
def test_budget_exhaustion_blocks_po_amendment_request(amendment_workflow_env):
    env = amendment_workflow_env
    po = env["po"]
    budget = env["budget"]
    orig_line = po.lines.first()

    # Cap budget allocated to $12,000 (committed is already $11,000, so available is only $1,000)
    budget.allocated_amount = Decimal("12000.00")
    budget.save(update_fields=["allocated_amount"])

    # Proposed amendment requires +$11,000 delta (exceeds $1,000 available)
    with pytest.raises(ValidationError, match="Insufficient budget for cost center"):
        request_po_amendment_service(
            po=po,
            reason="Exorbitant expansion beyond budget",
            updated_line_items=[
                {
                    "id": str(orig_line.id),
                    "item_description": orig_line.item_description,
                    "quantity": Decimal("20.00"),
                    "unit_price": Decimal("1000.00"),
                }
            ],
            requested_by_user=env["executive"],
        )
