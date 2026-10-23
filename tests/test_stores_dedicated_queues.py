from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.orders.models import POLine, PurchaseOrder
from apps.organization.models import CostCenter, Department, Organization
from apps.receipts.services import (
    create_goods_receipt_service,
    handoff_goods_to_stock_service,
    record_inspection_service,
)
from apps.vendors.models import Vendor, VendorCategory


@pytest.fixture
def dedicated_queues_setup(db, db_roles):
    org = Organization.objects.create(name="Queue Test Org", code="ORG-Q-TEST")
    dept = Department.objects.create(organization=org, name="Receiving Dept", code="DEPT-Q-RECV")
    cost_center = CostCenter.objects.create(
        department=dept, code="CC-Q-RECV", name="Central Receiving"
    )
    category = VendorCategory.objects.create(name="Industrial", code="CAT-IND-Q")
    vendor = Vendor.objects.create(
        legal_name="Apex Logistics Inc",
        tax_identification_number="TIN-APEX-001",
        category=category,
        status=Vendor.STATUS_ACTIVE,
    )

    receiver = User.objects.create_user(
        email="stores_queue_officer@test.com",
        password="Password123!",
        role=db_roles[Role.STORES_RECEIVER],
    )

    po = PurchaseOrder.objects.create(
        po_number="PO-2026-Q-001",
        version=1,
        vendor=vendor,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_ISSUED,
        subtotal=Decimal("15000.00"),
        tax_amount=Decimal("1500.00"),
        total_amount=Decimal("16500.00"),
    )

    line1 = POLine.objects.create(
        po=po,
        item_description="Precision Sensors",
        quantity=Decimal("20.00"),
        quantity_received=Decimal("0.00"),
        unit_of_measure="EA",
        unit_price=Decimal("500.00"),
    )

    line2 = POLine.objects.create(
        po=po,
        item_description="Control Modules",
        quantity=Decimal("10.00"),
        quantity_received=Decimal("0.00"),
        unit_of_measure="EA",
        unit_price=Decimal("500.00"),
    )

    # 1. Create a GRN that is PENDING inspection
    grn_pending = create_goods_receipt_service(
        po=po,
        received_by=receiver,
        receipt_items=[
            {
                "po_line_id": str(line1.id),
                "quantity_received": Decimal("10.00"),
                "quantity_accepted": Decimal("10.00"),
                "notes": "First batch",
            }
        ],
        delivery_note_number="DN-PENDING-001",
        remarks="Awaiting inspection",
    )

    # 2. Create a second GRN that is inspected: Line 2 received, 8 accepted, 2 rejected
    grn_inspected = create_goods_receipt_service(
        po=po,
        received_by=receiver,
        receipt_items=[
            {
                "po_line_id": str(line2.id),
                "quantity_received": Decimal("10.00"),
                "quantity_accepted": Decimal("10.00"),
                "notes": "Second batch",
            }
        ],
        delivery_note_number="DN-INSPECTED-002",
        remarks="Inspected shipment",
    )

    receipt_line2 = grn_inspected.lines.first()
    record_inspection_service(
        receipt=grn_inspected,
        inspected_by=receiver,
        inspection_items=[
            {
                "receipt_line_id": str(receipt_line2.id),
                "passed": False,
                "inspection_notes": "2 units damaged in transit",
                "rejected_quantity": Decimal("2.00"),
                "rejection_reason": "Damaged casing",
                "returned_to_vendor": False,
            }
        ],
    )

    return {
        "receiver": receiver,
        "po": po,
        "line1": line1,
        "line2": line2,
        "grn_pending": grn_pending,
        "grn_inspected": grn_inspected,
    }


def test_quality_inspection_queue_authenticated(client, dedicated_queues_setup):
    receiver = dedicated_queues_setup["receiver"]
    client.force_login(receiver)

    url = reverse("receipts_inspection_queue")
    response = client.get(url)

    assert response.status_code == 200
    assert "Quality Inspection Queue" in response.content.decode()
    assert "DN-PENDING-001" in response.content.decode()
    assert "DN-INSPECTED-002" in response.content.decode()


def test_quality_inspection_queue_filtering(client, dedicated_queues_setup):
    receiver = dedicated_queues_setup["receiver"]
    client.force_login(receiver)

    url = reverse("receipts_inspection_queue")

    # Filter PENDING
    resp_pending = client.get(f"{url}?status=PENDING")
    assert resp_pending.status_code == 200
    content_pending = resp_pending.content.decode()
    assert "DN-PENDING-001" in content_pending
    assert "DN-INSPECTED-002" not in content_pending

    # Filter FAILED / REJECTED
    resp_rejected = client.get(f"{url}?status=FAILED")
    assert resp_rejected.status_code == 200
    content_rejected = resp_rejected.content.decode()
    assert "DN-INSPECTED-002" in content_rejected
    assert "DN-PENDING-001" not in content_rejected


def test_stock_handoff_queue_view(client, dedicated_queues_setup):
    receiver = dedicated_queues_setup["receiver"]
    client.force_login(receiver)

    url = reverse("receipts_stock_handoff_queue")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Stock Handoff Queue" in content
    # Both GRNs have accepted quantities > 0
    assert "DN-PENDING-001" in content
    assert "DN-INSPECTED-002" in content


def test_stock_handoff_queue_status_update(client, dedicated_queues_setup):
    receiver = dedicated_queues_setup["receiver"]
    client.force_login(receiver)

    grn_inspected = dedicated_queues_setup["grn_inspected"]

    # Hand off grn_inspected to stock
    handoff_goods_to_stock_service(
        receipt=grn_inspected,
        handed_off_by=receiver,
        storage_location="BIN-A12",
        handoff_notes="Posted to bin A12",
    )

    url = reverse("receipts_stock_handoff_queue")

    # Check HANDED_OFF filter
    resp_handed_off = client.get(f"{url}?status=HANDED_OFF")
    assert resp_handed_off.status_code == 200
    content_handed_off = resp_handed_off.content.decode()
    assert grn_inspected.grn_number in content_handed_off
    assert "BIN-A12" in content_handed_off


def test_rejections_queue_view(client, dedicated_queues_setup):
    receiver = dedicated_queues_setup["receiver"]
    client.force_login(receiver)

    url = reverse("receipts_rejections_queue")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Rejections & Vendor Returns Queue" in content
    assert "Damaged casing" in content
    assert "Precision Sensors" not in content  # Line 1 had 0 rejected
    assert "Control Modules" in content  # Line 2 had 2 rejected


def test_rejections_queue_search(client, dedicated_queues_setup):
    receiver = dedicated_queues_setup["receiver"]
    client.force_login(receiver)

    url = reverse("receipts_rejections_queue")

    # Search by reason
    resp_search = client.get(f"{url}?q=Damaged")
    assert resp_search.status_code == 200
    content = resp_search.content.decode()
    assert "Control Modules" in content

    # Search by non-existent keyword
    resp_none = client.get(f"{url}?q=NonExistentKeywordXYZ")
    assert resp_none.status_code == 200
    assert "No Rejections or Returns Found" in resp_none.content.decode()


def test_unauthenticated_queues_redirect_to_login(client):
    assert client.get(reverse("receipts_inspection_queue")).status_code == 302
    assert client.get(reverse("receipts_stock_handoff_queue")).status_code == 302
    assert client.get(reverse("receipts_rejections_queue")).status_code == 302
    assert client.get(reverse("receipts_returns_queue")).status_code == 302


def test_dashboard_renders_with_dedicated_queue_links(client, dedicated_queues_setup):
    receiver = dedicated_queues_setup["receiver"]
    client.force_login(receiver)

    response = client.get("/")
    assert response.status_code == 200
    content = response.content.decode()

    # Check that dedicated queue URLs are present in dashboard and sidebar
    assert reverse("receipts_inspection_queue") in content
    assert reverse("receipts_stock_handoff_queue") in content
    assert reverse("receipts_rejections_queue") in content
    assert reverse("orders_list") in content
    assert reverse("receipts_list") in content
    assert "Record GRN" not in content


def test_grn_detail_view_status_gated_actions(client, dedicated_queues_setup):
    receiver = dedicated_queues_setup["receiver"]
    grn_pending = dedicated_queues_setup["grn_pending"]
    grn_inspected = dedicated_queues_setup["grn_inspected"]
    client.force_login(receiver)

    # 1. Test Pending Inspection state
    resp_pending = client.get(f"/receipts/{grn_pending.id}/")
    assert resp_pending.status_code == 200
    pending_content = resp_pending.content.decode()
    assert "Pending Inspection" in pending_content
    assert "Quality Inspection" in pending_content
    assert f"/receipts/{grn_pending.id}/inspect/" in pending_content
    # Stock handoff must NOT be active while pending inspection
    assert f"/receipts/{grn_pending.id}/handoff/" not in pending_content
    assert "Stock Handoff Locked" in pending_content or "Pending Inspection" in pending_content
    assert "View PO" in pending_content

    # 2. Test Inspected with Accepted Goods state
    resp_inspected = client.get(f"/receipts/{grn_inspected.id}/")
    assert resp_inspected.status_code == 200
    inspected_content = resp_inspected.content.decode()
    assert "Hand Off to Stock" in inspected_content
    assert f"/receipts/{grn_inspected.id}/handoff/" in inspected_content
    assert "Quality Inspection" in inspected_content
    assert "View PO" in inspected_content

    # 3. Test Rejected Goods details
    assert "Damaged casing" in inspected_content
    assert "Rejected:" in inspected_content or "Rejection" in inspected_content
    assert "Return to Vendor" in inspected_content


def test_receipts_list_record_goods_receipt_action(client, dedicated_queues_setup):
    receiver = dedicated_queues_setup["receiver"]
    client.force_login(receiver)

    response = client.get(reverse("receipts_list"))
    assert response.status_code == 200
    content = response.content.decode()

    # Verify '+ Record Goods Receipt' button exists and points to orders_list
    assert "Record Goods Receipt" in content
    assert reverse("orders_list") in content
