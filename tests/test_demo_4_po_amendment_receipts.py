from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.budgets.services import allocate_budget_service
from apps.orders.models import PurchaseOrder
from apps.orders.selectors import get_po_version_history
from apps.orders.services import (
    acknowledge_purchase_order_service,
    amend_purchase_order_service,
    generate_purchase_order_service,
)
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.receipts.services import create_goods_receipt_service
from apps.vendors.models import Vendor, VendorCategory


@pytest.mark.django_db
def test_demo_4_po_execution_amendment_versioning_and_receipts(db_roles):
    """
    Day-90 Acceptance Demonstration 4:
    Generate PO, amend it (versioning V1 -> V2), record partial and final receipts (GRN), and demonstrate preserved PO versions.
    """
    today = timezone.now().date()

    # 1. Setup Org, Cost Center, Vendor & Users
    org = Organization.objects.create(name="HPE Tech Solutions", code="HPE-US")
    dept = Department.objects.create(organization=org, name="Engineering", code="DEPT-ENG")
    cost_center = CostCenter.objects.create(department=dept, code="CC-ENG-101", name="R&D Lab")

    period = FiscalPeriod.objects.create(
        organization=org,
        year=today.year,
        period_number=1,
        name=f"FY-{today.year}-Q1",
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=60),
    )
    allocate_budget_service(
        cost_center=cost_center, fiscal_period=period, allocated_amount=Decimal("300000.00")
    )

    proc_exec = User.objects.create_user(
        email="proc_exec@hpe.com", password="Password123!", role=db_roles[Role.PROC_EXEC]
    )
    stores_receiver = User.objects.create_user(
        email="stores@hpe.com", password="Password123!", role=db_roles[Role.STORES_RECEIVER]
    )

    category = VendorCategory.objects.create(name="Networking Hardware", code="CAT-NET")
    vendor = Vendor.objects.create(
        legal_name="Cisco Systems Partner",
        tax_identification_number="TIN-CISCO-88",
        category=category,
        status=Vendor.STATUS_ACTIVE,
    )
    vendor_user = User.objects.create_user(
        email="vendor@cisco.com",
        password="Password123!",
        role=db_roles[Role.VENDOR_USER],
        vendor=vendor,
    )

    # 2. Generate Purchase Order (Version 1)
    po = generate_purchase_order_service(
        vendor=vendor,
        cost_center=cost_center,
        line_items=[
            {
                "item_description": "Enterprise Core Switches 48-Port",
                "quantity": 10,
                "unit_price": "5000.00",
            }
        ],
        created_by_user=proc_exec,
    )

    assert po.status == PurchaseOrder.STATUS_ISSUED
    assert po.version == 1
    assert po.subtotal == Decimal("50000.00")
    assert po.total_amount == Decimal("55000.00")  # Subtotal $50k + 10% Tax $5k

    # 3. Vendor Acknowledges PO
    po = acknowledge_purchase_order_service(po=po, vendor_user=vendor_user)
    assert po.status == PurchaseOrder.STATUS_ACKNOWLEDGED

    # 4. Issue Change Order Amendment (Update quantity from 10 to 12 -> Version 2)
    amend_purchase_order_service(
        po=po,
        reason="Scope change: additional 2 switches required for redundant datacenter rack.",
        updated_line_items=[
            {
                "item_description": "Enterprise Core Switches 48-Port",
                "quantity": 12,
                "unit_price": "5000.00",
            }
        ],
        requested_by_user=proc_exec,
    )

    po.refresh_from_db()
    assert po.version == 2
    assert po.subtotal == Decimal("60000.00")
    assert po.total_amount == Decimal("66000.00")

    # Verify PO Version History preserves V1 snapshot
    history = get_po_version_history(po.id)
    assert history.count() == 1
    snapshot = history.first().previous_version_snapshot
    assert snapshot["version"] == 1
    assert Decimal(snapshot["total_amount"]) == Decimal("55000.00")

    # 5. Record Partial Goods Receipt (GRN 1: 8 of 12 units) -> Status PARTIAL_RECEIPT
    po_line = po.lines.first()
    grn1 = create_goods_receipt_service(
        po=po,
        received_by=stores_receiver,
        receipt_items=[
            {
                "po_line_id": po_line.id,
                "quantity_received": 8,
                "quantity_accepted": 8,
                "inspection_notes": "Batch 1: 8 units passed physical quality inspection.",
            }
        ],
        delivery_note_number="DN-CISCO-001",
    )

    po.refresh_from_db()
    po_line.refresh_from_db()
    assert grn1.grn_number.startswith("GRN-")
    assert po_line.quantity_received == Decimal("8.00")
    assert po.status == PurchaseOrder.STATUS_PARTIAL_RECEIPT

    # 6. Record Final Goods Receipt (GRN 2: Remaining 4 of 12 units) -> Status COMPLETED
    create_goods_receipt_service(
        po=po,
        received_by=stores_receiver,
        receipt_items=[
            {
                "po_line_id": po_line.id,
                "quantity_received": 4,
                "quantity_accepted": 4,
                "inspection_notes": "Batch 2: Final 4 units delivered and accepted.",
            }
        ],
        delivery_note_number="DN-CISCO-002",
    )

    po.refresh_from_db()
    po_line.refresh_from_db()
    assert po_line.quantity_received == Decimal("12.00")
    assert po.status == PurchaseOrder.STATUS_COMPLETED

    # 7. Verify Audit Trail for Amendment and Receipts
    audit_records = AuditLog.objects.filter(
        target_model="PurchaseOrder", target_object_id=str(po.id)
    )
    assert audit_records.count() >= 3
